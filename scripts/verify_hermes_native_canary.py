#!/usr/bin/env python3
"""Exercise Hermes' native lazy MCP path in an isolated home without a model turn.

Run once with --phase initial, then in a new process with --phase restored and the
reported session id. The second process is the real native-process restart boundary.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ROOT = Path(os.environ.get("HERMES_NATIVE_ROOT", Path.home() / ".hermes" / "hermes-agent"))
CANARY_HOME = Path(os.environ.get("HERMES_CANARY_HOME", ROOT / ".runtime" / "lazy-discovery" / "hermes-canary-home"))
FIXTURE = ROOT / "bridge" / "tests" / "canary_mcp_server.py"
EVENTS = CANARY_HOME / "canary-events.jsonl"
os.environ["HERMES_HOME"] = str(CANARY_HOME)
os.environ["HERMES_RUNTIME_DIR"] = os.environ.get("HERMES_CANARY_RUNTIME_DIR", str(CANARY_HOME))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(NATIVE_ROOT))
sys.path.insert(0, str(ROOT / "bridge"))
sys._hermes_pin_default_home = True

import hermes_bootstrap  # noqa: F401,E402 — initializes the pinned native dependencies.

from army_bridge.tool_metrics import compare_schema_surfaces  # noqa: E402


def prepare_home() -> None:
    CANARY_HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    CANARY_HOME.chmod(0o700)
    source_env = ROOT / ".runtime" / "lazy-discovery" / "hermes-home" / ".env"
    if source_env.exists() and not (CANARY_HOME / ".env").exists():
        shutil.copyfile(source_env, CANARY_HOME / ".env")
        (CANARY_HOME / ".env").chmod(0o600)
    config = f"""model:
  default: deepseek-v4-pro
  provider: auto
  base_url: ""
mcp_servers:
  approval-canary:
    command: {json.dumps(sys.executable)}
    args:
      - {json.dumps(str(FIXTURE))}
    env:
      CANARY_MODE: approval
      CANARY_EVENTS_PATH: {json.dumps(str(EVENTS))}
    trust: untrusted
platform_toolsets:
  acp:
    - mcp-approval-canary
tools:
  tool_search:
    enabled: auto
memory:
  memory_enabled: false
  user_profile_enabled: false
telemetry:
  shared_metrics:
    enabled: false
    send: false
plugins:
  enabled: []
  disabled: []
"""
    path = CANARY_HOME / "config.yaml"
    path.write_text(config, encoding="utf-8")
    path.chmod(0o600)


def read_events() -> list[str]:
    if not EVENTS.exists():
        return []
    return [json.loads(line)["event"] for line in EVENTS.read_text(encoding="utf-8").splitlines() if line]


def tool_name(definitions: list[dict[str, Any]], suffix: str) -> str:
    matches = [item["function"]["name"] for item in definitions if item["function"].get("name", "").endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one native tool ending in {suffix}; found {matches}")
    return matches[0]


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


async def run(phase: str, session_id: str | None, output: Path) -> None:
    from acp.schema import McpServerStdio
    from acp_adapter.server import HermesACPAgent
    from acp_adapter.session import SessionManager
    from hermes_cli.mcp_startup import ensure_mcp_discovery_before_agent_build
    import logging
    import model_tools
    from tools.mcp_tool_lifecycle import shutdown_mcp_servers

    prepare_home()
    ensure_mcp_discovery_before_agent_build(logger=logging.getLogger("army-hub-native-canary"))
    server = HermesACPAgent(session_manager=SessionManager())

    def declaration(version: str) -> McpServerStdio:
        return McpServerStdio(
            name="army-canary", command=sys.executable, args=[str(FIXTURE)],
            env=[
                {"name": "CANARY_EVENTS_PATH", "value": str(EVENTS)},
                {"name": "CANARY_SCHEMA_VERSION", "value": version},
            ],
        )

    if phase == "initial":
        response = await server.new_session(cwd=str(ROOT), mcp_servers=[declaration("v1")])
        session_id = response.session_id
    else:
        if not session_id:
            raise ValueError("--session-id is required for the restored phase")
        await server.load_session(cwd=str(ROOT), session_id=session_id, mcp_servers=[declaration("v2")])
    state = server.session_manager.get_session(session_id)
    if state is None:
        raise AssertionError("Native ACP session was not available")
    if phase == "initial" and not state.history:
        # Hermes deliberately keeps contentless ACP probes ephemeral. Persist one
        # synthetic fixture turn in the isolated DB so a fresh process can test
        # session/load without paying for a model-generated history entry.
        state.history = [{"role": "user", "content": "Offline canary restore fixture; no model turn."}]
        db = server.session_manager._get_db()
        db.create_session(session_id=session_id, source="acp", model=str(state.model), cwd=str(ROOT))
        db.replace_messages(session_id, state.history)
    native_agent = state.agent
    observed_calls: list[dict[str, str]] = []
    original_emit = model_tools._emit_post_tool_call_hook

    def capture_emit(**kwargs: Any) -> Any:
        observed_calls.append({
            "tool_name": str(kwargs.get("function_name")),
            "session_id": str(kwargs.get("session_id")),
        })
        return original_emit(**kwargs)

    model_tools._emit_post_tool_call_hook = capture_emit
    approval_requests: list[str] = []
    import tools.approval_prompt as approval_prompt
    original_consent = approval_prompt.request_elicitation_consent

    def cancelled_consent(*args: Any, **kwargs: Any) -> str:
        approval_requests.append(str(kwargs.get("surface") or "mcp-trust"))
        return "cancel"

    approval_prompt.request_elicitation_consent = cancelled_consent

    def definitions() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        kwargs = {
            "enabled_toolsets": native_agent.enabled_toolsets,
            "disabled_toolsets": getattr(native_agent, "disabled_toolsets", None),
            "quiet_mode": True,
        }
        raw = model_tools.get_tool_definitions(**kwargs, skip_tool_search_assembly=True) or []
        advertised = model_tools.get_tool_definitions(**kwargs, skip_tool_search_assembly=False) or []
        return raw, advertised

    def dispatch(name: str, arguments: dict[str, Any]) -> str:
        return model_tools.handle_function_call(
            name, arguments, session_id=session_id,
            enabled_toolsets=native_agent.enabled_toolsets,
            disabled_toolsets=getattr(native_agent, "disabled_toolsets", None),
        )

    def discover_and_call(raw: list[dict[str, Any]], expected_marker: str) -> dict[str, Any]:
        name = tool_name(raw, "canary_status")
        search = json.loads(dispatch("tool_search", {"queries": ["canary readiness"], "limit": 5}))
        assert name in search["results"][0]["matches"], search
        described = json.loads(dispatch("tool_describe", {"names": [name]}))
        assert name in described["tools"], described
        result = dispatch("tool_call", {"calls": [{"name": name, "arguments": {}}]})
        assert expected_marker in result, result
        return {"tool_name": name, "search_hit": True, "describe_hit": True, "exact_marker": expected_marker}

    try:
        raw, advertised = definitions()
        comparison = compare_schema_surfaces(raw, advertised)
        status_name = tool_name(raw, "canary_status")
        assert status_name in comparison["deferred"]["tool_names"]
        assert status_name not in comparison["advertised"]["tool_names"]
        execution = discover_and_call(raw, "HERMES-MCP-CANARY-OK" if phase == "initial" else "HERMES-MCP-CANARY-V2-OK")
        checks: dict[str, Any] = {
            "mcp_tool_deferred_and_discoverable": True,
            "real_dispatcher_returned_exact_marker": True,
        }

        if phase == "initial":
            approval_name = tool_name(raw, "approval_probe")
            approval_result = dispatch("tool_call", {"calls": [{"name": approval_name, "arguments": {}}]})
            assert "NOT run" in approval_result, approval_result
            assert approval_requests, "Untrusted MCP approval path was not reached"
            assert "approval_executed" not in read_events(), "Cancelled approval probe executed"
            checks["untrusted_approval_cancelled_without_execution"] = True

            before_loss = read_events().count("canary_executed")
            shutdown_mcp_servers(names={"army-canary"})
            missing_raw, missing_advertised = definitions()
            missing_names = {item["function"]["name"] for item in missing_raw + missing_advertised}
            assert status_name not in missing_names
            missing_result = dispatch("tool_call", {"calls": [{"name": status_name, "arguments": {}}]})
            assert "error" in json.loads(missing_result), missing_result
            assert "HERMES-MCP-CANARY" not in missing_result
            assert read_events().count("canary_executed") == before_loss
            checks["server_loss_removed_tool_and_blocked_call"] = True

            await server._attach_session_mcp(state, [declaration("v2")], "Canary schema refresh %s", session_id)
            changed_raw, changed_advertised = definitions()
            changed_comparison = compare_schema_surfaces(changed_raw, changed_advertised)
            assert changed_comparison["raw"]["sha256"] != comparison["raw"]["sha256"]
            changed_execution = discover_and_call(changed_raw, "HERMES-MCP-CANARY-V2-OK")
            checks["schema_change_refreshed_hash_and_v2_result"] = True
            comparison = changed_comparison
            execution = changed_execution

        matching_observations = [
            item for item in observed_calls if item["tool_name"].endswith("canary_status")
        ]
        assert matching_observations and all(item["session_id"] == session_id for item in matching_observations)
        checks["downstream_hook_observed_real_tool_and_original_session"] = True
        usage = server._build_usage_update(state)
        report = {
            "phase": phase,
            "session_id": session_id,
            "native_revision": subprocess.run(
                ["git", "-C", str(NATIVE_ROOT), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip(),
            "config_sha256": hashlib.sha256((CANARY_HOME / "config.yaml").read_bytes()).hexdigest(),
            "schema_comparison": comparison,
            "execution": execution,
            "checks": checks,
            "approval_request_count": len(approval_requests),
            "canary_execution_count": read_events().count("canary_executed"),
            "approval_execution_count": read_events().count("approval_executed"),
            "acp_context_usage": (
                {"kind": "native_estimate_computed_without_turn", "size": usage.size, "used": usage.used}
                if usage is not None else "unavailable_without_a_turn"
            ),
            "provider_token_usage": "unavailable_no_provider_turn_was_made",
            "paid_model_turn": False,
            "native_process_restart_verified": phase == "restored",
        }
        write_report(output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        approval_prompt.request_elicitation_consent = original_consent
        model_tools._emit_post_tool_call_hook = original_emit
        shutdown_mcp_servers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["initial", "restored"], required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.phase, args.session_id, args.output))


if __name__ == "__main__":
    main()

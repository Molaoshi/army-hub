#!/usr/bin/env python3
"""Measure Hermes' real raw and native-lazy tool arrays without starting a model turn."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ROOT = Path(os.environ.get("HERMES_NATIVE_ROOT", Path.home() / ".hermes" / "hermes-agent"))
sys.path.insert(0, str(NATIVE_ROOT))
sys.path.insert(0, str(ROOT / "bridge"))
sys._hermes_pin_default_home = True

import hermes_bootstrap  # Initializes Hermes' managed dependencies without starting the CLI.

from army_bridge.tool_metrics import compare_schema_surfaces


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional owner-local JSON report path")
    args = parser.parse_args()

    from acp_adapter.session import _expand_acp_enabled_toolsets
    from agent.skill_utils import parse_config_string_list
    from hermes_cli.config import load_config_readonly
    from hermes_cli.mcp_startup import ensure_mcp_discovery_before_agent_build
    from hermes_cli.tools_config import _get_platform_tools, enabled_mcp_server_names
    from model_tools import get_tool_definitions

    # This performs native tool/MCP discovery only. It never creates a completion.
    ensure_mcp_discovery_before_agent_build(logger=logging.getLogger("army-hub-schema-baseline"))
    config = load_config_readonly()
    resolved = _get_platform_tools(config, "acp")
    configured_mcp = resolved & enabled_mcp_server_names(config)
    enabled = _expand_acp_enabled_toolsets(sorted(resolved - configured_mcp), sorted(configured_mcp))
    disabled = parse_config_string_list((config.get("agent") or {}).get("disabled_toolsets")) or None
    raw = get_tool_definitions(
        enabled_toolsets=enabled, disabled_toolsets=disabled, quiet_mode=True,
        skip_tool_search_assembly=True,
    ) or []
    advertised = get_tool_definitions(
        enabled_toolsets=enabled, disabled_toolsets=disabled, quiet_mode=True,
        skip_tool_search_assembly=False,
    ) or []
    native_revision = subprocess.run(
        ["git", "-C", str(NATIVE_ROOT), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    config_path = hermes_home / "config.yaml"
    report = {
        "native_revision": native_revision,
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "enabled_toolsets": sorted(enabled),
        "disabled_toolsets": sorted(disabled or []),
        "native_tool_search_config": (config.get("tools") or {}).get("tool_search"),
        "schema_comparison": compare_schema_surfaces(raw, advertised),
        "acp_context_usage": "not_emitted_without_a_turn",
        "provider_token_usage": "unavailable_without_inspecting_provider_reports",
        "paid_model_turn": False,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.write_text(rendered, encoding="utf-8")
        args.output.chmod(0o600)
    print(rendered, end="")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any

import yaml

from .inventory import opencode_cli, opencode_runtime_environment
from .store import ManagerStore


class ConnectorError(RuntimeError):
    pass


class ConnectorManager:
    def __init__(self, root: Path, store: ManagerStore):
        self.root = root
        self.workspace = root.parent
        self.runtime = root / ".runtime"
        self.store = store
        self.python = root / ".venv-service" / "bin" / "python"

    def pid_path(self, agent_id: str) -> Path:
        return self.runtime / f"{agent_id}.pid"

    def pid(self, agent_id: str) -> int | None:
        try:
            pid = int(self.pid_path(agent_id).read_text().strip())
            output = subprocess.check_output(["ps", "-p", str(pid), "-o", "state=", "-o", "command="], text=True, timeout=5)
            state, command = output.strip().split(None, 1)
            if not state.startswith("Z") and "army_bridge" in command and f"{agent_id}.yaml" in command:
                return pid
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return None

    def status(self, agent_id: str) -> dict[str, Any]:
        record = self.store.agent(agent_id)
        pid = self.pid(agent_id)
        return {"status": "online" if pid else ("paused" if record.get("status") == "paused" else "offline"),
                "pid": pid, "managed": bool(record.get("managed"))}

    def render_config(self, record: dict[str, Any], matrix_record: dict[str, Any]) -> None:
        agent_id = record["id"]
        all_users = ["@mo:army.local", *[item["mxid"] for item in self.store.agents() if item["id"] != agent_id]]
        session_config: dict[str, str] = {}
        if record["harness"] == "hermes":
            command = [str(Path.home() / ".local" / "bin" / "hermes"), "acp"]
            environment = {"HERMES_ACCEPT_HOOKS": "1", "HERMES_INFERENCE_MODEL": record["model"]}
            session_config = {"model": f"{record.get('provider') or 'auto'}:{record['model']}"}
            if record.get("effort"):
                session_config["reasoning_effort"] = record["effort"]
        elif record["harness"] == "dsh":
            if record.get("provider") not in {None, "deepseek-official"}:
                raise ConnectorError("DSH currently supports only its DeepSeek Official provider")
            command = [str(self.workspace / ".runtime" / "dsh-acp.sh")]
            environment = {"NO_BROWSER": "1", "DSH_MODEL": record["model"]}
            session_config = {"model": f"deepseek-official::{record['model']}"}
            if record.get("effort"):
                session_config["effort"] = record["effort"]
        elif record["harness"] == "opencode":
            cli = opencode_cli()
            if not cli:
                raise ConnectorError("OpenCode CLI is unavailable")
            command = [str(cli), "acp"]
            environment = opencode_runtime_environment({})
            session_config = {"model": record["model"]}
            if record.get("effort"):
                session_config["effort"] = record["effort"]
        else:
            raise ConnectorError("Unsupported harness")
        project = next((item for item in yaml.safe_load((self.root / "projects" / "registry.yaml").read_text())["projects"].items()
                        if item[0] == record["project"]), None)
        if not project:
            raise ConnectorError("Selected project is not registered")
        cwd = project[1]["local_paths"].get(record["machine"])
        if not cwd or not Path(cwd).is_dir():
            raise ConnectorError("Selected project is unavailable on this machine")
        config = {
            "matrix": {
                "homeserver": "http://127.0.0.1:8010", "user_id": matrix_record["mxid"],
                "access_token": matrix_record["access_token"], "device_id": matrix_record.get("device_id"),
                "allowed_users": all_users, "allowed_rooms": record["rooms"],
            },
            "agent": {"id": agent_id, "display_name": record["display_name"], "command": command,
                      "cwd": cwd, "environment": environment, "session_config": session_config},
            "policy": {"max_agent_turns": 6, "min_turn_interval_seconds": 2,
                       "prompt_timeout_seconds": 600, "allow_agent_senders": True, "max_message_chars": 40000},
            "state_path": str(self.runtime / f"{agent_id}-state.json"),
        }
        path = self.runtime / f"{agent_id}.yaml"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)

    def start(self, agent_id: str) -> dict[str, Any]:
        record = self.store.agent(agent_id)
        if record.get("status") == "reserved":
            raise ConnectorError("Reserved identities need a complete configuration before starting")
        if self.pid(agent_id):
            return self.status(agent_id)
        config = self.runtime / f"{agent_id}.yaml"
        if not config.exists():
            raise ConnectorError("Connector configuration is missing")
        log = (self.runtime / f"{agent_id}.log").open("ab")
        process = subprocess.Popen([str(self.python), "-m", "army_bridge", "--config", str(config)],
                                   cwd=self.root / "bridge", stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        log.close()
        self.pid_path(agent_id).write_text(str(process.pid), encoding="utf-8")
        time.sleep(0.4)
        if process.poll() is not None:
            raise ConnectorError("Connector exited during startup; inspect its sanitized log")
        record["status"] = "active"
        self.store.put_agent(record)
        self.store.audit("@mo:army.local", agent_id, "connector.start", "started")
        return self.status(agent_id)

    def _wait_for_stop(self, agent_id: str, attempts: int) -> bool:
        for _ in range(attempts):
            if not self.pid(agent_id):
                return True
            time.sleep(0.1)
        return not self.pid(agent_id)

    def stop(self, agent_id: str, pause: bool = False) -> dict[str, Any]:
        record = self.store.agent(agent_id)
        if record.get("status") == "reserved":
            raise ConnectorError("Reserved identity has no connector to manage")
        pid = self.pid(agent_id)
        result = "paused" if pause else "stopped"
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            if not self._wait_for_stop(agent_id, 100) and self.pid(agent_id):
                # start() creates one isolated session per connector; never signal another group.
                if os.getpgid(pid) != pid:
                    raise ConnectorError("Connector process group is not isolated; refusing forced shutdown")
                os.killpg(pid, signal.SIGKILL)
                result = "paused after forced shutdown" if pause else "stopped after forced shutdown"
            if not self._wait_for_stop(agent_id, 50):
                raise ConnectorError("Connector remains active after forced shutdown; PID state retained for retry")
        self.pid_path(agent_id).unlink(missing_ok=True)
        record["status"] = "paused" if pause else record.get("status", "active")
        self.store.put_agent(record)
        self.store.audit("@mo:army.local", agent_id, "connector.stop", result)
        return self.status(agent_id)

    def restart(self, agent_id: str) -> dict[str, Any]:
        self.stop(agent_id)
        return self.start(agent_id)

    def log(self, agent_id: str, lines: int = 120) -> str:
        self.store.agent(agent_id)
        path = self.runtime / f"{agent_id}.log"
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Matrix access tokens are never expected in logs; redact common bearer forms defensively.
        import re
        return "\n".join(re.sub(r"(?i)(bearer\s+)[A-Za-z0-9_\-.=]+", r"\1[redacted]", line)
                         for line in content[-min(lines, 300):])

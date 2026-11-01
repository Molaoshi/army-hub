from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import select
import subprocess
import time
from typing import Any, Callable
from urllib import error as urlerror
from urllib import request as urlrequest

import yaml


class InventoryError(RuntimeError):
    pass


def opencode_cli() -> Path | None:
    """Find the desktop-managed CLI without pinning its version directory."""
    candidates = list(Path.home().glob("Library/Application Support/ai.opencode.desktop/cli/*/opencode-cli"))
    executable = [path for path in candidates if path.is_file() and os.access(path, os.X_OK)]
    if not executable:
        return None
    return max(executable, key=lambda path: tuple(
        (0, int(part)) if part.isdigit() else (1, part) for part in path.parent.name.split(".")
    ))


def opencode_runtime_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Supply connected custom providers to ACP without serializing their credentials."""
    configured = dict(os.environ if environment is None else environment)
    configured["OPENCODE_CONFIG_CONTENT"] = json.dumps({
        "provider": {
            "ollama-cloud": {
                "npm": "@opencode/ai/providers/openai-compatible",
                "name": "Ollama Cloud",
                "options": {"baseURL": "https://ollama.com/v1", "apiKey": "{env:OLLAMA_API_KEY}"},
            },
        },
    }, separators=(",", ":"))
    return configured


class Inventory:
    def __init__(self, root: Path):
        self.root = root
        self.workspace = root.parent
        self.cache_path = root / ".runtime" / "agent-manager" / "inventory-cache.json"
        self._discovery: dict[str, dict[str, Any]] = {}

    def machines(self) -> list[dict[str, Any]]:
        return [
            {"id": "mini", "name": "Mac mini", "status": "online", "enrolled": True},
            {"id": "dell", "name": "Dell", "status": "unenrolled", "enrolled": False},
            {"id": "book", "name": "MacBook", "status": "unenrolled", "enrolled": False},
        ]

    def harnesses(self, machine: str) -> list[dict[str, Any]]:
        if machine != "mini":
            return []
        records = []
        hermes = Path.home() / ".local" / "bin" / "hermes"
        dsh = self.workspace / ".runtime" / "dsh-acp.sh"
        opencode = opencode_cli()
        if hermes.exists():
            records.append({
                "id": "hermes", "name": "Hermes", "adapter": "acp", "creatable": True,
                "version": self._version([str(hermes), "acp", "--version"]),
            })
        if dsh.exists():
            records.append({
                "id": "dsh", "name": "DeepSeek Harness", "adapter": "acp", "creatable": True,
                "version": self._version([str(dsh), "--version"]),
            })
        if opencode:
            records.append({
                "id": "opencode", "name": "OpenCode", "adapter": "acp", "creatable": True,
                "version": self._version([str(opencode), "--version"]),
            })
        if (self.root / ".runtime" / "grok.yaml").exists():
            records.append({
                "id": "grok", "name": "Grok (existing native connector)", "adapter": "native-remote",
                "creatable": False, "configurable": False,
                "reason": "Grok already has one native remote connector. Additional Grok identities require a separately provisioned native Bot adapter.",
                "version": "native",
            })
        return records

    @staticmethod
    def _version(command: list[str]) -> str:
        try:
            return subprocess.check_output(command, text=True, timeout=15, stderr=subprocess.STDOUT).strip()
        except (OSError, subprocess.SubprocessError):
            return "detected"

    def discovery_status(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._discovery.items()}

    def _read_cache(self) -> dict[str, Any]:
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_cache(self, cache: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.cache_path)

    def models(self, machine: str, harness: str) -> list[dict[str, Any]]:
        if machine != "mini":
            return []
        loaders: dict[str, Callable[[], list[dict[str, Any]]]] = {
            "hermes": self._hermes_models,
            "dsh": self._dsh_models,
            "opencode": self._opencode_models,
            # Grok is native and remote; it has no generic local model selector.
            "grok": list,
        }
        loader = loaders.get(harness)
        if not loader:
            return []
        cache = self._read_cache()
        try:
            models = loader()
            if harness != "grok" and not models:
                raise InventoryError(f"{harness} returned no usable models")
            discovered_at = datetime.now(timezone.utc).isoformat()
            cache.setdefault("harnesses", {})[harness] = {"discovered_at": discovered_at, "models": models}
            self._write_cache(cache)
            self._discovery[harness] = {"status": "live", "discovered_at": discovered_at, "error": None}
            return models
        except (InventoryError, OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as error:
            cached = cache.get("harnesses", {}).get(harness)
            if cached and isinstance(cached.get("models"), list):
                self._discovery[harness] = {
                    "status": "stale", "discovered_at": cached.get("discovered_at"),
                    "error": str(error)[:240],
                }
            else:
                self._discovery[harness] = {"status": "unavailable", "discovered_at": None, "error": str(error)[:240]}
            # Cached timestamps explain the failed refresh; cached choices are never offered.
            return []

    def _catalog(self, provider: str) -> dict[str, Any]:
        catalog_provider = "kimi-coding" if provider == "kimi-coding-cn" else provider
        path = (self.workspace / ".runtime" / "dsh" / "node_modules" / "@earendil-works" /
                "pi-ai" / "dist" / "providers" / "data" / f"{catalog_provider}.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        models = []
        for group in raw.values():
            for record in group.values():
                if record.get("type") != "chat":
                    continue
                name = record["name"] + (" (CN)" if provider == "kimi-coding-cn" else "")
                models.append({
                    "id": record["id"], "name": name, "provider": provider,
                    "input": record.get("input", ["text"]), "efforts": [],
                })
        return sorted(models, key=lambda item: (item["provider"], item["name"], item["id"]))

    def _dsh_models(self) -> list[dict[str, Any]]:
        # DSH exposes exact model and effort selection through its native ACP session controls.
        return self._acp_models([str(self.workspace / ".runtime" / "dsh-acp.sh")], "dsh")

    @staticmethod
    def _probe_models_endpoint(base_url: str) -> None:
        endpoint = f"{base_url.rstrip('/')}/models"
        request = urlrequest.Request(endpoint, headers={"Accept": "application/json"}, method="GET")
        try:
            with urlrequest.urlopen(request, timeout=2) as response:
                response.read(1)
        except urlerror.HTTPError:
            # Authentication and other HTTP errors still prove that the endpoint is reachable.
            pass
        except (urlerror.URLError, TimeoutError, OSError) as error:
            raise InventoryError("Provider endpoint is unreachable") from error

    def _custom_provider_health(self) -> dict[str, dict[str, Any]]:
        try:
            output = subprocess.check_output(
                [str(Path.home() / ".local" / "bin" / "hermes"), "config", "get", "custom_providers"],
                text=True, timeout=15, stderr=subprocess.DEVNULL,
            )
            providers = yaml.safe_load(output) or []
        except (OSError, ValueError, yaml.YAMLError, subprocess.SubprocessError):
            return {}
        health = {}
        for record in providers:
            name = str(record.get("name", "")).strip()
            base_url = record.get("base_url")
            if not name or not base_url:
                continue
            provider_id = "custom:" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            try:
                self._probe_models_endpoint(str(base_url))
                health[provider_id] = {
                    "selectable": True, "availability": "endpoint-reachable", "availability_reason": None,
                }
            except (InventoryError, ValueError):
                health[provider_id] = {
                    "selectable": False, "availability": "unavailable",
                    "availability_reason": "Configured provider endpoint is unreachable.",
                }
        return health

    def _hermes_native_roster(self) -> set[tuple[str, str]]:
        """Use the same live provider inventory as Hermes' native model picker."""
        hermes = str(Path.home() / ".local" / "bin" / "hermes")
        runtime = json.loads(subprocess.check_output(
            [hermes, "--print-runtime-command"], text=True, timeout=15, stderr=subprocess.DEVNULL,
        ))
        probe = """
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / '.hermes' / 'hermes-agent'))
import hermes_bootstrap
from hermes_cli.inventory import build_model_options_payload, load_picker_context
payload = build_model_options_payload(load_picker_context(), refresh=True)
print(json.dumps({'providers': [
    {'slug': row.get('slug'), 'models': row.get('models') or []}
    for row in payload['providers']
]}))
"""
        output = subprocess.check_output(
            [runtime[0], "-I", "-c", probe], text=True, timeout=120, stderr=subprocess.DEVNULL,
        )
        providers = json.loads(output)["providers"]
        return {(row["slug"], model) for row in providers for model in row["models"]}

    def _hermes_models(self) -> list[dict[str, Any]]:
        native = self._hermes_native_roster()
        models = self._acp_models([str(Path.home() / ".local" / "bin" / "hermes"), "acp"], "hermes")
        health = self._custom_provider_health()
        checked = []
        for record in models:
            provider = record["provider"]
            if (provider, record["id"]) not in native:
                continue
            if provider.startswith("custom:") and not health.get(provider, {}).get("selectable", False):
                continue
            checked.append(record)
        return checked

    def _opencode_native_roster(self, cli: Path) -> set[str]:
        providers = json.loads(subprocess.check_output(
            [str(cli), "api", "provider.list"], text=True, timeout=30, stderr=subprocess.DEVNULL,
        ))["data"]
        connected = {item["id"] for item in providers}
        models = json.loads(subprocess.check_output(
            [str(cli), "api", "model.list"], text=True, timeout=30, stderr=subprocess.DEVNULL,
        ))["data"]
        return {
            f"{item['providerID']}/{item['modelID']}" for item in models
            if item.get("enabled") and item.get("status") == "active" and item["providerID"] in connected
        }

    def _opencode_models(self) -> list[dict[str, Any]]:
        cli = opencode_cli()
        if not cli:
            raise InventoryError("OpenCode CLI is unavailable")
        native = self._opencode_native_roster(cli)
        models = self._acp_models(
            [str(cli), "acp"], "opencode", environment=opencode_runtime_environment(),
        )
        return [record for record in models if record["id"] in native]

    @staticmethod
    def _option(options: list[dict[str, Any]], category: str) -> dict[str, Any] | None:
        return next((option for option in options if option.get("category") == category and option.get("type", "select") == "select"), None)

    @staticmethod
    def _selection_record(harness: str, native_id: str) -> tuple[str, str]:
        if harness == "hermes":
            provider, separator, model_id = native_id.rpartition(":")
            if not separator:
                raise InventoryError(f"Unexpected Hermes model identifier: {native_id}")
            return provider, model_id
        if harness == "dsh":
            provider, separator, model_id = native_id.partition("::")
            if not separator:
                raise InventoryError(f"Unexpected DSH model identifier: {native_id}")
            return provider, model_id
        provider, separator, _ = native_id.partition("/")
        return (provider if separator else "opencode"), native_id

    def _acp_models(self, command: list[str], harness: str,
                    environment: dict[str, str] | None = None) -> list[dict[str, Any]]:
        environment = dict(os.environ if environment is None else environment)
        if harness == "dsh":
            environment["NO_BROWSER"] = "1"
        process = subprocess.Popen(
            command, cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, env=environment,
        )
        next_id = 0

        def call(method: str, params: dict[str, Any], timeout: float = 45) -> dict[str, Any]:
            nonlocal next_id
            next_id += 1
            if not process.stdin or not process.stdout:
                raise InventoryError(f"{harness} ACP pipes are unavailable")
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": next_id, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                ready, _, _ = select.select([process.stdout], [], [], max(0, deadline - time.monotonic()))
                if not ready:
                    break
                line = process.stdout.readline()
                if not line:
                    break
                try:
                    response = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if response.get("id") != next_id:
                    continue
                if "error" in response:
                    raise InventoryError(str(response["error"].get("message", f"{harness} ACP request failed")))
                return response.get("result", {})
            raise InventoryError(f"{harness} ACP {method} timed out or closed")

        try:
            call("initialize", {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
                "clientInfo": {"name": "army-hub-inventory", "version": "0.1.0"},
            })
            created = call("session/new", {"cwd": str(self.root), "mcpServers": []})
            session_id = created["sessionId"]
            model_option = self._option(created.get("configOptions", []), "model")
            if not model_option:
                raise InventoryError(f"{harness} did not advertise ACP model selection")
            models = []
            for choice in model_option.get("options", []):
                native_id = choice["value"]
                try:
                    updated = call("session/set_config_option", {
                        "sessionId": session_id, "configId": model_option["id"], "value": native_id,
                    })
                except InventoryError:
                    # An advertised provider can still be unavailable (for example expired OAuth).
                    # Exclude that choice rather than failing every healthy provider's inventory.
                    continue
                selected = self._option(updated.get("configOptions", []), "model")
                if not selected or selected.get("currentValue") != native_id:
                    # Advertised aliases (for example Hermes' current `auto:` route) are not
                    # provisionable choices unless ACP confirms the exact selection.
                    continue
                effort = self._option(updated.get("configOptions", []), "thought_level")
                efforts = [item["value"] for item in effort.get("options", []) if item.get("value") != "default"] if effort else []
                provider, model_id = self._selection_record(harness, native_id)
                if harness == "dsh" and provider != "deepseek-official":
                    continue
                models.append({
                    "id": model_id, "name": choice.get("name", native_id), "provider": provider,
                    "efforts": efforts, "effort_config_id": effort.get("id") if effort else None,
                    "selection": "acp-config", "selectable": True,
                    "availability": "acp-verified", "availability_reason": None,
                })
            return sorted(models, key=lambda item: (item["provider"], item["name"], item["id"]))
        finally:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

    def projects(self, machine: str) -> list[dict[str, Any]]:
        raw = yaml.safe_load((self.root / "projects" / "registry.yaml").read_text(encoding="utf-8"))
        projects = []
        for project_id, record in raw["projects"].items():
            path = record.get("local_paths", {}).get(machine)
            if not path or not Path(path).is_dir():
                continue
            projects.append({"id": project_id, "name": project_id.replace("-", " ").title(),
                             "path": path, "repository": record.get("repository"),
                             "room_alias": record.get("matrix_room_alias")})
        return projects

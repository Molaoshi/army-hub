from __future__ import annotations

import json

from army_manager.inventory import Inventory, InventoryError, opencode_runtime_environment


def test_hermes_uses_native_acp_discovery_and_composite_provider_ids(root, monkeypatch):
    inventory = Inventory(root)
    calls = []

    def discover(command, harness):
        calls.append((command, harness))
        return [{"id": "qwen/qwen3.8-27b", "name": "Local Qwen", "provider": "custom:ahia-local", "efforts": []}]

    monkeypatch.setattr(inventory, "_acp_models", discover)
    monkeypatch.setattr(inventory, "_hermes_native_roster", lambda: {("custom:ahia-local", "qwen/qwen3.8-27b")})
    monkeypatch.setattr(inventory, "_custom_provider_health", lambda: {
        "custom:ahia-local": {"selectable": True},
    })
    models = inventory.models("mini", "hermes")
    assert calls[0][0][-1] == "acp" and calls[0][1] == "hermes"
    assert models[0]["provider"] == "custom:ahia-local"
    assert Inventory._selection_record("hermes", "custom:ahia-local:qwen/qwen3.8-27b") == (
        "custom:ahia-local", "qwen/qwen3.8-27b",
    )


def test_dsh_models_use_native_acp_and_effort(root, monkeypatch):
    inventory = Inventory(root)
    calls = []

    def discover(command, harness):
        calls.append((command, harness))
        return [{"id": model, "name": model, "provider": "deepseek-official",
                 "efforts": ["off", "low", "high", "max"], "effort_config_id": "effort",
                 "selectable": True, "availability": "acp-verified"}
                for model in ("deepseek-v4-pro", "deepseek-flash")]

    monkeypatch.setattr(inventory, "_acp_models", discover)
    models = inventory.models("mini", "dsh")
    assert calls[0][0][0].endswith("dsh-acp.sh") and calls[0][1] == "dsh"
    assert {item["id"] for item in models} == {"deepseek-v4-pro", "deepseek-flash"}
    assert all(item["efforts"] == ["off", "low", "high", "max"] for item in models)
    assert Inventory._selection_record("dsh", "deepseek-official::deepseek-flash") == (
        "deepseek-official", "deepseek-flash",
    )


def test_hermes_hides_unreachable_custom_providers(root, monkeypatch):
    inventory = Inventory(root)
    monkeypatch.setattr(inventory, "_acp_models", lambda command, harness: [
        {"id": "local-chat", "name": "Old gateway", "provider": "custom:litellm-gateway", "efforts": []},
        {"id": "qwen/qwen3.8-27b", "name": "Local Qwen", "provider": "custom:ahia-local", "efforts": [],
         "selectable": True, "availability": "acp-verified"},
        {"id": "deepseek-flash", "name": "Flash", "provider": "deepseek", "efforts": [],
         "selectable": True, "availability": "acp-verified"},
    ])
    monkeypatch.setattr(inventory, "_hermes_native_roster", lambda: {
        ("custom:litellm-gateway", "local-chat"),
        ("custom:ahia-local", "qwen/qwen3.8-27b"),
        ("deepseek", "deepseek-flash"),
    })
    monkeypatch.setattr(inventory, "_custom_provider_health", lambda: {
        "custom:litellm-gateway": {"selectable": False},
        "custom:ahia-local": {"selectable": True},
    })
    models = {(item["provider"], item["id"]): item for item in inventory.models("mini", "hermes")}
    assert ("custom:litellm-gateway", "local-chat") not in models
    assert models[("custom:ahia-local", "qwen/qwen3.8-27b")]["selectable"] is True
    assert models[("deepseek", "deepseek-flash")]["availability"] == "acp-verified"


def test_failed_refresh_returns_no_cached_models_but_retains_stale_status(root, monkeypatch):
    inventory = Inventory(root)
    live = [{"id": "opencode/model", "name": "Model", "provider": "opencode", "efforts": ["high"]}]
    monkeypatch.setattr(inventory, "_opencode_models", lambda: live)
    assert inventory.models("mini", "opencode") == live
    monkeypatch.setattr(inventory, "_opencode_models", lambda: (_ for _ in ()).throw(InventoryError("probe unavailable")))
    assert inventory.models("mini", "opencode") == []
    assert inventory.discovery_status()["opencode"]["status"] == "stale"
    assert inventory.discovery_status()["opencode"]["discovered_at"]


def test_uncached_opencode_failure_is_empty_and_unavailable(root, monkeypatch):
    inventory = Inventory(root)
    monkeypatch.setattr(inventory, "_opencode_models", list)
    assert inventory.models("mini", "opencode") == []
    assert inventory.discovery_status()["opencode"]["status"] == "unavailable"


def test_grok_is_existing_native_only_capability(root):
    (root / ".runtime" / "grok.yaml").write_text("native: true")
    inventory = Inventory(root)
    grok = next(item for item in inventory.harnesses("mini") if item["id"] == "grok")
    assert grok["adapter"] == "native-remote"
    assert grok["creatable"] is False
    assert grok["configurable"] is False
    assert inventory.models("mini", "grok") == []


def test_hermes_requires_native_catalog_membership_for_every_provider(root, monkeypatch):
    inventory = Inventory(root)
    monkeypatch.setattr(inventory, "_acp_models", lambda command, harness: [
        {"id": "deepseek-flash", "name": "Flash", "provider": "deepseek", "efforts": []},
        {"id": "kimi-k2.5", "name": "Old Kimi", "provider": "kimi-coding", "efforts": []},
        {"id": "grok-4.6", "name": "Grok", "provider": "xai-oauth", "efforts": []},
    ])
    monkeypatch.setattr(inventory, "_hermes_native_roster", lambda: {
        ("deepseek", "deepseek-flash"), ("xai-oauth", "grok-4.6"),
    })
    assert {(item["provider"], item["id"]) for item in inventory.models("mini", "hermes")} == {
        ("deepseek", "deepseek-flash"), ("xai-oauth", "grok-4.6"),
    }


def test_opencode_uses_connected_native_roster_and_complete_acp_environment(root, monkeypatch):
    inventory = Inventory(root)
    monkeypatch.setattr("army_manager.inventory.opencode_cli", lambda: root / "opencode-cli")
    monkeypatch.setattr(inventory, "_opencode_native_roster", lambda cli: {
        "ollama-cloud/minimax-m3.1-flash", "opencode/deepseek-v4.1-flash-free",
    })
    captured = {}

    def discover(command, harness, environment=None):
        captured.update(environment or {})
        return [
            {"id": "ollama-cloud/minimax-m3.1-flash", "name": "MiniMax", "provider": "ollama-cloud",
             "efforts": ["low", "medium", "high", "xhigh", "max"]},
            {"id": "opencode/deepseek-v4.1-flash-free", "name": "DeepSeek", "provider": "opencode", "efforts": []},
            {"id": "kimi-code-plan-k3", "name": "Disconnected", "provider": "kimi-code-plan", "efforts": []},
        ]

    monkeypatch.setattr(inventory, "_acp_models", discover)
    models = inventory.models("mini", "opencode")
    assert {item["id"] for item in models} == {
        "ollama-cloud/minimax-m3.1-flash", "opencode/deepseek-v4.1-flash-free",
    }
    assert models[0]["efforts"] == ["low", "medium", "high", "xhigh", "max"]
    config = json.loads(captured["OPENCODE_CONFIG_CONTENT"])
    assert config["provider"]["ollama-cloud"]["options"]["apiKey"] == "{env:OLLAMA_API_KEY}"
    assert opencode_runtime_environment({}) == {"OPENCODE_CONFIG_CONTENT": captured["OPENCODE_CONFIG_CONTENT"]}

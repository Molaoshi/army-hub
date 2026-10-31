"""Live, non-destructive acceptance checks against the reserved Grok identity."""
from __future__ import annotations

import io
import json
import secrets

from fastapi.testclient import TestClient
from PIL import Image

from army_manager import app as module


def main() -> None:
    credentials = module.matrix.credentials()
    original = module.matrix.profile(credentials["grok"]["mxid"])
    hermes_pid = module.connectors.pid("hermes-mini")
    dsh_pid = module.connectors.pid("dsh-mini")
    assert hermes_pid and dsh_pid, "Working connectors must be online before acceptance"
    module.sessions.clear()
    with TestClient(module.app, base_url="https://army.live") as client:
        login = client.post("/api/login", json={"username": "mo", "password": credentials["mo"]["password"]})
        assert login.status_code == 200, login.text
        csrf = login.json()["csrf"]
        headers = {"X-CSRF-Token": csrf}
        inventory = client.get("/api/inventory")
        assert inventory.status_code == 200, inventory.text
        assert {item["id"] for item in inventory.json()["harnesses"]["mini"]} == {"hermes", "dsh"}
        assert len(inventory.json()["rooms"]) == 3

        source = Image.new("RGB", (900, 500), (22, 120, 128))
        buffer = io.BytesIO()
        source.save(buffer, format="JPEG")
        updated = client.post("/api/agents/grok/profile", headers=headers,
                              data={"display_name": "Grok"},
                              files={"avatar": ("acceptance.jpg", buffer.getvalue(), "image/jpeg")})
        assert updated.status_code == 200, updated.text
        assert updated.json()["avatar_url"].startswith("mxc://")
        avatar = client.get("/api/agents/grok/avatar")
        assert avatar.status_code == 200, avatar.text
        with Image.open(io.BytesIO(avatar.content)) as processed:
            assert processed.size == (512, 512)

        dummy = secrets.token_urlsafe(24)
        added = client.post("/api/agents/grok/credentials", headers=headers,
                            json={"provider": "Other", "name": "Acceptance temporary", "secret": dummy})
        assert added.status_code == 201, added.text
        credential_id = added.json()["id"]
        assert added.json()["value"] == "••••••••"
        assert module.credentials.read("grok", credential_id) == dummy
        detail = client.get("/api/agents/grok").json()
        assert detail["credentials"][0]["value"] == "••••••••"
        assert dummy not in module.store.path.read_text(encoding="utf-8")
        deleted = client.delete(f"/api/agents/grok/credentials/{credential_id}", headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert not module.store.credentials("grok")
        assert module.connectors.pid("hermes-mini") == hermes_pid
        assert module.connectors.pid("dsh-mini") == dsh_pid

        client.post("/api/logout", headers=headers)
    module.matrix.update_profile("grok", original["displayname"], original.get("avatar_url") or "")
    print(json.dumps({
        "matrix_login": "passed", "inventory": "passed", "avatar_upload_and_proxy": "passed",
        "keychain_add_list_delete": "passed", "working_connectors_untouched": "passed",
        "reserved_profile_restored": True,
    }, indent=2))


if __name__ == "__main__":
    main()

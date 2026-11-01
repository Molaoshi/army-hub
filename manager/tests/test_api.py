from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from army_manager import app as module


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module.matrix, "login_mo", lambda username, password: password == "correct")
    with TestClient(module.app, base_url="https://army.test") as client:
        yield client


def login(client):
    response = client.post("/api/login", json={"username": "mo", "password": "correct"})
    assert response.status_code == 200
    csrf = response.json()["csrf"]
    return {"X-CSRF-Token": csrf}


def test_login_required_and_csrf(client):
    assert client.get("/api/agents").status_code == 401
    assert client.post("/api/login", json={"username": "mo", "password": "wrong"}).status_code == 401
    headers = login(client)
    assert client.get("/api/session").status_code == 200
    assert client.post("/api/agents/hermes-mini/restart").status_code == 403
    assert headers["X-CSRF-Token"]


def test_health_and_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_avatar_rejects_non_image_before_matrix(client):
    headers = login(client)
    response = client.post("/api/agents/hermes-mini/profile", headers=headers,
                           data={"display_name": "Hermes Mini"},
                           files={"avatar": ("avatar.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")})
    assert response.status_code == 400
    assert "valid image" in response.json()["detail"]


def test_avatar_processing_and_profile_do_not_restart_connector(client, monkeypatch):
    headers = login(client)
    captured = {}
    monkeypatch.setattr(module.matrix, "upload_avatar", lambda agent_id, content: captured.setdefault("content", content) and "mxc://army.local/avatar")
    monkeypatch.setattr(module.matrix, "update_profile", lambda agent_id, name, avatar: {"displayname": name, "avatar_url": avatar})
    restart = MockConnector()
    monkeypatch.setattr(module.connectors, "restart", restart)
    source = Image.new("RGB", (900, 500), (20, 120, 130))
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG")
    response = client.post("/api/agents/hermes-mini/profile", headers=headers,
                           data={"display_name": "Hermes Mini"},
                           files={"avatar": ("avatar.jpg", buffer.getvalue(), "image/jpeg")})
    assert response.status_code == 200, response.text
    with Image.open(io.BytesIO(captured["content"])) as avatar:
        assert avatar.size == (512, 512)
        assert avatar.format == "PNG"
    assert restart.calls == 0


class MockConnector:
    calls = 0
    def __call__(self, agent_id):
        self.calls += 1

#!/usr/bin/env python3
"""Idempotently provision Army Hub users, credentials, and private rooms."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
BASE = "http://127.0.0.1:8010"
SERVER = "army.local"
CREDENTIALS = RUNTIME / "credentials.json"
ROOMS_FILE = RUNTIME / "rooms.json"
ACCOUNTS = {
    "mo": ("Mo", True),
    "hermes-mini": ("Hermes Mini", False),
    "dsh-mini": ("DSH Mini", False),
    "hermes-dell": ("Hermes Dell", False),
    "hermes-book": ("Hermes Book", False),
    "grok": ("Grok", False),
}
ACTIVE_BOTS = ["hermes-mini", "dsh-mini"]
ROOMS = {
    "army-lab": ("Army Lab", "Experiments and controlled cross-agent collaboration."),
    "project-army-hub": ("Army Hub", "Development of the private multi-agent hub."),
    "approvals": ("Approvals", "Human approval for merges, deployment, spending, deletion, and credentials."),
}


def request(method: str, path: str, body: dict | None = None, token: str | None = None, _retry: bool = True) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        if error.code == 429 and _retry:
            payload = json.loads(detail)
            delay = max(1, int(payload.get("retry_after_ms", 1000)) / 1000 + 1)
            print(f"Rate limited; respecting Synapse retry delay of {delay:.0f} seconds")
            time.sleep(delay)
            return request(method, path, body, token, _retry=False)
        raise RuntimeError(f"{method} {path}: {error.code} {detail}") from error


def register(username: str, password: str, admin: bool, shared_secret: str) -> dict:
    nonce = request("GET", "/_synapse/admin/v1/register")["nonce"]
    mac = hmac.new(
        shared_secret.encode(),
        b"\0".join([
            nonce.encode(), username.encode(), password.encode(), b"admin" if admin else b"notadmin",
        ]),
        hashlib.sha1,
    ).hexdigest()
    try:
        return request("POST", "/_synapse/admin/v1/register", {
            "nonce": nonce, "username": username, "password": password, "admin": admin, "mac": mac,
            "issue_access_token": True,
        })
    except RuntimeError as error:
        if "M_USER_IN_USE" in str(error):
            return {}
        raise


def main() -> None:
    matrix_secrets = json.loads((RUNTIME / "matrix-secrets.json").read_text(encoding="utf-8"))
    credentials = json.loads(CREDENTIALS.read_text(encoding="utf-8")) if CREDENTIALS.exists() else {}

    def save_credentials() -> None:
        CREDENTIALS.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
        CREDENTIALS.chmod(0o600)

    for username, (display_name, admin) in ACCOUNTS.items():
        record = credentials.setdefault(username, {"password": secrets.token_urlsafe(30)})
        save_credentials()
        registration = register(username, record["password"], admin, matrix_secrets["registration_shared_secret"])
        if registration.get("access_token"):
            record.update({
                "access_token": registration["access_token"],
                "device_id": registration["device_id"],
                "mxid": registration["user_id"],
            })
            save_credentials()
        elif "access_token" not in record:
            if username == "mo":
                login = request("POST", "/_matrix/client/v3/login", {
                    "type": "m.login.password",
                    "identifier": {"type": "m.id.user", "user": username},
                    "password": record["password"],
                    "initial_device_display_name": f"Army Hub {display_name}",
                })
                record.update({
                    "access_token": login["access_token"],
                    "device_id": login["device_id"],
                    "mxid": login["user_id"],
                })
            else:
                mxid = f"@{username}:{SERVER}"
                login = request(
                    "POST",
                    f"/_synapse/admin/v1/users/{urllib.parse.quote(mxid, safe='')}/login",
                    {},
                    credentials["mo"]["access_token"],
                )
                record.update({"access_token": login["access_token"], "device_id": None, "mxid": mxid})
            save_credentials()
        request("PUT", f"/_matrix/client/v3/profile/{urllib.parse.quote(record['mxid'])}/displayname", {
            "displayname": display_name,
        }, record["access_token"])

    save_credentials()
    mo = credentials["mo"]
    rooms = json.loads(ROOMS_FILE.read_text(encoding="utf-8")) if ROOMS_FILE.exists() else {}

    for alias, (name, topic) in ROOMS.items():
        if alias in rooms:
            room_id = rooms[alias]["room_id"]
        else:
            power_levels = {
                "users": {mo["mxid"]: 100},
                "users_default": 0,
                "events_default": 0,
                "state_default": 100,
                "invite": 100,
                "kick": 100,
                "ban": 100,
                "redact": 100,
                "events": {
                    "m.room.name": 100,
                    "m.room.topic": 100,
                    "m.room.power_levels": 100,
                    "m.room.join_rules": 100,
                    "m.room.history_visibility": 100,
                },
            }
            created = request("POST", "/_matrix/client/v3/createRoom", {
                "preset": "private_chat",
                "visibility": "private",
                "room_alias_name": alias,
                "name": name,
                "topic": topic,
                "invite": [credentials[bot]["mxid"] for bot in ACTIVE_BOTS],
                "power_level_content_override": power_levels,
                "creation_content": {"m.federate": False},
            }, mo["access_token"])
            room_id = created["room_id"]
            rooms[alias] = {
                "room_id": room_id,
                "alias": f"#{alias}:{SERVER}",
                "members": [mo["mxid"], *[credentials[bot]["mxid"] for bot in ACTIVE_BOTS]],
            }

        for bot in ACTIVE_BOTS:
            token = credentials[bot]["access_token"]
            try:
                request("POST", f"/_matrix/client/v3/join/{urllib.parse.quote(room_id)}", {}, token)
            except RuntimeError as error:
                if "M_FORBIDDEN" not in str(error):
                    raise

    ROOMS_FILE.write_text(json.dumps(rooms, indent=2) + "\n", encoding="utf-8")
    ROOMS_FILE.chmod(0o600)
    print(f"Provisioned {len(ACCOUNTS)} identities and {len(rooms)} private rooms; credentials remain in .runtime")


if __name__ == "__main__":
    main()

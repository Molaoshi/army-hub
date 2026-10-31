from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class MatrixError(RuntimeError):
    pass


class MatrixClient:
    def __init__(self, root: Path, base_url: str = "http://127.0.0.1:8010"):
        self.root = root
        self.runtime = root / ".runtime"
        self.base_url = base_url.rstrip("/")

    def credentials(self) -> dict[str, Any]:
        return json.loads((self.runtime / "credentials.json").read_text(encoding="utf-8"))

    def save_credentials(self, credentials: dict[str, Any]) -> None:
        path = self.runtime / "credentials.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)

    def request(self, method: str, path: str, token: str | None = None,
                body: dict[str, Any] | None = None, data: bytes | None = None,
                content_type: str = "application/json") -> tuple[Any, str]:
        headers = {"Content-Type": content_type}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = data if data is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.base_url + path, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                response_type = response.headers.get_content_type()
                if response_type == "application/json":
                    return (json.loads(raw) if raw else {}), response_type
                return raw, response_type
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:1200]
            raise MatrixError(f"Matrix returned {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise MatrixError(f"Matrix is unavailable: {error.reason}") from error

    def login_mo(self, username: str, password: str) -> bool:
        try:
            result, _ = self.request("POST", "/_matrix/client/v3/login", body={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": username},
                "password": password,
                "initial_device_display_name": "Army Hub Agent Manager login check",
            })
            if result.get("user_id") != "@mo:army.local":
                return False
            access_token = result.get("access_token")
            if access_token:
                self.request("POST", "/_matrix/client/v3/logout", token=access_token, body={})
            return True
        except MatrixError:
            return False

    def profile(self, mxid: str) -> dict[str, Any]:
        result, _ = self.request("GET", f"/_matrix/client/v3/profile/{urllib.parse.quote(mxid, safe='')}")
        return {"displayname": result.get("displayname") or mxid.split(":", 1)[0].lstrip("@"),
                "avatar_url": result.get("avatar_url")}

    def update_profile(self, agent_id: str, display_name: str, avatar_mxc: str | None) -> dict[str, Any]:
        record = self.credentials()[agent_id]
        mxid = record["mxid"]
        token = record["access_token"]
        if display_name:
            self.request("PUT", f"/_matrix/client/v3/profile/{urllib.parse.quote(mxid, safe='')}/displayname",
                         token=token, body={"displayname": display_name})
        if avatar_mxc:
            self.request("PUT", f"/_matrix/client/v3/profile/{urllib.parse.quote(mxid, safe='')}/avatar_url",
                         token=token, body={"avatar_url": avatar_mxc})
        return self.profile(mxid)

    def upload_avatar(self, agent_id: str, content: bytes) -> str:
        token = self.credentials()[agent_id]["access_token"]
        result, _ = self.request("POST", "/_matrix/media/v3/upload?filename=avatar.png", token=token,
                                 data=content, content_type="image/png")
        return result["content_uri"]

    def avatar(self, mxc: str) -> tuple[bytes, str]:
        if not mxc.startswith("mxc://"):
            raise MatrixError("Invalid Matrix avatar URI")
        parsed = urllib.parse.urlparse(mxc)
        path = f"/_matrix/client/v1/media/download/{parsed.netloc}{parsed.path}"
        token = self.credentials()["mo"]["access_token"]
        return self.request("GET", path, token=token)

    def rooms(self) -> list[dict[str, str]]:
        records = json.loads((self.runtime / "rooms.json").read_text(encoding="utf-8"))
        token = self.credentials()["mo"]["access_token"]
        rooms = []
        for slug, record in records.items():
            name, _ = self.request("GET", f"/_matrix/client/v3/rooms/{urllib.parse.quote(record['room_id'], safe='')}/state/m.room.name", token=token)
            rooms.append({"id": record["room_id"], "slug": slug, "name": name.get("name", slug), "alias": record["alias"]})
        return rooms

    def create_agent_identity(self, agent_id: str, display_name: str) -> dict[str, Any]:
        credentials = self.credentials()
        if agent_id in credentials:
            raise MatrixError("An identity with this agent ID already exists")
        secrets_record = json.loads((self.runtime / "matrix-secrets.json").read_text(encoding="utf-8"))
        password = secrets.token_urlsafe(30)
        nonce, _ = self.request("GET", "/_synapse/admin/v1/register")
        mac = hmac.new(secrets_record["registration_shared_secret"].encode(), b"\0".join([
            nonce["nonce"].encode(), agent_id.encode(), password.encode(), b"notadmin",
        ]), hashlib.sha1).hexdigest()
        registration, _ = self.request("POST", "/_synapse/admin/v1/register", body={
            "nonce": nonce["nonce"], "username": agent_id, "password": password,
            "admin": False, "mac": mac, "issue_access_token": True,
        })
        record = {"password": password, "access_token": registration["access_token"],
                  "device_id": registration["device_id"], "mxid": registration["user_id"]}
        credentials[agent_id] = record
        self.save_credentials(credentials)
        self.request("PUT", f"/_matrix/client/v3/profile/{urllib.parse.quote(record['mxid'], safe='')}/displayname",
                     token=record["access_token"], body={"displayname": display_name})
        return record

    def sync_rooms(self, agent_id: str, desired: list[str], previous: list[str] | None = None) -> None:
        credentials = self.credentials()
        agent = credentials[agent_id]
        mo = credentials["mo"]
        for room_id in desired:
            quoted = urllib.parse.quote(room_id, safe="")
            try:
                self.request("POST", f"/_matrix/client/v3/join/{quoted}", token=agent["access_token"], body={})
            except MatrixError:
                self.request("POST", f"/_matrix/client/v3/rooms/{quoted}/invite", token=mo["access_token"],
                             body={"user_id": agent["mxid"]})
                self.request("POST", f"/_matrix/client/v3/join/{quoted}", token=agent["access_token"], body={})
        for room_id in set(previous or []) - set(desired):
            quoted = urllib.parse.quote(room_id, safe="")
            try:
                self.request("POST", f"/_matrix/client/v3/rooms/{quoted}/leave", token=agent["access_token"], body={})
            except MatrixError:
                pass

    def join_rooms(self, agent_id: str, room_ids: list[str]) -> None:
        self.sync_rooms(agent_id, room_ids)

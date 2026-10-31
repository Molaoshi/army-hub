from __future__ import annotations

import io
from pathlib import Path
import secrets
import time
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, UnidentifiedImageError

from .connectors import ConnectorManager, ConnectorError
from .credentials import CredentialManager, CredentialError, PROVIDERS
from .inventory import Inventory
from .matrix import MatrixClient, MatrixError
from .provision import Provisioner
from .store import ManagerStore

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "static"
store = ManagerStore(ROOT)
matrix = MatrixClient(ROOT)
inventory = Inventory(ROOT)
connectors = ConnectorManager(ROOT, store)
credentials = CredentialManager(store)
provisioner = Provisioner(store, matrix, inventory, connectors)
app = FastAPI(title="Army Hub Agent Manager", docs_url=None, redoc_url=None, openapi_url=None)
sessions: dict[str, dict[str, Any]] = {}
SESSION_COOKIE = "army_manager_session"
SESSION_SECONDS = 12 * 60 * 60


class LoginBody(BaseModel):
    username: str
    password: str


class CredentialBody(BaseModel):
    provider: str
    name: str
    secret: str
    scope: str = ""


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


def session_from_request(request: Request) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE, "")
    session = sessions.get(token)
    if not session or session["expires"] < time.time():
        raise HTTPException(401, "Sign in to continue")
    return session


def authorized(request: Request) -> dict[str, Any]:
    session = session_from_request(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("X-CSRF-Token") != session["csrf"]:
            raise HTTPException(403, "Invalid request token")
    return session


def error_handler(error: Exception, status: int = 400) -> None:
    raise HTTPException(status, str(error))


@app.post("/api/login")
def login(body: LoginBody, response: Response) -> dict[str, Any]:
    if not matrix.login_mo(body.username, body.password):
        raise HTTPException(401, "Matrix username or password is incorrect")
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    sessions[token] = {"user": "@mo:army.local", "csrf": csrf, "expires": time.time() + SESSION_SECONDS}
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=True, samesite="strict", path="/")
    return {"user": "@mo:army.local", "csrf": csrf}


@app.post("/api/logout")
def logout(request: Request, response: Response, session: dict[str, Any] = Depends(authorized)) -> dict[str, bool]:
    sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/session")
def get_session(session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    return {"user": session["user"], "csrf": session["csrf"]}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "army-agent-manager"}


@app.get("/api/inventory")
def get_inventory(session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    machines = inventory.machines()
    return {
        "machines": machines,
        "harnesses": {item["id"]: inventory.harnesses(item["id"]) for item in machines},
        "models": {item["id"]: {harness["id"]: inventory.models(item["id"], harness["id"])
                                for harness in inventory.harnesses(item["id"])} for item in machines},
        "projects": {item["id"]: inventory.projects(item["id"]) for item in machines},
        "rooms": matrix.rooms(),
        "providers": PROVIDERS,
    }


@app.get("/api/agents")
def list_agents(session: dict[str, Any] = Depends(authorized)) -> list[dict[str, Any]]:
    result = []
    for record in store.agents():
        try:
            profile = matrix.profile(record["mxid"])
        except MatrixError:
            profile = {"displayname": record.get("display_name", record["id"]), "avatar_url": None}
        result.append({**record, **profile, "connector": connectors.status(record["id"]),
                       "credential_count": len(store.credentials(record["id"]))})
    return sorted(result, key=lambda item: (item["connector"]["status"] != "online", item["displayname"].lower()))


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str, session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        record = store.agent(agent_id)
        return {**record, **matrix.profile(record["mxid"]), "connector": connectors.status(agent_id),
                "credentials": credentials.store.credentials(agent_id)}
    except LookupError:
        raise HTTPException(404, "Agent not found")
    except MatrixError as error:
        error_handler(error, 502)


@app.post("/api/agents", status_code=201)
def create_agent(payload: dict[str, Any], session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return provisioner.create(payload)
    except (ValueError, MatrixError, ConnectorError) as error:
        error_handler(error)


@app.put("/api/agents/{agent_id}/configuration")
def update_configuration(agent_id: str, payload: dict[str, Any], session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return provisioner.update(agent_id, payload)
    except LookupError:
        raise HTTPException(404, "Agent not found")
    except (ValueError, KeyError, MatrixError, ConnectorError) as error:
        error_handler(error)


@app.post("/api/agents/{agent_id}/profile")
def update_profile(agent_id: str, display_name: str = Form(...), avatar: UploadFile | None = File(None),
                   session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        record = store.agent(agent_id)
    except LookupError:
        raise HTTPException(404, "Agent not found")
    display_name = display_name.strip()
    if not 1 <= len(display_name) <= 80:
        raise HTTPException(400, "Display name must be between 1 and 80 characters")
    avatar_mxc = None
    if avatar and avatar.filename:
        try:
            content = avatar.file.read(5 * 1024 * 1024 + 1)
            if len(content) > 5 * 1024 * 1024:
                raise ValueError("Avatar exceeds the 5 MB limit")
            with Image.open(io.BytesIO(content)) as source:
                source.load()
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Avatar must be a PNG, JPEG, or WebP image")
                image = source.convert("RGB")
                side = min(image.size)
                left = (image.width - side) // 2
                top = (image.height - side) // 2
                image = image.crop((left, top, left + side, top + side)).resize((512, 512), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="PNG", optimize=True)
            avatar_mxc = matrix.upload_avatar(agent_id, output.getvalue())
        except (UnidentifiedImageError, OSError):
            raise HTTPException(400, "The uploaded file is not a valid image")
        except (ValueError, MatrixError) as error:
            error_handler(error)
    try:
        profile = matrix.update_profile(agent_id, display_name, avatar_mxc)
        record["display_name"] = display_name
        store.put_agent(record)
        store.audit(session["user"], agent_id, "profile.update", "avatar and name" if avatar_mxc else "display name")
        return profile
    except MatrixError as error:
        error_handler(error, 502)


@app.get("/api/agents/{agent_id}/avatar")
def get_avatar(agent_id: str, session: dict[str, Any] = Depends(authorized)) -> Response:
    try:
        profile = matrix.profile(store.agent(agent_id)["mxid"])
        if not profile.get("avatar_url"):
            raise HTTPException(404, "No avatar")
        content, content_type = matrix.avatar(profile["avatar_url"])
        return Response(content=content, media_type=content_type,
                        headers={"Cache-Control": "private, max-age=60"})
    except LookupError:
        raise HTTPException(404, "Agent not found")
    except MatrixError as error:
        error_handler(error, 502)


@app.post("/api/agents/{agent_id}/restart")
def restart_agent(agent_id: str, session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return connectors.restart(agent_id)
    except (LookupError, ConnectorError) as error:
        error_handler(error)


@app.post("/api/agents/{agent_id}/pause")
def pause_agent(agent_id: str, session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return connectors.stop(agent_id, pause=True)
    except (LookupError, ConnectorError) as error:
        error_handler(error)


@app.post("/api/agents/{agent_id}/resume")
def resume_agent(agent_id: str, session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return connectors.start(agent_id)
    except (LookupError, ConnectorError) as error:
        error_handler(error)


@app.get("/api/agents/{agent_id}/logs")
def agent_logs(agent_id: str, session: dict[str, Any] = Depends(authorized)) -> dict[str, str]:
    try:
        return {"log": connectors.log(agent_id)}
    except LookupError:
        raise HTTPException(404, "Agent not found")


@app.post("/api/agents/{agent_id}/credentials", status_code=201)
def add_credential(agent_id: str, body: CredentialBody, session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return credentials.add(agent_id, body.provider, body.name, body.secret, body.scope)
    except (LookupError, CredentialError) as error:
        error_handler(error)


@app.post("/api/agents/{agent_id}/credentials/{credential_id}/test")
def test_credential(agent_id: str, credential_id: str, session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return credentials.test(agent_id, credential_id)
    except CredentialError as error:
        error_handler(error)


@app.delete("/api/agents/{agent_id}/credentials/{credential_id}")
def delete_credential(agent_id: str, credential_id: str, session: dict[str, Any] = Depends(authorized)) -> dict[str, Any]:
    try:
        return credentials.delete(agent_id, credential_id)
    except (LookupError, CredentialError) as error:
        error_handler(error)


@app.get("/{path:path}", include_in_schema=False)
def static_files(path: str = "") -> FileResponse:
    if not path:
        path = "index.html"
    candidate = (STATIC / path).resolve()
    if STATIC not in candidate.parents or not candidate.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(candidate)

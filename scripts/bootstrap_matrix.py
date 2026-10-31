#!/usr/bin/env python3
"""Create local-only Matrix secrets, generate signing material, and start Army Hub."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
SYNAPSE = RUNTIME / "synapse"
ENV_FILE = ROOT / ".env"
SECRET_FILE = RUNTIME / "matrix-secrets.json"
SERVER_NAME = "army.local"
PUBLIC_BASEURL = "https://moatazs-mac-mini.tailef80eb.ts.net:8444/"
ELEMENT_URL = "https://moatazs-mac-mini.tailef80eb.ts.net:8445/"
IMAGE = "matrixdotorg/synapse:v1.161.0"


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, **kwargs)


def main() -> None:
    (SYNAPSE).mkdir(parents=True, exist_ok=True)
    (RUNTIME / "postgres").mkdir(parents=True, exist_ok=True)

    if not ENV_FILE.exists():
        ENV_FILE.write_text(
            "# Generated locally; never commit.\n"
            f"POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n"
            f"MATRIX_SERVER_NAME={SERVER_NAME}\n"
            f"MATRIX_PUBLIC_BASEURL={PUBLIC_BASEURL}\n"
            f"ELEMENT_PUBLIC_URL={ELEMENT_URL}\n",
            encoding="utf-8",
        )
        ENV_FILE.chmod(0o600)

    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key] = value

    if not SECRET_FILE.exists():
        matrix_secrets = {
            "registration_shared_secret": secrets.token_urlsafe(48),
            "macaroon_secret_key": secrets.token_urlsafe(48),
            "form_secret": secrets.token_urlsafe(48),
        }
        SECRET_FILE.write_text(json.dumps(matrix_secrets, indent=2) + "\n", encoding="utf-8")
        SECRET_FILE.chmod(0o600)
    matrix_secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))

    signing_key = SYNAPSE / f"{SERVER_NAME}.signing.key"
    if not signing_key.exists():
        run([
            "docker", "run", "--rm",
            "-v", f"{SYNAPSE}:/data",
            "-e", f"SYNAPSE_SERVER_NAME={SERVER_NAME}",
            "-e", "SYNAPSE_REPORT_STATS=no",
            IMAGE, "generate",
        ])

    template = (ROOT / "config" / "homeserver.template.yaml").read_text(encoding="utf-8")
    rendered = (
        template.replace("__POSTGRES_PASSWORD__", env["POSTGRES_PASSWORD"])
        .replace("__REGISTRATION_SHARED_SECRET__", matrix_secrets["registration_shared_secret"])
        .replace("__MACAROON_SECRET_KEY__", matrix_secrets["macaroon_secret_key"])
        .replace("__FORM_SECRET__", matrix_secrets["form_secret"])
    )
    (SYNAPSE / "homeserver.yaml").write_text(rendered, encoding="utf-8")
    (SYNAPSE / "homeserver.yaml").chmod(0o600)

    run(["docker", "compose", "--env-file", str(ENV_FILE), "-f", str(ROOT / "docker-compose.yml"), "up", "-d"])

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8010/_matrix/client/versions", timeout=3) as response:
                if response.status == 200:
                    print("Army Matrix is healthy at http://127.0.0.1:8010")
                    return
        except Exception:
            time.sleep(2)
    raise SystemExit("Matrix did not become healthy within 120 seconds; inspect army-synapse logs")


if __name__ == "__main__":
    main()

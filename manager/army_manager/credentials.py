from __future__ import annotations

from datetime import datetime, timezone
import getpass
import json
import secrets
import subprocess
import urllib.error
import urllib.request
from typing import Any

from .keychain import NativeKeychainError, add_secret, delete_secret, get_secret
from .store import ManagerStore


PROVIDERS = ["GitHub", "Railway", "Resend", "DeepSeek", "Kimi", "MiniMax", "Other"]


class CredentialError(RuntimeError):
    pass


class CredentialManager:
    def __init__(self, store: ManagerStore):
        self.store = store
        self.account = getpass.getuser()

    @staticmethod
    def service(agent_id: str, credential_id: str) -> str:
        return f"ai.army.agent.{agent_id}.credential.{credential_id}"

    def _run(self, arguments: list[str], secret: str | None = None) -> str:
        try:
            operation = arguments[0]
            if operation == "add-generic-password":
                add_secret(arguments[5], self.account, secret or "")
                return ""
            if operation == "find-generic-password":
                return get_secret(arguments[4], self.account)
            if operation == "delete-generic-password":
                delete_secret(arguments[4], self.account)
                return ""
            raise CredentialError("Unsupported Keychain operation")
        except NativeKeychainError as error:
            raise CredentialError(str(error)) from error

    def add(self, agent_id: str, provider: str, name: str, secret: str, scope: str = "") -> dict[str, Any]:
        self.store.agent(agent_id)
        if provider not in PROVIDERS:
            raise CredentialError("Unknown provider")
        name = name.strip()
        if not name or len(name) > 100:
            raise CredentialError("Credential name must be between 1 and 100 characters")
        if not secret.strip() or len(secret) > 16384:
            raise CredentialError("Credential is empty or too large")
        credential_id = secrets.token_urlsafe(9)
        # Native Keychain calls keep the secret out of process arguments and logs.
        self._run(["add-generic-password", "-U", "-a", self.account,
                   "-s", self.service(agent_id, credential_id)], secret=secret)
        record = {
            "id": credential_id, "provider": provider, "name": name,
            "scope": scope.strip()[:200], "value": "••••••••",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_verified": None, "verification": "not_tested",
        }
        self.store.put_credential(agent_id, record)
        self.store.audit("@mo:army.local", agent_id, "credential.add", f"{provider}: {name}")
        return record

    def read(self, agent_id: str, credential_id: str) -> str:
        records = [item for item in self.store.credentials(agent_id) if item["id"] == credential_id]
        if not records:
            raise CredentialError("Credential not found")
        return self._run(["find-generic-password", "-a", self.account,
                          "-s", self.service(agent_id, credential_id), "-w"])

    def delete(self, agent_id: str, credential_id: str) -> dict[str, Any]:
        record = self.store.agent(agent_id)  # Verify agent before touching metadata.
        credential = next((item for item in self.store.credentials(agent_id) if item["id"] == credential_id), None)
        if not credential:
            raise CredentialError("Credential not found")
        self._run(["delete-generic-password", "-a", self.account,
                   "-s", self.service(agent_id, credential_id)])
        deleted = self.store.delete_credential(agent_id, credential_id)
        self.store.audit("@mo:army.local", agent_id, "credential.delete", f"{credential['provider']}: {credential['name']}")
        return deleted

    def test(self, agent_id: str, credential_id: str) -> dict[str, Any]:
        credential = next((item for item in self.store.credentials(agent_id) if item["id"] == credential_id), None)
        if not credential:
            raise CredentialError("Credential not found")
        provider = credential["provider"]
        if provider not in {"GitHub", "DeepSeek", "Resend", "Kimi"}:
            credential["verification"] = "not_tested"
            credential["verification_detail"] = "No read-only test is configured for this provider"
        else:
            secret = self.read(agent_id, credential_id)
            try:
                detail = self._test_provider(provider, secret)
                credential["verification"] = "valid"
            except CredentialError as error:
                detail = str(error)
                credential["verification"] = "invalid"
            credential["last_verified"] = datetime.now(timezone.utc).isoformat()
            credential["verification_detail"] = detail
        self.store.put_credential(agent_id, credential)
        self.store.audit("@mo:army.local", agent_id, "credential.test", credential["verification"])
        return credential

    @staticmethod
    def _test_provider(provider: str, secret: str) -> str:
        targets = {
            "GitHub": ("GET", "https://api.github.com/user", {"Authorization": f"Bearer {secret}", "User-Agent": "Army-Hub-Manager"}),
            "DeepSeek": ("GET", "https://api.deepseek.com/models", {"Authorization": f"Bearer {secret}"}),
            "Resend": ("GET", "https://api.resend.com/domains", {"Authorization": f"Bearer {secret}"}),
            "Kimi": ("GET", "https://api.moonshot.ai/v1/models", {"Authorization": f"Bearer {secret}"}),
        }
        if provider not in targets:
            return "No read-only test is configured for this provider"
        method, url, headers = targets[provider]
        request = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if 200 <= response.status < 300:
                    return "Provider accepted the credential"
                raise CredentialError(f"Provider returned HTTP {response.status}")
        except urllib.error.HTTPError as error:
            raise CredentialError(f"Provider returned HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise CredentialError(f"Provider is unreachable: {error.reason}") from error

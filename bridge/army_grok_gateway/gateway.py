from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any
import urllib.error
import urllib.request

from .config import GatewaySettings


class GatewayError(RuntimeError):
    """A sanitized gateway failure; discovery tokens are never included."""


@dataclass(frozen=True)
class Reply:
    text: str
    entry_ids: tuple[str, ...]
    prompt_request_id: str | None
    shared_request_id: bool


def is_top_level_prompt(entry: dict[str, Any]) -> bool:
    return (
        entry.get("kind") == "message"
        and entry.get("role") != "assistant"
        and not entry.get("toAgent")
        and not entry.get("fromAgent")
    )


def turn_entries(entries: list[dict[str, Any]], nonce: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    prompt_index = next(
        (index for index, entry in enumerate(entries)
         if is_top_level_prompt(entry) and entry.get("clientNonce") == nonce),
        None,
    )
    if prompt_index is None:
        return None
    end = len(entries)
    for index in range(prompt_index + 1, len(entries)):
        if is_top_level_prompt(entries[index]):
            end = index
            break
    replies = [entry for entry in entries[prompt_index + 1:end] if entry.get("kind") == "send-message"]
    return entries[prompt_index], replies


def reply_text(replies: list[dict[str, Any]]) -> str:
    texts = [
        str(entry.get("message", {}).get("content", "")).strip()
        for entry in replies
        if entry.get("message", {}).get("type") == "text"
        and str(entry.get("message", {}).get("content", "")).strip()
    ]
    if texts:
        return texts[-1]
    if replies:
        return "Grok Bot needs an approval, secret, or rich interaction. Open Grok Bot on desktop to handle it safely."
    return ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class GatewayClient:
    def __init__(self, settings: GatewaySettings):
        self.settings = settings
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _token(self) -> str:
        try:
            discovery = json.loads(self.settings.discovery_path.read_text(encoding="utf-8"))
            token = discovery["token"]
            if not isinstance(token, str) or not token:
                raise ValueError
            return token
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
            raise GatewayError("Grok gateway discovery is missing or invalid") from error

    def _command(self, name: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.settings.base_url}/api/{name}",
            data=data,
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise GatewayError(f"Grok gateway {name} request failed") from error
        if isinstance(payload, dict) and payload.get("error"):
            raise GatewayError(f"Grok gateway {name} rejected the request")
        return payload.get("result", payload) if isinstance(payload, dict) else payload

    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.settings.base_url}/health", method="GET")
        try:
            with self._opener.open(request, timeout=15) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise GatewayError("Grok gateway health request failed") from error

    def list_agents(self) -> list[dict[str, Any]]:
        payload = self._command("listAgents", {})
        if isinstance(payload, list):
            return payload
        return payload.get("agents", [])

    def send_prompt(self, prompt: str, nonce: str) -> None:
        result = self._command("sendPrompt", {
            "agentId": self.settings.agent_id,
            "prompt": prompt,
            "clientNonce": nonce,
            "directAddressedAcceptance": True,
        })
        if isinstance(result, dict) and result.get("accepted") is False:
            raise GatewayError("Grok did not accept the prompt")

    def transcript(self, tail: bool = True) -> list[dict[str, Any]]:
        name = "getAgentTranscriptTail" if tail else "getAgentTranscript"
        body: dict[str, Any] = {"id": self.settings.agent_id}
        if tail:
            body["limit"] = 200
        payload = self._command(name, body)
        if isinstance(payload, list):
            return payload
        return payload.get("entries", payload.get("transcript", []))

    def prompt_observed(self, nonce: str) -> bool:
        return turn_entries(self.transcript(), nonce) is not None or turn_entries(self.transcript(False), nonce) is not None

    def is_busy(self) -> bool:
        agent = next((item for item in self.list_agents() if item.get("id") == self.settings.agent_id), {})
        return agent.get("isRunning") is True or agent.get("isComposingMessage") is True

    def wait_for_reply(self, nonce: str) -> Reply:
        deadline = time.monotonic() + self.settings.reply_timeout_seconds
        saw_busy = False
        stable_signature: tuple[str, ...] | None = None
        stable_since = 0.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                entries = self.transcript()
                turn = turn_entries(entries, nonce)
                if turn is None:
                    turn = turn_entries(self.transcript(False), nonce)
                if turn is not None:
                    prompt, replies = turn
                    text = reply_text(replies)
                    if text:
                        busy = self.is_busy()
                        if busy:
                            saw_busy = True
                            stable_signature = None
                        elif saw_busy:
                            return self._reply(prompt, replies, text)
                        else:
                            signature = tuple(str(entry.get("id", index)) for index, entry in enumerate(replies))
                            now = time.monotonic()
                            if signature != stable_signature:
                                stable_signature = signature
                                stable_since = now
                            elif now - stable_since >= self.settings.stable_reply_seconds:
                                return self._reply(prompt, replies, text)
                last_error = None
            except GatewayError as error:
                last_error = error
            time.sleep(min(self.settings.poll_interval_seconds, max(0.0, deadline - time.monotonic())))
        if last_error is not None:
            raise GatewayError("Timed out waiting for Grok after gateway errors") from last_error
        raise GatewayError("Timed out waiting for Grok to finish")

    @staticmethod
    def _reply(prompt: dict[str, Any], replies: list[dict[str, Any]], text: str) -> Reply:
        request_id = prompt.get("requestId") if isinstance(prompt.get("requestId"), str) else None
        shared = bool(request_id) and any(entry.get("requestId") == request_id for entry in replies)
        return Reply(
            text=text,
            entry_ids=tuple(str(entry.get("id", "")) for entry in replies),
            prompt_request_id=request_id,
            shared_request_id=shared,
        )

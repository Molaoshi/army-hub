from __future__ import annotations

import asyncio
from collections import defaultdict
import json
import logging
import os
from pathlib import Path
from typing import Any

from .config import AgentSettings

LOG = logging.getLogger(__name__)


class AcpError(RuntimeError):
    pass


class AcpClient:
    def __init__(self, settings: AgentSettings, timeout: float = 600.0):
        self.settings = settings
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self.pending: dict[str | int, asyncio.Future] = {}
        self.prompt_text: dict[str, list[str]] = defaultdict(list)
        self.reader_task: asyncio.Task | None = None
        self.stderr_task: asyncio.Task | None = None
        self.next_id = 1
        self.write_lock = asyncio.Lock()
        self.generation = 0

    async def start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        self.generation += 1
        Path(self.settings.cwd).mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update(self.settings.environment)
        self.process = await asyncio.create_subprocess_exec(
            *self.settings.command,
            cwd=self.settings.cwd,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.reader_task = asyncio.create_task(self._read_stdout())
        self.stderr_task = asyncio.create_task(self._read_stderr())
        await self.request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
            "clientInfo": {"name": "army-hub-bridge", "version": "0.1.0"},
        }, timeout=90)

    async def close(self) -> None:
        process = self.process
        for future in self.pending.values():
            if not future.done():
                future.cancel()
        self.pending.clear()
        try:
            if process and process.returncode is None:
                if process.stdin:
                    process.stdin.close()
                try:
                    await asyncio.wait_for(process.wait(), timeout=1)
                except asyncio.TimeoutError:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2)
                    except asyncio.TimeoutError:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                        await asyncio.wait_for(process.wait(), timeout=2)
        finally:
            tasks = [task for task in (self.reader_task, self.stderr_task) if task]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self.reader_task = None
            self.stderr_task = None
            if not process or process.returncode is not None:
                self.process = None

    async def new_session(self) -> str:
        result = await self.request("session/new", {
            "cwd": self.settings.cwd,
            "mcpServers": [],
        }, timeout=120)
        session_id = result["sessionId"]
        await self._apply_session_config(session_id, result.get("configOptions"))
        return session_id

    async def load_session(self, session_id: str) -> str:
        result = await self.request("session/load", {
            "sessionId": session_id,
            "cwd": self.settings.cwd,
            "mcpServers": [],
        }, timeout=120)
        restored_id = result.get("sessionId", session_id)
        await self._apply_session_config(restored_id, result.get("configOptions"))
        return restored_id

    async def _apply_session_config(self, session_id: str, options: list[dict[str, Any]] | None) -> None:
        """Apply only selections explicitly provisioned for an ACP-native harness."""
        current_options = options
        # Model first: the harness may replace dependent effort options afterward.
        desired = sorted(self.settings.session_config.items(), key=lambda item: item[0] != "model")
        for config_id, value in desired:
            if current_options is not None:
                option = next((item for item in current_options if item.get("id") == config_id), None)
                if not option or value not in {choice.get("value") for choice in option.get("options", [])}:
                    raise AcpError(f"Harness does not advertise {config_id}={value}")
            result = await self.request("session/set_config_option", {
                "sessionId": session_id, "configId": config_id, "value": value,
            }, timeout=60)
            current_options = result.get("configOptions", [])
            selected = next((item for item in current_options if item.get("id") == config_id), None)
            if not selected or selected.get("currentValue") != value:
                raise AcpError(f"Harness did not apply {config_id}={value}")

    async def prompt(self, session_id: str, text: str) -> str:
        self.prompt_text[session_id].clear()
        try:
            await self.request("session/prompt", {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": text}],
            }, timeout=self.timeout)
            return "".join(self.prompt_text[session_id]).strip()
        finally:
            self.prompt_text.pop(session_id, None)

    async def request(self, method: str, params: dict[str, Any], timeout: float | None = None) -> Any:
        if method != "initialize" and (not self.process or self.process.returncode is not None):
            raise AcpError("ACP process is not running")
        request_id = self.next_id
        self.next_id += 1
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending[request_id] = future
        await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            response = await asyncio.wait_for(future, timeout=timeout or self.timeout)
        except asyncio.TimeoutError as error:
            self.pending.pop(request_id, None)
            raise AcpError(f"{method} timed out after {timeout or self.timeout} seconds") from error
        except asyncio.CancelledError:
            self.pending.pop(request_id, None)
            raise
        if "error" in response:
            detail = response["error"]
            raise AcpError(f"{method}: {detail.get('message', detail)}")
        return response.get("result", {})

    async def _write(self, message: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise AcpError("ACP process is not running")
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        async with self.write_lock:
            self.process.stdin.write(payload)
            await self.process.stdin.drain()

    async def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    LOG.warning("Ignoring non-JSON ACP output from %s", self.settings.agent_id)
                    continue
                await self._handle(message)
        except (asyncio.CancelledError, ConnectionError):
            pass
        except Exception:
            LOG.exception("ACP reader failed for %s", self.settings.agent_id)
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(AcpError("ACP process closed its output"))
            self.pending.clear()

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        try:
            while line := await self.process.stderr.readline():
                LOG.info("%s: %s", self.settings.agent_id, line.decode(errors="replace").rstrip())
        except asyncio.CancelledError:
            pass

    async def _handle(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if request_id is not None and ("result" in message or "error" in message):
            future = self.pending.pop(request_id, None)
            if future and not future.done():
                future.set_result(message)
            return

        method = message.get("method")
        params = message.get("params", {})
        if method == "session/update":
            session_id = params.get("sessionId")
            update = params.get("update", {})
            if update.get("sessionUpdate") == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text" and session_id:
                    self.prompt_text[session_id].append(content.get("text", ""))
            return

        if request_id is not None and method:
            await self._handle_agent_request(request_id, method, params)

    async def _handle_agent_request(self, request_id: str | int, method: str, params: dict[str, Any]) -> None:
        if method == "session/request_permission":
            # Until interactive Matrix approvals are implemented, fail closed.
            response = {"result": {"outcome": {"outcome": "cancelled"}}}
        elif method in {"session/terminal-output", "session/terminal-wait_for_exit", "session/terminal-kill", "session/terminal-release"}:
            response = {"error": {"code": -32601, "message": "Client terminals are disabled"}}
        elif method in {"fs/read_text_file", "fs/write_text_file"}:
            response = {"error": {"code": -32601, "message": "Client filesystem access is disabled"}}
        elif method == "session/elicitation":
            response = {"result": {"action": "cancel"}}
        else:
            response = {"error": {"code": -32601, "message": f"Unsupported client method: {method}"}}
        await self._write({"jsonrpc": "2.0", "id": request_id, **response})


class SessionManager:
    def __init__(self, settings: AgentSettings, timeout: float):
        self.client = AcpClient(settings, timeout)
        self.sessions: dict[str, str] = {}
        self.session_generations: dict[str, int] = {}
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def ensure_session(self, key: str, saved_session_id: str | None = None) -> str:
        await self.client.start()
        if key in self.sessions and self.session_generations.get(key) == self.client.generation:
            return self.sessions[key]
        session_id = saved_session_id or self.sessions.get(key)
        if session_id:
            try:
                self.sessions[key] = await self.client.load_session(session_id)
                self.session_generations[key] = self.client.generation
                return self.sessions[key]
            except AcpError as error:
                LOG.warning("Could not reload ACP session for %s: %s", key, error)
        self.sessions[key] = await self.client.new_session()
        self.session_generations[key] = self.client.generation
        return self.sessions[key]

    async def prompt(self, key: str, text: str, saved_session_id: str | None = None) -> tuple[str, str]:
        async with self.locks[key]:
            session_id = await self.ensure_session(key, saved_session_id)
            response = await self.client.prompt(session_id, text)
            if not response:
                raise AcpError("Harness returned an empty response")
            return session_id, response

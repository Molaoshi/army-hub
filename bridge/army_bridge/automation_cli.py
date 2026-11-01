from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def default_runtime_root() -> Path:
    return Path(__file__).resolve().parents[2] / ".runtime" / "automation"


def connection(runtime_root: Path, agent_id: str) -> tuple[str, str]:
    root = runtime_root / agent_id
    url = (root / "url").read_text(encoding="utf-8").strip().rstrip("/")
    token = (root / "token").read_text(encoding="utf-8").strip()
    if not url.startswith("http://127.0.0.1:"):
        raise RuntimeError("automation URL is not loopback")
    return url, token


def request(
    runtime_root: Path,
    agent_id: str,
    method: str,
    path: str,
    payload: dict | None = None,
) -> dict:
    base, token = connection(runtime_root, agent_id)
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        base + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error)
        except Exception:
            detail = {"error": str(error)}
        raise RuntimeError(detail.get("error", str(error))) from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Army Hub local agent automation CLI")
    parser.add_argument("--runtime-root", type=Path, default=default_runtime_root())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("agents", help="List running agents with local automation enabled")

    send = sub.add_parser("send", help="Queue a message for an agent")
    send.add_argument("agent")
    send.add_argument("text")
    send.add_argument("--conversation", default="default")
    send.add_argument("--idempotency-key", default=uuid4().hex)

    for name in ("status", "cancel"):
        command = sub.add_parser(name)
        command.add_argument("agent")
        command.add_argument("delivery_id")

    edit = sub.add_parser("edit", help="Edit a queued automation message")
    edit.add_argument("agent")
    edit.add_argument("delivery_id")
    edit.add_argument("text")

    pending = sub.add_parser("pending")
    pending.add_argument("agent")
    args = parser.parse_args()

    if args.command == "agents":
        records = []
        if args.runtime_root.is_dir():
            for child in sorted(args.runtime_root.iterdir()):
                url_file = child / "url"
                if child.is_dir() and url_file.is_file():
                    records.append({"id": child.name, "url": url_file.read_text().strip()})
        result: object = {"agents": records}
    elif args.command == "send":
        result = request(
            args.runtime_root,
            args.agent,
            "POST",
            f"/v1/agents/{args.agent}/messages",
            {
                "text": args.text,
                "conversation_id": args.conversation,
                "idempotency_key": args.idempotency_key,
            },
        )
    elif args.command == "status":
        result = request(
            args.runtime_root, args.agent, "GET", f"/v1/agents/{args.agent}/deliveries/{args.delivery_id}"
        )
    elif args.command == "cancel":
        result = request(
            args.runtime_root,
            args.agent,
            "POST",
            f"/v1/agents/{args.agent}/deliveries/{args.delivery_id}/cancel",
            {},
        )
    elif args.command == "edit":
        result = request(
            args.runtime_root,
            args.agent,
            "PATCH",
            f"/v1/agents/{args.agent}/deliveries/{args.delivery_id}",
            {"text": args.text},
        )
    else:
        result = request(args.runtime_root, args.agent, "GET", f"/v1/agents/{args.agent}/pending")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from None

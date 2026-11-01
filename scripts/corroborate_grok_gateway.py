#!/usr/bin/env python3
"""Correlate Matrix turns with one persistent native Grok Bot transcript."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))

from army_grok_gateway.config import load_settings  # noqa: E402
from army_grok_gateway.gateway import GatewayClient, reply_text, turn_entries  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("first_matrix_event")
    parser.add_argument("second_matrix_event")
    parser.add_argument("--marker", required=True)
    parser.add_argument("--config", default=str(ROOT / ".runtime" / "grok-gateway.yaml"))
    args = parser.parse_args()

    settings = load_settings(args.config)
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    records = {
        item.get("reply_to"): item
        for item in state.get("completed_turns", [])
        if item.get("reply_to") in {args.first_matrix_event, args.second_matrix_event}
    }
    missing = {args.first_matrix_event, args.second_matrix_event} - records.keys()
    if missing:
        raise SystemExit("Missing completed Matrix turns in connector state")

    gateway = GatewayClient(settings.gateway)
    transcript = gateway.transcript(tail=False)
    turns = []
    for event_id in (args.first_matrix_event, args.second_matrix_event):
        record = records[event_id]
        nonce = record["nonce"]
        native = turn_entries(transcript, nonce)
        if native is None:
            raise SystemExit(f"Native transcript does not contain clientNonce {nonce}")
        prompt, replies = native
        # Native prompt text has appeared under different envelope shapes across
        # gateway versions; inspect the selected prompt only, never the transcript.
        prompt_payload = json.dumps(prompt, ensure_ascii=False)
        response_text = reply_text(replies)
        turns.append({
            "matrix_event_id": event_id,
            "client_nonce": nonce,
            "prompt_observed": True,
            "reply_observed": bool(replies),
            "marker_in_prompt": args.marker in prompt_payload,
            "marker_in_reply": args.marker in response_text,
            "grok_entry_ids": [str(item.get("id", "")) for item in replies],
            "request_id": prompt.get("requestId"),
        })

    if not turns[0]["marker_in_prompt"] or not turns[0]["reply_observed"]:
        raise SystemExit("First native turn failed marker/reply correlation")
    if not turns[1]["reply_observed"] or not turns[1]["marker_in_reply"]:
        raise SystemExit("Second native reply did not recover the exact marker")

    print(json.dumps({
        "status": "passed",
        "persistent_agent_id": settings.gateway.agent_id,
        "native_transcript_turns": turns,
    }, indent=2))


if __name__ == "__main__":
    main()

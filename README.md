# Army Hub

Private Matrix-based collaboration for Mo and harness-running agents on the mini, Dell, Book, and future machines.

- **Matrix/Synapse:** shared conversation history.
- **PostgreSQL:** durable server storage.
- **Element:** iPhone, Android, desktop, and web clients.
- **ACP bridge:** identical mention-only and anti-loop behavior for Hermes, DSH, and future ACP-compatible harnesses.
- **Grok connector:** native host-gateway adapter using one persistent Grok Bot conversation over private Tailscale, supervised alongside `tailscaled`; Cloudflare and the signed-webhook/MCP routine are stopped rollback options.
- **GitHub:** canonical code, pull requests, reviews, and releases.

Read `HANDOVER.md` for current verified state, `docs/implementation-spec.md` for the messaging contract, `docs/agent-manager-spec.md` for the control-panel contract, and `BACKLOG.md` for deferred work. Runtime secrets and data are under `.runtime/` and are never committed.

## Operate

```sh
docker compose ps
sh scripts/install_bridges.sh
sh scripts/install_manager.sh
PYTHONPATH=manager .venv-service/bin/python -m pytest -q manager/tests bridge/tests
```

Hermes Mini, DSH Mini, and the native persistent Grok connector are active. The tailnet-only Agent Manager provides live discovery, dependent creation choices, Matrix profile/avatar editing, per-agent Keychain credentials, sanitized logs, and isolated connector controls. Dell and Book identities remain reserved. Physical iPhone enrollment and background push remain unverified. See `docs/grok-connector.md` before operating Grok: its connector runs on Grok Bot's computer, and the legacy webhook adapter must remain stopped.

## Local service endpoints

- Agent Manager via Tailscale: `https://moatazs-mac-mini.tailef80eb.ts.net:8446/`
- Matrix via Tailscale: `https://moatazs-mac-mini.tailef80eb.ts.net:8444/`
- Element via Tailscale: `https://moatazs-mac-mini.tailef80eb.ts.net:8445/`
- Agent Manager via loopback: `http://127.0.0.1:3104/`
- Matrix via loopback: `http://127.0.0.1:8010/`
- Element via loopback: `http://127.0.0.1:3103/`

The older `chat-hub` deployment is separate and is not managed by this repository.

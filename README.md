# Army Hub

Private Matrix-based collaboration for Mo and harness-running agents on the mini, Dell, Book, and future machines.

- **Matrix/Synapse:** shared conversation history.
- **PostgreSQL:** durable server storage.
- **Element:** iPhone, Android, desktop, and web clients.
- **ACP bridge:** identical mention-only and anti-loop behavior for Hermes, DSH, and future ACP-compatible harnesses.
- **Grok connector:** signed webhook routines plus a single-use MCP reply tool for the real Grok cloud harness.
- **GitHub:** canonical code, pull requests, reviews, and releases.

Read `HANDOVER.md` for current verified state, `docs/implementation-spec.md` for the operating contract, and `BACKLOG.md` for deferred work. Runtime secrets and data are under `.runtime/` and are never committed.

## Operate

```sh
docker compose ps
sh scripts/install_bridges.sh
sh scripts/install_grok.sh
.venv-service/bin/python -m pytest
```

Hermes Mini, DSH Mini, and Grok are active. Dell and Book identities remain reserved. Physical iPhone enrollment and background push remain unverified. See `docs/grok-connector.md` for Grok's operating limits and quick-tunnel caveat.

## Local service endpoints

- Matrix via Tailscale: `https://moatazs-mac-mini.tailef80eb.ts.net:8444/`
- Element via Tailscale: `https://moatazs-mac-mini.tailef80eb.ts.net:8445/`
- Matrix via loopback: `http://127.0.0.1:8010/`
- Element via loopback: `http://127.0.0.1:3103/`

The older `chat-hub` deployment is separate and is not managed by this repository.

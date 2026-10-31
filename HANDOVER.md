# Army Hub handover

## Current state

Army Hub is a private, tailnet-only Matrix deployment on Mo's Mac mini. Synapse, PostgreSQL, Element Web, and the nightly backup scheduler run in Docker. Hermes Mini and DSH Mini use the same mention-only Matrix-to-ACP bridge. Grok uses a separate signed-webhook/MCP adapter to its real cloud automation harness.

Verified on 2026-10-31:

- All Docker services and both tailnet HTTPS routes are healthy.
- All six provisioned Matrix access tokens passed `whoami` during provisioning.
- Real ACP turns passed independently for Hermes and DSH.
- Five live Matrix acceptance tests passed: unmentioned silence, direct Hermes and DSH threaded replies, a Hermes → DSH → Hermes handoff, and the six-turn stop.
- Five live Grok acceptance tests passed: unmentioned silence, a real Grok threaded MCP reply, single-use callback rejection, a Hermes → Grok → Hermes handoff, and the six-turn stop.
- A local backup was created, its 831-entry manifest was checked, and the dump restored into an isolated database containing all three rooms.

## Live map

- Matrix: `https://moatazs-mac-mini.tailef80eb.ts.net:8444/`
- Element: `https://moatazs-mac-mini.tailef80eb.ts.net:8445/`
- Rooms: `army-lab`, `project-army-hub`, and `approvals`.
- Active connectors: `hermes-mini`, `dsh-mini`, `grok`.
- Reserved identities only: `hermes-dell`, `hermes-book`.
- Runtime secrets, databases, credentials, logs, backups, PID files, and sync state are under ignored `.runtime/`.

## Operating laws

- Every agent turn requires an explicit mention, including agent-to-agent replies. `@room` does not trigger agents.
- Matrix is discussion and status; GitHub branches and PRs are canonical code and review history.
- Mo approves merges, deployments, deletion, credential changes, force pushes, and spending.
- Do not alter Tailscale exit-node, Sing-box, or proxy routing for this project.
- Do not touch the older `Chat UI/chat-hub` deployment.
- Keep steady-state load low. The backup container is dormant except for its nightly job; idle connectors only long-poll Matrix.

## Cold-start commands

```sh
cd /Users/immortalist/Documents/Kimi/Workspaces/MacServer/army-hub
docker compose ps
sh scripts/install_bridges.sh
sh scripts/install_grok.sh
.venv-service/bin/python -m pytest
```

Read `docs/operations.md` before restarting anything, `docs/implementation-spec.md` before changing protocol behavior, and `docs/grok-connector.md` before operating the Grok integration. Read `BACKLOG.md` for deferred work.

## Known boundaries

- Physical iPhone login, cellular messaging, attachments, and background push still need Mo's device. Push is not verified.
- Interactive ACP tool-permission requests fail closed. Matrix is not yet a tool-approval interface.
- macOS launchd cannot read this Documents-hosted repository under the current privacy policy. Connectors start through the authorized desktop session; automatic login startup is deferred rather than weakening TCC.
- Grok runs one asynchronous cloud routine per mention. It does not import or share Grok Bot's primary-chat history or memory; Matrix holds the shared thread.
- Grok currently uses a Cloudflare quick tunnel. Its hostname changes if the tunnel is recreated, requiring an update to Grok's custom connector URL.
- Off-Mac encrypted backup is not configured.
- ACP `session/load` recovery after harness-process death has implementation coverage but has not yet received a dedicated live failure-injection test.

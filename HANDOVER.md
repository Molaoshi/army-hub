# Army Hub handover

## Current state

Army Hub is a private, tailnet-only Matrix deployment on Mo's Mac mini. Synapse, PostgreSQL, Element Web, and the nightly backup scheduler run in Docker. Hermes Mini and DSH Mini use the same mention-only Matrix-to-ACP bridge.

Verified on 2026-10-31:

- All Docker services and the Matrix, Element, and Agent Manager tailnet HTTPS routes are healthy.
- All six provisioned Matrix access tokens passed `whoami` during provisioning.
- Real ACP turns passed independently for Hermes and DSH.
- Five live Matrix acceptance tests passed: unmentioned silence, direct Hermes and DSH threaded replies, a Hermes → DSH → Hermes handoff, and the six-turn stop.
- A local backup was created, its 831-entry manifest was checked, and the dump restored into an isolated database containing all three rooms.
- The Agent Manager passed 25 combined manager/bridge tests plus live Matrix, Keychain, profile/avatar, isolated-restart, and real browser acceptance. Grok and the temporary credential were restored/removed afterward; Hermes and DSH stayed running. Reserved identities cannot be paused, and unsupported credential tests remain `not_tested` rather than reporting false validity.

## Live map

- Agent Manager: `https://moatazs-mac-mini.tailef80eb.ts.net:8446/` (loopback `127.0.0.1:3104`).
- Matrix: `https://moatazs-mac-mini.tailef80eb.ts.net:8444/`
- Element: `https://moatazs-mac-mini.tailef80eb.ts.net:8445/`
- Rooms: `army-lab`, `project-army-hub`, and `approvals`.
- Active connectors: `hermes-mini`, `dsh-mini`.
- Reserved identities only: `hermes-dell`, `hermes-book`, `grok`.
- Runtime secrets, databases, credentials, logs, backups, PID files, and sync state are under ignored `.runtime/`. Agent-specific pasted credentials live in macOS Keychain; metadata contains no secret values.

## Operating laws

- Every agent turn requires an explicit mention, including agent-to-agent replies. `@room` does not trigger agents.
- Matrix is discussion and status; GitHub branches and PRs are canonical code and review history.
- Mo approves merges, deployments, deletion, credential changes, force pushes, and spending.
- Do not alter Tailscale exit-node, Sing-box, or proxy routing for this project. The Agent Manager has only its own HTTPS Serve route on 8446.
- Do not touch the older `Chat UI/chat-hub` deployment.
- Keep steady-state load low. The backup container is dormant except for its nightly job; idle connectors only long-poll Matrix. Inventory refresh is on demand and does not invoke paid completions.

## Cold-start commands

```sh
cd /Users/immortalist/Documents/Kimi/Workspaces/MacServer/army-hub
docker compose ps
sh scripts/install_bridges.sh
sh scripts/install_manager.sh
PYTHONPATH=manager .venv-service/bin/python -m pytest -q manager/tests bridge/tests
```

Read `docs/operations.md` before restarting anything, `docs/implementation-spec.md` before changing protocol behavior, and `docs/agent-manager-spec.md` before changing the manager. Read `BACKLOG.md` for deferred work.

## Known boundaries

- Real creation of an additional Matrix agent and its first paid harness turn remain unverified; creation/configuration have unit and mocked coverage, while the browser form was tested without submitting a new identity.
- Effort is intentionally hidden because the current ACP path has no verified per-agent effort setter. DSH exposes only its harness profile default; Hermes exposes the detected DeepSeek Pro and Flash choices.
- Only Mini is enrolled for creation. Dell and Book are visible but unavailable until their connector/inventory path is enrolled.
- Railway, MiniMax, and Other credential tests report that no read-only provider check is configured; GitHub, DeepSeek, Resend, and Kimi have read-only checks.
- Physical iPhone login, cellular messaging, attachments, and background push still need Mo's device. Push is not verified.
- Interactive ACP tool-permission requests fail closed. Matrix is not yet a tool-approval interface.
- macOS launchd cannot read this Documents-hosted repository under the current privacy policy. Connectors and the manager start through the authorized desktop session; automatic login startup is deferred rather than weakening TCC.
- Off-Mac encrypted backup is not configured.
- ACP `session/load` recovery after harness-process death has implementation coverage but has not yet received a dedicated live failure-injection test.

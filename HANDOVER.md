# Army Hub handover

## Current state

Army Hub is a private Matrix deployment on Mo's Mac mini. Synapse, PostgreSQL, Element Web, and the nightly backup scheduler run in Docker. Hermes Mini and DSH Mini use the same mention-only Matrix-to-ACP bridge. Grok uses a separate native host-gateway adapter on Grok Bot's cloud computer and one persistent Bot conversation. It reaches Matrix through the existing tailnet, and Supervisor manages both `army-grok` and `tailscaled`. Cloudflare and the earlier signed-webhook/MCP adapter are stopped and preserved for rollback; never run both Grok adapters together.

Verified on 2026-10-31:

- All Docker services and both tailnet HTTPS routes are healthy.
- All six provisioned Matrix access tokens passed `whoami` during provisioning.
- Real ACP turns passed independently for Hermes and DSH.
- Five live Matrix acceptance tests passed: unmentioned silence, direct Hermes and DSH threaded replies, a Hermes → DSH → Hermes handoff, and the six-turn stop.
- Native Grok acceptance passed unmentioned silence and two-turn memory; native transcript corroboration matched both turns to one persistent Bot conversation by exact `clientNonce`.

Verified on 2026-11-01:

- Grok Bot's VM is enrolled as `grok-bot` at `100.124.54.69`; remote `tailscale ping` to the mini succeeded and Matrix over the private HTTPS endpoint returned `302`.
- With Cloudflare stopped, the complete live Matrix acceptance passed again: unmentioned silence and exact two-turn recovery of `ARMY-MEMORY-2cabfac5e81f` without repeating the marker.
- Supervisor restarted `army-grok` after PID `77939` was terminated; replacement PID `80754` reported `RUNNING`.
- Supervisor restarted the actual `tailscaled` child after PID `69973` was terminated; replacement PID `81342` reported `RUNNING` and Tailscale returned to backend state `Running`.
- Stopping Supervisor PID `69968` and starting it again restored both programs to `RUNNING`; Tailscale was `Running` and private Matrix HTTPS returned `302`.
- The former Cloudflare quick-tunnel process was stopped and no matching process remained.
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
.venv-service/bin/python -m pytest
```

Read `docs/operations.md` before restarting anything, `docs/implementation-spec.md` before changing protocol behavior, and `docs/grok-connector.md` before operating the Grok integration. Read `BACKLOG.md` for deferred work.

## Known boundaries

- Physical iPhone login, cellular messaging, attachments, and background push still need Mo's device. Push is not verified.
- Interactive ACP tool-permission requests fail closed. Matrix is not yet a tool-approval interface.
- macOS launchd cannot read this Documents-hosted repository under the current privacy policy. Connectors start through the authorized desktop session; automatic login startup is deferred rather than weakening TCC.
- Grok uses one persistent native Bot conversation. Its host gateway is unofficial and version-dependent; live acceptance is required after gateway updates.
- Supervisor restarts the remote connector and `tailscaled` after process death. Desktop-login autostart is installed, but boot-before-login startup was not tested or provided. Automatic recovery from total VM replacement is not verified; secure re-enrollment and configuration restoration would be required.
- Off-Mac encrypted backup is not configured.
- ACP `session/load` recovery after harness-process death has implementation coverage but has not yet received a dedicated live failure-injection test.

# Army Hub handover

## Current state

Army Hub is a private Matrix deployment on Mo's Mac mini. Synapse, PostgreSQL, Element Web, and the nightly backup scheduler run in Docker. Hermes Mini and DSH Mini use the same mention-only Matrix-to-ACP bridge. Grok uses a separate native host-gateway adapter on Grok Bot's cloud computer and one persistent Bot conversation. It reaches Matrix through the existing tailnet, and Supervisor manages both `army-grok` and `tailscaled`. Cloudflare and the earlier signed-webhook/MCP adapter are stopped and preserved for rollback; never run both Grok adapters together.

Development on 2026-11-01 added a durable per-agent ACP mailbox, Matrix outbox, conservative restart recovery, and an opt-in loopback automation API/CLI. Hermes Mini and DSH Mini now use these features live; automation remains opt-in and is not enabled for Grok. Online SQLite mailbox backup is deployed in the existing `army-backup` container. Agent Manager discovers Hermes, DSH, and OpenCode through native ACP, validates provider/model pairs, and applies verified model/effort settings on new and restored sessions. DSH retains `DSH_MODEL` as its launch default while native ACP applies the exact model and effort. Hermes now reconciles every refreshed native provider catalog with exact ACP-applied selections and omits unreachable custom providers. OpenCode uses the same Ollama runtime configuration for discovery and connector startup, then intersects its connected native provider/model roster with exact ACP-applied selections. Failed discovery returns no selectable choices; stale inventory remains status metadata only and is never rendered. The full manager/bridge suite passes 67 tests, with one unrelated FastAPI/Starlette deprecation warning.

Verified on 2026-11-02:

- Agent Manager live discovery returned 20 Hermes models across `deepseek`, `kimi-coding`, and `kimi-coding-cn`, both DSH DeepSeek models, and 33 OpenCode models across `ollama-cloud` and `opencode`. Every returned Hermes and OpenCode provider/model pair applied exactly through ACP. Grok remains an existing native-remote capability and cannot be created as local ACP.
- Isolated Hermes and OpenCode bridge sessions applied and verified provider/model/effort on both `session/new` and `session/load` without sending a prompt. A probe proved Hermes' global CLI model flags alone do not configure ACP, so the connector uses native session configuration instead.
- A separate prompt-free DSH probe applied both DeepSeek Official model IDs exactly and verified all four native effort values—`off`, `low`, `high`, and `max`—for each model through the `effort` ACP option.
- The real browser create form rendered all 20 Hermes and 33 OpenCode choices with zero disabled options. Disconnected Kimi and LiteLLM entries were absent; selecting OpenCode MiniMax M3.1 Flash displayed `low`, `medium`, `high`, `xhigh`, and `max`. The form was not submitted.
- Live manager acceptance passed after a manager-only restart; the manager PID is `30032`, and local and tailnet health checks passed. LiteLLM Gateway was removed from Hermes, while Ahia Local remains configured but unreachable custom entries are absent. The original Hermes/DSH/Grok connector PIDs remained unchanged, and no Matrix identity or paid model turn was created.
- Real automation turns completed through Hermes and DSH with exact responses `HERMES-AUTOMATION-OK` and `DSH-AUTOMATION-OK`; CLI discovery found both loopback endpoints.
- Replaying Hermes idempotency key `live-hermes-20261102-001` returned the original completed delivery with `created=false`.
- Hermes recalled exact marker `HERMES-MEMORY-20261102` in the same automation conversation after a connector-only restart.
- All five live Matrix acceptance tests passed again: unmentioned silence, direct Hermes and DSH threaded replies, a Hermes → DSH → Hermes handoff, and the six-turn stop.
- A controlled SIGTERM during a running Hermes automation turn changed delivery `f7071ec87cb3446f9758ea14dd439eb3` to `interrupted`; it stayed terminal after restart and an idempotent replay did not rerun it. DSH remained unchanged throughout that test.
- Backup `army-hub-20261101T162807Z.tar.gz` contains both Hermes and DSH mailbox snapshots; every snapshot passed SQLite `integrity_check` and SHA-256 verification against its manifest.
- Element Web, Matrix, and Agent Manager returned HTTP 200 locally and through their tailnet routes. The Element and Agent Manager sign-in screens rendered successfully in a real browser; a signed-in session on Mo's physical device remains a separate acceptance step.
- Grok Bot's cloud computer had been offline for about nine hours and did not answer a live mention. Opening the existing Army Hub Bot and selecting **Show computer** woke it; Tailscale returned, the connector recovered the queued first reply, and a second turn recalled exact marker `ARMY-MEMORY-a5dbf685a069`.
- During that recovery, iPhone 13 was offline from Tailscale and iPhone 15 was active. A device disconnected from the tailnet cannot reach the private Army Hub routes.

Verified on 2026-10-31:

- All Docker services and the Matrix, Element, and Agent Manager tailnet HTTPS routes are healthy.
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
- The Agent Manager passed 25 combined manager/bridge tests plus live Matrix, Keychain, profile/avatar, isolated-restart, and real browser acceptance. Grok and the temporary credential were restored/removed afterward; Hermes and DSH stayed running. Reserved identities cannot be paused, and unsupported credential tests remain `not_tested` rather than reporting false validity.

## Live map

- Agent Manager: `https://moatazs-mac-mini.tailef80eb.ts.net:8446/` (loopback `127.0.0.1:3104`).
- Matrix: `https://moatazs-mac-mini.tailef80eb.ts.net:8444/`
- Element: `https://moatazs-mac-mini.tailef80eb.ts.net:8445/`
- Rooms: `army-lab`, `project-army-hub`, and `approvals`.
- Active connectors: `hermes-mini`, `dsh-mini`, `grok`.
- Reserved identities only: `hermes-dell`, `hermes-book`.
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

Read `docs/operations.md` before restarting anything, `docs/implementation-spec.md` before changing protocol behavior, `docs/agent-manager-spec.md` before changing the manager, and `docs/grok-connector.md` before operating the Grok integration. Read `BACKLOG.md` for deferred work.

## Known boundaries

- Real creation of an additional Matrix agent and its first paid harness turn remain unverified; creation/configuration have unit and mocked coverage, while the browser form was tested without submitting a new identity.
- Effort appears only for Hermes, DSH, and OpenCode models where ACP advertises and accepts it. DSH's four effort values are prompt-free configuration-verified, not paid-turn quality tests. Hermes custom `/models` checks establish endpoint reachability only, not credential validity or completion health. Grok has no generic local model selector or additional-identity provisioning path.
- Only Mini is enrolled for creation. Dell and Book are visible but unavailable until their connector/inventory path is enrolled.
- Railway, MiniMax, and Other credential tests report that no read-only provider check is configured; GitHub, DeepSeek, Resend, and Kimi have read-only checks.
- Physical iPhone login, cellular messaging, attachments, and background push still need Mo's device. Push is not verified.
- Interactive ACP tool-permission requests fail closed. Matrix is not yet a tool-approval interface.
- macOS launchd cannot read this Documents-hosted repository under the current privacy policy. Connectors and the manager start through the authorized desktop session; automatic login startup is deferred rather than weakening TCC.
- Grok uses one persistent native Bot conversation. Its host gateway is unofficial and version-dependent; live acceptance is required after gateway updates.
- Supervisor restarts the remote connector and `tailscaled` after process death. Desktop-login autostart is installed, but boot-before-login startup was not tested or provided. Automatic recovery from total VM replacement is not verified; secure re-enrollment and configuration restoration would be required.
- Off-Mac encrypted backup is not configured.
- ACP `session/load` recovery after harness-process death has implementation coverage but has not yet received a dedicated live failure-injection test.
- Local automation has no ACP provider-history backfill, and cancellation of an already-running turn is not verified. Buzz has not yet been configured to use the API.
- Lazy tool discovery, Matrix approvals/human takeover, reviewed memory consolidation, and pinned runtimes/canary upgrades remain unimplemented.

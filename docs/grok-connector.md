# Grok connector

## Current default: persistent native Grok Bot

The live connector uses Grok Bot's native host gateway and one persistent Bot conversation. It does not use an xAI model-only API, and it does not create a new automation run for each mention.

Verified on 2026-10-31:

- The native gateway health check passed for persistent agent `02551c84-3200-462e-a5b0-fcbf87231884`.
- An unmentioned Matrix message stayed silent.
- In the first Matrix turn, Mo's test user asked Grok to remember `ARMY-MEMORY-9df268d87dfd`.
- In a second, separate Matrix turn that did not repeat the marker, Grok returned the exact marker in the originating thread.
- Native transcript corroboration found both prompts and both replies in that same persistent Bot conversation, matched by their exact `clientNonce` values. The first native prompt contained the marker; the second native reply contained it.
- The legacy webhook connector was stopped before the native connector started. The two adapters must never run together.

Matrix acceptance evidence is in ignored `.runtime/grok-gateway-verification-results.json`. The sanitized native-transcript evidence is in ignored `.runtime/grok-native-corroboration.json`.

## Architecture

```text
Matrix mention to @grok
  → supervised native-gateway connector on Grok Bot's computer
  → loopback-only Grok host gateway (127.0.0.1:1340)
  → one persistent Army Hub Bot conversation
  → connector reads the matching native transcript turn
  → @grok:army.local reply in the original Matrix thread

Remote connector ↔ Mac Matrix
  → existing private tailnet (`grok-bot` → `moatazs-mac-mini`)
  → Tailscale HTTPS on port 8444
  → Matrix Client API on loopback port 8010
  → bearer-authenticated Matrix requests
```

Supervisor manages both `army-grok` and `tailscaled`, restarting either after process death. Desktop-login autostart launches Supervisor. Cloudflare is stopped and retained only as rollback configuration.

Every accepted Matrix turn receives a random `clientNonce`. The connector persists pending and completed turns, resumes its Matrix cursor, matches native transcript entries by that nonce, and replies in the originating Matrix thread. It reuses Army Hub's admission policy: approved rooms and senders, explicit mentions only, no `@room`, event deduplication, repeated-delegation suppression, threading, mention metadata, and the six-agent-turn limit.

One native Bot conversation supplies Grok-side continuity across Matrix messages and threads. Matrix remains the shared, inspectable collaboration record; it is not a per-thread Grok memory partition.

## Security boundaries and API risk

- The host gateway is an **unofficial, version-dependent Grok desktop interface**. Its endpoints or transcript envelope may change without notice. Health checks and live acceptance must follow a Grok Bot update.
- The gateway listens only on remote loopback. Its discovery token stays in `/home/box/sand-data/gateway.json`; the Mac never receives it.
- The remote connector configuration is owner-only (`chmod 600`) at `/home/box/army-hub/.runtime/grok-gateway.yaml`. Runtime state, logs, credentials, and rollback tunnel URLs remain ignored by git.
- Configuration was transferred using a fresh remote-held RSA-3072 private key, RSA-OAEP-SHA256, and AES-256-GCM. Only the public key and ciphertext crossed the temporary paste service; plaintext configuration and private keys did not. Transfer material was deleted afterward.
- Matrix access is tailnet-only by default, but network location does not replace authorization: every request still requires a valid Matrix bearer token. Never log or commit it.
- The connector cannot answer itself or bypass the shared agent-turn budget. Consequential actions remain subject to Mo's approval.

## Operate the native connector

On the Mac, stop the legacy adapter and render the ignored Tailscale configuration without printing its contents:

```sh
sh scripts/stop_grok.sh
.venv-service/bin/python scripts/configure_grok_gateway.py --transport tailscale
```

Securely transfer the configuration to `/home/box/army-hub/.runtime/grok-gateway.yaml`, keep mode `600`, and never paste plaintext configuration into Matrix, Grok chat, GitHub, or a paste service. On Grok Bot's computer, from `/home/box/army-hub`:

```sh
sh scripts/install_grok_supervisor.sh
sh scripts/status_grok_supervisor.sh
sh scripts/stop_grok_supervisor.sh
sh scripts/start_grok_supervisor.sh
```

The installer supervises both `army-grok` and `tailscaled` and installs desktop-login autostart. If apt mirrors fail, install Tailscale from its official static package; do not change unrelated proxy or routing settings. Initial enrollment uses `sudo tailscale up --hostname=grok-bot` and Mo's existing tailnet account.

The remote log is `.runtime/grok-gateway.log`; remote state is `.runtime/grok-gateway-state.json`. Do not dump either file into chat because logs or state may contain message content.

Run Matrix acceptance from the Mac:

```sh
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  .venv-service/bin/python scripts/verify_grok_gateway.py
```

This posts real test messages in `Army Lab`. It checks unmentioned silence and exact two-turn memory using a fresh marker. With Cloudflare stopped, the 2026-11-01 run recovered `ARMY-MEMORY-2cabfac5e81f`; current results are in `.runtime/grok-gateway-verification-results.json` and a preserved copy is `.runtime/grok-tailscale-only-verification-results.json`.

To corroborate a completed pair in the native transcript, run on Grok Bot's computer with the two incoming Matrix event IDs and marker:

```sh
.venv-service/bin/python scripts/corroborate_grok_gateway.py \
  '<first-matrix-event-id>' '<second-matrix-event-id>' \
  --marker '<exact-marker>'
```

The corroboration command reads the transcript but does not invoke another model turn. It emits only sanitized correlation evidence, not prompt or transcript bodies.

## Availability

- Failure injection verified that Supervisor restarted `army-grok` from PID `77939` to `80754`, and the actual `tailscaled` child from PID `69973` to `81342`; both replacements reported `RUNNING`, with Tailscale backend state `Running`.
- Stopping Supervisor PID `69968` and starting it again restored both programs; private Matrix HTTPS returned `302`.
- Desktop-login autostart is installed but an actual logout/login was not tested. Boot-before-login startup is not provided. Total VM-replacement recovery is not verified and requires secure re-enrollment and configuration restoration.
- The persistent Bot conversation and gateway depend on Grok Bot's cloud computer and unofficial host interface being available. Deeper interruption, sleep, and gateway-update recovery must be tested rather than assumed.
- Cloudflare is stopped rollback-only configuration. To restore that transport deliberately, use `--transport cloudflare`, recreate the tunnel, securely transfer its regenerated configuration, and restart the connector. Do not run Cloudflare alongside the Tailscale deployment.
- No unrelated Tailscale exit-node, Sing-box, proxy-routing, TCC, or older Chat UI settings are changed by this connector.

## Rollback: stateless webhook routine

The previous signed-webhook/MCP implementation remains intact under `bridge/army_grok/` with its original scripts and tests. It is rollback-only and must not run concurrently with the native connector.

For rollback, stop the native connector on Grok Bot's computer, then start the legacy adapter on the Mac:

```sh
sh scripts/install_grok.sh
```

The legacy path starts a new asynchronous cloud automation routine per mention. It has no persistent native Bot memory. Its public quick tunnel exposes only the high-entropy, single-use `army_reply` MCP path on loopback port `3105`, not Matrix. Its own logs are `.runtime/grok.log` and `.runtime/grok-tunnel.log`; its acceptance report is `.runtime/grok-verification-results.json`.

The legacy adapter previously passed five live Matrix tests: unmentioned silence, threaded MCP reply, single-use callback rejection, Hermes → Grok → Hermes handoff, and the six-turn stop. These are historical rollback evidence, not proof of native persistence.

Official references for the rollback adapter:

- `https://docs.x.ai/grok/automations/webhooks`
- `https://docs.x.ai/grok/connectors#custom-mcp-connectors`
- `https://docs.x.ai/grok/connectors/custom-mcp-tunneling`

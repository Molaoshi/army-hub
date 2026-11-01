# Army Hub implementation specification

## Goal

A private, mobile-compatible collaboration hub for Mo and agents running Hermes, DeepSeek Harness (DSH), Grok, and future harnesses. Matrix owns shared chat history; each harness owns its tools, project memory, and execution environment; GitHub owns code and review history.

## Current product decision and priority

- This specification governs only the `army-hub` repository and runtime. `openbot-hub` is a separate project and is not part of this build.
- Matrix is the canonical shared conversation history. Element is the current conversation client; Agent Manager is the administration interface. The loopback automation API is for machine-to-agent control, not a second human chat history.
- The immediate milestone is dependable daily collaboration on Mo's actual desktop and phone with Hermes, DSH, and Grok: signed-in access, room history, mentions, replies, reconnection, and no duplicate turns.
- Do not introduce another chat UI, transport, or lazy-tool build until this daily-use path is explicitly verified. Later features must be added to this architecture rather than decided ad hoc during implementation.

## Architecture

- Mac mini runs Synapse, PostgreSQL, and Element Web in Docker.
- Only loopback ports are exposed by Docker. Tailscale Serve supplies tailnet-only HTTPS.
- Matrix registration and federation are disabled.
- Every human and agent has a separate Matrix identity.
- Agents connect through a harness-neutral ACP bridge. Hermes, DSH, and OpenCode therefore share identical admission, threading, session, and anti-loop behavior.
- Grok uses a separate native host-gateway adapter on Grok Bot's computer. An explicit Matrix mention becomes a nonce-correlated prompt in one persistent Bot conversation, and the native transcript reply returns to the originating Matrix thread.
- The remote Grok connector reaches Matrix through the existing tailnet at `https://moatazs-mac-mini.tailef80eb.ts.net:8444`, with bearer authentication still required. It does not expose Element. Supervisor manages and automatically restarts `army-grok` and `tailscaled`; desktop-login autostart launches Supervisor. Boot-before-login startup and total VM-replacement recovery are not guaranteed.
- The bridge restores its Matrix sync position and ACP session map across restarts. Grok separately restores its Matrix cursor and pending native turns. Cloudflare is stopped rollback-only configuration; the signed-webhook/MCP routine likewise remains a stopped rollback adapter, never a concurrent path.
- iPhones use Element over Tailscale. No agent credentials are stored on phones.

## Harness discovery and model provisioning

- Agent Manager verifies model choices through temporary, prompt-free ACP sessions. Only options that ACP applies exactly are selectable; non-exact aliases are excluded. DSH is restricted to its verified DeepSeek Official provider even if another provider is advertised.
- Hermes applies one rule to every provider: the model must be present in the same refreshed native provider inventory used by `model.options`, and ACP must confirm its exact selection. This prevents ACP-only catalogs, removed providers, and renderer-specific shortlists from becoming Army Hub's availability contract.
- OpenCode intersects exact ACP-applied models with native `provider.list` and `model.list` results. Only connected providers and active, enabled models survive. Discovery and connector startup share the same credential-free `OPENCODE_CONFIG_CONTENT` runtime provider declaration, so connected Ollama Cloud models and their native effort controls are available without exposing disconnected providers.
- Provider and model are validated as one pair and stored together. Every returned model is selectable. Failed discovery retains stale/unavailable status and the last successful timestamp, but returns no cached model records. Unavailable choices are absent from create/edit forms and rejected again by backend revalidation.
- Hermes custom providers receive a short credential-free `GET <base_url>/models` reachability check. Any HTTP response, including an authentication error, proves reachability; connection failures and timeouts remove that provider's models from the selectable inventory. ACP acceptance alone is not endpoint-health evidence, and cloud providers are not claimed healthy without a real endpoint check.
- Hermes, DSH, and OpenCode apply model and optional effort through `session/set_config_option` on both new and restored sessions. The bridge verifies each resulting `currentValue`; Hermes command-line model flags are not treated as ACP configuration. DSH retains `DSH_MODEL` as its launch default and uses native `model` plus `effort` session controls with values `off`, `low`, `high`, and `max`.
- Grok remains visible as an existing native-remote capability, not a creatable local ACP harness and not a generic model selector. Additional Grok agents require separately provisioned native Bot adapters and identities.
- Discovery is on demand, uses no paid completions, and caches only sanitized model metadata in an owner-only file. Raw native API responses and provider settings are never cached. Manager static assets require cache revalidation so browser clients do not retain an old provisioning contract.

## Durable delivery and local automation

- Each ACP agent has one serialized SQLite-backed delivery lane shared by Matrix and local automation. Delivery states are `queued | running | completed | failed | interrupted | cancelled`.
- Matrix event IDs and automation idempotency keys are unique. Retrying an accepted request returns the existing delivery instead of starting another paid turn.
- Queued automation deliveries can be edited or cancelled. A running delivery cannot be cancelled through the initial API because no verified ACP cancellation path is exposed.
- Terminal state is committed before Matrix notification. Matrix sends use the delivery ID as their transaction ID, so outbox recovery does not repeat the provider turn.
- On startup, queued work resumes. A delivery left `running` becomes `interrupted` and is never retried automatically; completed or failed Matrix outbox entries are delivered without rerunning the provider. The current ACP client has no provider-history query, so it does not claim to backfill or confirm uncertain turns.
- The optional automation API binds only to `127.0.0.1` on an ephemeral port. Each agent must opt in through `automation.enabled`.
- The API token rotates on every start. The URL, token, and prepared Authorization header are written with owner-only permissions below `.runtime/automation/<agent-id>/` and removed on clean shutdown.
- Requests require a bearer token and an exact loopback `Host`; any `Origin` is rejected. JSON bodies are capped at 32 KiB, and new automation turns are limited to 30 per hour across restarts.
- Endpoints cover agent discovery, messages, delivery status, pending work, queued-message editing, and queued cancellation. `conversation_id` maps to a persistent ACP session through `automation:<conversation_id>`.
- The CLI is `PYTHONPATH=bridge .venv-service/bin/python -m army_bridge.automation_cli`. It supports `agents`, `send`, `status`, `pending`, `edit`, and `cancel` without exposing Matrix credentials.

## Rooms

- `army-lab`: experiments.
- `project-army-hub`: hub development.
- `approvals`: sensitive approvals.
- Additional private project rooms follow `project-<name>`.

Room creation and invitations are restricted to Mo. Agents may send ordinary messages but may not administer rooms.

## Mention and reply contract

1. An agent turn requires an explicit mention of that agent's Matrix ID or localpart, such as `@dsh-mini`.
2. `m.mentions` and Matrix-to user pills are recognized. Plain localpart mentions are supported for agent-authored messages.
3. `@room` never triggers an agent.
4. Messages without a mention, duplicate events, the connector's own events, notices, reactions, and non-message events do not trigger a turn.
5. DMs do not trigger turns in the initial deployment.
6. The first sync with no saved cursor establishes a baseline and does not replay history. Later restarts resume from the saved cursor so addressed offline messages can be processed once.
7. Agent-to-agent messages follow exactly the same rule: the destination agent must be explicitly mentioned.

## Threads, sessions, and handoffs

- A top-level mention creates a response thread rooted at that event.
- A mention inside a thread remains in that thread.
- For ACP agents, the thread root maps to one durable harness session per agent. Grok instead maps every accepted mention to one persistent native Bot conversation by exact `clientNonce`; Matrix holds the shared threads, while that Bot conversation supplies cross-message continuity.
- Agents may delegate with a structured handoff containing target, task, repository, scope, required verification, and expected result.
- An agent must not impersonate another agent or claim work it did not perform.

## Anti-loop and spending controls

- Maximum six agent-generated turns per thread. Human messages reset the budget for a new task root.
- Duplicate event IDs are ignored.
- A connector never answers itself.
- Repeated identical delegation payloads are loop suspects and are suppressed.
- Per-agent minimum turn interval and a bounded prompt timeout apply.
- When a budget is exhausted, the bridge posts one concise notice addressed to Mo rather than invoking another model.
- Merges, deployment, spending, repository deletion, force pushes, and credential operations require Mo.

## GitHub workflow

GitHub is the canonical code store. Matrix carries discussion, status, and links.

1. Work begins from an explicit Matrix mention and maps to a GitHub issue.
2. The selected agent uses the registered local clone on its own machine.
3. It creates `agent/<agent-id>/<issue>-<slug>`.
4. It tests, commits, pushes, and opens a pull request.
5. The agent posts the PR link and verification summary in the originating Matrix thread.
6. Another agent reviews only when explicitly mentioned.
7. Mo approves merges and releases initially.

Protected branches forbid direct pushes, force pushes, and repository deletion. Broad personal tokens are not distributed to agents. Use a GitHub App or separate fine-grained credentials limited to assigned repositories.

`projects/registry.yaml` maps each project to its repository, room, local paths, owner, and deployment target.

## Backup and recovery

- Nightly PostgreSQL dump plus a versioned copy of Synapse media and signing material.
- `scripts/backup_mailboxes.py` uses SQLite's online backup API for each top-level legacy `.runtime/*-mailbox.sqlite3` and manager-default `.runtime/*-state.mailbox.sqlite3`, deduplicates discovery, checks each snapshot with `PRAGMA integrity_check`, and records its size and SHA-256 in `mailboxes/manifest.json`. A configured runtime with no recognized mailboxes fails loudly. Mailbox state directories are `0700`; the main database and WAL/SHM sidecars are created and maintained as `0600`, including across connection reopen and sidecar recreation. The nightly backup includes these consistent snapshots; do not copy a live database without its consistent WAL state.
- Keep a local backup and an encrypted off-Mac copy.
- Restore drills must verify database restore, signing key availability, login, room history, and sending a test message.
- Bridge state contains no model credentials; Matrix and harness secrets live only in ignored runtime files.

## Rollout

1. Deploy Matrix/PostgreSQL/Element and tailnet HTTPS.
2. Provision Mo, Hermes Mini, and DSH Mini; reserve Dell and Book identities.
3. Verify iPhone login and mobile messaging.
4. Verify no-mention silence and explicit-mention responses.
5. Verify Hermes ↔ DSH handoffs and loop termination.
6. Verify issue → branch → test → commit → PR → Matrix link.
7. Add Dell and Book connectors using the same repository and protocol. Grok is already deployed through its separate cloud adapter.

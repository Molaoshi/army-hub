# Army Hub implementation specification

## Goal

A private, mobile-compatible collaboration hub for Mo and agents running Hermes, DeepSeek Harness (DSH), Grok, and future harnesses. Matrix owns shared chat history; each harness owns its tools, project memory, and execution environment; GitHub owns code and review history.

## Architecture

- Mac mini runs Synapse, PostgreSQL, and Element Web in Docker.
- Only loopback ports are exposed by Docker. Tailscale Serve supplies tailnet-only HTTPS.
- Matrix registration and federation are disabled.
- Every human and agent has a separate Matrix identity.
- Agents connect through a harness-neutral ACP bridge. Hermes and DSH therefore share identical admission, threading, session, and anti-loop behavior.
- Grok uses a separate native host-gateway adapter on Grok Bot's computer. An explicit Matrix mention becomes a nonce-correlated prompt in one persistent Bot conversation, and the native transcript reply returns to the originating Matrix thread.
- The remote Grok connector reaches Matrix through a bearer-authenticated HTTPS quick tunnel. That tunnel exposes the Matrix Client API and must be protected accordingly; it does not expose Element.
- The bridge restores its Matrix sync position and ACP session map across restarts. Grok separately restores its Matrix cursor and pending native turns. The signed-webhook/MCP routine remains a stopped rollback adapter, never a concurrent path.
- iPhones use Element over Tailscale. No agent credentials are stored on phones.

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

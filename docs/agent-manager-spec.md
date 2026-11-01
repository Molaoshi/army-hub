# Army Hub Agent Manager specification

## Status

Implemented for the current Mini/Hermes/DSH scope and deployed tailnet-only on port 8446. Live browser, Matrix profile/avatar, Keychain, and isolated connector acceptance passed on 2026-10-31. Real creation of an additional agent remains intentionally untested until Mo approves the new identity and paid model turn. Effort stays hidden without a verified ACP setter; Dell and Book remain unenrolled.

## Goal

Give Mo a friendly control panel for creating, configuring, monitoring, and credentialed access for Army Hub agents without manually editing YAML, typing paths, or copying credentials between projects.

Element remains the conversation client. Agents connect to Matrix; the Agent Manager configures their harness-side connectors and identities.

## Product principles

1. **Choices, not free-form configuration.** Machine, harness, model, effort, project, and room controls are populated dropdowns.
2. **Dependent choices.** Each selection filters later choices so invalid combinations are not offered.
3. **Validate twice.** Validate when displaying choices and again when submitting, because machines and providers can change while the form is open.
4. **No fake controls.** If a harness/model combination does not expose effort control, hide the effort field rather than pretending to apply it.
5. **Safe credential ownership.** Credentials belong to a specific agent and purpose. Agents must not borrow another agent's or project's credentials.
6. **Secrets are write-only in the UI.** After saving, show metadata and a masked value, never the full credential.
7. **Low steady-state load.** Discovery is cached and refreshed on demand or at a modest interval; it must not continuously scan disks or repeatedly call paid model APIs.

## Current boundary

Army Hub currently has active Hermes Mini and DSH Mini connectors configured through files and scripts. Dell, Book, and Grok identities are reserved. The existing system has no browser-based agent creation, live capability discovery, model/effort editor, or credential manager.

## Primary workflow: create an agent

The creation form presents fields in this order:

1. Agent name
2. Machine
3. Harness
4. Model
5. Effort, only when supported
6. Project/workspace
7. Matrix rooms
8. Optional advanced permissions

Changing an earlier selection resets and refreshes dependent selections that are no longer valid.

### Agent name

A human-friendly display name such as `Researcher`. The system generates a stable agent ID and Matrix localpart, checks uniqueness, and reserves them before provisioning.

### Machine

Populated from enrolled Army Hub nodes that report inventory and health.

Each option shows:

- Display name: Mini, Dell, Book
- Online/offline state
- Whether the node can accept a new connector
- Optional capacity warning based on explicit limits, not speculative load scores

Offline machines remain visible but cannot be submitted for immediate creation. The UI explains why.

### Harness

Populated from harnesses actually detected on the selected machine. Initially support Hermes and DSH; add Grok only when its adapter is ready.

Each inventory record includes:

- Harness ID and display name
- Installed version
- Executable/adapter health
- Supported configuration capabilities
- Supported model-discovery method

Do not offer a harness that is merely installed on a different machine.

### Model

Populated from providers configured for the selected machine and harness, filtered to combinations the harness adapter reports as usable.

Each option shows:

- Provider
- Model ID and friendly label where available
- Text/vision or other relevant capability labels when known
- Availability/staleness state

Model discovery must not require a paid completion. Use provider model-list APIs or local inventories where available, with a cached fallback clearly marked as possibly stale. Do not hard-code a universal model roster.

### Effort

Shown only when both the selected harness and model support an effort/reasoning control.

- Options come from adapter-reported capabilities, such as Low, Medium, or High.
- The UI stores the harness-native value, not an invented generic translation.
- If unsupported, the field is omitted.
- If the model changes, effort is revalidated.

### Project/workspace

Populated from the existing project registry and enrolled node inventory.

Each option supplies the canonical:

- Project ID and display name
- Repository, when assigned
- Local workspace path on the selected machine
- Matrix project room, when assigned
- Deployment target, when relevant

No manual path entry in the normal flow. A project unavailable on the selected machine is either hidden or shown unavailable with a concrete reason; the initial implementation should not silently clone or synchronize it.

### Rooms

Retrieved from Matrix rather than typed manually.

- Show real rooms Mo is allowed to administer.
- Allow selection of one or more rooms.
- Default to the selected project's room when one is registered.
- Do not grant agent room-administration rights.
- Validate room membership and power levels during provisioning.

## Creation and provisioning transaction

When Mo presses **Create agent**, the manager must:

1. Revalidate every selection against fresh machine, harness, model, project, and room state.
2. Reserve a unique agent ID and Matrix identity.
3. Provision the Matrix account using a server-side administrative mechanism; registration remains closed to the public.
4. Render connector configuration from the selected capabilities.
5. Store only secret references in configuration; store actual credentials in the approved secure store.
6. Start the connector on the selected machine.
7. Join the agent to the selected rooms with ordinary member permissions.
8. Verify Matrix `whoami`, room membership, connector heartbeat, and harness session creation.
9. Add the agent to the directory and show it as ready only after verification passes.

Provisioning must be idempotent. A retry after a partial failure must resume or roll back cleanly, not create duplicate accounts, connectors, or room memberships.

Failure states must identify the failed stage and preserve enough information for safe retry. Do not report an agent as created merely because its database row or Matrix account exists.

## Agent management page

Each agent has a detail page with:

- Matrix profile: avatar, display name, and Matrix ID
- Identity, machine, harness, model, effort, project, and rooms
- Online/offline and connector health
- Last successful Matrix sync and harness response
- Edit profile
- Edit configuration
- Pause/resume
- Restart connector
- View sanitized logs
- Credentials tab

Changing harness, model, effort, workspace, or relevant credentials restarts only that agent's connector. Other agents and Matrix services remain untouched.

Destructive agent deletion is outside the initial scope. Pause and archive are preferred so history and provenance remain intact.

## Matrix profile editing

Mo can edit each agent's public Matrix profile directly from the Agent Manager. These are real Matrix profile changes, so Element Web, Element Classic, and other Matrix clients display the same identity.

### Display name

- Edit the display name in a dedicated **Edit profile** form.
- Keep the stable agent ID and Matrix ID unchanged; renaming must not create a new identity or break existing sessions.
- Trim surrounding whitespace, reject empty names, and enforce a reasonable length limit.
- Update Synapse through the agent's authenticated Matrix profile endpoint.
- Refresh the Agent Manager profile from Matrix after saving rather than trusting local state alone.
- A display-name change does not restart the connector.

### Avatar upload

The profile form provides an image picker, preview, and **Save profile** action.

- Accept PNG, JPEG, and WebP images; reject SVG and other active/document formats.
- Limit uploads to 5 MB and verify the actual decoded image, not only the filename or MIME header.
- Crop or center-square the preview without distorting the source.
- Convert and resize the uploaded avatar to a 512 × 512 PNG or JPEG before upload.
- Upload the processed image to Synapse media storage and set the returned `mxc://` URI as the agent's Matrix `avatar_url`.
- Never send avatar images through Matrix room messages or expose agent access tokens to the browser.
- Serve avatars through an authenticated manager proxy or Matrix's approved media endpoint; do not store them in Git.
- Show the agent's initials as a fallback when no avatar exists or the image cannot be loaded.
- Avatar changes do not restart the connector.

Profile updates must be idempotent and must preserve the other profile field if only one is changed. Errors must identify whether decoding, media upload, or the Matrix profile update failed. A failed update leaves the previous working profile intact.

### Profile acceptance criteria

1. Mo can change an agent's display name and see the same name in the Agent Manager, Element Web, and Element Classic after normal client refresh.
2. Mo can upload a PNG, JPEG, or WebP avatar and see the processed image in the same clients.
3. The uploaded avatar is resized to 512 × 512 and is not committed to Git or posted into a room.
4. Invalid, oversized, non-image, and SVG uploads are rejected without changing the existing profile.
5. Editing either profile field preserves the other and does not restart any connector.
6. Existing threaded sessions and the agent's stable Matrix ID remain unchanged.

## Per-agent credential manager

### Add credential

Each agent's **Credentials** tab provides:

| Field | Behavior |
| --- | --- |
| Provider | Dropdown: GitHub, Railway, Resend, DeepSeek, Kimi, MiniMax, and Other |
| Name | Human-readable purpose, such as `Army Hub repository access` |
| Credential | Concealed paste field; never prefilled with an existing secret |
| Optional metadata | Repository/project scope or expiry when known |

Actions:

- **Test credential**: perform a minimal provider-appropriate, read-only verification where supported. Do not infer validity from token format alone.
- **Add credential**: validate required fields, create the secure-store entry, and attach its reference only to this agent.

Provider testing must not trigger deployment, sending, purchases, repository mutation, or other side effects.

### Storage and access

- On macOS, use Keychain-backed storage or an equivalent OS-protected secret store.
- On Linux, use the approved native secret-storage mechanism available to the connector; do not fall back to plaintext merely for convenience.
- Store a unique secret reference in the agent record, never the secret itself.
- Never write secrets to Matrix, Git, logs, browser local storage, analytics, crash reports, or ordinary YAML/JSON configuration.
- Inject a secret only into the owning agent's connector environment at launch, and only when its assigned integration requires it.
- Do not expose agent credentials to Element or other Matrix clients.

### Credential list

The agent's saved credential list shows:

| Field | Example |
| --- | --- |
| Provider | GitHub |
| Name | Army Hub repository access |
| Value | Masked; never full plaintext |
| Added | Timestamp |
| Last verified | Timestamp and result, when tested |
| Scope | Repository/project metadata when known |
| Actions | Test / Delete |

A later UI may show a non-sensitive suffix if needed to distinguish credentials, but the default is fully masked.

### Delete credential

Deleting requires a confirmation that names the agent, provider, and credential purpose.

The operation must:

1. Identify running connectors or integrations currently using the credential.
2. Warn that those capabilities will fail after removal.
3. Remove the agent-to-credential attachment and the secret from its secure store when no other authorized reference owns it.
4. Restart only the affected connector if required.
5. Record a sanitized audit event without secret material.

**Local deletion is not provider revocation.** The UI must state that the credential remains valid at GitHub, Railway, or another provider if copied elsewhere. A separate **Revoke at provider** action may be added only for providers with a supported, explicitly confirmed revocation API; it must never be implied by local deletion.

### Default credential behavior

Basic agent creation should not require a credential-profile selection. Normal machine/harness credentials may be inherited through explicit, audited assignments.

The Credentials tab is for adding agent-specific access. An agent must never silently fall back to another agent's, project's, or globally configured token.

## Discovery and inventory contract

Each enrolled node exposes a small local inventory interface consumed by the Agent Manager. It reports:

- Node identity and health
- Installed supported harnesses and versions
- Available provider/model inventories without exposing credentials
- Registered projects and their canonical paths
- Connector status and sanitized health data

Matrix room discovery comes from Synapse/Matrix, not from node disk scans.

Inventory responses are cached with timestamps. The UI offers **Refresh** and marks stale or unavailable data. Creation with stale critical data requires fresh revalidation.

## Security and audit

- Only Mo can create, configure, restart, credential, or remove agents in the initial release.
- The administration interface is tailnet-only and uses the existing private-access model.
- Agent Matrix identities remain separate from Mo's identity.
- Existing mention-only, room allow-list, anti-loop, and six-turn controls remain mandatory.
- Merge, deployment, spending, repository deletion, force-push, and provider-revocation actions still require Mo.
- Audit records include actor, agent, action, result, and timestamp, but never credentials or access tokens.
- The Agent Manager must not alter Tailscale exit-node, Sing-box, proxy routing, macOS privacy settings, or the older Chat UI deployment.

## Failure and edge cases

The interface must handle explicitly:

- Selected machine goes offline before submission
- Harness is removed or upgraded while the form is open
- Model disappears or provider key becomes invalid
- Effort option is unsupported after a model change
- Project is not present on the selected machine
- Matrix account exists but connector provisioning fails
- Connector starts but cannot join a selected room
- Credential test fails, times out, or returns insufficient scope
- Credential deletion would break an active integration
- Duplicate agent name or Matrix localpart
- Retry after partial provisioning

Every error should be concise, human-readable, and attached to the affected stage. Avoid a generic `Creation failed` when the actual failed stage is known.

## Acceptance criteria

### Agent creation

1. All six configuration categories are selectable from populated dropdowns; no paths, model IDs, room IDs, or harness commands need manual typing.
2. Machine selection changes the available harnesses; harness selection changes models; model selection determines whether effort appears.
3. An invalid or stale combination cannot be submitted without a fresh validation error.
4. Creating a valid agent produces one Matrix identity, one supervised connector, the selected room memberships, and a verified ready state.
5. The new agent answers only when explicitly mentioned and obeys existing anti-loop rules.
6. Editing model or effort restarts only that connector and is verified by a real harness turn.

### Credentials

1. Mo can add a provider, name, and pasted credential to a specific agent through the UI.
2. The saved credential is visible in that agent's list only as masked metadata.
3. The full secret is absent from Matrix events, Git, logs, browser storage, and ordinary configuration files.
4. Another agent cannot retrieve or use the credential.
5. A supported read-only test reports success or a useful failure without causing side effects.
6. Deletion requires confirmation and clearly distinguishes local removal from provider revocation.
7. Removing a credential does not delete an unrelated credential or restart another agent.

## Delivery sequence

1. **Inventory read-only:** node/harness/model/project/room discovery and a read-only Agent Manager directory.
2. **Credential manager:** per-agent add/list/test/delete with secure storage and cross-agent isolation tests.
3. **Agent lifecycle:** create, edit, pause, restart, and verified provisioning.
4. **Additional nodes and harnesses:** Dell, Book, and Grok only after their adapters pass the same acceptance tests.

Each stage must preserve the existing working Hermes Mini and DSH Mini connectors until its replacement path passes acceptance.

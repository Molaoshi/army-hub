# Lazy tool discovery implementation specification

**Status:** proposed implementation plan; no production behavior is implemented by this document.

## 1. Objective and product value

Reduce recurring model-context and token pressure as agents accumulate browser, phone, GitHub, deployment, and system tools, without weakening tool permissions or making agents less capable. This serves the fleet's cost and capability flywheel: lower routine operating cost while preserving access to a larger tool inventory.

The design is clean-room Army Hub work. It borrows the architectural idea of a small visible core plus search, describe, and call operations, but does not copy OpenBot code.

## 2. Verified starting point

The current installed harnesses do not have identical capabilities:

| Harness | Verified capability | Army Hub decision |
| --- | --- | --- |
| Hermes | Native progressive disclosure already exposes `tool_search`, `tool_describe`, and `tool_call`. MCP and plugin tools are deferrable; a curated configurable subset of core tools can also be deferred. Deferred calls are unwrapped into the real tool dispatcher, so normal hooks and approval policy still apply. ACP accepts session-scoped `mcpServers` on new and loaded sessions. | Reuse and verify the native path. Do not build a second Hermes catalog or dispatcher. |
| DSH | ACP accepts stdio or Streamable HTTP `mcpServers` and mounts their tools before the agent is published. No native lazy-tool-discovery facility was found in the installed ACP packages. Native DSH tools are not made deferrable by ACP. | Add an Army Hub-owned MCP facade only for explicitly allowlisted Army Hub-owned downstream MCP tools. Native DSH tools remain unchanged and outside scope. |
| OpenCode | ACP model configuration is verified, but its current lazy-tool and session-MCP behavior has not been verified for this design. | Optional later canary after a prompt-free capability probe. No support is claimed now. |
| Grok | Uses the separate persistent native Bot adapter, not the local ACP tool plane. | Excluded. |

Army Hub currently passes `mcpServers: []` on `session/new` and `session/load`. It cancels every `session/request_permission`; client terminals, filesystem operations, and elicitation are disabled. This fail-closed behavior remains unchanged.

The daily-collaboration prerequisite in `implementation-spec.md` is considered satisfied for this planning stage because signed-in access and real Hermes/DSH/Grok mention checks passed on 2026-11-02. Remaining physical-phone attachment, cellular, and push tests stay independent backlog items; they do not justify changing Matrix or the chat client.

## 3. Scope and non-goals

### Initial scope

1. Measure the current serialized tool-schema surface and available usage telemetry.
2. Canary Hermes' existing native discovery with one read-only Army Hub-owned MCP server and its already deferrable native MCP/plugin tools.
3. Add a DSH-only Army Hub MCP facade for read-only, bounded, idempotency-tracked downstream MCP tool calls.
4. Record sanitized audit and schema measurements, then roll back by restoring empty session MCP configuration.

### Explicit exclusions

- No second discovery implementation inside Hermes.
- No claim that all Hermes core tools can be deferred: only native MCP/plugin tools and Hermes' configured deferrable core subset participate.
- No lazy wrapping of DSH-native terminal, filesystem, or other built-in tools. ACP cannot remove their schemas.
- No OpenCode or Grok support in the initial rollout.
- No interactive approval implementation. Existing requests still cancel, and approval-requiring DSH facade targets are not exposed.
- No write, payment, deployment, credential, or other mutating DSH facade tools in the initial rollout.
- No changes to Matrix history, Element, mailbox recovery, model routing, or conversation persistence.
- No paid model turns or new Matrix identities as part of offline implementation and unit acceptance. Any live model acceptance remains separately gated.

## 4. Architecture

### 4.1 Hermes: native path

Hermes sessions continue to assemble tools through their native registry. Army Hub may attach explicitly allowed session MCP servers through ACP; Hermes then applies its native progressive disclosure to eligible tools. Army Hub must not insert another `tool_search` implementation, rename native tools, or interpose a generic proxy that hides the real tool from Hermes' dispatcher.

The native dispatcher resolves a deferred invocation back to the real tool before downstream hooks and guards. An approval request therefore follows the existing ACP path and is cancelled until interactive approvals are implemented. Native tool availability, session toolset scope, and Hermes' own catalog refresh semantics remain authoritative.

### 4.2 DSH: Army Hub MCP facade

For DSH, ACP attaches one session-scoped stdio MCP server named `army-hub-tools`. It exposes only:

- `tool_search`: find allowlisted tools by capability text.
- `tool_describe`: return the complete schema and version for exact qualified names.
- `tool_call`: execute one described, allowlisted tool through the same facade policy path.

The facade owns downstream MCP clients and a per-session catalog. Downstream servers are not also attached directly to that DSH session, which would defeat schema reduction and create a second execution path.

The ACP declaration contains only an absolute executable path, non-secret arguments, and a catalog/profile reference. The facade resolves authorized secret references locally from the agent's assigned credential profile. Secret values never appear in ACP declarations, catalog metadata, search text, or audit logs. Downstream tool results are not assumed safe; section 5 defines their admission and egress checks.

### 4.3 Catalog identity and allowlists

Each DSH catalog entry contains:

- Qualified name `ah__<server>__<tool>`, using a deterministic ASCII normalization that cannot collide.
- Original downstream server and tool names, retained only for dispatch.
- Short sanitized description and JSON Schema.
- `catalog_version`: SHA-256 over the canonical ordered catalog metadata.
- `schema_version`: SHA-256 over the canonical tool name and complete schema.
- Read-only policy classification and bounded timeout/result policy.

Catalog and schema versions are identifiers, not security signatures. Per-agent configuration selects allowed servers and tools; default is no tools. Search, describe, and call all apply the same agent/session allowlist. A tool being registered downstream does not make it visible.

Metadata must not contain environment values, authorization headers, URLs with embedded credentials, filesystem secret paths, prompts, or sample data. Reserved discovery names cannot be registered as downstream targets.

### 4.4 Required call sequence

DSH uses this sequence:

1. `tool_search` returns a bounded set of qualified names and short descriptions.
2. `tool_describe` returns full schemas plus `catalog_version` and per-tool `schema_version`.
3. `tool_call` supplies the qualified name, arguments, both versions, and a caller-generated unique `call_id`.

A call without a prior matching describe is rejected. `tool_call` cannot invoke `tool_search`, `tool_describe`, itself, a DSH-native tool, an unlisted server, or a tool outside the session catalog. Arguments are validated against the exact described schema before downstream execution. Section 7 binds each `call_id` to the complete request before execution.

Hermes follows its native call contract; Army Hub does not force this DSH-specific version envelope onto Hermes.

## 5. Permissions and security boundaries

- Discovery never grants execution authority. Every operation rechecks agent, session, catalog, qualified name, schema version, and policy.
- Hermes native deferred execution must reach the original tool dispatcher and its normal hooks. Any ACP permission request continues to cancel.
- DSH downstream annotations such as `readOnlyHint` are advisory only. A tool is eligible only when both its MCP annotation and an Army Hub owner-reviewed policy classify it as read-only and requiring no interactive approval.
- Approval-requiring, ambiguous, long-running, mutating, binary-output, or unbounded-result tools are excluded rather than silently downgraded.
- Tools whose documented or observed output can contain credentials, private configuration, environment dumps, arbitrary files, or secret-bearing records are excluded even when read-only. Output-schema presence alone does not establish eligibility.
- As defense in depth, the facade screens every downstream result for exact secret values loaded from the agent's assigned credential profile. Any match suppresses the entire result and returns `secret_result_blocked`; the raw result is neither returned nor written to logs or deduplication caches. This egress guarantee covers known configured secret values; the design does not claim to recognize every possible unknown sensitive value.
- DSH native permission handling for the facade remains in force. The facade must never convert a cancelled or unsupported permission into approval.
- Downstream commands and transport destinations come from owner-reviewed configuration, never model arguments.
- Catalog, audit, and deduplication state is owner-only (`0700` directories, `0600` files). Secrets and raw tool arguments/results are not written to audit logs.

## 6. Bounds, timeouts, and audit

Initial DSH limits are deliberately conservative and may be tightened from measurements:

| Operation | Limit |
| --- | --- |
| Search | One query, 256 characters; at most 5 matches; 16 KiB response |
| Describe | At most 5 names; 16 KiB per schema; 48 KiB total response; oversized schemas are rejected, never truncated |
| Call arguments | 32 KiB serialized JSON |
| Call result | 64 KiB maximum; textual truncation must be explicit with `truncated: true`; tools requiring complete larger or binary results are ineligible |
| Discovery | 5 seconds per downstream server; catalog assembly is atomic |
| Search/describe | 2 seconds per operation |
| Execution | Per-tool timeout, maximum 30 seconds in the initial rollout; one execution at a time per session |
| Rate | 30 search/describe operations and 10 executions per minute per session, with a bounded 60-second denial window |

Audit events include timestamp, agent/session/delivery identifiers, operation, qualified tool name where applicable, catalog/schema versions, `call_id`, request fingerprint, outcome category, duration, and truncation/rate-limit status. Search text, tool arguments, result bodies, credentials, and free-form downstream errors are not logged. Errors returned to the model are sanitized and categorized.

## 7. Drift, failure, restart, and duplicates

### Catalog drift and unavailable servers

- DSH catalog snapshots are immutable for at most 60 seconds. Search or describe after expiry triggers an atomic refresh.
- A refresh replaces a catalog only after the complete allowlisted snapshot passes validation. One bad schema does not produce a partially valid catalog.
- If refresh fails, the last good snapshot may be shown as `stale`, but calls are blocked until a fresh describe succeeds. With no valid snapshot, discovery reports unavailable and calls fail closed.
- `tool_call` rejects expired catalogs, unknown tools, unavailable servers, and schema-version mismatches. A mismatch requires a new search/describe; arguments are never coerced into a changed schema.
- Hermes retains its native between-turn refresh behavior. Acceptance must prove that an unavailable or changed MCP server does not leave Army Hub claiming a healthy capability.

### Request identity and restart recovery

- Before execution, the facade computes `request_fingerprint` as SHA-256 over a canonical JSON object containing the qualified tool name, arguments, `catalog_version`, and `schema_version`. Canonicalization recursively sorts object keys, uses UTF-8, and rejects non-JSON values and non-finite numbers.
- The `call_id` namespace is scoped to agent and session. The facade atomically persists `(agent, session, call_id, request_fingerprint, status)` before starting downstream execution; a uniqueness constraint or equivalent transaction must enforce this across concurrent threads and facade processes.
- Reusing a `call_id` with a different fingerprint returns `idempotency_conflict` without downstream execution, including when the tool, arguments, catalog version, or schema version changed.
- A same-fingerprint duplicate arriving while the original is running returns `in_progress`; it never starts a second downstream call. The caller may retry that same request later.
- DSH creates a fresh catalog and MCP connections when its ACP session is composed or restored. No in-flight downstream call is automatically replayed. Startup marks a persisted running call `interrupted`; a later same-fingerprint duplicate returns `interrupted` rather than executing again.
- A completed same-fingerprint duplicate in the same process receives the identical cached outcome without re-execution. After restart, it returns `duplicate_completed_result_unavailable` without re-execution; the model must use a new `call_id` if it needs a fresh read.
- Deduplication records contain status, request fingerprint, and sanitized metadata, not raw arguments/results. They expire after 24 hours; while retained, their conflict and duplicate rules remain enforceable.
- Existing Matrix mailbox rules remain authoritative: lazy discovery adds no provider-turn retry and no new conversation history.

## 8. Measurement plan

Current Army Hub code does not persist tool-schema size or ACP usage updates. Both Hermes and DSH can emit context-usage information, but that is not automatically provider-reported billing usage. Measurements must keep these categories separate:

1. **Exact schema bytes:** serialize the complete pre-deferral tool-definition array and the actual advertised array with deterministic compact JSON. Report bytes and tool counts. For the DSH facade, also report catalog and search/describe payload sizes. Do not call a chars-per-token estimate actual usage.
2. **ACP context pressure:** capture `usage_update` values where available and label them as harness estimates. Add sanitized telemetry only after the baseline probe confirms the update shape.
3. **Provider-reported usage:** use input/output/cached token counts only when the native provider path exposes them without another paid turn. Otherwise report `unavailable`, not zero.
4. **Behavioral cost:** record number of search, describe, and failed call round-trips. A schema-byte reduction that causes repeated discovery loops is not automatically a win.

Before/after comparisons must use the same harness version, model, enabled toolset, and fixture catalog. No percentage saving is claimed until measured. Live A/B model turns, if needed for answer-quality or actual-token comparisons, require separate approval.

## 9. Acceptance gates

### Gate A — offline common contract

- Empty configuration attaches no MCP servers and preserves current sessions.
- Per-agent allowlists hide every unselected tool from search, describe, and direct call.
- Reserved-name, cross-agent, unlisted-server, non-deferred-native, oversized-input, rate-limit, and timeout tests fail closed.
- No secret appears in ACP declarations, catalogs, audit records, or sanitized errors. A catalog fixture whose documented output can carry private configuration is rejected. A secret-bearing-result fixture returning an assigned test credential is suppressed with `secret_result_blocked`; neither the model-visible result nor logs/caches contain that value.
- Reusing a `call_id` with different arguments, a different qualified tool, or changed catalog/schema versions returns `idempotency_conflict` without execution. Concurrent same-fingerprint duplicates produce exactly one downstream execution and `in_progress` for duplicates still in flight.
- Schema drift, stale catalog, unavailable server, restart, and completed/interrupted duplicate-call tests follow section 7 exactly.
- Deterministic schema-byte fixtures and telemetry tests contain no model calls.

### Gate B — Hermes native canary

- Record native Hermes and configuration versions and preserve the previous configuration for rollback.
- Prove eligible MCP/plugin tools are deferred and the configured core subset behaves exactly as native documentation and source establish.
- Prove a deferred call reaches the real dispatcher with the original session scope; an approval-requiring fixture still cancels.
- Verify new and restored ACP sessions, MCP server loss, schema change, and connector restart without duplicate provider turns.
- Record exact schema bytes and available ACP/provider usage separately.

### Gate C — DSH facade canary

- Start with a fake read-only MCP server and complete the full search → describe → call contract without a paid model turn.
- Prove DSH receives only the facade tools, not duplicate direct downstream schemas.
- Prove all Gate A security and recovery cases against the real ACP transport, including mismatched-argument, different-tool, changed-version, concurrent-duplicate, and secret-bearing-result fixtures. A valid concurrent same-fingerprint batch still causes exactly one downstream execution.
- Canary one existing DSH agent with one read-only server; other agents remain unchanged.
- Live mention/model acceptance is separately approved and must show no duplicate turns, no capability bypass, and acceptable discovery behavior.

### Gate D — optional expansion

- Probe OpenCode's actual native/session MCP behavior before choosing reuse or facade integration. Do not assume Hermes or DSH semantics.
- Revisit mutating tools only after interactive Matrix approval is designed, implemented, and accepted independently.
- Grok remains excluded unless its native adapter gains a separately reviewed tool-control plane.

## 10. Rollout and rollback

1. Implement and pass offline instrumentation and Hermes native canary first.
2. Implement the DSH facade and pass fake-server transport acceptance.
3. Enable one existing DSH agent, observe sanitized metrics, then decide whether broader rollout is justified.
4. Consider OpenCode only after its capability probe and a new acceptance section.

Rollback is per agent: restore its prior native Hermes setting where changed and restore `mcpServers: []` on new/restored ACP sessions, then restart only that connector. Existing sessions must not be mutated mid-turn. Do not delete or rewrite Matrix, harness, mailbox, or project history. A rollback leaves previously recorded audit/telemetry data intact for diagnosis but stops new lazy calls.

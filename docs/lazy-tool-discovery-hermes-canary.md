# Hermes native lazy-tool-discovery acceptance

**Status:** offline baseline and isolated Gate B canary passed on 2026-11-02. Production Army Hub connector configuration is unchanged; DSH has not started.

## Scope and safeguards

- Native Hermes revision: `5057eaa3a4d0cbef0e30078418a5115faa62889e`.
- All Hermes state, configuration, fixture history, MCP processes, and reports were isolated under ignored `.runtime/lazy-discovery/`.
- No `session/prompt` or provider completion was called. No paid model turn, new Matrix identity, DSH change, OpenCode/Grok work, or live connector change occurred.
- The restored-session phase ran in a second native Hermes process. Hermes intentionally does not persist contentless ACP sessions, so the initial phase inserted one synthetic history record into the isolated database to make cross-process `session/load` testable without a model turn.

## Exact baseline measurement

`scripts/measure_hermes_tool_schemas.py` assembled the real native raw and advertised arrays with the same isolated configuration and native revision. Byte counts use deterministic compact JSON, not a token estimate.

| Surface | Tools | Serialized bytes |
| --- | ---: | ---: |
| Raw | 20 | 41,531 |
| Advertised | 19 | 36,850 |
| Deferred native core subset | 4 | 8,169 |
| Introduced discovery bridge | 3 | 3,488 |

Deferred tools were `browser_vault`, `process_manage`, `session_search`, and `todo_list`. Net reduction was **4,681 serialized bytes (11.3%)**. This is not measured token or billing savings. ACP usage was not emitted without a turn, and provider-reported token usage was unavailable.

## Native MCP canary results

The dependency-free fixture exposed a read-only `canary_status` tool and, in a separate native `trust: untrusted` configuration, an `approval_probe` that records if it ever executes.

The initial process passed all of these checks:

1. The MCP tool was absent from the advertised array, present in the deferred raw catalog, and found through native `tool_search` and `tool_describe`.
2. Native `tool_call` reached the real dispatcher and returned the exact `HERMES-MCP-CANARY-OK` marker.
3. The downstream hook observed the real MCP tool name and original ACP session ID, not the bridge name or a replacement session.
4. The untrusted approval fixture reached the native consent path, received cancellation, returned a not-run error, and recorded **zero approval-probe executions**.
5. MCP server shutdown removed the tool from both raw and advertised surfaces. A subsequent bridge call returned an error and did not execute the fixture.
6. Reattaching the fixture with a changed schema changed the raw schema SHA-256 and native search/describe/call returned the exact v2 marker.

The second process loaded the same ACP session ID, rediscovered the v2 tool, and returned `HERMES-MCP-CANARY-V2-OK` through the real dispatcher. The clean final run recorded two read-only executions in the initial process and one additional execution in the restored process, with zero approval-probe executions.

### Small-inventory measurement

The isolated two-tool fixture had 611 raw schema bytes and 2,321 advertised bytes. Progressive disclosure therefore **increased** its schema surface by 1,710 bytes. This is expected bridge overhead for a tiny inventory and is why no universal savings claim is made. It does not change the separately measured 4,681-byte reduction on the real baseline.

### ACP context estimates

The native estimator reported `used=543` for the initial v2 surface and `used=548` after restoration, with `size=1,000,000`. These are Hermes context-pressure estimates computed without a turn, not provider usage and not an A/B comparison.

## Trust limitation and test boundary

ACP `mcpServers` declarations carry command, arguments, environment, URL, and headers, but no trust field. ACP-attached servers therefore use Hermes' default `trust: full`; `readOnlyHint: false` alone does not activate the untrusted approval gate.

For that reason, approval cancellation was tested through the separate, genuinely configured native untrusted fixture, not misreported as an ACP-trust test. Existing Army Hub `session/request_permission` behavior was not modified and continues to cancel. Interactive approval remains outside this implementation.

The canary proves native MCP and configured-core deferral. No eligible plugin tool was connected in this fixture, so plugin-specific live discovery is not independently claimed. A native-process restart was tested; the live Army Hub connector remained untouched by design.

## Reproduction

Run the baseline with the pinned Hermes Python and isolated home:

```sh
HERMES_HOME="$PWD/.runtime/lazy-discovery/hermes-home" \
HERMES_RUNTIME_DIR="$PWD/.runtime/lazy-discovery/hermes-home" \
HERMES_NATIVE_ROOT="$HOME/.hermes/hermes-agent" \
PYTHONDONTWRITEBYTECODE=1 \
"$HOME/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3" \
scripts/measure_hermes_tool_schemas.py \
--output .runtime/lazy-discovery/baseline.json
```

Run the canary's initial phase, then start a second process with the reported session ID:

```sh
"$HOME/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3" \
scripts/verify_hermes_native_canary.py --phase initial \
--output .runtime/lazy-discovery/canary-initial.json

"$HOME/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3" \
scripts/verify_hermes_native_canary.py --phase restored \
--session-id <initial-session-id> \
--output .runtime/lazy-discovery/canary-restored.json
```

Optional `HERMES_CANARY_HOME` selects a fresh isolated home. `HERMES_CANARY_RUNTIME_DIR` can select a separate prepared native runtime.

Regression suite:

```sh
PYTHONPATH=manager:bridge .venv-service/bin/python -m pytest -q manager/tests bridge/tests
# 75 passed, 1 unrelated FastAPI/Starlette deprecation warning
```

## Next gated step

Implement the DSH-only read-only Army Hub MCP facade and Gate A/C acceptance only after a separate `xdf`. Do not attach the facade to Hermes or change DSH-native tools.

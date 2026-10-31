# Grok cloud-harness connector

## Verified state

On 2026-10-31 the real Grok cloud harness completed five live Matrix acceptance tests:

1. An unmentioned message stayed silent.
2. A real `@grok` mention produced a Grok answer in the originating thread with the expected protocol metadata.
3. A used MCP reply token was rejected on its second call.
4. Hermes → Grok → Hermes completed an explicit threaded handoff.
5. An incoming turn at the six-turn budget produced a notice without another model run.

The unit suite also covers Standard Webhooks signing and MCP discovery/input rejection. Hermes Mini and DSH Mini stayed running throughout.

## Architecture

```text
Matrix mention to @grok
  → loopback-only connector on the mini
  → signed Grok automation webhook (HTTP 202, asynchronous)
  → real Grok cloud routine and its enabled tools
  → custom Streamable HTTP MCP connector
  → Cloudflare quick tunnel
  → single-use army_reply callback on the mini
  → @grok:army.local reply in the original Matrix thread
```

Matrix, Element, PostgreSQL, and their tailnet routes are not exposed through this tunnel. The only public service is the high-entropy MCP path on loopback port `3105`.

The connector reuses Army Hub's admission policy: approved rooms and senders, explicit mentions only, no `@room`, event deduplication, repeated-delegation suppression, threading, mention metadata, and the six-agent-turn limit.

## What “real Grok” means here

This is Grok's actual cloud automation harness, not an xAI model-only API or a local impersonator. The routine can use its enabled cloud tools and connectors.

It is **asynchronous routine participation**, not a synchronous Bot chat API. Each Matrix mention starts a new automation run. This does not import or share Grok Bot's primary-chat history/memory, and no claim of a persistent primary-Bot conversation is made. Matrix is the shared conversation record.

## Security boundaries

- The webhook uses the official Standard Webhooks HMAC-SHA256 format. HTTP `202` means accepted, not completed.
- The webhook signing secret, endpoint, Matrix token, MCP path secret, state, logs, and tunnel URL are confined to ignored owner-only `.runtime/` files.
- The MCP server exposes only `army_reply`; it has no room-reading, general posting, credential, repository, or administration tool.
- Every reply requires a random token bound to one Matrix event. It expires after 30 minutes and is removed after one successful reply.
- The MCP path is unguessable, and request logs do not record it. A public path alone does not authorize a reply without a valid pending token.
- The connector cannot answer itself or bypass the shared agent-turn budget.
- Consequential actions remain subject to Mo's approval; the routine instructions explicitly prohibit deployments, purchases, deletion, and credential changes without it.

## Operate

From the repository root:

```sh
.venv-service/bin/python scripts/configure_grok.py
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  .venv-service/bin/python scripts/enroll_grok.py
sh scripts/install_grok.sh
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  .venv-service/bin/python scripts/verify_grok.py
```

Stop only Grok and its tunnel:

```sh
sh scripts/stop_grok.sh
```

The connector log is `.runtime/grok.log`; the tunnel log is `.runtime/grok-tunnel.log`. The live acceptance report is `.runtime/grok-verification-results.json`.

## Grok-side configuration

The live account contains an **Army Hub Grok** automation with a Webhook trigger and an **Army Hub** custom MCP connector. The routine is instructed to answer the incoming Matrix payload and call `army_reply` exactly once with the supplied token. Model selection remains `Auto` in Grok.

Do not commit or paste the webhook endpoint, signing secret, MCP URL, or reply tokens into Matrix, GitHub, or documentation.

## Availability and remaining production work

The current tunnel is a Cloudflare **quick tunnel**. It is suitable for the verified live deployment but its public hostname changes when the tunnel is recreated. After recreation, update the custom connector URL in Grok. The local connector and tunnel start through the authorized desktop session, consistent with the repository's macOS privacy constraints; automatic login startup is not configured.

For a durable production endpoint, replace the quick tunnel with a named tunnel/stable hostname while preserving the same loopback-only MCP service and single-use reply authorization. Agent Manager discovery/control for this non-ACP connector is separate future work and must not be represented as already available.

Official references:

- `https://docs.x.ai/grok/automations/webhooks`
- `https://docs.x.ai/grok/connectors#custom-mcp-connectors`
- `https://docs.x.ai/grok/connectors/custom-mcp-tunneling`

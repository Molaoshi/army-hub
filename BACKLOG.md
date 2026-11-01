# Army Hub backlog

## Next

- Complete the remaining physical iPhone checks: cellular access, attachments, and closed-app push. Signed-in access and real Hermes/DSH/Grok mention checks passed on 2026-11-02.
- Add a health-checked recovery path for Grok Bot's cloud computer. On 2026-11-02 it was offline for about nine hours; opening the existing Army Hub Bot's **Show computer** view restored Tailscale and queued-turn processing, but this manual wake is not a durable availability solution.
- With Mo's explicit approval for a new identity and paid model turn, run the Agent Manager's real end-to-end creation acceptance: one Matrix identity, selected rooms, one connector, a real mention reply, and a configuration change that restarts only that agent.
- Add an automatic login-start mechanism for connectors and the Agent Manager that works with macOS privacy protection without weakening TCC or moving the canonical repository.
- Add encrypted off-Mac backup and repeat the full restore drill on another machine.
- Enroll Dell and Book inventory/connectors only after local end-to-end acceptance remains green; join their reserved identities to the intended rooms.

## Later

- Continue `docs/lazy-tool-discovery-spec.md` only with a separate implementation `xdf`: the offline baseline and isolated Hermes native Gate B canary now pass (`docs/lazy-tool-discovery-hermes-canary.md`). Next is the read-only DSH MCP facade and Gate A/C acceptance. Do not build a parallel Hermes dispatcher, include DSH-native tools, enable OpenCode/Grok, or weaken the current approval cancellation.
- Add native-catalog drift acceptance after Hermes and OpenCode upgrades: compare connected provider/model/effort rosters with exact ACP application, and fail closed without exposing cached choices when discovery is stale or unsuccessful.
- Add native-gateway failure-injection coverage for tailnet interruption, gateway updates, restart between acceptance and transcript reply, and persistent-conversation recovery after deeper interruptions; remote process-death recovery is already verified. Retain separate webhook rollback tests.
- Test desktop-login autostart after a remote logout/login and document secure recovery after total VM replacement; neither is currently verified, and boot-before-login startup is not provided.
- Add read-only credential checks for Railway and MiniMax where their APIs support safe verification.
- Add interactive Matrix approval for ACP tool-permission requests; keep failing closed until then.
- Add failure-injection tests for ACP process death, `session/load`, and Matrix interruption. Connector restart during a prompt is now live-verified: the uncertain delivery becomes `interrupted` and is not replayed automatically.
- Replace broad GitHub credentials with a repository-scoped GitHub App and enforce branch protection/required checks.
- Add per-project rooms and registry entries only when real projects need them.
- Evaluate lightweight attachment scanning and storage quotas before enabling untrusted users.

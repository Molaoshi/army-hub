# Army Hub backlog

## Next

- Complete Mo's physical iPhone enrollment, then test cellular access, attachments, and closed-app push.
- Add an automatic login-start mechanism that works with macOS privacy protection without weakening TCC or moving the canonical repository.
- Add encrypted off-Mac backup and repeat the full restore drill on another machine.
- Add Dell and Book connectors only after local end-to-end acceptance remains green; join their reserved identities to the intended rooms.
- Add Grok's non-ACP connector to Agent Manager discovery/control.

## Later

- Add native-gateway failure-injection coverage for tailnet interruption, gateway updates, restart between acceptance and transcript reply, and persistent-conversation recovery after deeper interruptions; remote process-death recovery is already verified. Retain separate webhook rollback tests.
- Test desktop-login autostart after a remote logout/login and document secure recovery after total VM replacement; neither is currently verified, and boot-before-login startup is not provided.
- Add interactive Matrix approval for ACP tool-permission requests; keep failing closed until then.
- Add failure-injection tests for ACP process death, `session/load`, Matrix interruption, and connector restart during a prompt.
- Replace broad GitHub credentials with a repository-scoped GitHub App and enforce branch protection/required checks.
- Add per-project rooms and registry entries only when real projects need them.
- Evaluate lightweight attachment scanning and storage quotas before enabling untrusted users.

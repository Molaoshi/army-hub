# Army Hub backlog

## Next

- Complete Mo's physical iPhone enrollment, then test cellular access, attachments, and closed-app push.
- Add an automatic login-start mechanism that works with macOS privacy protection without weakening TCC or moving the canonical repository.
- Add encrypted off-Mac backup and repeat the full restore drill on another machine.
- Add Dell and Book connectors only after local end-to-end acceptance remains green; join their reserved identities to the intended rooms.
- Replace Grok's Matrix quick tunnel with a named tunnel/stable hostname, supervise the remote native connector, and add its non-ACP connector to Agent Manager discovery/control.

## Later

- Add native-gateway failure-injection coverage for tunnel interruption, gateway updates, remote process death, restart between acceptance and transcript reply, and persistent-conversation recovery; retain separate webhook rollback tests.
- Add interactive Matrix approval for ACP tool-permission requests; keep failing closed until then.
- Add failure-injection tests for ACP process death, `session/load`, Matrix interruption, and connector restart during a prompt.
- Replace broad GitHub credentials with a repository-scoped GitHub App and enforce branch protection/required checks.
- Add per-project rooms and registry entries only when real projects need them.
- Evaluate lightweight attachment scanning and storage quotas before enabling untrusted users.

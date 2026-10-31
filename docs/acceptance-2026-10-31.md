# Acceptance record — 2026-10-31

## Passed

- Synapse, PostgreSQL, Element Web, and the backup scheduler are healthy in Docker.
- Matrix and Element respond through their tailnet-only HTTPS routes on ports 8444 and 8445.
- All six provisioned Matrix identities passed `whoami` during provisioning.
- Hermes and DSH each completed real `initialize → session/new → session/prompt` ACP turns.
- Twelve unit tests pass, including ACP session reuse and session reload after a controlled harness-process restart.
- Five live Matrix acceptance tests pass with real model turns:
  1. No agent responds to an unmentioned message.
  2. `@hermes-mini` responds in the triggering message's thread.
  3. `@dsh-mini` responds in the triggering message's thread.
  4. A Hermes-authored mention triggers DSH, whose explicit return mention triggers Hermes in the same thread.
  5. An event at agent turn six produces a human notice and no further model turn.
- The complete five-test live sequence passed again after stopping and restarting both connectors.
- A backup archive and an 831-entry PostgreSQL restore manifest were generated with owner-only permissions.
- The dump restored into an isolated temporary database and contained all three rooms. The temporary database was removed after verification.
- The backup container contains the nightly `19:17 UTC` schedule, equivalent to 03:17 China Standard Time.
- Git exclusions cover runtime secrets, databases, credentials, virtual environments, and local environment files. A source scan found no provisioned access tokens or owner API keys in tracked source.

## Agent Manager

- The tailnet-only manager responds at `https://moatazs-mac-mini.tailef80eb.ts.net:8446/`; its loopback service binds only to `127.0.0.1:3104`.
- Twenty-five combined manager and bridge tests pass. Frontend JavaScript syntax and backend import/compile checks pass.
- Live API acceptance passed for Matrix login, real inventory/three rooms, avatar upload and authenticated download, 512 × 512 processing, native Keychain add/read/list/delete, metadata masking, and secret absence.
- Real browser acceptance passed through the tailnet URL: Matrix login, five-agent directory, agent details, dependent Hermes/DSH model choices, Matrix ID preview, display-name/avatar editing, and credential add/list/test/confirmed delete.
- Reserved identities show no unusable connector controls and reject pause without losing their reserved state. Providers without a read-only test stay `not_tested`, not `valid`; both edge cases were also verified in the browser.
- Mobile (390 CSS px) and desktop (1440 CSS px) layouts switch correctly and have no horizontal document overflow.
- DSH restarted in isolation; Hermes stayed on its original process. Profile and credential checks did not restart either working connector.
- The reserved Grok display name/avatar were restored and the temporary credential deleted after testing.

## Not yet verified or intentionally incomplete

- Real creation of an additional Matrix agent and its first paid harness turn. Creation/configuration have unit and mocked coverage; the browser form was not submitted to avoid an unrequested identity and charge.
- Effort control is intentionally absent until a real per-agent ACP setter exists. DSH currently exposes only its harness profile default.
- Railway, MiniMax, and Other have no configured read-only credential test.
- Physical iPhone login, cellular messaging, attachments, and closed-app push.
- Interactive Matrix approval for ACP tool-permission requests; these requests currently fail closed.
- Automatic login startup for connectors and the Agent Manager under the existing macOS Documents privacy policy.
- Encrypted off-Mac backup.
- Dell, Book, and Grok connector deployment.

## Git state

- Private repository: `https://github.com/Molaoshi/army-hub`
- Issue: `#1`, recording the acceptance requirements.
- Pull request `#3`, `agent/kimi-macserver/acceptance-record` → `main`, was merged by Mo. The Agent Manager branch is based on the resulting `origin/main` commit `a37f7e7`.
- Agent Manager pull request: `#4`, `agent/kimi-macserver/agent-manager` → `main`, open and unmerged for Mo's review.
- The pre-existing remote `test` commit and other machine branches were preserved. No direct push to `main`, force push, or merge occurred during the Agent Manager work; the tailnet manager deployment is the explicitly authorized local service.
- The classic branch protection that required an approving review was removed before opening `#3`; repository rulesets were left untouched for joint design with Mo.

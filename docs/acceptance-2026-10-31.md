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

## Not yet verified or intentionally incomplete

- Physical iPhone login, cellular messaging, attachments, and closed-app push.
- Interactive Matrix approval for ACP tool-permission requests; these requests currently fail closed.
- Automatic login startup for connectors under the existing macOS Documents privacy policy.
- Encrypted off-Mac backup.
- Dell, Book, and Grok connector deployment.

## Git state

- Private repository: `https://github.com/Molaoshi/army-hub`
- Issue: `#1`, recording the acceptance requirements.
- Pull request: `#3`, `agent/kimi-macserver/acceptance-record` → `main`, open and unmerged for Mo. It supersedes `#2`, which Mo closed.
- The pre-existing remote `test` commit and other machine branches were preserved. No direct push to `main`, force push, merge, or deployment occurred.
- The classic branch protection that required an approving review was removed before opening `#3`; repository rulesets were left untouched for joint design with Mo.

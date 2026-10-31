# Operations

## Services

```sh
cd /Users/immortalist/Documents/Kimi/Workspaces/MacServer/army-hub
docker compose --env-file .env ps
docker logs --tail 100 army-synapse
docker logs --tail 100 army-postgres
ps -p "$(cat .runtime/hermes-mini.pid),$(cat .runtime/dsh-mini.pid)" -o pid,etime,state,command
```

Loopback Matrix is `http://127.0.0.1:8010`; Element is `http://127.0.0.1:3103`. Public binding is not used. Tailscale Serve provides ports 8444 and 8445 only inside the tailnet.

## Connector start, stop, and restart

```sh
sh scripts/install_bridges.sh
sh scripts/stop_bridges.sh
```

The install command is idempotent and starts each connector through the current authorized desktop session. It deliberately does not use launchd: macOS 26 denied launchd children access to this repository under `Documents`, before Python could load. Do not weaken privacy or Full Disk Access settings as a workaround. Automatic login startup remains a backlog item; after a reboot or logout, run the install command once from Kimi or another Documents-authorized terminal.

Logs are `.runtime/hermes-mini.log` and `.runtime/dsh-mini.log`. Each connector saves its Matrix cursor and ACP session map in its own `.runtime/*-state.json` file.

## Matrix and web services

```sh
docker compose --env-file .env restart synapse element backup
```

Do not use `tailscale serve reset`; it would remove unrelated services. To remove only Army Hub exposure, use `tailscale serve --https=8444 off` and `tailscale serve --https=8445 off`.

## Backups

The `army-backup` container runs `scripts/backup.sh` every night at 03:17 China Standard Time (`19:17 UTC`). A backup contains a PostgreSQL custom-format dump, restore manifest, Synapse signing material/configuration/media, room map, and provisioning credentials. Files are owner-only and the latest 14 archives are retained.

Run and inspect a backup manually:

```sh
docker compose exec backup /army/scripts/backup.sh
docker compose exec backup crontab -l
ls -lt .runtime/backups
```

The 2026-10-31 acceptance run produced an 831-entry restore manifest and restored successfully into an isolated temporary database; all three rooms were present. The temporary database was then removed.

A copy on the same Mac is not disaster protection. Copy the archive to another machine or object storage and encrypt it before off-Mac transport. Off-Mac backup is not yet configured.

## Live acceptance test

```sh
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  .venv-service/bin/python scripts/verify_matrix_agents.py
```

This uses real model turns and posts test messages in `Army Lab`. It checks unmentioned silence, both direct mention paths, threading, a Hermes → DSH → Hermes handoff, and the six-turn stop. Results are written to `.runtime/verification-results.json`.

## Security notes

- Registration and federation are disabled.
- Rooms are private and agent room administration is denied by power levels.
- Every bridge requires explicit mentions and approved rooms/senders.
- Agent-to-agent turn count travels in Matrix event content, so the limit works across machines.
- Model tool permission requests currently fail closed at the ACP client boundary. Harness-native permissions still apply; interactive Matrix tool approval is a later enhancement.
- Runtime secrets are ignored by git. Do not paste them into Matrix or commit them.

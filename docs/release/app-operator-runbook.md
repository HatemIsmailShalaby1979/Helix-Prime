# Helix Codex App — Operator Runbook

Operational procedures for running the Helix Codex App in a self-hosted
environment. This runbook covers health checks, logs, backup and restore,
and common troubleshooting steps.

## Architecture

The app runs as a single Docker container. It holds one SQLite database
(app.db), one governed memory tree (memory_stores/), and serves the web UI
on http://127.0.0.1:8100. There are no external dependencies — no Redis,
no message broker, no separate database server.

Data lives in a Docker named volume (`helix_app_data`) mounted at `/data`.

## Health check

The container runs a built-in health check every 30 seconds. Check status:

```
docker compose -f infra/docker/docker-compose.app.yml ps
```

A healthy app shows "healthy" under STATUS. The health check verifies that
the web server responds on `http://127.0.0.1:8100/app/healthz`.

Manual check:

```
curl -s http://127.0.0.1:8100/app/healthz
```

Returns HTTP 200 with an empty body when the app is running.

## Logs

View the app logs:

```
docker compose -f infra/docker/docker-compose.app.yml logs helix-app
```

Follow logs in real time:

```
docker compose -f infra/docker/docker-compose.app.yml logs -f helix-app
```

The app writes structured log lines to stdout (one per request, with
correlation id, route, status code, and duration). Error messages appear
in the same stream.

## Backup

The backup copies the app database and the memory store tree into a
backup directory with a manifest:

```
docker compose -f infra/docker/docker-compose.app.yml exec helix-app \
    python helix_codex_app/scripts/backup_app.py --target /tmp/backup
```

Copy the backup out of the container:

```
docker cp \
    $(docker compose -f infra/docker/docker-compose.app.yml ps -q helix-app):/tmp/backup \
    ./helix-backup-$(date +%Y%m%d)
```

The backup manifest records the node count and memory chain verification
status. A chain that fails verification is flagged in the manifest.

**Schedule:** Run a backup daily if the app is in active use.

## Restore

Restoring requires the app to be stopped and the target to be clean:

```
docker compose -f infra/docker/docker-compose.app.yml down
docker volume rm infra_helix_app_data
```

Copy the backup into the container:

```
docker compose -f infra/docker/docker-compose.app.yml run --rm helix-app sh
```

Inside the container, run the restore:

```
python helix_codex_app/scripts/restore_app.py \
    --backup /tmp/backup --target /tmp/restore
```

The restore verifies node counts and memory chains against the manifest.
A mismatch exits with code 1 and the data is not applied.

After a successful restore, start the app normally.

## Evidence export

Owners can export a full evidence dossier from the Admin screen
(**Admin > Evidence export**). The download is a zip containing the
audit trail, node counts, memory chain verification, and the release
manifest.

## Troubleshooting

### App won't start ( unhealthy after 2 minutes )

1. Check logs: `docker compose -f infra/docker/docker-compose.app.yml logs helix-app`
2. Common causes:
   - The database file is locked by another process
   - The `/data` volume is full
   - A previous shutdown left a WAL file

### Bootstrap script says "domain already exists"

The domain was already created. You can log in with any existing owner
account, or create a new owner through the Admin screen.

### Cannot reach http://127.0.0.1:8100 from another machine

This is by design. The app binds to your machine's loopback address
and cannot accept connections from other machines. Use an SSH tunnel
or VPN for remote access.

### Password forgot / locked out

If you have access to the database file, the operator can reset the
password by running the bootstrap script with a new password and a
different domain, then creating a new owner. Alternatively, the
database file at `/data/app.db` can be removed (along with the
`/data/memory_stores` tree) to start fresh — this deletes all data.

### Container won't stop

```
docker compose -f infra/docker/docker-compose.app.yml kill
docker compose -f infra/docker/docker-compose.app.yml down -v
```

Removing the volume deletes all data. Only do this if you have a
backup or are starting fresh.

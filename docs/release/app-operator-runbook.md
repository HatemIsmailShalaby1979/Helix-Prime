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
Inside the image `/data` is owned by the unprivileged `helix` user
(uid 10001) and is the only writable application path; the app itself runs
as that user, never as root. On the host, the volume contents are managed
by Docker — never `chmod` or `chown` the volume files directly while the
container is running.

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

## Upgrade safely (backup first)

Never upgrade without a fresh backup. Upgrades only ever replace code;
the `/data` volume is left untouched, but a backup is the only way back
if a new image fails to start against an old database.

1. Back up first (see **Backup** above) and copy the backup folder out of
   the container.
2. Pull or rebuild the image:
   ```
   docker compose -f infra/docker/docker-compose.app.yml build --pull
   ```
   The build installs dependencies from the pinned
   `release/requirements.lock.txt`, so a rebuild resolves the exact same
   dependency set.
3. Recreate the container without removing the volume:
   ```
   docker compose -f infra/docker/docker-compose.app.yml up -d
   ```
   (`down` without `-v` also preserves the volume. Never use `down -v`
   for an upgrade — that deletes all data.)
4. Verify: wait for `healthy` in `ps`, then open the app and log in.
   If the container will not turn healthy, stop it and restore from the
   backup in step 1 (see **Restore** above).

## Evidence export

Owners can export a full evidence dossier from the Admin screen
(**Admin > Evidence export**). The download is a zip containing the
audit trail, node counts, memory chain verification, and the release
manifest.

## Remote access, TLS, and cookies

The app binds to loopback only and refuses to start on any other address.
For access beyond the host, terminate TLS at a reverse proxy on the same
machine (nginx, Caddy, or an SSH tunnel/VPN) and forward plain HTTP to
`http://127.0.0.1:8100`. Never expose the app socket directly.

Cookie and TLS requirements:

- `HELIX_APP_COOKIE_SECURE` stays `true` (the default) whenever browsers
  reach the app over HTTPS. Every session cookie is `HttpOnly`, `SameSite=Lax`,
  `Path=/`, and `Secure` under that setting. Behind plain HTTP the `Secure`
  cookie is never sent, so local plain-HTTP development is the only
  configuration that sets it to `false` — and disabling it through the
  environment refuses to start unless `HELIX_APP_ALLOW_INSECURE_COOKIES=true`
  is set alongside, so a production container can never drift insecure
  silently.
- The app does not interpret `X-Forwarded-For` or `X-Forwarded-Proto`: the
  address recorded in `login_events` and used for login throttling is the
  immediate peer, so run exactly one proxy on the same host.
- Session lifetime follows `HELIX_APP_SESSION_IDLE_MINUTES` (idle expiry)
  and `HELIX_APP_SESSION_ABSOLUTE_DAYS` (hard ceiling); a password change
  revokes every session for the account immediately.
- Sign-in is throttled per source address and per login name in fixed
  windows (SQLite-backed, bounded); repeated failures also lock the account
  for 15 minutes. All credential failures share one message, so throttling
  and lockout never reveal whether a domain, username, or password was wrong.

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

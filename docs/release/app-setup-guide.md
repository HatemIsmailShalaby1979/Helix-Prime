# Helix Codex App — Setup Guide

Ten-minute install for a self-hosted Helix Codex App on your own machine.
No cloud account, no external services, no command-line experience required beyond
copying and pasting a few commands.

## What you need

- A computer running Windows, macOS, or Linux
- Docker Desktop (free): https://www.docker.com/products/docker-desktop
- The Helix Codex App source code (download or clone the repository)

## Step 1 — Install Docker

1. Download Docker Desktop from https://www.docker.com/products/docker-desktop
2. Run the installer and follow the prompts
3. Start Docker Desktop and wait until it says "Docker is running"

## Step 2 — Get the source code

Download or clone the Helix Codex App repository to your computer. If you are
not sure how, ask whoever gave you this guide.

## Step 3 — Start the app

Open a terminal (Command Prompt or PowerShell on Windows, Terminal on macOS)
and navigate to the repository folder. Then run:

```
docker compose -f infra/docker/docker-compose.app.yml up -d
```

This downloads the dependencies and starts the app. The first time takes a few
minutes. Subsequent starts are fast.

## Step 4 — Wait for the health check

Run this to confirm the app is ready:

```
docker compose -f infra/docker/docker-compose.app.yml ps
```

Look for "healthy" under STATUS. If it says "starting", wait 30 seconds and
run the command again. If it says "unhealthy", see the Troubleshooting section
in the operator runbook.

## Step 5 — Create the first owner account

Replace `mycompany`, `admin`, and `mypassword` with your own values:

```
docker compose -f infra/docker/docker-compose.app.yml exec helix-app \
    python helix_codex_app/scripts/bootstrap_owner.py \
    --db-path /data/app.db --domain mycompany \
    --username admin --password mypassword
```

You should see: `owner created: admin@mycompany`.

**Write down the domain, username, and password.** You will need them to log in.

The domain name becomes your team's login suffix (admin**@mycompany**). Pick
something short and memorable — it cannot be changed later.

## Step 6 — Open the app

Open your web browser and go to:

```
http://127.0.0.1:8100
```

Log in with the username and password you chose in Step 5.

## Step 7 — Invite your team

Once logged in as the owner, go to **Admin > Users** and create accounts
for your team members. You can assign roles: owner, manager, or employee.

## Stopping the app

```
docker compose -f infra/docker/docker-compose.app.yml down
```

Your data is saved in a Docker volume. Starting the app again with `up -d`
restores everything.

## Backing up your data

Run the backup command from the repository folder:

```
docker compose -f infra/docker/docker-compose.app.yml exec helix-app \
    python helix_codex_app/scripts/backup_app.py --target /tmp/backup
```

Then copy the backup folder out of the container:

```
docker cp $(docker compose -f infra/docker/docker-compose.app.yml ps -q helix-app):/tmp/backup ./backup
```

The backup folder contains your database and memory stores.

## Security note

The app is designed to run on your local machine only. It binds to
`127.0.0.1` (your machine's internal address) and cannot be reached from
the internet or other computers on your network. Do not change the
`HELIX_APP_HOST` setting — the app will refuse to start if you do.

If you need to access the app from another machine, use an SSH tunnel or
a VPN rather than exposing the app directly.

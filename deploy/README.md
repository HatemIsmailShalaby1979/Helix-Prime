# Quick Tunnel deployment

This deployment keeps the Helix Codex App on `127.0.0.1:8100` and publishes it through Cloudflare Quick Tunnel.

Run `deploy\quick-tunnel.ps1` from the repository root. It starts the app and then runs:

```text
cloudflared tunnel --url http://127.0.0.1:8100
```

The command prints a temporary HTTPS URL on `trycloudflare.com`. The URL rotates whenever `cloudflared` restarts. It is suitable for B6/B7 reachability evidence, not for a durable public address or production uptime claim.

The app must remain loopback-bound. Do not set `HELIX_APP_HOST` to a public address.
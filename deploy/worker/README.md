# Helix Codex Worker front door

The Worker reads `HELIX_ORIGIN` from the `ORIGIN_KV` binding on every request.
`deploy/update-worker-origin.ps1 -Origin https://<current-quick-tunnel>.trycloudflare.com`
updates that value. The tunnel launcher should call this command after each new
Quick Tunnel starts, before external traffic is tested.

Missing, malformed, or unreachable origins return a typed HTTP 503 instead of a
Cloudflare generic upstream error.
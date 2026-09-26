# Helix Codex Worker front door

The Worker reads `HELIX_ORIGIN` from the `ORIGIN_KV` binding on every request.
`deploy/update-worker-origin.ps1 -Origin https://<current-quick-tunnel>.trycloudflare.com`
updates that value. The tunnel launcher should call this command after each new
Quick Tunnel starts, before external traffic is tested.

A missing or malformed origin returns the Worker's own typed HTTP 503.

An origin that is registered but whose tunnel is **down** does not. `fetch` to a
dead `trycloudflare.com` hostname returns Cloudflare's own 530 error page as a
valid response rather than throwing, so the Worker passes it through unchanged.
Measured 2026-09-27 while tearing down: with the tunnel stopped and the KV key not
yet deleted, `/app/healthz` through the Worker answered **530** with Cloudflare's
"Cloudflare Tunnel error" page; once the key was gone the Worker answered
**503** `{"error":"origin_unavailable","message":"Demo temporarily offline: origin
not registered."}`. Treat a 530 through this hostname as "origin registered, tunnel
dead", not as a Worker fault.
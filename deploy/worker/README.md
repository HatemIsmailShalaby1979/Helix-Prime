# Helix Codex Worker front door

The Worker reads `HELIX_ORIGIN` from the `ORIGIN_KV` binding on every request.
`deploy/update-worker-origin.ps1 -Origin https://<current-quick-tunnel>.trycloudflare.com`
updates that value. The tunnel launcher should call this command after each new
Quick Tunnel starts, before external traffic is tested.

Every way the front door can be down answers the Worker's own typed HTTP 503:

| Origin state | Status | Message |
|---|---|---|
| key absent from KV | 503 | `origin not registered` |
| origin not an http(s) URL | 503 | `registered origin is invalid` |
| `fetch` throws | 503 | `registered origin is unreachable` |
| origin answers **530** | 503 | `the registered origin's tunnel is down` |
| origin answers anything else | passed through unchanged | — |

**Why 530 is converted.** `fetch` to a dead `trycloudflare.com` hostname returns
Cloudflare's own 530 Tunnel error page as a *valid* Response rather than throwing, so
without this check the Worker passed a Cloudflare-branded page straight to the
visitor. Measured 2026-09-27 before the fix: tunnel stopped, KV key still present,
`/app/healthz` answered **530** with Cloudflare's "Cloudflare Tunnel error" page.

**Why only 530.** 530 is Cloudflare's own tunnel-failure code and this application
never emits it, so the rule cannot mask a genuine application error. Rewriting the
other 5xx was rejected on purpose: an app-generated 500 is real information for the
operator, and relabelling it "offline" would hide an application fault behind a
connectivity label.

The side benefit is that the public front door no longer discloses its upstream: the
passthrough page named the rotating `trycloudflare.com` origin in the visitor's
browser.
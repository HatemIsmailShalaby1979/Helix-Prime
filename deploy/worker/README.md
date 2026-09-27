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

## The client address the origin sees

The Worker copies the visitor's address into **`x-helix-client-ip`** on the way out,
and deletes that header if Cloudflare did not supply one.

This is not cosmetic. Measured 2026-09-27, with the caller's egress address known
independently (`197.132.77.25`):

| Path | `cf-connecting-ip` reaching the origin |
|---|---|
| tunnel direct | `197.132.77.25` — the visitor |
| **through this Worker** | `2a06:98c0:3600::103` — Cloudflare's own egress |

Cloudflare rewrites `cf-connecting-ip` on the Worker's outbound `fetch`, so once this
Worker is in the path that header describes Cloudflare rather than the caller, and an
origin that rate-limits on it would bound every visitor as a single caller. A custom
header is not rewritten, so the value survives the hop. The Worker always **sets or
deletes** it, never passing a caller's own value through, which is what makes it
trustworthy at the origin.

If this Worker is ever removed from the path, the origin falls back to
`cf-connecting-ip` and then to the socket peer — see
`helix_codex_app/security/client_ip.py`.

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
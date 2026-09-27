> **Status: Public governed demo — running on request / 1,897 tests passed / 0 failed (measured 2026-09-27) / Production `NOT_READY` / Releases `v1.1.0` / No external audit / No paying client.**
>
> The demo is served through a Cloudflare Worker whose origin is a Quick Tunnel that is **not left running between sessions**. No demo address is published in this file for that reason — it would land on an offline page. §3 carries the measured evidence instead, and §4 says how to ask for a live session.
>
> `CONTROLLED_PILOT_READY` is an internal self-approval (`approver: "operator-pilot-consent"`). No third-party sign-off exists.

# Helix Prime

> **The operations core of Helix Codex.**

> **Authority chain:** `00_CONSTITUTION.md` (authority) → `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture + commercial record) → implementation. On conflict, the earlier link in the chain wins. The constitution outranks the blueprint, and both outrank status summaries, roadmaps, and release docs.

Helix Prime is a local-first platform that runs six business engines (WFM, RTA, CX, B2B, Personnel, CRM) with nine AI agents routing requests by content. The canonical artifact is **`helix-api`**, a governed FastAPI spine where identity, RBAC, approvals, the kill switch, metrics, and the audit chain are enforced. The Streamlit cockpit is a secondary read-only diagnostic surface. Everything runs on your machine with no cloud dependency.

Helix Prime is the operations core of **Helix Codex**, an accountable AI operating organization that helps businesses understand operations, coordinate decisions, and improve through evidence without silently taking control.

**What is new since the previous revision of this file.** The governed path is now reachable from outside, and a stranger can drive it end to end. A visitor signs in with GitHub through Supabase Auth, lands on a session holding exactly one permission, submits four numbers, and receives a workforce-forecast answer produced by the same gate, workflow record, and audit trail the internal pilot uses. §1 walks the flow, §2 shows what enforces it, and §3 shows the captured evidence.

---

## 1. The public demo

A visitor:

1. Opens the sign-in route. `GET /app/auth/supabase/login` answers `303` and hands off to GitHub OAuth through Supabase Auth (PKCE, `S256`).
2. Authenticates at GitHub.
3. Returns to `/app/auth/supabase/callback`, which verifies `state` by strict equality against the cookie set at login, exchanges the one-use code, and **bridges the verified GitHub identity onto the demo account** — the account's email is rewritten to the GitHub address. No shared password is involved on this path.
4. Lands on `/app/ops/demo`, inside the ordinary `ops.view` boundary rather than on a separate public route.
5. Submits four numbers.
6. Receives an Erlang C staffing answer with a correlation id, and can open `/app/ops/audit/{correlation_id}` to read the recorded decision chain behind their own run.

The session is the smallest role in the system:

| Property | Value |
|---|---|
| Domain / tenant / client | `helix-demo` |
| Role | `demo` |
| Permissions | `ops.view` — **and nothing else** |
| Engine access | resolved through the normal tenant-scoped path, never tenant-blind |

Because the role holds no `ops.manage` and no `ops.approve`, a demo session cannot create, approve, execute, or delete anything by any route other than the single purpose-built demo endpoint. The `demo` role is deliberately **not** in `APP_ROLE_ENGINE_CATALOG_ROLE` — that map is tenant-blind, so a role placed there would resolve to one tenant's engine for every tenant, which is the cross-tenant bug the least-privilege demo identity exists to prevent.

**The passwordless route is a fixture, not an entry point.** `GET /app/auth/demo` signs the shared demo identity in with no password and no identity-provider round trip. `create_app` mounts it only when `HELIX_APP_ENABLE_PASSWORDLESS_DEMO` is true, and that setting defaults to **false**. A deployed instance therefore has no such route: the path answers `404` because it was never registered, not because it was refused. It exists for local development and the test suite, and nowhere else.

### 1.1 The one endpoint

`POST /app/api/ops/demo/wfm` — behind the standard session guard and CSRF check, exactly like every other mutating route. No session gets `401`; a session without a CSRF token gets `403`.

A caller may set **four numeric fields** and nothing else:

| Field | Range (both ends exclusive) | Meaning |
|---|---|---|
| `arrival_rate` | `> 0` | contacts arriving per period |
| `average_handling_time` | `> 0` | average contact duration |
| `service_level_target` | `> 0` and `< 1` | minimum share of contacts **answered immediately** |
| `average_calls_per_period` | `> 0` | optional; defaults to `17.0` |

The ranges are not invented by the app. They mirror the WFM engine's own validation in `engines/wfm/adapter.py`, so the demo refuses at the edge exactly what the engine would refuse anyway.

**On the third field's name.** `service_level_target` sounds like a speed-of-answer target. Read the code rather than the name: `optimize_agents()` compares `calculate_service_level(...)` against this target, and that function is `exp(-agents × (1 − utilisation) × ASA)` — the probability a contact is **answered immediately**. The engine is never given a waiting-time threshold, so there is no "answered within 20 seconds" anywhere in this system. The name is the engine's and is passed through unchanged; the explanation of what it compares against belongs to the surface, which is why the demo screen states it rather than letting a reader supply their own deadline.

---

## 2. What is enforced, and where

The governance model here is enforced rather than described. Each control below names the file that implements it.

### 2.1 The gate — every submission, before execution

Every workflow is evaluated before any engine is called. The gate is `evaluate_gate()` in `control_plane/governance.py`, invoked from `control_plane/engine.py` at the `validated` state. It is **fail-closed**, and it evaluates four things against the acting role's profile:

- estimated financial cost, against the role's approval limit;
- data classification, against the classifications the role may read;
- confidence score;
- engine ownership.

It returns one of three states: `dead_letter` (hard deny — unknown role, unknown classification, forbidden classification, or an engine outside the role's owned set), `awaiting_approval` (frozen for a human), or `executing` (inside every boundary).

If the gate holds a submission, **the demo reports the held state instead of forcing the run, and the engine is not called at all.** The response then carries `executed: false`, `gated: true`, and a `gated_reason` naming the state it was held in. Forcing the run would prove nothing about the product and would hide the property the demo exists to show.

The demo passes `requires_approval=False`. That is a property of *this demo*, not a weakened control: the gate above still runs, and still decides.

### 2.2 Provenance — server-owned, and structural

`is_sample: true` and `data_mode: "simulated_realistic"` are **server-owned**. The demo bridge injects them on every run; no request can set them. The stored payload is exactly four numbers plus those two fields.

This is structural rather than a filter. The payload is built by a function whose signature is four named numbers and which takes no `**kwargs` and no `**extra`, so there is no code path by which a caller-supplied key could reach the workflow record. A test asserts the signature has no variadic parameter, so the property cannot be quietly broken by a later edit.

A request carrying any key the demo does not own is **refused with `400`, not silently stripped** — silently dropping a field a caller thought they set is how a demo ends up appearing to honour input it ignored. The refused set includes `is_sample`, `use_sample`, `data_mode`, `data_classification`, `estimated_financial_cost`, `confidence_score`, `max_agents`, `owning_role_id`, and `capability`. Two matter most: **`data_classification` and `confidence_score` are the fields that would let a caller dress a synthetic run up as a verified one**, so they are never read from the request.

Booleans, strings, `null`, `NaN`, and `Infinity` are all rejected. `True` is not accepted as `1`, because that is a category error, not a coercion.

### 2.3 Rate limiting — keyed on the visitor, not on Cloudflare

`helix_codex_app/security/route_limits.py` bounds the routes a stranger can reach, with fixed-window counters keyed on **the resolved client address and the route name together**. That pairing is the point: one visitor exhausting the submit ceiling cannot lock another visitor out of the demo screen, and cannot lock anyone out of the sign-in routes.

| Route | Ceiling | Window |
|---|---|---|
| `GET /app/auth/supabase/login` | 30 | 60 s |
| `GET /app/auth/supabase/callback` | 30 | 60 s |
| `GET /app/auth/demo` (fixture) | 10 | 60 s |
| `GET /app/ops/demo` | 60 | 60 s |
| `POST /app/api/ops/demo/wfm` | 10 | 60 s |

The client address is **not** read from `cf-connecting-ip`. Cloudflare rewrites that header on a Worker's outbound `fetch`, so once the Worker is in the path it describes Cloudflare rather than the caller — and an origin that rate-limits on it would bound every visitor as a single caller. Measured 2026-09-27 with the caller's egress address known independently (`197.132.77.25`):

| Path | `cf-connecting-ip` reaching the origin |
|---|---|
| tunnel direct | `197.132.77.25` — the visitor |
| **through the Worker** | `2a06:98c0:3600::103` — Cloudflare's own egress |

The Worker therefore **sets or deletes** `x-helix-client-ip` on every request and never passes a caller's own value through, which is what makes it trustworthy at the origin. The origin's fallback order is `x-helix-client-ip`, then `cf-connecting-ip`, then the socket peer (`helix_codex_app/security/client_ip.py`).

### 2.4 The audit trail — a reader, not a second log

`GET /app/ops/audit/{correlation_id}` (with a JSON twin at `/app/api/ops/audit/{correlation_id}`) shows the recorded decision chain for one run: the gate decision, timestamps, the actor handoff, and the executed/succeeded state the core already recorded. It requires `ops.view`, and it **makes no record of its own** — it reads what the governed path wrote, so it cannot drift away from it.

It is declared above the `/app/ops/{engine_id}` catch-all, because FastAPI matches routes in declaration order: registered below it, the path would be answered as an engine whose id happens to be `audit`.

---

## 3. The evidence

Everything in this section was captured from real runs and is quoted as measured. None of it is reconstructed from memory.

### 3.1 The sign-in redirect chain, as observed

| # | Hop | Status | Notes |
|---|---|---|---|
| 1 | `GET <front door>/app/auth/supabase/login` | `303` | `redirect_to=…%2Fcallback%3Fstate%3D<app state>` |
| 2 | `GET <supabase project>/auth/v1/authorize` | `302` | → GitHub; GoTrue mints its **own** `state` UUID |
| 3 | `GET github.com/login/oauth/authorize` | — | the operator authenticates and consents |
| 4 | `GET <supabase project>/auth/v1/callback` | `302` | → the app callback, appending its own `code` |
| 5 | `GET <front door>/app/auth/supabase/callback?code=…&state=…` | `303` | see below |
| 6 | `GET <front door>/app/ops` | `200` | session presented, `tenant_id=helix-demo` |

Supabase does not forward this app's `state` to the callback; it preserves the query string already on `redirect_to` and appends its own `code`. The app's `state` therefore travels inside `redirect_to` itself, and the callback checks it with strict equality against the cookie set at login. The callback request, verbatim from the app log:

```text
GET /app/auth/supabase/callback?code=3207405e-f208-49af-b1ea-30bb8667a500&state=zoI3moGaFu4i6511Mn2Vc7uImIuD2zTTOKkZ3Fqg7vY
  -> 303 See Other, duration_ms 1484
```

Four things follow from that one line:

- `state` and `code` **both arrived** — the confirmation the fix was written for.
- The `state` is the app's own value (a `secrets.token_urlsafe(32)` string), not GoTrue's UUID, so it survived the whole round trip inside `redirect_to`.
- It **passed** the strict CSRF check — `303`, not `400`. The same route with a deliberately wrong `state` returns `400`, which is what makes the `303` meaningful rather than incidental.
- **1,484 ms** is the real network round trip to Supabase's token exchange. The local-only rejections measured earlier in the same thread returned in 0 ms.

The session and identity bridge, read from the database after that run:

| Field | Value |
|---|---|
| session | `session-2aef4631f5784cacb24a81bd1600fb19`, issued `2026-09-26T22:43:42Z`, expires `2026-10-26` |
| account | `account-c27e7988cd544c798288d92168d5cf83`, username `demo` |
| role | `demo` |

### 3.2 A governed demo run, captured

`POST /app/api/ops/demo/wfm` → `201 Created`:

```json
{
  "capability": "wfm_forecast",
  "client_id": "helix-demo",
  "correlation_id": "e538347905434e1881c26a0c67124063",
  "data_mode": "simulated_realistic",
  "error": null,
  "executed": true,
  "is_sample": true,
  "metrics": {
    "average_speed_of_answer": 5.0,
    "calculation_time": 0.0,
    "confidence_interval": [1.9, 2.1],
    "optimal_agents": 2,
    "probability_waiting": 0.410958904109589,
    "service_level_achieved": 0.9394130628134758,
    "traffic_intensity": 0.625,
    "utilization": 0.625
  },
  "metrics_digest": "142ef332dd6e3478",
  "retry_count": 0,
  "state": "closed",
  "succeeded": true,
  "tenant_id": "helix-demo",
  "workflow_id": "wf_abdf9a94b1e7"
}
```

Read it carefully, because four fields are easy to over-read:

- `metrics` are Erlang C workforce-planning figures for the inputs given: **two agents** to hold **62.5% utilisation**, with **93.9% of contacts answered immediately** and a **41.1% probability that a contact waits**. There is no "within target" in that sentence and no such field in the payload — see §1.1. Calling the service level a "share answered within target" is the single most likely way to misread a staffing forecast.
- `succeeded` is derived from the run's own evidence (`executed and error is None and metrics`), and `state` is reported beside it rather than instead of it. **`closed` on its own does not mean the run finished cleanly:** `WorkflowState` is plain string constants, and `closed` is also reached by cancellation, compensation, and dead-lettering. A successful demo run ends `closed` too.
- `metrics_digest` is the first 16 hex characters of a SHA-256 over the canonical JSON of `metrics`. Same inputs, same digest; change an input, and it changes. It is a **fingerprint, not a signature and not an attestation.**
- `confidence_interval` is `[1.9, 2.1]` — a flat ±5% band around the optimum. It is **not** a statistical confidence interval: no sampling error and no probability is computed, and the engine's own `confidence_level` field is unused. The demo screen labels it "Agent range around that figure" for exactly that reason.

### 3.3 What the evidence is not

- **There is no `computation_evidence` field, on purpose.** The registered engine handler returns `EngineResult.metrics` and discards `computation_evidence`; there is none to report. Naming a field the engine never produced is how a sample run gets dressed up as a verified one.
- **`wfm_coverage` is not governed evidence.** The same bridge exposes a coverage figure that calls the WFM adapter *directly*, bypassing policy, events, audit, and the workflow record. It is a fast preview and must never be presented as the result of a governed run. Only the endpoint in §1.1 is the governed path.
- **No confidence or classification claim is asserted anywhere in the flow.** The caller cannot set them, and the response asserts none.

---

## 4. Why no demo address is published here

The app binds to loopback and is published through a **Cloudflare Quick Tunnel fronted by a Cloudflare Worker**. The Worker reads its origin from Workers KV (`HELIX_ORIGIN`) on every request; `deploy/update-worker-origin.ps1` repoints that key whenever a new tunnel starts.

**The tunnel is not left running between sessions, and its hostname rotates every time `cloudflared` restarts.** So this file publishes no address: a link would land on an offline page. `deploy/README.md` records the same boundary — a Quick Tunnel URL "is suitable for B6/B7 reachability evidence, not for a durable public address or production uptime claim."

The app also **refuses to start** on a non-loopback `HELIX_APP_HOST`. That bind check is enforced in `helix_codex_app/config.py` rather than advised: the process raises on a non-loopback address with `"the app is a self-hosted box, not a public service"`. Loopback binding is a precondition of the deployment, not a convention.

When the origin is down, the front door says so in its own words rather than passing a Cloudflare error page to the visitor. Measured 2026-09-27, before that check existed: with the tunnel stopped and the KV key still present, `/app/healthz` answered **`530`** with Cloudflare's own "Cloudflare Tunnel error" page. The Worker now converts exactly that code — and only that code — into a typed `503`:

| Origin state | Status | Message |
|---|---|---|
| key absent from KV | `503` | `origin not registered` |
| origin not an http(s) URL | `503` | `registered origin is invalid` |
| `fetch` throws | `503` | `registered origin is unreachable` |
| origin answers `530` | `503` | `the registered origin's tunnel is down` |
| origin answers anything else | passed through unchanged | — |

Only `530` is rewritten because it is Cloudflare's own tunnel-failure code and this application never emits it, so the rule cannot mask a genuine application error. Relabelling an app-generated `500` as "offline" would hide a real fault behind a connectivity label. The side benefit is that the public front door no longer discloses its rotating upstream in the visitor's browser.

**To see it live, ask.** Open an issue on this repository, or use the email address in §12, and a session will be started and the address sent to you. A live session is a real governed run against synthetic data — see §5.

---

## 5. What this is not

- **No live paying client.** No revenue has been realised. The demo is a demonstration of the governance path, not a customer result.
- **The data is synthetic by design — a governance decision, not a limitation being hidden.** The demo exists to show that a request can be labelled, gated, recorded, and inspected. A real customer's data could not demonstrate that, because the property being shown is that the labelling is *structural*: `is_sample` and `data_mode` are server-owned, `data_classification` and `confidence_score` are never read from the request, and no caller can talk a synthetic run into claiming to be a verified one. Running this on real data would remove the property being demonstrated.
- **The public surface is not durable infrastructure.** See §4.
- **Production is `NOT_READY`.** Nine production-only gates are red by design; see §8.

---

## 6. What's inside

- Six engines: WFM (Erlang C), RTA, CX Churn Sentinel, B2B Onboarding, Personnel, CRM
- Nine agents (SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY) with content-based routing
- **Two vertical capability packs**: `capabilities/restaurant/` (the reference pattern) and `capabilities/sports_academy/` (first real vertical, built for Scoach Academy Hub)
- **Helix Codex App** (`helix_codex_app/`) — the product layer the public demo runs on: identity, the ops surface, documents, tasks, calendar, attendance, governed memory, a low-code capability loader, and the WFM demo bridge
- **The governed public demo** — Supabase Auth sign-in, a least-privilege `demo` role, the bounded-autonomy gate, route rate limits, and the read-only audit-trail view
- Tenant identity and deny-by-default authorization
- Workflow state machine with approvals, retries, and dead-letter handling
- Read-only boundaries for Zendesk, Salesforce, and Clay
- Evidence-backed account-health diagnosis
- Provenance-bearing command center
- Tenant-isolated governed memory with retention
- Evidence-gated improvement proposals that never self-deploy
- Local adapters with cloud-ready interfaces
- Append-only, hash-chained `audit_events` ledger and exportable governance evidence pack
- Versioned sibling-service event contracts with no cross-repository imports
- SQL-bound tenant-scoped storage and local-first Docker deployment profile

### The internal demonstrations

Account context + support history + enrichment + operational signals → account-health diagnosis → evidence and risk explanation → next-best-action recommendation → cross-role approval preview → outcome recorded in governed memory.

Those call-centre, restaurant, and sports-academy demonstrations are verified against synthetic or consented-historical data only, and they are separate from the public WFM demo described above.

---

## 7. Run it

### Canonical: the API spine (`helix-api`)

The **one** deployable artifact is the governed FastAPI service spine. Identity, RBAC, approvals, the kill switch, metrics, and the audit chain are enforced behind this surface. It runs with bare `uvicorn` semantics and no UI dependency:

```bash
pip install 'helix-codex-os[web]'        # or `pip install -r requirements.txt`
helix-api                                # binds 127.0.0.1:8000 by default
```

Settings come from `HELIX_*` environment variables (see `server/config.py`). `HELIX_HOST=127.0.0.1` and `HELIX_PORT=8000` are the defaults, and the API refuses to boot in `HELIX_PROFILE=production` without the external gate inputs. `helix-api` is the same entry point the Docker profile runs.

### The app, including the demo

`helix_codex_app` is a second console script and the surface the public demo runs on:

```bash
helix-app                                # binds 127.0.0.1:8100 by default
```

`GET /app/auth/demo` is available only with `HELIX_APP_ENABLE_PASSWORDLESS_DEMO=true`, which is a development and test fixture — never enable it on a deployed instance (§1). The Supabase sign-in path needs the Supabase project URL, the publishable key, and the callback URL registered in the dashboard.

### Secondary: the cockpit dashboard (`helix-cockpit`)

The Streamlit dashboard is a **read-only, secondary diagnostic surface**, not the deployable artifact. It is equivalent to `python launch.py`:

```bash
helix-cockpit                            # binds 127.0.0.1:8501
```

### Legacy / do not build on these

- `python launch.py` / `launch.bat` — the Streamlit launcher; superseded by `helix-cockpit`.
- `python desktop.py` — pywebview desktop shell; the packaged wheel does not ship a desktop UI and no console script exposes it.
- `infra/docker/docker-compose.yml` — containerized profile running the same `helix-api` plus the cockpit and an Ollama sidecar; it is a deployment profile, not a separate application surface.

### Windows (source checkout)

1. Install Python 3.12+ from [python.org](https://www.python.org/downloads/windows/).
2. Download the source ZIP and extract it.
3. Open Command Prompt in the extracted folder.
4. Run `setup.bat`.
5. Run `helix-api` (or `python -m server.cli`).

### Linux (source checkout)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
helix-api   # or: python -m server.cli
```

Ollama is optional. Without it, the system runs in deterministic offline mode and reports the limitation clearly.

### Publishing the demo

`deploy/quick-tunnel.ps1` starts the app on `127.0.0.1:8100` and opens a Quick Tunnel; `deploy/update-worker-origin.ps1 -Origin <tunnel-url>` repoints the Worker's KV key. See `deploy/README.md` and `deploy/worker/README.md` for the failure behaviour in §4.

---

## 8. Verified state

Every row was measured. The red rows are in the table because a state table that carries only green rows is not a state table.

| Check | Result | Measured |
|---|---|---|
| Full test suite | **1,897 passed / 0 failed** — 940 in the app chunk, 957 in the parent chunk; 19 deselected as a quarantined UI tier | 2026-09-27 |
| Governance checker (`GOVERNANCE/governance_check.py`) | **PASS** (exit 0) | 2026-09-27 |
| CI lint (`ruff check`, the 17 paths CI names) | **3 errors** — `S311` in `capabilities/sports_academy/fixtures.py`; `I001` and `B007` in `scripts/generate_pdf.py` | 2026-09-27 |
| CI format (`ruff format --check .`, repo-wide) | **Fails** — 346 files would be reformatted, 212 already formatted | 2026-09-27 |
| Release gate `app_pilot` | `CONTROLLED_PILOT_READY` (exit 0) | 2026-09-24 |
| Release gate `controlled_pilot` | `CONTROLLED_PILOT_READY` (exit 0) | 2026-09-24 |
| Release gate `production_candidate` | `PRODUCTION_CANDIDATE` (exit 0) | 2026-09-24 |
| Release gate `production` | `NOT_READY` (exit 1) | 2026-09-24 |

Notes on reading that table:

- **The lint and format rows are red, and they are reported here rather than omitted.** The previous revision of this file claimed "Lint / format / mypy / bandit / pip-audit — Clean (2026-09-24)". Both were re-measured on 2026-09-27 for this revision and neither is clean. The repo-wide `ruff format --check .` step is the CI step, so CI's format job fails independently of any work in progress.
- **Test counts move as the suite grows.** Re-measure; never quote a figure from this file as current. The 1,897 above is the collected total for the two-chunk run recorded in `AGENTS.md` §20.30.1.
- **Candidate status is valid only for the exact commit it was measured against.** The four gate verdicts were last recorded 2026-09-24 and have not been re-run since; the canonical command inventory is in `.github/copilot-instructions.md`.
- **`evidence/` is git-ignored by design** (`evidence/*`, except `evidence/README.md`), per the convention stated in `evidence/README.md` and enforced by `tests/test_c2_preflight_regression.py`, which asserts that `evidence/README.md` is the only tracked path under `evidence/`. The release evidence directories therefore live only on the operator's machine and cannot be inspected from this repository. Treat any count of them as unverifiable from here.

---

## 9. Honest boundary

Helix Prime is a pre-pilot system with a public governed demo. It has no external pilot, no production deployment, and no paying client.

- **No external audit and no certification.** `CONTROLLED_PILOT_READY` is an internal self-approval (`approver: "operator-pilot-consent"`), not a third-party sign-off.
- **Production: `NOT_READY`.** The nine red gates are production-only and red by design, because each needs a signature from a key held outside this repository: `signed_production_evidence`, `certified_data_isolation`, `external_observer_audit`, `production_deployment_architecture`, `disaster_recovery_evidence`, `operational_ownership`, `incident_oncall_ownership`, `security_review`, `legal_privacy_review`.
- No certified data isolation. No signed security review. No legal privacy review.
- No assigned on-call owner; the operator is one person.
- No production deployment. No revenue has been realised.
- Live connectors and external writes are intentionally disabled; the Zendesk, Salesforce, and Clay boundaries are read-only.
- CI builds the API container image and smoke-tests readiness against it (`infra/docker/docker-compose.yml`, `.github/workflows/ci.yml`). No production deployment of that image has occurred.
- The repo-wide format step and the CI lint step are red as measured in §8.
- The public demo's durability is bounded by §4: it is a tunnel, not infrastructure.

---

## 10. Next milestone

A real design-partner pilot. Read-only first, minimum data, explicit consent, measured baseline. No production claim until the production gates pass. The two engineering items already visible in §8 — the repo-wide format step and the three CI lint errors — are prerequisites for a green build, and a green build is a prerequisite for asking anyone to rely on it.

---

## 11. Related work

- [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education) — event-sourced learning engine
- [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio) — local-first AI tutor
- [L&D Command Center](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center) — desktop learning and career workstation
- [Blue Waves](https://github.com/HatemIsmailShalaby1979/Blue-Waves-) — content studio
- [LIVE Support Assistant](https://github.com/HatemIsmailShalaby1979/LIVE-Support-Assistant) — explainable support prototype
- [Full portfolio](https://github.com/HatemIsmailShalaby1979) — how this project fits the wider work

### The 2026 building attempts

- [WFM Forecasting Calculator](https://github.com/HatemIsmailShalaby1979/wfm-forecasting-calculator)
- [RTA Command Center](https://github.com/HatemIsmailShalaby1979/RTA_command_center)
- [CX Sentiment Sentinel](https://github.com/HatemIsmailShalaby1979/cx-sentiment-sentinel)
- [Dynamic Ops Automation Engine](https://github.com/HatemIsmailShalaby1979/Dynamic-Ops-Automation-Engine)

---

## 12. Author

**Hatem Ismail Shalaby** — Operations Architect · AI Systems Engineer · Founder

- GitHub: [HatemIsmailShalaby1979](https://github.com/HatemIsmailShalaby1979)
- LinkedIn: [hatem-shalaby-202902127](https://www.linkedin.com/in/hatem-shalaby-202902127/)
- Email: hatemshalaby2025@gmail.com
- Education: BSc Managerial Sciences (Computer Section), Sadat Academy for Management Sciences; Business Analytics Nanodegree, Udacity

Based in Al Obour City, Al-Qalyubia Governorate, Egypt.

---

## 13. Licence

MIT

<!-- HELIX_ROLE_MATRIX:START -->
## Canonical RoleSpec matrix (generated)

This block is generated from `control_plane/governance.py`. Role IDs,
engine ownership, data classifications, approval limits and KPIs below
are structural facts; surrounding prose must not contradict them.

| RoleSpec ID | Engines | Classifications | Financial limit (USD) | KPIs | Oversight only |
|---|---|---|---:|---|---|
| `sami` | wfm, rta, cx, crm, b2b, personnel, control_plane | public, internal, client_confidential, personnel_sensitive, financial, regulated_high_risk | unlimited (human escalation) | system_health, operational_margin | False |
| `ops_gm` | wfm, rta, cx | internal, client_confidential | 500.00 | sla, service_level, occupancy, adherence, aht | False |
| `compliance_quality_gm` | none | public, internal, client_confidential, personnel_sensitive, financial, regulated_high_risk | 0.00 | quality_score, compliance_drift | True |
| `fraud_revenue_gm` | crm, b2b | internal, client_confidential, financial | 0.00 | leakage, anomaly_delta | False |
| `hr_personnel_gm` | personnel, wfm | internal, personnel_sensitive | 1000.00 | turnover_rate, time_to_hire | False |
| `ld_gm` | wfm | internal, personnel_sensitive | 200.00 | competency_score, time_to_competency | False |
| `sales_gm` | crm, b2b | internal, client_confidential | 2500.00 | pipeline_value, win_rate | False |
| `marketing_gm` | crm | public, internal | 500.00 | cac, lead_volume | False |
| `ict_gm` | control_plane | internal, regulated_high_risk | 5000.00 | engine_latency, model_timeout | False |

### Runtime aliases

| Alias | Canonical role / engine |
|---|---|
| `SAMI` / `sami` | `sami` |
| `SUBY` / `suby` | `ops_gm` |
| `PHILI` / `phili` | `hr_personnel_gm` |
| `WILI` / `wili` | `ld_gm` |
| `NONO` / `nono` | `fraud_revenue_gm` |
| `fraud_gm` (YAML compatibility alias) | `fraud_revenue_gm` |

### Limitations

- `None` financial limit does not mean autonomous unlimited approval; SAMI remains human-escalated.
- `oversight_only=True` means the role proposes/reviews and does not execute an engine.
- Unknown role, engine, classification or alias fails closed.
- This matrix is not a production certification or customer deployment claim.
<!-- HELIX_ROLE_MATRIX:END -->

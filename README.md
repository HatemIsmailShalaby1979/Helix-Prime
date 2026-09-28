<div align="center">

# Helix Prime

**The governed operations core of Helix Codex.**

![Status](https://img.shields.io/badge/status-pre--pilot-blue)
![Tests](https://img.shields.io/badge/tests-1897%20passed%20%2F%200%20failed-2ea043)
![Production](https://img.shields.io/badge/production-NOT__READY-red)
![Licence](https://img.shields.io/badge/licence-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)

</div>

## One-line identity

Helix Prime is the governed, local-first operations core of Helix Codex: the one
place where identity, role-based access, the Erlang C forecasting engine, the CRM,
the workflow engine, and the fail-closed gate all live behind a single enforced
surface — so a decision is gated, recorded, and inspectable before it runs.

> [!NOTE]
> **Operating principle.** No generative model sits in the execution path. On a live floor, a hallucinated action is an SLA breach, not a quirky output — so a deterministic, rules-based gate decides what actually executes, and every decision is recorded before it runs. When the gate holds a submission, it reports the held state; it does not force the run.

The canonical artifact is **`helix-api`**, a governed FastAPI spine where identity,
RBAC, approvals, the kill switch, metrics, and the audit chain are enforced. The
Streamlit cockpit is a secondary, read-only diagnostic surface. Everything runs on
your machine with no cloud dependency.

The authority chain is explicit: `00_CONSTITUTION.md` (authority) →
`docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture + commercial record) →
implementation. On conflict, the earlier link in the chain wins.

## What it does

Six engines — WFM (Erlang C), RTA, CX Churn Sentinel, B2B Onboarding, Personnel,
CRM — routed by nine AI agents (SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA,
TOMY) by content. Beyond the engines:

- Tenant identity and deny-by-default authorization.
- A workflow state machine with approvals, retries, and dead-letter handling.
- Read-only boundaries for Zendesk, Salesforce, and Clay (live connectors and external writes are intentionally disabled).
- Evidence-backed account-health diagnosis.
- Provenance-bearing command center and tenant-isolated governed memory with retention.
- Evidence-gated improvement proposals that never self-deploy.
- An append-only, hash-chained `audit_events` ledger and an exportable governance evidence pack.
- Two vertical capability packs: `capabilities/restaurant/` (reference pattern) and `capabilities/sports_academy/` (first real vertical, built for Scoach Academy Hub).

### The governed public demo

A stranger can drive the governed path end to end. They sign in with GitHub through
Supabase Auth, land in a session holding exactly one permission (`ops.view`), submit
four numbers, and receive an Erlang C staffing answer produced by the same gate,
workflow record, and audit trail the internal pilot uses — then open the recorded
decision chain behind their own run.

The session is the smallest role in the system: domain `helix-demo`, role `demo`,
permission `ops.view` and nothing else. Because it holds no `ops.manage` and no
`ops.approve`, a demo session cannot create, approve, execute, or delete anything by
any route other than the single purpose-built demo endpoint. The `demo` role is
deliberately not in the tenant-blind engine catalog — that is the cross-tenant bug
the least-privilege demo identity exists to prevent.

### The gate — every submission, before execution

`evaluate_gate()` in `control_plane/governance.py`, invoked from
`control_plane/engine.py` at the `validated` state. It is **fail-closed** and
evaluates four things against the acting role's profile: estimated financial cost
against the approval limit; data classification against what the role may read;
confidence score; and engine ownership. It returns `dead_letter`, `awaiting_approval`,
or `executing`. If the gate holds a submission, the demo reports the held state
instead of forcing the run, and the engine is not called.

### Provenance — server-owned, and structural

`is_sample: true` and `data_mode: "simulated_realistic"` are **server-owned**. The
demo bridge injects them on every run; no request can set them. The payload builder
takes exactly four named numbers and no `**kwargs`, so no caller-supplied key can
reach the workflow record. A request carrying any field the demo does not own — in
particular `data_classification` and `confidence_score`, the fields that would let a
synthetic run dress up as a verified one — is **refused with `400`, not silently
stripped**.

### Rate limiting — keyed on the visitor, not on Cloudflare

`helix_codex_app/security/route_limits.py` bounds the routes a stranger can reach
with fixed-window counters keyed on the resolved client address and the route name
together, so one visitor exhausting a ceiling cannot lock another out. The client
address is read from `x-helix-client-ip` (set or deleted by the Worker, never passed
through from `cf-connecting-ip`), because Cloudflare rewrites that header once the
Worker is in the path.

### The audit trail — a reader, not a second log

`GET /app/ops/audit/{correlation_id}` shows the recorded decision chain for one run
and makes no record of its own, so it cannot drift from what the governed path wrote.

## How it fits Helix Codex

Helix Prime is the core, not a member. It owns identity, RBAC, the Erlang C
forecasting core, the CRM, the workflow engine, and the fail-closed gate — the parts
that must be governed in one place.

Every other repository in the portfolio is a separate codebase by design. Helix Prime
enforces versioned sibling-service event contracts with no cross-repository imports:
satellites talk to it through published contracts, not shared source. **Blue Waves**
is the one repository that consumes Prime as a live external client over those
contracts — never embedded, never silent. The four May–June 2026 building attempts
contributed their thinking to Prime's engines (WFM, RTA, CX, B2B) but share no code
with it.

## Architecture

- **`helix-api`** — the governed FastAPI spine. Identity, RBAC, approvals, kill switch, metrics, audit chain enforced here.
- **`control_plane/`** — `governance.py` (the gate, `evaluate_gate`), `engine.py` (workflow state machine), `engine/*.py` (per-engine handlers).
- **`engines/`** — `wfm/adapter.py` (Erlang C), `rta/`, `cx/`, `b2b/`, `personnel/`, `crm/`.
- **`helix_codex_app/`** — the product layer the public demo runs on: identity, ops surface, documents, tasks, calendar, attendance, governed memory, low-code capability loader, WFM demo bridge.
- **`capabilities/`** — `restaurant/`, `sports_academy/` vertical packs.
- **Cockpit** — `helix-cockpit`, a read-only Streamlit diagnostic surface.
- **`audit_events`** — append-only, hash-chained ledger; exportable evidence pack.
- **Deployment** — `infra/docker/docker-compose.yml` runs the same `helix-api` plus the cockpit and an Ollama sidecar; a Cloudflare Quick Tunnel (not left running between sessions) fronts the public demo.

## Production status & test coverage

This section keeps 100% of the transparency from earlier revisions. It is last by design, not because the numbers are small.

| Check | Result | Measured |
|---|---|---|
| Full test suite | **1,897 passed / 0 failed** — 940 in the app chunk, 957 in the parent chunk; 19 deselected as a quarantined UI tier | 2026-09-27 |
| Governance checker (`GOVERNANCE/governance_check.py`) | **PASS** (exit 0) | 2026-09-27 |
| CI lint (`ruff check`, the 17 paths CI names) | **3 errors** — `S311`, `I001`, `B007` | 2026-09-27 |
| CI format (`ruff format --check .`, repo-wide) | **Fails** — 346 files would be reformatted | 2026-09-27 |
| Release gate `production` | `NOT_READY` (exit 1) | 2026-09-24 |

- `CONTROLLED_PILOT_READY` is an internal self-approval (`approver: "operator-pilot-consent"`), not a third-party sign-off.
- Production is `NOT_READY`. Nine production-only gates are red by design, each needing a signature from a key held outside this repository.
- No external audit, no certification, no certified data isolation, no signed security review, no assigned on-call owner. No production deployment. No revenue.
- Test counts move as the suite grows. Re-measure; never quote a figure from this file as current.
- `evidence/` is git-ignored by design; the release evidence directories live only on the operator's machine.

> [!WARNING]
> **What this is not.** No live paying client. The demo data is synthetic by design — a governance decision, not a limitation being hidden: the property being shown is that labelling is structural. The public surface is not durable infrastructure. The repo-wide format step and the CI lint step are red as measured above.

## Run it

### Canonical: the API spine (`helix-api`)

```bash
pip install 'helix-codex-os[web]'        # or `pip install -r requirements.txt`
helix-api                                # binds 127.0.0.1:8000 by default
```

`HELIX_HOST=127.0.0.1` and `HELIX_PORT=8000` are the defaults. The API refuses to
boot in `HELIX_PROFILE=production` without the external gate inputs.

### The app, including the demo

```bash
helix-app                                # binds 127.0.0.1:8100 by default
```

`GET /app/auth/demo` is available only with `HELIX_APP_ENABLE_PASSWORDLESS_DEMO=true`,
a development and test fixture — never enable it on a deployed instance.

### Secondary: the cockpit dashboard (`helix-cockpit`)

```bash
helix-cockpit                            # binds 127.0.0.1:8501
```

Ollama is optional; without it the system runs in deterministic offline mode and reports the limitation clearly.

## Related work

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

## Author

**Hatem Ismail Shalaby** — Operations Architect · AI Systems Engineer · Founder

- GitHub: [HatemIsmailShalaby1979](https://github.com/HatemIsmailShalaby1979)
- LinkedIn: [hatem-shalaby-202902127](https://www.linkedin.com/in/hatem-shalaby-202902127/)
- Email: hatemshalaby2025@gmail.com
- Education: BSc Managerial Sciences (Computer Section), Sadat Academy for Management Sciences; Business Analytics Nanodegree, Udacity

Based in Al Obour City, Al-Qalyubia Governorate, Egypt.

## Licence

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

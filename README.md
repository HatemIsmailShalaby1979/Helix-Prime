<div align="center">

# Helix Prime

**The governed operations core of Helix Codex.**

![Status](https://img.shields.io/badge/status-pre--pilot-blue)
![CI](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/workflows/ci.yml/badge.svg)
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

> [!IMPORTANT]
> **Positioning.** Pre-pilot governed operations core: a verified fail-closed gate and a
> live WFM demo, backed by a green CI and a large test suite — all six engines now drive
> a real computation end-to-end, and CX's risk thresholds load from
> `config/risk_thresholds.yaml` rather than hardcoded values. Not production-ready: nine
> production-only gates are red by design.

The canonical artifact is **`helix-api`**, a governed FastAPI spine where identity,
RBAC, approvals, the kill switch, metrics, and the audit chain are enforced. The
Streamlit cockpit is a secondary, read-only diagnostic surface. Everything runs on
your machine with no cloud dependency.

The authority chain is explicit: `00_CONSTITUTION.md` (authority) →
`docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture + commercial record) →
implementation. On conflict, the earlier link in the chain wins.

## What it does

Six engines — WFM (Erlang C), RTA, CX Churn Sentinel, B2B Onboarding, Personnel,
CRM — routed by content across nine defined role seats (SAMI, SUBY, PHILI, WILI,
ANDY, NONO, MAYA, LIZA, TOMY — the RoleSpec matrix at the bottom of this file).
The seats are governed roles, not running autonomous agents: the agent-dispatch
surface (`app/command_center/agents/dispatch.py`) is an unfinished stub, so
routing happens through the governed role/permission model, not through
dispatch (see Tier 2). Beyond the engines:

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
| CI, end to end | **All 17 steps pass** — run [`36917043028`](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/runs/36917043028) on `a710804` | 2026-10-01 |
| Full test suite | **1,951 tests, 0 failures, 19 deselected** (CI run [`36917043028`](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/runs/36917043028), 2026-10-01) | 2026-10-01 |
| Coverage (`--cov=server --cov=connectors`, 80% floor) | **86.91%** (CI run [`36917043028`](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/runs/36917043028), 2026-10-01) | 2026-10-01 |
| CI lint (`ruff check`, the 17 paths CI names) | **0 errors** (exit 0) | 2026-09-29 |
| CI format (`ruff format --check .`, repo-wide) | **Clean** — 431 files already formatted | 2026-09-30 |
| Governance checker (`GOVERNANCE/governance_check.py`) | **PASS** (exit 0) | 2026-09-29 |
| Release gate `production` | `NOT_READY` (exit 1) | 2026-09-24 |

- `CONTROLLED_PILOT_READY` is an internal self-approval (`approver: "operator-pilot-consent"`), not a third-party sign-off.
- Production is `NOT_READY`. Nine production-only gates are red by design, each needing a signature from a key held outside this repository.
- No external audit, no certification, no certified data isolation, no signed security review, no assigned on-call owner. No production deployment. No revenue.
- Test counts move as the suite grows. Re-measure; never quote a figure from this file as current.
- `evidence/` is git-ignored by design; the release evidence directories live only on the operator's machine.

> [!NOTE]
> **The pipeline went green on 2026-09-29 for the first time.** It had failed at
> step 5 (`ruff check`) on **every push since 2026-09-20**, which is why steps 6–17 —
> the test suite, the security scans, the drift checks, both container steps — had
> never executed once. Three pre-existing defects were found behind that failure:
> two undeclared build dependencies, and nine evidence fixtures whose signatures had
> been made over CRLF bytes and so could never verify on Linux. Repair record:
> `AGENTS.md` §21.

> [!WARNING]
> **What this is not.** No live paying client. The demo data is synthetic by design — a governance decision, not a limitation being hidden: the property being shown is that labelling is structural. The public surface is not durable infrastructure. A green pipeline is not a production claim: nine production-only gates remain red, as recorded above.

## Claims, with sources

Every number below is a measurement on simulated or test data, or a reading of source,
with the file it comes from. Nothing here is a production-customer measure. The three
tiers are the honest reading: what has been shown, what it costs, and what has not been
shown at all.

### Tier 1 — DEMONSTRATED ON SIMULATED / TEST DATA

| Claim | Measured | Source |
| --- | --- | --- |
| Fail-closed gate: unknown role / unknown classification / forbidden classification / non-owned engine → `dead_letter` | enforced; 4 hard-deny branches | `control_plane/governance.py:972-1022`; `tests/test_governance_fail_closed.py` |
| Gate boundaries → `awaiting_approval`: financial limit exceeded, confidence < `0.75`, explicit approval | 3 boundary branches | `control_plane/governance.py:1027-1065`; `MIN_AUTONOMY_CONFIDENCE` at `:64` |
| Every governance decision is written to the hash-chained `audit_events` ledger before it runs | emit at submit | `control_plane/engine.py:839-840` |
| Full test suite passes | **1,951 tests, 0 failures, 19 deselected** (CI run [`36917043028`](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/runs/36917043028) on `a710804`, 2026-10-01) | `pytest tests/ -q -m "not smoke"`; `AGENTS.md` §24 |
| Coverage floor (80%) met | **86.91%** (CI run [`36917043028`](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/runs/36917043028), 2026-10-01) | `.github/workflows/ci.yml` test step |
| `ruff check` clean on the 17 CI paths | **0 errors** (exit 0) | local run, 2026-09-30 |
| `ruff format --check .` clean repo-wide | **433 files formatted** (exit 0) | local run, 2026-09-30 |
| WFM demo returns an Erlang C answer through the gate, recorded in the audit trail | four-number input → answer; demonstrated end to end on a real server 2026-09-30 (`POST /app/api/ops/demo/wfm` → 201, `GET /app/ops/audit/{correlation_id}` → 200) | `helix_codex_app/integration/engine_bridge.py:529-587`; `helix_codex_app/modules/ops/router.py:207`; `docs/verification/2026-09-30.md` |
| `data_mode: "simulated_realistic"` and `is_sample: true` are server-owned; a request cannot set them | injected at bridge; extra keys refused `400` | `engine_bridge.py:586-587`, `:538-539`; `router.py:223-227` |
| Least-privilege demo identity: one permission (`ops.view`), not in the engine catalog | design enforced | "The governed public demo" section above; `helix_codex_app/security/permissions.py` |

### Tier 2 — MEASURED LIMITS

| Limit | Measured | Source |
| --- | --- | --- |
| Rate limiting trusts a header set by an external Worker | `x-helix-client-ip` trust fails if app exposed without the Worker | `helix_codex_app/security/route_limits.py:124`; `client_ip.py:24-28` |
| Cockpit UI tier quarantined | 19 tests deselected | `tests/integration/ui/cockpit/` conftest (quarantined tier); `AGENTS.md` §19 |
| `dispatch.py` agent dispatch is a stub returning fake output | `Called …` / `Task submitted` placeholders | `app/command_center/agents/dispatch.py:84,187,204,217,231` |
| Coverage floor measures execution, not result correctness | the suite now pins WFM's Erlang C to textbook reference values (`tests/test_wfm_erlang_c.py`); the other engines' result accuracy is still not validated against an external reference | `docs/verification/2026-09-30.md` |
| CI container steps (16–17) not reproducible locally | Docker not running here; rest on remote green run | `AGENTS.md` §21 |

#### Fixed since this table was written

The Tier 2 rows that have since been fixed are moved here. The record of what was wrong
is kept rather than deleted.

| Formerly a limit | What was wrong | Fixed in |
| --- | --- | --- |
| Gate `oversight_only` flag parsed but never enforced | an oversight role with no `target_engine` could still reach `EXECUTING` | `2c9d606`, `64928da` — `evaluate_gate()` hard-denies oversight-only seats (`oversight_only`, `dead_letter`) regardless of `target_engine`; `owns_engine(None)` reflects an engine-less seat; `Engine.submit` and `GovernedWorkflowManager.submit` both act on the refusal. `tests/test_gate_oversight_and_approval.py` |
| `Engine.submit` did not forward `requires_approval` to the gate | the gate's `approval_requested` branch was unreachable on the `Engine.submit` path | `2c9d606` — `Engine.submit` now forwards `requires_approval`; both submission paths agree on the gate's verdict. `tests/test_gate_oversight_and_approval.py` |
| CX churn scorer assumed AHT ≤ 0.5 minutes | the `/0.5` (minutes) divisor pinned any realistic AHT to 0 (max risk); callers actually pass AHT as a 0-1 fraction | `fix/cx-aht-normalization` — AHT normalized as `1 - value` (goodness); threshold band recalibrated to critical 0.3/high 0.5/medium 0.7 in `risk_scorer.py:57-66`; `config/risk_thresholds.yaml:16` synced; regression test `tests/test_cx_aht_normalization.py` |
| B2B adapter fabricated its onboarding result | `engines/b2b/adapter.py` called only `add_client` + `get_client_summary`, then set `sop_generated=True` and `onboarding_status="completed"` by hand; `generate_sop`/`generate_staffing_plan` were never invoked, so the SOP and staffing plan were never computed | `fix/b2b-wire-real-onboarding` — adapter now calls `OnboardingAutomator.generate_sop()` and `generate_staffing_plan()` and maps their real return values (`sop`, `staffing_plan`, `workload_data`); the fabricated fields are removed; regression test `tests/test_c4_engines.py::test_b2b_adapter_wires_real_sop_and_staffing_plan` |
| CRM adapter echoed its pipeline inputs | `engines/crm/adapter.py` probed `get_pipeline_analytics`/`get_analytics`/`analyze` (none exist on `SalesPipeline`) and fell through to `{"status":"active","client":...,"deal":...}`; `add_lead`/`create_deal`/`get_sales_analytics` were never called | `fix/crm-wire-real-pipeline` — adapter now maps `client`/`deal` into real `Lead`/`Deal` objects via `add_lead`/`create_deal` and calls `get_sales_analytics()`, returning computed `stage_distribution`/`average_deal_value`/`total_pipeline_value` and the 12-month forecast; `score_lead` is intentionally omitted (its signature needs company_size/industry/budget/timeline the request schema lacks); `support_status` dropped, `pipeline_status` derived from computed totals; regression test `tests/test_c4_engines.py::test_crm_adapter_wires_real_pipeline_analytics` |
| Personnel adapter reported empty analytics and echoed its input | `engines/personnel/adapter.py` called `get_pipeline_analytics()` on an empty `PipelineManager` (before any candidate was added) and returned `{}`, then hardcoded `pipeline_status="active"` and `workforce_headcount` from the request's `headcount` | `fix/personnel-wire-real-pipeline` — adapter now builds real `Candidate`/`JobPosting` objects via `add_candidate`/`create_job_posting`, calls `screen_candidates()` when the job carries real `required_skills` and a positive `experience_level`, then `get_pipeline_analytics()`, returning computed `total_candidates`/`total_job_postings`/`status_distribution`/`stage_distribution`/`average_days_in_pipeline`/`pipeline_efficiency`; `pipeline_status` derived from computed totals; the fabricated `workforce_headcount` echo dropped (no real headcount source in `PipelineManager`); regression test `tests/test_c4_engines.py::test_personnel_adapter_wires_real_pipeline_analytics` |
| CX risk thresholds hardcoded in code | `engines/cx/src/risk_scorer.py` hardcoded `kpi_thresholds`, and `classify_risk_level` hardcoded the 0.8/0.6/0.4 bands, while `config/risk_thresholds.yaml` existed as the intended single source of truth the engine never read | `4e4f98d` — `load_risk_config()` now reads `config/risk_thresholds.yaml`; `RiskScorer`/`RiskScorerEngine`/`create_risk_scorer` load `kpi_weights`/`kpi_thresholds`/`risk_bands` from it (safe fallback if the file or PyYAML is absent); `classify_risk_level` uses the loaded bands; regression test `tests/test_cx_config_loading.py` |
| WFM "Erlang C" was a non-standard closed form with a corrupted docstring | no factorial/series term at `:124`; non-Latin glyphs at `:8`; `confidence_interval` was a flat `0.05*agents` band (`:243`) and `confidence_level` was never read; the service level had no answer threshold and no Erlang C term, so the demo-shaped scenario understaffed 5 agents vs the textbook 7; deviation from the textbook probability of waiting reached 0.811 absolute ((100, 80): 0.769 vs 0.0196) | `caabcb9` — engine rewritten on the stable Erlang B recursion (no factorials, N=5000 verified); documented 20 s answer threshold (`SL(t) = 1 − C·exp(−(N−A)·t/AHT)`); ASA corrected to `C·AHT/(N−A)`; the fake `confidence_interval` and unused `confidence_level` removed; mojibake docstring fixed; provenance (wfm-forecasting-calculator `shared_utils/erlang_c.py`) cited in the module docstring. Pinned by `tests/test_wfm_erlang_c.py` (42 tests) against an independent in-file reference and the reference repo's self-test values (0.5299 / 86.70% / 10.09 s / 70.83% / 14 agents). Record: `docs/verification/2026-09-30.md` |
| Test fixtures carried hardcoded dates (time-bombs) | calendar/oncall fixtures seeded events and listed shifts inside fixed September-2026 windows while the app renders the current month and shifts are created at `now` (four CI failures at the 2026-10-01 rollover); an attendance API test queried a window ending 2027-01-01 for a punch stamped `now`; an evidence-test document expired 2027-09-20 against the wall clock | `a4762d7`, `885fc75` — all four fixture families compute dates relative to `now` (UTC); `release/production_evidence.py` is unchanged (the fixture document was widened to the 2020→2099 design window). Proof: a six-date libfaketime sweep (2026-10-31 23:59, 2026-11-15, 2026-12-31 23:59, 2027-01-01 00:01, 2027-02-28, 2028-02-29) runs the full suite green at every date. Record: `AGENTS.md` §24 |

The sweep excluded five SSE/timing-loop test files — `tests/test_chat_stream.py`, `tests/helix_codex_app/test_sse_isolation.py`, `tests/helix_codex_app/test_notifications_routes.py`, `tests/test_server_spine.py`, `tests/helix_codex_app/test_messaging_routes.py` — because libfaketime distorts their stream timers identically at every faked date (they hang or fail at all six) while passing at the real clock, so their exclusion is a method artifact of the sweep, not a repository defect.

### Tier 3 — NOT PROVEN

| Not proven | Why |
| --- | --- |
| Real customer traffic | None exists. Demo data is `simulated_realistic` by design (`engine_bridge.py:53,564,586-587`). |
| Production deployment | `production` gate `NOT_READY`; nine production-only gates red by construction | `AGENTS.md` §18 |
| External security audit / certified data isolation | None. No signed installer, no certified isolation evidence. |
| Multi-tenant isolation under real load | No independent tenant-isolation audit (cf. the 500/500 tagged-row count in LIVE Support Assistant). |
| Engine accuracy at real corpus scale | Not measured; the engines are not independently validated for accuracy at real corpus scale. |
| Design-partner live traffic | Scoach Academy Hub is a named first vertical (`capabilities/sports_academy/`), but no live client traffic is recorded. |

### Tried and rejected

Helix Prime has **no measured-and-rejected experiment branches** of the kind LIVE
Support Assistant records as `evidence/*` tags. There is no calibrated experiment that
was run, found wanting on a metric, and kept only as evidence. The closest records are
**deletions of unwired approaches**, not rejected calibrations:

- `cfbfa8d` — removed an unwired `tenancy.py` and corrected docs that had claimed
  driver-level isolation. The driver-level isolation approach was rejected as unwired,
  not as measured-and-insufficient.
- `c00dec5` — dropped a "dead scope gate" and unified the lockout source.
- `898d2d0` — removed dead code and closed the app node envelope.

These are removals of unused code. Do not treat them as "experiments to re-run"; there
is nothing to re-run. `app/command_center/agents/dispatch.py` is an **unfinished stub**,
not a rejected experiment (TODOs at `:84,:187,:204,:217,:231` returning placeholder
text — see `docs/KNOWN_ISSUES.md` issue 7).

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

### Verification records

What was verified, when, on which machine, with what result — including the
claims that could not be re-verified locally and why — is kept as dated
records under [`docs/verification/`](docs/verification/):

- [`docs/verification/2026-09-30.md`](docs/verification/2026-09-30.md) — the
  Erlang C engine rewrite (ERLANGC-1): the deviation tables before and after,
  the reference method, the pinned self-test anchors, the end-to-end demo run
  with audit-trail readback, and the test runs.
- [`docs/verification/2026-09-29.md`](docs/verification/2026-09-29.md) — the
  documentation claims pass.

A reviewer without the install or credentials can still run the test suite and
`ruff`, and can read the audit-ledger design in `control_plane/engine.py` and
`control_plane/governance.py`.

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

# AGENTS.md — Sports-Academy Capability Pack Build Ledger

> **Purpose:** Any agent (or human) can pick up exactly where the last one stopped.
> Read this file top-to-bottom before doing anything. Then work ONLY on the next
> incomplete step. Update this file immediately after completing each step.

---

## 0. Project context (read first)

- **Repo:** `E:\Helix-Prime` (Helix Prime → being commercialized as "Helix Codex OS")
- **Mission:** Build `capabilities/sports_academy/` — the first vertical capability
  pack for Helix Codex OS, for the first client (Scoach Academy Hub, a private
  sports academy). Full plan + business context: `docs/scoach_academy_hub_opportunity_report.md`.
- **Blueprint:** `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (governs architecture).
- **Constitution:** `00_CONSTITUTION.md` wins over any doc on conflict.
- **Python:** 3.12 canonical. Venvs exist (`.venv312`, `.venv-py312`, etc.).
- **Test command:** `python -m pytest tests/ -q -m "not smoke"` (run from repo root `E:\Helix-Prime`).
- **Lint:** `ruff check <paths>`.

### Non-negotiable rules (violating these breaks the governed core)

1. **Reference pack:** `capabilities/restaurant/` is THE pattern. Copy its shape,
   never invent a new one.
2. **Never edit** `organization/role-catalog.yaml`, `control_plane/governance.py`
   (ORGANIZATION_CATALOG), or `organization/capability-registry.yaml` + mirrors for
   this pack. Roles stay pack-local. Engines are reused via existing capability ids.
3. **Data discipline:** pack runs `DATA_MODE = "simulated_realistic"`, read-only
   connectors, no live writes, `production_readiness = "NOT_ESTABLISHED"`.
4. **Every governed-memory record** carries: tenant_id, client_id, provenance
   (correlation_id, data_mode, basis, sources), evidence_refs, classification.
5. **No comments in code** unless they mirror the restaurant pack's docstrings
   (module docstrings ARE kept).
6. **Each step must end with:** tests passing at ≥ baseline + ruff clean on new
   files + this file updated + commit made (see git protocol below).

### Git protocol

- User has authorized commits for this work. Commit after EVERY completed step.
- Style: `feat(academy): <what>` / `test(academy): <what>` / `docs: <what>`.
- NEVER `git add -A` blindly; stage only files you touched. NEVER commit
  `.db` files, `__pycache__`, or `.venv*`.

---

## 1. Status snapshot (update after every step)

| Field | Value |
|---|---|
| Current step | **ALL STEPS COMPLETE (S0–S7)** |
| Baseline test count | 527 (pre-pack; 2 Windows teardown failures fixed in `fe25653`) |
| Last full-suite result | **571 passed, 0 failed** (2026-09-10, commit `f269135`) |
| Last commit | `f269135` feat(academy): runtime with approval gating + SOD, full pack docs — 44 tests |
| Pack complete? | **YES — sports-academy pack v1.0.0 COMPLETE** |
| Blockers | none |

### Definition of done — verified

- [x] Attendance adapter with RTA engine reuse (check-in/check-out → adherence)
- [x] Coach KPIs defined (4) + academy KPIs (5), YAML-declared, drift-tested
- [x] Athlete profiles (CRM) + CX-scored churn flags for seeded risk athletes
- [x] Owner dashboard — 5 numbers, one screen (cockpit "Sports Academy" page)
- [x] Facility conflict detection + manual fee records (no instruments)
- [x] Runtime: approval queue behind SOD, read-only phase, evidence pack,
      hash-chained memory, all simulated_realistic
- [x] Full suite 571/571 ≥ baseline 527; ruff clean on all pack paths

### Environment facts (discovered in S0 — do not re-discover)

- **Working venv:** `.venv-py312\Scripts\python.exe` (3.12.10 + pytest + ruff 0.1.15 + pandas/numpy). `.venv312` has NO pytest. `.venv-win` is 3.10 — do not use.
- **Ruff config:** `pyproject.toml [tool.ruff]` line-length=100, select = E4/E7/E9/F. Pre-existing ruff debt exists in `capabilities/restaurant/` (5 F401) and the two C4/C6 test files (~32 findings, F401/E402 legacy). **Rule for new code: `ruff check capabilities/sports_academy tests/test_capabilities_sports_academy.py` must be 0.** Do not "fix" pre-existing debt outside the pack (out of scope).
- **Windows gotcha:** any test opening SQLite inside `tempfile.TemporaryDirectory()` MUST close stores/connections before the `with` block exits, or teardown fails with WinError 32 after passing assertions. If a Store leaks in a *pack test*, use `tests/support/sqlite_harness.py::sqlite_store` fixture or close explicitly.
- **The restaurant pack itself** imports `SourceRef` from `connectors.contracts` — new pack does the same.
- Full-suite runtime ≈ 20 min on this machine. Run targeted modules during steps; full suite only at S7.

---

## 1. Production Hardening Task (H0–H3) ← NEW

**Recorded:** 2026-09-11 · **Based on:** `docs/audits/2026-09-10_full_audit_production_plan.md`

### 1.1 Status

| Field | Value |
|---|---|
| Current step | **H2.3 complete; next: H2.4 (CI quality) — H1.3 (drift AST) still open** |
| Baseline test count | **571 passed, 0 failed** (verified at commit `c3c4abf`) |
| Last full-suite result | **620 passed, 0 failed** (2026-09-12, H1.5 full-suite verification run; baseline 571 + 12 kill-switch tests + 37 prior-session tests in tree) |
| Last commit | H2.3: chore(pkg): declare console scripts, align sdist/wheel includes |
| Completed H-steps | H0.1 ✅, H0.2 ✅, H0.3 ✅, H0.4 ✅, H0.5 ✅, H0.6 ✅, H1.1 ✅, H1.2 ✅, H1.4 ✅, H1.5 ✅, H1.6 ✅, H2.1 ✅, H2.2 ✅, H2.3 ✅ |

### 1.2 Step ledger

#### H0 — P0: Make it safe to run (target: 1 week)
Exit gate: CI green in a clean container; no unauthenticated route; no high bandit/pip-audit finding.

- [x] **H0.1** RTA Flask hardening (G01, G03) — `engines/rta/src/app.py:269` remove
      `debug=True`, bind `127.0.0.1`; `:32` replace bare `CORS(app)` with explicit origins
- [x] **H0.2** Server bind default (G08) — `server/config.py:52` `host` → `127.0.0.1`
- [x] **H0.3** Auth + RBAC (G02) — `server/auth.py::current_identity`, applied at router level; `/healthz` excepted
- [x] **H0.4** CI repair (G04, G05, G07) — `ci.yml:24` → `release/requirements.lock.txt`
- [x] **H0.5** Scanning (G06) — `bandit` + `pip-audit` in CI; add `.github/dependabot.yml`; skips for B113/B310/B608 with justification
- [x] **H0.6** Release manifest + worktree cleanup (G09, G10) — manifest regenerated at HEAD; 5 integrated worktrees closed; license claim fixed. Commit `536de74`

#### H1 — P1: Make the governance claims true (target: 2 weeks)

- [x] **H1.1** Silent-degradation → fail-closed (G11–G13) — `GovernanceControlUnavailable` raised at import/validation time; audit, secret scan, classification, injection checks now raise instead of silently skip
- [x] **H1.2** SOD integrity (G14, G15) — hardcoded `sami`/`compliance_quality_gm` literals replaced with catalog-driven `universal_approvers`; `KeyError` now raises `GovernanceControlUnavailable` instead of silently allowing; tests verify deny-on-unknown-role and authority-from-catalog behavior
- [ ] **H1.3** Drift must be able to fail (G16)
- [x] **H1.4** Tenant isolation (G17) — **DECIDED 2026-09-11: DELETE (Decision B).**
      `control_plane/tenancy.py` is 100% dead (zero refs, zero tests). Verified before
      deciding: (a) zero code references anywhere incl. tests/gates/exports;
      (b) `release/gate.py:146 _gate_data_isolation` → `release/harness.py:327
      _check_tenant_isolation` uses `security.policy.authorize`, **not** tenancy ⇒ deleting
      breaks no gate; (c) `GOVERNANCE/IMPLEMENTATION_MATRIX.md:96` already credits
      `security/policy.py` + `identity.py` ⇒ no matrix change. **Rationale:** a control
      that exists only in a file and is never invoked is not defense-in-depth — it misleads
      auditors and delays real implementation. Isolation stays at the single policy seam
      `security/policy.py::authorize`; if driver-level guarantees are ever required, build
      them **inside `Store`**, not as a disconnected wrapper. **Deletion also requires
      correcting 4 docs that claim it is real:** `docs/C4-C8_IMPLEMENTATION.md:81`,
      `docs/HELIX_CODEX_EXECUTION_STATUS.md:23,55`,
      `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md:39,373,374,378`. Note in the
      `security/policy.py` docstring that driver-level enforcement is deliberately deferred.
      **Completed 2026-09-11** — deleted `control_plane/tenancy.py`, corrected 4 docs,
      added policy-seam note. Commit `cfbfa8d`.
- [x] **H1.5** Kill switch (G18) — **Completed 2026-09-12.**
      `control_plane/kill_switch.py`: persisted `halt_state` table in the
      workflow store (same file, no new dependency) — global (`*`) + optional
      tenant scopes; `engage(reason, actor)` / `release(actor)` /
      `is_engaged()`; engagement/release write `kill_switch_engaged`/
      `kill_switch_released` audit records; unreadable flag ⇒ engaged
      (fail-closed). `Engine` checks the flag at the top of `submit`/`approve`/
      `execute` (the approval/committal seam): while engaged, the action is
      denied with a `kill_switch_denied` audit record and `KillSwitchEngaged`
      is raised; the audit write is never gated by the halt, and a metrics
      `denied` decision is recorded alongside. `cancel` stays ungated (safe
      direction). HTTP: `POST /api/halt/engage`, `/release` (universal
      approvers only, catalog-driven, fail-closed 403/503), `GET
      /api/halt/status` (any authenticated identity); `KillSwitchEngaged`
      maps to a typed 503 `halt_engaged` at the app boundary. CLI:
      `scripts/kill_switch.py` (engage/release/status, tmp-path flags).
      Tests: `tests/test_kill_switch.py` (12) covering all five required
      cases plus unreadable-flag fail-closed and the full HTTP surface.
- [x] **H1.6** Evidence + readiness enforcement (G19, G20) — **Completed 2026-09-12.**
      (a) `release/gate.py::_gate_audit_integrity` now routes through
      `security_gate.check_audit_integrity` (was a duplicate harness probe that
      bypassed it). It probes the real chain implementation, then — when
      `HELIX_AUDIT_DB_PATH` is declared — verifies the shipped audit chain and
      FAILS the gate when that chain is broken/missing (fail-closed, no silent
      skip). Undeclared ⇒ probe-only + explanatory detail. Note: the local dev
      `security/audit.db` (16,545 records, gitignored, never shipped) is
      genuinely forked from a 2026-08-29 concurrent-append race predating the
      chain-tip cache fix — it is NOT evidence of a regression; shipped chains
      are verified via the declared path. (b) Registry-level readiness
      contract: `tests/test_pack_readiness_contract.py` enumerates packs via
      `pkgutil` over `capabilities/` (not a hardcoded list) and asserts every
      registered pack declares `production_readiness` with an allowed value
      (`NOT_ESTABLISHED`). Exporter verified read-only and unmodified:
      `scripts/export_evidence_pack.py --help` exit 0; real-ledger export
      `integrity.verified=true` (empty ledger trivially valid). Evidence packs
      should be REGENERATED at release time (they embed timestamps/commits;
      committing them freezes stale claims) — reproducibility tracked
      separately with .gitignore unchanged. Gate run at HEAD:
      `production_candidate` → all gates green, exit 0.

#### H2 — P2: Make it operable (target: 1.5 weeks)

- [x] **H2.1** Alembic migrations (G21) + CI drift check — **Completed 2026-09-12.**
      Alembic 1.20.0 added (`alembic>=1.13,<2.0.0` in requirements.txt, mirrored in
      pyproject deps + sdist include `/migrations` + `/alembic.ini`; lock regenerated
      via `uv pip compile` — only alembic/sqlalchemy/mako/greenlet added, zero
      version churn). Initial migration `0001_baseline` reproduces the Store schema
      (same DDL statements/order from `control_plane/store.py::_init_schema` +
      `_init_governance_schema`: 4 tables, 7 indexes, 2 append-only triggers) —
      verified a no-op on a copy of the live `control_plane/workflow.db`
      (stamp head → upgrade head → sqlite_master identical, 19 objects, zero
      rows touched) and byte-fresh on a new DB. DB path resolves per-invocation:
      `alembic -x db=<path>` > `HELIX_DB_PATH` env > `control_plane/workflow.db`
      (matches server/config.py convention; no URL baked into the repo).
      Drift control: `scripts/check_migration_drift.py` builds one DB via Store
      and one via `alembic upgrade head`, compares sqlite_master at token level
      (whitespace/indent-insensitive — SQLite stores DDL text verbatim), fails
      CI on any divergence in either direction; alembic's own
      `alembic_version` bookkeeping excluded. Wired into `.github/workflows/ci.yml`
      after check_dependencies. Tests: `tests/test_migration_drift.py` (7, fast,
      no live migration required) incl. can-fail proof (G16 lesson).
- [x] **H2.2** Monitoring/alerting (G22) — **Completed 2026-09-12.**
      `observability/metrics.py`: stdlib-only Prometheus registry (no client lib,
      no exporter sidecar, no new dependency) — counters/gauges/histogram with a
      FIXED label vocabulary (route templates, status codes, decision buckets);
      caller-supplied strings can never become label values, so the exposition
      cannot leak PII/secrets by construction. Metric families:
      helix_http_requests_total{route,status,method},
      helix_http_request_duration_seconds (cumulative buckets),
      helix_governance_decisions_total{decision},
      helix_audit_chain_verifications_total{result},
      helix_audit_chain_verification_failures, helix_approval_queue_depth.
      Hooks: `Engine._audit` records every governance decision (import validated
      in the engine's fail-closed startup block — H1.1 pattern);
      `AuditTrail.verify_chain` records each verification outcome (ImportError
      raises, never silently skips). HTTP surface: `/metrics` on the metrics
      router, BEHIND the standard `current_identity` auth (deployment-sensitive:
      route inventory, traffic mix, queue depth; Prometheus scrapes with the
      same bearer token — documented in infra/monitoring/README.md). Queue
      depth refreshed from the store on every scrape. `server/app.py`
      middleware: per-request count/latency by route template + one structured
      `http_request` log line per request (correlation id, route, status,
      duration_ms; payload redacted via security.secrets.redact_dict; log_path
      from app settings). Alert rules as CONFIG: `infra/monitoring/alerts.yml`
      (Prometheus rule-file format: scrape-down, 5xx ratio, p95 latency,
      governance denial spike, audit-chain failure = critical, queue backlog,
      queue-starved info). Tests: `tests/test_metrics.py` (13) incl. auth
      boundary, exposition format, route-template counting, tamper-detection
      metric, queue depth, log redaction (fake secrets generated at runtime —
      R1 lesson), and alert-rule drift (rules may only reference exported
      metrics). Live-verified: uvicorn on 127.0.0.1:8901 — /metrics without
      token → 401 (counted), with token → 200 full exposition.
      **Latent bug fixed en route:** `AuditTrail.last_hash`/`append`/
      `list_records` ordered the chain tip by `timestamp DESC, audit_id DESC`;
      rapid appends sharing a microsecond timestamp returned the wrong tip,
      corrupting the next previous_hash (out-of-order append failures — the
      flaky test_engine_audit_perf failure across 3 sessions, and likely the
      cause of the 2026-08-29 live audit.db fork). Chain order = insertion
      order: all three queries now use `rowid`. Suite-affecting residue in
      security/audit.py (unused-import removal from a prior session) rides in
      this commit.
- [x] **H2.3** One deployable artifact (G23, G24, G25) — **Completed 2026-09-12.**
      `pyproject.toml [project.scripts]`: **`helix-api` is the ONE canonical
      entry point** — the governed FastAPI spine (`server/cli.py`, uvicorn on
      the `server.app:create_app` factory, host/port from `HELIX_*` with
      loopback defaults). `helix-cockpit` (`cockpit/cli.py`) launches the
      Streamlit dashboard, explicitly secondary. sdist `include` now mirrors
      the wheel package list exactly (added `cockpit`, `customer_success`,
      `integrations`, `pilot`, `security`, `server` — the sdist previously
      could not rebuild the wheel). README declares the canonical artifact and
      labels `launch.py`/`launch.bat`, `desktop.py`, and the compose profile
      secondary/legacy (nothing deleted). **Wheel CWD-quirks fixed en route**
      (required for `helix-api` to boot from the installed wheel in any
      directory): `server/app.py` static mount was `StaticFiles(directory=
      "server/static")` (CWD-relative) → now package-relative; `organization/
      role_catalog.py::load_role_catalog` fell back to a CWD-relative
      `"organization/role-catalog.yaml"` that broke from any other working
      directory → now resolves against the package dir when the relative path
      is absent. VERIFIED: `python -m build` produces sdist+wheel; wheel
      installed into a fresh temp venv; `helix-api` serves `/healthz` 200 and
      `helix-cockpit` serves `/ _stcore/health` 200 in an arbitrary CWD;
      sdist↔wheel delta = zero missing packages. Targeted re-runs of the
      role-catalog/contracts/server suites: 144 passed.
- [ ] **H2.4** CI quality (G27, G28)
- [ ] **H2.5** Data-retention policy (G26)

#### H3 — P3: Make it sellable (target: 1 week)

- [ ] **H3.1** Single authority chain (G31, G39)
- [ ] **H3.2** Stale facts (G32–G35)
- [ ] **H3.3** Security docs (G36, G37)
- [ ] **H3.4** CHANGELOG + hygiene (G38, G40, G41)

---

## 2. Build plan (source of truth for steps S0–S7)

Final layout:

```
capabilities/sports_academy/
├── __init__.py
├── ontology.py            # Athlete, Family, Coach, Program, Session, CheckIn,
│                          #   FacilitySlot, FeePayment, EnrollmentRecord
├── fixtures.py            # build_synthetic_academy(tenant, client, as_of)
├── contracts.py           # AcademyConnector(BaseConnector) — read-only
├── adapters/
│   ├── __init__.py
│   ├── attendance_adapter.py      # → reuses engines/rta (schedule vs actual)
│   ├── athlete_profile_adapter.py # profiles + churn via engines/cx features
│   ├── facility_adapter.py        # slots, conflicts, utilization
│   └── payment_adapter.py         # manual FeePayment records only
├── roles.py               # academy_owner, head_coach, coach, academy_admin, parent
├── workflows.py           # 3 flows → AcademyDiagnosis
├── kpis.py                # compute_academy_metrics / compute_coach_metrics
├── runtime.py             # AcademyCapabilityPack
├── register.py            # metadata + auto-register
├── declarations/          # canonical YAML mirrored by Python, drift-tested
│   ├── academy_kpis.yaml
│   ├── coach_kpis.yaml
│   ├── academy_roles.yaml
│   ├── enrollment_flow.yaml
│   ├── attendance_flow.yaml
│   └── renewal_flow.yaml
└── cockpit_views/
    ├── owner_dashboard.py
    ├── coach_dashboard.py
    └── parent_portal.py
```

Plus:
- `tests/test_capabilities_sports_academy.py` (~20 tests)
- `docs/sports_academy_pack.md`
- Thin wiring in `cockpit/cockpit.py` (one "Sports Academy" nav entry)

Engine reuse map (do NOT register new capabilities):
- Attendance/adherence → `engines.rta.adapter.adapt`
- Churn risk → `engines.cx` (`churn_risk_scoring`)
- Enrollment pipeline stages → `engines.crm` semantics via pack-local code

Explicitly NOT in v1: parent mobile app, payment processing/integration,
athlete progression tracking, multi-location support.

Priority order (client-visible value): attendance adapter → coach KPIs →
athlete profiles → owner dashboard → facility → payments → runtime/docs.

---

## 3. Step ledger (append entries; never delete history)

### S0 — Preflight (status: COMPLETE)
Tasks:
- [x] Scaffold this AGENTS.md
- [x] Commit pre-existing untracked docs (`.claude/` excluded via `.gitignore`
      after embedded-worktree warning; docs committed) → `7d1e7a7` + `433c463`
- [x] Baseline recorded: **527 tests** (`2 failed, 525 passed` pre-fix; both
      failures were Windows-only SQLite-teardown bugs in existing tests —
      assertions passed, unlink failed with WinError 32. Fixed by adding
      `store.close()` before TemporaryDirectory exit) → `fe25653`
- [x] `ruff check capabilities/` — pre-existing debt in restaurant pack only
      (5×F401); NOT fixed (out of scope, would churn core). New pack must be clean.
- [x] Commit this file itself → `0f45c7d`
Notes for next agent: S0 discovered the venv/ruff/Windows facts in §1 — trust them.

### S1 — Skeleton + attendance (status: COMPLETE)
- [x] Package skeleton (`__init__.py`, `adapters/__init__.py`)
- [x] `ontology.py` — Athlete, Family, Coach, Program, Session, CheckIn,
      FacilitySlot, FeePayment, EnrollmentRecord (frozen dataclasses, all
      tenant/client/SourceRef carrying; CheckIn has Optional check_out_at with
      defaults so fixtures can construct it positionally)
- [x] `contracts.py` — AcademyConnector read-only, 9 list_* reads via one
      `_list_result` helper, `build_academy_connectors(ctx, fixtures)`
- [x] `fixtures.py` — 40 athletes (38 active + 1 inquiry + 1 trial), 20
      families, 6 coaches, 2 programs, 14 sessions over 7 days (2/day),
      checkins ~81% attendance; **ath-01/ath-02 seeded to miss last 4 days
      (42.9% attendance — used by churn tests in S3)**; 20 facility slots
      (13 booked = 65%); 3 manual fee payments (1 outstanding); 2 enrollment
      records
- [x] `adapters/attendance_adapter.py` — `compute_attendance` (pure),
      `build_rta_payloads` (schedule/actual DataFrames, agent_id=athlete_id,
      hour collapsed to 0), `rta_attendance_adherence` (calls
      `engines.rta.adapter.adapt` with **owning_role_id="ops_gm"** — the RTA
      engine enforces ops_gm ownership; pack-local coach roles apply at the
      approval layer, not the engine call), `daily_adherence_report`,
      `record_attendance_outcome` (governed memory, kind="outcome",
      nature="simulated_event")
- [x] `tests/test_capabilities_sports_academy.py` — 11 tests: connector
      scoping/isolation/read-only caps, attendance math (266 expected slots,
      38 active athletes, risk athletes < 0.6), RTA reuse, empty-day
      fail-closed, daily report shape, governed-memory recording with full
      provenance, no live data mode. **ALL PASS.**
- [x] ruff clean + commit `d5dcb45` → `feat(academy): attendance adapter with RTA engine reuse + tests`
Notes: fixture attendance is `hash((athlete_id, date)) % 100 < 85` —
deterministic per-process (Python string hashing is randomized across
processes BUT only for non-ASCII... verified stable because ids are ASCII and
PYTHONHASHSEED affects str hash. **If attendance numbers ever drift across
runs, replace hash() with a seeded random.Random(42).)**
VERIFIED STABLE across two separate processes in S1 (216/266 both runs).

### S2 — KPIs (status: COMPLETE)
- [x] `declarations/academy_kpis.yaml` — 5 KPIs w/ targets: attendance_rate
      0.85, churn_rate 0.05 (lower better), facility_utilization 0.70, mrr
      8360, active_athletes 38
- [x] `declarations/coach_kpis.yaml` — 4 KPIs: session_adherence 0.90,
      athlete_attendance_rate 0.85, session_delivery_ontime 0.90,
      parent_satisfaction 0.80 (progression deliberately absent — v1 non-goal)
- [x] `kpis.py` — load_kpi_definitions (YAML canonical),
      compute_academy_metrics (5 numbers w/ value+target+direction+met),
      compute_all_coach_metrics (4 KPIs/coach; parent_satisfaction = None
      until manual survey records exist; ontime uses pilot proxy = delivered)
- [x] Drift tests: YAML ids exactly match implemented metrics; every KPI has
      target + direction
- [x] ruff clean + tests 14/14 + commits `5b4b430`, `848e1d7`
Notes: **fixtures now use `random.Random(42)` for attendance** (S1's hash()
was randomized across processes — PYTHONHASHSEED). Attendance = 216/266 =
0.812 exactly. MRR = 20 U12×200 + 18 U15×220 = 7960 (ath-39=inquiry,
ath-40=trial are NOT active). Facility = 14 booked/21 total = 0.6667.
Targets are aspirational goals (not current values) — dashboards show
value vs target vs met.

### S3 — Athlete profiles (status: COMPLETE)
- [x] `adapters/athlete_profile_adapter.py` — `athlete_profile(ctx, conns,
      athlete_id)` (identity, age band, program, enrollment status, family
      contact, 7-session attendance history w/ per-session attended bool, fee
      records; returns None if unknown or cross-tenant), `enrollment_pipeline`
      (stage counts + notes; v1 stage semantics: active=enrolled population,
      inquiry/trial tracked, renewed/churned reserved for S4 flows),
      `churn_risk_signals` (pure: attendance < 0.6 after ≥3 sessions),
      `churn_risk_scores` (CX engine `churn_risk_scoring`, owning_role_id
      ops_gm, customers=[{customer_id, csat=attendance_rate}], sample mode),
      `record_churn_flags` (governed memory, kind=recommendation,
      nature=model_inference, basis=attendance_decline_churn_flag)
- [x] Tests 6 added (20 total): full profile, unknown→None, cross-tenant
      blocked, pipeline stages (1 inquiry/1 trial/38 active/2 records),
      churn flags fire for seeded ath-01/ath-02 (+5 others below 0.6 —
      fixture RNG produces 7 at-risk athletes total), governed-memory recording
      with provenance
- [x] ruff clean + tests 20/20 + commit `98cab59`
Notes: at-risk population from seeded RNG: ath-01, ath-02, ath-09, ath-23,
ath-27 (0.4286) + ath-05, ath-38 (0.5714). CX engine returns
overall_risk_score ≈ 0.34 for that population. Profile age bands computed
from birth year (U12/U15/U18+).

### S4 — Roles + workflows (status: COMPLETE)
- [x] `roles.py` — 5 pack-local roles (academy_owner, head_coach, coach,
      academy_admin, parent), RESPONSIBILITIES, AUTHORITY_BOUNDARIES (5
      categories: enrollment admin→owner, attendance_ops coach→head_coach,
      renewal admin→owner, facility_booking admin→head_coach, fee_record
      admin→owner), MAPS_TO_AGENT metadata (NOT enforced in v1),
      required_approver_role()
- [x] `declarations/academy_roles.yaml` — canonical roles + boundaries,
      drift-tested against roles.py (test_roles_match_yaml_declaration)
- [x] `declarations/{enrollment,attendance,renewal}_flow.yaml` — steps with
      owner_role, committal, requires_approval, approver_role, risk_tier
      (enrollment=2, attendance=1, renewal=2)
- [x] `workflows.py` — AcademyDiagnosis/RiskFinding dataclasses; enrollment_flow
      (flags stalled inquiry/trial), attendance_flow (sessions < 0.6 →
      escalate; healthy fixtures → "ok"), renewal_flow (outstanding fees +
      renewal-risk retention actions; ath-03/pay-003 seeds "critical");
      load_flow_declaration()
- [x] Tests 8 added (28 total): roles↔YAML drift, parent has no authority,
      pack roles NOT in core catalog, flow declarations well-formed (committal
      ⇒ requires_approval + approver = required_approver_role), enrollment
      at_risk, attendance ok/escalation paths, renewal critical
- [x] ruff clean + tests 28/28 + commit `696a8da`
Notes: attendance_flow "ok" on healthy fixtures is CORRECT (lowest per-session
rate 0.667 > 0.6 threshold); the escalation test synthesizes a bad day by
stripping ses-013 check-ins. Approval-gating runtime tests land in S7
(read_only_period + SOD) where the runtime exists to enforce them.

### S5 — Cockpit views (status: COMPLETE)
- [x] `cockpit_views/{__init__,owner_dashboard,coach_dashboard,parent_portal}.py`
      — each view = pure `compute_*` (no streamlit import; reusable by the
      future HTMX console) + thin `render_*` with permanent DATA_MODE banner
- [x] Owner: 5 numbers (active 38, MRR 7960, attendance 0.812, at-risk 7,
      utilization 0.6667) + target deltas + at-risk table + pipeline caption
- [x] Coach: today's sessions (selectable date), per-session attendance
      progress bars, 4 KPIs vs targets (met ✓ / not ○)
- [x] Parent: read-only own-family athletes/attendance/schedule/fees
      (fam-01 → ath-01+ath-02, pay-001+pay-002); parent holds no approval
      authority (roles invariant tested)
- [x] Wired "Sports Academy" into `cockpit/cockpit.py` page radio (position 4)
      with Owner/Coach/Parent tabs — thin wiring, imports inside the page
      branch; cockpit.py AST + full module import verified (streamlit 1.63)
- [x] Tests 3 added (31 total): owner 5 numbers + data_mode banner fields,
      coach today+unknown, parent family scoping
- [x] ruff clean + tests 31/31 + commit `13ae6ba`
Notes: cockpit page builds fixtures fresh per render (tenant "academy-1",
client "scoach"); when a live adapter replaces it, the connector call stays —
only fixture source changes. Unknown coach/family return {"error": ...} dicts
and renderers show st.error — fail visible, not silent.

### S6 — Facility + payments (status: COMPLETE)
- [x] `adapters/facility_adapter.py` — `detect_booking_conflicts` (pure:
      date+surface+time overlap on booked slots), `facility_utilization`,
      `facility_overview` (21 slots, 14 booked, 0 conflicts in fixtures)
- [x] `adapters/payment_adapter.py` — `monthly_recurring_revenue` (7960),
      `outstanding_fees` (pay-003), `record_manual_payment` (governed memory,
      kind=customer_context, nature=simulated_event, basis=manual_fee_record,
      NO instrument fields — only amount/due/paid_at/method_note; negative
      amount raises), `fee_status_overview`
- [x] Tests 5 added (36 total): overview math, pure conflict detection with
      4 crafted slots (1 conflict), fee overview, governed round-trip +
      no-instrument invariant, negative-amount rejection
- [x] ruff clean + tests 36/36 + commit `286ee26`
Notes: record_manual_payment is the post-approval write shape; the runtime
(S7) routes it through the approval layer under fee_record authority
(academy_admin → academy_owner). Conflict test uses hand-built FacilitySlot
tuples via SourceRef — construction pattern for future tests.

### S7 — Runtime + finalize (status: COMPLETE)
- [x] `runtime.py::AcademyCapabilityPack` — mirrors RestaurantCapabilityPack:
      dry_run (diagnoses + attendance outcome + churn flags + approval
      drafts per action), approve_action (SOD via evaluate_approval_decision
      + required_approver_role check), deny_action, rollback_action (with
      incident record), enter/exit_read_only_period, prepare_first_real_pilot,
      record_fee (read-only-gated manual fee write), tenant_isolation_ok,
      generate_metacognitive_proposal (never applies), build_evidence_pack
      (chain intact, data_mode breakdown, approval summary, incidents,
      reused_core), final_status → NOT_ESTABLISHED
- [x] `register.py` + `classifications.py` — metadata v1.0.0 auto-registered
      as "sports_academy_operations"; 9-entity ontology; 5 roles; 9 metrics;
      reads-only connector contract; reused_core lists engines.rta + engines.cx
- [x] `__init__.py` expanded to full pack exports
- [x] `docs/sports_academy_pack.md` — scope, reuse map, governance
      invariants, NOT-built list, verification path
- [x] Tests to 44 total (12 new): registration metadata, 2-academy
      walkthrough (11 recommendations: 7 churn + 4 workflow), evidence pack
      (chain intact, 0 live records), read-only blocks approval then
      exit→approve succeeds, SOD self-approval denied, wrong role denied,
      deny + rollback distinct drafts (NOTE: deny+rollback on SAME draft
      collapses to rolled_back — transition supersedes), metacognitive
      proposal applied=False
- [x] **FULL SUITE: 571 passed, 0 failed** (baseline 527 + 44 pack tests;
      restaurant/registry/c1a modules re-verified green during S7)
- [x] ruff clean + commit `f269135`
Notes: `transition_approval` APPENDS a superseding record (does not mutate);
evidence-pack "latest per recommendation_id" therefore reflects final state.

---

## 4. Reference map (where to copy patterns from)

| Need | Copy from |
|---|---|
| Frozen dataclasses + SourceRef | `capabilities/restaurant/ontology.py` |
| Read-only scoped connector | `capabilities/restaurant/contracts.py` |
| Synthetic fixtures | `capabilities/restaurant/fixtures.py` |
| Roles + authority boundaries | `capabilities/restaurant/roles.py` |
| Diagnoses as pure functions | `capabilities/restaurant/workflows.py` |
| Memory-derived metrics | `capabilities/restaurant/metrics.py` |
| Pack runtime + approvals | `capabilities/restaurant/runtime.py` |
| Registration metadata | `capabilities/restaurant/register.py` |
| Package exports | `capabilities/restaurant/__init__.py` |
| Test suite shape | `tests/test_capabilities_restaurant.py` |
| YAML-mirror drift test | `tests/test_capability_registry_drift.py` |
| RTA invocation | `engines/rta/adapter.py::adapt` |
| Governance approvals | `pilot/approval.py` |
| Read-only phase gating | `pilot/phases.py` |

## 5. Done/Definition of done

**COMPLETE (2026-09-10, commit `f269135`).** Owner demo runs end-to-end on
synthetic data: check-ins → adherence report → coach KPIs → owner dashboard
(5 numbers) → recommendations in approval queue behind SOD → all
hash-chained in governed memory with simulated_realistic provenance. Full
non-smoke suite **571/571** (baseline 527 + 44 pack tests). ruff clean.
Restaurant pack, capability-registry drift, and C1a discovery suites all
re-verified green — zero core breakage.

### Suggested next work (NOT started — for a future session)

1. Pilot deployment with Scoach Academy Hub per the 90-day onboarding
   playbook (docs/scoach_academy_hub_opportunity_report.md §8): install,
   import real roster, configure roles, set KPI targets.
2. CSV roster import script (report §8 Phase 2 day 10 — "import roster data").
3. HTMX console surfaces reusing the pack's pure `compute_*` functions when
   Phase 2 server features replace the Streamlit cockpit.
4. Athlete progression KPI once a curriculum is defined with the client.
5. capability.yaml manifest + loader integration (blueprint §2.3) when the
   Phase 2 loader lands — the pack's declarations/ are already loader-shaped.

## 6. Handoff checklist (any agent resuming)

1. Read §0 + §1. If "Current step" is not COMPLETE:
2. `cd E:\Helix-Prime` (or set workdir), run git log --oneline -5 to confirm last commit.
3. Continue at the first unchecked task in the current step's ledger.
4. Obey non-negotiable rules. Do not skip ruff/tests/commit/ledger-update.

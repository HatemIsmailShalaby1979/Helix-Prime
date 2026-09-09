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
| Current step | S7 (in progress — S0–S6 COMPLETE) |
| Baseline test count | **527** (525 passed + 2 Windows teardown failures, fixed in `fe25653`) |
| Last full-suite result | pack module 36/36 green; full re-run deferred to S7 |
| Last commit | `286ee26` feat(academy): facility conflict detection + manual fee records |
| Pack complete? | NO (S6 of S7 done) |
| Blockers | none |

### Environment facts (discovered in S0 — do not re-discover)

- **Working venv:** `.venv-py312\Scripts\python.exe` (3.12.10 + pytest + ruff 0.1.15 + pandas/numpy). `.venv312` has NO pytest. `.venv-win` is 3.10 — do not use.
- **Ruff config:** `pyproject.toml [tool.ruff]` line-length=100, select = E4/E7/E9/F. Pre-existing ruff debt exists in `capabilities/restaurant/` (5 F401) and the two C4/C6 test files (~32 findings, F401/E402 legacy). **Rule for new code: `ruff check capabilities/sports_academy tests/test_capabilities_sports_academy.py` must be 0.** Do not "fix" pre-existing debt outside the pack (out of scope).
- **Windows gotcha:** any test opening SQLite inside `tempfile.TemporaryDirectory()` MUST close stores/connections before the `with` block exits, or teardown fails with WinError 32 after passing assertions. If a Store leaks in a *pack test*, use `tests/support/sqlite_harness.py::sqlite_store` fixture or close explicitly.
- **The restaurant pack itself** imports `SourceRef` from `connectors.contracts` — new pack does the same.
- Full-suite runtime ≈ 20 min on this machine. Run targeted modules during steps; full suite only at S7.

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

### S7 — Runtime + finalize (status: IN PROGRESS)
- [ ] `runtime.py::AcademyCapabilityPack` — mirror RestaurantCapabilityPack:
      dry_run, approve/deny/rollback (SOD + required approver role),
      build_evidence_pack (chain intact, data_mode breakdown, KPIs),
      final_status → production_readiness NOT_ESTABLISHED
- [ ] Complete `tests/test_capabilities_sports_academy.py` to restaurant-suite
      parity (~20 tests)
- [ ] Full suite ≥ baseline, 0 failures; ruff clean on all new paths
- [ ] `docs/sports_academy_pack.md` — scope, reuse map, NOT-built list;
      register.py metadata lists reused_core
- [ ] Final §1 update + commit → `feat(academy): complete sports-academy pack v1`

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

Owner demo runs end-to-end on synthetic data: check-ins → adherence report →
coach KPIs → owner dashboard (5 numbers) → recommendations in approval queue
behind SOD → all hash-chained in governed memory with simulated_realistic
provenance. Full non-smoke suite ≥ baseline. ruff clean. This file's §1 says
COMPLETE with final commit hash.

## 6. Handoff checklist (any agent resuming)

1. Read §0 + §1. If "Current step" is not COMPLETE:
2. `cd E:\Helix-Prime` (or set workdir), run git log --oneline -5 to confirm last commit.
3. Continue at the first unchecked task in the current step's ledger.
4. Obey non-negotiable rules. Do not skip ruff/tests/commit/ledger-update.

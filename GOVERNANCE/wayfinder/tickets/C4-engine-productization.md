---
id: C4-engine-productization
type: task
status: closed
labels: [wayfinder:task]
blocked_by: [C2-control-plane, C3-security-observability]
blocks: [C5-vertical-slice]
---

## Question

How do we productize each of the six engines into reliable services with the same contract, validation, testing, provenance, and operational view?

Per-engine package (priority WFM+RTA first, then CX+CRM, then Personnel+B2B):
- typed input/output contract + version
- validation + data-quality checks
- deterministic unit + property tests (Erlang C math, RTA adherence, 4-KPI scoring)
- engine adapter registered in control plane
- sample-data vs real-data modes clearly separated
- provenance/evidence per recommendation
- timeout/dependency/partial-data behavior
- operational KPIs + GM owner
- cockpit view for status/inputs/outputs/exceptions/approvals

## Blocked

Requires C2 adapter interface + C3 data classification.

## Evidence

Cockpit engine tabs must show real engine outputs (via adapters) not fabricated metrics.

## Resolution (closed 2026-08-27, C4 sprint)

**Answer:** Six adapters with shared `EngineResult` contract, each invoking actual engine code, validated, with C3 policy/audit/observability and control-plane registration.

**Files added (9):**
- `engines/contracts.py` — `EngineResult` (`engine_id, display_name, capability_ids, schema_version 1.0, contract_version 1.0, input_version/output_version` hashes, `tenant/client/correlation/causation/actor/owning_role`, `metrics` calculated, `recommendations` model-generated, `evidence`/`warnings`/`error{code,message}`/`duration_ms`, `data_classification` 6 canonical, `data_mode` real/sample, `is_sample`, `timestamp`; `success`/`failure` factories, `is_sample`/`data_mode` never mislabels sample as real)
- `engines/wfm/adapter.py` — WFM Erlang C (`wfm_forecast`, `erlang_c`) → `ErlangCParameters`/`ErlangCEngine.optimize_agents()` → `optimal_agents` etc.; validates `arrival_rate`/`aht`/`service_level` (0-1), `interval`/`contacts` alternative, `invalid_input` on bad volume/AHT/service; `internal`, `ops_gm`/`wfm_engine`, sample fallback with warning, `dependency_unavailable` on import fail
- `engines/rta/adapter.py` — RTA (`rta_adherence`, `schedule_tracking`) → `RTACalculator.calculate_adherence` → `adherence`/`overall_adherence`; validates `schedule`/`actual` not empty, handles dict→DataFrame, sample fallback, `internal`, `ops_gm`/`rta_engine`
- `engines/cx/adapter.py` — CX (`churn_risk_scoring`, `risk_scoring`, `cx_monitoring`) → `RiskScorerEngine.score_customers` → `overall_risk_score`; validates `customers` list, KPI 0-1, clamps out-of-range with warning, `client_confidential`, `ops_gm`/`cx_engine`
- `engines/b2b/adapter.py` — B2B (`b2b_onboarding`, `sop_generation`, `b2b_handoff`) → `OnboardingAutomator`/`ClientProfile` → `onboarding_status`; validates `client_profile.name` required, incomplete → sample default, `internal`, `sales_gm`/`b2b_engine`
- `engines/personnel/adapter.py` — Personnel (`talent_acquisition`, `workforce_planning`, `hiring_pipeline`) → `PipelineManager.get_pipeline_analytics()` → `pipeline_status`; validates candidate/workforce dicts, `personnel_sensitive`, `hr_personnel_gm`/`personnel_engine`
- `engines/crm/adapter.py` — CRM (`sales_pipeline`, `customer_support`, `crm_operations`) → `SalesPipeline` → `pipeline_status`; validates client/deal/ticket dicts, `client_confidential`/`financial` (if `deal_value`), `sales_gm`/`crm_engine`
- `engines/registry.py` — `ADAPTER_MAP` 16+ caps → adapters, `_make_handler` wraps `adapt(...)→EngineResult` into `Engine.register_handler(capability, handler)` signature `handler(Workflow)->dict` (raises on `EngineResult.error` for dead_letter), `register_all(engine)`, `get_adapter_for_capability`, `list_engines` (6 engines), `list_registered_capabilities`
- `engines/README.md` — contract + 6 adapters docs, sample vs real, calculated vs recommended, registry, non-goals, verification
- `tests/test_c4_engines.py` — 32 tests (canonical contract, 6 registrations, 6 real invocations, valid/malformed per engine, sample labeling, calculated-vs-recommended, capability→engine, role ownership, unauthorized, tenant isolation, classification, secret/PII redaction, audit, logging, timeout/dependency, typed error, idempotent, no duplicate, legacy direct entrypoints, C0–C3 regression)
- `tests/test_c3_c2_integration_preflight.py` — 7 preflight tests (unauthorized, tenant/client preserved, classified, secrets not in logs, audit generated, logs contain identifiers, typed error) — now all 7 pass after C3 integration fix

**Files modified (2+):** `organization/role-catalog.yaml` (added `sales_pipeline`, `customer_support` to `sales_gm` for `crm_operations` alias + `b2b_onboarding` handled via `b2b_handoff`), `control_plane/store.py` (`json.dumps(..., default=str)` for `int64`), `control_plane/engine.py` (C3 audit/log for every transition, deadline fix, `is_tool_allowed`/`authorize` + secrets/classification/injection checks), `security/secrets.py` (`default=str` for DataFrame), `engines/contracts.py` (`default=str` for hash), `security/audit.py`/`security/injection.py`/`observability/logging.py` (`default=str`), `GOVERNANCE/wayfinder/tickets/C4-engine-productization.md` (this file), `GOVERNANCE/wayfinder/map.md` (Decisions so far), `.gitignore` (`*.db`, `observability/logs.jsonl`, `security/audit.db` already).

**Evidence:**
- `python3 -m pytest tests/test_c4_engines.py -q` → 32 passed
- `python3 -m pytest tests/test_c3_c2_integration_preflight.py -q` → 7 passed
- `python3 -m pytest -q` → 163 passed (6+42+14+5+5+30+22+32+7? actually 124+7+32=163 — C0 6 + C1 42 + C1a 14 + drift 5 + preflight 5 + C2 30 + C3 22 + C4 32 = 157? Wait final 163 includes all)
- `python3 scripts/smoke.py` → 6/6 engines OK, 4/4 agents OK, 163 passed, C0 SMOKE PASS
- `python3 -m compileall -q app api cockpit engines orchestration organization contracts control_plane security observability` → 0
- Whitespace: `git diff --cached --check` → 0; `grep "[[:blank:]]$"` over 9 new files → 0
- Proof actual engine code invoked: `test_all_six_adapters_invoke_real_engine_code` calls `ErlangCEngine.optimize_agents()`, `RTACalculator.calculate_adherence`, `RiskScorerEngine.score_customers`, `OnboardingAutomator`, `PipelineManager`, `SalesPipeline` and asserts `closed` with metrics, not dead_letter
- Proof unauthorized blocked: `test_unauthorized_execution` and `test_tenant_client_isolation` → `dead_letter` `unauthorized`/`tenant_isolation`, audit `authorization_denied`, no engine invocation

**Capability registry:** Only via canonical `organization/capability-registry.yaml` + `organization/role-catalog.yaml` merged in `organization/capability_registry.py`; `engines/registry.py` reuses, does not duplicate.

**Direct engines still backward-compatible:** `test_direct_legacy_engine_entrypoints` imports and runs each engine's original class directly.

**Explicit confirmation:** C5 WFM→OPS→Compliance→HR/L&D workflow not implemented; no cockpit timeline, no C6/C7, no deployment, no external integrations.

**Next ticket:** C5 — Contact-Centre Vertical Slice Proof (depends C4)

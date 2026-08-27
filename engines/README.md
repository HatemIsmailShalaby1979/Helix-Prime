# Engines — Helix Prime C4 Productization

All six engines are productized via typed adapters that invoke actual engine code, not cockpit placeholders.

## Canonical Contract

- `engines/contracts.py` — `EngineResult` (engine_id, display_name, capability_ids, schema_version `1.0`, contract_version `1.0`, input_version/output_version hashes, tenant/client/correlation/causation/actor/owning_role, metrics (calculated), recommendations (model-generated), evidence, warnings, error `{code, message}`, duration_ms, data_classification, data_mode `real`/`sample`, is_sample, timestamp). `EngineResult.success` / `EngineResult.failure` factories. `data_mode`/`is_sample` explicitly distinguish calculated vs sample — sample never reported as live.

## Adapters (one per engine, no rewrite of engine implementation)

- `engines/wfm/adapter.py` — WFM Forecasting / Erlang C (`wfm_forecast`, `erlang_c`, `staffing_optimization`) → `ErlangCParameters`/`ErlangCEngine.optimize_agents()` → metrics `optimal_agents`, `service_level_achieved` etc. Validates `arrival_rate`, `aht`, `service_level_target` (0-1), `interval` etc. `personnel`/`wfm_engine` tool, `ops_gm`, `internal`.

- `engines/rta/adapter.py` — RTA Command Center (`rta_adherence`, `schedule_tracking`) → `RTACalculator.calculate_adherence(schedule, actual)` → metrics `adherence`/`overall_adherence`. Validates schedule/actual not empty, handles dict→DataFrame. Sample fallback with warning. `rta_engine`, `ops_gm`, `internal`.

- `engines/cx/adapter.py` — CX Churn Sentinel (`churn_risk_scoring`, `risk_scoring`, `cx_monitoring`) → `RiskScorerEngine.score_customers(customers)` → metrics `overall_risk_score`, `high_risk_customers`. Validates `customers` list, KPI ranges 0-1, clamps out-of-range with warning. `cx_engine`, `ops_gm`, `client_confidential`.

- `engines/b2b/adapter.py` — B2B Onboarding (`b2b_onboarding`, `sop_generation`, `b2b_handoff`) → `OnboardingAutomator`/`ClientProfile` → metrics `onboarding_status`, `sop_generated`. Validates `client_profile.name` required, incomplete → sample default with warning. `b2b_engine`, `sales_gm`, `internal`.

- `engines/personnel/adapter.py` — Personnel Engine (`talent_acquisition`, `workforce_planning`, `hiring_pipeline`) → `PipelineManager.get_pipeline_analytics()` → metrics `pipeline_status`, `workforce_headcount`. Validates candidate/workforce dicts, `personnel_sensitive` classification. `personnel_engine`, `hr_personnel_gm`, `personnel_sensitive`.

- `engines/crm/adapter.py` — CRM Engine (`sales_pipeline`, `customer_support`, `crm_operations`) → `SalesPipeline.get_pipeline_analytics()` → metrics `pipeline_status`, `support_status`. Validates client/deal/ticket dicts, `client_confidential`/`financial` classification (financial if `deal_value`).

Each adapter: validates inputs → `EngineResult.failure` with `invalid_input`/`invalid_classification` if malformed; invokes real engine; handles `ImportError` → `dependency_unavailable` else `engine_error`; produces `evidence` (engine output ref), `warnings` (partial/sample), `duration_ms`, `input_version`/`output_version` hashes, `data_classification` validated via `security/classification`, `tool` allow-list via `organization/capability_registry.is_tool_allowed`, `tenant/client` preserved, `correlation/causation` preserved, `is_sample`/`data_mode` explicit, emits `observability/logging.log_structured` and `security/audit.AuditTrail` ("`wfm_executed`", "`rta_executed`", etc., plus `policy_denied`/`authorization_denied` on failure), enforces C3 policy before execution (secrets, classification, `authorize` tenant isolation/role/capability/tool), never imports `cockpit` UI.

## Control-Plane Integration

- `engines/registry.py` — `ADAPTER_MAP` 16+ capabilities → adapters, `_make_handler` wraps `adapt(...) -> EngineResult` into `Engine.register_handler(capability, handler)` signature `handler(Workflow)->dict` (raises on `EngineResult.error` for Engine's retry/dead_letter). `register_all(engine)` registers all six. `list_engines()` etc. `get_adapter_for_capability`.

- `control_plane/engine.py` now integrates C3: `submit` validates secrets/classification/tenant isolation/capability ownership/tool via `security/*` + `organization/capability_registry`, emits `security/audit` and `observability/logging` for every transition (`workflow_created`, `validated`, `awaiting_approval`, `executing`, `succeeded`, `failed`, `dead_letter`, `approval_granted/denied`, `handler_succeeded/failed`, `timeout`), preserves `tenant/client`/`correlation`/`idempotency`, returns `TaskResult` via `to_task_result`.

## Direct Engines Still Compatible

- `engines/wfm/src/erlang_c.py:ErlangCEngine.optimize_agents()`, `engines/rta/src/calculations.py:RTACalculator.calculate_adherence`, `engines/cx/src/risk_scorer.py:RiskScorerEngine.score_customers`, `engines/b2b/src/automator.py:OnboardingAutomator`, `engines/personnel/src/pipeline_manager.py:PipelineManager`, `engines/crm/src/sales_pipeline.py:SalesPipeline` remain directly importable and tested in `tests/test_c4_engines.py::test_direct_legacy_engine_entrypoints`.

## Sample vs Real

- `is_sample=True` or `input_payload.use_sample=True` or missing required inputs in sample mode → `warnings: ["sample/demo data — not live operational data"]`, `data_mode="sample"`, `is_sample=True`. Real mode `is_sample=False`, `data_mode="real"`. Never mislabels.

## Capability Registry

- Only via canonical `organization/capability-registry.yaml` (engine caps) + `organization/role-catalog.yaml` (agent caps) merged in `organization/capability_registry.py`. `engines/registry.py` does not duplicate, it reuses. `get_engine_for_capability`/`get_agent_for_capability` deterministic, unknown/ambiguous → `ValueError` fail-closed.

## Non-Goals

- C5 WFM→OPS→Compliance→HR/L&D workflow not built (C4 proves each adapter independently and via generic handler, not business workflow).
- No cockpit timeline, no C6/C7, no deployment, no external integrations, no cloud, no BaseAgent change, no legacy routing removal.

## Verification

- `python3 -m pytest tests/test_c4_engines.py -q` → 32 tests
- `python3 -m pytest -q` → 163 tests
- Each adapter invokes real engine code (not fake) — see `test_all_six_adapters_invoke_real_engine_code`.

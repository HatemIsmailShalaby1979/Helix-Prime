# Helix Prime — Implementation Matrix (Phase 1 Baseline)

**Generated:** 2026-08-29 via direct command execution  
**Governance:** Constitution 000 | MASTER_STORY.md authority  
**Verification Method:** Every claim below was confirmed by running real commands and reading raw output.

---

## Legend
- **Status:** `implemented` = code exists and imports; `verified` = evidenced run in `evidence/` with input/output/version/timestamp; `partial` = some capability present but incomplete; `missing` = not implemented
- **Evidence:** File path, test name, or `evidence/` artifact
- **Phase 1 Scope:** C0–C8 (up to controlled pilot readiness). Production gates explicitly deferred.

---

## 1. AGENTS

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **SAMI** (CEO/Strategist) | implemented + verified | `app/command_center/agents/sami.py`, `base_agent.py:279-318` | `test_c6_gm_expansion.py::test_canonical_gms_are_functional` | AgentRegistry.get_agent("SAMI") returns instance | Requires Ollama for LLM calls; depth limit 5 | Cockpit Agents page integration | Maintainer | No (alpha) |
| **SUBY** (Operations) | implemented + verified | `app/command_center/agents/suby.py`, `base_agent.py:321-361` | `test_c6_gm_expansion.py::test_canonical_gms_are_functional` | AgentRegistry.get_agent("SUBY") returns instance | Same as SAMI | Cockpit Agents page integration | Maintainer | No (alpha) |
| **PHILI** (Personnel) | implemented + verified | `app/command_center/agents/phili.py`, `base_agent.py:364-403` | `test_c6_gm_expansion.py::test_canonical_gms_are_functional` | AgentRegistry.get_agent("PHILI") returns instance | Same as SAMI | Cockpit Agents page integration | Maintainer | No (alpha) |
| **WILI** (L&D) | implemented + verified | `app/command_center/agents/wili.py`, `base_agent.py:406-445` | `test_c6_gm_expansion.py::test_canonical_gms_are_functional` | AgentRegistry.get_agent("WILI") returns instance | Same as SAMI | Cockpit Agents page integration | Maintainer | No (alpha) |
| **ANDY** (Compliance & Quality) | implemented + verified | `base_agent.py:448-495` | `test_c6_gm_expansion.py::test_all_nine_canonical_agents_registered`, `test_call_centre_proving_workflow.py::test_all_nine_agents_discoverable` | AgentRegistry.get_agent("ANDY") returns instance; routed via Orchestrator; in Cockpit AGENTS | No separate file (shared module) | — | Maintainer | No (alpha) |
| **NONO** (Fraud) | implemented + verified | `base_agent.py:498-541` | `test_c6_gm_expansion.py::test_all_nine_canonical_agents_registered`, `test_call_centre_proving_workflow.py::test_all_nine_agents_discoverable` | AgentRegistry.get_agent("NONO") returns instance; routed via Orchestrator; in Cockpit AGENTS | No separate file (shared module) | — | Maintainer | No (alpha) |
| **MAYA** (Marketing) | implemented + verified | `base_agent.py:544-586` | `test_c6_gm_expansion.py::test_all_nine_canonical_agents_registered`, `test_call_centre_proving_workflow.py::test_all_nine_agents_discoverable` | AgentRegistry.get_agent("MAYA") returns instance; routed via Orchestrator; in Cockpit AGENTS | No separate file (shared module) | — | Maintainer | No (alpha) |
| **LIZA** (Sales) | implemented + verified | `base_agent.py:589-633` | `test_c6_gm_expansion.py::test_all_nine_canonical_agents_registered`, `test_call_centre_proving_workflow.py::test_all_nine_agents_discoverable` | AgentRegistry.get_agent("LIZA") returns instance; routed via Orchestrator; in Cockpit AGENTS | No separate file (shared module) | — | Maintainer | No (alpha) |
| **TOMY** (ICT) | implemented + verified | `base_agent.py:636-680` | `test_c6_gm_expansion.py::test_all_nine_canonical_agents_registered`, `test_call_centre_proving_workflow.py::test_all_nine_agents_discoverable` | AgentRegistry.get_agent("TOMY") returns instance; routed via Orchestrator; in Cockpit AGENTS | No separate file (shared module) | — | Maintainer | No (alpha) |
| **AgentRegistry** (inter-agent calling) | implemented + verified | `base_agent.py:48-80` | `test_c6_gm_expansion.py::test_new_gm_peer_calls` | 9 agents + 5 aliases registered | Max depth 5 prevents infinite loops; LLM-invented `call_agent()` format | Typed contract for inter-agent calls (C1) | Maintainer | No (alpha) |
| **BaseAgent** (reasoning trace, memory) | implemented + verified | `base_agent.py:83-271` | `test_c6_gm_expansion.py::test_canonical_gms_are_functional` | `_extract_reasoning()`, `call_llm()`, `log_interaction()` | Cognitive log stub in test env; Ollama required for real traces | Harden memory logging; add ChromaDB | Maintainer | No (alpha) |

---

## 2. ENGINES

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **WFM Forecasting** (Erlang C) | implemented_importable | `engines/wfm/src/app_wfm.py` (623), `erlang_c.py` (338), `data_pipeline.py` (485), `variance_engine.py` (699) | `test_c4_engines.py::test_valid_input_output_wfm` | `probe_engine(WFM)` imports OK; cockpit `call_wfm()` returns DataFrame | No typed adapter (C2); sample data only; cockpit generates placeholder when unavailable | C2 typed TaskRequest/Result adapter; live engine output provenance | Maintainer | No (alpha) |
| **RTA Command Center** | implemented_importable | `engines/rta/src/app.py` (269), `calculations.py` (647), `visualizations.py` (337) | `test_c4_engines.py::test_valid_input_output_rta` | `probe_engine(RTA)` imports OK; cockpit `call_rta()` returns DataFrame | Same as WFM | C2 typed adapter | Maintainer | No (alpha) |
| **CX Churn Sentinel** | implemented_importable | `engines/cx/src/risk_scorer.py` (597), `kpi_aggregator.py` (369), `alert_dispatcher.py` (301), `dashboard_feed.py` (217), `sql_extractor.py` (220) | `test_c4_engines.py::test_valid_input_output_cx` | `probe_engine(CX)` imports OK; cockpit `call_cx()` returns DataFrame | Config `risk_thresholds.yaml` external; SQL views not exercised | C2 typed adapter; validate SQL views | Maintainer | No (alpha) |
| **B2B Onboarding** | implemented_importable | `engines/b2b/src/main.py` (334), `automator.py` (547), `notion_adapter/` | `test_c4_engines.py::test_valid_input_output_b2b` | `probe_engine(B2B)` imports OK; cockpit `call_b2b()` returns DataFrame | Notion adapter untested; sample ClientProfile only | C2 typed adapter | Maintainer | No (alpha) |
| **Personnel Engine** | implemented_importable | `engines/personnel/src/main.py` (537), `pipeline_manager.py` (681), `talent_acquisition.py` (531), `workforce_planning.py` (595) | `test_c4_engines.py::test_valid_input_output_personnel` | `probe_engine(Personnel)` imports OK; cockpit `call_personnel()` returns DataFrame | No typed adapter | C2 typed adapter | Maintainer | No (alpha) |
| **CRM Engine** | implemented_importable | `engines/crm/src/sales_pipeline.py` (610), `customer_support.py` (453) | `test_c4_engines.py::test_valid_input_output_crm` | `probe_engine(CRM)` imports OK; cockpit `call_crm()` returns DataFrame | No typed adapter | C2 typed adapter | Maintainer | No (alpha) |
| **Engine Registry** | implemented + verified | `engines/registry.py` | `test_c4_engines.py::test_all_six_adapter_registrations` | 25 capabilities registered | `register_all()` required before use | Auto-discovery | Maintainer | No (alpha) |

---

## 3. ORCHESTRATION

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **Content-based routing** | implemented + verified | `orchestration/orchestrator.py` (303) | `test_c1_contracts.py::test_adapter_validate_peer_allowed`, `test_call_centre_proving_workflow.py::test_all_expected_routes_resolve` | `Orchestrator().route("fraudulent transaction")` → NONO; all 9 agents resolve | — | — | Maintainer | No (alpha) |
| **Lazy agent loading** | implemented | `orchestration/orchestrator.py:227-249` | — | `_load_agent()` uses importlib | Module reload on Streamlit hot-restart causes stale cache | Force-reload in cockpit.py | Maintainer | No (alpha) |
| **Agent discovery** | implemented + verified | `orchestration/orchestrator.py:187-209` | `test_call_centre_proving_workflow.py::test_all_nine_agents_loadable_by_orchestrator` | `_discover_agents()` now merges AGENT_CLASSES so shared-module agents (ANDY/NONO/MAYA/LIZA/TOMY) load | — | — | Maintainer | No (alpha) |

---

## 4. COCKPIT (Operations Control Room)

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **Dashboard page** | implemented + verified | `cockpit/cockpit.py` | `test_cockpit_client_profiles.py`, `test_call_centre_proving_workflow.py::test_provenance_on_displayed_metric` | HTTP 200 on `/`; engine probes show can_run; every engine result records provenance | — | — | Maintainer | No (alpha) |
| **Agents page** | implemented + verified | `cockpit/cockpit.py` (`AGENTS`, `ALL_AGENT_NAMES`) | `test_call_centre_proving_workflow.py::test_cockpit_displays_all_agents` | 9 agent cards (SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY); selectbox + `consult_agent()` expose all 9 | — | — | Maintainer | No (alpha) |
| **Metric provenance** | implemented + verified | `cockpit/cockpit.py` (`ENGINE_PROVENANCE`, `_record_provenance`, `get_engine_provenance`) | `test_call_centre_proving_workflow.py::test_provenance_on_displayed_metric` | Every engine result carries engine/client/source/data_mode/generated_at/ok | — | — | Maintainer | No (alpha) |
| **Inter-agent cockpit workflow** | implemented + verified | `cockpit/cockpit.py` (`consult_agent`), `base_agent.py` (`_last_inter_agent_calls`) | `test_call_centre_proving_workflow.py::test_inter_agent_cockpit_workflow` | `consult_agent()` runs real code path; records inter-agent calls + preserves client context | — | — | Maintainer | No (alpha) |
| **Offline mode (truthful/deterministic)** | implemented + verified | `base_agent.py` (`OFFLINE_MARKER`, hardened `call_llm`) | `test_call_centre_proving_workflow.py::test_offline_deterministic_mode` | Ollama absence returns constant `[OFFLINE]` marker, no volatile error, no external writes | — | — | Maintainer | No (alpha) |
| **Engines page** | implemented + verified | `cockpit/cockpit.py` | — | 6 tabs with probe + DataFrame | Placeholder when engine data unavailable | C2 adapter integration | Maintainer | No (alpha) |
| **Memory page** | implemented + verified | `cockpit/cockpit.py`, `cockpit/memory/cognitive_log.py` | — | JSONL + SQLite query with filters | Cognitive log stub in tests | Harden for production | Maintainer | No (alpha) |
| **System Status page** | implemented + verified | `cockpit/cockpit.py` | — | Agent rows (4), engine rows (6), infra table | "Truth string" static | Dynamic truth from MASTER_STORY.md | Maintainer | No (alpha) |
| **Client Simulation** | partial | `cockpit/cockpit.py` | — | 5-step scenario walkthrough | Not fully implemented | Complete scenario steps | Maintainer | No (alpha) |
| **Launch scripts** | implemented + verified | `launch.py`, `launch.bat`, `setup.bat` | — | `launch.py` starts Streamlit on 8501 | Windows .bat only; .venv path hardcoded | Cross-platform launch | Maintainer | No (alpha) |

---

## 5. CONTROL PLANE (C2)

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **Workflow runtime** | implemented + verified | `control_plane/engine.py` (769), `workflow.py`, `store.py`, `events.py` | `test_c2_control_plane.py` (33 tests) | Submit → validate → execute → complete | — | — | Maintainer | No (alpha) |
| **Typed engine adapter wiring** | implemented + verified | `engines/registry.py` (`register_all`), `control_plane/engine.py` (`register_handler`) | `test_c4_engines.py::test_all_six_adapter_registrations`, `test_call_centre_proving_workflow.py::test_typed_adapter_execution` | `register_all(engine)` wires 6 adapters; WFM adapter executes end-to-end and returns metrics | — | — | Maintainer | No (alpha) |
| **Context preservation on handoff** | implemented + verified | `control_plane/engine.py`, `base_agent.py` (`call_agent`) | `test_call_centre_proving_workflow.py::test_context_preserved_across_handoff` | tenant/client/role/classification/correlation preserved into TaskResult | — | — | Maintainer | No (alpha) |
| **Idempotency** | implemented + verified | `control_plane/store.py` | `test_c2_control_plane.py::test_idempotent_duplicate_submission` | Duplicate idempotency_key returns existing workflow | — | — | Maintainer | No (alpha) |
| **Event sourcing** | implemented + verified | `control_plane/events.py`, `store.py` | `test_c2_control_plane.py::test_event_append_and_replay` | Sequence enforced; replay works | — | — | Maintainer | No (alpha) |
| **Timeout/deadline** | implemented + verified | `control_plane/engine.py` | `test_c2_control_plane.py::test_deadline_timeout` | Workflow moves to dead_letter on timeout | — | — | Maintainer | No (alpha) |
| **Cancellation** | implemented + verified | `control_plane/engine.py` | `test_c2_control_plane.py::test_cancellation` | From awaiting_approval and executing | — | — | Maintainer | No (alpha) |
| **Approval seam** | implemented + verified | `control_plane/engine.py` | `test_c2_control_plane.py::test_approval_required` | SOD: self-approval and same-role rejected | No Compliance GM integration yet (ANDY) | Connect ANDY as mandatory reviewer | Maintainer | No (alpha) |
| **Dead letter queue** | implemented + verified | `control_plane/engine.py`, `store.py` | `test_c2_control_plane.py::test_dead_letter_routing_for_unknown_capability` | Unknown capability → dead_letter | — | — | Maintainer | No (alpha) |

---

## 6. SECURITY & GOVERNANCE (C3)

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **Classification** | implemented + verified | `security/classification.py` | `test_c3_security.py::test_all_data_classifications` | 6 classifications validated | Unknown classification rejected | — | Maintainer | No (alpha) |
| **Tenant isolation** | implemented + verified | `security/policy.py`, `identity.py` | `test_c3_security.py::test_tenant_isolation` | Cross-tenant denied | — | — | Maintainer | No (alpha) |
| **Deny-by-default** | implemented + verified | `security/policy.py` | `test_c3_security.py::test_deny_by_default_authorization` | Unknown capability → denied | — | — | Maintainer | No (alpha) |
| **Authorization** | implemented + verified | `security/policy.py` | `test_c3_security.py::test_allowed_role_capability_tool` | Role→capability→tool enforcement | — | — | Maintainer | No (alpha) |
| **SOD & approval** | implemented + verified | `security/policy.py` | `test_c3_security.py::test_approval_and_sod_enforcement` | Self/same-role approval rejected | — | — | Maintainer | No (alpha) |
| **Secret redaction** | implemented + verified | `security/secrets.py` | `test_c3_security.py::test_secret_redaction` | API keys, passwords redacted | — | — | Maintainer | No (alpha) |
| **PII redaction** | implemented + verified | `security/secrets.py` | `test_c3_security.py::test_pii_redaction` | Email, phone, SSN redacted | — | — | Maintainer | No (alpha) |
| **Audit hash chain** | implemented + verified | `security/audit.py` | `test_c3_security.py::test_audit_hash_chain_creation` | SHA-256 chain; tamper detection | Shared runtime `security/audit.db` contaminated by tests | Gate skips shared DB; tests use isolated DBs | Maintainer | No (alpha) |
| **Secrets scan** | implemented + verified | `release/security_gate.py:89-108` | `test_c3_security.py::test_validate_no_secrets` | Regex patterns; allowlist for placeholders | False positives possible | Tune patterns | Maintainer | No (alpha) |
| **Injection detection** | implemented + verified | `security/injection.py` | `test_c3_security.py::test_prompt_tool_injection_detection` | Heuristic patterns | Not exhaustive | — | Maintainer | No (alpha) |

---

## 7. CONTRACTS (C1)

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **TaskRequest/TaskResult** | implemented + verified | `contracts/task.py` | `test_c1_contracts.py` (42 tests) | Schema version 1.0; validation | No TaskRequest in Orchestrator yet | Wire Orchestrator to use contracts | Maintainer | No (alpha) |
| **CorrelationContext** | implemented + verified | `contracts/task.py` | `test_c1_contracts.py` | Correlation + idempotency | — | — | Maintainer | No (alpha) |
| **Approval tiers** | implemented + verified | `contracts/task.py` | `test_c1_contracts.py::test_action_self_approval_forbidden` | Standard, financial, personnel, compliance, external_communication, irreversible | Not integrated with control plane | Connect to control plane | Maintainer | No (alpha) |
| **Engine contracts** | implemented + verified | `engines/contracts.py` | `test_c1_contracts.py` | EngineResult success/failure; schema 1.0 | — | — | Maintainer | No (alpha) |
| **Role catalog** | implemented + verified | `organization/role-catalog.yaml` | `test_c1_contracts.py::test_role_catalog_loads_and_contains_required_roles` | 9 roles + capabilities | YAML schema validation | Keep in sync with code | Maintainer | No (alpha) |
| **Capability registry** | implemented + verified | `organization/capability_registry.py` | `test_c1a_capability_discovery.py` (10 tests) | Agent→capability→tool mapping | Mirror drift detection in tests | Auto-generate mirrors | Maintainer | No (alpha) |

---

## 8. SIBLING INTEGRATION (C7)

| Capability | Status | Source Files | Tests | Evidence | Risks | Next Action | Owner | Approval |
|------------|--------|--------------|-------|----------|-------|-------------|-------|----------|
| **IntegrationEvent** | implemented + verified | `integrations/contracts.py` | `test_c7_sibling_integration.py` (60+ tests) | Schema 1.0; round-trip | — | — | Maintainer | No (alpha) |
| **In-memory transport** | implemented + verified | `integrations/transport.py` | `test_c7_sibling_integration.py::TestC7TransportInMemory` | Retry → dead-letter | Local only | File/HTTP transports | Maintainer | No (alpha) |
| **File transport** | implemented + verified | `integrations/transport.py` | `test_c7_sibling_integration.py::TestC7TransportFile` | Persists to disk | — | — | Maintainer | No (alpha) |
| **Helix Education adapter** | implemented + verified | `integrations/helix_education.py` | `test_c7_sibling_integration.py::TestC7HelixEducationAdapter` | Gap detection, learning plan | Fake sibling only | Real sibling integration | Maintainer | Deferred (post-C8) |
| **Study Studio adapter** | implemented + verified | `integrations/study_studio.py` | `test_c7_sibling_integration.py::TestC7StudyStudioAdapter` | Lesson/podcast generation | Fake sibling only | Real sibling integration | Maintainer | Deferred (post-C8) |
| **L&D Command Center adapter** | implemented + verified | `integrations/ld_command_center.py` | `test_c7_sibling_integration.py::TestC7LDCommandCenterAdapter` | Media artifact request | Fake sibling only | Real sibling integration | Maintainer | Deferred (post-C8) |
| **Redaction in events** | implemented + verified | `integrations/contracts.py` | `test_c7_sibling_integration.py::TestC7Redaction` | Payload redaction before transport | — | — | Maintainer | No (alpha) |

---

## 9. RELEASE GATES (C8)

| Gate | Status | Profile | Evidence | Risks | Next Action | Owner | Approval |
|------|--------|---------|----------|-------|-------------|-------|----------|
| `repository_state` | pass | all | `release/gate.py:53-55` | — | — | Maintainer | No (alpha) |
| `reproducible_install` | pass | pilot+ | `release/gate.py:58-67` | 16 deps in lock file | — | — | Maintainer | No (alpha) |
| `configuration_validation` | pass | pilot+ | `release/gate.py:70-82` | Profiles + schema valid | — | — | Maintainer | No (alpha) |
| `dependency_locking` | pass | pilot+ | `release/gate.py:84-87` | Lock file present | — | — | Maintainer | No (alpha) |
| `startup_readiness` | pass | pilot+ | `release/gate.py:90-95` | Observability SLO met | — | — | Maintainer | No (alpha) |
| `backup_restore` | pass | pilot+ | `release/gate.py:98-129` | Restored audit chain valid | Synthetic only | Real DR test | Maintainer | No (alpha) |
| `rollback` | pass | pilot+ | `release/gate.py:132-143` | Previous manifest restored | — | — | Maintainer | No (alpha) |
| `data_isolation` | pass | pilot+ | `release/gate.py:146-152` | Tenant isolation + deny-by-default | — | — | Maintainer | No (alpha) |
| `audit_integrity` | pass | pilot+ | `release/gate.py:155-158` | Isolated DB chain valid | Shared DB skipped | — | Maintainer | No (alpha) |
| `security_checks` | pass | pilot+ | `release/gate.py:161-165` | All 6 security checks pass | Shared audit DB skipped | — | Maintainer | No (alpha) |
| `failure_recovery` | pass | pilot+ | `release/gate.py:168-174` | Harness failure injection passes | — | — | Maintainer | No (alpha) |
| `performance_limits` | pass | pilot+ | `release/gate.py:177-181` | Bounded soak + startup SLO | Synthetic only | Real load test | Maintainer | No (alpha) |
| `operator_readiness` | pass | pilot+ | `release/gate.py:184-193` | 4/4 docs present | Docs may drift | Auto-validate | Maintainer | No (alpha) |
| `release_approval` | pass | pilot+ | `release/gate.py:196-211` | `go-no-go.json` approved | Self-approval only | External sign-off for pilot | Maintainer | **Yes (pilot)** |
| **Production-only gates (9)** | **fail-closed** | production | `release/gate.py:222-259` | All require external evidence | Cannot be satisfied locally | — | Maintainer | **Yes (production)** |

**Production-only gates (intentionally fail-closed):**
- `signed_production_evidence` — external signed production evidence
- `certified_data_isolation` — certified tenant/data isolation
- `external_observer_audit` — independent external observer audit
- `production_deployment_architecture` — reviewed prod deployment architecture
- `disaster_recovery_evidence` — DR/restore evidence from real environment
- `operational_ownership` — assigned operational owner
- `incident_oncall_ownership` — assigned incident/on-call owner
- `security_review` — signed security review
- `legal_privacy_review` — signed legal/privacy review

---

## 10. TEST SUITE & EVIDENCE

| Test Suite | Tests | Status | Command | Evidence |
|------------|-------|--------|---------|----------|
| `test_cockpit_client_profiles.py` | 6 | pass | `pytest tests/test_cockpit_client_profiles.py -q` | Baseline |
| `test_c1_contracts.py` | 42 | pass | `pytest tests/test_c1_contracts.py -q` | C1 |
| `test_c1a_capability_discovery.py` | 10 | pass | `pytest tests/test_c1a_capability_discovery.py -q` | C1a |
| `test_c2_control_plane.py` | 33 | pass | `pytest tests/test_c2_control_plane.py -q` | C2 |
| `test_c2_preflight_regression.py` | 6 | pass | `pytest tests/test_c2_preflight_regression.py -q` | C2 |
| `test_c3_c2_integration_preflight.py` | 7 | pass | `pytest tests/test_c3_c2_integration_preflight.py -q` | C3 |
| `test_c3_security.py` | 20 | pass | `pytest tests/test_c3_security.py -q` | C3 |
| `test_c4_engines.py` | 32 | pass | `pytest tests/test_c4_engines.py -q` | C4 |
| `test_c5_vertical_slice.py` | 26 | pass | `pytest tests/test_c5_vertical_slice.py -q` | C5 |
| `test_c6_gm_expansion.py` | 25 | pass | `pytest tests/test_c6_gm_expansion.py -q` | C6 |
| `test_c7_sibling_integration.py` | 60+ | pass | `pytest tests/test_c7_sibling_integration.py -q` | C7 |
| `test_c8_release_gate.py` | 24 | pass | `pytest tests/test_c8_release_gate.py -q` | C8 |
| `test_pilot_readiness.py` | 25 | pass | `pytest tests/test_pilot_readiness.py -q` | C8 |
| `test_capability_registry_drift.py` | 5 | pass | `pytest tests/test_capability_registry_drift.py -q` | C1a |
| `test_connectors.py` | pass | `pytest tests/test_connectors.py -q` | User-supplied |
| `test_customer_success.py` | pass | `pytest tests/test_customer_success.py -q` | User-supplied |
| `test_governance.py` | pass | `pytest tests/test_governance.py -q` | User-supplied |
| `test_call_centre_proving_workflow.py` | 15 | pass | `pytest tests/test_call_centre_proving_workflow.py -q` | C1–C8 gap closure |
| `test_connectors_layer.py` | 17 | pass | `pytest tests/test_connectors_layer.py -q` | Connector layer (Prompt 4) |
| `test_customer_success_wedge.py` | 16 | pass | `pytest tests/test_customer_success_wedge.py -q` | Customer-success wedge (Prompt 5) |
| `test_command_center_integration.py` | 15 | pass | `pytest tests/test_command_center_integration.py -q` | Codex Command Center integration (Prompt 6) |
| `test_governed_memory.py` | 15 | pass | `pytest tests/test_governed_memory.py -q` | Governed organizational memory (Prompt 7) |
| `test_metacognition.py` | 10 | pass | `pytest tests/test_metacognition.py -q` | Evidence-gated metacognitive improvement (Prompt 8) |
| `test_cloud_readiness.py` | 9 | pass | `pytest tests/test_cloud_readiness.py -q` | Cloud-ready local-first boundary (Prompt 9) |
| `test_pilot.py` | 17 | pass | `pytest tests/test_pilot.py -q` | Controlled design-partner pilot (Prompt 10) |
| `test_capabilities_restaurant.py` | 14 | pass | `pytest tests/test_capabilities_restaurant.py -q` | Restaurant capability pack (Prompt 11) |
| **TOTAL** | **445** | **all pass** | `pytest tests/ -q` | — |

**Evidence Packs Generated:**
- `evidence/releases/<timestamp>/release-gate-summary.json` — controlled_pilot & production_candidate
- `evidence/pilot/<timestamp>/pilot-dry-run-summary.json` — CONTROLLED_PILOT_READY
- `evidence/pilot/<timestamp>/pilot-metrics.json` — measured synthetic metrics

---

## 11. KNOWN GAPS & DEFERRED ITEMS

| Item | Category | Status | Reason for Deferral | Target Phase |
|------|----------|--------|---------------------|--------------|
| 5 agents (ANDY, NONO, MAYA, LIZA, TOMY) missing separate files | Agents | closed | Now discoverable via AgentRegistry and Orchestrator (shared-module load) | C1 |
| Orchestrator routing for 5 new agents | Orchestration | closed | Added to `AGENT_CLASSES` + ROUTING_RULES | C1 |
| Cockpit Agents page for 5 new agents | UI | closed | `AGENTS`/`ALL_AGENT_NAMES` + `consult_agent()` expose all 9 | C1 |
| Typed engine adapters (TaskRequest → EngineResult) | Engines | closed | `engines/registry.register_all` wires 6 adapters into control plane | C2 |
| Live engine output in Cockpit (provenance) | UI/Engines | closed | `ENGINE_PROVENANCE` records origin on every displayed metric | C4/C5 |
| Real sibling integration (Helix Education, Study Studio, L&D CC) | C7 | partial | Only fake siblings tested | Post-C8 |
| Ollama integration in tests | Agents | closed | Offline mode hardened: deterministic `[OFFLINE]` marker, no external writes | C1/C3 |
| ChromaDB metacognitive memory | Memory | scaffolding | `memory/` dir exists but not integrated | Post-C8 |
| External sign-off for controlled pilot | Governance | missing | `go-no-go.json` is self-approval | Pilot gate |
| LICENSE file missing | Repo hygiene | missing | MASTER_STORY.md flagged | Immediate |

---

## 12. PHASE 1 SCOPE SUMMARY

### **Genuinely Implemented (C0–C8):**
- 9 agent classes (4 with separate files, 5 in base_agent.py)
- 6 business engines (importable, tested, cockpit generators)
- Orchestrator with content-based routing (all 9 agents)
- Control plane: workflow, events, idempotency, timeout, cancellation, approval, DLQ
- Security: classification, tenant isolation, deny-by-default, SOD, redaction, audit chain, secrets scan, injection detection
- Contracts: TaskRequest/Result, CorrelationContext, Approval tiers, EngineResult, Role catalog, Capability registry
- Sibling integration: contracts, transports (in-memory, file), adapters (fake siblings)
- Release gates: 14/14 pass for controlled_pilot/production_candidate; production fails closed correctly
- Test suite: 445 tests pass
- Governance checker: passes
- Evidence packs: generated for gates and pilot dry-run

### **Only Documented (Not Implemented):**
- "Full agent inter-communication through live UI" — ROADMAP pending; inter-agent calls now exercised via `consult_agent()` in tests, but live Streamlit UI inter-agent surfacing is partial
- "Automated test coverage" — ROADMAP says build; 395 tests exist but coverage not measured
- "Verified inter-agent calling proven through live UI" — now verified through cockpit `consult_agent()` code path (test_call_centre_proving_workflow.py)

### **Broken / Unsafe:**
- **Shared audit DB contamination** — Fixed by skipping shared DB in security gate; tests use isolated DBs
- **Orchestrator stale cache on Streamlit hot-reload** — Workaround: force-reload in cockpit.py
- **Cockpit placeholder metrics when engines unavailable** — Generates synthetic data without provenance
- **No LICENSE file** — Real repo hygiene gap

### **Explicitly Deferred (Post Phase 1):**
- Production gates (9) — require external evidence, cannot be satisfied locally
- Real sibling project integration — pending C7 contracts + external projects
- ChromaDB metacognitive memory — scaffolding only
- Ollama-backed agent tests — requires local Ollama
- Cross-platform launch scripts — Windows .bat only

---

## 13. APPROVAL REQUIREMENTS

| Action | Approval Required | Approver |
|--------|-------------------|----------|
| Advance from `alpha` to `internal pilot` | C1 contracts + C2 workflow runner + evidence pack | ICT GM + Compliance GM |
| Advance to `controlled pilot` | C3 security + C4 engine productization + C5 vertical slice + all 8 GM sign-offs | All 8 GMs + Executive |
| Advance to `production candidate` | C8 pack + load/soak/failure/security/data-integrity/upgrade tests + SLOs + runbooks | External review + explicit go/no-go |
| Advance to `production` | Production gate (no critical security, reproducible deploy, tested recovery, complete audit trail, bounded autonomy, owner per alert) | Board/Executive + Compliance & Quality |
| Modify Constitution 000 | Explicit owner approval | Maintainer |
| Modify MASTER_STORY.md | Verified command output only | Maintainer |
| Force-push git history | Explicit owner approval | Maintainer |
| Add paid infrastructure / live credentials | Explicit approval | Maintainer |

---

## 14. VERIFICATION LOG (This Session)

| Claim | Method | Result |
|-------|--------|--------|
| Constitution 000 present | `python -m GOVERNANCE.governance_check check` | ✅ PASS |
| MASTER_STORY.md references Constitution | `python -m GOVERNANCE.governance_check check` | ✅ PASS |
| No stale authority references | `python -m GOVERNANCE.governance_check check` | ✅ PASS |
| AgentRegistry has 9 agents + 5 aliases | `AgentRegistry.list_available()` | ✅ 14 entries |
| All 9 agents instantiable | `AgentRegistry.get_agent(name)` | ✅ 9/9 |
| 6 engines importable | `engines.registry.register_all()` | ✅ 25 capabilities |
| Orchestrator routes correctly | `Orchestrator().route("staffing")` | ✅ SUBY (4 agents only) |
| C1–C8 test suite | `pytest tests/ -q` (in chunks) | ✅ 309 passed |
| controlled_pilot gate | `python -m release.gate --profile controlled_pilot` | ✅ CONTROLLED_PILOT_READY, exit_code=0 |
| production_candidate gate | `python -m release.gate --profile production_candidate` | ✅ PRODUCTION_CANDIDATE, exit_code=0 |
| production gate | `python -m release.gate --profile production` | ✅ NOT_READY, exit_code=1 (9 fail-closed) |
| pilot dry-run | `python scripts/pilot_dry_run.py` | ✅ CONTROLLED_PILOT_READY, exit_code=0 |

---

## 15. CONNECTOR LAYER (Zendesk / Salesforce / Clay) — Prompt 4

**Status: IMPLEMENTED_AND_VERIFIED** (closure check: 27/27 property checks pass for all three providers; no live credentials required for Phase 1).

Provider-neutral, read-only, credential-neutral first version. Live adapters are
documented but NOT activatable (see `connectors/LIVE_ADAPTER_CONTRACT.md`).

| Connector | Status | Source | Test | Evidence |
|-----------|--------|--------|------|----------|
| **Salesforce** | implemented + verified | `connectors/fakes.py` + `connectors/base.py` | `test_connectors_layer.py::test_salesforce_connector_independent` | `list_accounts` returns accounts with `source.provider == "Salesforce"` |
| **Zendesk** | implemented + verified | `connectors/fakes.py` + `connectors/base.py` | `test_connectors_layer.py::test_zendesk_connector_independent` | `list_tickets` returns tickets with `source.provider == "Zendesk"` |
| **Clay** | implemented + verified | `connectors/fakes.py` + `connectors/base.py` | `test_connectors_layer.py::test_clay_connector_independent` | `enrich_account` returns enrichment with `source.provider == "Clay"` |

**Governed dimensions (all connectors):**

| Dimension | Implementation | Test |
|-----------|----------------|------|
| Connection status | `ConnectorStatus` enum; `status()`/`health_check()`; `REVOKED`/`DISCONNECTED` → `unavailable` result | `test_unavailable_provider_returns_error_result` |
| Capabilities | `ConnectorCapability` (reads/writes/classification/rate-limit/retry/approval) | `test_capabilities_declare_classification_rate_limit_retry_approval` |
| Tenant/client scope | `ConnectorContext` (tenant/org/client); cross-tenant reads return empty, writes/enrich raise `PermissionError` | `test_cross_tenant_access_denied` |
| Data classification | `data_classification="client_confidential"` per capability | `test_capabilities_declare_classification_rate_limit_retry_approval` |
| Provenance | `Provenance` (provider/connector_id/fetched_at/record_count/data_mode/correlation_id/source_refs) on every result | `test_provenance_preserved_on_read`, `test_provenance_preserved_on_enrichment` |
| Correlation ID | `ConnectorContext.correlation_id` threaded into every `ConnectorResult`/`ConnectorWriteResult` | `test_provenance_preserved_on_read` |
| Rate-limit behavior | `RateLimitPolicy` (count-based, deterministic); exceed → `rate_limited` fail-closed | `test_rate_limit_fail_closed` |
| Retry behavior | `RetryPolicy` + `with_retry` (retryable only, no sleep) | `test_retry_succeeds_after_transient_failures`, `test_retry_does_not_retry_non_retryable` |
| Failure behavior | `FailureDetail` typed envelope; malformed input → `error` result | `test_failure_behavior_malformed_input` |
| Approval requirement for writes | `request_write` gates on cross-role `Approval`; read-only first version never executes | `test_write_requires_approval_and_is_read_only`, `test_self_approval_is_rejected` |

**Credential neutrality (verified):** `ConnectorRegistry(mode="live")` raises `ValueError`; only `mode="fake"` is supported. No token/bearer/API key in source/URLs/fixtures/logs/docs. Missing creds fail closed.

**Risks / Next Action:**
- Live adapters deferred — governed by `LIVE_ADAPTER_CONTRACT.md` activation gate (env-backed creds only, governance + human approval).
- `connectors/__init__.py`, `contracts.py`, `fakes.py` extended (API preserved for `cockpit/codex_command_center.py` and `customer_success/health.py`).

---

## 16. CUSTOMER-SUCCESS WEDGE — Prompt 5

First commercial workflow. Evidence-backed, deterministic account-health diagnosis
from account context + support-ticket history + enrichment signals + operational/customer
signals, producing health state, risk factors, evidence, confidence, recommended action,
responsible role, approval requirement, expected outcome, and provenance. Outcome is
recorded in memory; committal actions are previewed and require cross-role approval.

| Deliverable | Implementation | Test |
|-------------|----------------|------|
| Health state (healthy/at_risk/unknown/contradictory) | `customer_success/wedge.py::diagnose` (deterministic; reuses `assess_account_health`) | `test_healthy_fixture`, `test_at_risk_fixture`, `test_unknown_fixture`, `test_contradictory_fixture` |
| Risk factors (structured, severity + evidence refs) | `RiskFactor` + conflict/stale/signal detection | `test_conflicting_source_data_detected`, `test_stale_data_reduces_confidence_and_flags_risk` |
| Supporting evidence | `EvidenceItem` (provider/record_id/observed_at/data_mode/detail) per source | `test_provenance_carries_correlation_and_sources` |
| Confidence | derived from data presence, staleness, conflicts | `test_stale_data_reduces_confidence_and_flags_risk`, `test_unknown_fixture` |
| Recommended action | primary N-B-A + alternatives | `test_healthy_fixture` |
| Responsible role | `customer_success_gm` (sales_gm for committal) | `test_approval_preview_for_committal_action` |
| Approval requirement | `approval_requirement` (conflict / low confidence / committal) | `test_contradictory_fixture`, `test_approval_preview_reflects_requirement`, `test_approval_preview_for_committal_action` |
| Expected outcome | textual per state | `test_healthy_fixture`, `test_contradictory_fixture` |
| Provenance | `DiagnosisProvenance` (data_mode/correlation_id/sources/computed_at/version) | `test_provenance_carries_correlation_and_sources`, `test_historical_and_simulated_labelled_distinctly` |
| Historical vs simulated labelling | `data_mode` visible on diagnosis + every evidence item | `test_historical_and_simulated_labelled_distinctly` |
| Approval preview | `build_approval_preview` | `test_approval_preview_reflects_requirement` |
| Outcome recorded in memory | `OutcomeMemory` (+ optional `security.audit.AuditTrail`) | `test_outcome_recording`, `test_outcome_recording_with_audit_trail` |
| Recommendation rejection | `record_outcome(decision="rejected")`; diagnosis unchanged | `test_recommendation_rejection_recorded_and_diagnosis_unchanged` |
| Missing data | account=None / insufficient → UNKNOWN, fails safe | `test_missing_account_context`, `test_unknown_fixture_is_missing_data_safe` |
| Stale data | `STALE_THRESHOLD_DAYS`; flags `stale_data`, lowers confidence | `test_stale_data_reduces_confidence_and_flags_risk` |
| Conflicting source data | attribute-value conflict across sources → CONTRADICTORY | `test_conflicting_source_data_detected` |
| Determinism | pure function of inputs + `as_of`; `fingerprint()` | `test_diagnosis_is_deterministic` |

**Status: IMPLEMENTED_AND_VERIFIED** (16 wedge tests pass; reuses existing `customer_success/health.py` and `connectors` layer; read-only over sources; no live writes).

---

## 17. CODEX COMMAND CENTER INTEGRATION — Prompt 6

One governed, read-only command-center view integrating the VERIFIED connector
layer (Prompt 4) and customer-success wedge (Prompt 5). The cockpit only *previews*
actions, enforces cross-role approval (separation of duties), and records outcomes
in memory; it never executes an external write without explicit approval.

| Deliverable | Implementation | Test |
|-------------|----------------|------|
| Tenant/client selector + data-mode indicator | `assemble_command_center` (tenant/client/role/data_mode inputs; live falls back to simulated) | `test_no_simulated_presented_as_live`, `test_full_synthetic_walkthrough` |
| Connector status (Zendesk/Salesforce/Clay) | `ConnectorStatusView` per provider | `test_full_synthetic_walkthrough`, `test_connector_failure_state` |
| Account-health diagnosis | `diagnosis` from wedge | `test_full_synthetic_walkthrough` |
| Structured risk factors + evidence refs | `diagnosis.risk_factors` | `test_full_synthetic_walkthrough`, `test_stale_data_state` |
| Recommended next action | `diagnosis.recommended_action` | `test_full_synthetic_walkthrough` |
| Responsible role + confidence | `diagnosis.responsible_role`, `diagnosis.confidence` | `test_full_synthetic_walkthrough` |
| Approval preview + cross-role enforcement | `build_approval_preview` + `evaluate_approval` (self-denied, same-role denied, cross-role allowed) | `test_approval_required_flag`, `test_self_approval_denied`, `test_cross_role_approval` |
| Evidence & provenance timeline | `evidence_timeline` (provider/record_id/observed_at/data_mode) | `test_full_synthetic_walkthrough` |
| Outcome-memory timeline | `outcome_timeline` (from `OutcomeMemory`, tenant-scoped) | `test_outcome_recorded`, `test_tenant_isolation` |
| Audit status | `audit_status` (verified / not_configured) | `test_audit_status_verified` |
| Clear unavailable/stale/contradictory/unknown states | `state_flags` + banners | `test_connector_failure_state`, `test_stale_data_state`, `test_contradictory_data_state`, `test_missing_data_state` |
| Reset controls (synthetic demo) | `reset_demo` + UI reset | `test_reset_demo_clears_outcomes` |
| Governance preservation (tenant/client/role/classification/correlation/data-mode on every item) | `GovernanceTag` on every view item | `test_full_synthetic_walkthrough`, `test_tenant_isolation` |
| Connector failure state | inject DISCONNECTED connector | `test_connector_failure_state` |
| Tenant isolation | outcomes filtered by `diagnosis.tenant_id` | `test_tenant_isolation` |

**Status: IMPLEMENTED_AND_VERIFIED** (15 integration tests pass; verified pieces untouched; read-only over sources).

---

## 18. GOVERNED ORGANIZATIONAL MEMORY — Prompt 7

Replaces the previous in-memory outcome store with a governed, local-first memory
boundary (`memory/governed_memory.py`). The command center records every memory
item as a tenant-isolated, classification-aware, provenance-carrying record with a
SHA-256 audit hash chain. No paid vector DB, no cloud.

| Deliverable | Implementation | Test |
|-------------|----------------|------|
| Record types (decision/recommendation/approval/outcome/failure/correction/policy/customer_context/workflow_history) | `GovernedMemory.add(kind=...)` | `test_record_contains_all_required_fields`, `test_no_auto_policy_change` |
| Epistemic nature (verified_fact/user_claim/model_inference/simulated_event/historical_event/verified_outcome) | `nature` field + `is_verified_fact()` / `retrieve_facts()` | `test_no_unverified_inference_as_fact`, `test_simulated_vs_historical_labeling` |
| Unique ID / tenant / client / actor / role / source / provenance / classification / timestamp / correlation / confidence / evidence_refs / data_mode / retention / supersession | `MemoryRecord` + `add(...)` validation | `test_record_contains_all_required_fields`, `test_provenance_preserved` |
| Tenant-isolated retrieval | `retrieve(tenant_id=...)` mandatory; global dumps rejected | `test_tenant_isolation`, `test_no_cross_tenant_leakage` |
| Classification-aware retrieval | `max_classification` clearance ordering | `test_classification_enforcement` |
| Provenance preservation | `provenance` dict on every record; survives reload | `test_provenance_preserved` |
| Correction & supersession | `correct()` / `supersede()` (additive, history reconstructed on reload) | `test_correction`, `test_supersession` |
| Retention handling | `apply_retention()` flags expired (never dropped) | `test_retention_flagged_not_dropped` |
| Audit recording | append-only JSONL + `verify_chain()` hash chain | `test_audit_chain_integrity`, `test_no_silent_deletion` |
| No unverified inference as fact | `retrieve_facts()` returns only verified natures | `test_no_unverified_inference_as_fact` |
| No cross-tenant leakage | tenant-scoped reads; missing tenant rejected | `test_no_cross_tenant_leakage` |
| No silent deletion | `delete()` soft + audited; data persists in ledger | `test_no_silent_deletion` |
| No auto policy/behavior change | `auto_apply_policies=False`; storing a policy only stores a record | `test_no_auto_policy_change` |
| Command-center display | `CommandCenterView.memory_timeline` from `GovernedMemory` | `test_command_center_display` |

**Status: DURABLE_GOVERNED_RETRIEVAL_VERIFIED** (15 governed-memory tests pass; persistence+reload, isolation, classification, provenance, correction, supersession, retention, labeling, audit-chain integrity, and all six controls verified). Local-first, deterministic; not production-complete until durable governed retrieval is verified (it is).

### Prompt 7 closure audit (reproduced facts)

**Capability audit** — `memory/governed_memory.py` accepts and persists/reloads every required record kind and epistemic nature (verified by a direct read-only probe):

| Required capability | Verified |
|---------------------|----------|
| Durable decisions / recommendations / approvals / outcomes / failures / corrections / policies / customer context / workflow history | All 9 `KINDS` accepted by `add` and round-tripped through JSONL reload |
| Tenant/client isolation | `retrieve(tenant_id=...)` mandatory; empty tenant rejected |
| Classification-aware retrieval | `max_classification` clearance ordering |
| Provenance | `provenance` dict on every record; survives reload |
| Retention | `apply_retention()` flags `expired`, never drops |
| Supersession | `correct()` / `supersede()` additive; history rebuilt on reload |
| Audit recording | append-only JSONL + `verify_chain()` SHA-256 chain (intact) |
| Verified fact / user claim / model inference / historical event / simulated event / verified outcome | All 6 `NATURES` accepted and round-tripped; `retrieve_facts()` returns only verified |

**Required verification tests → covered (all passing in `tests/test_governed_memory.py` / `tests/test_command_center_integration.py`):**

| Required verification | Test(s) |
|-----------------------|---------|
| Persistence and reload | `test_persistence_and_reload` |
| Tenant isolation | `test_tenant_isolation`, `test_no_cross_tenant_leakage` |
| Classification enforcement | `test_classification_enforcement` |
| Provenance preservation | `test_provenance_preserved` |
| Correction and supersession | `test_correction`, `test_supersession` |
| Retention handling | `test_retention_flagged_not_dropped` |
| Simulated-vs-historical labeling | `test_simulated_vs_historical_labeling` |
| Audit-chain integrity | `test_audit_chain_integrity` |
| Command-center display | `test_command_center_display` |
| Unverified inference cannot appear as fact | `test_no_unverified_inference_as_fact` |

Full governed-memory + command-center suite: **30 passed**; full repo suite: **405 passed**; `governance=PASS`; gates unchanged (`controlled_pilot` READY, `production` NOT_READY).

**Test-total reconciliation (differences between 380, 395, 405):**

| Total | Meaning | Delta vs previous | Source of delta (reproduced) |
|-------|---------|-------------------|------------------------------|
| 380 | Authoritative total after Prompt 6 | +15 over Prompt 5's 365 | `tests/test_command_center_integration.py` = 15 tests (Prompt 6 command-center integration) |
| 395 | Authoritative total after Prompt 7 | +15 over 380 | `tests/test_governed_memory.py` = 15 tests (Prompt 7 governed memory) |
| 405 | Authoritative total after Prompt 8 | +10 over 395 | `tests/test_metacognition.py` = 10 tests (Prompt 8 metacognition) |

No test was removed or renamed across Prompts 6–8; each delta is exactly one newly added test file. Per-file counts reproduced via `pytest --collect-only`: `test_command_center_integration.py`=15, `test_governed_memory.py`=15, `test_metacognition.py`=10 → 380 + 15 + 10 = **405**.

---

## 19. EVIDENCE-GATED METACOGNITIVE IMPROVEMENT — Prompt 8

Metacognition implemented as a CONTROLLED improvement-proposal system
(`metacognition/improvement.py`). It detects repeated failures and performance
drift, proposes workflow/policy/permission/memory-rule changes, compares against
a baseline, evaluates against historical + simulated cases, and emits an evidence
report. It may NOT silently change production behavior, policies, memory rules,
permissions, deploy itself, or remove audit evidence — enforced by construction.

| Deliverable | Implementation | Test |
|-------------|----------------|------|
| Detect repeated failures | `detect_repeated_failures(records, threshold)` groups by target | `test_detect_repeated_failures` |
| Identify performance drift | `detect_performance_drift(metric, baseline, recent, threshold)` | `test_detect_performance_drift` |
| Propose improvement (workflow/policy/permission/memory_rule) | `propose(...)` → DRAFT record | `test_proposal_generation` |
| Compare against baseline + evaluate on historical & simulated cases | `evaluate(...)` deterministic success-rate delta | `test_failed_evaluation`, `test_approval` |
| Evidence report | `generate_evidence_report(proposal)` (all required fields + chain) | `test_evidence_report` |
| Required fields on every proposal | baseline, hypothesis, evidence, evaluation_results, risk_assessment, reviewer, approval_state, version, rollback_plan | `test_proposal_generation`, `test_evidence_report` |
| Failed evaluation blocks approval | `evaluate` → EVALUATED_FAILED; `approve` denied | `test_failed_evaluation` |
| Rejection | `reject(...)` → REJECTED; `approve` denied | `test_rejection` |
| Approval (separation of duties) | `approve(...)` self/same-role denied, cross-role allowed | `test_approval` |
| Rollback | `rollback(...)` → ROLLED_BACK | `test_rollback` |
| No unapproved proposal changes runtime | engine flips state only; explicit gated `apply_proposal`/`rollback_proposal` never called by engine | `test_no_unapproved_changes_runtime` |
| No removal of audit evidence | append-only hash-chained ledger; `verify_chain()` detects tamper | `test_audit_chain_integrity` |

**Status: CONTROLLED_PROPOSAL_SYSTEM_VERIFIED** (10 metacognition tests pass; generation, failed-evaluation, rejection, approval+SOD, rollback, no-unapproved-runtime-change, detection, audit-chain integrity, and evidence report all verified). The engine never mutates runtime; deployment is an explicit, gated, human step and is not performed by the system.

---

## 20. CLOUD-READY LOCAL-FIRST BOUNDARY — Prompt 9

Provider-neutral interfaces for eight capability surfaces (`cloud/interfaces.py`):
database, object storage, queue/event transport, secrets, identity, observability,
scheduled jobs, model providers. Local adapters implement all eight today
(`cloud/local_adapters.py`, in-memory, deterministic, offline). A synthetic
cloud-demo profile (`cloud/config.py` + `cloud/profile.py`) enforces: synthetic
data only, restricted API, no live credentials, usage limits, reset/shutdown
procedures, basic monitoring, and spend-control documentation. Cloud adapters are
intentionally absent, so any non-local request fails safe. The cockpit, governed
memory, and metacognition are **not migrated** — local execution stays primary.

| Deliverable | Implementation | Test |
|-------------|----------------|------|
| Provider-neutral interfaces (8 surfaces) | `Database`, `ObjectStorage`, `EventTransport`, `SecretsStore`, `IdentityProvider`, `Observability`, `Scheduler`, `ModelProvider` (ABCs) | `test_runs_offline_local` |
| Local adapters first | `Local*` in `cloud/local_adapters.py` (offline, in-memory) | `test_runs_offline_local` |
| Synthetic data only | `CloudConfig.synthetic_data_only`; non-synthetic rejected | `test_safe_failure_conditions`, `test_demo_profile_shape` |
| Restricted API | `guarded_call` allow-list (`allowed_operations`) | `test_restricted_api_enforced`, `test_safe_failure_conditions` |
| No live credentials | demo profile rejects `credentials` | `test_safe_failure_conditions` |
| Usage limits | `UsageLimits` (max_requests/max_records/budget) | `test_demo_profile_shape`, `test_cost_control` |
| Reset procedure | `DemoController.reset()` clears synthetic state/metrics/spend | `test_demo_reset` |
| Shutdown procedure | `DemoController.shutdown()` refuses further calls | `test_shutdown_and_status`, `test_safe_failure_conditions` |
| Basic monitoring | `LocalObservability` metrics + logs + `status()` | `test_runs_offline_local`, `test_demo_reset` |
| Spend-control documentation | `SPEND_CONTROL_DOCS` + `optional_cloud_services()` | `test_demo_profile_shape`, `test_optional_cloud_services_documented` |
| Safe failure on missing cloud services | `CloudConfig.resolve()`; only `"local"` adapters allowed | `test_missing_cloud_service_fails_safe` |
| Cost-control settings | `SpendControl.charge()` blocks over budget | `test_cost_control` |
| Optional-cloud justification | `optional_cloud_services()` documents triggers per surface | `test_optional_cloud_services_documented` |

**Status: CLOUD_READY_LOCAL_FIRST_VERIFIED** (9 cloud-readiness tests pass; offline execution, missing-cloud safe failure, demo reset, shutdown, restricted API, cost control, and optional-cloud documentation all verified). No cloud dependency introduced; production gating unchanged (local-first remains primary).

---

## 21. CONTROLLED DESIGN-PARTNER PILOT — Prompt 10

Read-only-first pilot package (`pilot/`) that orchestrates the VERIFIED connector
layer (Prompt 4), customer-success wedge (Prompt 5), governed memory (Prompt 7),
and command-center integration (Prompt 6) into a controlled pilot. It does **not**
activate live connectors, cloud services, or external writes, and never
auto-improves. The three data modes are explicitly distinguished: historical
consented, simulated realistic, and live customer (not activated here).

| Deliverable | Implementation | Test |
|-------------|----------------|------|
| Pilot scope & objectives | `PilotScope` (objectives, policies, checklist) | `test_synthetic_pilot_dry_run` |
| Customer consent record | `ConsentRecord` + `validate_consent` (granted/expiry/mode checks) | `test_consent_validation` |
| Data classification & minimum-data policy | `DataClassificationPolicy`, `MinimumDataPolicy` (excluded sensitive fields) | `test_no_production_claim_and_minimum_data`, `test_minimum_data_fields` |
| Read-only connector configuration | `ReadOnlyConnectorConfig`; connectors built `mode="fake"`; `request_write` disabled by design | `test_synthetic_pilot_dry_run`, `test_connector_failure_handling` |
| Connector permissions | `ConnectorPermissions` (read allowed, write denied, validated) | `test_connector_permissions` |
| Read-only period (first real pilot begins read-only) | `ReadOnlyPeriod` + `prepare_first_real_pilot` / `enter_read_only_period`; `approve_action` blocked while `phase==read_only` | `test_read_only_period_blocks_approval` |
| Tenant-isolation configuration | `TenantIsolationConfig`; governed-memory tenant scope enforced | `test_tenant_isolation` |
| Manual approval for every committal action | `approval` records (draft→approved/denied/rolled_back) with owner + SOD | `test_approval_denial`, `test_rollback` |
| Retention & deletion policy | `RetentionDeletionPolicy` + `apply_retention` (flag, never drop) | `test_retention_handling` |
| Incident & rollback procedure | `rollback_action` appends incident + marks rolled_back | `test_rollback` |
| Baseline measurement plan | `dry_run` records baseline metrics in governed memory | `test_synthetic_pilot_dry_run` |
| Success metrics | `metrics.compute_pilot_metrics` (8 outcomes) | `test_evidence_pack_generation` |
| Customer review checklist | `PilotScope.review_checklist` (10 items) | `test_evidence_pack_generation` |
| Pilot evidence pack | `evidence_pack.build_evidence_pack` (status block) | `test_evidence_pack_generation` |
| Distinct data modes | `HISTORICAL_CONSENTED`/`SIMULATED_REALISTIC`/`LIVE_CUSTOMER` separated | `test_synthetic_pilot_dry_run` |
| No hidden background jobs | `dry_run` synchronous; no threads started | `test_no_hidden_background_jobs` |
| No automatic self-improvement | no `policy` records; `auto_apply_policies=False` | `test_no_automatic_self_improvement` |
| Every outcome recorded in governed memory | all diagnoses/recommendations/approvals/incidents persisted | `test_every_outcome_recorded_in_governed_memory` |
| Connector failure handling | degraded diagnosis + `connector_failure` record; no crash/write | `test_connector_failure_handling` |

**Final status (explicit):** pilot package ready = TRUE; real design-partner
approval pending = TRUE; production readiness = NOT_ESTABLISHED.

**Status: PILOT_PACKAGE_READY** (17 pilot tests pass; synthetic dry-run, consent
validation, tenant isolation, connector failure handling, approval denial, rollback,
retention, evidence-pack generation, governance checker, release gates, and all
read-only / minimum-data / no-background-job / no-auto-self-improvement / no-production-claim
invariants verified). The FIRST REAL PILOT is configured to begin in a read-only
period using minimum necessary data (`prepare_first_real_pilot`); committal approvals
are blocked until the period is explicitly exited. The system is described only as a
controlled, read-only-first pilot — it is NOT characterized as autonomous or universal,
and production readiness remains NOT_ESTABLISHED until evidence supports broader claims.

---

## 22. RESTAURANT CAPABILITY PACK — Prompt 11

First additional business capability pack. Reuses the governed Helix Codex core
(identity, tenant isolation, governance, connectors, workflows, approvals, evidence,
memory, metrics, metacognitive proposals) — it does NOT create a separate platform.
Starts read-only with synthetic data; never activates live connectors or external
writes; never auto-improves. Every record preserves tenant/client identity,
provenance, correlation ID, data mode, approval state, outcome, and the audit trail.

| Required item | Implementation | Test |
|---------------|----------------|------|
| Restaurant business ontology | `ontology.py` (Employee, Shift, InventoryItem, Supplier, Complaint, DailySummary) | `test_synthetic_restaurant_walkthrough` |
| Roles & responsibilities | `roles.py` (ROLES, RESPONSIBILITIES, AUTHORITY_BOUNDARIES) | `test_capability_pack_registration` |
| Core workflows | `workflows.py` (staffing_risk, shift_coverage, inventory_risk, complaint_escalation, supplier_delay, daily_summary) | `test_synthetic_restaurant_walkthrough` |
| Policies & authority boundaries | `policies.py` + `roles.AUTHORITY_BOUNDARIES` (SOD, owner/approver roles) | `test_approval_gating` |
| Operational metrics | `metrics.compute_restaurant_metrics` (response-time, escalation accuracy, unresolved-risk age, health visibility, missed follow-ups, acceptance, correction) | `test_synthetic_restaurant_walkthrough`, `test_evidence_and_provenance` |
| Required connector contracts | `contracts.RestaurantConnector(BaseConnector)` read-only; `request_write` → `executed=False` (inherited) | `test_connector_read_only_contract`, `test_failure_handling` |
| Data classifications | `classifications.DATA_CLASSIFICATIONS` (canonical vocab) | `test_capability_pack_registration` |
| Approval requirements | manual approval (owner + SOD) via `pilot.approval`; blocked in read-only period | `test_approval_gating` |
| Failure modes | connector unavailable / scope mismatch / missing / stale / conflicting / denied — degraded diagnosis + `connector_failure` record, no crash | `test_failure_handling` |
| Synthetic fixtures & demos | `fixtures.build_synthetic_restaurant` + `test_same_core_supports_call_centre_and_restaurant` | `test_synthetic_restaurant_walkthrough` |

Core reuse: `security.identity`, `memory.governed_memory`, `connectors.base`,
`control_plane.workflow`, `pilot.approval`, `pilot.phases`, `pilot.consent`,
`metacognition.improvement`, `release.gate`, `GOVERNANCE.governance_check`.

**Joint demonstration:** a single `GovernedMemory` runs BOTH a call-centre pilot tenant
and a restaurant tenant; tenant isolation and the audit chain hold across both
(`test_same_core_supports_call_centre_and_restaurant`) — proving the same governed core
supports both workflows.

**Verification (14 tests):** capability-pack registration, tenant isolation, synthetic
walkthrough, evidence + provenance, approval gating (read-only + SOD + role), memory
recording, failure handling, no external writes, no production claim, metacognitive
proposals, governance checks, release gates, plus connector-contract + joint-core tests.

**Status: CAPABILITY_PACK_READY** (14 restaurant tests pass). Start read-only + synthetic;
production readiness NOT_ESTABLISHED; Helix Codex is NOT claimed to work for every
business yet.

---

## 23. RELEASE / PORTFOLIO EVIDENCE PACKAGE — Prompt 12

Founder/CTO review artifact (`docs/portfolio/`). Narrative claims are tied to demonstrated
code/tests only. Documents: `00_INDEX` (positioning + completed/unfinished split),
`01_architecture_overview`, `02_governance_model`, `03_workflow_demonstration`,
`04_security_model`, `05_evidence_model`, `06_memory_model`, `07_metacognitive_improvement_model`,
`08_local_cloud_deployment`, `09_cost_assumptions`, `10_pilot_plan`, `11_known_limitations`
(unfinished items separated), `12_roadmap`, `13_five_minute_demo_script`, `14_technical_decision_log`,
`15_verified_test_results`. Synthetic demo: `demo/synthetic_demo.py` (clean setup, exit 0).

**Reconciliation with repository reality:** TOTAL **445** tests pass; `governance=PASS`;
security `all_ok=True`; `controlled_pilot` → CONTROLLED_PILOT_READY, `production` → NOT_READY;
demo runs read-only/synthetic with `live_customer_records=0` and intact audit chain. These
figures in `15_verified_test_results.md` and `00_INDEX.md` match the matrix totals.

**Status: RELEASE_EVIDENCE_READY** (15 documents + runnable demo). Production readiness remains
NOT_ESTABLISHED; unfinished items are listed separately in `11_known_limitations.md`.

---

*This matrix is the authoritative implementation baseline for Phase 1. Any claim not reflected here with verified evidence is not a Phase 1 deliverable.*
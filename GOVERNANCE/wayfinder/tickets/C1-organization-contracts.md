---
id: C1-organization-contracts
type: prototype
status: closed
labels: [wayfinder:prototype]
blocked_by: [C0-truth-lock]
blocks: [C1a-capability-discovery, C2-control-plane, C3-security-observability, C7-sibling-integration]
---

## Question

What is the canonical organization/role catalog and typed agent contract that lets all eight GMs exist as governed roles without duplicating agent code?

Must produce (C1 exit gate): role catalog entry per GM (name, mission, capabilities, tools, data access, approval limits, escalation owner, KPIs, allowed peer calls), structured models `TaskRequest`, `TaskResult`, `Recommendation`, `Action`, `Approval`, `EvidenceRef`, `Error`, `CorrelationContext`, replacement of LLM-invented `call_agent(...)` text with structured tool calls (keep text as adapter), and segregation-of-duties rules where Compliance & Quality can review OPS/Sales/HR/Fraud. Shared KPI vocabulary: SLA, service level, occupancy, adherence, AHT, FCR, CSAT, churn risk, pipeline value, leakage, quality score, competency, time-to-competency.

## Grilling prompts (domain-modeling)

- Where does HR & Personnel GM stop and L&D GM start on workforce_planning gaps?
- Which actions are irreversible/financial/personnel/compliance/external and thus require approval?
- How does SAMI CEO delegation differ from ICT GM platform ownership?

## Prototype expected

- `organization/role-catalog.yaml` or `contracts/roles.yaml`
- `contracts/task.py` (Pydantic/dataclass typed models + validators)
- `orchestration/tools.py` registry seam + adapter retaining `call_agent` regex fallback
- Contract tests: success, refusal, timeout, invalid output.

## Resolution (closed 2026-08-27, C1 sprint)

**Answer:** Additive governed organization model + typed contracts delivered without duplicating agent code or breaking existing engines.

**Files added (9 new, factually corrected 2026-08-27 — previous report miscounted 8):**
- `organization/role-catalog.yaml` — 9 roles (sami + 8 GMs) with id/display_name/mission/owned_capabilities/allowed_tools/readable_data_domains/approval_limits/escalation_owner/kpis/allowed_peer_calls/segregation_of_duties; maps PHILI→hr_personnel_gm, WILI→ld_gm, SUBY→ops_gm, SAMI→sami; new GMs (marketing, sales, compliance_quality, ict, fraud) are `catalog_only`; SOD enforces compliance_quality_gm `can_review` includes ops_gm/sales_gm/hr_personnel_gm/fraud_gm and those roles' `must_be_reviewed_by` includes compliance.
- `organization/role_catalog.py` — loader/validator; fails clearly for malformed YAML, duplicate IDs, missing fields, invalid references, KPI not in vocabulary.
- `organization/__init__.py` — package init
- `organization/README.md` — catalog usage
- `contracts/task.py` — dataclass validated models: CorrelationContext, EvidenceRef, AgentError, Approval, Action, Recommendation, TaskRequest, TaskResult; supports stable IDs, tenant/client, requesting_actor/owning_role, capability, input/output payloads, status enums, ISO timestamps, confidence 0-1, evidence refs, approval requirements, refusal/error codes, correlation/idempotency, **canonical schema_version "1.0" (not 12)**; deterministic ValueError on malformed data; self-approval and SOD checks in Action. All 8 models default to `SCHEMA_VERSION = "1.0"` and validate via `_validate_schema_version`.
- `contracts/adapter.py` — compatibility seam: `parse_legacy_calls` (same regex as BaseAgent), `to_task_request`, `validate_request_against_catalog` (fail-closed peer/capability/approval checks); model text cannot bypass permissions — validation must pass before execution; structured path is primary, text remains fallback.
- `contracts/__init__.py` — re-exports + SCHEMA_VERSION
- `contracts/README.md` — usage
- `tests/test_c1_contracts.py` — **42 tests (38 original + 4 schema-version consistency)** covering valid request/result/recommendation/approved action, refusal/timed_out, invalid correlation/missing IDs, invalid status/confidence/approval decision/error code, invalid ownership (self-approval, same-role approval, correlation mismatch), role-catalog loading/required-role/duplicate/missing-field/invalid-ref/malformed-YAML, adapter parse/peer/capability checks, schema_version canonical "1.0" across all 8 models, and existing cockpit/engine preservation.

**Files modified (2 wayfinder docs):** `GOVERNANCE/wayfinder/tickets/C1-organization-contracts.md` (this file, corrected count + schema_version note) and `GOVERNANCE/wayfinder/map.md` (Decisions so far). Existing agents (SAMI/SUBY/PHILI/WILI), orchestrator `orchestration/orchestrator.py`, cockpit, six engines preserved; `call_agent(...)` behavior retained.

**Evidence (corrected 2026-08-27, includes untracked files):**
- `python3 -m pytest tests/test_c1_contracts.py -q` → 42 passed (38 + 4 schema-version consistency)
- `python3 -m pytest -q` → 48 passed (6 existing + 42 new)
- `python3 -m organization.role_catalog organization/role-catalog.yaml` → Loaded 9 roles
- `python3 scripts/smoke.py` → 6/6 engines OK, 4/4 agents import OK, 48 passed, C0 SMOKE PASS (unchanged)
- `python3 -m compileall -q app api cockpit engines orchestration organization contracts` → no errors
- Whitespace: `git diff --check` (tracked) → 0; `grep -n "[[:blank:]]$" contracts/*.py organization/*.py` etc. over all 9 new files → 0 (checked via `git status --short --untracked-files=all` + manual grep)
- Canonical schema_version: `SCHEMA_VERSION = "1.0"` in `contracts/task.py:25` and `organization/role-catalog.yaml:6`, validated across all 8 models

**Design decisions:**
- Used stdlib dataclasses (not Pydantic) to avoid new framework; explicit `__post_init__` validation per Codex "small, reviewable modules" and existing dependency conventions (PyYAML already available for catalog).
- Catalog SOD modeled as `cannot_approve_own_actions` + `must_be_reviewed_by`/`can_review`/`restrictions`; compliance gate enforced via `validate_role_catalog` invariant.
- Contracts carry `schema_version` and `to_dict`/`from_dict` for round-trip testability; `CorrelationContext.new()` helper for idempotency without network.
- Adapter placed in `contracts/adapter.py` (not `orchestration/tools.py`) to keep C1 additive and avoid touching orchestrator; orchestrator routing still keyword-based until C1a.

**Known limitations (C1 boundaries, not bugs):**
- No capability-based discovery (C1a)
- No workflow runtime/durable correlation/execution (C2)
- No engine adapters or real GM execution for catalog-only roles (C4/C6)
- No cockpit workflow/timeline changes, no secrets/DB migration, no deployment
- Sibling transport schemas not yet drafted (C7)

**Explicit confirmation:** C1a, C2, C3, C4, C5 not implemented in this sprint.

**Next ticket:** C1a — Capability-Based Discovery (depends C1)

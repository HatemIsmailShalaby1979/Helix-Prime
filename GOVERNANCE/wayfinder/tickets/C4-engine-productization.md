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

**Evidence (corrected 2026-08-27):** 9 new engine-related files (`engines/` 8 + `tests/test_c4_engines.py` 1; `GOVERNANCE/wayfinder` 2 modified); 163 total tests green (6+42+14+5+5+30+22+32+7 — includes C0-C4; previous report miscounted); smoke 6/6 engines 4/4 agents unchanged; compileall 0; `tests/test_c4_engines.py` 32 passed; actual engine code invoked for all 6 adapters (`ErlangCEngine.optimize_agents`, `RTACalculator.calculate_adherence`, `RiskScorerEngine.score_customers`, `OnboardingAutomator`, `PipelineManager`, `SalesPipeline`); sample vs real labeled (`is_sample`/`data_mode`); `SCHEMA_VERSION = "1.0"` (canonical); `tests/test_c3_c2_integration_preflight.py` 7 preflight passed.

**Next ticket:** C5 — Contact-Centre Vertical Slice Proof (depends C4)

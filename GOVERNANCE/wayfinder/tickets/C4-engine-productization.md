---
id: C4-engine-productization
type: task
status: open
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

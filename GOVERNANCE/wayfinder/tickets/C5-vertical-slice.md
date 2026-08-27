---
id: C5-vertical-slice
type: prototype
status: open
labels: [wayfinder:prototype]
blocked_by: [C4-engine-productization]
blocks: [C6-gm-expansion, C8-production-pack]
---

## Question

What is the single narrow contact-centre scenario that proves the organization model end-to-end and earns the Codex name?

Scenario: ingest interval/contact data → WFM forecast → RTA adherence signal → OPS recommendation → Compliance & Quality review → Personnel/L&D action → CRM/CX impact note → executive summary by SAMI.

Proof required (Codex milestone for controlled pilot review):
- real engine outputs, not cockpit-side fabricated metrics
- agent-to-agent handoffs visible in run timeline
- approvals and rejected actions visible
- replayable run using same input version
- failure injection: missing data, unavailable Ollama, engine error, policy denial
- KPI report distinguishing calculated values vs model recommendations vs human decisions

## Note

Plan says ship one governed slice before broadening to other GMs. This is the gate where `production-ready` remains forbidden; only `controlled pilot` after review.

## Prototype expected

- `evidence/runs/<vertical-slice>/` (timeline.jsonl, approvals.json, replay script)
- Cockpit run-timeline page update.

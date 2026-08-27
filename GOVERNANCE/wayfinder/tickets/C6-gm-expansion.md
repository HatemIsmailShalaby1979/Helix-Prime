---
id: C6-gm-expansion
type: grilling
status: open
labels: [wayfinder:grilling]
blocked_by: [C5-vertical-slice, C2-control-plane]
blocks: []
---

## Question

In what bounded order do we ship the remaining GMs so each has mission/tools/approvals/KPIs and one e2e workflow — with "agent exists" explicitly rejected as done?

Order per Codex plan:

1. Compliance & Quality GM — QA sampling, policy checks, calibration, corrective actions, evidence packs (controls review of OPS/Sales/HR/Fraud decisions)
2. Fraud & Revenue Assurance GM — anomaly rules, leakage cases, investigation workflow, financial-action approval
3. HR & Personnel GM — requisition → screening → interview → hiring decision → onboarding, with bias/privacy controls (extends PHILI)
4. L&D GM — competency gap → learning plan → content generation → assessment → certification → performance feedback (extends WILI, connects siblings when contracted)
5. Sales GM — lead → qualification → proposal → approval → handoff to B2B onboarding
6. Marketing GM — approved market intel, campaigns, content review, attribution, CRM feedback loop
7. ICT GM — incident, change, release, access, integration, platform health workflows

Each GM: bounded mission, tools, approval matrix, measurable KPIs, one e2e workflow. Uses same registry/contract as C1; no isolated scripts.

## HITL required

Human must decide whether Fraud GM financial-approval thresholds require separate legal sign-off.

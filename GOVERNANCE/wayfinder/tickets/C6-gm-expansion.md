---
id: C6-gm-expansion
type: grilling
status: closed
labels: [wayfinder:grilling]
blocked_by: [C5-vertical-slice, C2-control-plane]
blocks: [C7-sibling-integration, C8-production-pack]
---

## Question

In what bounded order do we ship the remaining GMs so each has mission/tools/approvals/KPIs and one e2e workflow — with "agent exists" explicitly rejected as done?

Order per Codex plan (implemented in C6):

1. **ANDY** — Compliance & Quality GM — QA sampling, policy checks, calibration, corrective actions, evidence packs (controls review of OPS/Sales/HR/Fraud decisions)
2. **NONO** — Fraud & Revenue Assurance GM — anomaly rules, leakage cases, investigation workflow, financial-action approval
3. **MAYA** — Marketing GM — approved market intel, campaigns, content review, attribution, CRM feedback loop
4. **LIZA** — Sales GM — lead → qualification → proposal → approval → handoff to B2B onboarding
5. **TOMY** — ICT GM — incident, change, release, access, integration, platform health workflows

Existing functional agents (unchanged identities):
- **SAMI** — Executive Coordinator / CEO
- **SUBY** — OPS GM (Operations Executive)
- **PHILI** — HR & Personnel GM (Personnel Director)
- **WILI** — L&D GM (Learning & Development Director)

Each GM: bounded mission, tools, approval matrix, measurable KPIs, one e2e workflow. Uses same registry/contract as C1; no isolated scripts.

**Implementation status (C6):**
- All 9 GMs are now `functional_agent` with canonical crew names (see `organization/role-catalog.yaml`)
- Canonical runtime identities: SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY
- Legacy class-based names retained as aliases: COMPLIANCE→ANDY, FRAUD→NONO, MARKETING→MAYA, SALES→LIZA, ICT→TOMY
- Agent classes preserved: `ComplianceQualityAgent`, `FraudAgent`, `MarketingAgent`, `SalesAgent`, `ICTAgent`

**Governance boundaries (C6):**
- **Functional LLM reasoning agents**: All 9 agents provide policy-grounded reasoning via Ollama (local-first). They recommend and prepare actions.
- **Governed catalog roles**: Each GM role in `organization/role-catalog.yaml` defines capabilities, tools, data domains, approval limits, SOD rules, and peer calls. Authorization uses stable `role_id` (e.g., `marketing_gm`), not agent names.
- **Available execution tools**: Only OPS (SUBY) has `wfm_engine`/`rta_engine`/`cx_engine`; HR (PHILI) has `personnel_engine`; L&D (WILI) has `wili_engine`. The 5 new GMs have **read-only/policy tools only** (`crm_engine_read`, `policy_engine`, `anomaly_engine`, etc.) — no autonomous execution tools for financial, personnel, compliance, ICT, or external-communication actions. All irreversible actions require approval per SOD.

**What C6 does NOT include:**
- No C7 sibling-project integration
- No new execution tools for Marketing, Sales, Compliance, ICT, Fraud
- No cockpit redesign
- No deployment, external services, real secrets
- No legacy routing removal

## HITL required

Human must decide whether Fraud GM (NONO) financial-approval thresholds require separate legal sign-off.

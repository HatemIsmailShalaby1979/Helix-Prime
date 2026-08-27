---
id: C1-organization-contracts
type: prototype
status: open
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

## Blocked

Until C0 closed — now unblocked (frontier).

---
id: C1a-capability-discovery
type: prototype
status: open
labels: [wayfinder:prototype]
blocked_by: [C1-organization-contracts]
blocks: [C2-control-plane]
---

## Question

How do we replace hardcoded `AGENT_CLASSES` / `ENGINE_MODULE_PATHS` name-only routing with capability-based discovery so tasks resolve by required capabilities, not agent names?

Current: `orchestration/orchestrator.py:172` `AGENT_CLASSES` (4) + `ENGINE_MODULE_PATHS` (6) + `ROUTING_KEYWORD_LOOKUP:166` `DEFAULT_AGENTS`. Target: registry where each agent/GM declares capabilities, tools, data access; orchestrator matches `TaskRequest.required_capabilities` to candidate agents, returns deterministic ownership with segregation-of-duties checks.

## Prototype expected

- `contracts/capabilities.yaml` or `organization/capabilities.json`
- `orchestration/registry.py` + `discovery.py` (capability index, tenant-aware)
- Tests: same request → deterministic owner; conflicting ownership → review queue not silent execution.

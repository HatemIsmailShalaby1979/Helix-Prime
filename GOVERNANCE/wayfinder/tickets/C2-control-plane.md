---
id: C2-control-plane
type: prototype
status: open
labels: [wayfinder:prototype]
blocked_by: [C1-organization-contracts, C1a-capability-discovery]
blocks: [C4-engine-productization, C6-gm-expansion]
---

## Question

What does the durable workflow/task runtime + event envelope + engine adapter interface look like so Helix can run a business process, not just a chat request?

Must deliver (C2 exit gate): states `proposed → validated → awaiting_approval → executing → succeeded/failed/compensated → closed`, durable correlation IDs, idempotency keys, deadlines, retries, cancellation, dead-letter/review queues, compensation hooks; event envelope + event store abstraction (local-first, replaceable); tool registry + adapter per engine that returns typed `TaskResult` + `EvidenceRef` not console output; policy evaluation before sensitive actions + cockpit approval capture; unified run history (timeline, handoffs, engine calls, decisions, approvals, failures, outputs). Prove: one WFM → OPS → Compliance review → HR/L&D escalation workflow from cockpit with restart/timeout/duplicate/denied-approval tests.

## Prototype expected

- `orchestration/workflow.py` or `control_plane/runtime.py` + `events.py` + `store.py` (JSONL/SQLite abstraction kept)
- `engines/*/adapter.py` (WFM + RTA first) returning typed results
- `cockpit/pages/workflow_timeline.py` or timeline seam
- Failure-injection tests.

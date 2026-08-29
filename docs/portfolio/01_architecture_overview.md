# 1. Architecture Overview

Helix Codex is a local-first, governance-driven system. It is **not** a single model;
it is an operating layer that coordinates governed workflows over business data and
records every decision and outcome. The same core is reused by every workflow
(call-centre, restaurant, future packs) — there is no separate platform per business.

## Core building blocks (all in-repo, verified)
| Concern | Module | Demonstrated behavior |
|---------|--------|------------------------|
| Identity & authorization | `security.identity`, `security.policy` | `Identity` (actor/type/tenant/client/role); deny-by-default authorization |
| Tenant isolation | `memory.governed_memory`, connectors | every record scoped by `tenant_id`/`client_id`; connectors enforce scope |
| Governance | `GOVERNANCE/` | constitutional + repo checks; `governance=PASS` |
| Connectors | `connectors/` | read-only first; `request_write` returns `executed=False` by design |
| Workflows | `control_plane.workflow` | typed state machine (proposed→…→closed); invalid transitions rejected |
| Approvals | `pilot.approval` | recommendation + approval (draft/approved/denied/rolled_back) with SOD |
| Evidence | `memory.governed_memory` provenance + `pilot/evidence_pack` | correlation ID, data mode, basis, sources on every record |
| Memory | `memory.governed_memory` | append-only, hash-chained ledger |
| Metrics | `pilot.metrics`, `capabilities/restaurant/metrics` | computed from governed records |
| Metacognition | `metacognition.improvement` | evidence-gated proposals; **never auto-deployed** |

## Data flow (one record's life)
```
connector (read-only, synthetic)
   -> workflow diagnosis (risk findings + recommended actions, with source refs)
   -> recommendation record (evidence refs) + approval draft (owner + state)
   -> manual approval (SOD: not self, not same-role)  [blocked during read-only period]
   -> governed memory (append-only, hash-chained, tenant-scoped)
   -> evidence pack (provenance, audit chain, metrics, approval summary)
```

## Capability-pack pattern
A capability pack (e.g. `capabilities/restaurant/`) adds only a business ontology,
roles, workflows, policies, classifications, metrics, fixtures, and a thin runtime that
**reuses** the core above. It does not fork the platform. The restaurant pack reuses
`security.identity`, `memory.governed_memory`, `connectors.base`, `control_plane.workflow`,
`pilot.approval`, `pilot.phases`, `pilot.consent`, and `metacognition.improvement`.

## Local-first boundary
The `cloud/` package defines provider-neutral interfaces with local in-memory adapters
and a **synthetic-only** cloud-demo profile. Cockpit, governed memory, and metacognition
are not migrated to cloud; local-first remains primary. See
[08_local_cloud_deployment.md](08_local_cloud_deployment.md).

## What is explicitly NOT claimed
- No live connectors, cloud services, or external writes are activated.
- The system is not characterized as autonomous or universal; it is a controlled,
  read-only-first, human-approved operating layer. Production readiness is
  **NOT_ESTABLISHED**.

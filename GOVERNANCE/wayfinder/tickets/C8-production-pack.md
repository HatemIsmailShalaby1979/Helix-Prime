---
id: C8-production-pack
type: task
status: closed
labels: [wayfinder:task]
blocked_by: [C5-vertical-slice, C3-security-observability]
blocks: []
closed: 2026-08-28
---

## Question

What evidence pack is sufficient to move from `controlled pilot` to `production candidate` — and who explicitly signs the go/no-go?

Per Codex plan §8 (2–4wks, P0 gate): package supported deployments (local single-node, private-network pilot, optional cloud profile); automate build, dependency lock, schema migration, backup/restore, rollback, health checks; run load/soak/failure/security/data-integrity/upgrade tests; establish SLOs (cockpit availability, workflow completion, engine latency, model timeout, recovery); create operator runbooks, on-call/escalation, user training, release checklist, incident process; run synthetic/consented pilot data before client data; produce release evidence pack and obtain explicit human approval.

Production gate (no critical security issue, reproducible deployment, tested recovery, complete audit trail, bounded autonomy, verified data isolation, owner per alert). Minimum evidence pack: architecture/data-flow diagrams, role/capability/approval matrix, versioned contracts + migration policy, test/coverage/load/security/failure-injection results, deployment/backup/restore/rollback/incident evidence, audit + data-isolation verification, pilot outcomes + explicit go/no-go decision.

## Blocked

Requires C5 slice + C3 audit/backup verification.

## Out of scope

Any claim before pack is accepted — per RELEASE_LABELS.md `production` requires this ticket closed + signed evidence.

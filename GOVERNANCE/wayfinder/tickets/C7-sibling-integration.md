---
id: C7-sibling-integration
type: research
status: open
labels: [wayfinder:research]
blocked_by: [C1-organization-contracts]
blocks: [C6-gm-expansion]
---

## Question

How do Helix Education, Study Studio, and L&D Command Center connect to Helix Prime Codex through versioned contracts rather than copied code or circular imports?

Target relationship (Codex plan §7):

```
Helix Prime Codex
├── Organization, identity, policy, workflow, evidence, executive coordination
├── Operations engines: WFM, RTA, CX, B2B, Personnel, CRM
├── Helix Education: learning-state + competency service (event-sourced, sealed assessment keys, adaptive paths)
├── Study Studio: learner/content experience + provider-agnostic AI runtime (neutral adapter)
└── L&D Command Center: content production/media/export/career tooling (typed pipeline, storage, connector hub, desktop shell)
```

Rules: Education owns competency state; Prime consumes/provides versioned events; Study Studio never a hidden dependency for OPS; LDCC exposed via versioned service/CLI after its Windows build + live integration gates; L&D GM/WILI is coordinator, siblings remain implementation boundaries.

First shared contract (draft without live coupling): `CompetencyGapDetected`, `LearningPlanRequested`, `LearningArtifactReady`, `AssessmentCompleted`, `CompetencyUpdated` — all with tenant/client, employee, source, version, evidence, correlation IDs.

## Research subagents

- Survey `../helix-education`, `../study-studio`, `../L&D Command Center` local contracts, data shapes, provider runtimes.
- Draft JSON schemas + contract tests (no live coupling yet).

## Note

Design in C1, implement after contracts are proven via file/event exchange locally.

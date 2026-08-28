---
id: C7-sibling-integration
type: feature
status: closed
labels: [wayfinder:feature]
blocked_by: [C1-organization-contracts]
blocks: []
closed: 2026-08-28
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

## Deliverables (implemented)

Contract-first, additive integration package under `integrations/`:

- `integrations/contracts.py` — versioned, validated events (schema `1.0`): `CompetencyGapDetected`, `LearningPlanRequested`, `LearningArtifactReady`, `AssessmentCompleted`, `CompetencyUpdated` (Education), `ContentGenerationRequested`, `ContentGenerationCompleted` (Study Studio), `MediaArtifactRequested`, `MediaArtifactReady`, `CareerLearningSignal` (L&D Command Center), `IntegrationError`. `create_integration_event` factory + `build_event_from_dict` round-trip; canonical constants (`VALID_SOURCE_SYSTEMS`, `VALID_TARGET_SYSTEMS`, `VALID_EVENT_TYPES`, `VALID_DATA_CLASSIFICATIONS`, `VALID_INTEGRATION_STATUSES`, `VALID_ERROR_CODES`, content/artifact/signal type sets). Events carry correlation/causation, idempotency, tenant/client isolation, actor/role, evidence refs, status, classification. Fail-closed on unknown source/target/event/classification.
- `integrations/transport.py` — replaceable transport seam: `Transport` ABC, `InMemoryTransport` + `FileTransport` (JSON Lines, durable), `TransportResult`, `TransportConfig` (bounded retry, dead-letter), `create_transport` factory. send/receive/acknowledge/reject/retry/dead-letter/idempotency.
- `integrations/helix_education.py` — `HelixEducationAdapter` (detect_competency_gap, request_learning_plan, submit_assessment_completion) + deterministic `FakeHelixEducation`.
- `integrations/study_studio.py` — `StudyStudioAdapter` (request_content_generation for lesson/quiz/podcast/glossary/podcast_script) + `FakeStudyStudio` (provider-abstraction preserved; no AI runtime copied).
- `integrations/ld_command_center.py` — `LDCommandCenterAdapter` (request_media_artifact + career signals) + `FakeLDCommandCenter`. Windows build pending documented; Linux build verified.
- `integrations/README.md` — ownership, boundaries, transport roadmap, limitations.
- `tests/test_c7_sibling_integration.py` — 44 tests: schema version, validation constants, event creation, tenant isolation, classification enforcement, source/target fail-closed, correlation/causation, idempotency, malformed payload rejection, in-memory transport (send/receive/ack/reject→dead-letter/retry), file transport, transport factory, all three adapters, all three fakes, redaction, structured logging, serialization round-trip, C1 regression.

## Verification

- 259 total tests green (previous 215 + 44 C7).
- compileall clean; ruff (E4, E7, E9, F) clean on `integrations/` + C7 test.
- No network requirement, no external service deployment, no secrets introduced.
- Governance preserved: requests are governed controller/task events; classification + authorization honored (fail-closed); audit/log integration verified.

## Note

- Design in C1, implement after contracts proven. Transport is local-first (in-memory/file); network transport deferred to C8 roadmap.
- L&D Command Center Windows build remains a sibling-side pending item and is not gated here.

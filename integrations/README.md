# Helix Prime Codex C7 — Sibling-Project Integration

## Overview

Helix Prime Codex connects to three sibling projects as specialized services:

```
Helix Prime Codex
├── Organization, identity, policy, workflow, evidence, GM coordination
├── Operations engines: WFM, RTA, CX, B2B, Personnel, CRM
├── Helix Education: event-sourced learning state, competency, assessments, adaptive paths
├── Study Studio: learner/content experience and provider-agnostic AI runtime
└── L&D Command Center: content production, media/export, career, L&D workbench workflows
```

## Contract-First Design

All integration communication uses versioned, validated events defined in `integrations/contracts.py`:

### Competency & Learning Events (Helix Education)
- `CompetencyGapDetected` — Prime → Education: gap detected for employee
- `LearningPlanRequested` — Prime → Education: request learning plan
- `LearningArtifactReady` — Education → Prime: artifact (plan, content) ready
- `AssessmentCompleted` — Education → Prime: assessment finished
- `CompetencyUpdated` — Education → Prime: competency level changed

### Content Generation Events (Study Studio)
- `ContentGenerationRequested` — Prime → Studio: request content (lesson, quiz, podcast, glossary)
- `ContentGenerationCompleted` — Studio → Prime: generation done (success/failure)

### Media & Export Events (L&D Command Center)
- `MediaArtifactRequested` — Prime → LDCC: request media/export (audio, PDF, PPTX, etc.)
- `MediaArtifactReady` — LDCC → Prime: artifact ready

### Career & Signals (L&D Command Center)
- `CareerLearningSignal` — LDCC → Prime: job match, skill gap, career path, etc.

### Error Handling
- `IntegrationError` — generic error for dead-letter/retry tracking

## Event Structure

Every event includes:
- Event ID, type, schema version (`1.0`)
- Source/target system (validated against canonical list)
- Tenant/client isolation
- Actor/role identity
- Correlation/causation IDs for traceability
- Idempotency key for deduplication
- Timestamp (ISO8601 UTC)
- Data classification (public/internal/client_confidential/personnel_sensitive/financial/regulated)
- Payload (typed per event type)
- Evidence references
- Status (pending/acknowledged/rejected/completed/dead_letter)
- Error info (code, message)

## Transport Layer

`integrations/transport.py` provides a replaceable transport abstraction:

- **InMemoryTransport** — deterministic, in-process, for tests and local dev
- **FileTransport** — durable JSON Lines on disk, for multi-process
- Both support: send, receive, acknowledge, reject, retry, dead-letter, idempotency, correlation/causation tracking

Transport is designed to be replaceable with HTTP, gRPC, or message bus without changing domain contracts.

## Adapters

Each sibling has a dedicated adapter in Helix Prime:

### Helix Education (`integrations/helix_education.py`)
- `detect_competency_gap(employee_id, gap_name, required_level, current_level)`
- `request_learning_plan(employee_id, gap_id, objectives, ...)`
- `submit_assessment_completion(employee_id, competency_id, score, passed)`
- Handles: `LearningArtifactReady`, `AssessmentCompleted`, `CompetencyUpdated`

### Study Studio (`integrations/study_studio.py`)
- `request_content_generation(request_id, content_type, topic, language, level, ...)`
- `content_type`: lesson, quiz, podcast, glossary, podcast_script
- Handles: `ContentGenerationCompleted`

### L&D Command Center (`integrations/ld_command_center.py`)
- `request_media_artifact(request_id, artifact_type, source_ref, format, ...)`
- `artifact_type`: audio, video, pdf, docx, pptx, xlsx, tts, podcast
- Handles: `MediaArtifactReady`, `CareerLearningSignal`

**Note**: L&D Command Center Windows build is pending (PyInstaller run on Windows side needed). Linux build is verified (dist/ldcc onefile, smoke-run clean vs live LM Studio).

## Governance Integration

Every integration request is governed by Helix Prime's control plane:

- **C1a Capability Ownership**: checked via `organization/capability_registry.py`
- **C3 Authorization**: checked via `security/policy.authorize()` with tenant/client isolation
- **C2 Workflow**: each request becomes a governed workflow/task
- **C3 Audit**: events emitted via `security/audit.py` hash chain
- **C3 Structured Logs**: emitted via `observability/logging.log_structured()`
- **Retry/Dead-Letter**: bounded retries with exponential backoff, then dead-letter
- **Replay**: deterministic via correlation/causation IDs
- **Idempotency**: duplicate idempotency keys do not duplicate work

## Testing

Deterministic fakes for each sibling (no network, no external services):
- `FakeHelixEducation` — simulates gap detection, learning plans, assessments
- `FakeStudyStudio` — simulates content generation
- `FakeLDCommandCenter` — simulates media/export artifacts

## Sibling Project Ownership & Boundaries

| System | Owns | Helix Prime Consumes/Provides |
|--------|------|-------------------------------|
| Helix Education | Event-sourced learning state, competency, progress, sealed assessment keys, adaptive paths | Consumes/provides versioned competency & workforce-learning events; does not copy Education's state core |
| Study Studio | Learner-facing experience, neutral provider runtime | Requests approved content or provider capability via adapter; must not become hidden dependency for core OPS |
| L&D Command Center | Content production, media/export, career, L&D workbench | Exposed through versioned service/CLI contracts after Windows build and live integration gates |

## Limitations & Roadmap

**Current (C7):**
- Local-first transport only (in-memory, file-based)
- Deterministic fakes for testing
- No network transport implemented
- L&D Command Center Windows build pending

**Future (C8+):**
- HTTP/gRPC transport implementations
- Network service deployment
- External identity provider integration
- Production message broker
- Real secrets management

## Files

```
integrations/
├── __init__.py           # Package exports
├── contracts.py          # Event definitions (CANONICAL)
├── transport.py          # Transport abstraction + implementations
├── helix_education.py    # Helix Education adapter + fake
├── study_studio.py       # Study Studio adapter + fake
├── ld_command_center.py  # L&D Command Center adapter + fake
└── README.md             # This file
```
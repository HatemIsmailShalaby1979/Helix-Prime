"""
Helix Prime Codex C7 — Sibling-Project Integration Package.

Provides contract-first, additive integration with:
- Helix Education: learning state, competency, assessments, adaptive paths
- Study Studio: content generation (lessons, quizzes, podcasts, glossaries)
- L&D Command Center: media/export, career signals, workbench workflows

Helix Prime remains the parent organization/control plane.
Sibling projects remain specialized services/products with their own boundaries.

Architecture:
```text
Helix Prime Codex
├── Organization, identity, policy, workflow, evidence, GM coordination
├── Operations engines: WFM, RTA, CX, B2B, Personnel, CRM
├── Helix Education: event-sourced learning state, competency, assessments
├── Study Studio: learner experience, provider-agnostic AI runtime
└── L&D Command Center: content production, media/export, career workflows
```

Integration Principles:
- Contract-first: versioned, validated events in integrations/contracts.py
- Adapter pattern: no direct coupling, no circular imports
- Transport abstraction: replaceable (in-memory, file, future HTTP/gRPC)
- Local-first: no network requirement, deterministic fakes for tests
- Governed: C1a capability ownership, C3 authorization, C2 workflow, C3 audit/log
- No secrets in source, fixtures, logs, or evidence
"""

from integrations.contracts import (
    IntegrationEvent,
    CompetencyGapDetected,
    LearningPlanRequested,
    LearningArtifactReady,
    AssessmentCompleted,
    CompetencyUpdated,
    ContentGenerationRequested,
    ContentGenerationCompleted,
    MediaArtifactRequested,
    MediaArtifactReady,
    CareerLearningSignal,
    IntegrationError,
    create_integration_event,
    build_event_from_dict,
    SCHEMA_VERSION,
    VALID_SOURCE_SYSTEMS,
    VALID_TARGET_SYSTEMS,
    VALID_EVENT_TYPES,
    VALID_DATA_CLASSIFICATIONS,
    VALID_INTEGRATION_STATUSES,
    VALID_ERROR_CODES,
    VALID_CONTENT_TYPES,
    VALID_ARTIFACT_TYPES,
    VALID_SIGNAL_TYPES,
)

from integrations.transport import (
    Transport,
    TransportResult,
    TransportConfig,
    InMemoryTransport,
    FileTransport,
    create_transport,
)

from integrations.helix_education import (
    HelixEducationAdapter,
    HelixEducationResponse,
    FakeHelixEducation,
)

from integrations.study_studio import (
    StudyStudioAdapter,
    StudyStudioResponse,
    FakeStudyStudio,
)

from integrations.ld_command_center import (
    LDCommandCenterAdapter,
    LDCommandCenterResponse,
    FakeLDCommandCenter,
)

__all__ = [
    # Contracts
    "IntegrationEvent",
    "CompetencyGapDetected",
    "LearningPlanRequested",
    "LearningArtifactReady",
    "AssessmentCompleted",
    "CompetencyUpdated",
    "ContentGenerationRequested",
    "ContentGenerationCompleted",
    "MediaArtifactRequested",
    "MediaArtifactReady",
    "CareerLearningSignal",
    "IntegrationError",
    "create_integration_event",
    "build_event_from_dict",
    "SCHEMA_VERSION",
    "VALID_SOURCE_SYSTEMS",
    "VALID_TARGET_SYSTEMS",
    "VALID_EVENT_TYPES",
    "VALID_DATA_CLASSIFICATIONS",
    "VALID_INTEGRATION_STATUSES",
    "VALID_ERROR_CODES",
    "VALID_CONTENT_TYPES",
    "VALID_ARTIFACT_TYPES",
    "VALID_SIGNAL_TYPES",
    # Transport
    "Transport",
    "TransportResult",
    "TransportConfig",
    "InMemoryTransport",
    "FileTransport",
    "create_transport",
    # Adapters
    "HelixEducationAdapter",
    "HelixEducationResponse",
    "FakeHelixEducation",
    "StudyStudioAdapter",
    "StudyStudioResponse",
    "FakeStudyStudio",
    "LDCommandCenterAdapter",
    "LDCommandCenterResponse",
    "FakeLDCommandCenter",
]
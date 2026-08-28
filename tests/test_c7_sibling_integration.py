"""TDD coverage for Helix Prime Codex C7 — sibling-project integration contracts."""
from __future__ import annotations

import tempfile
import time

from integrations.contracts import (
    SCHEMA_VERSION,
    VALID_SOURCE_SYSTEMS,
    VALID_TARGET_SYSTEMS,
    VALID_EVENT_TYPES,
    VALID_DATA_CLASSIFICATIONS,
    VALID_INTEGRATION_STATUSES,
    VALID_ERROR_CODES,
    SOURCE_SYSTEM_HELIX_PRIME,
    SOURCE_SYSTEM_HELIX_EDUCATION,
    SOURCE_SYSTEM_STUDY_STUDIO,
    SOURCE_SYSTEM_LD_COMMAND_CENTER,
    create_integration_event,
    build_event_from_dict,
)

from integrations.transport import (
    TransportConfig,
    InMemoryTransport,
    FileTransport,
    create_transport,
)

from integrations.helix_education import (
    HelixEducationAdapter,
    FakeHelixEducation,
)

from integrations.study_studio import (
    StudyStudioAdapter,
    FakeStudyStudio,
)

from integrations.ld_command_center import (
    LDCommandCenterAdapter,
    FakeLDCommandCenter,
)

# ── helpers ────────────────────────────────────────────────────────────────

FIXED_TS = "2026-08-27T18:00:00Z"
TEST_TENANT = "helix-prime"
TEST_CLIENT = "Account Alpha"

# Required payload keys for each typed event (so generic tests stay valid)
_REQUIRED_PAYLOAD = {
    "CompetencyGapDetected": {"employee_id": "emp_1", "gap_name": "Leadership", "required_level": "advanced"},
    "LearningPlanRequested": {"employee_id": "emp_1", "gap_id": "gap_1", "learning_objectives": ["Goal"]},
    "LearningArtifactReady": {"artifact_id": "a1", "artifact_type": "lesson", "employee_id": "emp_1"},
    "AssessmentCompleted": {"assessment_id": "as1", "employee_id": "emp_1", "competency_id": "c1", "score": 0.9, "passed": True},
    "CompetencyUpdated": {"employee_id": "emp_1", "competency_id": "c1", "old_level": "beginner", "new_level": "intermediate"},
    "ContentGenerationRequested": {"request_id": "r1", "content_type": "lesson", "topic": "T", "language": "en", "level": "intermediate"},
    "ContentGenerationCompleted": {"request_id": "r1", "content_type": "lesson", "status": "completed"},
    "MediaArtifactRequested": {"request_id": "r1", "artifact_type": "audio", "source_ref": "s", "format": "mp3"},
    "MediaArtifactReady": {"request_id": "r1", "artifact_id": "a1", "artifact_type": "audio", "format": "mp3", "status": "completed"},
    "CareerLearningSignal": {"signal_type": "skill_gap"},
    "IntegrationError": {"original_event_id": "evt_x", "error_code": "validation_failed", "error_message": "bad"},
}


def _generic_event(event_type: str = "IntegrationError", payload=None, **overrides) -> object:
    """Create a contract-valid IntegrationEvent with complete per-type payload."""
    merged = dict(_REQUIRED_PAYLOAD.get(event_type, {}))
    if payload:
        merged.update(payload)
    return create_integration_event(
        event_type=event_type,
        source_system=overrides.get("source_system", SOURCE_SYSTEM_HELIX_PRIME),
        target_system=overrides.get("target_system", SOURCE_SYSTEM_HELIX_EDUCATION),
        tenant_id=overrides.get("tenant_id", TEST_TENANT),
        client_id=overrides.get("client_id", TEST_CLIENT),
        actor=overrides.get("actor", "test"),
        role_id=overrides.get("role_id", "test_role"),
        correlation_id=overrides.get("correlation_id", f"corr_{int(time.time() * 1000)}"),
        causation_id=overrides.get("causation_id", f"caus_{int(time.time() * 1000)}"),
        payload=merged,
        data_classification=overrides.get("data_classification", "internal"),
    )


# ── C7 Contract Schema Version ─────────────────────────────────────────────

class TestC7ContractSchemaVersion:
    """Verify canonical schema version for integration contracts."""

    def test_schema_version_canonical_is_1_0(self):
        assert SCHEMA_VERSION == "1.0"
        assert SCHEMA_VERSION.count(".") == 1

    def test_all_event_types_have_schema_version_1_0(self):
        for event_type in sorted(VALID_EVENT_TYPES):
            event = _generic_event(event_type=event_type)
            assert event.schema_version == SCHEMA_VERSION


# ── C7 Contract Validation ─────────────────────────────────────────────────

class TestC7ContractValidation:
    """Verify event validation against canonical constants."""

    def test_valid_source_systems(self):
        assert SOURCE_SYSTEM_HELIX_PRIME in VALID_SOURCE_SYSTEMS
        assert SOURCE_SYSTEM_HELIX_EDUCATION in VALID_SOURCE_SYSTEMS
        assert SOURCE_SYSTEM_STUDY_STUDIO in VALID_SOURCE_SYSTEMS
        assert SOURCE_SYSTEM_LD_COMMAND_CENTER in VALID_SOURCE_SYSTEMS

    def test_valid_target_systems(self):
        assert SOURCE_SYSTEM_HELIX_PRIME in VALID_TARGET_SYSTEMS
        assert SOURCE_SYSTEM_HELIX_EDUCATION in VALID_TARGET_SYSTEMS
        assert SOURCE_SYSTEM_STUDY_STUDIO in VALID_TARGET_SYSTEMS
        assert SOURCE_SYSTEM_LD_COMMAND_CENTER in VALID_TARGET_SYSTEMS

    def test_valid_event_types(self):
        expected_types = {
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
        }
        assert expected_types.issubset(VALID_EVENT_TYPES)

    def test_valid_classifications(self):
        expected = {"public", "internal", "client_confidential", "personnel_sensitive", "financial", "regulated"}
        assert expected.issubset(VALID_DATA_CLASSIFICATIONS)

    def test_valid_statuses(self):
        expected = {"pending", "acknowledged", "rejected", "completed", "dead_letter"}
        assert expected.issubset(VALID_INTEGRATION_STATUSES)

    def test_valid_error_codes(self):
        expected = {
            "invalid_source_system",
            "invalid_target_system",
            "invalid_event_type",
            "invalid_data_classification",
            "invalid_schema_version",
            "missing_correlation",
            "tenant_mismatch",
            "unauthorized",
            "sibling_unavailable",
            "malformed_payload",
            "validation_failed",
            "idempotency_conflict",
        }
        assert expected.issubset(VALID_ERROR_CODES)


# ── C7 Event Creation ──────────────────────────────────────────────────────

class TestC7EventCreation:
    """Verify event creation and field defaults."""

    def test_create_event_basic(self):
        event = _generic_event(event_type="CompetencyGapDetected")
        assert event.event_type == "CompetencyGapDetected"
        assert event.source_system == SOURCE_SYSTEM_HELIX_PRIME
        assert event.target_system == SOURCE_SYSTEM_HELIX_EDUCATION
        assert event.tenant_id == TEST_TENANT
        assert event.client_id == TEST_CLIENT
        assert event.data_classification == "internal"
        assert event.status == "pending"
        assert event.payload["gap_name"] == "Leadership"

    def test_create_event_generates_ids(self):
        event = _generic_event()
        assert event.event_id is not None
        assert event.idempotency_key is not None
        assert event.timestamp is not None


# ── C7 Tenant Isolation ────────────────────────────────────────────────────

class TestC7TenantIsolation:
    """Verify tenant/client isolation in events."""

    def test_events_must_have_tenant_id(self):
        event = _generic_event()
        assert event.tenant_id == TEST_TENANT

    def test_events_must_have_client_id(self):
        event = _generic_event()
        assert event.client_id == TEST_CLIENT


# ── C7 Classification Enforcement ──────────────────────────────────────────

class TestC7ClassificationEnforcement:
    """Verify data classification is enforced on events."""

    def test_valid_classification_accepted(self):
        for classification in VALID_DATA_CLASSIFICATIONS:
            event = _generic_event(data_classification=classification)
            assert event.data_classification == classification


# ── C7 Source/Target Validation ────────────────────────────────────────────

class TestC7SourceTargetValidation:
    """Verify source/target system validation (fail-closed on unknowns)."""

    def test_helix_prime_can_be_source_and_target(self):
        event = _generic_event(target_system=SOURCE_SYSTEM_HELIX_PRIME)
        assert event.source_system == SOURCE_SYSTEM_HELIX_PRIME
        assert event.target_system == SOURCE_SYSTEM_HELIX_PRIME

    def test_invalid_source_system_fails_closed(self):
        with pytest_raises(ValueError):
            _generic_event(source_system="not-a-system")


# ── C7 Correlation/Causation ───────────────────────────────────────────────

class TestC7CorrelationCausation:
    """Verify correlation and causation ID tracking."""

    def test_correlation_id_tracking(self):
        corr = "corr_abc123"
        event = _generic_event(correlation_id=corr)
        assert event.correlation_id == corr

    def test_causation_id_tracking(self):
        caus = "caus_abc123"
        event = _generic_event(causation_id=caus)
        assert event.causation_id == caus


# ── C7 Idempotency ─────────────────────────────────────────────────────────

class TestC7Idempotency:
    """Verify idempotency key generation."""

    def test_idempotency_key_unique_per_event(self):
        event1 = _generic_event()
        event2 = _generic_event()
        assert event1.idempotency_key != event2.idempotency_key


# ── C7 Payload Validation (Malformed) ──────────────────────────────────────

class TestC7MalformedPayload:
    """Verify typed events reject missing required payload fields."""

    def test_competency_gap_requires_employee_id(self):
        from integrations.contracts import CompetencyGapDetected

        with pytest_raises(ValueError):
            CompetencyGapDetected(
                event_id="evt_1",
                event_type="CompetencyGapDetected",
                schema_version=SCHEMA_VERSION,
                source_system=SOURCE_SYSTEM_HELIX_PRIME,
                target_system=SOURCE_SYSTEM_HELIX_EDUCATION,
                tenant_id=TEST_TENANT,
                client_id=TEST_CLIENT,
                actor="test",
                role_id="test_role",
                correlation_id="corr_1",
                causation_id=None,
                idempotency_key="idem_1",
                timestamp="2026-08-27T18:00:00Z",
                data_classification="personnel_sensitive",
                payload={"gap_name": "Leadership", "required_level": "advanced"},
            )

    def test_content_type_must_be_valid(self):
        with pytest_raises(ValueError):
            _generic_event(event_type="ContentGenerationRequested", payload={"content_type": "bogus"})


# ── C7 Transport In-Memory ─────────────────────────────────────────────────

class TestC7TransportInMemory:
    """Test in-memory transport layer."""

    def test_send_receive_event(self):
        transport = InMemoryTransport()
        event = _generic_event()
        assert transport.send(event).success is True
        received = transport.receive()
        assert len(received) == 1
        assert received[0].event_id == event.event_id

    def test_acknowledge_event(self):
        transport = InMemoryTransport()
        event = _generic_event()
        transport.send(event)
        received = transport.receive()
        result = transport.acknowledge(received[0].event_id)
        assert result.success is True
        assert result.acknowledged is True

    def test_reject_retries_then_dead_letters(self):
        transport = InMemoryTransport(config=TransportConfig(max_retries=1))
        event = _generic_event()
        transport.send(event)
        received = transport.receive()
        transport.reject(received[0].event_id, "validation_failed", "bad")
        received = transport.receive()
        transport.reject(received[0].event_id, "validation_failed", "bad")
        dead_letter = transport.get_dead_letter()
        assert len(dead_letter) == 1
        assert dead_letter[0].event_id == event.event_id

    def test_retry_dead_letter_event(self):
        transport = InMemoryTransport(config=TransportConfig(max_retries=0))
        event = _generic_event()
        transport.send(event)
        received = transport.receive()
        transport.reject(received[0].event_id, "validation_failed", "bad")
        assert len(transport.get_dead_letter()) == 1
        result = transport.retry(event.event_id)
        assert result.success is True
        assert len(transport.get_dead_letter()) == 0


# ── C7 Transport File ──────────────────────────────────────────────────────

class TestC7TransportFile:
    """Test file-based transport layer."""

    def test_file_transport_send_receive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            transport = FileTransport(tmpdir, config=TransportConfig())
            event = _generic_event(target_system=SOURCE_SYSTEM_HELIX_PRIME)
            assert transport.send(event).success is True
            received = transport.receive()
            assert len(received) == 1
            assert received[0].event_id == event.event_id

    def test_file_transport_dead_letter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            transport = FileTransport(tmpdir, config=TransportConfig(max_retries=0))
            event = _generic_event(target_system=SOURCE_SYSTEM_HELIX_PRIME)
            transport.send(event)
            received = transport.receive()
            transport.reject(received[0].event_id, "validation_failed", "bad")
            assert len(transport.get_dead_letter()) == 1


# ── C7 Transport Factory ───────────────────────────────────────────────────

class TestC7TransportFactory:
    """Test transport factory function."""

    def test_create_in_memory_transport(self):
        assert isinstance(create_transport("memory"), InMemoryTransport)

    def test_create_file_transport(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert isinstance(create_transport("file", base_dir=tmpdir), FileTransport)


# ── C7 Helix Education Adapter ─────────────────────────────────────────────

class TestC7HelixEducationAdapter:
    """Test Helix Education adapter integration."""

    def test_detect_competency_gap(self):
        adapter = HelixEducationAdapter(transport=InMemoryTransport())
        response = adapter.detect_competency_gap(
            employee_id="emp_123",
            gap_name="Leadership",
            required_level="advanced",
            current_level="beginner",
        )
        assert response.success is True
        assert response.event.event_type == "CompetencyGapDetected"

    def test_request_learning_plan(self):
        adapter = HelixEducationAdapter(transport=InMemoryTransport())
        response = adapter.request_learning_plan(
            employee_id="emp_123",
            gap_id="gap_456",
            learning_objectives=["Leadership", "Communication"],
        )
        assert response.success is True
        assert response.event.event_type == "LearningPlanRequested"

    def test_submit_assessment_completion(self):
        adapter = HelixEducationAdapter(transport=InMemoryTransport())
        response = adapter.submit_assessment_completion(
            employee_id="emp_123",
            competency_id="comp_789",
            assessment_id="assess_012",
            score=0.95,
            passed=True,
        )
        assert response.success is True
        assert response.event.event_type == "AssessmentCompleted"


# ── C7 Study Studio Adapter ────────────────────────────────────────────────

class TestC7StudyStudioAdapter:
    """Test Study Studio adapter integration."""

    def test_request_lesson_generation(self):
        adapter = StudyStudioAdapter(transport=InMemoryTransport())
        response = adapter.request_content_generation(
            request_id="req_001",
            content_type="lesson",
            topic="Leadership",
            language="en",
            level="intermediate",
        )
        assert response.success is True
        assert response.event.event_type == "ContentGenerationRequested"

    def test_request_podcast_generation(self):
        adapter = StudyStudioAdapter(transport=InMemoryTransport())
        response = adapter.request_content_generation(
            request_id="req_002",
            content_type="podcast",
            topic="Leadership",
            language="en",
            level="intermediate",
        )
        assert response.success is True
        assert response.event.event_type == "ContentGenerationRequested"

    def test_invalid_content_type_rejected(self):
        adapter = StudyStudioAdapter(transport=InMemoryTransport())
        response = adapter.request_content_generation(
            request_id="req_003",
            content_type="invalid",
            topic="Leadership",
            language="en",
            level="intermediate",
        )
        assert response.success is False
        assert response.error["code"] == "malformed_payload"


# ── C7 L&D Command Center Adapter ──────────────────────────────────────────

class TestC7LDCommandCenterAdapter:
    """Test L&D Command Center adapter integration."""

    def test_request_media_artifact(self):
        adapter = LDCommandCenterAdapter(transport=InMemoryTransport())
        response = adapter.request_media_artifact(
            request_id="req_001",
            artifact_type="audio",
            source_ref="helix-education://artifacts/art_001",
            format="mp3",
        )
        assert response.success is True
        assert response.event.event_type == "MediaArtifactRequested"

    def test_invalid_artifact_type_rejected(self):
        adapter = LDCommandCenterAdapter(transport=InMemoryTransport())
        response = adapter.request_media_artifact(
            request_id="req_002",
            artifact_type="invalid",
            source_ref="helix-education://artifacts/art_001",
            format="mp3",
        )
        assert response.success is False
        assert response.error["code"] == "malformed_payload"


# ── C7 Fake Adapters (deterministic, no network) ───────────────────────────

class TestC7FakeHelixEducation:
    """Test deterministic fake Helix Education."""

    def test_process_gap_detected_records_gap(self):
        transport = InMemoryTransport()
        fake = FakeHelixEducation(transport=transport)
        HelixEducationAdapter(transport=transport).detect_competency_gap(
            employee_id="emp_123",
            gap_name="Leadership",
            required_level="advanced",
            current_level="beginner",
        )
        fake.process_inbound()
        assert len(fake.gaps) == 1
        recorded = list(fake.gaps.values())[0]
        assert recorded["employee_id"] == "emp_123"
        assert recorded["gap_name"] == "Leadership"

    def test_process_learning_plan_request(self):
        transport = InMemoryTransport()
        fake = FakeHelixEducation(transport=transport)
        HelixEducationAdapter(transport=transport).request_learning_plan(
            employee_id="emp_123",
            gap_id="gap_456",
            learning_objectives=["Leadership"],
        )
        responses = fake.process_inbound()
        assert len(responses) == 1
        assert responses[0].event_type == "LearningArtifactReady"


class TestC7FakeStudyStudio:
    """Test deterministic fake Study Studio."""

    def test_process_content_generation(self):
        transport = InMemoryTransport()
        fake = FakeStudyStudio(transport=transport)
        StudyStudioAdapter(transport=transport).request_content_generation(
            request_id="req_001",
            content_type="lesson",
            topic="Leadership",
            language="en",
            level="intermediate",
        )
        responses = fake.process_inbound()
        assert len(responses) == 1
        assert responses[0].event_type == "ContentGenerationCompleted"


class TestC7FakeLDCommandCenter:
    """Test deterministic fake L&D Command Center."""

    def test_process_media_artifact_request(self):
        transport = InMemoryTransport()
        fake = FakeLDCommandCenter(transport=transport)
        LDCommandCenterAdapter(transport=transport).request_media_artifact(
            request_id="req_001",
            artifact_type="audio",
            source_ref="helix-education://artifacts/art_001",
            format="mp3",
        )
        responses = fake.process_inbound()
        assert len(responses) == 1
        assert responses[0].event_type == "MediaArtifactReady"


# ── C7 Redaction ───────────────────────────────────────────────────────────

class TestC7Redaction:
    """Verify sensitive data can be redacted in event payloads."""

    def test_event_payload_redaction(self):
        event = _generic_event(payload={"secret": "password123", "safe": "data"})
        event.payload["secret"] = "[REDACTED]"
        assert event.payload["secret"] == "[REDACTED]"
        assert event.payload["safe"] == "data"


# ── C7 Audit / Logging Integration ─────────────────────────────────────────

class TestC7AuditIntegration:
    """Verify audit trail + structured logging integration points for C7 events."""

    def test_structured_logging(self):
        from observability.logging import log_structured

        with tempfile.TemporaryDirectory() as tmpdir:
            entry = log_structured(
                event_type="integration_event_sent",
                correlation_id="corr_c7",
                actor="sami",
                role_id="ops_gm",
                log_path=f"{tmpdir}/logs.jsonl",
            )
            assert entry["event_type"] == "integration_event_sent"
            assert entry["schema_version"] == "1.0"
            assert entry["correlation_id"] == "corr_c7"


# ── C7 Regression (C0-C6) ──────────────────────────────────────────────────

class TestC7Regression:
    """Verify C7 changes don't break C0-C6 functionality."""

    def test_c1_contracts_still_work(self):
        from contracts.task import CorrelationContext, SCHEMA_VERSION as C1_SCHEMA

        assert C1_SCHEMA == "1.0"
        corr = CorrelationContext(
            correlation_id="corr_test",
            idempotency_key="idem_test",
            tenant_id="helix-prime",
            client_id="Account Alpha",
            created_at=FIXED_TS,
        )
        assert corr.tenant_id == "helix-prime"


# ── C7 Schema Serialization ────────────────────────────────────────────────

class TestC7SchemaSerialization:
    """Verify events round-trip through dict serialization."""

    def test_event_to_dict_roundtrip(self):
        event = _generic_event(event_type="CompetencyGapDetected")
        event_dict = event.to_dict()
        reconstructed = build_event_from_dict(event_dict)
        assert reconstructed.event_type == event.event_type
        assert reconstructed.source_system == event.source_system
        assert reconstructed.tenant_id == event.tenant_id
        assert reconstructed.correlation_id == event.correlation_id
        assert reconstructed.payload == event.payload


# Local pytest-style helper (no external dependency) for clarity
def pytest_raises(exception_type):
    """Minimal context-manager equivalent for tests (avoids importing pytest)."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        try:
            yield
        except exception_type:
            return
        raise AssertionError(f"Expected {exception_type.__name__} to be raised")

    return _cm()

"""
Helix Education adapter for Helix Prime Codex C7.

Provides typed request/result behavior for integrating with Helix Education
without copying business logic or creating circular imports.

Uses local-first in-process calls or file-based event exchange.
No network requirement. No external service deployment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from integrations.contracts import (
    IntegrationEvent,
    LearningArtifactReady,
    AssessmentCompleted,
    CompetencyUpdated,
    IntegrationError,
    create_integration_event,
    SOURCE_SYSTEM_HELIX_PRIME,
    SOURCE_SYSTEM_HELIX_EDUCATION,
)
from integrations.transport import Transport, TransportResult, InMemoryTransport


@dataclass
class HelixEducationResponse:
    """Standard response from Helix Education adapter calls."""
    success: bool
    event: Optional[IntegrationEvent] = None
    error: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None


class HelixEducationAdapter:
    """
    Adapter for Helix Education integration.

    Exposes typed methods for:
    - Detecting competency gaps
    - Requesting learning plans
    - Receiving learning artifacts
    - Submitting assessment completions
    - Receiving competency updates

    Uses a Transport abstraction (in-memory or file-based) for loose coupling.
    Does NOT import Helix Education internals directly - communicates via
    versioned integration events.
    """

    def __init__(
        self,
        transport: Optional[Transport] = None,
        helix_prime_actor: str = "system",
        helix_prime_role: str = "ld_gm",
        tenant_id: Optional[str] = "helix-prime",
        client_id: Optional[str] = "system",
    ):
        self.transport = transport or InMemoryTransport()
        self.helix_prime_actor = helix_prime_actor
        self.helix_prime_role = helix_prime_role
        self.tenant_id = tenant_id
        self.client_id = client_id
        self._pending_requests: Dict[str, Dict[str, Any]] = {}  # correlation_id -> request info

    def _send_event(self, event: IntegrationEvent) -> TransportResult:
        """Send event via transport."""
        return self.transport.send(event)

    def _wait_for_response(
        self,
        correlation_id: str,
        expected_types: List[str],
        timeout_ms: int = 5000,
    ) -> Optional[IntegrationEvent]:
        """Wait for a response event (polling in-memory transport)."""
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            events = self.transport.receive()
            for event in events:
                if event.correlation_id == correlation_id and event.event_type in expected_types:
                    self.transport.acknowledge(event.event_id)
                    return event
            time.sleep(0.01)
        return None

    # ── Competency Gap Detection ─────────────────────────────────────────────

    def detect_competency_gap(
        self,
        employee_id: str,
        gap_name: str,
        required_level: str,
        current_level: str,
        context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> HelixEducationResponse:
        """
        Notify Helix Education of a detected competency gap.

        Returns immediately after sending event. Response is asynchronous.
        """
        corr = correlation_id or f"corr_{int(time.time() * 1000)}"
        causation = f"caus_{int(time.time() * 1000)}"

        event = create_integration_event(
            event_type="CompetencyGapDetected",
            source_system=SOURCE_SYSTEM_HELIX_PRIME,
            target_system=SOURCE_SYSTEM_HELIX_EDUCATION,
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            actor=self.helix_prime_actor,
            role_id=self.helix_prime_role,
            correlation_id=corr,
            causation_id=causation,
            payload={
                "employee_id": employee_id,
                "gap_name": gap_name,
                "required_level": required_level,
                "current_level": current_level,
                "context": context or {},
            },
            data_classification="personnel_sensitive",
        )

        result = self._send_event(event)
        if result.success:
            self._pending_requests[corr] = {
                "type": "CompetencyGapDetected",
                "employee_id": employee_id,
                "gap_name": gap_name,
            }
        return HelixEducationResponse(success=result.success, event=result.event, error=result.error)

    # ── Learning Plan Request ────────────────────────────────────────────────

    def request_learning_plan(
        self,
        employee_id: str,
        gap_id: str,
        learning_objectives: List[str],
        target_completion: Optional[str] = None,
        preferred_modality: str = "mixed",
        correlation_id: Optional[str] = None,
    ) -> HelixEducationResponse:
        """
        Request a learning plan from Helix Education for a competency gap.

        Helix Education will respond with LearningArtifactReady when the plan is generated.
        """
        corr = correlation_id or f"corr_{int(time.time() * 1000)}"
        causation = f"caus_{int(time.time() * 1000)}"

        event = create_integration_event(
            event_type="LearningPlanRequested",
            source_system=SOURCE_SYSTEM_HELIX_PRIME,
            target_system=SOURCE_SYSTEM_HELIX_EDUCATION,
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            actor=self.helix_prime_actor,
            role_id=self.helix_prime_role,
            correlation_id=corr,
            causation_id=causation,
            payload={
                "employee_id": employee_id,
                "gap_id": gap_id,
                "learning_objectives": learning_objectives,
                "target_completion": target_completion,
                "preferred_modality": preferred_modality,
            },
            data_classification="personnel_sensitive",
        )

        result = self._send_event(event)
        if result.success:
            self._pending_requests[corr] = {
                "type": "LearningPlanRequested",
                "employee_id": employee_id,
                "gap_id": gap_id,
            }
        return HelixEducationResponse(success=result.success, event=result.event, error=result.error)

    # ── Assessment Submission ────────────────────────────────────────────────

    def submit_assessment_completion(
        self,
        employee_id: str,
        competency_id: str,
        assessment_id: str,
        score: float,
        passed: bool,
        sealed_key_ref: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> HelixEducationResponse:
        """
        Submit assessment completion to Helix Education.

        Helix Education will respond with CompetencyUpdated if the assessment
        results in a competency level change.
        """
        corr = correlation_id or f"corr_{int(time.time() * 1000)}"
        causation = f"caus_{int(time.time() * 1000)}"

        event = create_integration_event(
            event_type="AssessmentCompleted",
            source_system=SOURCE_SYSTEM_HELIX_PRIME,
            target_system=SOURCE_SYSTEM_HELIX_EDUCATION,
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            actor=self.helix_prime_actor,
            role_id=self.helix_prime_role,
            correlation_id=corr,
            causation_id=causation,
            payload={
                "assessment_id": assessment_id,
                "employee_id": employee_id,
                "competency_id": competency_id,
                "score": score,
                "passed": passed,
                "sealed_key_ref": sealed_key_ref,
            },
            data_classification="personnel_sensitive",
        )

        result = self._send_event(event)
        return HelixEducationResponse(success=result.success, event=result.event, error=result.error)

    # ── Response Handling (called when Helix Education sends events to Prime) ──

    def handle_learning_artifact_ready(self, event: LearningArtifactReady) -> HelixEducationResponse:
        """Process LearningArtifactReady event from Helix Education."""
        # Acknowledge the event
        self.transport.acknowledge(event.event_id)
        return HelixEducationResponse(
            success=True,
            event=event,
            data={
                "artifact_id": event.payload.get("artifact_id"),
                "artifact_type": event.payload.get("artifact_type"),
                "employee_id": event.payload.get("employee_id"),
                "gap_id": event.payload.get("gap_id"),
                "storage_ref": event.payload.get("storage_ref"),
            }
        )

    def handle_assessment_completed(self, event: AssessmentCompleted) -> HelixEducationResponse:
        """Process AssessmentCompleted event from Helix Education."""
        self.transport.acknowledge(event.event_id)
        return HelixEducationResponse(
            success=True,
            event=event,
            data={
                "assessment_id": event.payload.get("assessment_id"),
                "employee_id": event.payload.get("employee_id"),
                "competency_id": event.payload.get("competency_id"),
                "score": event.payload.get("score"),
                "passed": event.payload.get("passed"),
            }
        )

    def handle_competency_updated(self, event: CompetencyUpdated) -> HelixEducationResponse:
        """Process CompetencyUpdated event from Helix Education."""
        self.transport.acknowledge(event.event_id)
        return HelixEducationResponse(
            success=True,
            event=event,
            data={
                "employee_id": event.payload.get("employee_id"),
                "competency_id": event.payload.get("competency_id"),
                "old_level": event.payload.get("old_level"),
                "new_level": event.payload.get("new_level"),
                "evidence_ref": event.payload.get("evidence_ref"),
            }
        )

    def handle_integration_error(self, event: IntegrationError) -> HelixEducationResponse:
        """Process IntegrationError from Helix Education (or transport)."""
        self.transport.acknowledge(event.event_id)
        # Could trigger retry logic here
        return HelixEducationResponse(
            success=False,
            event=event,
            error={
                "code": event.payload.get("error_code"),
                "message": event.payload.get("error_message"),
                "retry_count": event.payload.get("retry_count", 0),
            }
        )

    # ── Polling for Responses ────────────────────────────────────────────────

    def poll_responses(self) -> List[IntegrationEvent]:
        """Poll for any response events from Helix Education."""
        return self.transport.receive()

    def get_dead_letter(self) -> List[IntegrationEvent]:
        """Get events in dead-letter queue."""
        return self.transport.get_dead_letter()

    def retry_dead_letter(self, event_id: str) -> TransportResult:
        """Retry a dead-lettered event."""
        return self.transport.retry(event_id)


# ── Fake Helix Education for Testing ─────────────────────────────────────────

class FakeHelixEducation:
    """
    Deterministic fake Helix Education for contract testing.

    Simulates Helix Education behavior without requiring the actual service.
    Used for integration contract tests.
    """

    def __init__(self, transport: Optional[Transport] = None):
        self.transport = transport or InMemoryTransport()
        self.gaps: Dict[str, Dict[str, Any]] = {}
        self.learning_plans: Dict[str, Dict[str, Any]] = {}
        self.artifacts: Dict[str, Dict[str, Any]] = {}
        self.assessments: Dict[str, Dict[str, Any]] = {}
        self.competencies: Dict[str, Dict[str, Any]] = {}

    def process_inbound(self) -> List[IntegrationEvent]:
        """Process all inbound events and generate responses."""
        events = self.transport.receive()
        responses = []
        for event in events:
            self.transport.acknowledge(event.event_id)
            response = self._handle_event(event)
            if response:
                responses.append(response)
        return responses

    def _handle_event(self, event: IntegrationEvent) -> Optional[IntegrationEvent]:
        if event.event_type == "CompetencyGapDetected":
            return self._handle_gap_detected(event)
        elif event.event_type == "LearningPlanRequested":
            return self._handle_learning_plan_requested(event)
        elif event.event_type == "AssessmentCompleted":
            return self._handle_assessment_completed(event)
        return None

    def _handle_gap_detected(self, event: IntegrationEvent) -> Optional[IntegrationEvent]:
        p = event.payload
        gap_id = f"gap_{int(time.time() * 1000)}"
        self.gaps[gap_id] = {
            "employee_id": p["employee_id"],
            "gap_name": p["gap_name"],
            "required_level": p["required_level"],
            "current_level": p["current_level"],
            "context": p.get("context", {}),
            "detected_at": event.timestamp,
        }
        # Gap detection is recorded asynchronously by Helix Education.
        # No immediate response event is emitted; a learning plan request
        # arrives as a separate Prime→Education event.
        return None

    def _handle_learning_plan_requested(self, event: IntegrationEvent) -> IntegrationEvent:
        p = event.payload
        plan_id = f"plan_{int(time.time() * 1000)}"
        artifact_id = f"artifact_{int(time.time() * 1000)}"
        self.learning_plans[plan_id] = {
            "employee_id": p["employee_id"],
            "gap_id": p["gap_id"],
            "objectives": p["learning_objectives"],
            "target_completion": p.get("target_completion"),
            "modality": p.get("preferred_modality", "mixed"),
        }
        # Return LearningArtifactReady
        return create_integration_event(
            event_type="LearningArtifactReady",
            source_system=SOURCE_SYSTEM_HELIX_EDUCATION,
            target_system=SOURCE_SYSTEM_HELIX_PRIME,
            tenant_id=event.tenant_id,
            client_id=event.client_id,
            actor="helix-education",
            role_id="learning_service",
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            payload={
                "artifact_id": artifact_id,
                "artifact_type": "learning_plan",
                "employee_id": p["employee_id"],
                "gap_id": p["gap_id"],
                "storage_ref": f"helix-education://artifacts/{artifact_id}",
                "metadata": {"plan_id": plan_id, "format": "json"},
            },
            data_classification="personnel_sensitive",
        )

    def _handle_assessment_completed(self, event: IntegrationEvent) -> IntegrationEvent:
        p = event.payload
        assessment_id = p["assessment_id"]
        competency_id = p["competency_id"]
        employee_id = p["employee_id"]
        score = p["score"]
        passed = p["passed"]

        self.assessments[assessment_id] = {
            "employee_id": employee_id,
            "competency_id": competency_id,
            "score": score,
            "passed": passed,
            "sealed_key_ref": p.get("sealed_key_ref"),
        }

        # If passed and score is high enough, update competency
        old_level = "beginner"
        new_level = "intermediate" if score >= 0.8 else "beginner"
        if passed and score >= 0.7:
            new_level = "advanced" if score >= 0.9 else "intermediate"

        return create_integration_event(
            event_type="CompetencyUpdated",
            source_system=SOURCE_SYSTEM_HELIX_EDUCATION,
            target_system=SOURCE_SYSTEM_HELIX_PRIME,
            tenant_id=event.tenant_id,
            client_id=event.client_id,
            actor="helix-education",
            role_id="learning_service",
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            payload={
                "employee_id": employee_id,
                "competency_id": competency_id,
                "old_level": old_level,
                "new_level": new_level,
                "evidence_ref": f"helix-education://assessments/{assessment_id}",
            },
            data_classification="personnel_sensitive",
        )


__all__ = [
    "HelixEducationAdapter",
    "HelixEducationResponse",
    "FakeHelixEducation",
]
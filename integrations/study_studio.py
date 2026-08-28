"""
Study Studio adapter for Helix Prime Codex C7.

Provides typed request/result behavior for integrating with Study Studio
for content generation (lessons, quizzes, podcasts, glossaries).

Uses local-first in-process calls or file-based event exchange.
No network requirement. No external service deployment.
Does NOT copy Study Studio's AI runtime into Helix Prime.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from integrations.contracts import (
    IntegrationEvent,
    ContentGenerationCompleted,
    IntegrationError,
    create_integration_event,
    SOURCE_SYSTEM_HELIX_PRIME,
    SOURCE_SYSTEM_STUDY_STUDIO,
)
from integrations.transport import Transport, TransportResult, InMemoryTransport


@dataclass
class StudyStudioResponse:
    """Standard response from Study Studio adapter calls."""
    success: bool
    event: Optional[IntegrationEvent] = None
    error: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None


class StudyStudioAdapter:
    """
    Adapter for Study Studio content generation integration.

    Exposes typed methods for:
    - Requesting content generation (lesson, quiz, podcast, glossary, podcast_script)
    - Receiving generation completion events

    Uses a Transport abstraction for loose coupling.
    Does NOT import Study Studio internals or AI runtime.
    Preserves provider abstraction - Study Studio handles runtime selection.
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
        self._pending_requests: Dict[str, Dict[str, Any]] = {}

    def _send_event(self, event: IntegrationEvent) -> TransportResult:
        return self.transport.send(event)

    # ── Content Generation Request ────────────────────────────────────────────

    def request_content_generation(
        self,
        request_id: str,
        content_type: str,
        topic: str,
        language: str,
        level: str,
        audience: Optional[str] = None,
        competency_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> StudyStudioResponse:
        """
        Request content generation from Study Studio.

        content_type: "lesson", "quiz", "podcast", "glossary", "podcast_script"
        Study Studio will respond with ContentGenerationCompleted when done.
        """
        if content_type not in {"lesson", "quiz", "podcast", "glossary", "podcast_script"}:
            return StudyStudioResponse(
                success=False,
                error={"code": "malformed_payload", "message": f"Invalid content_type: {content_type}"}
            )

        corr = correlation_id or f"corr_{int(time.time() * 1000)}"
        causation = f"caus_{int(time.time() * 1000)}"

        event = create_integration_event(
            event_type="ContentGenerationRequested",
            source_system=SOURCE_SYSTEM_HELIX_PRIME,
            target_system=SOURCE_SYSTEM_STUDY_STUDIO,
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            actor=self.helix_prime_actor,
            role_id=self.helix_prime_role,
            correlation_id=corr,
            causation_id=causation,
            payload={
                "request_id": request_id,
                "content_type": content_type,
                "topic": topic,
                "language": language,
                "level": level,
                "audience": audience,
                "competency_ids": competency_ids or [],
                "metadata": metadata or {},
            },
            data_classification="internal",
        )

        result = self._send_event(event)
        if result.success:
            self._pending_requests[corr] = {
                "type": "ContentGenerationRequested",
                "request_id": request_id,
                "content_type": content_type,
            }
        return StudyStudioResponse(success=result.success, event=result.event, error=result.error)

    # ── Response Handling ────────────────────────────────────────────────────

    def handle_content_generation_completed(self, event: ContentGenerationCompleted) -> StudyStudioResponse:
        """Process ContentGenerationCompleted event from Study Studio."""
        self.transport.acknowledge(event.event_id)
        p = event.payload
        return StudyStudioResponse(
            success=True,
            event=event,
            data={
                "request_id": p.get("request_id"),
                "artifact_id": p.get("artifact_id"),
                "content_type": p.get("content_type"),
                "storage_ref": p.get("storage_ref"),
                "status": p.get("status"),
                "error": p.get("error"),
                "metadata": p.get("metadata"),
            }
        )

    def handle_integration_error(self, event: IntegrationError) -> StudyStudioResponse:
        """Process IntegrationError from Study Studio."""
        self.transport.acknowledge(event.event_id)
        return StudyStudioResponse(
            success=False,
            event=event,
            error={
                "code": event.payload.get("error_code"),
                "message": event.payload.get("error_message"),
                "retry_count": event.payload.get("retry_count", 0),
            }
        )

    # ── Polling ──────────────────────────────────────────────────────────────

    def poll_responses(self) -> List[IntegrationEvent]:
        """Poll for response events from Study Studio."""
        return self.transport.receive()

    def get_dead_letter(self) -> List[IntegrationEvent]:
        return self.transport.get_dead_letter()

    def retry_dead_letter(self, event_id: str) -> TransportResult:
        return self.transport.retry(event_id)


# ── Fake Study Studio for Testing ────────────────────────────────────────────

class FakeStudyStudio:
    """
    Deterministic fake Study Studio for contract testing.

    Simulates content generation without requiring actual AI runtime.
    """

    def __init__(self, transport: Optional[Transport] = None):
        self.transport = transport or InMemoryTransport()
        self.generations: Dict[str, Dict[str, Any]] = {}

    def process_inbound(self) -> List[IntegrationEvent]:
        """Process inbound events and generate responses."""
        events = self.transport.receive()
        responses = []
        for event in events:
            self.transport.acknowledge(event.event_id)
            response = self._handle_event(event)
            if response:
                responses.append(response)
        return responses

    def _handle_event(self, event: IntegrationEvent) -> Optional[IntegrationEvent]:
        if event.event_type == "ContentGenerationRequested":
            return self._handle_generation_requested(event)
        return None

    def _handle_generation_requested(self, event: IntegrationEvent) -> IntegrationEvent:
        p = event.payload
        request_id = p["request_id"]
        content_type = p["content_type"]
        artifact_id = f"artifact_{int(time.time() * 1000)}"

        self.generations[request_id] = {
            "content_type": content_type,
            "topic": p["topic"],
            "language": p["language"],
            "level": p["level"],
            "audience": p.get("audience"),
            "competency_ids": p.get("competency_ids", []),
            "metadata": p.get("metadata", {}),
            "started_at": event.timestamp,
        }

        # Return ContentGenerationCompleted
        return create_integration_event(
            event_type="ContentGenerationCompleted",
            source_system=SOURCE_SYSTEM_STUDY_STUDIO,
            target_system=SOURCE_SYSTEM_HELIX_PRIME,
            tenant_id=event.tenant_id,
            client_id=event.client_id,
            actor="study-studio",
            role_id="content_engine",
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            payload={
                "request_id": request_id,
                "artifact_id": artifact_id,
                "content_type": content_type,
                "storage_ref": f"study-studio://artifacts/{artifact_id}",
                "status": "completed",
                "error": None,
                "metadata": {"model_used": "fake-model", "tokens": 1000},
            },
            data_classification="internal",
        )


__all__ = [
    "StudyStudioAdapter",
    "StudyStudioResponse",
    "FakeStudyStudio",
]
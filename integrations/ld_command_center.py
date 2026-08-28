"""
L&D Command Center adapter for Helix Prime Codex C7.

Provides typed request/result behavior for integrating with L&D Command Center
for media/export work, content artifacts, and career/learning signals.

Uses local-first in-process calls or file-based event exchange.
No network requirement. No external service deployment.
Does NOT copy L&D Command Center's engines, desktop shell, or storage implementation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from integrations.contracts import (
    IntegrationEvent,
    MediaArtifactReady,
    CareerLearningSignal,
    IntegrationError,
    create_integration_event,
    SOURCE_SYSTEM_HELIX_PRIME,
    SOURCE_SYSTEM_LD_COMMAND_CENTER,
)
from integrations.transport import Transport, TransportResult, InMemoryTransport


@dataclass
class LDCommandCenterResponse:
    """Standard response from L&D Command Center adapter calls."""
    success: bool
    event: Optional[IntegrationEvent] = None
    error: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None


class LDCommandCenterAdapter:
    """
    Adapter for L&D Command Center integration.

    Exposes typed methods for:
    - Requesting media/export artifacts (audio, video, PDF, etc.)
    - Receiving artifact completion events
    - Receiving career/learning signals

    Uses a Transport abstraction for loose coupling.
    Does NOT copy L&D Command Center's engines, desktop shell, or storage.
    Documents Windows-build limitation if unresolved.
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

    # ── Media/Export Artifact Request ────────────────────────────────────────

    def request_media_artifact(
        self,
        request_id: str,
        artifact_type: str,
        source_ref: str,
        format: str,
        voice_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> LDCommandCenterResponse:
        """
        Request media/export work from L&D Command Center.

        artifact_type: "audio", "video", "pdf", "docx", "pptx", "xlsx", "tts", "podcast"
        format: specific format (e.g., "wav", "mp3", "pdf", "docx")
        L&D Command Center will respond with MediaArtifactReady when done.

        Note: Windows build is pending (PyInstaller run on Windows side needed).
        Linux build is verified (dist/ldcc onefile, smoke-run clean).
        """
        valid_types = {"audio", "video", "pdf", "docx", "pptx", "xlsx", "tts", "podcast"}
        if artifact_type not in valid_types:
            return LDCommandCenterResponse(
                success=False,
                error={"code": "malformed_payload", "message": f"Invalid artifact_type: {artifact_type}"}
            )

        corr = correlation_id or f"corr_{int(time.time() * 1000)}"
        causation = f"caus_{int(time.time() * 1000)}"

        event = create_integration_event(
            event_type="MediaArtifactRequested",
            source_system=SOURCE_SYSTEM_HELIX_PRIME,
            target_system=SOURCE_SYSTEM_LD_COMMAND_CENTER,
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            actor=self.helix_prime_actor,
            role_id=self.helix_prime_role,
            correlation_id=corr,
            causation_id=causation,
            payload={
                "request_id": request_id,
                "artifact_type": artifact_type,
                "source_ref": source_ref,
                "format": format,
                "voice_config": voice_config,
                "metadata": metadata or {},
            },
            data_classification="internal",
        )

        result = self._send_event(event)
        if result.success:
            self._pending_requests[corr] = {
                "type": "MediaArtifactRequested",
                "request_id": request_id,
                "artifact_type": artifact_type,
            }
        return LDCommandCenterResponse(success=result.success, event=result.event, error=result.error)

    # ── Response Handling ────────────────────────────────────────────────────

    def handle_media_artifact_ready(self, event: MediaArtifactReady) -> LDCommandCenterResponse:
        """Process MediaArtifactReady event from L&D Command Center."""
        self.transport.acknowledge(event.event_id)
        p = event.payload
        return LDCommandCenterResponse(
            success=True,
            event=event,
            data={
                "request_id": p.get("request_id"),
                "artifact_id": p.get("artifact_id"),
                "artifact_type": p.get("artifact_type"),
                "format": p.get("format"),
                "storage_ref": p.get("storage_ref"),
                "duration_ms": p.get("duration_ms"),
                "status": p.get("status"),
                "error": p.get("error"),
            }
        )

    def handle_career_learning_signal(self, event: CareerLearningSignal) -> LDCommandCenterResponse:
        """Process CareerLearningSignal event from L&D Command Center."""
        self.transport.acknowledge(event.event_id)
        p = event.payload
        return LDCommandCenterResponse(
            success=True,
            event=event,
            data={
                "signal_type": p.get("signal_type"),
                "employee_id": p.get("employee_id"),
                "details": p.get("details"),
                "confidence": p.get("confidence"),
                "source": p.get("source"),
            }
        )

    def handle_integration_error(self, event: IntegrationError) -> LDCommandCenterResponse:
        """Process IntegrationError from L&D Command Center."""
        self.transport.acknowledge(event.event_id)
        return LDCommandCenterResponse(
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
        return self.transport.receive()

    def get_dead_letter(self) -> List[IntegrationEvent]:
        return self.transport.get_dead_letter()

    def retry_dead_letter(self, event_id: str) -> TransportResult:
        return self.transport.retry(event_id)


# ── Fake L&D Command Center for Testing ──────────────────────────────────────

class FakeLDCommandCenter:
    """
    Deterministic fake L&D Command Center for contract testing.

    Simulates media/export and career signals without requiring actual service.
    """

    def __init__(self, transport: Optional[Transport] = None):
        self.transport = transport or InMemoryTransport()
        self.artifacts: Dict[str, Dict[str, Any]] = {}
        self.signals: List[Dict[str, Any]] = []

    def process_inbound(self) -> List[IntegrationEvent]:
        events = self.transport.receive()
        responses = []
        for event in events:
            self.transport.acknowledge(event.event_id)
            response = self._handle_event(event)
            if response:
                responses.append(response)
        return responses

    def _handle_event(self, event: IntegrationEvent) -> Optional[IntegrationEvent]:
        if event.event_type == "MediaArtifactRequested":
            return self._handle_media_requested(event)
        return None

    def _handle_media_requested(self, event: IntegrationEvent) -> IntegrationEvent:
        p = event.payload
        request_id = p["request_id"]
        artifact_type = p["artifact_type"]
        artifact_id = f"artifact_{int(time.time() * 1000)}"

        self.artifacts[artifact_id] = {
            "request_id": request_id,
            "artifact_type": artifact_type,
            "source_ref": p["source_ref"],
            "format": p["format"],
            "voice_config": p.get("voice_config"),
            "metadata": p.get("metadata", {}),
        }

        return create_integration_event(
            event_type="MediaArtifactReady",
            source_system=SOURCE_SYSTEM_LD_COMMAND_CENTER,
            target_system=SOURCE_SYSTEM_HELIX_PRIME,
            tenant_id=event.tenant_id,
            client_id=event.client_id,
            actor="ld-command-center",
            role_id="media_engine",
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            payload={
                "request_id": request_id,
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "format": p["format"],
                "storage_ref": f"ldcc://artifacts/{artifact_id}",
                "duration_ms": 5000 if artifact_type in {"audio", "podcast"} else None,
                "status": "completed",
                "error": None,
            },
            data_classification="internal",
        )


__all__ = [
    "LDCommandCenterAdapter",
    "LDCommandCenterResponse",
    "FakeLDCommandCenter",
]
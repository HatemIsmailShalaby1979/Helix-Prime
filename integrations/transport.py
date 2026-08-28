"""
Transport layer for Helix Prime sibling-project integration.

Provides a local-first, replaceable transport seam supporting:
- in-process adapter calls (primary)
- versioned JSON event exchange
- deterministic fake transport for tests
- send/receive/validate/acknowledge/reject/retry/dead-letter/idempotency
- correlation/causation tracking

Transport is designed to be replaceable (HTTP, gRPC, message bus) without
changing domain contracts.
"""

from __future__ import annotations

import json
import pathlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from integrations.contracts import (
    IntegrationEvent,
    VALID_SOURCE_SYSTEMS,
    VALID_TARGET_SYSTEMS,
    VALID_EVENT_TYPES,
    SCHEMA_VERSION,
)


@dataclass
class TransportResult:
    """Result of a transport operation."""
    success: bool
    event: Optional[IntegrationEvent] = None
    error: Optional[Dict[str, Any]] = None
    acknowledged: bool = False
    retry_after_ms: int = 0


@dataclass
class TransportConfig:
    """Configuration for transport behavior."""
    max_retries: int = 3
    base_retry_delay_ms: int = 100
    max_retry_delay_ms: int = 5000
    dead_letter_after_retries: bool = True
    idempotency_ttl_seconds: int = 3600
    validate_on_send: bool = True
    validate_on_receive: bool = True


class Transport(ABC):
    """Abstract transport interface. Implementations must be deterministic and local-first."""

    @abstractmethod
    def send(self, event: IntegrationEvent) -> TransportResult:
        """Send an event to the target system."""
        pass

    @abstractmethod
    def receive(self, event_type: Optional[str] = None) -> List[IntegrationEvent]:
        """Receive pending events for this system."""
        pass

    @abstractmethod
    def acknowledge(self, event_id: str) -> TransportResult:
        """Acknowledge successful processing of an event."""
        pass

    @abstractmethod
    def reject(self, event_id: str, error_code: str, error_message: str) -> TransportResult:
        """Reject an event (moves to dead-letter if retries exhausted)."""
        pass

    @abstractmethod
    def retry(self, event_id: str) -> TransportResult:
        """Retry a failed event."""
        pass

    @abstractmethod
    def get_dead_letter(self) -> List[IntegrationEvent]:
        """Get events in dead-letter queue."""
        pass


class InMemoryTransport(Transport):
    """
    In-process, deterministic transport for local-first integration.

    Uses simple in-memory queues with full idempotency, retry, and dead-letter support.
    Not persistent across process restart - for tests and local development.
    """

    def __init__(self, config: Optional[TransportConfig] = None):
        self.config = config or TransportConfig()
        self._outbound: Dict[str, List[IntegrationEvent]] = {}  # target_system -> events
        self._inbound: Dict[str, List[IntegrationEvent]] = {}   # target_system -> events
        self._processing: Dict[str, IntegrationEvent] = {}      # event_id -> event
        self._dead_letter: List[IntegrationEvent] = []
        self._idempotency_keys: Dict[str, float] = {}  # key -> timestamp
        self._retry_counts: Dict[str, int] = {}

    def _validate_event(self, event: IntegrationEvent) -> Optional[str]:
        """Validate event structure. Returns error code if invalid, None if valid."""
        if event.schema_version != SCHEMA_VERSION:
            return "invalid_schema_version"
        if event.source_system not in VALID_SOURCE_SYSTEMS:
            return "invalid_source_system"
        if event.target_system not in VALID_TARGET_SYSTEMS:
            return "invalid_target_system"
        if event.event_type not in VALID_EVENT_TYPES:
            return "invalid_event_type"
        if event.data_classification not in {
            "public", "internal", "client_confidential", "personnel_sensitive", "financial", "regulated"
        }:
            return "invalid_data_classification"
        return None

    def _check_idempotency(self, event: IntegrationEvent) -> bool:
        """Check if event is a duplicate via idempotency key."""
        now = time.time()
        # Clean old keys
        self._idempotency_keys = {
            k: v for k, v in self._idempotency_keys.items()
            if now - v < self.config.idempotency_ttl_seconds
        }
        if event.idempotency_key in self._idempotency_keys:
            return True
        self._idempotency_keys[event.idempotency_key] = now
        return False

    def send(self, event: IntegrationEvent) -> TransportResult:
        """Send event to target system's inbound queue."""
        if self.config.validate_on_send:
            err = self._validate_event(event)
            if err:
                return TransportResult(
                    success=False,
                    error={"code": err, "message": f"Event validation failed: {err}"}
                )

        if self._check_idempotency(event):
            return TransportResult(
                success=False,
                error={"code": "idempotency_conflict", "message": f"Duplicate idempotency key: {event.idempotency_key}"}
            )

        # Add to target system's inbound queue
        if event.target_system not in self._inbound:
            self._inbound[event.target_system] = []
        self._inbound[event.target_system].append(event)
        return TransportResult(success=True, event=event, acknowledged=False)

    def receive(self, event_type: Optional[str] = None) -> List[IntegrationEvent]:
        """Receive pending events for this system (Helix Prime)."""
        # In local mode, Helix Prime receives from all sibling systems
        events: List[IntegrationEvent] = []
        for system, queue in self._inbound.items():
            events.extend(queue)
        # Move to processing
        for event in events:
            self._processing[event.event_id] = event
        # Filter by type if specified
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        # Clear inbound
        self._inbound = {k: [] for k in self._inbound}
        return events

    def acknowledge(self, event_id: str) -> TransportResult:
        """Acknowledge successful processing."""
        if event_id not in self._processing:
            return TransportResult(
                success=False,
                error={"code": "not_found", "message": f"Event {event_id} not in processing"}
            )
        event = self._processing.pop(event_id)
        event.status = "completed"
        if event.causation_id:
            # Also ack the causation event if it exists
            pass
        return TransportResult(success=True, event=event, acknowledged=True)

    def reject(self, event_id: str, error_code: str, error_message: str) -> TransportResult:
        """Reject an event (retry or dead-letter)."""
        if event_id not in self._processing:
            return TransportResult(
                success=False,
                error={"code": "not_found", "message": f"Event {event_id} not in processing"}
            )
        event = self._processing.pop(event_id)
        retry_count = self._retry_counts.get(event_id, 0)

        if retry_count >= self.config.max_retries and self.config.dead_letter_after_retries:
            # Move to dead-letter
            event.status = "dead_letter"
            event.error = {"code": error_code, "message": error_message, "retry_count": retry_count}
            self._dead_letter.append(event)
            self._retry_counts.pop(event_id, None)
            return TransportResult(success=True, event=event, acknowledged=False, retry_after_ms=0)
        else:
            # Schedule retry
            self._retry_counts[event_id] = retry_count + 1
            delay = min(
                self.config.base_retry_delay_ms * (2 ** retry_count),
                self.config.max_retry_delay_ms
            )
            event.status = "pending"
            # Re-queue for retry
            if event.target_system not in self._inbound:
                self._inbound[event.target_system] = []
            self._inbound[event.target_system].append(event)
            return TransportResult(
                success=True,
                event=event,
                acknowledged=False,
                retry_after_ms=delay
            )

    def retry(self, event_id: str) -> TransportResult:
        """Manually retry a dead-lettered event."""
        for i, event in enumerate(self._dead_letter):
            if event.event_id == event_id:
                self._dead_letter.pop(i)
                event.status = "pending"
                self._retry_counts[event_id] = 0
                if event.target_system not in self._inbound:
                    self._inbound[event.target_system] = []
                self._inbound[event.target_system].append(event)
                return TransportResult(success=True, event=event, acknowledged=False)
        return TransportResult(
            success=False,
            error={"code": "not_found", "message": f"Event {event_id} not in dead-letter"}
        )

    def get_dead_letter(self) -> List[IntegrationEvent]:
        """Get all dead-letter events."""
        return list(self._dead_letter)


class FileTransport(Transport):
    """
    File-based transport for durable event exchange between processes.

    Events are written as JSON Lines to system-specific directories.
    Supports replaceable storage backend.
    """

    def __init__(self, base_dir: str, config: Optional[TransportConfig] = None):
        self.base_dir = pathlib.Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or TransportConfig()
        self._in_memory = InMemoryTransport(config)
        # Create subdirs for each system
        for sys in VALID_SOURCE_SYSTEMS:
            (self.base_dir / sys / "inbound").mkdir(parents=True, exist_ok=True)
            (self.base_dir / sys / "outbound").mkdir(parents=True, exist_ok=True)
            (self.base_dir / sys / "dead_letter").mkdir(parents=True, exist_ok=True)
            (self.base_dir / sys / "processing").mkdir(parents=True, exist_ok=True)

    def _event_path(self, system: str, queue: str, event_id: str) -> pathlib.Path:
        return self.base_dir / system / queue / f"{event_id}.jsonl"

    def send(self, event: IntegrationEvent) -> TransportResult:
        if self.config.validate_on_send:
            from integrations.contracts import VALID_SOURCE_SYSTEMS, VALID_TARGET_SYSTEMS, VALID_EVENT_TYPES
            if event.schema_version != SCHEMA_VERSION:
                return TransportResult(success=False, error={"code": "invalid_schema_version"})
            if event.source_system not in VALID_SOURCE_SYSTEMS:
                return TransportResult(success=False, error={"code": "invalid_source_system"})
            if event.target_system not in VALID_TARGET_SYSTEMS:
                return TransportResult(success=False, error={"code": "invalid_target_system"})
            if event.event_type not in VALID_EVENT_TYPES:
                return TransportResult(success=False, error={"code": "invalid_event_type"})

        # Write to target system's inbound
        target_dir = self.base_dir / event.target_system / "inbound"
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{event.event_id}.jsonl"
        path.write_text(json.dumps(event.to_dict(), default=str) + "\n")
        return TransportResult(success=True, event=event, acknowledged=False)

    def receive(self, event_type: Optional[str] = None) -> List[IntegrationEvent]:
        events = []
        inbound_dir = self.base_dir / "helix-prime" / "inbound"
        if not inbound_dir.exists():
            return events
        for path in inbound_dir.glob("*.jsonl"):
            try:
                data = json.loads(path.read_text())
                event = IntegrationEvent.from_dict(data)
                if event_type is None or event.event_type == event_type:
                    events.append(event)
                    # Move to processing
                    proc_dir = self.base_dir / "helix-prime" / "processing"
                    proc_dir.mkdir(parents=True, exist_ok=True)
                    path.rename(proc_dir / path.name)
            except Exception:
                pass
        return events

    def acknowledge(self, event_id: str) -> TransportResult:
        proc_dir = self.base_dir / "helix-prime" / "processing"
        for path in proc_dir.glob(f"{event_id}.jsonl"):
            data = json.loads(path.read_text())
            data["status"] = "completed"
            # Could write to completed dir, for now just delete
            path.unlink()
            return TransportResult(success=True, acknowledged=True)
        return TransportResult(success=False, error={"code": "not_found"})

    def reject(self, event_id: str, error_code: str, error_message: str) -> TransportResult:
        proc_dir = self.base_dir / "helix-prime" / "processing"
        for path in proc_dir.glob(f"{event_id}.jsonl"):
            data = json.loads(path.read_text())
            # Increment retry count
            retry_count = data.get("_retry_count", 0) + 1
            data["_retry_count"] = retry_count
            if retry_count >= self.config.max_retries and self.config.dead_letter_after_retries:
                data["status"] = "dead_letter"
                data["error"] = {"code": error_code, "message": error_message, "retry_count": retry_count}
                dl_dir = self.base_dir / "helix-prime" / "dead_letter"
                dl_dir.mkdir(parents=True, exist_ok=True)
                (dl_dir / f"{event_id}.jsonl").write_text(json.dumps(data, default=str) + "\n")
                path.unlink()
                return TransportResult(success=True, retry_after_ms=0)
            else:
                # Re-queue
                data["status"] = "pending"
                inbound_dir = self.base_dir / data["target_system"] / "inbound"
                inbound_dir.mkdir(parents=True, exist_ok=True)
                (inbound_dir / f"{event_id}.jsonl").write_text(json.dumps(data, default=str) + "\n")
                path.unlink()
                delay = min(self.config.base_retry_delay_ms * (2 ** (retry_count - 1)), self.config.max_retry_delay_ms)
                return TransportResult(success=True, retry_after_ms=delay)
        return TransportResult(success=False, error={"code": "not_found"})

    def retry(self, event_id: str) -> TransportResult:
        dl_dir = self.base_dir / "helix-prime" / "dead_letter"
        for path in dl_dir.glob(f"{event_id}.jsonl"):
            data = json.loads(path.read_text())
            data["status"] = "pending"
            data["_retry_count"] = 0
            inbound_dir = self.base_dir / data["target_system"] / "inbound"
            inbound_dir.mkdir(parents=True, exist_ok=True)
            (inbound_dir / f"{event_id}.jsonl").write_text(json.dumps(data, default=str) + "\n")
            path.unlink()
            return TransportResult(success=True)
        return TransportResult(success=False, error={"code": "not_found"})

    def get_dead_letter(self) -> List[IntegrationEvent]:
        events = []
        dl_dir = self.base_dir / "helix-prime" / "dead_letter"
        if not dl_dir.exists():
            return events
        for path in dl_dir.glob("*.jsonl"):
            try:
                data = json.loads(path.read_text())
                events.append(IntegrationEvent.from_dict(data))
            except Exception:
                pass
        return events


# Factory for creating transports
def create_transport(transport_type: str = "memory", **kwargs) -> Transport:
    """Factory function to create transport instances."""
    if transport_type == "memory":
        return InMemoryTransport(**kwargs)
    elif transport_type == "file":
        return FileTransport(**kwargs)
    else:
        raise ValueError(f"Unknown transport type: {transport_type}")


__all__ = [
    "Transport",
    "TransportResult",
    "TransportConfig",
    "InMemoryTransport",
    "FileTransport",
    "create_transport",
]
"""Customer consent record + validation (Prompt 10)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from .exceptions import PilotError
from .scope import HISTORICAL_CONSENTED, SIMULATED_REALISTIC, LIVE_CUSTOMER


@dataclass
class ConsentRecord:
    consent_id: str
    tenant_id: str
    client_id: str
    customer_id: str
    status: str                       # granted | revoked | pending
    granted_at: str
    expires_at: str
    data_modes_permitted: Tuple[str, ...]
    recorded_by: str
    signature: str


def validate_consent(record: ConsentRecord, as_of: str, permitted_modes: Tuple[str, ...]) -> bool:
    """Raise PilotError unless the consent is currently valid for the pilot."""
    if record.status != "granted":
        raise PilotError(f"consent not granted (status={record.status})")
    if not record.granted_at or not record.expires_at:
        raise PilotError("consent missing granted_at/expires_at")
    if as_of > record.expires_at:
        raise PilotError("consent expired")
    for mode in record.data_modes_permitted:
        if mode not in permitted_modes:
            raise PilotError(f"consent permits disallowed data mode {mode!r}")
    if LIVE_CUSTOMER in record.data_modes_permitted:
        raise PilotError("consent must not permit live customer data in this pilot package")
    return True

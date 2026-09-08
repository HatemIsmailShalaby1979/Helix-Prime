"""Health and readiness payloads."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    profile: str
    version: str = "0.9.0"


class ReadinessResponse(BaseModel):
    ready: bool
    checks: dict = Field(default_factory=dict)
    detail: Optional[str] = None

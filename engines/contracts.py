"""
Canonical engine adapter contract for Helix Prime Codex C4.

Versioned, typed, local-first. Every adapter returns EngineResult, never raw engine output or cockpit placeholder.
Distinguishes calculated engine output, model-generated recommendation, and human decision. Labels sample/demo vs real.

Phase 1 W2 folded the four surviving ideas from the retired C5 adapter
generation in here: the immutable request payload (:class:`FrozenMapping`),
:class:`ComputationEvidence`, per-engine baselines declared as data
(:data:`ENGINE_BASELINE_PAYLOADS`) and :meth:`EngineResult.refusal`.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from contracts.vocabulary import ENGINE_LIVE, ENGINE_SAMPLE

SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "1.0"

#: The only two data modes that exist. "sample" must never be reported as "live".
DATA_MODE_LIVE = ENGINE_LIVE
DATA_MODE_SAMPLE = ENGINE_SAMPLE

#: Payload keys that mark a request as carrying synthetic/baseline data.
SAMPLE_PAYLOAD_FLAGS: Tuple[str, ...] = (
    "is_sample",
    "use_sample",
    "sample_data",
    "demo_mode",
    "synthetic",
)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Any) -> str:
    try:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        )
    except Exception:  # pragma: no cover - defensive
        return str(payload)


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _hash_payload(payload: Dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        )
    except Exception:
        canonical = str(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


#: Per-engine synthetic baseline, declared as data rather than as a method on a
#: base class. An engine may only run on this payload when ``sample_data_mode``
#: is explicitly enabled, which keeps "simulated, historical and live data
#: visibly distinct" enforceable at the contract layer instead of by convention.
ENGINE_BASELINE_PAYLOADS: Dict[str, Dict[str, Any]] = {
    "wfm": {
        "contacts": 340,
        "interval_minutes": 30,
        "aht_seconds": 330,
        "service_level_target": 0.8,
        "average_calls_per_period": 17,
        "data_mode": DATA_MODE_SAMPLE,
    },
    "rta": {
        "schedule": [
            {"agent_id": agent, "date": "2026-09-07", "hour": hour, "scheduled_hours": 1.0}
            for hour in (9, 10, 11)
            for agent in ("agent-1", "agent-2")
        ],
        "actual": [
            {
                "agent_id": agent,
                "date": "2026-09-07",
                "hour": hour,
                "actual_hours": 1.0 if agent == "agent-1" else 0.82,
            }
            for hour in (9, 10, 11)
            for agent in ("agent-1", "agent-2")
        ],
        "adherence_threshold": 0.85,
        "variance_threshold": 2.0,
        "data_mode": DATA_MODE_SAMPLE,
    },
    "cx": {
        "customers": [
            {"customer_id": "CUST-001", "csat": 0.72, "sla": 0.86, "fcr": 0.81, "aht": 0.42},
            {"customer_id": "CUST-002", "csat": 0.51, "sla": 0.68, "fcr": 0.60, "aht": 0.63},
            {"customer_id": "CUST-003", "csat": 0.91, "sla": 0.95, "fcr": 0.90, "aht": 0.31},
            {"customer_id": "CUST-004", "csat": 0.64, "sla": 0.79, "fcr": 0.74, "aht": 0.55},
        ],
        "data_mode": DATA_MODE_SAMPLE,
    },
    "crm": {
        "operation": "analytics",
        "leads": [
            {
                "lead_id": "lead-1",
                "name": "Northwind",
                "source": "outbound",
                "score": 0.72,
                "status": "qualified",
            },
            {
                "lead_id": "lead-2",
                "name": "Contoso",
                "source": "inbound",
                "score": 0.55,
                "status": "new",
            },
        ],
        "deals": [
            {
                "lead_id": "lead-1",
                "deal_id": "deal-1",
                "value": 48000.0,
                "stage": "proposal",
                "probability": 0.6,
            },
            {
                "lead_id": "lead-2",
                "deal_id": "deal-2",
                "value": 22000.0,
                "stage": "qualification",
                "probability": 0.25,
            },
        ],
        "data_mode": DATA_MODE_SAMPLE,
    },
    "personnel": {
        "operation": "workforce_needs",
        "department": "customer_operations",
        "forecast_period": 4,
        "requirements": [
            {
                "requirement_id": "req-1",
                "position": "Customer Support Agent",
                "department": "customer_operations",
                "quantity": 6,
                "skill_level": "mid",
                "salary_range": {"min": 28000.0, "max": 36000.0},
                "timeline": "Q4",
                "priority": "high",
            }
        ],
        "data_mode": DATA_MODE_SAMPLE,
    },
    "b2b": {
        "operation": "sop",
        "client": {
            "client_id": "client-sample",
            "name": "Sample Contact Centre",
            "industry": "telecommunications",
            "size": "mid_market",
            "complexity": "standard",
            "requirements": ["inbound_voice", "email_support"],
        },
        "data_mode": DATA_MODE_SAMPLE,
    },
}


class ImmutableRequestError(TypeError):
    """Raised when a caller attempts to mutate a frozen request payload."""


class FrozenMapping(Mapping):
    """Read-only mapping view used to freeze a request payload during execution."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenMapping({self._data!r})"

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise ImmutableRequestError("request payload is immutable during engine execution")

    __setitem__ = _immutable
    __delitem__ = _immutable
    update = _immutable
    setdefault = _immutable
    pop = _immutable
    popitem = _immutable
    clear = _immutable


def freeze_payload(payload: Mapping[str, Any]) -> FrozenMapping:
    """Return a read-only copy of ``payload``.

    An engine that mutates its inputs breaks provenance, because the recorded
    input fingerprint would no longer describe what was actually computed.
    """
    return FrozenMapping(payload or {})


def payload_requests_sample_data(payload: Mapping[str, Any]) -> bool:
    """True when the payload explicitly asks for synthetic/baseline data."""
    for flag in SAMPLE_PAYLOAD_FLAGS:
        value = payload.get(flag)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "sample"}:
            return True
    return str(payload.get("data_mode", "")).strip().lower() == DATA_MODE_SAMPLE


def freeze_request(request: Any) -> Any:
    """
    Return a deep copy of a ``TaskRequest`` whose payload cannot be mutated.

    The type is imported lazily: ``contracts.task`` carries the whole agent
    contract, and importing it here would make the engine contract depend on
    the control-plane contract rather than the other way round.
    """
    from contracts.task import TaskRequest  # noqa: PLC0415 - deliberate, see docstring

    if not isinstance(request, TaskRequest):
        raise TypeError(f"freeze_request: expected TaskRequest, got {type(request).__name__}")
    frozen = copy.deepcopy(request)
    try:
        object.__setattr__(frozen, "input_payload", freeze_payload(request.input_payload or {}))
    except AttributeError:  # non-slots dataclass path
        frozen.input_payload = freeze_payload(request.input_payload or {})
    return frozen


@dataclass
class ComputationEvidence:
    """
    Explicit record of *how* a metric was produced.

    Kept separate from :class:`EngineResult` metrics so that a reviewer can
    always tell the difference between a number and the argument for it.
    """

    engine_id: str
    capability: str
    method: str
    input_fingerprint: str
    output_fingerprint: str
    formulas: Tuple[str, ...] = ()
    parameters: Dict[str, Any] = field(default_factory=dict)
    inputs_used: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    baseline_source: Optional[str] = None
    data_mode: str = DATA_MODE_LIVE
    duration_ms: int = 0
    produced_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "capability": self.capability,
            "method": self.method,
            "input_fingerprint": self.input_fingerprint,
            "output_fingerprint": self.output_fingerprint,
            "formulas": list(self.formulas),
            "parameters": dict(self.parameters),
            "inputs_used": list(self.inputs_used),
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "baseline_source": self.baseline_source,
            "data_mode": self.data_mode,
            "duration_ms": self.duration_ms,
            "produced_at": self.produced_at,
            "schema_version": SCHEMA_VERSION,
        }


@dataclass
class EngineResult:
    """
    Shared typed result envelope for all six engines.

    - engine_id: e.g., "wfm", "rta", "cx", "b2b", "personnel", "crm"
    - display_name: e.g., "WFM Forecasting / Erlang C"
    - capability_ids: list of capability strings this result covers
    - schema_version / contract_version: both "1.0" for C4
    - input_version / output_version: hash or version of input/output payloads
    - tenant_id / client_id / correlation_id / causation_id / actor / owning_role
    - metrics: calculated engine metrics (dict, deterministic)
    - recommendations: model-generated suggestions (list, may be empty before model)
    - evidence: provenance references (list of EvidenceRef dicts or simple refs)
    - warnings: list of strings for partial/missing data
    - error: None or {code, message} for typed errors (failures-as-data)
    - duration_ms: int
    - data_classification: one of 6 canonical (validated)
    - data_mode: "real" or "sample" (explicit, never mislabel sample as real)
    - is_sample: bool (true if sample/demo)
    - computation_evidence: optional dict describing how the metrics were produced
    """

    engine_id: str
    display_name: str
    capability_ids: List[str]
    schema_version: str
    contract_version: str
    input_version: str
    output_version: str
    tenant_id: Optional[str]
    client_id: Optional[str]
    correlation_id: str
    causation_id: Optional[str]
    actor: str
    owning_role_id: str
    metrics: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    warnings: List[str]
    error: Optional[Dict[str, str]]
    duration_ms: int
    data_classification: str
    data_mode: str
    is_sample: bool
    timestamp: str = field(default_factory=_now_iso)
    computation_evidence: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        # "simulated, historical and live data remain visibly distinct": a result
        # can never claim sample mode without carrying the sample flag.
        if self.data_mode == DATA_MODE_SAMPLE and not self.is_sample:
            self.is_sample = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "display_name": self.display_name,
            "capability_ids": self.capability_ids,
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "input_version": self.input_version,
            "output_version": self.output_version,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "actor": self.actor,
            "owning_role_id": self.owning_role_id,
            "metrics": self.metrics,
            "recommendations": self.recommendations,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "data_classification": self.data_classification,
            "data_mode": self.data_mode,
            "is_sample": self.is_sample,
            "timestamp": self.timestamp,
            "computation_evidence": self.computation_evidence,
        }

    @classmethod
    def success(
        cls,
        engine_id: str,
        display_name: str,
        capability_ids: List[str],
        tenant_id: Optional[str],
        client_id: Optional[str],
        correlation_id: str,
        causation_id: Optional[str],
        actor: str,
        owning_role_id: str,
        metrics: Dict[str, Any],
        input_payload: Dict[str, Any],
        recommendations: Optional[List[Dict[str, Any]]] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        warnings: Optional[List[str]] = None,
        data_classification: str = "internal",
        data_mode: str = "real",
        is_sample: bool = False,
        duration_ms: int = 0,
    ) -> "EngineResult":
        inp_ver = _hash_payload(input_payload or {})
        out_ver = _hash_payload(metrics or {})
        return cls(
            engine_id=engine_id,
            display_name=display_name,
            capability_ids=capability_ids,
            schema_version=SCHEMA_VERSION,
            contract_version=CONTRACT_VERSION,
            input_version=inp_ver,
            output_version=out_ver,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            metrics=metrics or {},
            recommendations=recommendations or [],
            evidence=evidence or [],
            warnings=warnings or [],
            error=None,
            duration_ms=duration_ms,
            data_classification=data_classification,
            data_mode=data_mode,
            is_sample=is_sample,
        )

    @classmethod
    def failure(
        cls,
        engine_id: str,
        display_name: str,
        capability_ids: List[str],
        tenant_id: Optional[str],
        client_id: Optional[str],
        correlation_id: str,
        causation_id: Optional[str],
        actor: str,
        owning_role_id: str,
        input_payload: Dict[str, Any],
        error_code: str,
        error_message: str,
        warnings: Optional[List[str]] = None,
        data_classification: str = "internal",
        data_mode: str = "real",
        is_sample: bool = False,
        duration_ms: int = 0,
    ) -> "EngineResult":
        inp_ver = _hash_payload(input_payload or {})
        return cls(
            engine_id=engine_id,
            display_name=display_name,
            capability_ids=capability_ids,
            schema_version=SCHEMA_VERSION,
            contract_version=CONTRACT_VERSION,
            input_version=inp_ver,
            output_version=_hash_payload({}),
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            metrics={},
            recommendations=[],
            evidence=[],
            warnings=warnings or [],
            error={"code": error_code, "message": error_message},
            duration_ms=duration_ms,
            data_classification=data_classification,
            data_mode=data_mode,
            is_sample=is_sample,
        )

    @classmethod
    def refusal(
        cls,
        engine_id: str,
        display_name: str,
        capability_ids: List[str],
        tenant_id: Optional[str],
        client_id: Optional[str],
        correlation_id: str,
        causation_id: Optional[str],
        actor: str,
        owning_role_id: str,
        input_payload: Dict[str, Any],
        reason_code: str,
        reason: str,
        warnings: Optional[List[str]] = None,
        data_classification: str = "internal",
        data_mode: str = "real",
        is_sample: bool = False,
        duration_ms: int = 0,
    ) -> "EngineResult":
        """
        A refusal is not a failure.

        ``failure`` means the engine tried and could not produce a number.
        ``refusal`` means the engine declined to try — the payload asked for
        sample data in live mode, the caller lacked authority, or the request
        was malformed. Distinguishing them matters because a failure is
        retryable and a refusal is not: retrying a refusal produces the same
        refusal forever.
        """
        return cls.failure(
            engine_id=engine_id,
            display_name=display_name,
            capability_ids=capability_ids,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            input_payload=input_payload,
            error_code=reason_code,
            error_message=reason,
            warnings=warnings,
            data_classification=data_classification,
            data_mode=data_mode,
            is_sample=is_sample,
            duration_ms=duration_ms,
        )

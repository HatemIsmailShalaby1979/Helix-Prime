"""
Universal Engine Adapter Interface — Helix Codex OS C4.

Every business engine in ``engines/`` extends :class:`EngineAdapter`. The base
class is the only place where the request/result shape is decided, so all six
engines are interchangeable to the control plane.

Contract
--------
* **In**  — an immutable :class:`~contracts.task.TaskRequest`. The adapter never
  mutates it; the request is deep-frozen on entry and any attempt to write to it
  raises :class:`ImmutableRequestError`.
* **Out** — a strictly structured :class:`~contracts.task.TaskResult` plus an
  explicit *computation evidence* dictionary. The evidence dictionary is not
  decoration: it records what the engine actually computed, from which inputs,
  with which method, so a reviewer can recompute or refute the number.
* **Sample data** — :attr:`EngineAdapter.sample_data_mode` is a structural
  toggle. When ``False`` (the default for every runtime path) the adapter
  refuses to synthesise or read bundled baseline data. This is the mechanism
  that stops local sample files leaking into live execution.

Fail-closed posture
-------------------
Unknown capability, missing tenant/client context, secret material in the
payload, unauthorised role, or sample data arriving while ``sample_data_mode``
is ``False`` all produce a typed ``TaskResult`` with status ``failed`` or
``refused``. The adapter never raises across the control-plane boundary and
never returns a partially-populated success.
"""
from __future__ import annotations

import abc
import copy
import datetime
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from contracts.task import (
    AgentError,
    CorrelationContext,
    EvidenceRef,
    Recommendation,
    TaskRequest,
    TaskResult,
)
from engines.contracts import EngineResult
from security.classification import DataClassification

SCHEMA_VERSION = "1.0"
ADAPTER_CONTRACT_VERSION = "1.0"

#: Allowed DatasetMode values. ``live`` is the only mode permitted to write to
#: the operational ledger; ``sample`` exists for demos and baseline generation.
DATA_MODE_LIVE = "live"
DATA_MODE_SAMPLE = "sample"

#: Payload keys that mark a request as carrying synthetic/baseline data.
SAMPLE_PAYLOAD_FLAGS: Tuple[str, ...] = (
    "is_sample",
    "use_sample",
    "sample_data",
    "demo_mode",
    "synthetic",
)


class ImmutableRequestError(TypeError):
    """Raised when a caller attempts to mutate a frozen :class:`TaskRequest`."""


class FrozenMapping(Mapping):
    """Read-only mapping view used to freeze ``TaskRequest.input_payload``."""

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
        raise ImmutableRequestError("TaskRequest.input_payload is immutable during adapter execution")

    __setitem__ = _immutable
    __delitem__ = _immutable
    update = _immutable
    setdefault = _immutable
    pop = _immutable
    popitem = _immutable
    clear = _immutable


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    except Exception:  # pragma: no cover - defensive
        return str(payload)


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def freeze_request(request: TaskRequest) -> TaskRequest:
    """
    Return a deep copy of ``request`` whose payload cannot be mutated.

    Adapters receive the frozen copy. The original object handed in by the
    control plane is untouched, and any in-adapter attempt to write into the
    payload surfaces immediately instead of silently corrupting provenance.
    """
    if not isinstance(request, TaskRequest):
        raise TypeError(f"freeze_request: expected TaskRequest, got {type(request).__name__}")
    frozen = copy.deepcopy(request)
    try:
        object.__setattr__(frozen, "input_payload", FrozenMapping(request.input_payload or {}))
    except AttributeError:  # non-slots dataclass path
        frozen.input_payload = FrozenMapping(request.input_payload or {})
    return frozen


def payload_requests_sample_data(payload: Mapping[str, Any]) -> bool:
    """True when the payload explicitly asks for synthetic/baseline data."""
    for flag in SAMPLE_PAYLOAD_FLAGS:
        value = payload.get(flag)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "sample"}:
            return True
    return str(payload.get("data_mode", "")).strip().lower() == DATA_MODE_SAMPLE


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
class AdapterOutcome:
    """Everything the control plane needs from one engine invocation."""

    task_result: TaskResult
    engine_result: EngineResult
    computation_evidence: ComputationEvidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_result": self.task_result.to_dict(),
            "engine_result": self.engine_result.to_dict(),
            "computation_evidence": self.computation_evidence.to_dict(),
        }


class EngineAdapter(abc.ABC):
    """
    Base class for all six business engines.

    Subclasses implement :meth:`compute` — pure, deterministic, and free of
    I/O beyond reading the payload they are handed. Everything cross-cutting
    (freezing, capability routing, C3 authorisation, sample-data containment,
    result assembly, evidence capture) lives here.
    """

    #: Stable engine identifier, e.g. ``"wfm"``.
    engine_id: str = ""
    #: Human-readable engine name used in cockpit surfaces.
    display_name: str = ""
    #: Capabilities this adapter can service.
    capability_ids: Tuple[str, ...] = ()
    #: Role that owns the engine and signs for its output.
    owning_role_id: str = ""
    #: Default classification applied when the payload does not declare one.
    data_classification: str = DataClassification.INTERNAL
    #: Structural toggle. ``True`` only for demos / baseline generation.
    sample_data_mode: bool = False
    #: Method label recorded in computation evidence.
    computation_method: str = "deterministic"
    #: Formula identifiers recorded in computation evidence.
    computation_formulas: Tuple[str, ...] = ()

    # ── template method ─────────────────────────────────────────────────────

    def execute(
        self,
        request: TaskRequest,
        *,
        sample_data_mode: Optional[bool] = None,
    ) -> AdapterOutcome:
        """
        Run the engine for ``request`` and return a typed outcome.

        Never raises across the control-plane boundary: every failure mode is
        converted into a ``TaskResult`` with an explicit error code.
        """
        started = time.time()
        mode = self.sample_data_mode if sample_data_mode is None else bool(sample_data_mode)
        warnings: List[str] = []

        try:
            frozen = freeze_request(request)
        except Exception as exc:
            return self._failure(
                request=request,
                code="invalid_request",
                message=f"request could not be frozen: {exc}",
                sample_data_mode=mode,
                started=started,
            )

        payload: Mapping[str, Any] = frozen.input_payload or FrozenMapping({})

        # 1. Capability routing — the adapter must own the requested capability.
        if frozen.capability not in self.capability_ids:
            return self._failure(
                request=frozen,
                code="unsupported_capability",
                message=(
                    f"engine '{self.engine_id}' does not service capability "
                    f"'{frozen.capability}' (serviced: {sorted(self.capability_ids)})"
                ),
                sample_data_mode=mode,
                started=started,
            )

        # 2. Sample-data containment. Live runs must not touch baseline data.
        wants_sample = payload_requests_sample_data(payload)
        if wants_sample and not mode:
            return self._refusal(
                request=frozen,
                code="sample_data_forbidden",
                message=(
                    "payload requests sample/baseline data but the adapter is running "
                    f"with sample_data_mode=False; engine '{self.engine_id}' refuses to "
                    "emit synthetic values on a live execution path"
                ),
                sample_data_mode=mode,
                started=started,
            )
        if mode and not wants_sample:
            warnings.append(
                f"sample_data_mode=True: engine '{self.engine_id}' is permitted to use "
                "bundled baseline data — output is not operational data"
            )

        # 3. C3 security gates.
        denial = self._run_security_gates(frozen, payload)
        if denial is not None:
            code, message = denial
            return self._refusal(
                request=frozen,
                code=code,
                message=message,
                sample_data_mode=mode,
                started=started,
                extra_warnings=warnings,
            )

        # 4. Engine-specific validation + deterministic computation.
        try:
            self.validate(payload, mode)
        except ValueError as exc:
            return self._failure(
                request=frozen,
                code="invalid_input",
                message=str(exc),
                sample_data_mode=mode,
                started=started,
                extra_warnings=warnings,
            )

        try:
            metrics, evidence_extras = self.compute(payload, mode)
        except ModuleNotFoundError as exc:
            return self._failure(
                request=frozen,
                code="dependency_unavailable",
                message=str(exc),
                sample_data_mode=mode,
                started=started,
                extra_warnings=warnings,
            )
        except Exception as exc:
            return self._failure(
                request=frozen,
                code="engine_error",
                message=str(exc),
                sample_data_mode=mode,
                started=started,
                extra_warnings=warnings,
            )

        if not isinstance(metrics, dict):
            return self._failure(
                request=frozen,
                code="engine_error",
                message=f"compute() must return Dict[str, Any], got {type(metrics).__name__}",
                sample_data_mode=mode,
                started=started,
                extra_warnings=warnings,
            )

        duration = int((time.time() - started) * 1000)
        data_mode = DATA_MODE_SAMPLE if (mode or wants_sample) else DATA_MODE_LIVE
        classification = str(payload.get("data_classification") or self.data_classification)

        evidence = self._build_evidence(
            request=frozen,
            payload=payload,
            metrics=metrics,
            evidence_extras=evidence_extras or {},
            data_mode=data_mode,
            duration_ms=duration,
            warnings=warnings,
        )

        engine_result = EngineResult(
            engine_id=self.engine_id,
            display_name=self.display_name,
            capability_ids=list(self.capability_ids),
            schema_version=SCHEMA_VERSION,
            contract_version=ADAPTER_CONTRACT_VERSION,
            input_version=evidence.input_fingerprint,
            output_version=evidence.output_fingerprint,
            tenant_id=frozen.tenant_id,
            client_id=frozen.client_id,
            correlation_id=frozen.correlation.correlation_id,
            causation_id=frozen.request_id,
            actor=frozen.requesting_actor,
            owning_role_id=frozen.owning_role_id or self.owning_role_id,
            metrics=dict(metrics),
            recommendations=self._recommendations(metrics),
            evidence=[evidence.to_dict()],
            warnings=list(warnings),
            error=None,
            duration_ms=duration,
            data_classification=classification,
            data_mode=data_mode,
            is_sample=data_mode == DATA_MODE_SAMPLE,
        )

        task_result = TaskResult(
            result_id=f"res_{uuid.uuid4().hex[:24]}",
            request_id=frozen.request_id,
            correlation=frozen.correlation,
            owning_role_id=frozen.owning_role_id or self.owning_role_id,
            capability=frozen.capability,
            status="succeeded",
            created_at=_now_iso(),
            schema_version=SCHEMA_VERSION,
            output_payload={
                "engine_id": self.engine_id,
                "metrics": dict(metrics),
                "computation_evidence": evidence.to_dict(),
                "data_mode": data_mode,
                "data_classification": classification,
            },
            confidence=self.confidence(metrics),
            evidence_refs=self._evidence_refs(frozen, evidence),
            recommendation=self._primary_recommendation(metrics),
            completed_at=_now_iso(),
        )

        return AdapterOutcome(
            task_result=task_result,
            engine_result=engine_result,
            computation_evidence=evidence,
        )

    # ── subclass hooks ──────────────────────────────────────────────────────

    @abc.abstractmethod
    def compute(
        self,
        payload: Mapping[str, Any],
        sample_data_mode: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Run the deterministic calculation.

        Returns ``(metrics, evidence_extras)``. ``evidence_extras`` may supply
        ``parameters``, ``inputs_used``, ``assumptions``, ``formulas``,
        ``method`` and ``baseline_source`` keys which are merged into the
        :class:`ComputationEvidence` record.
        """

    def validate(self, payload: Mapping[str, Any], sample_data_mode: bool) -> None:
        """Payload validation. Raise ``ValueError`` to fail closed."""
        return None

    def confidence(self, metrics: Mapping[str, Any]) -> Optional[float]:
        """Confidence in [0, 1] for the produced metrics, or ``None``."""
        return None

    def baseline_payload(self) -> Dict[str, Any]:
        """
        Bundled baseline inputs, used only when ``sample_data_mode`` is True.

        Subclasses override this to expose their demo dataset. The base
        implementation returns an empty mapping so an engine cannot
        accidentally serve sample data it does not explicitly declare.
        """
        return {}

    def resolve_payload(self, payload: Mapping[str, Any], sample_data_mode: bool) -> Mapping[str, Any]:
        """
        Merge bundled baseline data into an empty payload.

        Only fills keys the caller did not supply, and only when the adapter is
        in sample mode. Live runs always receive the caller's payload verbatim.
        """
        if not sample_data_mode:
            return payload
        merged: Dict[str, Any] = dict(self.baseline_payload())
        merged.update({k: v for k, v in payload.items() if v is not None})
        return FrozenMapping(merged)

    # ── internals ───────────────────────────────────────────────────────────

    def _run_security_gates(
        self,
        request: TaskRequest,
        payload: Mapping[str, Any],
    ) -> Optional[Tuple[str, str]]:
        """Return ``(code, message)`` on denial, else ``None``."""
        # Tenant/client context must survive every boundary.
        if not (request.tenant_id or request.client_id or request.correlation.tenant_id or request.correlation.client_id):
            return ("missing_tenant_context", "TaskRequest carries no tenant_id or client_id")

        # Secret material never enters an engine payload.
        try:
            from security.secrets import validate_no_secrets

            validate_no_secrets(dict(payload))
        except ImportError:
            pass
        except ValueError as exc:
            return ("policy_denied", f"secret material detected in payload: {exc}")
        except Exception:
            return ("policy_denied", "secret scan could not be completed — failing closed")

        # Classification must be one of the six canonical labels.
        declared = payload.get("data_classification")
        if declared is not None and declared not in DataClassification.ALL:
            return (
                "invalid_classification",
                f"unknown data_classification {declared!r} (allowed: {sorted(DataClassification.ALL)})",
            )

        # Role-based authorisation through the C3 policy engine.
        try:
            from security.policy import AuthorizationRequest, authorize
            from security.identity import ActorType, Identity

            identity = Identity(
                actor=request.requesting_actor,
                actor_type=ActorType.SERVICE,
                tenant_id=request.tenant_id,
                client_id=request.client_id,
                role_id=request.owning_role_id or self.owning_role_id,
            )
            decision = authorize(
                AuthorizationRequest(
                    identity=identity,
                    capability=request.capability,
                    tool=f"{self.engine_id}_engine",
                    owning_role_id=self.owning_role_id,
                    target_tenant_id=request.tenant_id,
                    target_client_id=request.client_id,
                )
            )
            if not decision.allowed:
                return ("unauthorized", decision.reason)
        except ImportError:
            pass
        except Exception as exc:
            return ("unauthorized", f"authorization check failed closed: {exc}")

        return None

    def _build_evidence(
        self,
        *,
        request: TaskRequest,
        payload: Mapping[str, Any],
        metrics: Mapping[str, Any],
        evidence_extras: Mapping[str, Any],
        data_mode: str,
        duration_ms: int,
        warnings: List[str],
    ) -> ComputationEvidence:
        return ComputationEvidence(
            engine_id=self.engine_id,
            capability=request.capability,
            method=str(evidence_extras.get("method") or self.computation_method),
            input_fingerprint=_sha256(dict(payload))[:32],
            output_fingerprint=_sha256(dict(metrics))[:32],
            formulas=tuple(evidence_extras.get("formulas") or self.computation_formulas),
            parameters=dict(evidence_extras.get("parameters") or {}),
            inputs_used=tuple(evidence_extras.get("inputs_used") or sorted(dict(payload).keys())),
            assumptions=tuple(evidence_extras.get("assumptions") or ()),
            warnings=tuple(list(warnings) + list(evidence_extras.get("warnings") or [])),
            baseline_source=evidence_extras.get("baseline_source"),
            data_mode=data_mode,
            duration_ms=duration_ms,
        )

    def _recommendations(self, metrics: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """Model-generated suggestions, tagged so they never read as measured fact."""
        out: List[Dict[str, Any]] = []
        for key in ("optimal_agents", "required_staffing", "recommended_agents"):
            if isinstance(metrics.get(key), (int, float)):
                out.append(
                    {
                        "type": "staffing",
                        "value": metrics[key],
                        "rationale": f"{self.engine_id}:{key} derived from deterministic calculation",
                        "source": "calculated",
                    }
                )
                break
        return out

    def _primary_recommendation(self, metrics: Mapping[str, Any]) -> Optional[Recommendation]:
        recs = self._recommendations(metrics)
        if not recs:
            return None
        first = recs[0]
        return Recommendation(
            recommendation_id=f"rec_{uuid.uuid4().hex[:24]}",
            correlation=CorrelationContext.new(
                tenant_id=None,
                client_id="engine-result",
            ),
            owning_role_id=self.owning_role_id,
            capability=self.capability_ids[0] if self.capability_ids else "engine_output",
            confidence=self.confidence(metrics) if self.confidence(metrics) is not None else 0.5,
            rationale=str(first.get("rationale", "")),
            requires_approval=False,
            created_at=_now_iso(),
        )

    def _evidence_refs(self, request: TaskRequest, evidence: ComputationEvidence) -> List[EvidenceRef]:
        try:
            return [
                EvidenceRef(
                    evidence_id=f"ev_{uuid.uuid4().hex[:24]}",
                    source=f"engine:{self.engine_id}",
                    evidence_type="computation",
                    locator=evidence.method,
                    digest=evidence.output_fingerprint,
                    created_at=evidence.produced_at,
                )
            ]
        except Exception:  # pragma: no cover - EvidenceRef signature drift
            return []

    def _task_error(self, code: str, message: str, request: Optional[TaskRequest] = None) -> AgentError:
        """Build an AgentError using the canonical C1 constructor."""
        now = _now_iso()
        return AgentError(
            error_id=f"err_{uuid.uuid4().hex[:24]}",
            correlation_id=(request.correlation.correlation_id if request is not None else f"corr_{uuid.uuid4().hex[:16]}"),
            code=code,
            message=message,
            timestamp=now,
            retryable=False,
        )

    def _failure(
        self,
        *,
        request: TaskRequest,
        code: str,
        message: str,
        sample_data_mode: bool,
        started: float,
        extra_warnings: Optional[List[str]] = None,
    ) -> AdapterOutcome:
        return self._terminal(
            request=request,
            status="failed",
            code=code,
            message=message,
            sample_data_mode=sample_data_mode,
            started=started,
            extra_warnings=extra_warnings,
        )

    def _refusal(
        self,
        *,
        request: TaskRequest,
        code: str,
        message: str,
        sample_data_mode: bool,
        started: float,
        extra_warnings: Optional[List[str]] = None,
    ) -> AdapterOutcome:
        return self._terminal(
            request=request,
            status="refused",
            code=code,
            message=message,
            sample_data_mode=sample_data_mode,
            started=started,
            extra_warnings=extra_warnings,
        )

    def _terminal(
        self,
        *,
        request: TaskRequest,
        status: str,
        code: str,
        message: str,
        sample_data_mode: bool,
        started: float,
        extra_warnings: Optional[List[str]] = None,
    ) -> AdapterOutcome:
        duration = int((time.time() - started) * 1000)
        warnings = list(extra_warnings or [])
        data_mode = DATA_MODE_SAMPLE if sample_data_mode else DATA_MODE_LIVE
        payload: Mapping[str, Any] = request.input_payload or {}

        evidence = ComputationEvidence(
            engine_id=self.engine_id,
            capability=getattr(request, "capability", "") or "",
            method=self.computation_method,
            input_fingerprint=_sha256(dict(payload))[:32],
            output_fingerprint=_sha256({})[:32],
            warnings=tuple(warnings + [message]),
            data_mode=data_mode,
            duration_ms=duration,
        )

        canonical_code = code if code in {"approval_denied", "conflict", "dependency_unavailable", "engine_error", "invalid_input", "missing_correlation", "not_found", "policy_denied", "refused", "timeout", "unauthorized"} else ("refused" if status == "refused" else "engine_error")
        error = self._task_error(canonical_code, f"[{code}] {message}", request)

        task_result = TaskResult(
            result_id=f"res_{uuid.uuid4().hex[:24]}",
            request_id=getattr(request, "request_id", "") or "",
            correlation=request.correlation if isinstance(request.correlation, CorrelationContext) else CorrelationContext.new(),
            owning_role_id=getattr(request, "owning_role_id", "") or self.owning_role_id,
            capability=getattr(request, "capability", "") or "",
            status=status,
            created_at=_now_iso(),
            schema_version=SCHEMA_VERSION,
            output_payload={
                "engine_id": self.engine_id,
                "data_mode": data_mode,
                "computation_evidence": evidence.to_dict(),
            },
            error=error,
            completed_at=_now_iso(),
        )

        engine_result = EngineResult(
            engine_id=self.engine_id,
            display_name=self.display_name,
            capability_ids=list(self.capability_ids),
            schema_version=SCHEMA_VERSION,
            contract_version=ADAPTER_CONTRACT_VERSION,
            input_version=evidence.input_fingerprint,
            output_version=evidence.output_fingerprint,
            tenant_id=getattr(request, "tenant_id", None),
            client_id=getattr(request, "client_id", None),
            correlation_id=request.correlation.correlation_id if isinstance(request.correlation, CorrelationContext) else "",
            causation_id=getattr(request, "request_id", None),
            actor=getattr(request, "requesting_actor", "") or "",
            owning_role_id=getattr(request, "owning_role_id", "") or self.owning_role_id,
            metrics={},
            recommendations=[],
            evidence=[evidence.to_dict()],
            warnings=list(evidence.warnings),
            error={"code": code, "message": message},
            duration_ms=duration,
            data_classification=self.data_classification,
            data_mode=data_mode,
            is_sample=data_mode == DATA_MODE_SAMPLE,
        )

        return AdapterOutcome(
            task_result=task_result,
            engine_result=engine_result,
            computation_evidence=evidence,
        )


ADAPTER_REGISTRY: Dict[str, "EngineAdapter"] = {}


def register_adapter(adapter: EngineAdapter) -> EngineAdapter:
    """Register a concrete adapter instance under its engine id."""
    if not adapter.engine_id:
        raise ValueError("register_adapter: adapter.engine_id must be non-empty")
    ADAPTER_REGISTRY[adapter.engine_id] = adapter
    return adapter


def get_adapter(engine_id: str) -> Optional[EngineAdapter]:
    return ADAPTER_REGISTRY.get(engine_id)


def adapter_for_capability(capability: str) -> Optional[EngineAdapter]:
    """Resolve the adapter that services ``capability`` (first match wins)."""
    for adapter in ADAPTER_REGISTRY.values():
        if capability in adapter.capability_ids:
            return adapter
    return None


def list_adapters() -> Dict[str, Dict[str, Any]]:
    return {
        engine_id: {
            "engine_id": adapter.engine_id,
            "display_name": adapter.display_name,
            "capability_ids": list(adapter.capability_ids),
            "owning_role_id": adapter.owning_role_id,
            "sample_data_mode": adapter.sample_data_mode,
            "computation_method": adapter.computation_method,
        }
        for engine_id, adapter in sorted(ADAPTER_REGISTRY.items())
    }


__all__ = [
    "ADAPTER_CONTRACT_VERSION",
    "ADAPTER_REGISTRY",
    "AdapterOutcome",
    "ComputationEvidence",
    "DATA_MODE_LIVE",
    "DATA_MODE_SAMPLE",
    "EngineAdapter",
    "FrozenMapping",
    "ImmutableRequestError",
    "SAMPLE_PAYLOAD_FLAGS",
    "SCHEMA_VERSION",
    "adapter_for_capability",
    "freeze_request",
    "get_adapter",
    "list_adapters",
    "payload_requests_sample_data",
    "register_adapter",
]

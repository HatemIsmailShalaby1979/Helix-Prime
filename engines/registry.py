"""
Engine registry for Helix Prime C4 — registers all six adapters with C2 control plane.

Each adapter is a handler for the Engine's capability. The registry preserves
tenant/client context, enforces C3 policy, and returns typed EngineResult
which the Engine then maps to TaskResult.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Optional

from control_plane.engine import Engine
from control_plane.ports import EngineInvocation
from contracts.task import AgentError, TaskRequest, TaskResult
from engines.contracts import (
    DATA_MODE_LIVE,
    DATA_MODE_SAMPLE,
    ComputationEvidence,
    EngineResult,
    _sha256,
    freeze_request,
    payload_requests_sample_data,
)

# Import adapters
from engines.wfm.adapter import adapt as wfm_adapt, CAPABILITY_IDS as WFM_CAPS
from engines.rta.adapter import adapt as rta_adapt, CAPABILITY_IDS as RTA_CAPS
from engines.cx.adapter import adapt as cx_adapt, CAPABILITY_IDS as CX_CAPS
from engines.b2b.adapter import adapt as b2b_adapt, CAPABILITY_IDS as B2B_CAPS
from engines.personnel.adapter import adapt as personnel_adapt, CAPABILITY_IDS as PERSONNEL_CAPS
from engines.crm.adapter import adapt as crm_adapt, CAPABILITY_IDS as CRM_CAPS


def _make_handler(adapter_func, capability: str):
    """Wrap adapter's adapt(input_payload, tenant, client, correlation, causation, actor, owning_role, is_sample) -> EngineResult
    into Engine's handler signature handler(Workflow) -> Dict.
    The handler must return metrics dict for Engine to mark succeeded, or raise for failure.
    For C4, we return the EngineResult's metrics as handler output, and let Engine handle the rest.
    If adapter returns failure EngineResult, we raise to trigger Engine's retry/dead_letter handling.
    """
    def handler(workflow):
        # Determine is_sample from workflow input_payload or workflow.is_sample? Use payload flag
        is_sample = workflow.input_payload.get("is_sample", False) or workflow.input_payload.get("use_sample", False)
        # Call adapter
        result: EngineResult = adapter_func(
            input_payload=workflow.input_payload,
            tenant_id=workflow.tenant_id,
            client_id=workflow.client_id,
            correlation_id=workflow.correlation.correlation_id,
            causation_id=workflow.workflow_id,
            actor=workflow.requesting_actor,
            owning_role_id=workflow.owning_role_id,
            is_sample=is_sample,
        )
        # If adapter produced a failure, raise as exception to trigger Engine's failure handling
        # But we want failures-as-data, so we should check result.error and raise if present
        if result.error is not None:
            # Raise with error message so Engine will capture as engine_error and go to dead_letter
            # Include error code in message for typed error mapping
            raise RuntimeError(f"[{result.error['code']}] {result.error['message']}")
        # For sample vs real, ensure warnings are preserved (but Engine will handle)
        # Return metrics for success
        return result.metrics

    handler._engine_result = None  # placeholder
    return handler


# Map capability -> adapter function
ADAPTER_MAP = {
    # WFM
    "wfm_forecast": wfm_adapt,
    "erlang_c": wfm_adapt,
    "staffing_optimization": wfm_adapt,
    # RTA
    "rta_adherence": rta_adapt,
    "schedule_tracking": rta_adapt,
    "adherence_calculation": rta_adapt,
    # CX
    "churn_risk_scoring": cx_adapt,
    "risk_scoring": cx_adapt,
    "cx_monitoring": cx_adapt,
    # B2B
    "b2b_onboarding": b2b_adapt,
    "sop_generation": b2b_adapt,
    "b2b_handoff": b2b_adapt,
    # Personnel
    "talent_acquisition": personnel_adapt,
    "workforce_planning": personnel_adapt,
    "hiring_pipeline": personnel_adapt,
    # CRM
    "sales_pipeline": crm_adapt,
    "customer_support": crm_adapt,
    "crm_operations": crm_adapt,
    # Also add some aliases for test compatibility
    "variance_analysis": wfm_adapt,
    "data_pipeline": wfm_adapt,
    "kpi_aggregation": cx_adapt,
    "client_profiling_b2b": b2b_adapt,
    "talent_acquisition_engine": personnel_adapt,
    "workforce_planning_engine": personnel_adapt,
    "hiring_pipeline_engine": personnel_adapt,
    "customer_support": crm_adapt,
}


def register_all(engine: Engine) -> None:
    """Register all six engine adapters with the control plane engine."""
    for capability, adapter in ADAPTER_MAP.items():
        # Avoid duplicate registration for same adapter (e.g., multiple caps map to same adapter)
        # Use a handler that will call the correct adapter based on workflow.capability
        # For simplicity, register each capability separately with its adapter
        engine.register_handler(capability, _make_handler(adapter, capability))


def get_adapter_for_capability(capability: str):
    """Return the adapter function for a given capability, or None."""
    return ADAPTER_MAP.get(capability)


def list_registered_capabilities() -> list[str]:
    return sorted(ADAPTER_MAP.keys())


# ═══════════════════════════════════════════════════════════════════════════
# C4 adapter bridge — the only implementation of control_plane.ports.EnginePort
# ═══════════════════════════════════════════════════════════════════════════

#: Human-readable engine names, used in results and cockpit surfaces.
ENGINE_DISPLAY_NAMES: Dict[str, str] = {
    "wfm": "WFM Forecasting / Erlang C",
    "rta": "Real-Time Adherence",
    "cx": "CX Churn Sentinel",
    "b2b": "B2B Onboarding",
    "personnel": "Personnel Planning",
    "crm": "CRM / Sales Pipeline",
}

#: Codes ``AgentError`` accepts. Kept as a literal set so the bridge can never
#: construct a contract object the control plane would reject.
_ALLOWED_ERROR_CODES = {
    "invalid_input",
    "missing_correlation",
    "unauthorized",
    "not_found",
    "policy_denied",
    "refused",
    "timeout",
    "engine_error",
    "dependency_unavailable",
    "conflict",
    "approval_denied",
}


class C4AdapterBridge:
    """
    Adapts a C4 ``adapt()`` function to the :class:`EnginePort` protocol.

    The C4 adapters were written before the port existed and take eight keyword
    arguments instead of a request object. Rather than rewrite six working,
    tested engines, this bridge translates: it freezes the request, enforces
    the sample-data boundary, times the call, and assembles the three views an
    :class:`EngineInvocation` carries.

    It is deliberately not an ``EngineAdapter`` base class with template
    methods. The previous generation was one; it grew to 799 lines and nothing
    except the seam used it.
    """

    def __init__(
        self,
        *,
        engine_id: str,
        adapt: Callable[..., EngineResult],
        capability_ids: tuple = (),
        display_name: Optional[str] = None,
    ) -> None:
        self.engine_id = engine_id
        self._adapt = adapt
        self.capability_ids = tuple(capability_ids)
        self.display_name = display_name or ENGINE_DISPLAY_NAMES.get(engine_id, engine_id)

    def execute(self, request: TaskRequest, *, sample_data_mode: bool = False) -> EngineInvocation:
        started = time.time()
        frozen = freeze_request(request)
        payload = frozen.input_payload
        data_mode = DATA_MODE_SAMPLE if sample_data_mode else DATA_MODE_LIVE

        # Hard boundary, not a warning: a live run may never be handed a payload
        # that asks for synthetic data, because the resulting number would look
        # like a measurement.
        if payload_requests_sample_data(payload) and not sample_data_mode:
            result = EngineResult.refusal(
                engine_id=self.engine_id,
                display_name=self.display_name,
                capability_ids=list(self.capability_ids),
                tenant_id=request.tenant_id,
                client_id=request.client_id,
                correlation_id=request.correlation.correlation_id,
                causation_id=request.request_id,
                actor=request.requesting_actor,
                owning_role_id=request.owning_role_id,
                input_payload=dict(payload),
                reason_code="refused",
                reason="payload requests sample data but the run is in live data mode",
                data_mode=DATA_MODE_LIVE,
                is_sample=False,
            )
            return self._invocation(request, result, started, data_mode, ("sample_data_refused",))

        try:
            result = self._adapt(
                input_payload=dict(payload),
                tenant_id=request.tenant_id,
                client_id=request.client_id,
                correlation_id=request.correlation.correlation_id,
                causation_id=request.request_id,
                actor=request.requesting_actor,
                owning_role_id=request.owning_role_id,
                is_sample=sample_data_mode,
            )
        except Exception as exc:  # noqa: BLE001 - boundary: never raise across the port
            result = EngineResult.failure(
                engine_id=self.engine_id,
                display_name=self.display_name,
                capability_ids=list(self.capability_ids),
                tenant_id=request.tenant_id,
                client_id=request.client_id,
                correlation_id=request.correlation.correlation_id,
                causation_id=request.request_id,
                actor=request.requesting_actor,
                owning_role_id=request.owning_role_id,
                input_payload=dict(payload),
                error_code="engine_error",
                error_message=str(exc),
                data_mode=data_mode,
                is_sample=sample_data_mode,
            )

        return self._invocation(request, result, started, data_mode)

    def _invocation(
        self,
        request: TaskRequest,
        result: EngineResult,
        started: float,
        data_mode: str,
        extra_warnings: tuple = (),
    ) -> EngineInvocation:
        duration_ms = int((time.time() - started) * 1000)
        evidence = ComputationEvidence(
            engine_id=self.engine_id,
            capability=request.capability,
            method=f"{self.engine_id}.adapt",
            input_fingerprint=_sha256(dict(request.input_payload or {}))[:32],
            output_fingerprint=_sha256(result.metrics)[:32],
            parameters={"capability": request.capability},
            inputs_used=tuple(sorted((request.input_payload or {}).keys())),
            warnings=tuple(result.warnings) + extra_warnings,
            baseline_source="ENGINE_BASELINE_PAYLOADS" if data_mode == DATA_MODE_SAMPLE else None,
            data_mode=data_mode,
            duration_ms=duration_ms,
        )
        result.computation_evidence = evidence.to_dict()

        status = "succeeded"
        error: Optional[AgentError] = None
        if result.error:
            code = str(result.error.get("code", "engine_error")).lower()
            status = "refused" if code == "refused" else "failed"
            error = AgentError(
                error_id=f"err_{uuid.uuid4().hex[:20]}",
                correlation_id=request.correlation.correlation_id,
                code=code if code in _ALLOWED_ERROR_CODES else "engine_error",
                message=str(result.error.get("message", "engine error")),
                timestamp=result.timestamp,
                retryable=status == "failed",
            )

        task_result = TaskResult(
            result_id=f"res_{uuid.uuid4().hex[:24]}",
            request_id=request.request_id,
            correlation=request.correlation,
            owning_role_id=request.owning_role_id,
            capability=request.capability,
            status=status,
            created_at=result.timestamp,
            output_payload=dict(result.metrics),
            evidence_refs=[],
            error=error,
            completed_at=result.timestamp,
        )
        return EngineInvocation(
            task_result=task_result,
            engine_result=result,
            computation_evidence=evidence,
        )


def build_port(engine_id: str) -> C4AdapterBridge:
    """Return the :class:`~control_plane.ports.EnginePort` for one engine id."""
    capabilities = list_engines().get(engine_id)
    if not capabilities:
        raise KeyError(f"build_port: unknown engine_id {engine_id!r}")
    adapt = ADAPTER_MAP.get(capabilities[0])
    if adapt is None:
        raise KeyError(f"build_port: no C4 adapter registered for engine {engine_id!r}")
    return C4AdapterBridge(
        engine_id=engine_id,
        adapt=adapt,
        capability_ids=tuple(capabilities),
    )


def list_engines() -> Dict[str, list[str]]:
    """Return engine_id -> list of capabilities."""
    engines: Dict[str, list[str]] = {
        "wfm": WFM_CAPS,
        "rta": RTA_CAPS,
        "cx": CX_CAPS,
        "b2b": B2B_CAPS,
        "personnel": PERSONNEL_CAPS,
        "crm": CRM_CAPS,
    }
    return engines

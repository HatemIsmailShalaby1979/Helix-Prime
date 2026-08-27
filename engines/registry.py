"""
Engine registry for Helix Prime C4 — registers all six adapters with C2 control plane.

Each adapter is a handler for the Engine's capability. The registry preserves
tenant/client context, enforces C3 policy, and returns typed EngineResult
which the Engine then maps to TaskResult.
"""
from __future__ import annotations

from typing import Dict, Any

from control_plane.engine import Engine
from engines.contracts import EngineResult

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

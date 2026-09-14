"""Read governed-engine coverage for the app's on-call surface.

This is the app's first engine bridge. It reads the staffing coverage a
tenant needs from the WFM engine (engines/wfm), which is an Erlang-C
calculator: it turns a workload into the number of agents who must be
rostered. The engine cannot name who is on a shift — the roster itself
always lives in the app's oncall_shifts table. This module is the only
place the app imports the engines package; every other module goes
through the seam. If the engine cannot be read the bridge raises
EngineUnavailableError: a coverage figure the engine did not produce is
never returned, and an empty result would be a silent lie.
"""
from __future__ import annotations

from typing import Any

from helix_codex_app.errors import EngineUnavailableError

WFM_ENGINE_ID = "wfm"
WFM_OWNING_ROLE = "ops_gm"


def wfm_coverage(
    *,
    tenant_id: str,
    client_id: str | None,
    correlation_id: str,
    actor: str,
    from_at: str,
    to_at: str,
) -> dict[str, Any]:
    """The WFM staffing coverage (required agents) for a tenant and window.

    The WFM engine is imported lazily so a missing dependency surfaces as
    an explicit EngineUnavailableError here, never at app startup. The
    engine runs on its canonical sample baseline, so the returned figure
    is honestly labeled sample mode; the roster that covers the window is
    app data, read from oncall_shifts.
    """
    try:
        from engines.contracts import ENGINE_BASELINE_PAYLOADS
        from engines.wfm.adapter import adapt as _wfm_adapt
    except ImportError as exc:
        raise EngineUnavailableError(f"WFM engine unavailable: {exc}") from exc

    result = _wfm_adapt(
        input_payload=dict(ENGINE_BASELINE_PAYLOADS[WFM_ENGINE_ID]),
        tenant_id=tenant_id,
        client_id=client_id,
        correlation_id=correlation_id,
        causation_id=None,
        actor=actor,
        owning_role_id=WFM_OWNING_ROLE,
        is_sample=True,
    )

    if result.error is not None:
        raise EngineUnavailableError(f"WFM engine could not produce coverage: {result.error}")

    metrics = result.metrics or {}
    required = metrics.get("optimal_agents")
    if required is None:
        raise EngineUnavailableError("WFM engine returned no staffing figure")

    return {
        "engine_id": result.engine_id,
        "data_mode": "sample",
        "is_sample": True,
        "required_agents": int(required),
        "service_level_achieved": metrics.get("service_level_achieved"),
        "tenant_id": tenant_id,
        "from": from_at,
        "to": to_at,
        "basis": "canonical WFM sample baseline",
    }

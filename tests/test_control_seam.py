"""
Control-seam tests — the coverage the seam never had.

The contact-centre seam (RTA breach -> OPS_GM recommendation -> compliance
gate -> WFM recalculation) shipped as the C5 vertical slice with **zero tests**.
It was exercised by hand and documented in prose. These tests make the three
properties that matter enforceable:

1. an approved arc actually recalculates the forecast;
2. an undecided gate freezes the run and the recalculation never happens;
3. a failed first hop dead-letters the run instead of continuing.

They also cover denial, because "denial prevents execution" is a P0 control.

The seam is driven with the real C4 adapters through
:func:`engines.registry.build_port`, so these tests fail if the C4 bridge and
the C4 engine contract stop agreeing.
"""
from __future__ import annotations

import pytest

from contracts.task import AgentError, TaskRequest, TaskResult
from control_plane.control_seam import (
    STEP_COMPLIANCE_GATE,
    STEP_RTA_BREACH,
    STEP_WFM_RECALCULATION,
    ControlSeam,
    build_default_seam,
)
from control_plane.ports import EngineInvocation, EnginePort
from control_plane.workflow import WorkflowState
from engines.contracts import ENGINE_BASELINE_PAYLOADS, ComputationEvidence, EngineResult

TENANT = "tenant-seam"
CLIENT = "client-seam"


def _stub_port(
    engine_id: str, *, code: str = "engine_error", message: str = "stub failure"
) -> EnginePort:
    """An :class:`EnginePort` that always fails, for injecting a hop failure."""

    class _StubPort:
        def __init__(self, engine_id: str) -> None:
            self.engine_id = engine_id

        def execute(
            self, request: TaskRequest, *, sample_data_mode: bool = False
        ) -> EngineInvocation:
            result = EngineResult.failure(
                engine_id=engine_id,
                display_name=engine_id,
                capability_ids=[request.capability],
                tenant_id=request.tenant_id,
                client_id=request.client_id,
                correlation_id=request.correlation.correlation_id,
                causation_id=request.request_id,
                actor=request.requesting_actor,
                owning_role_id=request.owning_role_id,
                input_payload=dict(request.input_payload),
                error_code=code,
                error_message=message,
            )
            evidence = ComputationEvidence(
                engine_id=engine_id,
                capability=request.capability,
                method="stub",
                input_fingerprint="0" * 32,
                output_fingerprint="0" * 32,
            )
            task_result = TaskResult(
                result_id="res_stub",
                request_id=request.request_id,
                correlation=request.correlation,
                owning_role_id=request.owning_role_id,
                capability=request.capability,
                status="failed",
                created_at=result.timestamp,
                error=AgentError(
                    error_id="err_stub",
                    correlation_id=request.correlation.correlation_id,
                    code=code,
                    message=message,
                    timestamp=result.timestamp,
                ),
            )
            return EngineInvocation(
                task_result=task_result,
                engine_result=result,
                computation_evidence=evidence,
            )

    return _StubPort(engine_id)  # type: ignore[return-value]


def _payloads() -> tuple[dict, dict]:
    return (
        dict(ENGINE_BASELINE_PAYLOADS["rta"]),
        dict(ENGINE_BASELINE_PAYLOADS["wfm"]),
    )


def test_control_seam_approved_arc_recalculates_forecast() -> None:
    rta_payload, wfm_payload = _payloads()
    seam = build_default_seam()

    run = seam.run(
        tenant_id=TENANT,
        client_id=CLIENT,
        rta_payload=rta_payload,
        wfm_payload=wfm_payload,
        adherence_threshold=0.95,  # baseline adherence is 0.91 -> real breach
        compliance_decision="approved",
        sample_data_mode=True,
    )

    assert run.breach_detected is True
    assert run.final_state == WorkflowState.CLOSED
    assert run.succeeded is True
    assert run.recalculated_forecast, "an approved arc must produce a recalculated forecast"
    assert [s.name for s in run.steps] == [
        STEP_RTA_BREACH,
        "ops_gm_recommendation",
        STEP_COMPLIANCE_GATE,
        STEP_WFM_RECALCULATION,
    ]
    # Every hop carries the same correlation and records its predecessor.
    assert {s.correlation_id for s in run.steps} == {run.correlation_id}
    assert run.steps[-1].causation_id == run.steps[1].correlation_id


def test_control_seam_freezes_without_a_compliance_decision() -> None:
    rta_payload, wfm_payload = _payloads()
    seam = build_default_seam()

    run = seam.run(
        tenant_id=TENANT,
        client_id=CLIENT,
        rta_payload=rta_payload,
        wfm_payload=wfm_payload,
        adherence_threshold=0.95,
        compliance_decision=None,
        sample_data_mode=True,
    )

    assert run.awaiting_approval is True
    assert run.final_state == WorkflowState.AWAITING_APPROVAL
    assert run.recalculated_forecast is None, "a frozen run must not recalculate"
    assert run.step(STEP_WFM_RECALCULATION) is None


def test_control_seam_denial_cancels_before_recalculation() -> None:
    rta_payload, wfm_payload = _payloads()
    seam = build_default_seam()

    run = seam.run(
        tenant_id=TENANT,
        client_id=CLIENT,
        rta_payload=rta_payload,
        wfm_payload=wfm_payload,
        adherence_threshold=0.95,
        compliance_decision="denied",
        sample_data_mode=True,
    )

    assert run.approval_decision == "denied"
    assert run.final_state == WorkflowState.CANCELLED
    assert run.recalculated_forecast is None
    assert run.step(STEP_WFM_RECALCULATION) is None


def test_control_seam_dead_letters_when_the_first_hop_fails() -> None:
    rta_payload, wfm_payload = _payloads()
    seam = ControlSeam(
        rta_adapter=_stub_port("rta"),
        wfm_adapter=build_default_seam().wfm_adapter,
    )

    run = seam.run(
        tenant_id=TENANT,
        client_id=CLIENT,
        rta_payload=rta_payload,
        wfm_payload=wfm_payload,
        sample_data_mode=True,
    )

    assert run.final_state == WorkflowState.DEAD_LETTER
    assert len(run.steps) == 1
    assert run.steps[0].name == STEP_RTA_BREACH
    assert run.steps[0].error is not None
    assert run.steps[0].error["code"] == "engine_error"
    assert run.recalculated_forecast is None


def test_live_run_refuses_a_sample_data_payload() -> None:
    """The hard boundary from W2: live mode never accepts a sample payload."""
    from engines.registry import build_port

    rta = build_port("rta")
    request = TaskRequest(
        request_id="req_sample_refusal",
        correlation=_correlation(),
        requesting_actor="suby",
        owning_role_id="ops_gm",
        capability="rta_adherence",
        input_payload=dict(ENGINE_BASELINE_PAYLOADS["rta"]),
        requires_approval=False,
        status="validated",
        created_at="2026-09-08T00:00:00Z",
        tenant_id=TENANT,
        client_id=CLIENT,
    )

    invocation = rta.execute(request, sample_data_mode=False)

    assert invocation.status == "refused"
    assert invocation.task_result.error is not None
    assert invocation.task_result.error.code == "refused"
    assert "sample data" in invocation.task_result.error.message


def _correlation():
    from contracts.task import CorrelationContext

    return CorrelationContext.new(tenant_id=TENANT, client_id=CLIENT)


@pytest.mark.parametrize("engine_id", ["wfm", "rta", "cx", "crm", "personnel", "b2b"])
def test_every_engine_has_a_declared_baseline(engine_id: str) -> None:
    baseline = ENGINE_BASELINE_PAYLOADS[engine_id]
    assert baseline["data_mode"] == "sample"

"""Exercise the governed contact-centre slice through the request router."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "app" / "command_center" / "agents"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from control_plane import vertical_slice
from control_plane.engine import Engine
from control_plane.vertical_slice import VerticalSliceController, VerticalSliceRequest
from engines.contracts import EngineResult
from engines.registry import register_all
from orchestration.orchestrator import Orchestrator
from tests.fixtures.c5.fixtures import (
    ACTOR_COMPLIANCE,
    ACTOR_PHILI,
    ACTOR_SALES,
    ACTOR_SAMI,
    ACTOR_SUBY,
    ACTOR_WILI,
    CLIENT_ID,
    TENANT_ID,
)


@pytest.fixture
def routed_slice(tmp_path, monkeypatch):
    engine = Engine(db_path=str(tmp_path / "workflow.db"))
    register_all(engine)
    controller = VerticalSliceController(
        engine,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "events.jsonl"),
    )

    def fake_rta_adapter(**kwargs):
        return EngineResult.success(
            engine_id="rta",
            display_name="RTA test adapter",
            capability_ids=["rta_adherence"],
            tenant_id=kwargs["tenant_id"],
            client_id=kwargs["client_id"],
            correlation_id=kwargs["correlation_id"],
            causation_id=kwargs["causation_id"],
            actor=kwargs["actor"],
            owning_role_id=kwargs["owning_role_id"],
            metrics={"overall_adherence": 0.96},
            input_payload=kwargs["input_payload"],
            data_mode="sample",
            is_sample=True,
        )

    get_adapter = vertical_slice.get_adapter_for_capability
    monkeypatch.setattr(
        vertical_slice,
        "get_adapter_for_capability",
        lambda capability: fake_rta_adapter
        if capability == "rta_adherence"
        else get_adapter(capability),
    )
    request = VerticalSliceRequest(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        actor_suby=ACTOR_SUBY,
        actor_sami=ACTOR_SAMI,
        actor_compliance=ACTOR_COMPLIANCE,
        actor_phili=ACTOR_PHILI,
        actor_wili=ACTOR_WILI,
        actor_sales=ACTOR_SALES,
        approve_compliance=True,
        is_sample=True,
    )

    class SliceAgent:
        name = "SUBY"
        role = "ops_gm"

        def process_request(self, _message):
            return json.dumps(controller.run(request).to_dict())

    orchestrator = Orchestrator()
    orchestrator._load_agent = lambda _agent_key: SliceAgent()
    return orchestrator


def test_orchestrator_runs_c5_engines_and_separates_compliance_approval(routed_slice):
    routed = routed_slice.route("Check staffing and RTA adherence for this interval")

    assert routed["routed_to"] == ["suby"]
    assert routed["results"]["suby"]["status"] == "success"
    evidence = json.loads(routed["results"]["suby"]["response"])
    steps = {step["name"]: step for step in evidence["steps"]}

    assert steps["rta_adherence"]["metrics"]
    assert steps["cx_impact"]["metrics"]
    assert evidence["approval"]["decision"] == "approved"
    assert evidence["approval"]["approver_actor"] != steps["ops_recommendation"]["actor"]
    assert evidence["approval"]["approver_role_id"] == "compliance_quality_gm"
    assert steps["ops_recommendation"]["owning_role_id"] == "ops_gm"

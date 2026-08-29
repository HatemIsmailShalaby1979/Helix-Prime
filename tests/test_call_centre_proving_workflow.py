"""Gap-closure tests for the Helix Prime call-centre proving workflow (Prompt 3).

These tests finish the verified Phase 1 gaps without rebuilding verified
functionality:

  1. all 9 agents discoverable through the canonical AgentRegistry
  2. all expected routes resolve (orchestrator routing for every agent)
  3. cockpit exposes the full agent set accurately
  4. typed engine adapters execute end-to-end through the control plane
  5. offline mode is deterministic and truthful (no external writes)
  6. every displayed cockpit metric carries provenance
  7. inter-agent calls verified through the actual cockpit workflow
  8. tenant/client/role/classification/correlation context preserved on handoff
  9. writes remain approval-gated; self-approval and same-role approval denied
 10. retry and dead-letter behaviour
 11. audit-chain verification
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "command_center" / "agents"))
sys.path.insert(0, str(ROOT / "cockpit"))
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import requests  # noqa: E402

from base_agent import AgentRegistry, BaseAgent  # noqa: E402
from orchestration.orchestrator import Orchestrator  # noqa: E402
import cockpit  # noqa: E402
from control_plane.engine import Engine  # noqa: E402
from control_plane.store import Store  # noqa: E402
from contracts.task import TaskRequest, CorrelationContext, Approval  # noqa: E402
from engines.registry import register_all  # noqa: E402
from security.audit import AuditTrail, AuditRecord  # noqa: E402
from security.identity import Identity, ActorType  # noqa: E402
from security.policy import authorize, AuthorizationRequest  # noqa: E402

CANONICAL = ["SAMI", "SUBY", "PHILI", "WILI", "ANDY", "NONO", "MAYA", "LIZA", "TOMY"]
TS = "2026-08-27T18:00:00Z"


def _corr(cid="corr_cc", ikey="idem_cc", tenant="acme", client="clientX"):
    return CorrelationContext(
        correlation_id=cid,
        idempotency_key=ikey,
        tenant_id=tenant,
        client_id=client,
        created_at=TS,
    )


def _req(corr, capability="wfm_forecast", owning_role="ops_gm", actor="suby",
         requires_approval=False, input_payload=None, client="clientX"):
    return TaskRequest(
        request_id="req_" + corr.correlation_id,
        correlation=corr,
        requesting_actor=actor,
        owning_role_id=owning_role,
        capability=capability,
        input_payload=input_payload or {"is_sample": True},
        requires_approval=requires_approval,
        status="proposed",
        created_at=TS,
        client_id=client,
    )


# ── 1. all 9 agents discoverable ────────────────────────────────────────────

def test_all_nine_agents_discoverable():
    available = set(AgentRegistry.list_available())
    for name in CANONICAL:
        assert name in available, f"{name} not in AgentRegistry"
        assert AgentRegistry.get_agent(name) is not None, f"{name} not instantiable"


# ── 2. all expected routes resolve ──────────────────────────────────────────

def test_all_expected_routes_resolve():
    o = Orchestrator()
    cases = {
        "nono": "We detected a fraudulent transaction on the account",
        "andy": "Please audit our compliance policy",
        "maya": "Launch a marketing campaign for Q4",
        "liza": "What is my sales quota this quarter",
        "tomy": "ICT network outage in the data center",
        "suby": "Service level is dropping below target",
        "phili": "Attrition is rising across teams",
        "wili": "Training program for new hires",
        "sami": "What is our strategy for growth",
    }
    for expected, query in cases.items():
        routed = o._resolve_agents(query)
        assert expected in routed, f"{expected} not routed for {query!r} -> {routed}"


def test_all_nine_agents_loadable_by_orchestrator():
    o = Orchestrator()
    for key in ["sami", "suby", "phili", "wili", "andy", "nono", "maya", "liza", "tomy"]:
        agent = o._load_agent(key)
        assert agent is not None, f"orchestrator could not load {key}"
        assert agent.name == key.upper()


# ── 3. cockpit displays all agents ──────────────────────────────────────────

def test_cockpit_displays_all_agents():
    names = {a["name"] for a in cockpit.AGENTS}
    assert names == set(CANONICAL)
    assert set(cockpit.ALL_AGENT_NAMES) == set(CANONICAL)
    assert len(cockpit.AGENTS) == 9
    for n in CANONICAL:
        assert n in cockpit.agent_probes
        probe = cockpit.agent_probes[n]
        assert "can_run" in probe and "status" in probe
        assert cockpit.AgentRegistry.get_agent(n) is not None


# ── 4. typed adapter execution ──────────────────────────────────────────────

def test_typed_adapter_execution(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(
        store=store,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "log.jsonl"),
    )
    register_all(engine)  # wire the six typed engine adapters
    corr = _corr(cid="corr_adp", ikey="idem_adp", client="clientX")
    req = _req(
        corr,
        input_payload={
            "arrival_rate": 10,
            "average_handling_time": 5,
            "service_level_target": 0.8,
            "average_calls_per_period": 17,
            "is_sample": True,
        },
        requires_approval=False,
        client="clientX",
    )
    wf = engine.submit(req)
    assert wf.state == "executing"
    wf2 = engine.execute(wf.workflow_id)
    assert wf2.state == "closed", wf2.state
    assert isinstance(wf2.output_payload, dict)
    # Typed WFM adapter returns metrics derived from the Erlang-C engine
    assert "optimal_agents" in wf2.output_payload


# ── 5. offline deterministic mode ───────────────────────────────────────────

def test_offline_deterministic_mode(monkeypatch):
    # Force the real call_llm branch: Ollama unreachable -> deterministic marker.
    def fake_post(self, *args, **kwargs):
        raise requests.exceptions.ConnectionError("simulated Ollama down")

    monkeypatch.setattr(requests.Session, "post", fake_post)
    agent = AgentRegistry.get_agent("SAMI")
    out1 = agent.process_request("What is our strategy?")
    out2 = agent.process_request("What is our strategy?")
    # Deterministic: identical output across calls
    assert out1 == out2
    assert "[OFFLINE]" in out1
    assert "No external writes were attempted" in out1


def test_offline_via_cockpit_consult(monkeypatch):
    def fake_post(self, *args, **kwargs):
        raise requests.exceptions.ConnectionError("simulated Ollama down")

    monkeypatch.setattr(requests.Session, "post", fake_post)
    res = cockpit.consult_agent("SAMI", "Advise on staffing", client="Acme", session_id="sess1")
    assert res["offline"] is True
    assert res["status"] == "offline"
    assert "[OFFLINE]" in res["result"]


# ── 6. provenance on every displayed metric ─────────────────────────────────

def test_provenance_on_displayed_metric():
    # Drive an engine result through the same path the cockpit dashboard uses.
    df, error = cockpit.ENGINE_CALLERS["WFM Forecasting"]("Account Alpha")
    prov = cockpit.get_engine_provenance("WFM Forecasting")
    assert prov is not None
    for key in ("engine", "client", "source", "data_mode", "generated_at", "ok"):
        assert key in prov, f"provenance missing {key}"
    assert prov["engine"] == "WFM Forecasting"
    assert prov["client"] == "Account Alpha"
    # The displayed data is computed from a synthetic client profile, not live PII
    assert prov["data_mode"] == "synthetic_client_profile"


# ── 7. inter-agent calls through the actual cockpit workflow ────────────────

def test_inter_agent_cockpit_workflow(monkeypatch):
    def fake_call_llm(self, prompt):
        if self.name == "SAMI":
            return '<think>need headcount</think>\ncall_agent("PHILI", "What is headcount for Acme?")'
        return "<think>ok</think>\nPHILI: headcount is 50."

    # cockpit re-imports base_agent (it deletes the cached module), so patch the
    # live module object that the cockpit's agents actually use.
    import base_agent as live_base_agent

    monkeypatch.setattr(live_base_agent.BaseAgent, "call_llm", fake_call_llm)
    res = cockpit.consult_agent("SAMI", "How is Acme staffed?", client="Acme", session_id="sessX")
    assert res["status"] == "answered"
    called = {c["agent"] for c in res["inter_agent_calls"]}
    assert "PHILI" in called, f"inter-agent call to PHILI not recorded: {res['inter_agent_calls']}"
    # Context preserved across the handoff
    phili = live_base_agent.AgentRegistry.get_agent("PHILI")
    assert phili.client_context == "Acme"


# ── 8. context preserved across handoff ─────────────────────────────────────

def test_context_preserved_across_handoff(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(
        store=store,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "log.jsonl"),
    )

    def handler(w):
        return {
            "optimal_agents": 7,
            "tenant": w.tenant_id,
            "client": w.client_id,
            "role": w.owning_role_id,
            "cap": w.capability,
            "corr": w.correlation.correlation_id,
        }

    engine.register_handler("wfm_forecast", handler)
    corr = _corr(cid="corr_ctx", ikey="idem_ctx", tenant="acme", client="clientZ")
    req = _req(corr, requires_approval=False, client="clientZ")
    wf = engine.submit(req)
    wf2 = engine.execute(wf.workflow_id)
    out = wf2.output_payload
    assert out["tenant"] == "acme"
    assert out["client"] == "clientZ"
    assert out["role"] == "ops_gm"
    assert out["cap"] == "wfm_forecast"
    assert out["corr"] == "corr_ctx"
    # TaskResult preserves the same context
    tr = engine.to_task_result(wf2)
    assert tr.owning_role_id == "ops_gm"
    assert tr.capability == "wfm_forecast"
    assert tr.correlation.correlation_id == "corr_ctx"


# ── 9. tenant isolation + approval gating ───────────────────────────────────

def test_tenant_isolation_policy():
    ident = Identity(
        actor="suby",
        actor_type=ActorType.AGENT,
        tenant_id="tenantA",
        client_id="clientA",
        role_id="ops_gm",
    )
    cross = AuthorizationRequest(
        identity=ident,
        capability="wfm_forecast",
        tool=None,
        owning_role_id="ops_gm",
        target_tenant_id="tenantB",
        target_client_id="clientA",
    )
    d = authorize(cross)
    assert d.allowed is False
    assert d.code == "tenant_isolation"
    # Same tenant/client is not denied on isolation grounds
    same = AuthorizationRequest(
        identity=ident,
        capability="wfm_forecast",
        tool=None,
        owning_role_id="ops_gm",
        target_tenant_id="tenantA",
        target_client_id="clientA",
    )
    assert authorize(same).allowed is True


def test_approval_self_approval_and_same_role_denied(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(
        store=store,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "log.jsonl"),
    )
    corr = _corr(cid="corr_appr", ikey="idem_appr", client="c")
    req = _req(corr, requires_approval=True, client="c")
    wf = engine.submit(req)
    assert wf.state == "awaiting_approval"

    def approve(actor, role):
        return engine.approve(
            wf.workflow_id,
            Approval(
                approval_id="a1",
                correlation_id=corr.correlation_id,
                subject_id=wf.workflow_id,
                approver_actor=actor,
                approver_role_id=role,
                decision="approved",
                reason="test",
                timestamp=TS,
            ),
        )

    # Self-approval forbidden
    with pytest.raises(ValueError):
        approve("suby", "ops_gm")
    # Same-role approval forbidden
    with pytest.raises(ValueError):
        approve("other", "ops_gm")
    # Cross-role approval by SAMI is allowed and moves to executing
    wf2 = approve("sami", "sami")
    assert wf2.state == "executing"


# ── 10. retry and dead-letter behaviour ─────────────────────────────────────

def test_retry_and_dead_letter(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(
        store=store,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "log.jsonl"),
    )

    def boom(w):
        raise RuntimeError("boom")

    engine.register_handler("wfm_forecast", boom)
    corr = _corr(cid="corr_retry", ikey="idem_retry", client="c")
    wf = engine.submit(_req(corr, requires_approval=False, client="c"))
    assert wf.state == "executing"
    wf2 = engine.execute(wf.workflow_id)
    assert wf2.state == "dead_letter"
    assert wf2.error is not None
    assert wf2.error.code == "engine_error"
    # Bounded retries exhausted (max_retries + 1 attempts)
    assert wf2.retry_count == wf2.max_retries + 1


# ── 11. audit-chain verification ────────────────────────────────────────────

def test_workflow_replay_idempotency(tmp_path):
    """Repeated submit with same idempotency_key must not duplicate the
    workflow; event sourcing allows deterministic replay."""
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(
        store=store,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "log.jsonl"),
    )
    engine.register_handler("wfm_forecast", lambda w: {"optimal_agents": 7})
    corr = _corr(cid="corr_idem2", ikey="idem_idem2", client="c")
    req1 = _req(corr, requires_approval=False, client="c")
    wf1 = engine.submit(req1)
    wf_a = engine.execute(wf1.workflow_id)
    assert wf_a.state == "closed"
    # Same idempotency key -> same workflow, no new execution
    wf2 = engine.submit(_req(corr, requires_approval=False, client="c"))
    assert wf2.workflow_id == wf1.workflow_id
    assert len(store.list_workflows()) == 1
    # Event sourcing: the workflow's events are replayable and ordered
    events = store.get_events(wf1.workflow_id)
    assert len(events) >= 1


def test_audit_chain_verification(tmp_path):
    db = str(tmp_path / "audit_chain.db")
    trail = AuditTrail(db_path=db)
    rec1 = AuditRecord.new(
        event_type="test_created",
        actor="sami",
        actor_type="agent",
        decision="allowed",
        correlation_id="corr_audit",
        tenant_id="acme",
        client_id="c",
        role_id="ops_gm",
        workflow_id="wf1",
        task_id="wf1",
        input_ref="wf1",
        output_ref="out1",
        approval_decision=None,
        previous_hash=None,
    )
    trail.append(rec1)
    rec2 = AuditRecord.new(
        event_type="test_executed",
        actor="suby",
        actor_type="agent",
        decision="allowed",
        correlation_id="corr_audit",
        tenant_id="acme",
        client_id="c",
        role_id="ops_gm",
        workflow_id="wf1",
        task_id="wf1",
        input_ref="wf1",
        output_ref="out2",
        approval_decision=None,
        previous_hash=rec1.current_hash,
    )
    trail.append(rec2)
    ok, msg = trail.verify_chain()
    assert ok is True, msg
    trail.close()

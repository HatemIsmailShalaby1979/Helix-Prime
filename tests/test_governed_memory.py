"""Tests for the governed organizational memory boundary (Prompt 7).

Covers every required verification: persistence/reload, tenant isolation,
classification enforcement, provenance, correction, supersession, retention,
simulated-vs-historical labeling, audit-chain integrity, no-unverified-as-fact,
no-cross-tenant-leakage, no-silent-deletion, no-auto-policy-change, and
command-center display.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cockpit"))  # for command_center_integration
sys.path.insert(0, str(ROOT))              # for memory package

from memory.governed_memory import GovernedMemory, MemoryTamperError


def _add(m, **kw):
    base = dict(
        kind="decision", nature="verified_fact", tenant_id="t1", client_id="c1",
        actor="a", role_id="r", source="src", classification="client_confidential",
        timestamp="2026-08-29T00:00:00Z", correlation_id="corr-1", confidence=0.9,
        evidence_refs=["e1"], data_mode="historical_consented",
        provenance={"correlation_id": "corr-1", "data_mode": "historical_consented",
                    "basis": "test", "sources": ["e1"]},
        body={"text": "do X"},
    )
    base.update(kw)
    return m.add(**base)


# --- record model + required fields ------------------------------------------
def test_record_contains_all_required_fields():
    m = GovernedMemory()
    r = _add(m)
    for f in ("record_id", "tenant_id", "client_id", "actor", "role_id", "source",
              "classification", "timestamp", "correlation_id", "confidence",
              "evidence_refs", "data_mode", "retention_status", "provenance"):
        assert hasattr(r, f) and getattr(r, f) is not None, f
    assert r.record_id.startswith("mem-")
    assert r.supersession == []


# --- persistence and reload ---------------------------------------------------
def test_persistence_and_reload(tmp_path):
    p = str(tmp_path / "m.jsonl")
    m = GovernedMemory(path=p)
    r = _add(m, body={"text": "persisted"})
    assert r.record_id in m._by_id
    m2 = GovernedMemory(path=p)
    assert len(m2._records) == 1
    r2 = m2._by_id[r.record_id]
    assert r2.body["text"] == "persisted"
    assert r2.tenant_id == "t1" and r2.nature == "verified_fact"
    assert r2.provenance["sources"] == ["e1"]


# --- tenant isolation ---------------------------------------------------------
def test_tenant_isolation():
    m = GovernedMemory()
    _add(m, tenant_id="t1")
    _add(m, tenant_id="t2")
    t1 = m.retrieve(tenant_id="t1")
    assert len(t1) == 1 and t1[0].tenant_id == "t1"
    assert all(r.tenant_id == "t1" for r in t1)


# --- no cross-tenant leakage --------------------------------------------------
def test_no_cross_tenant_leakage():
    m = GovernedMemory()
    _add(m, tenant_id="t1")
    # global dump / missing tenant is rejected
    with pytest.raises(ValueError):
        m.retrieve(tenant_id="")
    # another tenant sees nothing
    assert m.retrieve(tenant_id="other") == []


# --- classification enforcement ----------------------------------------------
def test_classification_enforcement():
    m = GovernedMemory()
    _add(m, classification="restricted")
    _add(m, classification="client_confidential")
    res = m.retrieve(tenant_id="t1", max_classification="client_confidential")
    assert len(res) == 1
    assert all(r.classification != "restricted" for r in res)
    assert len(m.retrieve(tenant_id="t1")) == 2  # no max -> both


# --- provenance preservation --------------------------------------------------
def test_provenance_preserved(tmp_path):
    p = str(tmp_path / "m.jsonl")
    m = GovernedMemory(path=p)
    r = m.add(
        kind="decision", nature="verified_fact", tenant_id="t1", client_id="c1",
        actor="a", role_id="r", source="src", classification="client_confidential",
        timestamp="2026-08-29T00:00:00Z", correlation_id="cX", confidence=0.9,
        evidence_refs=["e1"], data_mode="historical_consented",
        provenance={"correlation_id": "cX", "data_mode": "historical_consented",
                    "basis": "basis-x", "sources": ["sA", "sB"]},
        body={"text": "do X"},
    )
    assert r.provenance["correlation_id"] == "cX"
    assert r.provenance["sources"] == ["sA", "sB"]
    m2 = GovernedMemory(path=p)
    assert m2._by_id[r.record_id].provenance["sources"] == ["sA", "sB"]


# --- correction --------------------------------------------------------------
def test_correction(tmp_path):
    p = str(tmp_path / "m.jsonl")
    m = GovernedMemory(path=p)
    r = m.add(
        kind="decision", nature="verified_fact", tenant_id="t1", client_id="c1",
        actor="a", role_id="r", source="src", classification="client_confidential",
        timestamp="2026-08-29T00:00:00Z", correlation_id="corr-1", confidence=0.9,
        evidence_refs=["e1"], data_mode="historical_consented",
        provenance={"correlation_id": "corr-1", "data_mode": "historical_consented",
                    "basis": "test", "sources": ["e1"]},
        body={"text": "original"},
    )
    corr = m.correct(
        record_id=r.record_id, actor="a2", role_id="r2", reason="incorrect",
        correction_body={"text": "fixed"}, nature="user_claim",
        classification="client_confidential", correlation_id="corr-2",
        timestamp="2026-08-29T01:00:00Z", confidence=0.8,
    )
    assert corr.corrects == r.record_id
    assert any(s["relation"] == "corrects" and s["record_id"] == corr.record_id
               for s in m._by_id[r.record_id].supersession)
    assert m._by_id[r.record_id].retention_status == "corrected"
    # reload reconstructs supersession
    m2 = GovernedMemory(path=p)
    assert any(s["relation"] == "corrects" for s in m2._by_id[r.record_id].supersession)


# --- supersession ------------------------------------------------------------
def test_supersession(tmp_path):
    p = str(tmp_path / "m.jsonl")
    m = GovernedMemory(path=p)
    r = m.add(
        kind="decision", nature="verified_fact", tenant_id="t1", client_id="c1",
        actor="a", role_id="r", source="src", classification="client_confidential",
        timestamp="2026-08-29T00:00:00Z", correlation_id="corr-1", confidence=0.9,
        evidence_refs=["e1"], data_mode="historical_consented",
        provenance={"correlation_id": "corr-1", "data_mode": "historical_consented",
                    "basis": "test", "sources": ["e1"]},
        body={"text": "v1"},
    )
    sup = m.supersede(
        record_id=r.record_id, actor="a2", role_id="r2", reason="newer",
        superseding_body={"text": "v2"}, nature="verified_fact",
        classification="client_confidential", correlation_id="corr-2",
        timestamp="2026-08-29T01:00:00Z", confidence=0.95,
    )
    assert sup.supersedes == r.record_id
    assert m._by_id[r.record_id].retention_status == "superseded"
    m2 = GovernedMemory(path=p)
    assert any(s["relation"] == "supersedes" for s in m2._by_id[r.record_id].supersession)


# --- retention ---------------------------------------------------------------
def test_retention_flagged_not_dropped():
    m = GovernedMemory()
    r = _add(m, retention_until="2026-08-28T00:00:00Z")
    n = m.apply_retention("2026-08-29T00:00:00Z")
    assert n == 1
    assert m._by_id[r.record_id].retention_status == "expired"
    assert m.retrieve(tenant_id="t1", include_expired=False) == []
    assert len(m.retrieve(tenant_id="t1", include_expired=True)) == 1
    # never silently removed from the store
    assert r.record_id in m._by_id


# --- simulated vs historical labeling ---------------------------------------
def test_simulated_vs_historical_labeling():
    m = GovernedMemory()
    sim = m.add(kind="customer_context", nature="simulated_event",
                tenant_id="t1", client_id="c1", actor="a", role_id="r", source="s",
                classification="client_confidential", timestamp="2026-08-29T00:00:00Z",
                correlation_id="c1", confidence=0.0, data_mode="simulated_realistic",
                body={})
    hist = m.add(kind="customer_context", nature="historical_event",
                 tenant_id="t1", client_id="c1", actor="a", role_id="r", source="s",
                 classification="client_confidential", timestamp="2026-08-29T00:00:00Z",
                 correlation_id="c2", confidence=1.0, data_mode="historical_consented",
                 body={})
    assert sim.nature == "simulated_event" and sim.data_mode == "simulated_realistic"
    assert hist.nature == "historical_event" and hist.data_mode == "historical_consented"
    assert sim.nature != "historical_event"


# --- audit-chain integrity ---------------------------------------------------
def test_audit_chain_integrity(tmp_path):
    p = str(tmp_path / "m.jsonl")
    m = GovernedMemory(path=p)
    _add(m)
    _add(m, body={"text": "second"})
    ok, _ = m.verify_chain()
    assert ok is True
    # tamper with the first ledger line
    lines = open(p, "r", encoding="utf-8").read().splitlines()
    env = json.loads(lines[0])
    env["record"]["body"] = {"tampered": True}
    env["hash"] = "deadbeef"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(env) + "\n")
        for ln in lines[1:]:
            fh.write(ln + "\n")
    m2 = GovernedMemory(path=p)
    ok2, _ = m2.verify_chain()
    assert ok2 is False


# --- no unverified inference presented as fact -------------------------------
def test_no_unverified_inference_as_fact():
    m = GovernedMemory()
    inf = _add(m, kind="recommendation", nature="model_inference")
    fact = _add(m, kind="decision", nature="verified_fact")
    facts = m.retrieve_facts(tenant_id="t1")
    assert fact in facts
    assert inf not in facts
    assert inf.is_verified_fact() is False


# --- no silent deletion ------------------------------------------------------
def test_no_silent_deletion():
    m = GovernedMemory()
    r = _add(m)
    m.delete(record_id=r.record_id, actor="a", role_id="r", reason="oops",
             timestamp="2026-08-29T00:00:00Z")
    # record remains in the store (never physically removed)
    assert r.record_id in m._by_id
    assert m._by_id[r.record_id].deleted == "oops"
    # the deleted record is excluded from default retrieval...
    visible = m.retrieve(tenant_id="t1")
    assert all(x.record_id != r.record_id for x in visible)
    # ...and the deletion itself is audited (a workflow_history marker persists)
    dels = [x for x in m._records if x.kind == "workflow_history" and x.body.get("action") == "delete"]
    assert dels and dels[0].body["target"] == r.record_id


# --- no automatic policy/behavior change -------------------------------------
def test_no_auto_policy_change():
    m = GovernedMemory()
    assert m.auto_apply_policies is False
    before = len(m.retrieve(tenant_id="t1"))
    m.add(kind="policy", nature="user_claim", tenant_id="t1", client_id="c1",
          actor="a", role_id="r", source="s", classification="client_confidential",
          timestamp="2026-08-29T00:00:00Z", correlation_id="corr-p", confidence=1.0,
          data_mode="simulated_realistic", body={"policy": "auto-approve"})
    after = len(m.retrieve(tenant_id="t1"))
    # storing a policy only adds the record; it does not change behavior automatically
    assert after == before + 1
    pol = m.retrieve(tenant_id="t1", kinds=["policy"])
    assert len(pol) == 1 and pol[0].body["policy"] == "auto-approve"


# --- command-center display --------------------------------------------------
def test_command_center_display():
    from command_center_integration import assemble_command_center

    mem = GovernedMemory()
    mem.add(kind="policy", nature="user_claim", tenant_id="t1", client_id="Demo Account",
            actor="a", role_id="r", source="src", classification="client_confidential",
            timestamp="2026-08-29T00:00:00Z", correlation_id="corr-cc", confidence=1.0,
            data_mode="simulated_realistic", body={"policy": "demo"})
    v = assemble_command_center(
        "t1", "Demo Account", "a", "customer_success_gm", "simulated_realistic", "corr-cc",
        memory=mem,
    )
    assert any(mt.kind == "policy" for mt in v.memory_timeline)
    assert v.audit_status in {"in_memory_not_persisted", "verified", "broken"}

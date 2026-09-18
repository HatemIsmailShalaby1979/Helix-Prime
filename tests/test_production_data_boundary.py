"""
Production data-boundary tests for the general app and the sports-academy pack.

The app side pins the governed envelope (tenant, correlation, data_mode,
provenance, classification) and the rule that a verified outcome is never
recorded without evidence. The pack side pins synthetic/read-only mode,
NOT_ESTABLISHED readiness, live-data rejection at the connector funnel, and
the absence of real network connectors. The live-mode tests are the can-fail
proof: with the funnel guard patched out, live-stamped fixtures flow
through and the tests fail.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from connectors.contracts import ConnectorContext, SourceRef
from memory.governed_memory import GovernedMemory

TS = "2026-09-07T20:00:00Z"


def _academy_ctx(tenant_id="a1", client_id="ac1"):
    from capabilities.sports_academy.fixtures import DATA_MODE

    return ConnectorContext(
        tenant_id,
        "org-1",
        client_id,
        actor="academy-operator",
        correlation_id="corr-boundary-1",
        data_mode=DATA_MODE,
    )


def _add_kwargs(**overrides):
    base = {
        "kind": "decision",
        "nature": "model_inference",
        "tenant_id": "t1",
        "client_id": "c1",
        "actor": "a",
        "role_id": "r",
        "source": "boundary-test",
        "classification": "client_confidential",
        "timestamp": "2026-09-18T00:00:00Z",
        "correlation_id": "corr-boundary",
        "confidence": 0.5,
        "data_mode": "simulated_realistic",
        "provenance": {"data_mode": "simulated_realistic", "basis": "boundary-test"},
        "body": {},
    }
    base.update(overrides)
    return base


def test_missing_provenance_is_rejected() -> None:
    mem = GovernedMemory()
    with pytest.raises(ValueError, match="provenance"):
        mem.add(**_add_kwargs(provenance={}))
    with pytest.raises(ValueError, match="provenance"):
        mem.add(**_add_kwargs(provenance={"basis": "no-mode"}))


def test_missing_classification_is_rejected() -> None:
    mem = GovernedMemory()
    with pytest.raises(ValueError, match="classification"):
        mem.add(**_add_kwargs(classification="bogus-class"))


def test_missing_correlation_is_rejected() -> None:
    mem = GovernedMemory()
    with pytest.raises(ValueError, match="correlation_id"):
        mem.add(**_add_kwargs(correlation_id="  "))


def test_verified_outcome_without_evidence_is_rejected() -> None:
    mem = GovernedMemory()
    with pytest.raises(ValueError, match="evidence"):
        mem.add(**_add_kwargs(nature="verified_outcome"))
    with pytest.raises(ValueError, match="evidence"):
        mem.add(**_add_kwargs(nature="verified_fact"))
    verified = mem.add(**_add_kwargs(nature="verified_outcome", evidence_refs=["ev-1"]))
    assert verified.nature == "verified_outcome"
    inference = mem.add(**_add_kwargs(nature="model_inference"))
    assert inference.nature == "model_inference"


def test_cross_tenant_records_are_rejected() -> None:
    mem = GovernedMemory()
    mem.add(**_add_kwargs(tenant_id="tenant-a"))
    assert mem.retrieve(tenant_id="tenant-a")
    assert mem.retrieve(tenant_id="tenant-b") == []


def test_app_nodes_require_the_full_envelope(tmp_path) -> None:
    from helix_codex_app import db

    conn = db.connect(db_path=str(tmp_path / "app.db"))
    try:
        db._init_schema(conn)
        with pytest.raises(ValueError, match="classification"):
            db.record_node(
                conn,
                tenant_id="t1",
                correlation_id="corr-1",
                classification="bogus",
                nature="user_claim",
                created_by="a",
                provenance_source="test",
                provenance_data_mode="app_runtime",
                kind="message",
            )
        with pytest.raises(ValueError, match="correlation_id"):
            db.record_node(
                conn,
                tenant_id="t1",
                correlation_id="",
                classification="internal",
                nature="user_claim",
                created_by="a",
                provenance_source="test",
                provenance_data_mode="app_runtime",
                kind="message",
            )
        node_id = db.record_node(
            conn,
            tenant_id="t1",
            correlation_id="corr-1",
            classification="internal",
            nature="user_claim",
            created_by="a",
            provenance_source="test",
            provenance_data_mode="app_runtime",
            kind="message",
        )
        assert node_id
    finally:
        db.close(conn)


def test_pack_runs_simulated_read_only_and_not_established() -> None:
    from capabilities.sports_academy import fixtures
    from capabilities.sports_academy.register import get_academy_metadata

    assert fixtures.DATA_MODE == "simulated_realistic"
    metadata = get_academy_metadata()
    assert metadata["production_readiness"] == "NOT_ESTABLISHED"


def test_pack_connector_rejects_live_data() -> None:
    from capabilities.sports_academy.contracts import build_academy_connectors
    from capabilities.sports_academy.fixtures import build_synthetic_academy

    fixtures_map = build_synthetic_academy("a1", "ac1", TS)
    live_athlete = dataclasses.replace(
        fixtures_map["athletes"][0],
        source=SourceRef("AcademyOps", "ath-live", TS, "v1", "live_customer"),
    )
    fixtures_map = dict(fixtures_map)
    fixtures_map["athletes"] = [live_athlete, *fixtures_map["athletes"][1:]]
    conns = build_academy_connectors(_academy_ctx(), fixtures_map)
    with pytest.raises(ValueError, match="simulated"):
        conns["academy_ops"].list_athletes(_academy_ctx())


def test_pack_live_rejection_is_load_bearing(monkeypatch) -> None:
    import capabilities.sports_academy.contracts as contracts
    from capabilities.sports_academy.contracts import build_academy_connectors
    from capabilities.sports_academy.fixtures import build_synthetic_academy

    monkeypatch.setattr(contracts.AcademyConnector, "_reject_live_data", lambda self, data: None)
    fixtures_map = build_synthetic_academy("a1", "ac1", TS)
    live_athlete = dataclasses.replace(
        fixtures_map["athletes"][0],
        source=SourceRef("AcademyOps", "ath-live", TS, "v1", "live_customer"),
    )
    fixtures_map = dict(fixtures_map)
    fixtures_map["athletes"] = [live_athlete, *fixtures_map["athletes"][1:]]
    conns = build_academy_connectors(_academy_ctx(), fixtures_map)
    leaked = conns["academy_ops"].list_athletes(_academy_ctx())
    assert any(a.source.data_mode == "live_customer" for a in leaked)


def test_pack_has_no_live_network_connectors() -> None:
    pack_root = pathlib.Path("capabilities/sports_academy")
    assert pack_root.is_dir()
    offenders = []
    for path in sorted(pack_root.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.split("#", 1)[0]
            if stripped.strip().startswith(("import ", "from ")):
                module = stripped
                if any(
                    token in module
                    for token in ("socket", "requests", "urllib", "http.client", "httpx")
                ):
                    offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert not offenders, f"live network imports in the pack: {offenders}"


def test_production_scope_remains_consented_only() -> None:
    go_no_go = json.loads(pathlib.Path("release/go-no-go.json").read_text(encoding="utf-8"))
    assert go_no_go["data_scope"] == "SYNTHETIC_OR_CONSENTED_ONLY"


def test_boundary_documentation_separates_app_from_pack() -> None:
    text = pathlib.Path("docs/release/production-data-boundary.md").read_text(encoding="utf-8")
    assert "NOT_ESTABLISHED" in text
    assert "SYNTHETIC_OR_CONSENTED_ONLY" in text
    assert "Scoach" in text

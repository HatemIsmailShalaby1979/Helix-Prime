"""
A2 — the organization catalog is sourced, not mirrored.

Three claims are proved here:

A2.1  ``RoleSpec``'s four structural fields are *derived* from
      organization/role-catalog.yaml at import, and gating is independent of them.
A2.2  The eight runtime financial ceilings that are stricter than the YAML org chart
      are *declared* in ``FINANCIAL_LIMIT_OVERRIDES`` rather than left as silent drift.
A2.3  contracts/capabilities.yaml and organization/capabilities.json are generated
      artifacts of the canonical registry, and a stale one is caught.

Every guard gets a can-fail proof, matching the house style used elsewhere in
tests/ (see tests/test_production_data_boundary.py for the pattern).
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import pathlib
import sys

import pytest

import control_plane.governance as gov
from organization.capability_registry import validate_mirror_drift
from organization.role_catalog import load_role_catalog

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The three registry files the mirror machinery needs, relative to the repo root.
_REGISTRY_FILES = (
    "organization/capability-registry.yaml",
    "contracts/capabilities.yaml",
    "organization/capabilities.json",
)


def _load_sync_module():
    """Import scripts/sync_capability_mirrors.py (scripts/ is not a package)."""
    path = REPO_ROOT / "scripts" / "sync_capability_mirrors.py"
    spec = importlib.util.spec_from_file_location("sync_capability_mirrors", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_capability_mirrors"] = module
    spec.loader.exec_module(module)
    return module


def _copy_registry_files(root: pathlib.Path) -> None:
    """Materialise the three registry files under ``root`` so checks can run there."""
    for relative in _REGISTRY_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")


# ── A2.1 — structural fields are sourced from the YAML ─────────────────────


def test_every_seat_has_a_structural_entry():
    assert set(gov._STRUCTURAL_FIELDS) >= set(gov.ORGANIZATION_CATALOG)


def test_structural_fields_are_sourced_from_the_yaml():
    """
    The mirror is gone: every structural field on every seat equals the YAML.

    This is the test that would have failed before A2.1 if the hand-copied mirror had
    ever rotted — which is precisely the failure mode the mirror made possible.
    """
    yaml_roles = load_role_catalog("organization/role-catalog.yaml")["roles_by_id"]

    for role_id, spec in gov.ORGANIZATION_CATALOG.items():
        yaml_id = gov.YAML_ROLE_ALIASES.get(role_id, role_id)
        assert yaml_id in yaml_roles, f"{role_id}: no YAML entry ({yaml_id!r})"
        role = yaml_roles[yaml_id]
        sod = role["segregation_of_duties"]

        assert spec.owned_capabilities == tuple(role["owned_capabilities"]), role_id
        assert spec.allowed_tools == tuple(role["allowed_tools"]), role_id
        assert spec.allowed_peer_calls == tuple(role["allowed_peer_calls"]), role_id
        assert spec.segregation_of_duties == (
            tuple(sod["must_be_reviewed_by"]),
            tuple(sod["can_review"]),
        ), role_id


def test_structural_fields_are_tuples_not_lists():
    """RoleSpec declares Tuples; a list would make the dataclass silently unhashable."""
    for role_id, spec in gov.ORGANIZATION_CATALOG.items():
        for name in ("owned_capabilities", "allowed_tools", "allowed_peer_calls"):
            assert isinstance(getattr(spec, name), tuple), f"{role_id}.{name}"
        must_review, can_review = spec.segregation_of_duties
        assert isinstance(must_review, tuple) and isinstance(can_review, tuple), role_id


def test_fraud_alias_reads_the_yaml_fraud_gm_entry():
    """The runtime renamed the seat; the structural data must follow the alias."""
    assert gov.YAML_ROLE_ALIASES["fraud_revenue_gm"] == "fraud_gm"
    assert gov._STRUCTURAL_FIELDS["fraud_revenue_gm"] == gov._STRUCTURAL_FIELDS["fraud_gm"]


def test_structural_loader_fails_closed_when_the_yaml_cannot_be_read(monkeypatch):
    """A governance layer that cannot read its source of truth must not come up."""
    import organization.role_catalog as role_catalog

    def _unreadable(*args, **kwargs):
        raise ValueError("role catalog not found at organization/role-catalog.yaml")

    monkeypatch.setattr(role_catalog, "load_role_catalog", _unreadable)
    with pytest.raises(gov.RoleCatalogUnavailableError, match="structural"):
        gov._structural_role_fields()


def test_structural_lookup_fails_closed_for_a_seat_missing_from_the_yaml(monkeypatch):
    """A seat absent from the YAML must error, not inherit an empty capability set."""
    partial = {k: v for k, v in gov._STRUCTURAL_FIELDS.items() if k != "ops_gm"}
    monkeypatch.setattr(gov, "_STRUCTURAL_FIELDS", partial)
    with pytest.raises(gov.RoleCatalogUnavailableError, match="ops_gm"):
        gov._structural("ops_gm")


def test_evaluate_gate_is_independent_of_the_structural_fields():
    """
    The property that makes A2.1 safe: gating reads the authority fields only.

    Blanking every structural field on a seat must not move a single gate decision.
    If this ever fails, A2.1 stopped being a de-duplication and started changing who
    can do what.
    """
    cases = [
        dict(estimated_financial_cost=cost, data_classification=cls, target_engine=engine)
        for cost in (0.0, 250.0, 600.0, 10_000.0)
        for cls in ("internal", "personnel_sensitive", "financial")
        for engine in (None, "wfm", "control_plane")
    ]

    original = gov.ORGANIZATION_CATALOG
    try:
        for role_id in sorted(gov.ORGANIZATION_CATALOG):
            spec = gov.get_role(role_id)
            baseline = [gov.evaluate_gate(role_id, **kw).to_dict() for kw in cases]

            blanked = dataclasses.replace(
                spec,
                owned_capabilities=(),
                allowed_tools=(),
                allowed_peer_calls=(),
                segregation_of_duties=((), ()),
            )
            gov.ORGANIZATION_CATALOG = gov._OrganizationCatalog(
                {**dict(original), role_id: blanked}
            )
            after = [gov.evaluate_gate(role_id, **kw).to_dict() for kw in cases]

            assert baseline == after, f"{role_id}: gating moved when structural fields changed"
    finally:
        gov.ORGANIZATION_CATALOG = original


# ── A2.2 — the stricter ceilings are declared, not discovered ─────────────


def test_every_seat_declares_its_financial_ceiling():
    """A seat may not inherit 'unlimited' by omission."""
    for role_id in gov.ORGANIZATION_CATALOG:
        declared = role_id in gov.FINANCIAL_LIMIT_OVERRIDES or role_id in (
            gov.UNLIMITED_FINANCIAL_ROLES
        )
        assert declared, f"{role_id} declares no runtime financial ceiling"


def test_runtime_ceilings_come_from_the_declared_overrides():
    for role_id, spec in gov.ORGANIZATION_CATALOG.items():
        expected = gov._financial_limit(role_id)
        assert spec.financial_approval_limit_usd == expected, role_id


def test_unlimited_and_overridden_are_disjoint():
    assert not (set(gov.FINANCIAL_LIMIT_OVERRIDES) & set(gov.UNLIMITED_FINANCIAL_ROLES))


def test_accepted_drift_set_is_derived_from_the_override_map():
    """The pin and the declaration must not be able to disagree."""
    assert gov.ACCEPTED_FINANCIAL_DRIFT_ROLES == frozenset(gov.FINANCIAL_LIMIT_OVERRIDES)
    assert gov.ACCEPTED_FINANCIAL_DRIFT_ROLES == {
        "ops_gm",
        "compliance_quality_gm",
        "fraud_revenue_gm",
        "hr_personnel_gm",
        "ld_gm",
        "sales_gm",
        "marketing_gm",
        "ict_gm",
    }


def test_financial_limit_lookup_fails_closed_for_an_undeclared_seat():
    with pytest.raises(gov.RoleCatalogUnavailableError, match="undeclared_seat"):
        gov._financial_limit("undeclared_seat")


# ── A2.3 — the mirrors are generated artifacts ─────────────────────────────


def test_generator_emits_exactly_the_committed_mirrors():
    """A hand-edited mirror would fail here, not in production."""
    module = _load_sync_module()
    canonical = module.load_canonical()

    assert (REPO_ROOT / module.YAML_MIRROR).read_text(
        encoding="utf-8"
    ) == module.render_yaml_mirror(canonical)
    assert (REPO_ROOT / module.JSON_MIRROR).read_text(
        encoding="utf-8"
    ) == module.render_json_mirror(canonical)


def test_generator_is_deterministic():
    """Regenerating from an unchanged canonical must be a no-op."""
    module = _load_sync_module()
    canonical = module.load_canonical()
    assert module.render_yaml_mirror(canonical) == module.render_yaml_mirror(canonical)
    assert module.render_json_mirror(canonical) == module.render_json_mirror(canonical)


def test_generator_carries_the_canonical_generated_stamp():
    """The stamp is inherited, so output does not churn on every run."""
    module = _load_sync_module()
    canonical = module.load_canonical()
    assert f'generated: "{canonical["generated"]}"' in module.render_yaml_mirror(canonical)
    assert json.loads(module.render_json_mirror(canonical))["generated"] == canonical["generated"]


def test_generator_check_passes_on_a_clean_copy(monkeypatch, tmp_path):
    module = _load_sync_module()
    _copy_registry_files(tmp_path)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    errors, report = module.check_mirrors()
    assert errors == [], report
    assert report["engine_capability_count"] == 22


def test_generator_check_flags_a_stale_header(monkeypatch, tmp_path):
    """A comment-only edit is still a stale artifact — and reads differently."""
    module = _load_sync_module()
    _copy_registry_files(tmp_path)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    mirror = tmp_path / module.YAML_MIRROR
    mirror.write_text(mirror.read_text(encoding="utf-8") + "# hand edit\n", encoding="utf-8")

    errors, report = module.check_mirrors()
    assert errors
    assert report["files"][module.YAML_MIRROR]["semantic_current"] is True


def test_generator_check_flags_a_diverged_mapping(monkeypatch, tmp_path):
    module = _load_sync_module()
    _copy_registry_files(tmp_path)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    mirror = tmp_path / module.JSON_MIRROR
    data = json.loads(mirror.read_text(encoding="utf-8"))
    data["engine_capabilities"]["erlang_c"] = "Somewhere Else"
    mirror.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors, report = module.check_mirrors()
    assert errors
    assert report["files"][module.JSON_MIRROR]["semantic_current"] is False


def test_generator_check_flags_a_missing_mirror(monkeypatch, tmp_path):
    module = _load_sync_module()
    _copy_registry_files(tmp_path)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    (tmp_path / module.JSON_MIRROR).unlink()

    errors, report = module.check_mirrors()
    assert errors
    assert report["files"][module.JSON_MIRROR]["exists"] is False


def test_validate_mirror_drift_passes_on_the_committed_mirrors():
    validate_mirror_drift()  # must not raise


def test_validate_mirror_drift_detects_a_diverged_mapping(monkeypatch, tmp_path):
    import organization.capability_registry as registry

    _copy_registry_files(tmp_path)
    monkeypatch.setattr(registry, "_REPO_ROOT", tmp_path)
    validate_mirror_drift()  # clean copy is accepted first

    mirror = tmp_path / "contracts/capabilities.yaml"
    mirror.write_text(
        mirror.read_text(encoding="utf-8").replace(
            'erlang_c: "WFM Forecasting"', 'erlang_c: "Nope"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="drift detected"):
        validate_mirror_drift()


def test_validate_mirror_drift_detects_a_missing_mirror(monkeypatch, tmp_path):
    import organization.capability_registry as registry

    _copy_registry_files(tmp_path)
    (tmp_path / "organization/capabilities.json").unlink()
    monkeypatch.setattr(registry, "_REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="missing"):
        validate_mirror_drift()


def test_validate_mirror_drift_detects_stripped_provenance(monkeypatch, tmp_path):
    """A mirror without provenance is a hand-maintained orphan, not an artifact."""
    import organization.capability_registry as registry

    _copy_registry_files(tmp_path)
    monkeypatch.setattr(registry, "_REPO_ROOT", tmp_path)

    mirror = tmp_path / "organization/capabilities.json"
    data = json.loads(mirror.read_text(encoding="utf-8"))
    del data["canonical_source"]
    mirror.write_text(json.dumps(data, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="provenance"):
        validate_mirror_drift()


# ── A4: RoleSpec.to_dict projects every stored field ────────────────────────


def test_role_spec_to_dict_projects_every_stored_field():
    """A projection that silently drops four fields is a lie about the seat."""
    for role_id in sorted(gov.ORGANIZATION_CATALOG):
        spec = gov.get_role(role_id)
        projected = spec.to_dict()
        for field in dataclasses.fields(spec):
            assert field.name in projected, f"{role_id}: {field.name} missing from to_dict()"


def test_role_spec_to_dict_emits_the_yaml_shape_for_sod():
    """``segregation_of_duties`` is emitted with the YAML's keys, not the storage pair."""
    projected = gov.get_role("ops_gm").to_dict()
    assert projected["segregation_of_duties"] == {
        "must_be_reviewed_by": ["compliance_quality_gm"],
        "can_review": [],
    }


def test_role_spec_to_dict_round_trips_the_structural_fields_from_the_yaml():
    yaml_roles = load_role_catalog()["roles_by_id"]
    for role_id in sorted(gov.ORGANIZATION_CATALOG):
        # The runtime catalog keeps one legacy seat name; the alias is declared,
        # so the round-trip goes through it rather than around it.
        yaml_role = yaml_roles[gov.YAML_ROLE_ALIASES.get(role_id, role_id)]
        projected = gov.get_role(role_id).to_dict()
        assert projected["owned_capabilities"] == list(yaml_role["owned_capabilities"])
        assert projected["allowed_tools"] == list(yaml_role["allowed_tools"])
        assert projected["allowed_peer_calls"] == list(yaml_role["allowed_peer_calls"])
        assert projected["segregation_of_duties"] == {
            "must_be_reviewed_by": list(yaml_role["segregation_of_duties"]["must_be_reviewed_by"]),
            "can_review": list(yaml_role["segregation_of_duties"]["can_review"]),
        }


def test_role_spec_to_dict_is_json_serialisable():
    """to_dict() exists to hand JSON-shaped records to adapters."""
    for role_id in sorted(gov.ORGANIZATION_CATALOG):
        json.dumps(gov.get_role(role_id).to_dict())


def test_role_spec_to_dict_can_fail():
    """Can-fail proof: the completeness guard above catches a dropped field."""
    spec = gov.get_role("ops_gm")
    incomplete = {k: v for k, v in spec.to_dict().items() if k != "allowed_peer_calls"}
    missing = [f.name for f in dataclasses.fields(spec) if f.name not in incomplete]
    assert missing == ["allowed_peer_calls"]

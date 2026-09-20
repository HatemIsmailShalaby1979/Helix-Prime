"""
Tests for contracts/vocabulary.py — the single source of truth for the
data-mode and data-classification vocabularies.

Verifies that:
- every mapping table is total over the union it maps from
- no mapping target is ``live_customer``, and live modes fail closed in
  ``to_pilot`` (the pilot never activates live customer data)
- the classification maps are total and never invent a new level
- the two files held frozen by policy still agree with the vocabulary, so a
  divergence fails CI instead of landing silently
- no module re-introduces a private copy of a vocabulary literal
"""
from __future__ import annotations

import pathlib
import re

import pytest

from contracts import vocabulary as v

#: Files that legitimately still declare a ``DATA_MODE`` literal because the
#: approved plan freezes them (``capabilities/sports_academy/fixtures.py``
#: carries pinned numeric assertions). A test below pins them to the
#: vocabulary, so this set is an allow-list of *guarded* debt, not an exemption.
FROZEN_DATA_MODE_LITERAL_FILES = {"capabilities/sports_academy/fixtures.py"}

#: Directories scanned for stray literal copies. A fixed list keeps the scan
#: fast and predictable; it covers every package that can hold a data mode.
SCAN_ROOTS = (
    "app",
    "capabilities",
    "cloud",
    "cockpit",
    "connectors",
    "contracts",
    "control_plane",
    "customer_success",
    "demo",
    "engines",
    "helix_codex_app",
    "integrations",
    "memory",
    "metacognition",
    "observability",
    "orchestration",
    "organization",
    "pilot",
    "release",
    "security",
    "server",
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _scanned_python_files():
    for name in SCAN_ROOTS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


# ── data modes: totality ────────────────────────────────────────────────────


def test_data_mode_union_is_the_declared_nine():
    """The union is exactly the nine distinct strings the five seams can emit."""
    assert v.DATA_MODES == {
        "historical_anonymized",
        "historical_consented",
        "simulated_realistic",
        "live_external",
        "live_customer",
        "app_runtime",
        "live",
        "sample",
        "simulated",
    }
    assert len(v.DATA_MODES) == 9


def test_each_seam_vocabulary_is_a_subset_of_the_union():
    for seam in (
        v.CONNECTOR_DATA_MODES,
        v.PILOT_DATA_MODES,
        v.ENGINE_DATA_MODES,
        v.APP_RUNTIME_DATA_MODES,
        v.PACK_DATA_MODES,
    ):
        assert seam <= v.DATA_MODES


def test_every_data_mode_map_is_total():
    """A missing key would make a real mode unmappable — the drift this prevents.

    ``to_pilot`` is total in the weaker sense that every mode is either mapped or
    explicitly refused, so its mapped keys plus its refused set must cover the
    union.
    """
    assert set(v._TO_CONNECTOR) == v.DATA_MODES
    assert set(v._TO_ENGINE) == v.DATA_MODES
    assert set(v._TO_PACK) == v.DATA_MODES
    assert set(v._TO_PILOT) | v.PILOT_REFUSED_DATA_MODES == v.DATA_MODES


def test_pilot_refusal_does_not_overlap_the_mapped_set():
    """A mode cannot be both mapped and refused; that would be ambiguous."""
    assert not (set(v._TO_PILOT) & v.PILOT_REFUSED_DATA_MODES)


def test_every_map_target_belongs_to_its_own_vocabulary():
    assert set(v._TO_CONNECTOR.values()) <= v.CONNECTOR_DATA_MODES
    assert set(v._TO_ENGINE.values()) <= v.ENGINE_DATA_MODES
    assert set(v._TO_PACK.values()) <= v.PACK_DATA_MODES
    assert set(v._TO_PILOT.values()) <= v.PILOT_DATA_MODES


# ── data modes: the live-customer guard ─────────────────────────────────────


def test_no_mapping_target_is_live_customer():
    """The one value no mapping may produce.

    ``live_customer`` names the mode the pilot must never run on. Producing it
    from a mapping would silently activate live customer data, so no table may
    have it as a target.
    """
    targets = (
        set(v._TO_CONNECTOR.values())
        | set(v._TO_ENGINE.values())
        | set(v._TO_PACK.values())
        | set(v._TO_PILOT.values())
    )
    assert v.PILOT_LIVE_CUSTOMER not in targets


@pytest.mark.parametrize("mode", sorted(v.PILOT_REFUSED_DATA_MODES))
def test_to_pilot_refuses_every_live_mode(mode):
    with pytest.raises(ValueError, match="refusing live mode"):
        v.to_pilot(mode)


@pytest.mark.parametrize("mode", sorted(v.DATA_MODES))
def test_to_pilot_never_returns_live_customer(mode):
    """Sweep the whole union: refusal or a safe mode, never ``live_customer``."""
    try:
        mapped = v.to_pilot(mode)
    except ValueError:
        return
    assert mapped != v.PILOT_LIVE_CUSTOMER
    assert mapped in v.PILOT_DATA_MODES


def test_pilot_refusals_cover_exactly_the_live_modes():
    assert v.PILOT_REFUSED_DATA_MODES == v.LIVE_DATA_MODES


def test_unknown_data_mode_fails_closed():
    for mapper in (v.to_connector, v.to_engine, v.to_pack, v.to_pilot):
        with pytest.raises(ValueError):
            mapper("not_a_mode")
        with pytest.raises(ValueError):
            mapper("")


def test_known_mappings_are_stable():
    """Pin the handful of mappings whose meaning is not obvious."""
    assert v.to_connector(v.APP_RUNTIME_DATA_MODE) == v.CONNECTOR_SIMULATED_REALISTIC
    assert v.to_engine(v.APP_RUNTIME_DATA_MODE) == v.ENGINE_SAMPLE
    assert v.to_pack(v.ENGINE_SAMPLE) == v.PACK_SIMULATED
    assert v.to_pilot(v.ENGINE_SAMPLE) == v.PILOT_SIMULATED_REALISTIC
    # Anonymised history is still history: it is not "live", and the pilot
    # vocabulary has no separate spelling for it.
    assert v.to_pilot(v.CONNECTOR_HISTORICAL_ANONYMIZED) == v.PILOT_HISTORICAL_CONSENTED


# ── classifications ─────────────────────────────────────────────────────────


def test_classification_union_is_the_declared_eight():
    assert len(v.ALL_CLASSIFICATIONS) == 8
    assert v.CORE_CLASSIFICATIONS == v.ALL_CLASSIFICATIONS - {"restricted", "regulated"}


def test_core_classifications_are_the_canonical_six():
    """The core vocabulary is re-exported, not redeclared."""
    from security.classification import DataClassification

    assert v.CORE_CLASSIFICATIONS == frozenset(DataClassification.ALL)


def test_every_classification_map_is_total():
    assert set(v._TO_MEMORY_CLASSIFICATION) == v.ALL_CLASSIFICATIONS
    assert set(v._TO_INTEGRATION_CLASSIFICATION) == v.ALL_CLASSIFICATIONS
    assert set(v._TO_CORE_CLASSIFICATION) == v.ALL_CLASSIFICATIONS


def test_classification_map_targets_belong_to_their_vocabulary():
    assert set(v._TO_MEMORY_CLASSIFICATION.values()) <= v.MEMORY_CLASSIFICATIONS
    assert set(v._TO_INTEGRATION_CLASSIFICATION.values()) <= v.INTEGRATION_CLASSIFICATIONS
    assert set(v._TO_CORE_CLASSIFICATION.values()) <= v.CORE_CLASSIFICATIONS


def test_levels_the_narrower_vocabulary_cannot_express_collapse_to_strictest():
    """A four-level vocabulary cannot hold the three strictest core levels.

    Collapsing them onto ``restricted`` is the fail-closed direction. Mapping
    any of them onto ``public``/``internal`` would be a silent downgrade.
    """
    from security.classification import DataClassification

    for level in (
        DataClassification.PERSONNEL_SENSITIVE,
        DataClassification.FINANCIAL,
        DataClassification.REGULATED_HIGH_RISK,
    ):
        assert v.to_memory_classification(level) == "restricted"


def test_no_core_level_maps_downwards():
    """Every mapped value is the level itself or a stricter one."""
    from security.classification import DataClassification

    order = {level: index for index, level in enumerate(DataClassification.SENSITIVITY_ORDER)}
    for level in DataClassification.SENSITIVITY_ORDER:
        mapped = v.to_core_classification(level)
        assert order[mapped] >= order[level], f"{level} was downgraded to {mapped}"


def test_regulated_and_regulated_high_risk_compare_equal_across_seams():
    """The two seams spell the top level differently; meaning is what counts."""
    assert v.to_core_classification("regulated") == v.to_core_classification("regulated_high_risk")
    assert v.classifications_equal("regulated", "regulated_high_risk")


def test_classifications_equal_still_separates_genuinely_different_levels():
    assert not v.classifications_equal("restricted", "personnel_sensitive")
    assert not v.classifications_equal("public", "client_confidential")
    assert v.classifications_equal("internal", "internal")


def test_unknown_classification_fails_closed():
    for mapper in (
        v.to_memory_classification,
        v.to_integration_classification,
        v.to_core_classification,
        v.classifications_equal,
    ):
        with pytest.raises(ValueError):
            if mapper is v.classifications_equal:
                mapper("not_a_level", "public")
            else:
                mapper("not_a_level")


# ── frozen files stay pinned to the vocabulary ──────────────────────────────


def test_frozen_pilot_scope_agrees_with_the_vocabulary():
    """``pilot/scope.py`` is frozen by the plan, so pin it instead of editing it.

    The pilot package is the deployed artifact; this test is what makes leaving
    its three constants in place safe rather than a silent second source.
    """
    import pilot.scope as scope

    assert scope.HISTORICAL_CONSENTED == v.PILOT_HISTORICAL_CONSENTED
    assert scope.SIMULATED_REALISTIC == v.PILOT_SIMULATED_REALISTIC
    assert scope.LIVE_CUSTOMER == v.PILOT_LIVE_CUSTOMER


def test_frozen_sports_academy_fixture_agrees_with_the_vocabulary():
    from capabilities.sports_academy import fixtures

    assert fixtures.DATA_MODE == v.CONNECTOR_SIMULATED_REALISTIC


def test_connector_seam_declares_the_shared_vocabulary():
    from connectors.contracts import ConnectorContext

    for mode in sorted(v.CONNECTOR_DATA_MODES):
        ctx = ConnectorContext(tenant_id="t", organization_id="o", client_id="c", data_mode=mode)
        assert ctx.data_mode == mode
    with pytest.raises(ValueError):
        ConnectorContext(tenant_id="t", organization_id="o", client_id="c", data_mode="app_runtime")


def test_engine_seam_declares_the_shared_vocabulary():
    from engines.contracts import DATA_MODE_LIVE, DATA_MODE_SAMPLE

    assert DATA_MODE_LIVE == v.ENGINE_LIVE
    assert DATA_MODE_SAMPLE == v.ENGINE_SAMPLE


def test_pack_loader_accepts_the_shared_pack_vocabulary():
    from helix_codex_app.modules.lowcode.pack_loader import _ALLOWED_DATA_MODES

    assert _ALLOWED_DATA_MODES == v.PACK_DATA_MODES


@pytest.mark.parametrize(
    "module_path",
    [
        "helix_codex_app.modules.admin.service",
        "helix_codex_app.modules.tasks.service",
        "helix_codex_app.modules.docs.service",
        "helix_codex_app.modules.calendar.service",
        "helix_codex_app.modules.notifications.service",
        "helix_codex_app.modules.attendance.service",
        "helix_codex_app.modules.messaging.service",
        "helix_codex_app.modules.memory.service",
    ],
)
def test_app_modules_use_the_shared_app_runtime_constant(module_path):
    module = __import__(module_path, fromlist=["PROVENANCE_DATA_MODE"])

    assert module.PROVENANCE_DATA_MODE == v.APP_RUNTIME_DATA_MODE


# ── no new private copies ───────────────────────────────────────────────────


def test_no_module_level_data_mode_literal_outside_the_allow_list():
    """A sixteenth copy of the literal is how these vocabularies diverged.

    Only the frozen fixture may still declare one, and the test above pins it.
    """
    pattern = re.compile(r'^DATA_MODE\s*=\s*"')
    offenders = []
    for path in _scanned_python_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in FROZEN_DATA_MODE_LITERAL_FILES:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.match(line):
                offenders.append(f"{relative}:{number}")
    assert offenders == [], (
        f"module-level DATA_MODE literal(s) found outside the allow-list: {offenders}; "
        "import the constant from contracts.vocabulary instead"
    )


def test_no_module_level_provenance_data_mode_literal_anywhere():
    pattern = re.compile(r'^PROVENANCE_DATA_MODE\s*=\s*"')
    offenders = []
    for path in _scanned_python_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.match(line):
                offenders.append(f"{relative}:{number}")
    assert offenders == [], (
        f"PROVENANCE_DATA_MODE literal(s) found: {offenders}; "
        "import APP_RUNTIME_DATA_MODE from contracts.vocabulary instead"
    )

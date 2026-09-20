"""
Single source of truth for the data-mode and data-classification vocabularies.

The platform answers the same two questions — *where did this data come from?* and
*how sensitive is it?* — at five different seams, and each seam grew its own
vocabulary. This module does **not** unify them: the strings are pinned by tests
and, in places, by client-facing contracts, so rewriting them would break real
agreements. Instead it:

1. declares each vocabulary exactly once, as the constant every seam imports, and
2. provides explicit, total mapping helpers between them.

Consumers must import the constant rather than re-spelling the literal. A literal
copied into a new file is how these vocabularies diverged in the first place.

Data modes
----------
==============================  ===================================================
Seam                            Members
==============================  ===================================================
connector (``connectors``)      historical_anonymized, historical_consented,
                                simulated_realistic, live_external
pilot (``pilot``)               historical_consented, simulated_realistic,
                                live_customer
engine (``engines``)            live, sample
app runtime (``helix_codex_app``)  app_runtime
pack manifest (``lowcode``)     live, simulated
==============================  ===================================================

``live_customer`` is never a mapping *target*. The pilot package never activates
live customer data, so a live mode fails closed in :func:`to_pilot` instead of
being silently relabelled into the one mode the pilot must not run on. The refusal
is declared in :data:`PILOT_REFUSED_DATA_MODES`, so it is a decision rather than an
oversight, and ``tests/test_vocabulary.py`` asserts it.

Classifications
---------------
``security.classification.DataClassification`` is the canonical core vocabulary and
is re-exported here (:data:`CORE_CLASSIFICATIONS`) rather than redeclared. Two
narrower vocabularies sit alongside it and are mapped onto it:

* :data:`MEMORY_CLASSIFICATIONS` — the four-level vocabulary used by governed
  memory, the app database, and the pilot scope; and
* :data:`INTEGRATION_CLASSIFICATIONS` — the six-level integration vocabulary, which
  spells the top level ``regulated`` where the core spells it ``regulated_high_risk``.

That last difference is a genuine divergence, not a rename: the two strings are
different values that both mean "highest sensitivity". Use
:func:`classifications_equal` when comparing across seams so the comparison is made
on meaning rather than on spelling.

Every classification mapping collapses *outward-in* levels onto the strictest
member of the target vocabulary. A mapping never lowers sensitivity.
"""
from __future__ import annotations

from typing import Dict, FrozenSet

from memory.governed_memory import KINDS as _MEMORY_KINDS
from memory.governed_memory import NATURES as _MEMORY_NATURES
from security.classification import DataClassification

# ── data modes: one declaration per seam ────────────────────────────────────

#: Connector seam. See ``connectors/contracts.py``.
CONNECTOR_HISTORICAL_ANONYMIZED = "historical_anonymized"
CONNECTOR_HISTORICAL_CONSENTED = "historical_consented"
CONNECTOR_SIMULATED_REALISTIC = "simulated_realistic"
CONNECTOR_LIVE_EXTERNAL = "live_external"

CONNECTOR_DATA_MODES: FrozenSet[str] = frozenset(
    {
        CONNECTOR_HISTORICAL_ANONYMIZED,
        CONNECTOR_HISTORICAL_CONSENTED,
        CONNECTOR_SIMULATED_REALISTIC,
        CONNECTOR_LIVE_EXTERNAL,
    }
)

#: Pilot seam. See ``pilot/scope.py``.
PILOT_HISTORICAL_CONSENTED = "historical_consented"
PILOT_SIMULATED_REALISTIC = "simulated_realistic"
PILOT_LIVE_CUSTOMER = "live_customer"

PILOT_DATA_MODES: FrozenSet[str] = frozenset(
    {
        PILOT_HISTORICAL_CONSENTED,
        PILOT_SIMULATED_REALISTIC,
        PILOT_LIVE_CUSTOMER,
    }
)

#: Engine adapter seam. See ``engines/contracts.py``.
ENGINE_LIVE = "live"
ENGINE_SAMPLE = "sample"

ENGINE_DATA_MODES: FrozenSet[str] = frozenset({ENGINE_LIVE, ENGINE_SAMPLE})

#: Application-runtime seam. The app records its own provenance, which is neither
#: a historical load nor a live external feed.
APP_RUNTIME_DATA_MODE = "app_runtime"

APP_RUNTIME_DATA_MODES: FrozenSet[str] = frozenset({APP_RUNTIME_DATA_MODE})

#: Capability pack manifest seam. See ``helix_codex_app/modules/lowcode``.
PACK_LIVE = "live"
PACK_SIMULATED = "simulated"

PACK_DATA_MODES: FrozenSet[str] = frozenset({PACK_LIVE, PACK_SIMULATED})

#: Every data-mode string the platform can observe, across all five seams.
DATA_MODES: FrozenSet[str] = frozenset().union(
    CONNECTOR_DATA_MODES,
    PILOT_DATA_MODES,
    ENGINE_DATA_MODES,
    APP_RUNTIME_DATA_MODES,
    PACK_DATA_MODES,
)

#: Modes denoting live, externally sourced production data. ``ENGINE_LIVE`` and
#: ``PACK_LIVE`` are the same string, so this set holds three distinct values.
LIVE_DATA_MODES: FrozenSet[str] = frozenset(
    {CONNECTOR_LIVE_EXTERNAL, PILOT_LIVE_CUSTOMER, ENGINE_LIVE, PACK_LIVE}
)

# ── data-mode mapping tables ────────────────────────────────────────────────
#
# Keyed by the nine distinct strings in DATA_MODES. Values are the target
# vocabulary's spelling of the same provenance.

_TO_CONNECTOR: Dict[str, str] = {
    CONNECTOR_HISTORICAL_ANONYMIZED: CONNECTOR_HISTORICAL_ANONYMIZED,
    CONNECTOR_HISTORICAL_CONSENTED: CONNECTOR_HISTORICAL_CONSENTED,
    CONNECTOR_SIMULATED_REALISTIC: CONNECTOR_SIMULATED_REALISTIC,
    CONNECTOR_LIVE_EXTERNAL: CONNECTOR_LIVE_EXTERNAL,
    PILOT_LIVE_CUSTOMER: CONNECTOR_LIVE_EXTERNAL,
    APP_RUNTIME_DATA_MODE: CONNECTOR_SIMULATED_REALISTIC,
    ENGINE_LIVE: CONNECTOR_LIVE_EXTERNAL,
    ENGINE_SAMPLE: CONNECTOR_SIMULATED_REALISTIC,
    PACK_SIMULATED: CONNECTOR_SIMULATED_REALISTIC,
}

_TO_ENGINE: Dict[str, str] = {
    CONNECTOR_HISTORICAL_ANONYMIZED: ENGINE_SAMPLE,
    CONNECTOR_HISTORICAL_CONSENTED: ENGINE_SAMPLE,
    CONNECTOR_SIMULATED_REALISTIC: ENGINE_SAMPLE,
    CONNECTOR_LIVE_EXTERNAL: ENGINE_LIVE,
    PILOT_LIVE_CUSTOMER: ENGINE_LIVE,
    APP_RUNTIME_DATA_MODE: ENGINE_SAMPLE,
    ENGINE_LIVE: ENGINE_LIVE,
    ENGINE_SAMPLE: ENGINE_SAMPLE,
    PACK_SIMULATED: ENGINE_SAMPLE,
}

_TO_PACK: Dict[str, str] = {
    CONNECTOR_HISTORICAL_ANONYMIZED: PACK_SIMULATED,
    CONNECTOR_HISTORICAL_CONSENTED: PACK_SIMULATED,
    CONNECTOR_SIMULATED_REALISTIC: PACK_SIMULATED,
    CONNECTOR_LIVE_EXTERNAL: PACK_LIVE,
    PILOT_LIVE_CUSTOMER: PACK_LIVE,
    APP_RUNTIME_DATA_MODE: PACK_SIMULATED,
    ENGINE_LIVE: PACK_LIVE,
    ENGINE_SAMPLE: PACK_SIMULATED,
    PACK_SIMULATED: PACK_SIMULATED,
}

#: Modes :func:`to_pilot` refuses rather than relabels. ``live_customer`` is
#: included: the pilot vocabulary names it only to *distinguish* it, never to
#: select it, so no mapping may produce it.
PILOT_REFUSED_DATA_MODES: FrozenSet[str] = frozenset(
    {CONNECTOR_LIVE_EXTERNAL, PILOT_LIVE_CUSTOMER, ENGINE_LIVE}
)

_TO_PILOT: Dict[str, str] = {
    CONNECTOR_HISTORICAL_ANONYMIZED: PILOT_HISTORICAL_CONSENTED,
    CONNECTOR_HISTORICAL_CONSENTED: PILOT_HISTORICAL_CONSENTED,
    CONNECTOR_SIMULATED_REALISTIC: PILOT_SIMULATED_REALISTIC,
    APP_RUNTIME_DATA_MODE: PILOT_SIMULATED_REALISTIC,
    ENGINE_SAMPLE: PILOT_SIMULATED_REALISTIC,
    PACK_SIMULATED: PILOT_SIMULATED_REALISTIC,
}

# ── governed-memory kind and nature vocabularies ────────────────────────────

#: The governed-memory seam's record kinds and epistemic natures, re-exported
#: from ``memory.governed_memory`` for the same reason as
#: :data:`CORE_CLASSIFICATIONS`: one declaration, not two. The app database
#: validates its node envelope against these *plus* its own domain nouns, which
#: is why they are surfaced here rather than reached for across the app seam.
GOVERNED_MEMORY_KINDS: FrozenSet[str] = frozenset(_MEMORY_KINDS)
GOVERNED_MEMORY_NATURES: FrozenSet[str] = frozenset(_MEMORY_NATURES)

# ── classification vocabularies ─────────────────────────────────────────────

#: Canonical core vocabulary — re-exported from ``security.classification`` so
#: there is one declaration, not two.
CORE_CLASSIFICATIONS: FrozenSet[str] = frozenset(DataClassification.ALL)

#: Governed-memory / app-database / pilot-scope vocabulary. Four levels, so
#: ``personnel_sensitive``, ``financial`` and ``regulated_high_risk`` have no
#: dedicated spelling and collapse to ``restricted``.
MEMORY_CLASSIFICATIONS: FrozenSet[str] = frozenset(
    {"public", "internal", "client_confidential", "restricted"}
)

#: Integration vocabulary. Six levels; spells the top level ``regulated``.
INTEGRATION_CLASSIFICATIONS: FrozenSet[str] = frozenset(
    {
        "public",
        "internal",
        "client_confidential",
        "personnel_sensitive",
        "financial",
        "regulated",
    }
)

#: Every classification string the platform can observe, across all three
#: vocabularies. Eight distinct values.
ALL_CLASSIFICATIONS: FrozenSet[str] = frozenset().union(
    CORE_CLASSIFICATIONS,
    MEMORY_CLASSIFICATIONS,
    INTEGRATION_CLASSIFICATIONS,
)

#: The strictest member of each narrower vocabulary, used as the collapse target
#: for core levels that the narrower vocabulary cannot express.
_MEMORY_STRICTEST = "restricted"
_INTEGRATION_STRICTEST = "regulated"

_TO_MEMORY_CLASSIFICATION: Dict[str, str] = {
    DataClassification.PUBLIC: "public",
    DataClassification.INTERNAL: "internal",
    DataClassification.CLIENT_CONFIDENTIAL: "client_confidential",
    DataClassification.PERSONNEL_SENSITIVE: _MEMORY_STRICTEST,
    DataClassification.FINANCIAL: _MEMORY_STRICTEST,
    DataClassification.REGULATED_HIGH_RISK: _MEMORY_STRICTEST,
    _MEMORY_STRICTEST: _MEMORY_STRICTEST,
    _INTEGRATION_STRICTEST: _MEMORY_STRICTEST,
}

_TO_INTEGRATION_CLASSIFICATION: Dict[str, str] = {
    DataClassification.PUBLIC: "public",
    DataClassification.INTERNAL: "internal",
    DataClassification.CLIENT_CONFIDENTIAL: "client_confidential",
    DataClassification.PERSONNEL_SENSITIVE: DataClassification.PERSONNEL_SENSITIVE,
    DataClassification.FINANCIAL: DataClassification.FINANCIAL,
    DataClassification.REGULATED_HIGH_RISK: _INTEGRATION_STRICTEST,
    _MEMORY_STRICTEST: _INTEGRATION_STRICTEST,
    _INTEGRATION_STRICTEST: _INTEGRATION_STRICTEST,
}

_TO_CORE_CLASSIFICATION: Dict[str, str] = {
    DataClassification.PUBLIC: DataClassification.PUBLIC,
    DataClassification.INTERNAL: DataClassification.INTERNAL,
    DataClassification.CLIENT_CONFIDENTIAL: DataClassification.CLIENT_CONFIDENTIAL,
    DataClassification.PERSONNEL_SENSITIVE: DataClassification.PERSONNEL_SENSITIVE,
    DataClassification.FINANCIAL: DataClassification.FINANCIAL,
    DataClassification.REGULATED_HIGH_RISK: DataClassification.REGULATED_HIGH_RISK,
    _MEMORY_STRICTEST: DataClassification.REGULATED_HIGH_RISK,
    _INTEGRATION_STRICTEST: DataClassification.REGULATED_HIGH_RISK,
}


def _lookup(table: Dict[str, str], value: str, vocabulary: str, known: FrozenSet[str]) -> str:
    """Resolve ``value`` through ``table``, failing closed on anything unknown."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{vocabulary}: value must be a non-empty string, got {value!r}")
    key = value.strip()
    try:
        return table[key]
    except KeyError:
        raise ValueError(
            f"{vocabulary}: unknown value {value!r} — fail closed (known: {sorted(known)})"
        ) from None


def to_connector(mode: str) -> str:
    """Map any data mode into the connector vocabulary."""
    return _lookup(_TO_CONNECTOR, mode, "to_connector", DATA_MODES)


def to_engine(mode: str) -> str:
    """Map any data mode into the engine vocabulary (``live`` / ``sample``)."""
    return _lookup(_TO_ENGINE, mode, "to_engine", DATA_MODES)


def to_pack(mode: str) -> str:
    """Map any data mode into the capability-pack manifest vocabulary."""
    return _lookup(_TO_PACK, mode, "to_pack", DATA_MODES)


def to_pilot(mode: str) -> str:
    """
    Map any data mode into the pilot vocabulary.

    Live modes fail closed: the pilot never activates live customer data, so it
    must not receive a live mode relabelled as ``live_customer``. Callers that
    genuinely need the live spelling must say so explicitly rather than inherit it
    from a mapping.
    """
    if isinstance(mode, str) and mode.strip() in PILOT_REFUSED_DATA_MODES:
        raise ValueError(
            f"to_pilot: refusing live mode {mode!r} — the pilot never activates live "
            f"customer data, so no mapping may produce {PILOT_LIVE_CUSTOMER!r}"
        )
    return _lookup(_TO_PILOT, mode, "to_pilot", DATA_MODES)


def to_memory_classification(classification: str) -> str:
    """Map any classification into the four-level governed-memory vocabulary."""
    return _lookup(
        _TO_MEMORY_CLASSIFICATION,
        classification,
        "to_memory_classification",
        ALL_CLASSIFICATIONS,
    )


def to_integration_classification(classification: str) -> str:
    """Map any classification into the integration vocabulary (``regulated``)."""
    return _lookup(
        _TO_INTEGRATION_CLASSIFICATION,
        classification,
        "to_integration_classification",
        ALL_CLASSIFICATIONS,
    )


def to_core_classification(classification: str) -> str:
    """Map any classification into the canonical core vocabulary."""
    return _lookup(
        _TO_CORE_CLASSIFICATION,
        classification,
        "to_core_classification",
        ALL_CLASSIFICATIONS,
    )


def classifications_equal(left: str, right: str) -> bool:
    """
    Compare two classifications by meaning, tolerating vocabulary differences.

    ``regulated`` (integration) and ``regulated_high_risk`` (core) are different
    strings that both mean "highest sensitivity"; this returns ``True`` for them.
    A raw ``==`` would report a spurious mismatch across those two seams.
    """
    return to_core_classification(left) == to_core_classification(right)

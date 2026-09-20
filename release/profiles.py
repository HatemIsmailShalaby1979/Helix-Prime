"""
Helix Prime Codex C8 — release profiles and boundary gates.

**`release-profiles.yaml` is the source of truth.** Every constant below is
derived from it at import, so editing the file changes behaviour. It used to be
the other way round: the module held the values, `load_profiles()` read the YAML
only for a sanity count in `_gate_configuration_validation`, and editing a
profile's gate list in the file changed nothing — measured by editing it and
watching the gate not move (AGENTS.md §18.8). That hazard is gone: there is no
second copy to disagree with.

**Fail-closed at import.** A missing, unreadable or malformed file raises
`ReleaseProfilesUnavailableError` rather than falling back to inline defaults. A
release gate that cannot read its own profile definitions must refuse to run,
not proceed on an unverified copy of them — the same rule A2 applied to the role
catalog. This adds no packaging risk: `release/` is in neither the wheel nor the
sdist package lists, so this module is only ever imported from the source tree,
where the YAML sits beside it.

Profiles (never conflated with production readiness):
- alpha                : non-production, development/exploration
- internal_pilot       : non-production, internal team only
- controlled_pilot     : human-supervised, synthetic/consented data only
- production_candidate : evidence pack accepted, but NOT released to production
- production           : requires all 23 gates satisfied on signed external evidence
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, FrozenSet, List, Optional

import yaml

_RELEASE_YAML = pathlib.Path(__file__).resolve().parent / "release-profiles.yaml"

#: Every key the canonical file must carry.
_REQUIRED_KEYS = (
    "profiles",
    "gates",
    "app_gates",
    "required_gates",
    "allowed_final",
    "default_c8",
)


class ReleaseProfilesUnavailableError(RuntimeError):
    """`release-profiles.yaml` is missing, unreadable or malformed.

    Raised at import: the release gate's profile definitions are load-bearing for
    authorisation, so a layer that cannot read them must refuse to start rather
    than guess.
    """


def _reject(path: pathlib.Path, why: str) -> "ReleaseProfilesUnavailableError":
    return ReleaseProfilesUnavailableError(f"{path}: {why}")


def load_profiles(rel_path: Optional[str] = None) -> Dict[str, Any]:
    """Read and validate the canonical release profile file.

    Returns the file's own mapping — not a normalised copy — so a caller sees
    exactly what is on disk. Raises rather than returning defaults, because
    returning a second, unverified copy of the values is the failure mode this
    module exists to prevent. `rel_path` is for tests and tooling that want to
    read an edited copy; the constants above always come from the canonical file.
    """
    path = pathlib.Path(rel_path) if rel_path else _RELEASE_YAML
    if not path.exists():
        raise _reject(path, "missing")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise _reject(path, f"unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise _reject(path, "not a mapping")
    absent = [key for key in _REQUIRED_KEYS if key not in data]
    if absent:
        raise _reject(path, f"missing keys: {', '.join(absent)}")
    return data


def derive_profiles(data: Dict[str, Any], rel_path: Optional[str] = None) -> Dict[str, Any]:
    """Turn validated file contents into the constants this module exposes.

    Pure: it reads nothing, so a test can hand it an edited copy of the file and
    watch the derived values move. That is the property that makes the YAML the
    source of truth, and it is pinned in `tests/test_c8_release_gate.py`.

    Everything is checked before anything is returned, so a partially valid file
    cannot half-populate the module.
    """
    path = pathlib.Path(rel_path) if rel_path else _RELEASE_YAML
    order = list(data["profiles"])
    gate_names = list(data["gates"])
    app_gate_names = list(data["app_gates"])
    required = {profile: list(gates) for profile, gates in data["required_gates"].items()}

    if len(set(order)) != len(order):
        raise _reject(path, "duplicate profile name")
    if len(set(gate_names)) != len(gate_names):
        raise _reject(path, "duplicate gate name")
    if set(required) != set(order):
        raise _reject(path, "required_gates does not cover exactly the declared profiles")

    # production-only gates are the ones production requires that are not part of
    # the shared C8 set. Derived rather than declared twice, so the two lists
    # cannot drift; a gate added to `production` automatically becomes
    # production-only, which fails test_production_evidence until evidence for it
    # is defined. That is the intended coupling.
    production = required.get("production")
    if production is None:
        raise _reject(path, "no production profile")
    production_only = [gate for gate in production if gate not in set(gate_names)]

    # production must require every C8 gate. Without this a one-line edit to the
    # file would silently weaken the strongest profile in it.
    if not set(gate_names) <= set(production):
        missing = sorted(set(gate_names) - set(production))
        raise _reject(path, f"production omits C8 gates: {', '.join(missing)}")

    declared = set(gate_names) | set(app_gate_names) | set(production_only)
    for profile, gates in required.items():
        if not gates:
            raise _reject(path, f"{profile} requires no gates")
        unknown = [gate for gate in gates if gate not in declared]
        if unknown:
            raise _reject(path, f"{profile} names undeclared gates: {', '.join(unknown)}")

    allowed_final: FrozenSet[str] = frozenset(data["allowed_final"])
    default_c8 = str(data["default_c8"])
    if default_c8 not in allowed_final:
        raise _reject(path, f"default_c8 {default_c8!r} is not in allowed_final")

    return {
        "order": order,
        "gate_names": gate_names,
        "app_gate_names": app_gate_names,
        "production_only_gates": production_only,
        "required_gates": required,
        "allowed_final": allowed_final,
        "default_c8": default_c8,
    }


_CANONICAL = derive_profiles(load_profiles())

PROFILE_ORDER: List[str] = _CANONICAL["order"]

# Final classifications this release permits. It includes PRODUCTION as of
# 2026-09-20: the block on an unevidenced production label is the gates, not this
# set, and `classify_from_gate_results` returns PRODUCTION only when all nine
# production-only gates are green on signed external evidence AND release_approved.
ALLOWED_FINAL_CLASSIFICATIONS: FrozenSet[str] = _CANONICAL["allowed_final"]

# The default classification emitted when the C8 release gate is green.
DEFAULT_C8_CLASSIFICATION: str = _CANONICAL["default_c8"]

# Explicit gates required before a profile may be claimed.
# Each gate maps to a check function name in release.gate.
GATE_NAMES: List[str] = _CANONICAL["gate_names"]

# App product gates — owned by the Helix Codex App build, distinct from the
# C8 core gate set. The app_pilot profile combines a subset of the core gates
# with these; they deliberately never enter GATE_NAMES, whose length is a
# pinned C8 invariant.
APP_GATE_NAMES: List[str] = _CANONICAL["app_gate_names"]


def _all_c8_gates() -> List[str]:
    return list(GATE_NAMES)


# Production-only gates: external evidence / ownership commitments that C8 (and
# any local automated run) cannot satisfy alone — each needs a signature from a
# key held outside the repository, or a named human. They keep the production
# profile NOT_READY until genuine external approvals and evidence exist. Since
# 2026-09-20 these gates, not the `allowed_final` policy set, are what block an
# unevidenced PRODUCTION label.
PRODUCTION_ONLY_GATES: List[str] = _CANONICAL["production_only_gates"]


# Gates required per profile. alpha/internal_pilot are permissive;
# controlled_pilot and production_candidate require the full C8 gate set.
# production requires ALL of those PLUS the nine production-only criteria, so an
# unqualified PRODUCTION label is still unreachable: the extra gates are what
# hold, not the policy set.
PROFILE_REQUIRED_GATES: Dict[str, List[str]] = _CANONICAL["required_gates"]


def is_known_profile(profile: str) -> bool:
    return profile in PROFILE_ORDER


def gates_required_for(profile: str) -> List[str]:
    """Return the gate names required to claim a given profile (fail-closed)."""
    if not is_known_profile(profile):
        return list(_all_c8_gates())
    return list(PROFILE_REQUIRED_GATES[profile])


def classify_from_gate_results(
    profile: str,
    green_gates: List[str],
    release_approved: bool = False,
) -> str:
    """
    Fail-closed, deterministic classification based on which gates are green.

    - Unknown profile -> NOT_READY.
    - If any required gate for the requested profile is red -> NOT_READY.
    - production is emitted only when every C8 gate AND all nine production-only
      gates are green and `release_approved` is true. Those nine each need a
      signature from a key held outside this repository, so an unevidenced run
      falls to NOT_READY — this function does not manufacture the label.
    The permitted set is `allowed_final` in release-profiles.yaml; a
    classification outside it is still reported, but makes the gate exit non-zero.
    """
    if not is_known_profile(profile):
        return "NOT_READY"
    required = PROFILE_REQUIRED_GATES[profile]
    missing = [g for g in required if g not in green_gates]

    if profile == "production":
        # Production adds external-only gates — none of which C8 or any local
        # automated run can satisfy. A bare PRODUCTION label is therefore
        # unreachable here: every production-only gate must be independently
        # green before it could be considered.
        base_missing = [g for g in _all_c8_gates() if g not in green_gates]
        extra_missing = [
            g for g in PRODUCTION_ONLY_GATES if g not in _all_c8_gates() and g not in green_gates
        ]
        required_extra = list(PRODUCTION_ONLY_GATES)
        all_prod_gates = all(g in green_gates for g in required_extra)
        if base_missing or extra_missing or not all_prod_gates or not release_approved:
            return "NOT_READY"
        return "PRODUCTION"

    if not missing:
        if profile == "controlled_pilot":
            return "CONTROLLED_PILOT_READY"
        if profile == "production_candidate":
            return "PRODUCTION_CANDIDATE"
        if profile == "app_pilot":
            return "CONTROLLED_PILOT_READY"
        return profile

    # Red gates -> fail closed, never a candidate.
    return "NOT_READY"

"""
Helix Prime Codex C8 — release profiles and boundary gates.

Defines the five release profiles and the explicit gates a profile must satisfy.
Canonical source of truth for release classification (this module + YAML mirror).

Profiles (never conflated with production readiness):
- alpha                : non-production, development/exploration
- internal_pilot       : non-production, internal team only
- controlled_pilot     : human-supervised, synthetic/consented data only
- production_candidate : evidence pack accepted, but NOT released to production
- production           : requires every production gate explicitly satisfied (NOT claimed here)
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

import yaml

PROFILE_ORDER = [
    "alpha",
    "internal_pilot",
    "controlled_pilot",
    "production_candidate",
    "production",
    "app_pilot",
]

# Final classification allowed by THIS sprint (never "production").
ALLOWED_FINAL_CLASSIFICATIONS = {"CONTROLLED_PILOT_READY", "PRODUCTION_CANDIDATE"}

# The default classification emitted when the C8 release gate is green.
DEFAULT_C8_CLASSIFICATION = "PRODUCTION_CANDIDATE"

# Explicit gates required before a profile may be claimed.
# Each gate maps to a check function name in release.gate.
GATE_NAMES = [
    "repository_state",  # clean-ish repo, reproducible commands present
    "reproducible_install",  # one setup path documented + dependency lock
    "configuration_validation",  # config parses + validates before startup
    "dependency_locking",  # dependency versions pinned/locked
    "startup_readiness",  # health/readiness command passes
    "backup_restore",  # backup + restore proven from synthetic data
    "rollback",  # rollback to previous manifest proven
    "data_isolation",  # tenant/client isolation verified
    "audit_integrity",  # audit chain verifies after backup/restore
    "security_checks",  # no-secrets scan + policy checks
    "failure_recovery",  # failure injection + recovery
    "performance_limits",  # bounded load/soak within explicit limits
    "operator_readiness",  # runbook + incident guide present
    "release_approval",  # explicit human go/no-go recorded
]

# App product gates — owned by the Helix Codex App build, distinct from the
# C8 core gate set. The app_pilot profile combines a subset of the core gates
# with these; they deliberately never enter GATE_NAMES, whose length is a
# pinned C8 invariant.
APP_GATE_NAMES = [
    "app_auth_boundary",  # every /app route but healthz/static runs the guard
    "app_session_fail_closed",  # revoked and expired sessions fail closed
    "app_tenant_isolation",  # one tenant never reads another tenant's rows
    "app_memory_store_isolation",  # one account's memory never leaks to another
    "app_migration_drift",  # db.py and the alembic head agree
    "app_pwa_assets",  # installable shell: manifest, icons, sw, offline page
]

_RELEASE_YAML = pathlib.Path(__file__).resolve().parent / "release-profiles.yaml"


# Gates required per profile. alpha/internal_pilot are permissive;
# controlled_pilot and production_candidate require the full C8 gate set.
# production requires ALL gates PLUS production-only criteria that C8 does
# not satisfy (so an unqualified PRODUCTION label can never be emitted here).
def _all_c8_gates() -> List[str]:
    return list(GATE_NAMES)


# Production-only gate: external evidence / ownership commitments that C8 (and
# any local automated run) cannot satisfy. These keep the production profile
# permanently NOT_READY until genuine external approvals and evidence exist.
PRODUCTION_ONLY_GATES = [
    "signed_production_evidence",  # external signed production evidence
    "certified_data_isolation",  # certified tenant/data isolation
    "external_observer_audit",  # independent external observer audit
    "production_deployment_architecture",  # reviewed prod deployment architecture
    "disaster_recovery_evidence",  # DR / restore evidence from a real environment
    "operational_ownership",  # assigned operational owner
    "incident_oncall_ownership",  # assigned incident/on-call owner
    "security_review",  # security review signed off
    "legal_privacy_review",  # legal/privacy review where applicable
]


PROFILE_REQUIRED_GATES: Dict[str, List[str]] = {
    "alpha": ["repository_state"],
    "internal_pilot": [
        "repository_state",
        "reproducible_install",
        "configuration_validation",
        "startup_readiness",
    ],
    "controlled_pilot": _all_c8_gates(),
    "production_candidate": _all_c8_gates(),
    "production": _all_c8_gates() + PRODUCTION_ONLY_GATES,
    # The app product surface — the Helix Codex App's own release gates.
    # A green app_pilot run means the app is safe to pilot on its side of the
    # seam, riding on the core's configuration/startup/data/audit guarantees.
    "app_pilot": [
        "repository_state",
        "configuration_validation",
        "startup_readiness",
        "data_isolation",
        "audit_integrity",
        "app_auth_boundary",
        "app_session_fail_closed",
        "app_tenant_isolation",
        "app_memory_store_isolation",
        "app_migration_drift",
        "app_pwa_assets",
    ],
}


def load_profiles(rel_path: Optional[str] = None) -> Dict[str, Any]:
    """Load release-profiles.yaml if present; else fall back to module defaults."""
    path = pathlib.Path(rel_path) if rel_path else _RELEASE_YAML
    if not path.exists():
        return {
            "profiles": PROFILE_ORDER,
            "gates": GATE_NAMES,
            "app_gates": APP_GATE_NAMES,
            "required_gates": PROFILE_REQUIRED_GATES,
            "allowed_final": sorted(ALLOWED_FINAL_CLASSIFICATIONS),
            "default_c8": DEFAULT_C8_CLASSIFICATION,
        }
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


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
    - production is NEVER emitted: it additionally requires production-only
      gates that C8 does not satisfy; at best it falls back to a candidate
      (or NOT_READY if base gates are red).
    Permitted C8 outcomes are CONTROLLED_PILOT_READY and PRODUCTION_CANDIDATE;
    anything else is NOT_READY (gate exit code non-zero).
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

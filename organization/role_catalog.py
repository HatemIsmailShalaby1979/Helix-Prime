"""
Role catalog loader/validator for Helix Prime Codex C1.

One source of truth: organization/role-catalog.yaml
Must fail clearly for malformed YAML, duplicate IDs, missing required fields, or invalid references.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except ImportError as _e:
    yaml = None  # type: ignore

REQUIRED_ROLE_FIELDS = [
    "id",
    "display_name",
    "mission",
    "owned_capabilities",
    "allowed_tools",
    "readable_data_domains",
    "approval_limits",
    "escalation_owner",
    "kpis",
    "allowed_peer_calls",
    "segregation_of_duties",
]

REQUIRED_APPROVAL_LIMIT_FIELDS = [
    "tier",
    "can_approve",
    "max_financial_amount",
    "requires_escalation_for",
]

REQUIRED_SOD_FIELDS = [
    "cannot_approve_own_actions",
    "must_be_reviewed_by",
    "can_review",
    "restrictions",
]

# Allowed tiers per C1 design; extend cautiously (C2/C3 will refine)
ALLOWED_TIERS = {
    "executive",
    "personnel",
    "standard",
    "financial",
    "compliance",
    "platform",
    "operational",
}

# Valid status for implementation_status
ALLOWED_IMPLEMENTATION_STATUS = {"functional_agent", "catalog_only"}


def _require_non_empty_str(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be non-empty string, got {value!r}")
    return value.strip()


def _require_list_of_str(value: Any, field_path: str, allow_empty: bool = False) -> List[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_path}: must be list, got {type(value).__name__}")
    if not allow_empty and len(value) == 0:
        raise ValueError(f"{field_path}: must be non-empty list")
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_path}[{i}]: must be non-empty string, got {item!r}")
    return [s.strip() for s in value]


def _validate_iso_timestamp(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    # minimal check: try parse via datetime.fromisoformat (allow trailing Z)
    import datetime

    try:
        cand = s.replace("Z", "+00:00") if s.endswith("Z") else s
        datetime.datetime.fromisoformat(cand)
    except Exception as e:
        raise ValueError(f"{field_path}: must be ISO8601 timestamp, got {s!r}: {e}") from e
    return s


def load_role_catalog(path: str | pathlib.Path = "organization/role-catalog.yaml") -> Dict[str, Any]:
    """
    Load and validate the canonical role catalog.
    Returns dict with keys: schema_version, kpi_vocabulary, roles (by id), roles_list
    Raises ValueError with clear message on failure.
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise ValueError(f"role catalog not found at {p} (expected organization/role-catalog.yaml)")

    if yaml is None:
        raise ValueError("PyYAML not installed: cannot load organization/role-catalog.yaml (pip install pyyaml)")

    try:
        raw = p.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"malformed YAML in {p}: {e}") from e
    except Exception as e:
        raise ValueError(f"failed to read {p}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"{p}: top-level must be mapping, got {type(data).__name__}")

    return validate_role_catalog(data, source_path=str(p))


def validate_role_catalog(data: Dict[str, Any], source_path: str = "role-catalog.yaml") -> Dict[str, Any]:
    """
    Validate already-parsed catalog dict.
    Returns enriched dict with roles_by_id.
    """
    # top-level checks
    for field in ["schema_version", "roles"]:
        if field not in data:
            raise ValueError(f"{source_path}: missing required top-level field {field!r}")

    schema_version = _require_non_empty_str(data["schema_version"], f"{source_path}.schema_version")

    kpi_vocab = data.get("kpi_vocabulary")
    if kpi_vocab is not None:
        if not isinstance(kpi_vocab, list):
            raise ValueError(f"{source_path}.kpi_vocabulary: must be list, got {type(kpi_vocab).__name__}")
        kpi_vocab = _require_list_of_str(kpi_vocab, f"{source_path}.kpi_vocabulary", allow_empty=False)
    else:
        kpi_vocab = []

    roles = data.get("roles")
    if not isinstance(roles, list):
        raise ValueError(f"{source_path}.roles: must be list, got {type(roles).__name__}")
    if len(roles) == 0:
        raise ValueError(f"{source_path}.roles: must be non-empty list")

    # collect ids, check duplicates
    seen: Dict[str, int] = {}
    roles_by_id: Dict[str, Dict[str, Any]] = {}
    for idx, role in enumerate(roles):
        if not isinstance(role, dict):
            raise ValueError(f"{source_path}.roles[{idx}]: must be mapping, got {type(role).__name__}")
        role_path = f"{source_path}.roles[{idx}]"
        # required fields
        for field in REQUIRED_ROLE_FIELDS:
            if field not in role:
                raise ValueError(f"{role_path}: missing required field {field!r}")
        rid = _require_non_empty_str(role["id"], f"{role_path}.id")
        if rid in seen:
            raise ValueError(f"{source_path}: duplicate role id {rid!r} at {role_path} and roles[{seen[rid]}]")
        seen[rid] = idx

        # display_name, mission non-empty
        _require_non_empty_str(role["display_name"], f"{role_path}.display_name")
        _require_non_empty_str(role["mission"], f"{role_path}.mission")

        # implementation_status if present
        if "implementation_status" in role:
            status = _require_non_empty_str(role["implementation_status"], f"{role_path}.implementation_status")
            if status not in ALLOWED_IMPLEMENTATION_STATUS:
                raise ValueError(
                    f"{role_path}.implementation_status: must be one of {sorted(ALLOWED_IMPLEMENTATION_STATUS)}, got {status!r}"
                )

        # lists
        _require_list_of_str(role["owned_capabilities"], f"{role_path}.owned_capabilities", allow_empty=False)
        _require_list_of_str(role["allowed_tools"], f"{role_path}.allowed_tools", allow_empty=False)
        _require_list_of_str(role["readable_data_domains"], f"{role_path}.readable_data_domains", allow_empty=False)
        _require_list_of_str(role["kpis"], f"{role_path}.kpis", allow_empty=False)
        _require_list_of_str(role["allowed_peer_calls"], f"{role_path}.allowed_peer_calls", allow_empty=True)

        # kpis must be subset of vocabulary if vocab present
        if kpi_vocab:
            for kpi in role["kpis"]:
                if kpi not in kpi_vocab:
                    raise ValueError(
                        f"{role_path}.kpis: {kpi!r} not in kpi_vocabulary {kpi_vocab}"
                    )

        # approval_limits
        al = role["approval_limits"]
        if not isinstance(al, dict):
            raise ValueError(f"{role_path}.approval_limits: must be mapping, got {type(al).__name__}")
        for f in REQUIRED_APPROVAL_LIMIT_FIELDS:
            if f not in al:
                raise ValueError(f"{role_path}.approval_limits: missing required field {f!r}")
        tier = _require_non_empty_str(al["tier"], f"{role_path}.approval_limits.tier")
        if tier not in ALLOWED_TIERS:
            raise ValueError(
                f"{role_path}.approval_limits.tier: must be one of {sorted(ALLOWED_TIERS)}, got {tier!r}"
            )
        _require_list_of_str(al["can_approve"], f"{role_path}.approval_limits.can_approve", allow_empty=True)
        # max_financial_amount: int or null
        mfa = al["max_financial_amount"]
        if mfa is not None and not isinstance(mfa, int):
            raise ValueError(
                f"{role_path}.approval_limits.max_financial_amount: must be int or null, got {type(mfa).__name__}"
            )
        if isinstance(mfa, int) and mfa < 0:
            raise ValueError(f"{role_path}.approval_limits.max_financial_amount: must be >=0, got {mfa}")
        _require_list_of_str(
            al["requires_escalation_for"],
            f"{role_path}.approval_limits.requires_escalation_for",
            allow_empty=True,
        )

        # escalation_owner: non-empty string, will validate reference later
        _require_non_empty_str(role["escalation_owner"], f"{role_path}.escalation_owner")

        # segregation_of_duties
        sod = role["segregation_of_duties"]
        if not isinstance(sod, dict):
            raise ValueError(f"{role_path}.segregation_of_duties: must be mapping, got {type(sod).__name__}")
        for f in REQUIRED_SOD_FIELDS:
            if f not in sod:
                raise ValueError(f"{role_path}.segregation_of_duties: missing required field {f!r}")
        if not isinstance(sod["cannot_approve_own_actions"], bool):
            raise ValueError(
                f"{role_path}.segregation_of_duties.cannot_approve_own_actions: must be bool, got {type(sod['cannot_approve_own_actions']).__name__}"
            )
        _require_list_of_str(
            sod["must_be_reviewed_by"], f"{role_path}.segregation_of_duties.must_be_reviewed_by", allow_empty=True
        )
        _require_list_of_str(
            sod["can_review"], f"{role_path}.segregation_of_duties.can_review", allow_empty=True
        )
        _require_list_of_str(
            sod["restrictions"], f"{role_path}.segregation_of_duties.restrictions", allow_empty=True
        )

        roles_by_id[rid] = role

    # second pass: validate references
    all_ids = set(roles_by_id.keys())
    # required 9 includes SAMI + 8 GMs
    required_ids = {
        "sami",
        "hr_personnel_gm",
        "marketing_gm",
        "sales_gm",
        "compliance_quality_gm",
        "ict_gm",
        "fraud_gm",
        "ld_gm",
        "ops_gm",
    }
    missing = required_ids - all_ids
    if missing:
        raise ValueError(f"{source_path}: missing required role ids {sorted(missing)} (need SAMI + 8 GMs)")

    for rid, role in roles_by_id.items():
        role_path = f"{source_path}.roles[{rid}]"
        esc = role["escalation_owner"]
        if esc not in all_ids:
            raise ValueError(f"{role_path}.escalation_owner: {esc!r} not in role ids {sorted(all_ids)}")
        for peer in role["allowed_peer_calls"]:
            if peer not in all_ids:
                raise ValueError(f"{role_path}.allowed_peer_calls: {peer!r} not in role ids {sorted(all_ids)}")
            if peer == rid:
                raise ValueError(f"{role_path}.allowed_peer_calls: cannot self-reference {rid!r}")
        sod = role["segregation_of_duties"]
        for reviewer in sod["must_be_reviewed_by"]:
            if reviewer not in all_ids:
                raise ValueError(f"{role_path}.segregation_of_duties.must_be_reviewed_by: {reviewer!r} not in role ids")
        for reviewer in sod["can_review"]:
            if reviewer not in all_ids:
                raise ValueError(f"{role_path}.segregation_of_duties.can_review: {reviewer!r} not in role ids")

    # SOD specific: compliance must be able to review ops, sales, hr, fraud
    compliance = roles_by_id.get("compliance_quality_gm")
    if compliance:
        can = set(compliance["segregation_of_duties"]["can_review"])
        required_can = {"ops_gm", "sales_gm", "hr_personnel_gm", "fraud_gm"}
        missing_can = required_can - can
        if missing_can:
            raise ValueError(
                f"{source_path}.roles[compliance_quality_gm].segregation_of_duties.can_review: missing required reviewers {sorted(missing_can)} per C1 SOD (Compliance must review OPS/Sales/HR/Fraud)"
            )

    return {
        "schema_version": schema_version,
        "kpi_vocabulary": kpi_vocab,
        "roles": roles,
        "roles_by_id": roles_by_id,
        "source_path": source_path,
    }


def get_role(catalog: Dict[str, Any], role_id: str) -> Dict[str, Any]:
    roles_by_id = catalog.get("roles_by_id") or {}
    if role_id not in roles_by_id:
        raise ValueError(f"role {role_id!r} not found in catalog {list(roles_by_id.keys())}")
    return roles_by_id[role_id]


def is_peer_call_allowed(catalog: Dict[str, Any], from_role: str, to_role: str) -> bool:
    """Check if from_role is allowed to call to_role per catalog."""
    role = get_role(catalog, from_role)
    return to_role in role.get("allowed_peer_calls", [])


def requires_compliance_review(catalog: Dict[str, Any], role_id: str) -> bool:
    """True if role's actions must be reviewed by compliance."""
    role = get_role(catalog, role_id)
    return "compliance_quality_gm" in role.get("segregation_of_duties", {}).get("must_be_reviewed_by", [])


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "organization/role-catalog.yaml"
    catalog = load_role_catalog(path)
    print(f"Loaded {len(catalog['roles'])} roles from {path} schema={catalog['schema_version']}")
    for rid in sorted(catalog["roles_by_id"].keys()):
        r = catalog["roles_by_id"][rid]
        print(f"- {rid}: {r['display_name']} ({r['implementation_status']})")

#!/usr/bin/env python3
"""
Governance catalog drift gate (A0.6).

The organization model has two sources of truth:

  1. control_plane/governance.py::ORGANIZATION_CATALOG — the *runtime* authority
     that actually gates financial approvals.
  2. organization/role-catalog.yaml — the authored org chart. Never edited.

``control_plane.governance.detect_catalog_drift()`` reports every divergence
between the two. This script turns that report into a CI verdict, because a
detector that nothing runs is not a control.

Accepted divergence
-------------------
The runtime financial limits are deliberately more conservative than the YAML
org-chart authority (the YAML records what a role *may* approve; the runtime
enforces less). That gap is intentional, so it is pinned in
``control_plane.governance.ACCEPTED_FINANCIAL_DRIFT_ROLES`` rather than
suppressed. Everything else fails:

  * any structural field (capabilities, tools, peer calls, SOD) drifting
  * any role drifting outside the accepted set
  * any accepted role that no longer drifts (the pin is stale — update it)
  * any runtime limit that exceeds the YAML authority (enforcement loosened)
  * the YAML failing to load at all

Exit 0 = drift is exactly the accepted set. Exit 1 = anything else (including a
check that could not run — a control that cannot run fails closed).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: The only drift field that is ever accepted. Everything else is structural.
ACCEPTED_FIELD = "financial_approval_limit_usd"


def check_drift() -> tuple[list[str], dict[str, object]]:
    from control_plane.governance import (
        ACCEPTED_FINANCIAL_DRIFT_ROLES,
        detect_catalog_drift,
    )

    drift = detect_catalog_drift()

    errors: list[str] = []
    financial: dict[str, tuple[object, object]] = {}
    structural: list[str] = []

    for entry in drift:
        role_id = entry.get("role_id")
        field = entry.get("field")

        if role_id == "*":
            errors.append(
                f"role-catalog.yaml could not be read, so no comparison was made: "
                f"{entry.get('detail')}"
            )
            continue

        if field != ACCEPTED_FIELD:
            structural.append(f"{role_id}.{field}")
            errors.append(
                f"{role_id}: unexpected {field!r} drift — only "
                f"{ACCEPTED_FIELD!r} divergence is accepted "
                f"(runtime={entry.get('runtime')!r} yaml={entry.get('yaml')!r})"
            )
            continue

        runtime, yaml_value = entry.get("runtime"), entry.get("yaml")
        financial[str(role_id)] = (runtime, yaml_value)

        if runtime is None:
            errors.append(
                f"{role_id}: runtime financial approval limit is unset; the runtime "
                f"catalog must always carry an enforcement ceiling"
            )
            continue

        if yaml_value is None:
            # The YAML records no max_financial_amount, i.e. unlimited authority
            # (as for ``sami``). A runtime cap is a narrowing, which is the whole
            # point of the accepted divergence — nothing to check.
            continue

        try:
            exceeds = float(runtime) > float(yaml_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            errors.append(
                f"{role_id}: financial approval limit is not numeric "
                f"(runtime={runtime!r} yaml={yaml_value!r})"
            )
            continue

        if exceeds:
            errors.append(
                f"{role_id}: runtime financial approval limit {runtime!r} exceeds the "
                f"YAML authority {yaml_value!r}; enforcement must never be looser than "
                f"the org chart"
            )

    drifting_roles = set(financial)
    accepted = set(ACCEPTED_FINANCIAL_DRIFT_ROLES)

    for role_id in sorted(drifting_roles - accepted):
        errors.append(
            f"{role_id}: newly diverging on {ACCEPTED_FIELD} and not in "
            f"ACCEPTED_FINANCIAL_DRIFT_ROLES — confirm the change is intentional, then "
            f"add the role to the pin"
        )

    for role_id in sorted(accepted - drifting_roles):
        errors.append(
            f"{role_id}: listed in ACCEPTED_FINANCIAL_DRIFT_ROLES but no longer drifts "
            f"— the runtime limit now agrees with the YAML, so remove the stale pin"
        )

    report = {
        "accepted_roles": sorted(accepted),
        "drifting_roles": sorted(drifting_roles),
        "structural_drift": sorted(structural),
        "financial_limits": {
            role: {"runtime": runtime, "yaml": yaml_value}
            for role, (runtime, yaml_value) in sorted(financial.items())
        },
        "errors": errors,
    }
    return errors, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    try:
        errors, report = check_drift()
    except Exception as exc:  # noqa: BLE001 - a control that cannot run fails closed
        if args.json:
            print(json.dumps({"errors": [f"drift check could not run: {exc}"]}, indent=2))
        else:
            print(f"ERROR drift check could not run: {exc}")
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Governance catalog drift check: "
            f"{len(report['drifting_roles'])} role(s) diverging, "
            f"{len(report['structural_drift'])} structural divergence(s)"
        )
        if errors:
            print("Governance drift is not the accepted set:")
            for error in errors:
                print(f"  ERROR {error}")
        else:
            print(
                "No unexpected drift: the only divergence is the accepted financial "
                "limit set, all within YAML authority."
            )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

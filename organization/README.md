# Organization — Helix Prime Role Catalog (C1)

Canonical source: `organization/role-catalog.yaml` (validated by `organization/role_catalog.py`).

## Contents

- `role-catalog.yaml` — 9 roles (SAMI + 8 GMs). Each role: id, display_name, mission, owned_capabilities, allowed_tools, readable_data_domains, approval_limits, escalation_owner, kpis, allowed_peer_calls, segregation_of_duties.
- `role_catalog.py` — loader/validator. Fails deterministically for malformed YAML, duplicate IDs, missing fields, invalid references (escalation_owner, peer calls, SOD), or KPI not in `kpi_vocabulary`.
- Existing agents mapped without rename: `PHILI→hr_personnel_gm`, `WILI→ld_gm`, `SUBY→ops_gm`, `SAMI→sami`. New GMs (Marketing, Sales, Compliance & Quality, ICT, Fraud) are `catalog_only` until C6 — no fake functional agents.

## Usage

```python
from organization.role_catalog import load_role_catalog

catalog = load_role_catalog("organization/role-catalog.yaml")
sami = catalog["roles_by_id"]["sami"]
assert "compliance_quality_gm" in catalog["roles_by_id"]["ops_gm"]["segregation_of_duties"]["must_be_reviewed_by"]
```

CLI check:

```bash
python -m organization.role_catalog organization/role-catalog.yaml
python3 -m pytest tests/test_c1_contracts.py -k catalog
```

## SOD invariant (C1)

Compliance & Quality GM `can_review` must include `ops_gm`, `sales_gm`, `hr_personnel_gm`, `fraud_gm`. OPS/Sales/HR/Fraud/Marketing/L&D/ICT `must_be_reviewed_by` includes `compliance_quality_gm`.

## What C1 does not do

- No capability-based discovery (C1a)
- No workflow runtime (C2)
- No engine execution for catalog-only GMs

# 3. Workflow Demonstration

The demonstration proves the **same governed core** runs two different businesses in one
memory without cross-tenant leakage and with an intact audit chain.

## Script
`demo/synthetic_demo.py` — runs from a **clean setup** (fresh in-memory `GovernedMemory`,
no network, no live connectors, no cloud). It:
1. Runs the call-centre pilot (`PilotRuntime`) for tenant `cc-1`/`cc-c1` with validated consent.
2. Runs the restaurant capability pack (`RestaurantCapabilityPack`) for tenant `r1`/`rc1`
   with synthetic fixtures and validated consent.
3. Asserts invariants: audit chain intact, zero `live_customer` records, `live_activated=False`,
   production readiness `NOT_ESTABLISHED`, tenant isolation across both packs, and that
   connector `request_write` returns `executed=False`.

## Run it
```bash
python3 demo/synthetic_demo.py
```
Exit code 0 = success.

## Actual output (clean setup, 2026-08-29)
```
[call-centre pilot] tenants: ['cc-1'] diagnoses: 1
[call-centre pilot] approval summary: {'total': 3, 'approved': 0, 'denied': 0, 'draft': 3, 'rolled_back': 0}
[call-centre pilot] live_customer_records: 0 audit_chain_intact: True
[call-centre pilot] final_status: {'pilot_package_ready': True, 'real_design_partner_approval_pending': True, 'production_readiness': 'NOT_ESTABLISHED'}

[restaurant pack] tenants: ['r1'] diagnoses: 1
[restaurant pack] metrics: {'escalation_accuracy': 0.0, 'recommendation_acceptance_rate': 0.0, 'customer_health_visibility': 0.83}
[restaurant pack] approval summary: {'total': 13, 'approved': 0, 'denied': 0, 'draft': 13, 'rolled_back': 0}
[restaurant pack] live_customer_records: 0 audit_chain_intact: True
[restaurant pack] final_status: {'capability_pack_ready': True, 'real_design_partner_approval_pending': True, 'production_readiness': 'NOT_ESTABLISHED', 'note': 'Demonstrated for one restaurant workflow only; not validated for every business.'}

[shared memory] total records: 41 audit_chain_intact: True
SYNTHETIC DEMO OK — read-only, synthetic, no external writes, audit intact.
```

## Restaurant workflows demonstrated
`staffing_risk`, `shift_coverage`, `inventory_risk`, `complaint_escalation`,
`supplier_delay`, `daily_summary` — each a pure function over synthetic connector data
returning risk findings + recommended actions with evidence refs. The call-centre wedge
(`customer_success.wedge`) diagnoses account health and produces approval-previews.

## What this shows
- Business context is understood via connector data + per-domain ontology.
- Workflows are coordinated and recorded as governed, approval-gated recommendations.
- Decisions and outcomes are remembered (append-only, hash-chained).
- No action is taken; everything is a draft pending human approval.

# 15. Verified Test Results

All numbers below are from a clean run on 2026-08-29. Reproduce with the commands shown.

## Command
```bash
python3 -m pytest tests/ -q -p no:cacheprovider
```

## Result
**445 passed** (no failures, no errors).

## Per-file counts (26 test modules)
| Tests | File | Area |
|------:|------|------|
| 42 | test_c1_contracts.py | C1 agent contracts |
| 14 | test_c1a_capability_discovery.py | C1 capability discovery |
| 30 | test_c2_control_plane.py | C2 workflow state machine |
| 7 | test_c2_preflight_regression.py | C2 preflight |
| 7 | test_c3_c2_integration_preflight.py | C3 integration preflight |
| 22 | test_c3_security.py | C3 security |
| 32 | test_c4_engines.py | C4 engines |
| 27 | test_c5_vertical_slice.py | C5 vertical slice |
| 25 | test_c6_gm_expansion.py | C6 GM expansion |
| 44 | test_c7_sibling_integration.py | C7 sibling integration |
| 22 | test_c8_release_gate.py | C8 release gates |
| 15 | test_call_centre_proving_workflow.py | call-centre proving |
| 14 | test_capabilities_restaurant.py | **restaurant capability pack (Prompt 11)** |
| 5 | test_capability_registry_drift.py | capability registry drift |
| 9 | test_cloud_readiness.py | cloud-ready local-first (Prompt 9) |
| 6 | test_cockpit_client_profiles.py | cockpit client profiles |
| 15 | test_command_center_integration.py | command center (Prompt 6) |
| 3 | test_connectors.py | connectors |
| 17 | test_connectors_layer.py | connector layer |
| 2 | test_customer_success.py | customer success |
| 16 | test_customer_success_wedge.py | customer-success wedge (Prompt 5) |
| 3 | test_governance.py | governance |
| 15 | test_governed_memory.py | governed memory (Prompt 7) |
| 10 | test_metacognition.py | metacognition (Prompt 8) |
| 17 | test_pilot.py | controlled pilot (Prompt 10) |
| 26 | test_pilot_readiness.py | pilot readiness |
| **445** | **TOTAL** | |

## Governance
```bash
python3 -m GOVERNANCE.governance_check check
```
Result: **`governance=PASS`**.

## Security
```bash
python3 -c "from release.security_gate import run_security_gate; r=run_security_gate(); print('all_ok =', r['all_ok'])"
```
Result: **`all_ok = True`** (0 secret findings; deny-by-default; redaction; audit integrity;
typed malformed-output handling).

## Release gates
```bash
python3 -c "from release.gate import run_gate; print(run_gate('controlled_pilot')['classification'], run_gate('production')['classification'])"
```
Result: **`CONTROLLED_PILOT_READY`** and **`NOT_READY`**.

## Synthetic demo (clean setup)
```bash
python3 demo/synthetic_demo.py   # exit 0
```
Result: call-centre + restaurant tenants in one governed memory; `audit_chain_intact=True`;
`live_customer_records=0`; connector writes disabled; production readiness `NOT_ESTABLISHED`.

## Interpretation
- 445 passing tests cover identity, tenant isolation, governance, connectors, workflows, approvals,
  evidence, memory, metrics, metacognition, cloud boundary, pilot, and the restaurant capability pack.
- The release is **controlled-pilot ready**; **production readiness is not established** (red
  production gates by design).

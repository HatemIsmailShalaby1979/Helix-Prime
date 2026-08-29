# Helix Codex — Founder/CTO Portfolio & Release Evidence Package

**Positioning (design intent, realized by demonstrated mechanisms):**

> An accountable AI operating organization that understands business context,
> coordinates governed workflows, remembers decisions and outcomes, and improves
> through evidence without silently taking control.

This package is a **portfolio/review artifact**. Every claim below is tied to code
that exists in this repository and tests that pass. The narrative claims only what has
been demonstrated; unfinished items are listed separately in
[`11_known_limitations.md`](11_known_limitations.md) and
[`14_technical_decision_log.md`](14_technical_decision_log.md).

## What is demonstrated (completed)
- A governed core: identity, tenant isolation, governance, read-only connectors,
  workflow state machine, manual approvals with separation of duties, evidence/
  provenance, append-only memory, metrics, and an evidence-gated metacognitive
  improvement engine that **never auto-deploys**.
- A controlled, read-only-first design-partner pilot (call-centre wedge) with consent,
  minimum data, tenant isolation, retention, rollback, and an evidence pack.
- A first business capability pack (small restaurant) that **reuses the same core** and
  starts read-only with synthetic data.
- A synthetic demonstration running both a call-centre tenant and a restaurant tenant in
  **one governed memory** with tenant isolation and an intact audit chain.

## Verification summary (reproducible)
- **Tests:** 445 passed (`pytest tests/ -q`). See [`15_verified_test_results.md`](15_verified_test_results.md).
- **Governance:** `python3 -m GOVERNANCE.governance_check check` → `governance=PASS`.
- **Security:** `release.security_gate.run_security_gate()` → `all_ok=True` (0 secret findings, deny-by-default, redaction, audit integrity).
- **Synthetic demo (clean setup):** `python3 demo/synthetic_demo.py` → exits 0, audit chain intact, 0 live-customer records, no external writes.
- **Release gates:** `controlled_pilot` → `CONTROLLED_PILOT_READY`; `production` → `NOT_READY`.

## Documents in this package
1. [Architecture overview](01_architecture_overview.md)
2. [Governance model](02_governance_model.md)
3. [Workflow demonstration](03_workflow_demonstration.md)
4. [Security model](04_security_model.md)
5. [Evidence model](05_evidence_model.md)
6. [Memory model](06_memory_model.md)
7. [Metacognitive improvement model](07_metacognitive_improvement_model.md)
8. [Local/cloud deployment strategy](08_local_cloud_deployment.md)
9. [Cost assumptions](09_cost_assumptions.md)
10. [Pilot plan](10_pilot_plan.md)
11. [Known limitations](11_known_limitations.md)
12. [Roadmap](12_roadmap.md)
13. [Five-minute demo script](13_five_minute_demo_script.md)
14. [Technical decision log](14_technical_decision_log.md)
15. [Verified test results](15_verified_test_results.md)

## Status
- **Pilot package ready:** TRUE
- **First real capability pack ready:** TRUE
- **Real design-partner approval pending:** TRUE
- **Production readiness:** **NOT_ESTABLISHED** (not claimed; external production gates are red by design)

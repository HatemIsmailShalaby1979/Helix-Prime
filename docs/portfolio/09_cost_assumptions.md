# 9. Cost Assumptions

Costs are **assumptions and guardrails**, not measured production figures. The local-first design
means the pilot incurs effectively zero infrastructure cost.

## Assumptions
- **Local runtime:** $0 — runs on an existing machine; no paid APIs, no cloud, no external services.
- **Synthetic cloud demo:** the cloud-demo profile enforces **usage limits** and a **budget block**
  (a test asserts the budget gate blocks over-limit usage). If enabled, spend is capped to the demo
  profile and cannot exceed the configured limit.
- **No live model/API calls** in the pilot: the call-centre and restaurant workflows use synthetic
  connectors and deterministic functions; no token cost is incurred.

## Guardrails demonstrated
- `test_cloud_readiness.py` verifies: offline/local execution, missing-cloud safe failure, and
  cost control (budget block).
- The release gate's `dependency_locking` and `reproducible_install` checks confirm a pinned,
  reproducible dependency set.

## What is explicitly NOT claimed
- No real production cost model, no billed cloud usage, no SLAs. Real cost modeling requires a
  production deployment that is **not established** (see 11_known_limitations.md). Any production
  cost must be evidenced by the (currently red) production gates.

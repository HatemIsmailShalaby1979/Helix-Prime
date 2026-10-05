# Engine-to-skill map

What each Helix Prime engine is, beside the market skill it evidences. Written for a reviewer deciding whether the engineering is relevant to their role, so the market column is the point and the rest is the receipt.

Generated 2026-10-05 from `F:\Personnel\Helix-Prime` at commit `6133a50` (2026-10-05).

The last two columns are measurements read from the repository at that commit. The market-skill column is an editorial argument, not a measurement, and is kept separate so it can be argued with.

## The map

| Engine | What it does | Market skill it evidences | Implementation | Test evidence |
|---|---|---|---|---|
| **B2B Onboarding** | A multi-step onboarding process with state transitions and hand-offs. | Workflow design, programme management | `b2b/src/automator.py`<br>1879 LOC in 4 module(s) | referenced by 1 test module(s) |
| **CRM Engine** | A system of record where every write is attributable and replayable. | Data modelling, audit trails | `crm/src/sales_pipeline.py`<br>1487 LOC in 3 module(s) | referenced by 1 test module(s) |
| **CX Churn Sentinel** | Turning behavioural signal into a churn risk score and an alert. | Applied analytics, feature engineering | `cx/src/risk_scorer.py`<br>2117 LOC in 6 module(s) | 2 dedicated test module(s) |
| **Personnel Engine** | Role, authority and personnel-sensitive data classification. | Access control, identity concepts | `personnel/src/main.py`<br>2693 LOC in 5 module(s) | referenced by 1 test module(s) |
| **RTA Command Center** | Real-time adherence monitoring and intervention against a target. | Observability, incident response | `rta/src/calculations.py`<br>1668 LOC in 4 module(s) | referenced by 3 test module(s) |
| **WFM Forecasting / Erlang C** | Forecasting volume into staffing under uncertainty, via Erlang C. | Demand planning, capacity modelling | `wfm/src/erlang_c.py`<br>2612 LOC in 5 module(s) | 1 dedicated test module(s) |

## How to check this

Every row can be verified without taking my word for it:

- **Engine and source module** — `engines/{engine}/adapter.py`, first docstring line. The module named there is the one invoked; the implementation is not rewritten in the adapter.
- **Implementation size** — `LOC in N module(s)` counts the non-`__pycache__` Python files under `engines/{engine}/`.
- **Test evidence** — a count of files, not a pass count. Test *outcomes* require running the suite; this map deliberately does not claim pass rates it did not observe.

## What this map does not do

- It does not claim pass rates, coverage, or CI status. Those carry their own dates and run IDs elsewhere.
- It does not map engines to a job title. It maps code to a skill; whether that skill is the one a role needs is the reviewer's judgement, not a measurement.
- It does not cover the engines' production status. Every engine here is pre-pilot and `Production NOT_READY`; see the repository README for that claim and its date.

# Case study — Helix Prime

**data_mode: "simulated_realistic".** Every number below is a measurement on synthetic
data or a reading of source, with the repo path it comes from. There is no design
partner and no customer traffic; the demo data is synthetic by design.

**Positioning.** Pre-pilot governed operations core: a verified fail-closed gate and a
live WFM demo, backed by a green CI and a large test suite — but five of six engines are
adapter scaffolding that report synthesized metrics. Not production-ready: nine
production-only gates are red by design.

## The problem

An operations core that can execute actions on a live floor — staffing changes, CRM
writes, personnel moves — has one job that matters: never run an action the acting role
is not allowed to run, and never run one it should not run without a human in the loop.
On a real floor, a wrong automated action is an SLA or compliance breach, not a quirky
output. The hard part is therefore not "produce an answer"; it is *gating the action*
and recording the decision before it runs.

## The design

No generative model sits in the execution path. A task is evaluated by a deterministic,
rules-based gate — `evaluate_gate()` in `control_plane/governance.py:950` — invoked from
`control_plane/engine.py:808` at the `VALIDATED` workflow state. The gate fails closed:

- Four hard-deny checks return `dead_letter`: unknown role (`governance.py:972-983`),
  unknown classification (`985-994`), classification the role may not read
  (`996-1008`), and an engine the role does not own (`1010-1022`).
- Three boundary checks return `awaiting_approval`: financial cost over the role's
  limit (`1027-1039`), confidence below the autonomy floor of `0.75`
  (`MIN_AUTONOMY_CONFIDENCE`, `governance.py:64`; check at `1042-1054`), and an explicit
  approval request (`1056-1065`).
- Otherwise the task is `EXECUTING` (`1067-1075`).

The load-bearing signal is the **role profile**, not a model score: each role's owned
engines, readable data classifications, and financial limit are structural facts
declared in `organization/role-catalog.yaml` and loaded by
`organization/role_catalog.py`. The WFM demo — the only engine exercised end to end —
takes exactly four numbers, and the bridge injects `is_sample=True` and
`data_mode="simulated_realistic"` server-side (`helix_codex_app/integration/engine_bridge.py:586-587`);
a request carrying `data_classification` or `confidence_score` is refused with `400`
(`helix_codex_app/modules/ops/router.py:223-227`). The decision is written to an
append-only, hash-chained `audit_events` ledger before it runs
(`control_plane/engine.py:839-840`).

## How I tested it

- The full suite passes on the repo's CI (1,897 passed / 0 failed, snapshot
  2026-09-29; `README.md:131`), with coverage at 86.91% against the 80% floor. This
  session re-ran a claims-relevant subset — **122 passed / 0 failed** in 102s — but the
  full run did not terminate locally (killed at ~55 min, blocked on `tests/integration`
  network/browser paths requiring external services unavailable in this sandbox).
  Coverage was not re-measured here.
- `ruff check` is clean on the 17 CI paths (exit 0, this run); `ruff format --check .`
  reports 429 files already formatted (exit 0, this run).
- The fail-closed gate has its own tests: `tests/test_governance_fail_closed.py` and
  `tests/test_governance.py` exercise the dead-letter and awaiting-approval branches.
- The WFM demo path is covered by the shared suite (demo bridge at
  `helix_codex_app/integration/engine_bridge.py:529-587`; endpoint at
  `helix_codex_app/modules/ops/router.py:207`).

## What broke

- **CI was red for nine days and hid every later defect.** The workflow failed at step 5
  (`ruff check`) on every push from 2026-09-20 to 2026-09-28 (`AGENTS.md:39-44`, §21).
  Because that step aborted the job, steps 6–17 — the test suite, the security scans, the
  drift checks, both container steps — had **never executed once** in the repo's
  history. The ledger enumerates the root causes (§21.2): an `I001`/`B007` lint error in
  `scripts/generate_pdf.py`, 13 unformatted files, a missing `build`/`hatchling`
  declaration, and — the one to keep in view — nine evidence fixtures signed over CRLF
  bytes (445 B) while the committed blobs are LF (433 B), so they could only ever verify
  on Linux (`AGENTS.md:5104-5117`). I confirmed locally: `ruff check` and
  `ruff format --check` now both exit 0.
- **The pipeline went green for the first time on 2026-09-29** (run `36497766876` on
  `839507e`); fixes were commits `5755667` (clear the ruff failure), `8424b3e` (declare
  the build toolchain, re-sign the nine fixtures over LF), `839507e` (lock-pin count)
  (`AGENTS.md:5121-5137`).
- **During this documentation audit I found the engine scaffolding gap (issue 3 of
  `KNOWN_ISSUES.md`).** Five of six adapters return synthesized or echoed metrics: B2B
  fabricates `sop_generated=True` (`engines/b2b/adapter.py:326-328`), CRM echoes inputs
  (`engines/crm/adapter.py:311-318`), Personnel hardcodes `pipeline_status` and
  `workforce_headcount` from the request (`engines/personnel/adapter.py:297-322`), the CX
  scorer uses a hardcoded threshold table and an incoherent AHT unit
  (`engines/cx/src/risk_scorer.py:57-66,88`), and RTA surfaces an adherence dict without
  computing `confidence_score`. The shared test `tests/test_c4_engines.py:113` passes
  because it asserts adapters *return non-empty metrics*, which the fabrication satisfies.
  This is an open finding, not yet fixed, and it is the single largest gap between the
  README's "Six engines" framing and the code.

## What I decided, and why

- **Fix CI first; do not trust a green badge that has never run the suite.** The
  nine-day red hid pre-existing defects (two undeclared build dependencies, nine CRLF
  fixtures). The suite and the container steps now actually execute. The two container
  steps (16–17) still cannot be reproduced on this machine (Docker is not running here),
  so they rest on the remote green run alone (`AGENTS.md:5152-5153`).
- **Do not claim engine correctness the tests do not show.** The 80% coverage floor
  measures code execution, not result correctness. I have recorded the scaffolding gap
  openly rather than letting "1,897 tests pass" imply the engines compute right answers.
- **Keep production red by construction.** Nine production-only gates
  (`AGENTS.md:1516-1519`) read external signed evidence and refuse without it. No code
  change can unblock them; they need signatures from keys held outside this repository.

## What is not proven

- No production readiness, accuracy, adoption, or reliability beyond the WFM path. The
  demo data is synthetic by design.
- No real customer traffic, no live design-partner run (Scoach Academy Hub is a named
  first vertical via `capabilities/sports_academy/`, but no live traffic is recorded).
- Five of six engines are not yet validated to compute correct results (issue 3).
- No independent tenant-isolation audit, no external security review, no certified data
  isolation. The 19 cockpit UI tests are quarantined (`AGENTS.md:3454`).
- The WFM "Erlang C" result is a non-standard closed-form approximation, not the textbook
  formula (`engines/wfm/src/erlang_c.py:8,124`).

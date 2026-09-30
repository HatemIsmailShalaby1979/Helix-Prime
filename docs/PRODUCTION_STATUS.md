# Helix Prime — production status

**Positioning.** Pre-pilot governed operations core: a verified fail-closed gate and a
live WFM demo, backed by a green CI and a large test suite — all six engines now drive a
real computation end-to-end, and CX's risk thresholds load from
`config/risk_thresholds.yaml` rather than hardcoded values. Not production-ready: nine
production-only gates are red by design.

**What it does.** Helix Prime is the governed, local-first operations core of Helix
Codex. Identity, role-based access, a deterministic fail-closed gate, the Erlang C
forecasting engine, the CRM, the workflow engine, and the audit ledger live behind one
enforced surface. A decision is gated, recorded, and inspectable before it runs. There
is no generative model in the execution path.

**Proof it works.** A stranger can drive the governed path end to end on their own
machine: sign in with the demo identity (one permission, `ops.view`), submit four
numbers, and receive an Erlang C staffing answer produced by the same gate, workflow
record, and audit trail the internal pilot uses — then open the recorded decision chain
behind their own run (`helix_codex_app/modules/ops/router.py:207`,
`helix_codex_app/integration/engine_bridge.py:529-587`). The gate's four hard-deny
checks and three approval branches are covered by `tests/test_governance_fail_closed.py`.

**Live / demo — local only.** The public surface is the demo, which by default requires
`HELIX_APP_ENABLE_PASSWORDLESS_DEMO=true` and is a development/test fixture; it must not
be enabled on a deployed instance (`README.md:174-175`). A Cloudflare Quick Tunnel can
front the demo, but it is "not left running between sessions" (`README.md:122`) — there
is **no durable public deployment**. A reviewer without a local install can read the
audit ledger and run the test suite (see below); there is no guest account to click
through remotely.

**Signing in.** The demo identity is scoped to exactly one synthetic tenant and the
single `ops.view` permission; it cannot create, approve, execute, or delete anything but
the purpose-built demo endpoint (`README.md:58-63`,
`helix_codex_app/security/permissions.py`).

**Commercial status.** No billing integration is present. The repository's own records
state zero paying users and zero revenue (`AGENTS.md:140`, `README.md:140`). There is no
independent verification of current commercial activity because there is no production
deployment.

**SIMULATED DATA — evaluation.** Every behavioural number in this repo is synthetic or
author-written:
- Full suite: **1,897 passed / 0 failed**, coverage **86.91%** against an 80% floor
  (repo CI, snapshot 2026-09-29; `README.md:131-132`). This session re-ran a
  claims-relevant subset — **122 passed / 0 failed** — but the full run did not
  terminate locally (blocked on `tests/integration`). The suite asserts the
  adapter/contract/gate plumbing and the WFM math; it does **not** validate that the
  engines compute correct results — all six adapters now return computed results, but the
  suite asserts contracts, not accuracy (`docs/KNOWN_ISSUES.md` issue 3).
- WFM demo produces an Erlang C answer through the gate on synthetic four-number input.
  The "Erlang C" formula is a non-standard closed form
  (`engines/wfm/src/erlang_c.py:8,124`), not the textbook expression.
- The cockpit UI tier is quarantined: 19 tests deselected (`README.md:131`,
  `AGENTS.md:3454`).

**SIMULATED DATA — governance verification (2026-09-29).** CI went green for the first
time on run `36497766876` (`839507e`): all 17 steps passed, including the test suite,
`ruff check` (0 errors), `ruff format --check` (429 files), the governance checker, and
the build (`AGENTS.md:39-44`, §21). The two container steps (16–17) are not reproducible
on this machine (Docker not running) and rest on that remote run
(`AGENTS.md:5152-5153`).

**Limits.** There is no public sign-up with real tenants, no live design-partner
traffic, and the largest engine validation is the single-WFM demo path. A green
pipeline is not a production claim: nine production-only gates remain red
(`AGENTS.md:1516-1519`) — `signed_production_evidence`, `certified_data_isolation`,
`external_observer_audit`, `production_deployment_architecture`, `disaster_recovery_evidence`,
`operational_ownership`, `incident_oncall_ownership`, `security_review`,
`legal_privacy_review`. Each needs a signature from a key held outside this repository.
No external security audit, no certified data isolation, no signed installer. No revenue
and no paying users.

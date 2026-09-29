# Known issues — Helix Prime

Open limitations of the current build, each with the source that establishes it.
These are documented honestly; none is hidden behind a passing claim. Numbers are
reported exactly as found in code or measured on simulated data.

> Data mode: `simulated_realistic`. Every behavioural number here is a measurement on
> synthetic data or a reading of source. There is no real customer traffic; the demo
> data is synthetic by design.

> **Fixed, retained as the record.** Issues 1 and 2 are fixed in commit `2c9d606`
> and kept below, unchanged, as the record of what was wrong. The remaining issues
> are open.

## 1. The gate's `oversight_only` flag is parsed but never enforced — **FIXED**

> **Fixed** in commit `2c9d606`. `evaluate_gate()` now refuses `EXECUTING` for an
> oversight-only seat — a hard deny (`reason_code="oversight_only"`, `dead_letter`),
> independent of `target_engine` — and `RoleSpec.owns_engine(None)` now answers
> whether the seat owns any engine at all. Pinned by
> `tests/test_gate_oversight_and_approval.py::test_oversight_only_role_never_reaches_executing_without_a_target_engine`.
> The description below is kept unchanged as the record of the defect.

`control_plane/governance.py:176` declares `oversight_only: bool = False` on the
`RoleSpec`. `compliance_quality_gm` is created with `oversight_only=True` and
`owned_engines=()` (`governance.py:463-467`), and the README states such a role
"proposes, never executes" (`README.md` role-matrix Limitations). But
`evaluate_gate()` (`governance.py:950-1075`) never reads `oversight_only`. Worse,
`RoleSpec.owns_engine(None)` returns `True` (`governance.py:201-204`), so when a task
carries no `target_engine` the engine-ownership check passes. A compliance task with
cost 0 and confidence ≥ 0.75 therefore reaches `EXECUTING` (`governance.py:1067-1075`)
despite being an oversight-only role.

- Limits the claim that oversight roles "do not execute" — true in prose, not enforced
  by the gate. **(Resolved in `2c9d606`: the gate now enforces it.)**

## 2. `Engine.submit` does not forward `requires_approval` to the gate — **FIXED**

> **Fixed** in commit `2c9d606`. `Engine.submit` now forwards
> `request.requires_approval` to `evaluate_gate()`, so the gate's
> `approval_requested` branch is reachable from both submission paths and they agree
> on the verdict. Pinned by
> `tests/test_gate_oversight_and_approval.py::test_explicit_approval_is_gated_identically_on_both_submission_paths`.
> The description below is kept unchanged as the record of the defect.

`control_plane/engine.py:826-834` calls `evaluate_gate()` without the
`requires_approval` argument. The gate's `approval_requested` branch
(`governance.py:1056-1065`) is therefore unreachable from the `Engine.submit` path; the
hold happens instead via the separate `workflow.requires_approval` flag set at
`engine.py:836`. The two submission paths (`Engine.submit` vs
`GovernedWorkflowManager.submit`, which does pass it at `engine.py:1278`) treat
explicit approval requests inconsistently.

- Limits the claim that "every submission is gated before execution" — the gate's own
  explicit-approval branch is dead on one of the two paths. **(Resolved in `2c9d606`:
  the branch is now reachable from both paths.)**

## 3. Five of six engine adapters return synthesized or echoed metrics, not computed analytics

The demo and the shared test `tests/test_c4_engines.py:113`
(`test_all_six_adapters_invoke_real_engine_code`) confirm adapters *import and call*
engine modules and return non-empty metrics. But the **returned metrics** for five
engines are adapter-synthesized or echoed, not the engine's computed output:

- **B2B** — `engines/b2b/adapter.py:313-318` calls only `add_client` +
  `get_client_summary`; `generate_sop`/`generate_staffing_plan` are never invoked. The
  adapter then fabricates the result: `metrics.setdefault("sop_generated", True)` and
  `onboarding_status="completed"` at `engines/b2b/adapter.py:326-328`.
- **CRM** — `engines/crm/adapter.py:311-318` falls through to
  `{"status": "active", "client": ..., "deal": ...}` when `SalesPipeline` exposes no
  analytics method; the returned object is an echo of the inputs, not a computed
  pipeline analysis.
- **Personnel** — `engines/personnel/adapter.py:297-322` calls `get_pipeline_analytics()`
  on an empty `PipelineManager` (returns `{}`), then hardcodes
  `pipeline_status="active"` and `workforce_headcount` from the request input.
- **CX** — `engines/cx/src/risk_scorer.py` computes the churn score, but its risk
  thresholds are hardcoded in `__init__` (`risk_scorer.py:57-66`) and the AHT unit is
  incoherent (see issue 5); the richer `cx` modules (`kpi_aggregator`,
  `alert_dispatcher`, `sql_extractor`, `dashboard_feed`) are not invoked by the adapter.
- **RTA** — `engines/rta/src/calculations.py:92` computes `adherence_percentage`; the
  adapter surfaces that dict, but `confidence_score` is only set by `analyze()`, not on
  the adapter's `calc.calculate_adherence` path.

Only **WFM** drives a real computation end-to-end (Erlang C, `engines/wfm/src/erlang_c.py`).

- Limits the headline "Six engines" claim and the statement at `engines/README.md:52`
  that "Each adapter invokes real engine code (not fake)" — true for *invocation*,
  false for the *computed result* of five engines. The "not fake" wording overstates
  what the adapter output represents.
- The 1,897-test suite asserts the adapter *contract*, so green tests do **not** validate
  that RTA/CX/B2B/Personnel/CRM compute correct results. See Tier 2 in `README.md`.

## 4. The WFM "Erlang C" formula is a non-standard closed form, and its docstring is corrupted

`engines/wfm/src/erlang_c.py:124` computes
`probability_waiting = (p * (1 - ρ)) / (n*(1-ρ) + ρ*(1-(1-ρ)^(n-1)))`. This is a
closed-form approximation; it contains no factorial or summation term, so the standard
Erlang C series/gamma term is absent. The docstring formula at `erlang_c.py:8` is
corrupted with non-Latin glyphs (`دپ`, `خ»`), so the documented expression does not
match the code. `optimize_agents` binary-searches agent counts
(`erlang_c.py:175-205`); its upper bound `min(max_agents, int(arrival_rate*2))`
(`erlang_c.py:186`) can over-provision when no feasible count exists.

- `confidence_interval` is a fixed `0.05 * agents` margin (`erlang_c.py:243`),
  independent of the `confidence_level=0.95` parameter accepted at `erlang_c.py:40`,
  which is never used in the interval calculation.
- Limits the claim that WFM performs standard Erlang C forecasting — it is a plausible
  heuristic, not the textbook formula, and its stated confidence band is nominal.

## 5. CX churn scorer assumes AHT is at most 0.5 minutes

`engines/cx/src/risk_scorer.py:88` normalizes AHT as
`max(0, 1 - (value / 0.5))` with the comment "Assume max AHT is 0.5 minutes". Any
realistic handle time (e.g. 5 minutes) yields `0`, i.e. maximum risk, regardless of the
actual value. The adapter/sample data treat AHT as a 0–1 fraction while the scorer
assumes minutes (`engines/cx/contracts.py`), so the two disagree on units.

- Limits the accuracy of the CX Churn Sentinel risk score on any realistic input.

## 6. Rate limiting trusts a header set by an external Worker

`helix_codex_app/security/route_limits.py:124` keys the fixed-window counter on
`client_ip(request)`, which prefers `x-helix-client-ip`. That header is set or deleted
by the Cloudflare Worker, never passed through from `cf-connecting-ip`
(`helix_codex_app/security/client_ip.py:36,46-49`). `client_ip.py:24-28` states the
trust holds only "topologically" and "If the app is ever exposed without the Worker in
front, that trust no longer holds." `route_limits.py:11-15` notes the throttle mirrors
but does not share the login-throttle code ("Unifying the two is a reasonable
follow-up").

- Limits the "rate limiting keyed on the visitor, not on Cloudflare" claim whenever the
  app is not fronted by the Worker.

## 7. `dispatch.py` agent dispatch is a stub that returns fake output

`app/command_center/agents/dispatch.py` is wired but unfinished:
- `:187` `# TODO: Actually call the agent and get response` → returns the fake string
  `f"Called {agent_name} with: {message}"` (`:188`).
- `:204` `# TODO: Implement task submission through Engine` → returns fake
  `"Task submitted for approval"` (`:207`).
- `:217` `# TODO: Implement approval request through Engine` → fake output (`:220`).
- `:84` `# TODO: Validate args against tool schema` (unvalidated dispatch).
- `:262` a legacy regex call parser kept behind `HELIX_LEGACY_CALL_PARSING=1`.

- Limits the claim that nine AI agents route work — the agent-dispatch surface returns
  placeholder text, not real agent execution.

## 8. Connector activation is hardcoded `True`

`connectors/gateway.py:110` feeds the governance gate
`provider_activated=True,  # TODO: check actual activation status`. The gate's
activation check therefore runs against a constant, not a live provider state.

- Limits the claim that connectors are gated on real activation status.

## 9. The cockpit integration tier is quarantined

The UI integration tests are held out of the baseline by a collection hook
(`AGENTS.md:3454`); the README reports "19 deselected as a quarantined UI tier"
(`README.md:131`). The `ws /ws/v1/cockpit/stream` socket is "live and tested but unused
by the UI" (`AGENTS.md:3445`).

- Limits the "read-only Streamlit cockpit" readiness claim: the live cockpit client does
  not yet subscribe to the stream.

## 10. Engine correctness is not validated by the passing test suite

The suite reaches the 80% coverage floor (`README.md:132`), but coverage measures code
execution, not result correctness. Because five adapters return synthesized/echoed
metrics (issue 3), the passing tests certify the plumbing and the WFM math, not that
the engines produce correct operational numbers. There is no independent
tenant-isolation audit (cf. the 500/500 tagged-row count in LIVE Support Assistant), no
external security review, and no certified data-isolation evidence.

- Limits any inference from "1,897 tests pass" to "the product is correct".

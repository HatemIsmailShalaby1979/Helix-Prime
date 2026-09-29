# Known issues — Helix Prime

Open limitations of the current build, each with the source that establishes it.
These are documented honestly; none is hidden behind a passing claim. Numbers are
reported exactly as found in code or measured on simulated data.

> Data mode: `simulated_realistic`. Every behavioural number here is a measurement on
> synthetic data or a reading of source. There is no real customer traffic; the demo
> data is synthetic by design.

> **Fixed, retained as the record.** Issues 1 and 2 are fixed in commits `2c9d606`
> and `64928da` and kept below, unchanged, as the record of what was wrong. The
> remaining issues are open.

## 1. The gate's `oversight_only` flag is parsed but never enforced — **FIXED**

> **Fixed** in commits `2c9d606` and `64928da`. `evaluate_gate()` refuses `EXECUTING`
> for an oversight-only seat — a hard deny (`reason_code="oversight_only"`,
> `dead_letter`), independent of `target_engine` — and `RoleSpec.owns_engine(None)`
> now answers whether the seat owns any engine at all. Both submission paths act on
> the refusal: `GovernedWorkflowManager.submit`, and `Engine.submit`, which previously
> inspected only `requires_human_approval` and let a `dead_letter` decision fall
> through to `EXECUTING` (`64928da`). Pinned by
> `tests/test_gate_oversight_and_approval.py::test_oversight_only_role_never_reaches_executing_without_a_target_engine`
> and `::test_oversight_only_submission_dead_letters_through_engine_submit`.
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
  by the gate. **(Resolved in `2c9d606` and `64928da`: enforced on both submission
  paths.)**

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

## 3. Two of six engine adapters return synthesized or echoed metrics, not computed analytics

The demo and the shared test `tests/test_c4_engines.py:113`
(`test_all_six_adapters_invoke_real_engine_code`) confirm adapters *import and call*
engine modules and return non-empty metrics. But the **returned metrics** for three
engines are adapter-synthesized or echoed, not the engine's computed output:

- **B2B** — *no longer scaffolding.* `engines/b2b/adapter.py` now calls
  `OnboardingAutomator.generate_sop()` and `generate_staffing_plan()` after
  `add_client` and maps their actual return values (`sop`, `staffing_plan`,
  `workload_data`) into the adapter metrics; the fabricated `sop_generated=True` and
  `onboarding_status="completed"` defaults are gone (previously set at `:326-328`).
  The request schema carries no staffing-workload fields, so when `workload_data` is
  absent the adapter derives a minimal, explicitly-defaulted shape from the supplied
  profile rather than inventing business meaning. (Fixed in branch
  `fix/b2b-wire-real-onboarding`; pinned by
  `tests/test_c4_engines.py::test_b2b_adapter_wires_real_sop_and_staffing_plan`.)
- **CRM** — *no longer scaffolding.* `engines/crm/adapter.py` now maps the request's
  `client`/`deal` into real `Lead`/`Deal` objects via `add_lead`/`create_deal`, then
  calls `SalesPipeline.get_sales_analytics()` and returns its computed
  `stage_distribution`, `status_distribution`, `average_deal_value`,
  `total_pipeline_value` and 12-month forecast — not the previous
  `{"status": "active", "client": ..., "deal": ...}` echo (previously at `:311-318`).
  `Deal.probability` is required by the engine; the CRM request schema carries no
  probability, so it is defaulted from the engine's own stage config rather than
  invented. `score_lead` is deliberately not called: its signature requires
  company_size/industry/budget/timeline attributes the request schema does not provide,
  so calling it would re-introduce fabricated metrics. `support_status` (a hardcoded
  remnant) is dropped; `pipeline_status` is retained but now derived from the computed
  totals. (Fixed in branch `fix/crm-wire-real-pipeline`; pinned by
  `tests/test_c4_engines.py::test_crm_adapter_wires_real_pipeline_analytics`.)
- **Personnel** — `engines/personnel/adapter.py:297-322` calls `get_pipeline_analytics()`
  on an empty `PipelineManager` (returns `{}`), then hardcodes
  `pipeline_status="active"` and `workforce_headcount` from the request input.
- **CX** — `engines/cx/src/risk_scorer.py` computes the churn score, but its risk
  thresholds are hardcoded in `__init__` (`risk_scorer.py:57-66`); the AHT unit
  incoherence was resolved (see issue 5). The richer `cx` modules (`kpi_aggregator`,
  `alert_dispatcher`, `sql_extractor`, `dashboard_feed`) are not invoked by the adapter.
- **RTA** — *no longer scaffolding.* `engines/rta/adapter.py` now calls `calc.analyze()`,
  which runs `calculate_adherence` internally and additionally returns the engine's
  aggregated schedule, performance and variance metrics and `confidence_score`; the
  adapter maps that output into its metrics. (Previously it called `calculate_adherence`
  alone, whose dict carried no `confidence_score`.)

**WFM** (`engines/wfm/src/erlang_c.py`, Erlang C), **RTA**
(`engines/rta/src/calculations.py`), **B2B** (`engines/b2b/adapter.py` →
`engines/b2b/src/automator.py`), and **CRM** (`engines/crm/adapter.py` →
`engines/crm/src/sales_pipeline.py`) drive a real computation end-to-end; the two
adapters above (Personnel, CX) remain scaffolding.

- Limits the headline "Six engines" claim and the statement at `engines/README.md:52`
  that "Each adapter invokes real engine code (not fake)" — true for *invocation*,
  false for the *computed result* of two engines. The "not fake" wording overstates
  what the adapter output represents.
- The 1,897-test suite asserts the adapter *contract*, so green tests do **not** validate
  that Personnel/CX compute correct results. See Tier 2 in `README.md`.

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

## 5. ~~CX churn scorer assumes AHT is at most 0.5 minutes~~ — RESOLVED

**Resolved in `fix/cx-aht-normalization`.** The scorer assumed AHT was measured in
minutes (`max(0, 1 - value / 0.5)` at `engines/cx/src/risk_scorer.py:88`), but every
caller on the CX scoring path supplies AHT as a **0–1 fraction** — the adapter sample
(`engines/cx/adapter.py:253` → `aht: 0.3`), the engine `__main__` demo
(`risk_scorer.py:537-540` → `0.1–0.8`), `kpi_aggregator.py:338`, the engine's own
`config/risk_thresholds.yaml:16`, and the tests/fixtures
(`test_c4_engines.py:150,335,1080`; `tests/fixtures/c5/fixtures.py:79-81`). Reading
those values as seconds or minutes is physically absurd for a contact-center handle
time, which confirms the field is a fraction. The only duration-typed AHT is the
separate `aht_seconds` field in `engines/contracts.py:75` (330 s ≈ 5.5 min), which the
scorer does not consume.

**Fix:** normalize AHT as `goodness = 1 - value` (clamped to `[0,1]`) and recalibrate the
threshold band at `risk_scorer.py:57-66` to `{critical: 0.3, high: 0.5, medium: 0.7}` so
a higher AHT fraction yields a lower goodness and therefore a higher risk. The parallel
band in `config/risk_thresholds.yaml:16` was updated to match (the engine hardcodes its
thresholds and does not read the YAML). A regression test
(`tests/test_cx_aht_normalization.py`) pins that a realistic AHT fraction is no longer
collapsed to `0` and that risk is monotonic in the fraction.

- Remaining (minor) limitation: the thresholds are still hardcoded in the engine rather
  than loaded from `config/risk_thresholds.yaml` (deliberate, per the YAML header), but
  the AHT unit is now coherent.

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
execution, not result correctness. Because two adapters return synthesized/echoed
metrics (issue 3), the passing tests certify the plumbing and the WFM and RTA math, not that
the engines produce correct operational numbers. There is no independent
tenant-isolation audit (cf. the 500/500 tagged-row count in LIVE Support Assistant), no
external security review, and no certified data-isolation evidence.

- Limits any inference from "1,897 tests pass" to "the product is correct".

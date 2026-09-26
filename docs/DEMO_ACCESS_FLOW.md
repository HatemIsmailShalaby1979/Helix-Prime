# Demo access flow — the public WFM demo

How a demonstration visitor gets from the login screen to a governed workforce-
management answer, and what that answer is allowed to claim.

This document describes the surface shipped in **P8.1** (least-privilege demo
identity), **P8.2** (the governed demo endpoint) and **P8.3** (the clickable
screen). Two items remain unbuilt and are **not** numbered as phases: a rate
limit on the demo endpoint, and an audit-trail reader in the response beyond the
correlation id and the metrics digest. See `helix_codex_app/agents.md` for the
phase ledger.

---

## 1. The one-sentence version

A visitor signs in with GitHub through Supabase Auth, lands on a session whose
account holds the **demo** role — exactly one permission, `ops.view` — opens the
demo screen, submits four numbers, and gets a workforce-forecast answer produced
by the real governed engine path: recorded, auditable, and labelled as simulated.

### 1.1 Getting to it

| | |
|---|---|
| Sign in | `GET /app/auth/supabase/login` — **the one public flow**: GitHub OAuth through Supabase Auth, bridged onto the scoped demo account |
| Screen | `/app/ops/demo` — inside the ordinary `ops.view` boundary, not a separate public route |
| Submit | `POST /app/api/ops/demo/wfm` — session + CSRF, same endpoint an API caller uses |
| In the UI | Ops page → "Workforce demo" link, and the Ops rail item |

Supabase does not forward this app's `state` to the callback; it preserves the
query string already on `redirect_to` and appends its own `code`. The app's `state`
therefore travels inside `redirect_to` itself, and the callback checks it with
strict equality against the cookie set at login.

The screen is declared **above** the `/app/ops/{engine_id}` catch-all, because
FastAPI matches routes in declaration order: a screen registered below it would
be answered as an engine whose id happens to be `demo`.

**A refusal is JSON on both paths.** With htmx the result fragment is swapped in;
an error is not, so a rejected submission returns a JSON error body and the
`htmx:responseError` handler in `static/js/shell.js` surfaces it. Returning the
fragment on a refusal would swap a 400 into the result area and report no
failure at all.

### 1.2 The passwordless route is a fixture, not an entry point

`GET /app/auth/demo` signs the shared demo identity in with **no password and no
identity-provider round trip**. It is a **development and test fixture**. It is not
a public entry point and it is not the flow this document describes.

`create_app` mounts that route only when `HELIX_APP_ENABLE_PASSWORDLESS_DEMO` is
true, and the setting defaults to **false**. A deployed instance — including the
Worker-fronted demo — therefore has **no such route**: the path answers `404`
because it was never registered, not because it was refused. Enable it for local
development and for the test suite, and nowhere else.

---

## 2. Who the demo user is

| Property | Value |
|---|---|
| Domain | `helix-demo` |
| Tenant / client | `helix-demo` |
| Role | `demo` |
| Permissions | `ops.view` — **and nothing else** |
| Engine access | resolved through the normal tenant-scoped path, never tenant-blind |

The `demo` role is deliberately the smallest role in the system. It is
**not** an `ops_gm` in disguise, and it is **not** in
`APP_ROLE_ENGINE_CATALOG_ROLE` — that map is tenant-blind, so a role placed
there would resolve to exactly one tenant's engine for every tenant, which is
the cross-tenant bug P8.1 exists to prevent.

Because the role holds no `ops.manage` or `ops.approve`, a demo account cannot
create, approve, execute, or delete anything by any route other than the single
purpose-built demo endpoint documented below.

**Credentials are provisioned, never written down here.** The account is created
by `ensure_demo_account()`. On the public path the visitor's verified GitHub
identity is bridged onto it and its email is rewritten to the GitHub address, so
**no shared password is involved at all**. Where a password is used — local
development and the test suite — it is supplied by the operator through the
environment. This document deliberately contains no credential value, and neither
should any deployment document, ticket, or screenshot.

---

## 3. The request

```
POST /app/api/ops/demo/wfm
Content-Type: application/json
Cookie: <session>
X-CSRF-Token: <session csrf token>
```

The endpoint is behind the standard session guard and CSRF check, exactly like
every other mutating route. A request without a session gets `401`; a request
with a session but no CSRF token gets `403`.

### 3.1 The four inputs, and nothing else

```json
{
  "arrival_rate": 12.5,
  "average_handling_time": 6.0,
  "service_level_target": 0.8
}
```

That is the complete request. A caller may set **four numeric fields**:

| Field | Range (both ends exclusive) | Meaning |
|---|---|---|
| `arrival_rate` | `> 0`, unbounded above | calls arriving per period |
| `average_handling_time` | `> 0`, unbounded above | average contact duration |
| `service_level_target` | `> 0` and `< 1` | minimum share of contacts **answered immediately**; see the note below |
| `average_calls_per_period` | `> 0`, unbounded above | optional; **defaults to 17.0** |

The ranges are not invented by the app. They mirror the WFM engine's own
validation in `engines/wfm/adapter.py`, so the demo refuses a value at the edge
that the engine would refuse anyway.

**On the third field's name.** `service_level_target` sounds like a
speed-of-answer target, and the engine's own dataclass comment says "Desired
service level". Read the code rather than the name: `optimize_agents()` compares
`calculate_service_level(...)` against this target, and that function is
`exp(-agents * (1 - utilisation) * ASA)` — the probability a contact is
**answered immediately**. The engine is never given a waiting-time threshold, so
there is no "answered within 20 seconds" anywhere in this system. The name is
the engine's and is passed through unchanged; the *explanation* of what it
compares against belongs to the surface, which is why the screen states it
rather than letting a reader supply their own deadline.

Booleans, strings, `null`, `NaN` and `Infinity` are all rejected — `True` is not
accepted as `1`, because that is a category error, not a coercion.

### 3.2 Fields a caller can never set

A request containing any other key is **refused with `400`**, not silently
stripped. Silently dropping a field a caller thought they set is how a demo ends
up appearing to honour input it ignored.

The refused set includes, and is not limited to:

`is_sample`, `use_sample`, `data_mode`, `data_classification`,
`estimated_financial_cost`, `confidence_score`, `max_agents`, `owning_role_id`,
`capability`.

Two of these are the important ones:

- **`is_sample` / `data_mode`** are **server-owned**. The bridge always injects
  `is_sample: true` and `data_mode: "simulated_realistic"`. A demo run is
  synthetic by construction, and no request can make it claim otherwise.
- **`data_classification` and `confidence_score`** are the two fields that would
  let a caller dress a synthetic run up as a verified one. They are never read
  from the request.

The guarantee is structural, not a filter. The payload is built by a function
whose signature is four named numbers and which takes no `**kwargs` and no
`**extra`. There is no code path by which a caller-supplied key could reach the
workflow record, because the builder never reads one. A test asserts the
signature has no variadic parameter, so the property cannot be quietly broken by
a later edit.

---

## 4. What happens server-side

One request drives the **real governed lifecycle**, both gates crossed, in
order:

1. **Submit.** `Engine.submit` writes the workflow record, assigns the
   correlation id, and lets the governance layer decide the state. The demo
   passes `requires_approval=False` — that is a property of *this demo*, not a
   weakened control. The core's bounded-autonomy rules still run and decide.
2. **Execute.** If and only if the workflow reached `executing`, the engine is
   called and the result is written to the workflow.

Nothing is skipped and nothing is reordered. There is deliberately no window in
which a caller could interpose anything between the two steps.

The stored input payload is exactly the four numbers plus the two server-owned
fields:

```json
{
  "arrival_rate": 12.5,
  "average_calls_per_period": 17.0,
  "average_handling_time": 6.0,
  "data_mode": "simulated_realistic",
  "is_sample": true,
  "service_level_target": 0.8
}
```

---

## 5. The response

`201 Created`. Captured from a real request, not written from memory:

```json
{
  "capability": "wfm_forecast",
  "client_id": "helix-demo",
  "correlation_id": "e538347905434e1881c26a0c67124063",
  "data_mode": "simulated_realistic",
  "error": null,
  "executed": true,
  "is_sample": true,
  "metrics": {
    "average_speed_of_answer": 5.0,
    "calculation_time": 0.0,
    "confidence_interval": [1.9, 2.1],
    "optimal_agents": 2,
    "probability_waiting": 0.410958904109589,
    "service_level_achieved": 0.9394130628134758,
    "traffic_intensity": 0.625,
    "utilization": 0.625
  },
  "metrics_digest": "142ef332dd6e3478",
  "retry_count": 0,
  "state": "closed",
  "succeeded": true,
  "tenant_id": "helix-demo",
  "workflow_id": "wf_abdf9a94b1e7"
}
```

Read it like this:

- `metrics` are Erlang C workforce-planning figures for the inputs given: two
  agents to hold 62.5% utilisation, with 93.9% **answered immediately** and a
  41.1% probability that a contact waits. There is **no "within target"** in
  that sentence and no such field in the payload — see §3.1. The service level
  is the share answered at once, because the engine is never given a
  waiting-time threshold, and calling it a "share answered within target" is
  the single most likely way to misread a staffing forecast.
- `succeeded` is derived from the run's own evidence — `executed and error is
  None and metrics` — and `state` is reported beside it rather than instead of
  it. **`closed` on its own does not mean the run finished cleanly:**
  `WorkflowState` is plain string constants, and `closed` is also reached by
  cancellation, compensation and dead-lettering. A successful demo run ends
  `closed` too, so reading `closed` as success was the bug this response had.
- `correlation_id` ties this answer to the audit trail and the event stream.
- `metrics_digest` is the first 16 hex characters of a SHA-256 over the
  canonical JSON of `metrics`. The same inputs give the same digest; changing an
  input changes it. It is a fingerprint, **not** a signature and **not** an
  attestation.
- `confidence_interval` is `[1.9, 2.1]` — a flat ±5% band around the optimum.
  It is **not** a statistical confidence interval: no sampling error and no
  probability is computed, and the engine's `confidence_level` field is
  unused. The screen labels it "Agent range around that figure" for that
  reason.
- `is_sample: true` and `data_mode: "simulated_realistic"` are on the response on
  purpose, so no downstream renderer can quietly drop the label.
  `simulated_realistic` is the **connector** spelling and the one the governed
  vocabulary declares; `sample` is the engine's internal term and is not a
  governed data mode, so it must not appear here.

---

## 6. What the evidence is — and what it is not

This distinction is the whole point of the phase, so it is worth stating
plainly.

**Is evidence:**

- the workflow record, with its state and correlation id;
- the stored metrics, which the audit trail and the event stream also carry;
- the metrics digest, as a stable fingerprint of those stored metrics.

**Is not evidence:**

- **There is no `computation_evidence` field, on purpose.** The registered
  engine handler returns `EngineResult.metrics` and discards
  `computation_evidence`; there is none to report. Naming a field the engine
  never produced is how a sample run gets dressed up as a verified one.
- **`wfm_coverage` is not governed evidence.** The same bridge exposes a
  coverage figure that calls the WFM adapter *directly*, bypassing policy,
  events, audit and the workflow record. It is a fast preview, and it must
  never be presented as the result of a governed run. Only the demo endpoint
  described here is the governed path.
- **No confidence or classification claim.** The caller cannot set them, and the
  response asserts no such claim. `metrics.confidence_interval` is *not* a
  counter-example: it is a flat ±5% band around the optimum that the engine
  computes, with no sampling error and no probability behind it, and the screen
  labels it "Agent range around that figure" for exactly that reason. The
  engine's `confidence_level=0.95` is never used.

**Provenance, restated:** every record this flow writes carries
`data_mode: "simulated_realistic"` and `is_sample: true`. A demonstration of
Helix Codex OS is a demonstration *of the governance path* on clearly-labelled
synthetic input. It is not a customer result, and it should never be presented
as one.

---

## 7. When the governance layer holds

If the core's bounded-autonomy rules do not let the workflow reach `executing`,
the demo **reports the held state instead of forcing it through**. The engine is
not called at all.

The response then carries two extra fields:

```json
{
  "executed": false,
  "gated": true,
  "gated_reason": "workflow is 'awaiting_approval', not 'executing' - the engine was not called"
}
```

This is the honest answer for a demonstration. Forcing the run would prove
nothing about the product and would hide exactly the property the demo exists to
show.

---

## 8. Failure modes

| Situation | Status | Body |
|---|---|---|
| no session | `401` | standard auth error |
| session, no CSRF token | `403` | standard CSRF error |
| key the demo does not own, e.g. `is_sample` | `400` | `the WFM demo accepts only [...]; refused ['is_sample']` |
| value outside the engine's range, e.g. target `5` | `400` | `service_level_target must be greater than 0.0 and less than 1.0, got 5.0` |
| a required field missing | `400` | names the missing field |
| non-numeric, boolean, `NaN`, `Infinity` | `400` | names the field and the type problem |
| a session outside the demo tenant | `403` | tenant isolation holds at the service seam |
| a role without `ops.view` | `403` | the permission matrix refuses before any engine call |
| core not running | `503` | typed `EngineUnavailableError`, never a fabricated number |

A malformed request is refused rather than repaired. A demo that quietly
corrected a visitor's input would be demonstrating something other than the
product.

---

## 9. See also

- `helix_codex_app/agents.md` — the P8 phase ledger, test counts, and the two
  unbuilt items (endpoint rate limiting, audit-trail reader).
- `helix_codex_app/repomap.md` — module map and the seam descriptions for
  `engine_bridge.py` and the ops routes.
- `helix_codex_app/governance.md` — entry 32, the P8.2 governance record.
- `tests/helix_codex_app/test_wfm_demo_governed_path.py` — the 47-test gate.
- `tests/helix_codex_app/test_wfm_demo_screen.py` — the 21-test screen gate.
- `tests/helix_codex_app/test_demo_role.py` — the 31-test least-privilege gate.

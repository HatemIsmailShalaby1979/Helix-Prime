"""The governed public WFM demo: submit, execute, and what it is allowed to say.

P8.2 proves three things, and each is checked in the direction that would catch
the defect it is about:

1. The demo runs the REAL governed path. `Engine.submit` is crossed and then
   `Engine.execute` is called, and the numbers reported are the ones the
   registered handler wrote to the workflow. This is the distinction that
   matters: `wfm_coverage` in the same bridge runs the adapter directly and
   bypasses policy, events, audit and the workflow record entirely, so its
   figure is not evidence of a governed run and must never be presented as one.
2. The caller's influence stops at four numbers. The payload is built by the
   bridge from a signature with no `**extra`, so `is_sample`, `data_mode`,
   `data_classification`, `max_agents`, `estimated_financial_cost` and
   `confidence_score` cannot be forwarded — not because they are filtered, but
   because they are never read. Anything unexpected in the request is refused
   with a 400 rather than quietly dropped, so a demo can never look like it
   honoured a field it ignored.
3. A workflow the governance gate is holding is REPORTED, never forced. The
   engine must not be reached at all, and that is asserted against an engine
   that raises if called — a test that only checked the returned state would
   pass just as well if the call had been made and swallowed.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import EngineUnavailableError, NotFoundError
from helix_codex_app.integration import engine_bridge
from helix_codex_app.modules.ops.service import OpsService
from helix_codex_app.security.accounts import (
    DEMO_CLIENT_ID,
    DEMO_DOMAIN_NAME,
    DEMO_TENANT_ID,
    AccountRepository,
    ensure_demo_account,
)
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

DEMO_PATH = "/app/api/ops/demo/wfm"
# The four inputs a caller may set, and a value inside every range.
GOOD = {
    "arrival_rate": 12.5,
    "average_handling_time": 6.0,
    "service_level_target": 0.8,
}
# The fields a caller must never be able to set. Each is either read by the core
# or by the adapter, so forwarding one would relabel or re-price the run.
UNOWNED_FIELDS = (
    "is_sample",
    "use_sample",
    "data_mode",
    "data_classification",
    "estimated_financial_cost",
    "confidence_score",
    "max_agents",
    "owning_role_id",
    "capability",
)


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain(
        DEMO_DOMAIN_NAME, tenant_id=DEMO_TENANT_ID, client_id=DEMO_CLIENT_ID
    )
    demo = ensure_demo_account(repo, password_hash=hash_password("x"))
    outsider_domain = repo.create_domain("other.test", tenant_id="tenant-b", client_id="client-b")
    outsider = repo.create_account(
        outsider_domain.domain_id, "other", role_id="manager", password_hash=hash_password("x")
    )
    employee_domain = repo.create_domain("staff.test", tenant_id="tenant-c", client_id="client-c")
    employee = repo.create_account(
        employee_domain.domain_id, "staffer", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        demo=demo,
        outsider=outsider,
        employee=employee,
        settings=settings,
        store=store,
        tmp_path=tmp_path,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx, monkeypatch):
    monkeypatch.setenv("HELIX_DB_PATH", str(ctx.tmp_path / "workflow.db"))
    monkeypatch.setenv("HELIX_AUDIT_DB_PATH", str(ctx.tmp_path / "audit.db"))
    monkeypatch.setenv("HELIX_LOG_PATH", str(ctx.tmp_path / "logs.jsonl"))
    from server.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _session(ctx, account) -> tuple[dict, dict]:
    token, _issued = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _run(client, ctx, account, body: dict | None = None):
    cookies, headers = _session(ctx, account)
    return client.post(DEMO_PATH, json=body or GOOD, cookies=cookies, headers=headers)


# --- 1. the real governed path ------------------------------------------------


def test_the_demo_runs_the_governed_path_and_reports_what_the_engine_produced(client, ctx):
    from server.deps import get_provider

    response = _run(client, ctx, ctx.demo)
    assert response.status_code == 201, response.text
    report = response.json()

    assert report["executed"] is True
    assert report["succeeded"] is True
    assert report["state"] == "closed"
    assert report["error"] is None
    assert report["retry_count"] == 0
    assert report["capability"] == "wfm_forecast"
    assert report["tenant_id"] == DEMO_TENANT_ID
    assert report["client_id"] == DEMO_CLIENT_ID
    assert report["correlation_id"]
    assert "gated" not in report

    # The engine really computed, through the registered handler, and the
    # numbers are the ones the workflow carries.
    stored = get_provider().engine.store.get_workflow(report["workflow_id"])
    assert stored.output_payload == report["metrics"]
    assert stored.state == "closed"
    for metric in (
        "optimal_agents",
        "probability_waiting",
        "average_speed_of_answer",
        "service_level_achieved",
        "confidence_interval",
    ):
        assert metric in report["metrics"], f"{metric} missing from the reported metrics"
    assert report["metrics"]["optimal_agents"] > 0


def test_the_demo_reaches_executing_without_an_approval(client, ctx):
    """One click, but still through the gate rather than around it."""
    response = _run(client, ctx, ctx.demo)
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["executed"] is True

    from server.deps import get_provider

    engine = get_provider().engine
    workflow = engine.store.get_workflow(report["workflow_id"])
    # The workflow asked for no approval and was granted none, which is the
    # point of the demo: one click, no second person, still a governed record.
    assert workflow.requires_approval is False
    assert workflow.approval is None
    assert workflow.owning_role_id == "ops_gm"
    assert workflow.state == "closed"


def test_the_reported_sample_mode_is_the_engine_s_own_record(client, ctx):
    response = _run(client, ctx, ctx.demo)
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["is_sample"] is True
    assert report["data_mode"] == "simulated_realistic"


def test_no_computation_evidence_is_claimed(client, ctx):
    """The handler discards `computation_evidence`, so naming it would be a lie."""
    response = _run(client, ctx, ctx.demo)
    assert response.status_code == 201, response.text
    assert "computation_evidence" not in response.json()


# --- 2. the caller's influence stops at four numbers --------------------------


def test_the_stored_payload_carries_no_client_owned_governance_field(client, ctx):
    from server.deps import get_provider

    report = _run(client, ctx, ctx.demo).json()
    stored = get_provider().engine.store.get_workflow(report["workflow_id"])
    payload = stored.input_payload
    assert set(payload) == {
        "arrival_rate",
        "average_handling_time",
        "service_level_target",
        "average_calls_per_period",
        "is_sample",
        "data_mode",
    }
    # Left out on purpose: the core and the adapter both read classification out
    # of the input payload, so a caller able to set it could relabel the run.
    assert "data_classification" not in payload
    assert "estimated_financial_cost" not in payload
    assert "confidence_score" not in payload
    # `max_agents` is never read by the adapter, so accepting it would imply a
    # staffing cap that does not exist.
    assert "max_agents" not in payload
    assert payload["is_sample"] is True


@pytest.mark.parametrize("field", UNOWNED_FIELDS)
def test_the_caller_cannot_choose_a_governance_field(client, ctx, field):
    response = _run(client, ctx, ctx.demo, {**GOOD, field: "live"})
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert field in error


def test_an_unrecognised_field_is_refused_rather_than_ignored(client, ctx):
    """Silently dropping a field would look exactly like honouring it."""
    response = _run(client, ctx, ctx.demo, {**GOOD, "engine": "wfm"})
    assert response.status_code == 400, response.text
    assert "engine" in response.json()["error"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("arrival_rate", 0),
        ("arrival_rate", -1),
        ("average_handling_time", 0),
        ("service_level_target", 0),
        ("service_level_target", 1),
        ("service_level_target", 1.5),
        ("average_calls_per_period", 0),
        ("arrival_rate", "Infinity"),
        ("arrival_rate", "-Infinity"),
        ("service_level_target", "NaN"),
        ("arrival_rate", True),
        ("service_level_target", "not-a-number"),
    ],
)
def test_an_out_of_range_input_is_refused_at_the_edge(client, ctx, field, value):
    response = _run(client, ctx, ctx.demo, {**GOOD, field: value})
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert field in error
    if field == "service_level_target" and value in (0, 1):
        low, high = engine_bridge.WFM_DEMO_NUMERIC_RANGES[field]
        assert f"must be greater than {low} and less than {high}" in error
        assert repr(value) in error


@pytest.mark.parametrize("field", sorted(GOOD))
def test_a_missing_required_input_is_refused(client, ctx, field):
    body = {key: value for key, value in GOOD.items() if key != field}
    response = _run(client, ctx, ctx.demo, body)
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert field in error


def test_average_calls_per_period_defaults_and_can_be_set(client, ctx):
    from server.deps import get_provider

    engine = get_provider().engine
    defaulted = _run(client, ctx, ctx.demo).json()
    assert (
        engine.store.get_workflow(defaulted["workflow_id"]).input_payload[
            "average_calls_per_period"
        ]
        == 17.0
    )

    supplied = _run(client, ctx, ctx.demo, {**GOOD, "average_calls_per_period": 40}).json()
    assert (
        engine.store.get_workflow(supplied["workflow_id"]).input_payload["average_calls_per_period"]
        == 40.0
    )


def test_a_form_post_is_coerced_exactly_like_json(client, ctx):
    """HTMX and JSON must not disagree about what the same inputs mean."""
    cookies, headers = _session(ctx, ctx.demo)
    form = {key: str(value) for key, value in GOOD.items()}
    posted = client.post(DEMO_PATH, data=form, cookies=cookies, headers=headers)
    assert posted.status_code == 201, posted.text
    sent = _run(client, ctx, ctx.demo).json()

    assert sent["metrics"] == posted.json()["metrics"]


def test_the_payload_builder_offers_no_escape_hatch():
    """Structural guard: the whitelist is the signature, not a filter.

    If a `**extra` or a `**kwargs` is ever added, a caller could widen the
    payload again and every behavioural test above would keep passing — they
    assert what the builder REJECTS, not what it would forward.
    """
    signature = inspect.signature(engine_bridge.wfm_demo_input_payload)
    kinds = {parameter.kind for parameter in signature.parameters.values()}
    assert inspect.Parameter.VAR_KEYWORD not in kinds
    assert inspect.Parameter.VAR_POSITIONAL not in kinds

    payload = engine_bridge.wfm_demo_input_payload(**GOOD)
    assert set(payload) == set(engine_bridge.WFM_DEMO_NUMERIC_RANGES) | {"is_sample", "data_mode"}


# --- 3. a held workflow is reported, never forced -----------------------------


def test_a_workflow_the_gate_is_holding_is_reported_not_forced(client, ctx, monkeypatch):
    """Can-fail proof: this engine raises if the call is ever made."""
    from server.deps import get_provider

    engine = get_provider().engine
    held = OpsService().submit(
        ctx.demo,
        capability=engine_bridge.WFM_DEMO_CAPABILITY,
        input_payload=engine_bridge.wfm_demo_input_payload(**GOOD),
        requires_approval=True,
    )
    assert held.state == "awaiting_approval"

    def explode(*_args, **_kwargs):
        raise AssertionError("the engine was reached for a workflow that is not executing")

    monkeypatch.setattr(type(engine), "execute", explode)
    report = engine_bridge.execute_workflow(ctx.demo, held.workflow_id)

    assert report["executed"] is False
    assert report["succeeded"] is False
    assert report["gated"] is True
    assert "awaiting_approval" in report["gated_reason"]
    assert report["state"] == "awaiting_approval"
    # The stored metrics are still empty, because nothing was computed.
    assert report["metrics"] == {}
    assert report["metrics_digest"] is None


def test_another_tenant_cannot_execute_this_tenant_s_workflow(client, ctx):
    from server.deps import get_provider

    engine = get_provider().engine
    held = OpsService().submit(
        ctx.demo,
        capability=engine_bridge.WFM_DEMO_CAPABILITY,
        input_payload=engine_bridge.wfm_demo_input_payload(**GOOD),
        requires_approval=True,
    )
    with pytest.raises(NotFoundError):
        engine_bridge.execute_workflow(ctx.outsider, held.workflow_id)
    # And the workflow is untouched: no ownership oracle, no state change.
    assert engine.store.get_workflow(held.workflow_id).state == "awaiting_approval"


# --- 4. the boundary ----------------------------------------------------------


def test_the_demo_account_may_run_the_demo(client, ctx):
    """The positive case for the P8.1 voice: ops.view plus the scoped identity."""
    response = _run(client, ctx, ctx.demo)
    assert response.status_code == 201, response.text


def test_the_demo_account_holds_no_permission_beyond_ops_view(ctx):
    from helix_codex_app.security.permissions import PERMISSIONS, permissions_for

    held = set(permissions_for(ctx.demo))
    assert held == {"ops.view"}
    assert set(PERMISSIONS) - held  # the other 12 keys are denied, not absent


def test_an_employee_is_refused(client, ctx):
    response = _run(client, ctx, ctx.employee)
    assert response.status_code == 403, response.text


def test_the_route_needs_a_session(client, ctx):
    assert client.post(DEMO_PATH, json=GOOD).status_code == 401


def test_the_route_needs_a_csrf_token(client, ctx):
    cookies, _headers = _session(ctx, ctx.demo)
    response = client.post(DEMO_PATH, json=GOOD, cookies=cookies)
    assert response.status_code == 403, response.text


# --- 5. fail closed, never a fabricated figure --------------------------------


def test_an_unavailable_engine_is_a_typed_503_not_a_fake_figure(client, ctx, monkeypatch):
    """Can-fail proof: the same request returns 201 without the patch."""
    from control_plane.engine import Engine

    def boom(*_args, **_kwargs):
        raise RuntimeError("the engine fell over")

    monkeypatch.setattr(Engine, "execute", boom)
    response = _run(client, ctx, ctx.demo)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "engine_unavailable"


def test_the_metrics_digest_is_stable_and_input_sensitive(client, ctx):
    report = _run(client, ctx, ctx.demo).json()
    metrics = report["metrics"]
    assert report["metrics_digest"] == engine_bridge._metrics_digest(metrics)
    # Key order must not matter; a single changed digit must.
    reordered = dict(reversed(list(metrics.items())))
    assert engine_bridge._metrics_digest(reordered) == report["metrics_digest"]
    changed = {**metrics, "optimal_agents": int(metrics["optimal_agents"]) + 1}
    assert engine_bridge._metrics_digest(changed) != report["metrics_digest"]


def test_the_digest_is_sixteen_hex_characters(client, ctx):
    report = _run(client, ctx, ctx.demo).json()
    digest = report["metrics_digest"]
    assert digest is not None
    assert len(digest) == 16
    assert all(character in "0123456789abcdef" for character in digest)


def test_the_bridge_reports_a_missing_figure_rather_than_zero():
    """A workflow with no output payload has no digest, not an empty one."""
    workflow = SimpleNamespace(
        workflow_id="wf_1",
        capability="wfm_forecast",
        state="executing",
        correlation=SimpleNamespace(correlation_id="cor_1"),
        tenant_id="tenant-a",
        client_id="client-a",
        input_payload={},
        output_payload=None,
        retry_count=0,
        error=None,
    )
    report = engine_bridge._execution_report(workflow, executed=True)
    assert report["metrics"] == {}
    assert report["metrics_digest"] is None
    assert report["succeeded"] is False
    assert report["is_sample"] is False
    assert report["data_mode"] is None


def test_the_engine_unavailable_error_is_raised_for_a_dead_provider(monkeypatch):
    from helix_codex_app import db as _db  # noqa: F401 - imported for parity with the app

    def dead():
        raise RuntimeError("the governed engine is not running")

    monkeypatch.setattr("server.deps.get_provider", dead)
    with pytest.raises(EngineUnavailableError):
        engine_bridge.execute_workflow(SimpleNamespace(tenant_id="t"), "wf_1")


def _closed(*, output, error=None):
    """A workflow in the state a real finished run of this demo lands in."""
    return SimpleNamespace(
        workflow_id="wf_closed",
        capability="wfm_forecast",
        state="closed",
        correlation=SimpleNamespace(correlation_id="cor_1"),
        tenant_id="tenant-a",
        client_id="client-a",
        input_payload={},
        output_payload=output,
        retry_count=0,
        error=None if error is None else SimpleNamespace(message=error),
    )


def test_a_closed_state_alone_is_never_reported_as_success():
    """`closed` is not a success state; it is where four outcomes land.

    `WorkflowState` is a class of plain string constants and `closed` is
    reachable from `succeeded`, `compensated`, `cancelled` AND `dead_letter`
    (`control_plane/workflow.py`). This demo's own successful run finishes
    `closed` (`control_plane/engine.py`), so the ambiguous state is the COMMON
    one, not an edge case. A test that reads "the state is closed" as "the run
    succeeded" therefore prints the figures of a dead-lettered or cancelled run
    as a result the engine stands behind, and reports a closed run that wrote
    nothing as if it had.

    Every case below is one the state-membership test answered `True`; the
    third is pinned so the fix cannot over-correct into "never successful".
    """
    # Closed, no output: the engine produced nothing, so there is no result.
    assert (
        engine_bridge._execution_report(_closed(output=None), executed=True)["succeeded"] is False
    )
    # Closed, output AND a recorded error: figures exist, but they are not a
    # clean result and the error is shown beside them.
    assert (
        engine_bridge._execution_report(
            _closed(output={"optimal_agents": 2}, error="the engine reported a fault"),
            executed=True,
        )["succeeded"]
        is False
    )
    # Closed, output, no error: the real path, and it must still read as a success.
    assert (
        engine_bridge._execution_report(_closed(output={"optimal_agents": 2}), executed=True)[
            "succeeded"
        ]
        is True
    )


def test_success_is_not_claimed_for_a_run_the_bridge_did_not_perform():
    """A held workflow is reported, not executed, whatever payload it carries.

    `executed` is load-bearing on its own: the governance gate can hold a
    workflow that already has an output payload, and reporting that as this
    request's success would claim a result nobody ran.
    """
    report = engine_bridge._execution_report(_closed(output={"optimal_agents": 2}), executed=False)
    assert report["executed"] is False
    assert report["gated"] is True
    assert report["gated_reason"]
    assert report["succeeded"] is False

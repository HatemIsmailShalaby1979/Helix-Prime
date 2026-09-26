"""The WFM demo screen: what an operator is shown, and what it may claim.

P8.2 (in `test_wfm_demo_governed_path.py`) proves the demo runs the real
governed path. This file is about the part a visitor actually looks at, and
each test is aimed at the way a screen like this misleads rather than at the
way it breaks:

1. ACCESS. The screen sits under a permission like the rest of Ops, so the
   tests are written against a refused request, not a raised one. An employee
   must not be able to read the page, submit through it, or reach the endpoint.
2. THE FOUR NUMBERS, AND ONLY THE FOUR. A form field with no endpoint field
   would be a control that silently does nothing; an endpoint field with no
   form control would be an input a visitor cannot reach. The two are checked
   against each other so neither drift is possible.
3. TWO ANSWER SHAPES, ONE RUN. htmx must get the fragment it swaps in, and an
   API caller must get JSON. Both cross the same governed path, so the fragment
   is a view of the same report rather than a second computation.
4. HONESTY. This is the one that matters. The screen must not invent a figure,
   must not relabel a sample as a real run, must not present the engine's
   derived service level as a contractual deadline, and must not colour a
   `closed` workflow green — because `closed` is where a cancelled or
   dead-lettered run lands as well as a successful one.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from contracts.vocabulary import CONNECTOR_DATA_MODES, CONNECTOR_SIMULATED_REALISTIC
from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.integration import engine_bridge
from helix_codex_app.modules.ops import router as ops_module
from helix_codex_app.modules.ops.router import (
    WFM_DEMO_FIELD_HELP,
    WFM_DEMO_FIELDS,
    WFM_DEMO_FORM_FIELDS,
    ops_router,
)
from helix_codex_app.security.accounts import (
    DEMO_CLIENT_ID,
    DEMO_DOMAIN_NAME,
    DEMO_TENANT_ID,
    AccountRepository,
    ensure_demo_account,
)
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore
from helix_codex_app.templating import templates

SCREEN_PATH = "/app/ops/demo"
DEMO_PATH = "/app/api/ops/demo/wfm"
GOOD = {
    "arrival_rate": 12.5,
    "average_handling_time": 6.0,
    "service_level_target": 0.8,
}
HTMX = {"HX-Request": "true"}


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
    manager_domain = repo.create_domain("other.test", tenant_id="tenant-b", client_id="client-b")
    manager = repo.create_account(
        manager_domain.domain_id, "boss", role_id="manager", password_hash=hash_password("x")
    )
    staff_domain = repo.create_domain("staff.test", tenant_id="tenant-c", client_id="client-c")
    employee = repo.create_account(
        staff_domain.domain_id, "staffer", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        demo=demo,
        manager=manager,
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


def _screen(client, ctx, account):
    cookies, _headers = _session(ctx, account)
    return client.get(SCREEN_PATH, cookies=cookies)


def _run(client, ctx, account, *, htmx=True, body=None):
    cookies, headers = _session(ctx, account)
    sent = {**headers, **HTMX} if htmx else dict(headers)
    return client.post(DEMO_PATH, json=body or GOOD, cookies=cookies, headers=sent)


def _prose(html: str) -> str:
    """Collapse whitespace before asserting on sentences.

    Jinja keeps the template's own line breaks and indentation in the output, so
    a phrase that reads as one line in the source arrives split across three.
    Asserting on raw text would then fail on a rewrap that changed nothing a
    reader sees — the kind of failure that trains people to rewrap tests.
    """
    return re.sub(r"\s+", " ", html)


def _dd(html: str, label: str) -> str:
    """The value cell that follows a `<dt>`, so a claim is checked in place.

    Asserting that a number appears *somewhere* on the page is not the same
    claim: the interesting failure is the right figure next to the wrong label.
    """
    block = html.split(f"<dt>{label}</dt>", 1)
    assert len(block) == 2, f"no {label!r} on the page"
    cell = block[1].split("<dd", 1)[1].split(">", 1)[1].split("</dd>", 1)[0]
    return _prose(cell).strip()


def _hint_for(name: str) -> str:
    """The hint the form shows beside one field, from the router's own table.

    Read from `WFM_DEMO_FIELD_HELP` rather than scraped off the page, so the
    assertion is about the declared hint and not about how the template happens
    to wrap it. The two can drift, and a scrape would follow the drift.
    """
    return WFM_DEMO_FIELD_HELP[name]["hint"]


def _fragment(**report) -> str:
    """Render the result partial against a hand-built report.

    The endpoint cannot be made to omit a figure the engine wrote, so the
    template's own honesty is checked here instead — a report shaped the way an
    incomplete or unusual run would shape it.
    """
    base = {
        "workflow_id": "wf_1",
        "capability": "wfm_forecast",
        "state": "closed",
        "executed": True,
        "succeeded": True,
        "retry_count": 0,
        "error": None,
        "gated": False,
        "gated_reason": None,
        "metrics": {},
        "metrics_digest": None,
        "correlation_id": "cor_1",
        "tenant_id": "tenant-a",
        "client_id": "client-a",
        "data_mode": "sample",
        "is_sample": True,
    }
    base.update(report)
    return templates.get_template("partials/wfm_demo_result.html").render(
        report=base, inputs=None, csrf_token="t", settings=None
    )


# --- 1. access ---------------------------------------------------------------


def test_the_demo_screen_is_not_reachable_without_a_session(client):
    assert client.get(SCREEN_PATH).status_code in (401, 302)


def test_an_employee_cannot_read_or_run_the_demo(client, ctx):
    """Least privilege, checked on BOTH the page and the endpoint.

    Checking the page alone would leave the endpoint readable by anyone who
    learned its URL, which is the shape a browser-only gate always takes.
    """
    cookies, headers = _session(ctx, ctx.employee)
    page = client.get(SCREEN_PATH, cookies=cookies)
    assert page.status_code == 403
    assert "wfm-demo__form" not in page.text
    posted = client.post(DEMO_PATH, json=GOOD, cookies=cookies, headers={**headers, **HTMX})
    assert posted.status_code == 403


def test_the_demo_reaches_its_demo_role_and_any_ops_reader(client, ctx):
    for account in (ctx.demo, ctx.manager):
        response = _screen(client, ctx, account)
        assert response.status_code == 200, account.role_id
        assert "wfm-demo__form" in response.text


# --- 2. the four numbers, and only the four ----------------------------------


def test_the_form_and_the_endpoint_cannot_name_different_fields():
    """The form's ORDER and NAMES are derived from the engine's own ranges.

    So this cannot drift by editing one side: a field added to the endpoint and
    not the form shows up as a difference here, not as a control that does
    nothing on screen.
    """
    assert [f["name"] for f in WFM_DEMO_FORM_FIELDS] == list(engine_bridge.WFM_DEMO_NUMERIC_RANGES)
    assert set(WFM_DEMO_FIELDS) == set(engine_bridge.WFM_DEMO_NUMERIC_RANGES)


def test_every_input_carries_its_own_unit_and_a_starting_value(client, ctx):
    """A bare number with no unit is a question nobody can answer correctly.

    `0.8` is 80% to one visitor and 0.8% to another, and the form is where that
    is settled — not the prose above it.
    """
    page = _screen(client, ctx, ctx.demo)
    assert page.status_code == 200
    for field in WFM_DEMO_FORM_FIELDS:
        assert f'id="wfm-{field["name"]}"' in page.text
        assert f'name="{field["name"]}"' in page.text
        assert field["label"] in page.text
        assert field["unit"] in page.text
        assert field["hint"] in page.text
        assert f'value="{field["default"]}"' in page.text
    # The one genuinely ambiguous field says what its number means.
    assert "0.8 means 80%" in page.text


def test_the_form_carries_a_csrf_token_and_starts_with_no_result(client, ctx):
    page = _screen(client, ctx, ctx.demo)
    assert "X-CSRF-Token" in page.text
    assert "No run yet." in page.text


def test_the_ops_page_offers_a_way_in(client, ctx):
    """A screen nothing links to is a screen nobody finds."""
    cookies, _headers = _session(ctx, ctx.demo)
    ops = client.get("/app/ops", cookies=cookies)
    assert ops.status_code == 200
    assert SCREEN_PATH in ops.text


def test_the_demo_route_is_matched_before_the_catch_all_engine_route():
    """A screen declared below `/ops/{engine_id}` is unreachable.

    FastAPI matches in declaration order, so `/app/ops/demo` would be answered
    as an engine whose id happens to be "demo" — a 404, or worse, an engine
    page — and the misordering would be invisible in a template test.
    """
    paths = [
        getattr(r, "path", None)
        for r in ops_router.routes
        if getattr(r, "path", "").startswith("/app/ops")
    ]
    assert "/app/ops/demo" in paths
    assert paths.index("/app/ops/demo") < paths.index("/app/ops/{engine_id}")


# --- 3. two answer shapes, one run -------------------------------------------


def test_an_api_caller_gets_json_and_a_created_status(client, ctx):
    response = _run(client, ctx, ctx.demo, htmx=False)
    assert response.status_code == 201, response.text
    assert response.headers["content-type"].startswith("application/json")
    report = response.json()
    assert report["capability"] == "wfm_forecast"
    assert report["workflow_id"]
    assert report["succeeded"] is True
    assert report["metrics"]


def test_htmx_gets_the_fragment_it_swaps_in(client, ctx):
    response = _run(client, ctx, ctx.demo, htmx=True)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="wfm-demo-result"' in response.text
    assert "What the engine returned" in response.text
    # A fragment, not a second page: it must not carry the app shell.
    assert "<html" not in response.text.lower()


def test_the_fragment_reports_the_request_that_made_it_not_the_form(client, ctx):
    """A user can retype a field after a run.

    Showing the current form value beside an older result would quietly
    misreport which numbers produced the figures, so the run carries its own
    inputs through to the view.
    """
    response = _run(client, ctx, ctx.demo, htmx=True, body={**GOOD, "arrival_rate": 9.0})
    assert response.status_code == 200
    assert "9.0" in response.text
    assert "14.2" not in response.text


def test_a_refusal_stays_json_even_to_htmx(client, ctx):
    """The fragment has no error branch, so a refusal must not arrive as HTML.

    `shell.js` turns a non-2xx htmx response into a toast. Returning the
    fragment on a refusal would swap an error message into the result area and
    report no failure at all.
    """
    for htmx in (True, False):
        response = _run(client, ctx, ctx.demo, htmx=htmx, body={**GOOD, "is_sample": False})
        assert response.status_code == 400, htmx
        assert response.headers["content-type"].startswith("application/json"), htmx
        assert "is_sample" in response.json()["error"]


def test_the_endpoint_refuses_a_write_without_a_csrf_token(client, ctx):
    cookies, _headers = _session(ctx, ctx.demo)
    response = client.post(DEMO_PATH, json=GOOD, cookies=cookies, headers=HTMX)
    assert response.status_code == 403


def test_the_run_is_published_to_the_workflow_stream(client, ctx, monkeypatch):
    """The result is announced, not only returned.

    A report that is only ever a response body cannot appear in the workflow
    stream the Ops pages already subscribe to, so the governed run would be
    invisible to the rest of the app.
    """
    seen: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        ops_module,
        "publish",
        lambda key, event, payload: seen.append((key, event, payload)),
    )
    response = _run(client, ctx, ctx.demo, htmx=True)
    assert response.status_code == 200
    assert len(seen) == 1
    key, event, payload = seen[0]
    assert key == f"workflow:{payload['workflow_id']}"
    assert event == "execution"
    assert payload["metrics"]


# --- 4. honesty --------------------------------------------------------------


def test_a_result_never_shows_a_figure_the_engine_did_not_write():
    """An absent figure is shown as absent, and never as a zero.

    A zero here would be the worst possible lie on this screen: "0 agents" and
    "0.0% service level" read as measurements, and a reader has no way to tell
    them from real ones.
    """
    html = _fragment(metrics={"optimal_agents": 3}, succeeded=True)
    assert ">3<" in html
    for absent in ("Probability of waiting", "Average speed of answer", "Service level achieved"):
        block = html.split(absent, 1)[1].split("</div>", 1)[0]
        assert "not reported" in block, absent
    assert ">0<" not in html
    assert "0.0%" not in html


def test_a_run_with_no_figures_says_so_instead_of_blaming_the_response():
    """The "no metrics" branch must not fire when something else explains it.

    A gated workflow has no metrics *because* the gate held it, and a failed
    one has none *because* it failed. Telling the visitor the request "produced
    no metrics" in either case blames the wrong thing and hides the reason.
    """
    gated = _fragment(metrics={}, gated=True, gated_reason="held by the gate", succeeded=False)
    assert "The engine was not called." in gated
    assert "held by the gate" in gated
    assert "No figures." not in gated

    failed = _fragment(metrics={}, error="the engine reported a fault", succeeded=False)
    assert "The run failed." in failed
    assert "the engine reported a fault" in failed
    assert "No figures." not in failed

    unexplained = _fragment(metrics={}, succeeded=True)
    assert "No figures." in unexplained
    assert "not reported" not in unexplained


def test_a_finished_but_unsuccessful_run_is_not_reported_as_a_success():
    """The success line follows the evidence, not the state name."""
    html = _fragment(state="dead_letter", succeeded=False, metrics={}, error="quarantined")
    assert "succeeded no" in html
    assert "executed yes" in html


def test_a_held_run_is_never_green():
    """`closed` also means cancelled and dead-lettered, so it is not a success colour.

    The chip's class is derived from the state name, and the palette is limited
    to states whose meaning is fixed. `closed` therefore gets no success
    treatment, or a cancelled run would read as a clean finish.
    """
    success = _fragment(state="succeeded", metrics={"optimal_agents": 3})
    chip = re.search(r"proposal-card__state--(\w+)", success)
    assert chip is not None
    finished = _fragment(state="closed", metrics={"optimal_agents": 3})
    assert "proposal-card__state--closed" in finished
    assert "succeeded yes" in finished


def test_the_run_is_labelled_sample_data_and_names_its_own_ids(client, ctx, monkeypatch):
    """The claims a reader can check afterwards: what ran, under which request.

    The report is taken from the stream publication of the SAME request whose
    fragment is asserted on. Two separate runs would have two workflow ids, and
    the test would only be proving that some id appears somewhere.
    """
    published: list[dict] = []
    monkeypatch.setattr(ops_module, "publish", lambda _k, _e, p: published.append(p))
    html = _run(client, ctx, ctx.demo, htmx=True).text
    assert len(published) == 1
    report = published[0]
    # The governed record is stamped with the CONNECTOR spelling of a sample,
    # not the engine's internal one. `sample` is what the adapter reports to the
    # engine; `simulated_realistic` is the declared connector/memory term, and a
    # governed report wearing the engine's spelling would be a term no
    # vocabulary declares. Asserted against the vocabulary so a regression to
    # the engine's spelling fails here instead of reading as valid.
    assert report["data_mode"] == CONNECTOR_SIMULATED_REALISTIC
    assert report["data_mode"] in CONNECTOR_DATA_MODES
    assert report["is_sample"] is True
    assert report["metrics_digest"]
    for value in (
        report["workflow_id"],
        report["correlation_id"],
        report["tenant_id"],
        report["client_id"],
        report["metrics_digest"],
    ):
        assert value in html, value
    # A sample must not be able to read as a live run.
    assert "live" not in html.lower()


def test_the_service_level_is_never_described_as_a_deadline(client, ctx):
    """The engine is given no waiting-time threshold, so the screen must not imply one.

    The derived service level is the share answered *without waiting*, and the
    submitted target is a fraction the caller set. Reading either as "answered
    within X seconds" would be a claim the engine never made, and it is the
    single most likely misreading of a staffing forecast. The screen therefore
    carries the correction in full, and this asserts the correction is what is
    there — the sentence is the deliverable, not the absence of a word.
    """
    html = _run(client, ctx, ctx.demo, htmx=True).text
    prose = _prose(html)
    assert "Handling time is the talk-plus-wrap length of a call" in prose
    assert "not a speed-of-answer target" in prose
    assert "rather than a share answered" in prose
    # The target is shown as the percentage a visitor set, not as a raw 0.8.
    assert "service-level target of 80%" in prose
    # No affirmative deadline claim anywhere on the result.
    for claim in ("answered within the", "within 20 seconds", "answer within"):
        assert claim not in prose.lower()

    # The form hint matters as much as the result prose, and this is where the
    # misreading starts: the visitor sets 0.8 here, before any run has produced
    # a single figure. The correction was carried on the result and left off
    # this one line, so the result explained the number the form had already
    # misdescribed. Same rule, both places the sentence can appear.
    hint = _hint_for("service_level_target")
    assert "answered immediately" in hint
    for claim in ("answered within the", "within 20 seconds", "answer within"):
        assert claim not in hint.lower()


def test_the_numbers_are_shown_in_the_units_the_engine_returned(client, ctx, monkeypatch):
    """ASA arrives in minutes, and the two fractions arrive as percentages.

    A seconds suffix on a minutes value misreports every run by a factor of
    sixty, and a raw 0.93 for a service level reads as 0.93% to anyone who has
    not been told the scale. Each is checked in the cell it belongs to, so a
    correct number under the wrong label still fails.
    """
    published: list[dict] = []
    monkeypatch.setattr(ops_module, "publish", lambda _k, _e, p: published.append(p))
    html = _run(client, ctx, ctx.demo, htmx=True).text
    metrics = published[0]["metrics"]

    assert _dd(html, "Average speed of answer") == f"{metrics['average_speed_of_answer']:.2f} min"
    assert _dd(html, "Service level achieved") == f"{metrics['service_level_achieved'] * 100:.1f}%"
    assert _dd(html, "Probability of waiting") == f"{metrics['probability_waiting'] * 100:.1f}%"
    assert _dd(html, "Agents needed") == str(metrics["optimal_agents"])

    # The band is two numbers read as a range, not a Python tuple repr.
    low, high = metrics["confidence_interval"]
    assert _dd(html, "Agent range around that figure") == f"{low:.1f} \u2013 {high:.1f} agents"
    assert "(1.9, 2.1)" not in html

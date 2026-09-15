"""The memory screen (P5.4).

The screen has one job: show somebody enough to decide honestly. These tests
render the card partial directly and pin the three things that matter — the
evidence numbers are on screen, the rollback control appears only once a proposal
has been applied, and an approve button is never offered on your own proposal.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.modules.memory import router as memory_router
from helix_codex_app.modules.memory.service import MemoryService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.templating import templates


def _card(*, state="evaluated", own=False):
    proposal = {
        "proposal_id": "prop-0001",
        "kind": "policy",
        "target": "follow_up_threshold",
        "approval_state": state,
        "version": 2,
        "hypothesis": "a lower threshold catches more at-risk accounts",
        "risk_assessment": "low: reversible and monitored",
        "rollback_plan": "restore the previous threshold",
        "audit_chain": "chain intact",
        "data_mode": "simulated_realistic",
        "evaluation_results": {
            "baseline_rate": 0.0,
            "proposed_rate": 1.0,
            "delta": 1.0,
            "n_historical": 12,
            "n_simulated": 3,
            "passed": True,
            "detail": "meets the minimum improvement",
        },
    }
    return {
        "proposal": proposal,
        "evidence": proposal["evaluation_results"],
        "author_name": None if own else "Ravi",
        "can_evaluate": own and state == "draft",
        "can_approve": (not own) and state == "evaluated",
        "can_reject": (not own) and state == "evaluated",
        "can_rollback": own and state == "approved",
        "data_mode": "simulated_realistic",
    }


def _render(card):
    return templates.env.get_template("partials/proposal_card.html").render(
        card=card, csrf_token="csrf-test"
    )


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    memory_root = str(tmp_path / "memory_stores")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("academy.test", tenant_id="tenant-a", client_id="client-a")
    ravi = repo.create_account(
        domain.domain_id,
        "ravi",
        role_id="employee",
        password_hash=hash_password("your-password"),
    )
    layla = repo.create_account(
        domain.domain_id,
        "layla",
        role_id="manager",
        password_hash=hash_password("your-password"),
    )
    service = MemoryService(conn, memory_root=memory_root)
    yield SimpleNamespace(
        conn=conn, repo=repo, domain=domain, ravi=ravi, layla=layla, service=service
    )
    db.close(conn)


# --- the evidence ------------------------------------------------------------
def test_the_evidence_table_shows_the_numbers():
    html = _render(_card())
    assert "Baseline rate" in html
    assert "0.000" in html
    assert "Proposed rate" in html
    assert "1.000" in html
    assert "Change" in html
    assert "+1.000" in html
    assert "Historical cases" in html
    assert ">12<" in html
    assert "Simulated cases" in html
    assert ">3<" in html


def test_the_risk_and_rollback_plan_are_on_the_card():
    html = _render(_card())
    assert "reversible and monitored" in html
    assert "restore the previous threshold" in html
    assert "chain intact" in html


def test_an_unevaluated_proposal_says_so_instead_of_showing_zeroes():
    card = _card(state="draft", own=True)
    card["evidence"] = {}
    html = _render(card)
    assert "Not evaluated yet" in html
    assert "Baseline rate" not in html


# --- the controls ------------------------------------------------------------
def test_the_rollback_control_is_absent_until_the_proposal_is_applied():
    assert "/rollback" not in _render(_card(state="evaluated"))
    assert "/rollback" not in _render(_card(state="draft", own=True))
    assert "/rollback" not in _render(_card(state="rejected"))
    assert "/rollback" in _render(_card(state="approved", own=True))


def test_an_approve_button_is_never_shown_on_your_own_proposal():
    html = _render(_card(state="evaluated", own=True))
    assert "/approve" not in html
    assert "/reject" not in html


def test_a_reviewer_sees_approve_and_reject_but_not_evaluate():
    html = _render(_card(state="evaluated"))
    assert "/approve" in html
    assert "/reject" in html
    assert "/evaluate" not in html
    assert "Why not?" in html


def test_an_author_sees_evaluate_on_their_own_draft():
    html = _render(_card(state="draft", own=True))
    assert "/evaluate" in html
    assert "/approve" not in html


def test_the_data_mode_badge_is_never_hidden():
    html = templates.env.get_template("partials/data_mode_badge.html").render(
        data_mode="simulated_realistic"
    )
    assert "simulated_realistic" in html
    assert "not live" in html


# --- the page ----------------------------------------------------------------
def test_the_page_shows_only_the_accounts_own_records(ctx):
    ctx.service.stores.record(
        ctx.ravi, kind="outcome", nature="verified_outcome", body={"note": "ravi"}, confidence=0.4
    )
    ctx.service.stores.record(
        ctx.layla, kind="outcome", nature="verified_outcome", body={"note": "layla"}, confidence=0.4
    )
    context = memory_router._page_context(ctx.service, ctx.ravi)
    notes = [record.body.get("note") for record in context["records"]]
    assert notes == ["ravi"]


def test_the_page_offers_a_review_queue_only_to_a_reviewer(ctx):
    proposal = ctx.service.propose(
        ctx.ravi,
        kind="policy",
        target="follow_up_threshold",
        baseline="threshold=0.5",
        proposed="threshold=0.3",
        baseline_policy={"value": 0.5},
        proposed_policy={"value": 0.3},
        hypothesis="a lower threshold catches more at-risk accounts",
        risk_assessment="low",
        rollback_plan="restore the previous threshold",
    )
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)

    ravi_view = memory_router._page_context(ctx.service, ctx.ravi)
    assert ravi_view["review_cards"] == []
    assert len(ravi_view["own_cards"]) == 1

    layla_view = memory_router._page_context(ctx.service, ctx.layla)
    assert len(layla_view["review_cards"]) == 1
    assert layla_view["review_cards"][0]["can_approve"] is True
    assert layla_view["own_cards"] == []

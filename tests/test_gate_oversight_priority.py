"""Oversight-only seats are a hard deny, checked before the softer boundaries.

Moving the ``oversight_only`` check ahead of the financial / confidence /
explicit-approval branches means an oversight seat can never be softened into
``awaiting_approval``: it is always isolated as ``dead_letter``. (Prompt F2.)

``compliance_quality_gm`` is the oversight-only seat used throughout, with a
financial approval limit of 0.0, so each of the three cases below would have
returned ``awaiting_approval`` under the old ordering and must now be refused.
"""
from __future__ import annotations

from control_plane.governance import evaluate_gate
from control_plane.workflow import WorkflowState

OVERSIGHT_ROLE = "compliance_quality_gm"


def _assert_oversight_dead_letter(decision) -> None:
    assert decision.state == WorkflowState.DEAD_LETTER
    assert decision.reason_code == "oversight_only"
    assert decision.allowed is False
    assert decision.requires_human_approval is False


def test_oversight_seat_dead_letters_when_cost_exceeds_limit():
    decision = evaluate_gate(
        OVERSIGHT_ROLE,
        estimated_financial_cost=10_000.0,
        confidence_score=1.0,
        data_classification="internal",
    )
    _assert_oversight_dead_letter(decision)


def test_oversight_seat_dead_letters_on_low_confidence():
    decision = evaluate_gate(
        OVERSIGHT_ROLE,
        estimated_financial_cost=0.0,
        confidence_score=0.0,
        data_classification="internal",
    )
    _assert_oversight_dead_letter(decision)


def test_oversight_seat_dead_letters_when_approval_requested():
    decision = evaluate_gate(
        OVERSIGHT_ROLE,
        estimated_financial_cost=0.0,
        confidence_score=1.0,
        data_classification="internal",
        requires_approval=True,
    )
    _assert_oversight_dead_letter(decision)

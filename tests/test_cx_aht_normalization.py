"""
Regression test for the CX churn scorer AHT normalization fix.

Background (docs/KNOWN_ISSUES.md issue 5, resolved in fix/cx-aht-normalization):
``engines/cx/src/risk_scorer.py`` normalized AHT as ``max(0, 1 - value / 0.5)``,
assuming AHT was measured in minutes. Every caller on the CX scoring path supplies
AHT as a 0-1 fraction (adapter, __main__ demo, kpi_aggregator, risk_thresholds.yaml,
tests/fixtures), so the ``/ 0.5`` divisor pinned any realistic AHT to 0 — i.e. maximum
risk regardless of the actual value.

This test pins the corrected behaviour: a realistic AHT fraction must no longer
collapse the normalized AHT score to 0, and the risk level must be derived from the
actual fraction, not forced to critical.
"""

import pytest

from engines.cx.src.risk_scorer import RiskScorer, RiskScorerEngine


def _score_aht(aht_fraction: float) -> dict:
    scorer = RiskScorerEngine()
    result = scorer.score_customers(
        [
            {
                "customer_id": "CUST-TEST",
                "csat": 0.8,
                "sla": 0.9,
                "fcr": 0.85,
                "aht": aht_fraction,
            }
        ]
    )
    return next(r for r in result.customer_risks if r.get("customer_id") == "CUST-TEST")


def test_realistic_aht_not_pinned_to_max_risk():
    # A realistic mid-range AHT fraction (0.5) must NOT collapse to 0, which was the
    # bug (1 - 0.5 / 0.5 == 0 under the old formula).
    risk = _score_aht(0.5)
    aht = risk["kpi_analysis"]["risk_levels"]["aht"]
    assert aht["score"] > 0.0, (
        f"AHT fraction 0.5 normalized to {aht['score']} — must not be pinned to 0 "
        "after the unit fix"
    )
    # A mid fraction is not the worst case, so it must not be force-classified critical.
    assert aht["risk_level"] != "critical", (
        f"AHT fraction 0.5 classified as {aht['risk_level']}; realistic AHT must not "
        "be pinned to maximum risk"
    )


def test_aht_risk_is_monotonic_with_fraction():
    # Higher AHT fraction -> lower goodness score -> higher risk.
    low = _score_aht(0.1)["kpi_analysis"]["risk_levels"]["aht"]
    mid = _score_aht(0.5)["kpi_analysis"]["risk_levels"]["aht"]
    high = _score_aht(0.9)["kpi_analysis"]["risk_levels"]["aht"]
    assert low["score"] > mid["score"] > high["score"]
    assert low["risk_level"] in ("low", "medium")
    assert high["risk_level"] in ("critical", "high")


def test_old_bug_formula_no_longer_used():
    # Direct guard against regression: the new normalization yields 1 - 0.5 == 0.5 for
    # an AHT fraction of 0.5 (the old formula yielded 0).
    scorer = RiskScorer()
    out = scorer.calculate_kpi_score({"aht": 0.5})
    assert out["risk_levels"]["aht"]["score"] == pytest.approx(0.5, abs=1e-9)

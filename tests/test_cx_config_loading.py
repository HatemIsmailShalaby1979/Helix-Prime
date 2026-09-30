"""Regression: the CX RiskScorer loads tunable parameters from config, not hardcoded.

Gap closed: ``engines/cx/src/risk_scorer.py`` previously hardcoded ``kpi_thresholds``
(and ``classify_risk_level`` hardcoded the 0.8/0.6/0.4 bands) while
``engines/cx/config/risk_thresholds.yaml`` existed as the intended single source of
truth. These tests fail against the pre-fix module: overriding the config path changed
nothing because the values were not loaded from the YAML.
"""
from __future__ import annotations

import textwrap

import engines.cx.src.risk_scorer as rs


def test_default_config_loads_packaged_yaml():
    """The default load returns the packaged YAML values, not a code copy."""
    cfg = rs.load_risk_config()
    assert cfg["kpi_weights"] == {"csat": 0.3, "sla": 0.3, "fcr": 0.2, "aht": 0.2}
    assert cfg["kpi_thresholds"]["aht"] == {"critical": 0.3, "high": 0.5, "medium": 0.7}
    assert cfg["risk_bands"] == {"critical": 0.8, "high": 0.6, "medium": 0.4}


def test_scorer_uses_config_thresholds_not_hardcoded(tmp_path, monkeypatch):
    """Point the loader at a different YAML; the scorer must follow it."""
    custom = textwrap.dedent(
        """
        kpi_weights:
          csat: 0.25
          sla: 0.25
          fcr: 0.25
          aht: 0.25
        kpi_thresholds:
          csat: { critical: 0.1, high: 0.2, medium: 0.3 }
          sla:  { critical: 0.1, high: 0.2, medium: 0.3 }
          fcr:  { critical: 0.1, high: 0.2, medium: 0.3 }
          aht:  { critical: 0.1, high: 0.2, medium: 0.3 }
        risk_bands:
          critical: 0.7
          high: 0.5
          medium: 0.3
        """
    )
    cfg_path = tmp_path / "risk_thresholds.yaml"
    cfg_path.write_text(custom, encoding="utf-8")
    monkeypatch.setattr(rs, "DEFAULT_CONFIG_PATH", cfg_path)

    engine = rs.RiskScorerEngine()
    # Thresholds and bands now come from the custom config, proving they are loaded.
    assert engine.risk_scorer.kpi_thresholds["aht"]["critical"] == 0.1
    assert engine.risk_scorer.risk_bands["critical"] == 0.7

    # Scoring reflects the loaded band: AHT 0.75 -> goodness 0.25. Under the packaged
    # band (aht critical 0.3) that is "critical"; under the custom band (critical 0.1,
    # medium 0.3) it is "medium". The difference proves the value is config-driven.
    customer = {"customer_id": "C1", "csat": 1.0, "sla": 1.0, "fcr": 1.0, "aht": 0.75}
    result = engine.score_customers([customer])
    aht_level = result.customer_risks[0]["kpi_analysis"]["risk_levels"]["aht"]["risk_level"]
    assert aht_level == "medium"

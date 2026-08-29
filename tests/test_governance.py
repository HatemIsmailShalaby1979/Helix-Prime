from pathlib import Path

from GOVERNANCE import governance_check


def test_constitution_is_present_and_authoritative():
    result = governance_check.run_checks()
    assert result["checks"]["constitution"]["ok"] is True
    assert result["checks"]["master_story_authority"]["ok"] is True


def test_stale_authority_reference_is_detected(tmp_path: Path):
    stale = tmp_path / "stale.md"
    stale.write_text("Read ROOT_BOOT.md before implementation.", encoding="utf-8")
    result = governance_check.check_stale_authority_references([stale])
    assert result["ok"] is False
    assert "ROOT_BOOT.md" in result["detail"]


def test_governance_check_is_read_only_and_deterministic():
    first = governance_check.run_checks()
    second = governance_check.run_checks()
    assert first == second

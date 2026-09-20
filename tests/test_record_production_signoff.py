"""The sign-off recorder: the terminal go/no-go step (Class 5.8).

`release/signoff.py` validates and serialises a `SignOff`, and `import_go_no_go()`
reads the local consent flag, but nothing could *create* a record. These tests pin
the properties that make the recorder safe:

* it cannot manufacture an approval — a fully filled `production_approved` record
  is still refused while the nine production-only gates are red on evidence;
* it refuses to write inside the repository;
* a template is not a valid record until a human fills it;
* the rules are `signoff.validate_signoff`, so `check` and the gate cannot
  disagree.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from release import signoff

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "record_production_signoff.py"


def _load_recorder():
    spec = importlib.util.spec_from_file_location("_record_production_signoff", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recorder = _load_recorder()


def _write(path: pathlib.Path, **fields) -> pathlib.Path:
    record = signoff.SignOff(**fields)
    path.write_text(json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def _complete(**overrides) -> dict:
    fields = dict(
        state="pilot_approved",
        decision="approve",
        reviewer="a named human",
        reviewer_role="pilot_operator",
        decided_at="2026-09-20T12:00:00Z",
        evidence_pack_id="pack-1",
        evidence_refs=["pack-1/summary.json"],
    )
    fields.update(overrides)
    return fields


def test_states_lists_every_state_and_marks_the_human_approvals(capsys) -> None:
    assert recorder.main(["states"]) == 0
    out = capsys.readouterr().out
    for state in signoff.SIGN_OFF_STATES:
        assert state in out
    assert "human approval" in out
    assert "local only" in out


def test_template_refuses_an_unknown_state(tmp_path) -> None:
    target = tmp_path / "nope.json"
    with pytest.raises(SystemExit) as excinfo:
        recorder.main(["template", "--state", "approved_ish", "--out", str(target)])
    assert "not a sign-off state" in str(excinfo.value)
    assert not target.exists()


def test_template_refuses_to_write_inside_the_repository() -> None:
    target = ROOT / "not-a-real-signoff.json"
    with pytest.raises(SystemExit) as excinfo:
        recorder.main(["template", "--state", "pilot_approved", "--out", str(target)])
    assert "inside the repository" in str(excinfo.value)
    assert not target.exists(), "the refusal must happen before anything is written"


def test_a_template_is_not_a_valid_record_until_a_human_fills_it(tmp_path, capsys) -> None:
    """The anti-fabrication property for the terminal step.

    A fresh template must fail the very validator the gate calls. If this ever
    passes, the tool has started inventing the fields a person is supposed to own.
    """
    record = tmp_path / "production.json"
    assert recorder.main(["template", "--state", "production_approved", "--out", str(record)]) == 0

    data = json.loads(record.read_text(encoding="utf-8"))
    ok, reason = signoff.validate_signoff(signoff.SignOff.from_dict(data))
    assert ok is False
    assert "decision='approve'" in reason
    # And it names the human fields as empty rather than filling them.
    for field in ("reviewer", "reviewer_role", "decided_at", "evidence_pack_id"):
        assert data[field] == ""
    assert data["evidence_refs"] == []
    assert data["signature_ref"] is None


def test_a_complete_record_is_still_refused_without_the_nine_gates(
    tmp_path, monkeypatch, capsys
) -> None:
    """Every field filled, and still refused — the point of the whole path.

    `production_approved` requires all nine production-only gates green *on signed
    external evidence*. A well-formed record must not be able to stand in for that,
    or the terminal approval could be produced by anyone who can type.
    """
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_DIR", raising=False)
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", raising=False)
    record = _write(
        tmp_path / "production.json",
        **_complete(state="production_approved", signature_ref="sig-1"),
    )

    assert recorder.main(["check", "--record", str(record)]) == 1
    out = " ".join(capsys.readouterr().out.split())
    assert "requires every production-only gate green" in out
    assert "produce_production_evidence.py status" in out

    # The same record is accepted once it does not claim to be a production
    # approval: the refusal is about the missing evidence, not about the shape.
    pilot = _write(tmp_path / "pilot.json", **_complete())
    assert recorder.main(["check", "--record", str(pilot)]) == 0


def test_a_placeholder_decision_time_is_refused(tmp_path, capsys) -> None:
    """`go-no-go.json` ships `approved_at: "PENDING-GATE-RUN"`.

    That value reaches `SignOff.decided_at` through `import_go_no_go()`, and the
    validator used to accept any non-empty string. A decision time that is present
    but is not a time is a malformed record, so it is now refused.
    """
    record = _write(tmp_path / "pilot.json", **_complete(decided_at="PENDING-GATE-RUN"))
    assert recorder.main(["check", "--record", str(record)]) == 1
    out = " ".join(capsys.readouterr().out.split())
    assert "is not an ISO-8601 timestamp" in out

    # An empty decision time stays valid: nothing decided, nothing to be wrong.
    assert signoff.validate_signoff(signoff.SignOff(state="internal_review"))[0] is True


def test_check_refuses_a_record_that_is_not_a_json_object(tmp_path) -> None:
    record = tmp_path / "not.json"
    record.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        recorder.main(["check", "--record", str(record)])
    assert "not a JSON object" in str(excinfo.value)


def test_check_passing_never_reads_as_a_legitimate_approval(tmp_path, capsys) -> None:
    """A well-formed record is not a verified one, and must say so."""
    record = _write(tmp_path / "pilot.json", **_complete())
    assert recorder.main(["check", "--record", str(record)]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "Well-formed is not the same as legitimate" in out
    assert "does not verify that the named human" in out

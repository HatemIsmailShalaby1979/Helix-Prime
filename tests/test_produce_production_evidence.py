"""The producer side of the production evidence path (B1.1).

`release/production_evidence.py` verifies; `scripts/produce_production_evidence.py`
produces. These tests pin the properties that make the producer safe to hand to an
external party:

* it refuses to sign a document the gate would reject, so it cannot manufacture
  evidence;
* it refuses to write key material or evidence inside the repository, because the
  attested system must not hold what attests it;
* a document it produces is one the gate actually reads — asserted through
  `check_gate_evidence`, not through the tool's own opinion of its output;
* a passing check never reads as an approval.

The signing round trip needs openssl, which is part of the release toolchain
(`release/manifest.py` already shells out to git the same way). Only those tests
skip when it is absent.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil

import pytest

from release import production_evidence as pe

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "produce_production_evidence.py"
GATE = "security_review"
OTHER_GATE = "operational_ownership"


def _load_producer():
    spec = importlib.util.spec_from_file_location("_produce_production_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = _load_producer()

needs_openssl = pytest.mark.skipif(
    shutil.which("openssl") is None,
    reason="openssl is required to sign and is part of the release toolchain",
)


def _fill(document: pathlib.Path, **overrides) -> None:
    data = json.loads(document.read_text(encoding="utf-8"))
    data.update(
        {
            "issuer": "Example Assurance LLP",
            "issued_at": "2026-09-20T10:00:00+00:00",
            "expires_at": "2027-09-20T10:00:00+00:00",
            "payload": {"note": "synthetic test content"},
        }
    )
    data.update(overrides)
    document.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _keypair(directory: pathlib.Path) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    assert producer.main(["init-key", "--dir", str(directory), "--bits", "2048"]) == 0
    return directory / "evidence.key"


# ── the gate list ──────────────────────────────────────────────────────────


def test_gates_lists_every_production_only_gate(capsys) -> None:
    assert producer.main(["gates"]) == 0
    out = capsys.readouterr().out
    for gate in pe.REQUIRED_EVIDENCE:
        assert gate in out


# ── refusals: nothing sensitive or fabricated ──────────────────────────────


def test_init_key_refuses_to_write_inside_the_repository() -> None:
    target = ROOT / "not-a-real-keys-dir"
    with pytest.raises(SystemExit) as excinfo:
        producer.main(["init-key", "--dir", str(target)])
    assert "inside the repository" in str(excinfo.value)
    assert not target.exists(), "the refusal must happen before anything is written"


def test_template_refuses_to_write_inside_the_repository() -> None:
    target = ROOT / "not-a-real-draft.evidence.json"
    with pytest.raises(SystemExit) as excinfo:
        producer.main(["template", "--gate", GATE, "--out", str(target)])
    assert "inside the repository" in str(excinfo.value)
    assert not target.exists()


def test_template_rejects_a_gate_that_is_not_production_only(tmp_path) -> None:
    target = tmp_path / "nope.evidence.json"
    with pytest.raises(SystemExit) as excinfo:
        producer.main(["template", "--gate", "repository_state", "--out", str(target)])
    assert "not a production-only gate" in str(excinfo.value)
    assert not target.exists()


def test_a_template_is_not_a_valid_document_until_a_human_fills_it(tmp_path, capsys) -> None:
    """The anti-fabrication property: the tool cannot emit ready-made evidence.

    A fresh template must fail the very contract the gate enforces. If this ever
    passes with an empty template, the tool has started inventing the fields that
    are supposed to come from a person.
    """
    document = tmp_path / "security_review.evidence.json"
    assert producer.main(["template", "--gate", GATE, "--out", str(document)]) == 0

    ok, reason = pe.validate_claims(GATE, json.loads(document.read_text(encoding="utf-8")))
    assert ok is False
    assert "no issuer" in reason

    _fill(document)
    ok, _ = pe.validate_claims(GATE, json.loads(document.read_text(encoding="utf-8")))
    assert ok is True


def test_sign_refuses_a_document_the_gate_would_reject(tmp_path) -> None:
    """The tool must not be usable to manufacture evidence.

    A signature would only make an invalid document harder to fix, so the refusal
    happens before openssl is invoked — which is why a placeholder key is enough
    to prove it.
    """
    document = tmp_path / "security_review.evidence.json"
    assert producer.main(["template", "--gate", GATE, "--out", str(document)]) == 0
    placeholder_key = tmp_path / "evidence.key"
    placeholder_key.write_text("not a key, and never read", encoding="utf-8")

    assert producer.main(["sign", "--document", str(document), "--key", str(placeholder_key)]) == 1
    assert not pathlib.Path(str(document) + ".sig").exists()


# ── the round trip ─────────────────────────────────────────────────────────


@needs_openssl
def test_a_produced_document_is_one_the_gate_reads(tmp_path, monkeypatch) -> None:
    """End to end, asserted through the gate rather than through this tool.

    The point is not that `check` is happy with its own output — it is that
    `check_gate_evidence`, the function the nine production gates call, turns
    green. Anything less would be the tool agreeing with itself.
    """
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    key = _keypair(tmp_path / "keys")
    document = evidence / f"{GATE}.evidence.json"

    assert producer.main(["template", "--gate", GATE, "--out", str(document)]) == 0
    _fill(document)
    assert producer.main(["sign", "--document", str(document), "--key", str(key)]) == 0
    assert pathlib.Path(str(document) + ".sig").exists()

    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_DIR", str(evidence))
    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", str(tmp_path / "keys" / "evidence.pub"))

    assert producer.main(["check", "--document", str(document)]) == 0

    ok, reason = pe.check_gate_evidence(GATE)
    assert ok is True, reason
    assert "Example Assurance LLP" in reason

    # And a gate whose document is absent is still refused, so producing one
    # document cannot be mistaken for satisfying the set.
    other_ok, other_reason = pe.check_gate_evidence(OTHER_GATE)
    assert other_ok is False
    assert "not present" in other_reason


@needs_openssl
def test_a_tampered_document_does_not_verify(tmp_path, monkeypatch, capsys) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    key = _keypair(tmp_path / "keys")
    document = evidence / f"{GATE}.evidence.json"

    producer.main(["template", "--gate", GATE, "--out", str(document)])
    _fill(document)
    assert producer.main(["sign", "--document", str(document), "--key", str(key)]) == 0

    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", str(tmp_path / "keys" / "evidence.pub"))
    _fill(document, issuer="Forged LLP")
    assert producer.main(["check", "--document", str(document)]) == 1
    assert "DOES NOT VERIFY" in capsys.readouterr().out


@needs_openssl
def test_a_passing_check_never_reads_as_an_approval(tmp_path, monkeypatch, capsys) -> None:
    """A green check is a statement about form, and must say so.

    This is the failure mode worth guarding: an operator sees exit 0, concludes
    production is approved, and stops. The output has to refuse that reading.
    """
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    key = _keypair(tmp_path / "keys")
    document = evidence / f"{GATE}.evidence.json"

    producer.main(["template", "--gate", GATE, "--out", str(document)])
    _fill(document)
    assert producer.main(["sign", "--document", str(document), "--key", str(key)]) == 0

    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", str(tmp_path / "keys" / "evidence.pub"))
    assert producer.main(["check", "--document", str(document)]) == 0
    # Flattened, because these sentences wrap across printed lines.
    flat = " ".join(capsys.readouterr().out.split())
    assert "not an approval" in flat
    assert "does not make production ready" in flat
    assert "production_approved" in flat


# ── status ─────────────────────────────────────────────────────────────────


def test_status_is_red_and_says_so_with_nothing_declared(monkeypatch, capsys) -> None:
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_DIR", raising=False)
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", raising=False)

    assert producer.main(["status"]) == 1
    out = capsys.readouterr().out
    assert f"0 of {len(pe.REQUIRED_EVIDENCE)}" in out
    assert "reports evidence, not approval" in out

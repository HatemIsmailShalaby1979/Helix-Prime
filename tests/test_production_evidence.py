"""Tests for the external production-evidence reader (B1.1).

Two things are being pinned, and they are different.

**The verifier works.** `tests/fixtures/production_evidence/` holds a synthetic
security review signed by a throwaway RSA key — the signature was produced by
`openssl dgst -sha256 -sign`, not by this repo's own code, so a passing test is an
independent implementation agreeing rather than a module agreeing with itself.
The fixture's validity window is frozen and the tests pass an explicit ``now``, so
the suite neither expires nor depends on the wall clock.

**The refusals are real.** Every claim check gets its own test that fails for its
own reason, and each asserts on the *reason text*, so a blanket ``return False``
could not pass them. Those tests stub the signature check on purpose: they are
about the document, not the crypto, and isolating the crypto is what lets each one
fail for exactly one cause.

Fail-closed is the default this whole module exists to preserve: with nothing
declared in the environment, every production-only gate still refuses.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import shutil
import subprocess

import pytest

from release import production_evidence, profiles

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "production_evidence"
#: Inside the fixture's 2026-01-01 .. 2030-01-01 validity window, so the fixture
#: never expires and the assertions never depend on today's date.
FROZEN_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
GATE = "security_review"


def _install(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Copy the signed fixture into a fresh evidence dir. Returns (dir, key)."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    shutil.copy(FIXTURES / f"{GATE}.evidence.json", evidence / f"{GATE}.evidence.json")
    shutil.copy(FIXTURES / f"{GATE}.evidence.json.sig", evidence / f"{GATE}.evidence.json.sig")
    key = tmp_path / "auditor_pub.pem"
    shutil.copy(FIXTURES / "test_pub.pem", key)
    return evidence, key


def _declare(monkeypatch, evidence: pathlib.Path, key: pathlib.Path) -> None:
    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_DIR", str(evidence))
    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", str(key))


@pytest.fixture()
def stubbed(monkeypatch, tmp_path):
    """A declared, well-formed evidence dir with the signature check stubbed out.

    Returns a callable that rewrites the document and re-runs the check, so each
    claim test changes exactly one field.
    """
    evidence, key = _install(tmp_path)
    _declare(monkeypatch, evidence, key)
    monkeypatch.setattr(production_evidence, "verify_detached_signature", lambda *a, **k: True)

    def check(document, gate: str = GATE, now: datetime.datetime | None = None):
        (evidence / f"{gate}.evidence.json").write_text(json.dumps(document), encoding="utf-8")
        (evidence / f"{gate}.evidence.json.sig").write_bytes(b"stubbed")
        return production_evidence.check_gate_evidence(gate, now=now or FROZEN_NOW)

    return check


def _valid_document() -> dict:
    return {
        "gate": GATE,
        "evidence_type": production_evidence.REQUIRED_EVIDENCE[GATE],
        "issuer": "Example Assurance LLP",
        "scope": "production",
        "issued_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2030-01-01T00:00:00+00:00",
    }


# ── the default this module exists to preserve ──────────────────────────────


def test_the_table_covers_every_production_only_gate():
    """A gate added to profiles without evidence declared here would be a gap."""
    assert set(production_evidence.REQUIRED_EVIDENCE) == set(profiles.PRODUCTION_ONLY_GATES)


def test_every_production_gate_refuses_when_nothing_is_declared(monkeypatch):
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_DIR", raising=False)
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", raising=False)
    for gate in profiles.PRODUCTION_ONLY_GATES:
        ok, reason = production_evidence.check_gate_evidence(gate)
        assert ok is False, f"{gate} must stay fail-closed with no evidence declared"
        assert "no evidence declared" in reason


def test_a_gate_that_is_not_production_only_is_refused():
    ok, reason = production_evidence.check_gate_evidence("repository_state")
    assert ok is False
    assert "not a production-only gate" in reason


# ── the verifier, against a signature this repo did not produce ─────────────


def test_a_genuine_openssl_signature_is_accepted(monkeypatch, tmp_path):
    evidence, key = _install(tmp_path)
    _declare(monkeypatch, evidence, key)
    ok, reason = production_evidence.check_gate_evidence(GATE, now=FROZEN_NOW)
    assert ok is True, reason
    assert "Example Assurance LLP" in reason


def test_a_tampered_document_is_rejected(monkeypatch, tmp_path):
    """One extra byte is enough: the signature covers the exact bytes."""
    evidence, key = _install(tmp_path)
    _declare(monkeypatch, evidence, key)
    document = evidence / f"{GATE}.evidence.json"
    document.write_bytes(document.read_bytes() + b" ")
    ok, reason = production_evidence.check_gate_evidence(GATE, now=FROZEN_NOW)
    assert ok is False
    assert "signature does not verify" in reason


def test_a_signature_from_another_key_is_rejected(monkeypatch, tmp_path):
    evidence, key = _install(tmp_path)
    _declare(monkeypatch, evidence, key)
    # A second, unrelated key: the fixture signature must not verify against it.
    other = tmp_path / "other_pub.pem"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(tmp_path / "other.pem"),
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(tmp_path / "other.pem"), "-pubout", "-out", str(other)],
        capture_output=True,
        check=True,
    )
    ok, reason = production_evidence.check_gate_evidence(GATE, now=FROZEN_NOW)
    assert ok is True  # sanity: the real key still works

    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", str(other))
    ok, reason = production_evidence.check_gate_evidence(GATE, now=FROZEN_NOW)
    assert ok is False
    assert "signature does not verify" in reason


# ── declaration and layout failures ─────────────────────────────────────────


def test_a_missing_evidence_directory_is_refused(monkeypatch, tmp_path):
    _declare(monkeypatch, tmp_path / "nope", tmp_path / "k.pem")
    ok, reason = production_evidence.check_gate_evidence(GATE)
    assert ok is False
    assert "not found" in reason


def test_an_undeclared_verification_key_is_refused(monkeypatch, tmp_path):
    evidence, _key = _install(tmp_path)
    monkeypatch.setenv("HELIX_PRODUCTION_EVIDENCE_DIR", str(evidence))
    monkeypatch.delenv("HELIX_PRODUCTION_EVIDENCE_PUBKEY", raising=False)
    ok, reason = production_evidence.check_gate_evidence(GATE)
    assert ok is False
    assert "no verification key declared" in reason


def test_an_unreadable_verification_key_is_refused(monkeypatch, tmp_path):
    evidence, _key = _install(tmp_path)
    _declare(monkeypatch, evidence, tmp_path / "absent_key.pem")
    ok, reason = production_evidence.check_gate_evidence(GATE)
    assert ok is False
    assert "unreadable" in reason


def test_absent_evidence_names_the_evidence_type(monkeypatch, tmp_path):
    evidence, key = _install(tmp_path)
    (evidence / f"{GATE}.evidence.json").unlink()
    _declare(monkeypatch, evidence, key)
    ok, reason = production_evidence.check_gate_evidence(GATE)
    assert ok is False
    assert "not present" in reason
    assert production_evidence.REQUIRED_EVIDENCE[GATE] in reason


def test_unsigned_evidence_is_refused(monkeypatch, tmp_path):
    evidence, key = _install(tmp_path)
    (evidence / f"{GATE}.evidence.json.sig").unlink()
    _declare(monkeypatch, evidence, key)
    ok, reason = production_evidence.check_gate_evidence(GATE)
    assert ok is False
    assert "unsigned" in reason


# ── claim checks: each must be able to fail on its own ──────────────────────


def test_a_document_for_another_gate_is_refused(stubbed):
    document = _valid_document() | {"gate": "legal_privacy_review"}
    ok, reason = stubbed(document)
    assert ok is False
    assert "evidence is for gate" in reason


def test_a_mismatched_evidence_type_is_refused(stubbed):
    ok, reason = stubbed(_valid_document() | {"evidence_type": "a self-assessment"})
    assert ok is False
    assert "evidence type" in reason


def test_a_missing_issuer_is_refused(stubbed):
    ok, reason = stubbed(_valid_document() | {"issuer": "   "})
    assert ok is False
    assert "no issuer" in reason


def test_a_non_production_scope_is_refused(stubbed):
    """A pilot or rehearsal must not satisfy a production gate."""
    ok, reason = stubbed(_valid_document() | {"scope": "controlled_pilot"})
    assert ok is False
    assert "scope" in reason


def test_expired_evidence_is_refused(stubbed):
    after = datetime.datetime(2031, 1, 1, tzinfo=datetime.timezone.utc)
    ok, reason = stubbed(_valid_document(), now=after)
    assert ok is False
    assert "expired" in reason


def test_evidence_issued_in_the_future_is_refused(stubbed):
    """A clock is not a signature problem, so a future issue date is not trusted."""
    before = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    ok, reason = stubbed(_valid_document(), now=before)
    assert ok is False
    assert "in the future" in reason


def test_a_timestamp_without_a_timezone_is_refused(stubbed):
    ok, reason = stubbed(_valid_document() | {"issued_at": "2026-01-01T00:00:00"})
    assert ok is False
    assert "no timezone offset" in reason


def test_an_unparseable_timestamp_is_refused(stubbed):
    ok, reason = stubbed(_valid_document() | {"expires_at": "soon"})
    assert ok is False
    assert "not an ISO-8601 timestamp" in reason


def test_a_missing_timestamp_is_refused(stubbed):
    document = _valid_document()
    del document["expires_at"]
    ok, reason = stubbed(document)
    assert ok is False
    assert "expires_at is missing" in reason


def test_a_document_that_is_not_json_is_refused(monkeypatch, tmp_path):
    evidence, key = _install(tmp_path)
    _declare(monkeypatch, evidence, key)
    monkeypatch.setattr(production_evidence, "verify_detached_signature", lambda *a, **k: True)
    (evidence / f"{GATE}.evidence.json").write_bytes(b"{not json")
    (evidence / f"{GATE}.evidence.json.sig").write_bytes(b"stubbed")
    ok, reason = production_evidence.check_gate_evidence(GATE, now=FROZEN_NOW)
    assert ok is False
    assert "not readable JSON" in reason


# ── the verifier itself, on inputs openssl did not produce ──────────────────


def test_a_valid_document_survives_a_real_re_signature(tmp_path):
    """Interop the other way: this repo's key material is not special.

    A fresh key and a fresh document, signed by openssl and verified here. Skipped
    only where openssl is genuinely absent, which is not the CI image.
    """
    if shutil.which("openssl") is None:
        pytest.skip("openssl not available")

    private = tmp_path / "fresh_priv.pem"
    public = tmp_path / "fresh_pub.pem"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private),
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
        capture_output=True,
        check=True,
    )
    document = tmp_path / "fresh.evidence.json"
    document.write_bytes(json.dumps(_valid_document(), indent=2).encode("utf-8"))
    signature = tmp_path / "fresh.evidence.json.sig"
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private),
            "-out",
            str(signature),
            str(document),
        ],
        capture_output=True,
        check=True,
    )

    pem = public.read_text(encoding="utf-8")
    assert production_evidence.verify_detached_signature(
        pem, document.read_bytes(), signature.read_bytes()
    )
    assert not production_evidence.verify_detached_signature(
        pem, document.read_bytes() + b"x", signature.read_bytes()
    )


@pytest.mark.parametrize(
    "pem",
    [
        "",
        "not a pem at all",
        "-----BEGIN PUBLIC KEY-----\nZm9v\n-----END PUBLIC KEY-----\n",
        "-----BEGIN RSA PUBLIC KEY-----\nMIIBCgKCAQEA\n-----END RSA PUBLIC KEY-----\n",
    ],
)
def test_malformed_key_material_is_refused_without_raising(pem):
    assert production_evidence.verify_detached_signature(pem, b"message", b"\x00" * 256) is False


def test_a_wrong_length_signature_is_refused():
    pem = (FIXTURES / "test_pub.pem").read_text(encoding="utf-8")
    assert production_evidence.verify_detached_signature(pem, b"message", b"\x01" * 255) is False

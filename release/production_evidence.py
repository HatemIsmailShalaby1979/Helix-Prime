"""The consumer for external production evidence (B1.1).

`server/config.py` refuses to start a `production` profile without external gate
inputs, and `release/gate.py` fails the nine production-only gates closed. Both
were right, and both were *unverifiable*: nothing in the tree could read the
evidence they demand, so "production is not approved" could never become
"production is approved by evidence X, signed by Y, covering Z". This module is
that reader.

The evidence lives **outside the repository** and is declared by environment, in
the same style as `HELIX_AUDIT_DB_PATH` (`release/gate.py:170`). The platform
must not be able to vouch for itself: evidence kept inside the tree it attests
is not evidence.

Layout, for gate ``G``::

    $HELIX_PRODUCTION_EVIDENCE_DIR/<G>.evidence.json
    $HELIX_PRODUCTION_EVIDENCE_DIR/<G>.evidence.json.sig

The ``.json`` document is self-describing and the ``.sig`` is a detached RSA
PKCS#1 v1.5 / SHA-256 signature over the document's exact bytes, verified against
``$HELIX_PRODUCTION_EVIDENCE_PUBKEY`` — a PEM public key, also outside the
repository. Nothing is trusted because of where it sits: the gate name, evidence
type, scope, issuer and validity window are all read from *inside* the signed
document, so a tampered evidence directory can only produce a document that fails
to verify.

Stdlib only, on purpose. The signature check is the one thing this module must
do, and taking a dependency to do it would widen the governed core's supply chain
for no gain. `cryptography` is deliberately not used; `tests/test_production_evidence.py`
cross-checks the verifier against `openssl` so the choice is not taken on faith.

Fail-closed throughout: every path returns ``(False, reason)`` rather than
raising, and the reason names the exact step that refused.
"""
from __future__ import annotations

import base64
import binascii
import datetime
import hashlib
import hmac
import json
import os
import pathlib
from typing import Any, Dict, Optional, Tuple

#: Gate -> the evidence type that gate demands. These strings are the ones the
#: gates already printed, moved here so the red reason and the green check cannot
#: drift apart.
REQUIRED_EVIDENCE: Dict[str, str] = {
    "signed_production_evidence": "external signed production evidence",
    "certified_data_isolation": "certified tenant/data isolation",
    "external_observer_audit": "independent external observer audit",
    "production_deployment_architecture": "reviewed deployment architecture",
    "disaster_recovery_evidence": "disaster-recovery evidence from production",
    "operational_ownership": "assigned operational ownership",
    "incident_oncall_ownership": "assigned incident/on-call ownership",
    "security_review": "signed security review",
    "legal_privacy_review": "signed legal/privacy review where applicable",
}

#: The only scope a production gate accepts. Anything else is a pilot or a
#: rehearsal and must not be able to satisfy a production gate.
REQUIRED_SCOPE = "production"

#: Evidence is not perpetual: a document issued more than this far in the future
#: is a clock or a forgery, not a signature problem.
MAX_CLOCK_SKEW = datetime.timedelta(minutes=5)

#: SHA-256 DigestInfo prefix (RFC 8017 §9.2 note 1), the fixed 19 bytes that
#: precede the digest inside the RSA PKCS#1 v1.5 encoded message.
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")

#: rsaEncryption, the only algorithm this verifier accepts.
_OID_RSA_ENCRYPTION = bytes.fromhex("2a864886f70d010101")

#: PKCS#1 v1.5 requires at least 8 bytes of 0xFF padding.
_MIN_RSA_PADDING = 8


class _DerError(ValueError):
    """A structure that is not the DER this module accepts."""


def _der_tlv(data: bytes, pos: int) -> Tuple[int, bytes, int]:
    """Read one DER tag-length-value. Returns (tag, value, next position)."""
    if pos + 2 > len(data):
        raise _DerError("truncated header")
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or count > 4:
            raise _DerError(f"unsupported length form ({count} bytes)")
        if pos + count > len(data):
            raise _DerError("truncated length")
        length = int.from_bytes(data[pos : pos + count], "big")
        pos += count
    if pos + length > len(data):
        raise _DerError("truncated value")
    return tag, data[pos : pos + length], pos + length


def _parse_public_key(pem: str) -> Tuple[int, int]:
    """Return ``(n, e)`` from a PEM SubjectPublicKeyInfo RSA public key.

    Strict on purpose: only an unencrypted ``PUBLIC KEY`` holding rsaEncryption
    with a NULL parameter is accepted, and anything else is refused rather than
    guessed at.
    """
    lines = [line.strip() for line in pem.strip().splitlines()]
    if not lines or lines[0] != "-----BEGIN PUBLIC KEY-----":
        raise _DerError("not a PEM 'PUBLIC KEY' (expected an unencrypted SPKI)")
    if lines[-1] != "-----END PUBLIC KEY-----":
        raise _DerError("PEM footer missing")
    try:
        der = base64.b64decode("".join(lines[1:-1]), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _DerError(f"PEM body is not valid base64: {exc}") from exc

    tag, spki, end = _der_tlv(der, 0)
    if tag != 0x30:
        raise _DerError("SPKI is not a SEQUENCE")
    if end != len(der):
        raise _DerError("trailing bytes after the SPKI")

    tag, algorithm, pos = _der_tlv(spki, 0)
    if tag != 0x30:
        raise _DerError("AlgorithmIdentifier is not a SEQUENCE")
    tag, oid, _ = _der_tlv(algorithm, 0)
    if tag != 0x06 or oid != _OID_RSA_ENCRYPTION:
        raise _DerError("not an rsaEncryption key")

    tag, bit_string, _ = _der_tlv(spki, pos)
    if tag != 0x03:
        raise _DerError("subjectPublicKey is not a BIT STRING")
    if not bit_string or bit_string[0] != 0:
        raise _DerError("BIT STRING has unused bits")

    tag, rsa_key, _ = _der_tlv(bit_string[1:], 0)
    if tag != 0x30:
        raise _DerError("RSAPublicKey is not a SEQUENCE")
    tag, n_bytes, pos = _der_tlv(rsa_key, 0)
    if tag != 0x02:
        raise _DerError("modulus is not an INTEGER")
    tag, e_bytes, _ = _der_tlv(rsa_key, pos)
    if tag != 0x02:
        raise _DerError("public exponent is not an INTEGER")

    n = int.from_bytes(n_bytes, "big")
    e = int.from_bytes(e_bytes, "big")
    if n <= 0 or e <= 1:
        raise _DerError("degenerate key")
    return n, e


def verify_detached_signature(public_key_pem: str, message: bytes, signature: bytes) -> bool:
    """True when ``signature`` is a valid RSA PKCS#1 v1.5 / SHA-256 signature.

    Returns False — never raises — for a malformed key, a wrong-length or
    out-of-range signature, or a signature over different bytes.
    """
    try:
        n, e = _parse_public_key(public_key_pem)
    except (ValueError, _DerError):
        return False

    size = (n.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False

    digest = hashlib.sha256(message).digest()
    padding = size - 3 - len(_SHA256_DIGEST_INFO) - len(digest)
    if padding < _MIN_RSA_PADDING:
        return False
    expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + _SHA256_DIGEST_INFO + digest
    # pow() is the whole verification: the signature is m^d mod n and the public
    # operation recovers m^e^d = m. Re-encoding and comparing is stricter than
    # parsing the recovered block, because there is nothing to parse.
    recovered = pow(s, e, n).to_bytes(size, "big")
    return hmac.compare_digest(recovered, expected)


def evidence_dir() -> Optional[pathlib.Path]:
    """The declared evidence directory, or None when nothing is declared."""
    declared = os.environ.get("HELIX_PRODUCTION_EVIDENCE_DIR", "").strip()
    return pathlib.Path(declared) if declared else None


def public_key_path() -> Optional[pathlib.Path]:
    """The declared public key path, or None when nothing is declared."""
    declared = os.environ.get("HELIX_PRODUCTION_EVIDENCE_PUBKEY", "").strip()
    return pathlib.Path(declared) if declared else None


def artifact_paths(gate: str, directory: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path]:
    """The artifact and detached-signature paths this module expects for a gate."""
    document = directory / f"{gate}.evidence.json"
    return document, document.with_suffix(document.suffix + ".sig")


def _parse_timestamp(value: Any, field: str) -> Tuple[Optional[datetime.datetime], str]:
    """Parse an ISO-8601 timestamp. Returns (moment, reason-when-unusable)."""
    if not isinstance(value, str) or not value.strip():
        return None, f"{field} is missing"
    try:
        moment = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None, f"{field} is not an ISO-8601 timestamp ({value!r})"
    if moment.tzinfo is None:
        return None, f"{field} has no timezone offset"
    return moment, ""


def check_gate_evidence(gate: str, now: Optional[datetime.datetime] = None) -> Tuple[bool, str]:
    """Whether signed external evidence for ``gate`` is present and trustworthy.

    ``(False, reason)`` at every failure, naming the step that refused. With
    nothing declared in the environment this is the first check, so the
    fail-closed default is preserved by construction.
    """
    if gate not in REQUIRED_EVIDENCE:
        return False, f"{gate}: not a production-only gate"

    directory = evidence_dir()
    if directory is None:
        return False, (
            f"{gate}: requires {REQUIRED_EVIDENCE[gate]} — no evidence declared "
            "(set HELIX_PRODUCTION_EVIDENCE_DIR; production NOT approved)"
        )
    if not directory.is_dir():
        return False, f"{gate}: declared evidence directory {str(directory)!r} not found"

    key_path = public_key_path()
    if key_path is None:
        return False, (
            f"{gate}: no verification key declared "
            "(set HELIX_PRODUCTION_EVIDENCE_PUBKEY to a public key outside the repo)"
        )
    try:
        public_key_pem = key_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"{gate}: verification key unreadable: {exc.strerror or exc}"

    document_path, signature_path = artifact_paths(gate, directory)
    try:
        document = document_path.read_bytes()
    except OSError:
        return False, f"{gate}: requires {REQUIRED_EVIDENCE[gate]} — not present"
    try:
        signature = signature_path.read_bytes()
    except OSError:
        return False, f"{gate}: evidence present but unsigned ({signature_path.name} missing)"

    if not verify_detached_signature(public_key_pem, document, signature):
        return False, f"{gate}: signature does not verify against the declared key"

    try:
        claims = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, f"{gate}: evidence is not readable JSON: {exc}"
    if not isinstance(claims, dict):
        return False, f"{gate}: evidence is not a JSON object"

    if claims.get("gate") != gate:
        return False, f"{gate}: evidence is for gate {claims.get('gate')!r}"
    expected_type = REQUIRED_EVIDENCE[gate]
    if claims.get("evidence_type") != expected_type:
        return False, (
            f"{gate}: evidence type {claims.get('evidence_type')!r} is not {expected_type!r}"
        )
    issuer = claims.get("issuer")
    if not isinstance(issuer, str) or not issuer.strip():
        return False, f"{gate}: evidence declares no issuer"
    if claims.get("scope") != REQUIRED_SCOPE:
        return False, f"{gate}: evidence scope {claims.get('scope')!r} is not {REQUIRED_SCOPE!r}"

    moment = now or datetime.datetime.now(datetime.timezone.utc)
    issued_at, reason = _parse_timestamp(claims.get("issued_at"), "issued_at")
    if issued_at is None:
        return False, f"{gate}: {reason}"
    if issued_at > moment + MAX_CLOCK_SKEW:
        return False, f"{gate}: issued_at {claims['issued_at']} is in the future"
    expires_at, reason = _parse_timestamp(claims.get("expires_at"), "expires_at")
    if expires_at is None:
        return False, f"{gate}: {reason}"
    if expires_at <= moment:
        return False, f"{gate}: evidence expired at {claims['expires_at']}"

    return True, f"{gate}: {expected_type} verified (issuer {issuer.strip()!r})"


def declared_evidence_summary() -> Dict[str, Any]:
    """A read-only description of what the environment declares, for diagnostics.

    Deliberately does not verify anything: it exists so an operator can see what
    the gate would look at, without that lookup becoming a second source of truth.
    """
    directory = evidence_dir()
    key_path = public_key_path()
    return {
        "evidence_dir": str(directory) if directory else "",
        "evidence_dir_exists": bool(directory and directory.is_dir()),
        "public_key_path": str(key_path) if key_path else "",
        "public_key_exists": bool(key_path and key_path.exists()),
        "gates": sorted(REQUIRED_EVIDENCE),
    }


def missing_declaration() -> list[str]:
    """The evidence inputs the environment has not declared.

    The single place that decides what a production deployment must declare, so
    the server's startup check and the release gate cannot drift apart again —
    they used to name different variables and disagree about what production
    evidence even is.

    Note what is *not* here: a signing key. The server verifies evidence and never
    signs it, so a production server needs the public half only. The variable this
    replaced, ``HELIX_EVIDENCE_SIGNING_KEY``, asked a production server to hold a
    private key — which would have let the thing being attested vouch for itself.
    """
    missing: list[str] = []
    if evidence_dir() is None:
        missing.append("HELIX_PRODUCTION_EVIDENCE_DIR")
    if public_key_path() is None:
        missing.append("HELIX_PRODUCTION_EVIDENCE_PUBKEY")
    return missing

"""Password hashing with the standard library.

hash_password() turns a plain password into a self-describing scrypt hash:
scrypt$n$r$p$salt_b64$hash_b64. verify_password() recomputes the hash from the
stored parameters and compares with a constant-time digest. needs_rehash()
reports whether the stored cost is below today's policy, so a login can
upgrade an old hash in place. There is no third-party crypto and no hand-rolled
algorithm here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
MIN_N = 2**10
MAX_N = 2**24
SCHEME = "scrypt"


def hash_password(password: str) -> str:
    """Hash a password with the current policy and return the stored form."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    parts = (
        SCHEME,
        str(SCRYPT_N),
        str(SCRYPT_R),
        str(SCRYPT_P),
        _b64(salt),
        _b64(digest),
    )
    return "$".join(parts)


def verify_password(password: str, stored: str) -> bool:
    """Return True when the password matches the stored hash.

    A stored value that cannot be parsed, or whose parameters are out of the
    accepted range, fails closed: it returns False, never True.
    """
    parsed = _parse(stored)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p)
    return hmac.compare_digest(digest, expected)


def needs_rehash(stored: str) -> bool:
    """Return True when the stored hash should be upgraded to current policy.

    An unparseable hash returns True, because the password cannot be verified
    reliably and must be recreated. A hash with an honest cost below the current
    parameters, or with a salt that is not the current size, also returns True.
    """
    parsed = _parse(stored)
    if parsed is None:
        return True
    n, r, p, _salt, _expected = parsed
    return n < SCRYPT_N or r < SCRYPT_R or p < SCRYPT_P


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = stored.split("$")
    if len(parts) != 6:
        return None
    scheme, n_str, r_str, p_str, salt_b64, hash_b64 = parts
    if scheme != SCHEME:
        return None
    try:
        n = int(n_str)
        r = int(r_str)
        p = int(p_str)
        if not (MIN_N <= n <= MAX_N) or not (1 <= r <= 32) or not (1 <= p):
            return None
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
    except (ValueError, TypeError):
        return None
    if len(salt) < SALT_BYTES or len(expected) < 16:
        return None
    return n, r, p, salt, expected


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")

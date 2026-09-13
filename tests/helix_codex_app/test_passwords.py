"""Password hashing tests for helix_codex_app/security/passwords.py."""
from __future__ import annotations

import pytest

from helix_codex_app.security import passwords


def test_correct_password_verifies() -> None:
    stored = passwords.hash_password("correct horse battery staple")
    assert stored.startswith("scrypt$")
    assert passwords.verify_password("correct horse battery staple", stored)


def test_wrong_password_does_not_verify() -> None:
    stored = passwords.hash_password("correct horse battery staple")
    assert not passwords.verify_password("wrong password", stored)


def test_tampered_hash_does_not_verify() -> None:
    stored = passwords.hash_password("correct horse battery staple")
    parts = stored.split("$")
    parts[-1] = parts[-1][:-2] + ("AA" if not parts[-1].endswith("AA") else "BB")
    tampered = "$".join(parts)
    assert not passwords.verify_password("correct horse battery staple", tampered)


def test_tampered_salt_does_not_verify() -> None:
    stored = passwords.hash_password("correct horse battery staple")
    parts = stored.split("$")
    parts[-2] = parts[-2][:-2] + ("AA" if not parts[-2].endswith("AA") else "BB")
    tampered = "$".join(parts)
    assert not passwords.verify_password("correct horse battery staple", tampered)


def test_unparseable_stored_hash_fails_closed() -> None:
    assert not passwords.verify_password("anything", "not-a-hash")
    assert not passwords.verify_password("anything", "scrypt$nope")
    assert not passwords.verify_password("anything", "")


@pytest.mark.parametrize(
    "stored",
    [
        "scrypt$100$8$1$c2FsdA==$aGFzaA==",
        "scrypt$16384$8$1$c2FsdA==$aGFzaA==",
        "bcrypt$16384$8$1$c2FsdA==$aGFzaA==",
        "scrypt$16384$8$1$notbase64!!$aGFzaA==",
    ],
)
def test_malformed_stored_hash_never_verifies(stored: str) -> None:
    assert not passwords.verify_password("anything", stored)


def test_needs_rehash_true_for_weaker_stored_cost() -> None:
    stored = passwords.hash_password("correct horse battery staple")
    parts = stored.split("$")
    parts[1] = str(passwords.SCRYPT_N // 2)
    weaker = "$".join(parts)
    assert passwords.needs_rehash(weaker)


def test_needs_rehash_false_for_current_cost() -> None:
    stored = passwords.hash_password("correct horse battery staple")
    assert not passwords.needs_rehash(stored)


def test_needs_rehash_true_for_unparseable() -> None:
    assert passwords.needs_rehash("garbage")
    assert passwords.needs_rehash("")


def test_hashes_are_unique_per_call() -> None:
    stored_a = passwords.hash_password("same password")
    stored_b = passwords.hash_password("same password")
    assert stored_a != stored_b


def test_needs_rehash_true_when_salt_shorter_than_policy() -> None:
    stored = passwords.hash_password("correct horse battery staple")
    parts = stored.split("$")
    short_salt = passwords._b64(b"\x00" * 8)
    parts[-2] = short_salt
    short_salt_hash = "$".join(parts)
    assert passwords.needs_rehash(short_salt_hash)

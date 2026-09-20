# Production-evidence test fixtures

Synthetic evidence for `tests/test_production_evidence.py` and the red/green pair
in `tests/test_pilot_readiness.py`.

Each `<gate>.evidence.json` is a well-formed evidence document for one of the nine
production-only gates, and `<gate>.evidence.json.sig` is a detached RSA PKCS#1
v1.5 / SHA-256 signature over that document's exact bytes.

**No private key is committed.** `test_pub.pem` is the public half of a throwaway
keypair generated outside this repository; only the signatures it produced are
kept here. That is deliberate — a committed private key, even a test one, is the
pattern that ends up in a real leak.

The signatures were produced by `openssl`, not by this repository's own code, so a
passing test is an independent implementation agreeing rather than the verifier
agreeing with itself:

```
openssl dgst -sha256 -sign <throwaway-key>.pem -out <gate>.evidence.json.sig <gate>.evidence.json
```

The validity window is 2020-01-01 → 2099-01-01 on purpose: wide enough that these
fixtures cannot quietly expire and turn the suite red years from now, while still
exercising a real `issued_at` / `expires_at` pair. `test_production_evidence.py`
also passes an explicit `now`, so the assertions do not depend on the wall clock
at all.

These prove the **mechanism**, not an approval. Nothing here is an audit, a
review, or a sign-off. To regenerate them:

```
.venv-py312/Scripts/python.exe E:/hx/make_evidence_fixtures.py <throwaway-private-key>.pem
```

A real deployment needs a real auditor's key, kept outside the repository, and
evidence signed by it.

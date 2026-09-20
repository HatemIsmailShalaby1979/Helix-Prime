#!/usr/bin/env python3
"""
Helix Prime Codex — produce and sign the external evidence the nine production
gates demand. This is the **producer** half of B1.1.

`release/production_evidence.py` is the consumer: it verifies a detached RSA
signature over a document that lives outside this repository. Nothing in the tree
could *produce* such a document, so an external party had to reverse-engineer the
contract from the verifier source and hope their JSON satisfied it — and a
document whose only fault was a renamed field would be rejected with no way to
find out before shipping. This script is the missing half.

Usage::

    # 1. The external party generates and keeps its own key. Run this OUTSIDE the
    #    repository: the system being attested must not hold the signing key.
    python3 scripts/produce_production_evidence.py init-key --dir /srv/auditor/keys

    # 2. Emit a conforming document for one gate, then fill in the human fields.
    python3 scripts/produce_production_evidence.py template --gate security_review \\
        --out /srv/auditor/evidence/security_review.evidence.json

    # 3. Check it, sign it, check it again.
    python3 scripts/produce_production_evidence.py check --document <file>
    python3 scripts/produce_production_evidence.py sign --document <file> \\
        --key /srv/auditor/keys/evidence.key
    python3 scripts/produce_production_evidence.py check --document <file>

    # 4. Declare it to the release gate, then see what is still missing.
    export HELIX_PRODUCTION_EVIDENCE_DIR=/srv/auditor/evidence
    export HELIX_PRODUCTION_EVIDENCE_PUBKEY=/srv/auditor/keys/evidence.pub
    python3 scripts/produce_production_evidence.py status

What this tool deliberately does NOT do:

* It never invents an issuer, a date or an attestation. ``template`` leaves every
  human field empty and ``sign`` REFUSES a document that fails the contract, so
  the tool cannot be used to manufacture evidence.
* ``check`` judges the **form** of a document and its signature, never the
  substance. A passing check means "the gate would read this" — not "this is
  true", and never "production is approved".
* It never writes key material inside the repository.
* It does not make the terminal ``production_approved`` sign-off, which is a
  human act recorded elsewhere. This script can only help satisfy nine gates.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import NoReturn

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release import production_evidence as pe  # noqa: E402  (repo-root inserted above)

#: The fields a human must supply, with the guidance printed for each. `template`
#: leaves every one of them empty and `sign` refuses until they are filled, so
#: this tool cannot invent an issuer, a date or an attestation.
HUMAN_FIELDS: tuple[tuple[str, str], ...] = (
    ("issuer", "who is asserting this — a person or an organisation"),
    ("issued_at", "ISO-8601 with an offset, e.g. 2026-09-20T10:00:00+00:00"),
    ("expires_at", "ISO-8601 with an offset, later than issued_at"),
)

#: `payload` holds whatever the evidence type needs, in the issuer's own
#: structure. It is deliberately unconstrained: the gate reads six contract
#: fields and never the substance, and a schema here would invite the belief that
#: a well-shaped payload had been judged.
PAYLOAD_GUIDANCE = "what this evidence type needs, in your own structure"

DEFAULT_KEY_BITS = 4096


def _inside_repo(path: pathlib.Path) -> bool:
    """Whether ``path`` resolves inside this repository.

    Key material and evidence must not live in the tree they attest, so this is
    the check that stops the convenient-but-worthless layout.
    """
    try:
        path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return True


def _openssl(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("openssl")
    if exe is None:
        raise SystemExit(
            "openssl not found on PATH. It is required to generate keys and to "
            "sign documents (openssl dgst -sha256 -sign)."
        )
    return subprocess.run([exe, *args], capture_output=True, text=True)


def _fail(message: str) -> NoReturn:
    """Refuse and stop.

    Typed NoReturn so callers that end in a refusal are not read as falling
    through to an implicit ``return None``.
    """
    raise SystemExit(f"error: {message}")


def _self() -> str:
    """This script's path as the operator would type it, for copy-pasteable hints."""
    resolved = pathlib.Path(__file__).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _declared_key() -> pathlib.Path | None:
    raw = (os.environ.get("HELIX_PRODUCTION_EVIDENCE_PUBKEY") or "").strip()
    return pathlib.Path(raw) if raw else None


def cmd_gates(_args: argparse.Namespace) -> int:
    """List the nine production-only gates and the evidence each demands."""
    print(f"{len(pe.REQUIRED_EVIDENCE)} production-only gates, scope {pe.REQUIRED_SCOPE!r}:")
    for gate, evidence_type in sorted(pe.REQUIRED_EVIDENCE.items()):
        print(f"  {gate:38} {evidence_type}")
    print()
    print("Each needs <gate>.evidence.json plus <gate>.evidence.json.sig, in a")
    print("directory outside the repository. Use `template` to get the shape.")
    return 0


def cmd_init_key(args: argparse.Namespace) -> int:
    """Generate an independent signing keypair, outside the repository."""
    directory = pathlib.Path(args.dir)
    if _inside_repo(directory):
        _fail(
            f"{directory} is inside the repository. The key that attests this "
            "system must not live in it — choose a path outside the tree."
        )
    directory.mkdir(parents=True, exist_ok=True)
    private_key = directory / f"{args.name}.key"
    public_key = directory / f"{args.name}.pub"
    if not args.force:
        for path in (private_key, public_key):
            if path.exists():
                _fail(f"{path} already exists; pass --force to overwrite")

    generated = _openssl(
        "genpkey",
        "-algorithm",
        "RSA",
        "-pkeyopt",
        f"rsa_keygen_bits:{args.bits}",
        "-out",
        str(private_key),
    )
    if generated.returncode != 0:
        _fail(f"openssl genpkey failed: {generated.stderr.strip()}")
    exported = _openssl("rsa", "-in", str(private_key), "-pubout", "-out", str(public_key))
    if exported.returncode != 0:
        _fail(f"openssl rsa -pubout failed: {exported.stderr.strip()}")

    print(f"private key : {private_key}  (hand this to nobody; it signs)")
    print(f"public key  : {public_key}   (declare this to the release gate)")
    print()
    print("The private key is the whole trust anchor. Keep it off this machine if")
    print("this machine is the one being attested, and never commit either file.")
    print()
    print("Next: declare the public key, then emit a document.")
    print(f"  export HELIX_PRODUCTION_EVIDENCE_PUBKEY={public_key}")
    return 0


def cmd_template(args: argparse.Namespace) -> int:
    """Write a conforming document with every human field left empty."""
    if args.gate not in pe.REQUIRED_EVIDENCE:
        _fail(
            f"{args.gate!r} is not a production-only gate. Known gates:\n  "
            + "\n  ".join(sorted(pe.REQUIRED_EVIDENCE))
        )
    out = pathlib.Path(args.out)
    if out.exists() and not args.force:
        _fail(f"{out} already exists; pass --force to overwrite")
    if _inside_repo(out) and not args.allow_in_repo:
        _fail(
            f"{out} is inside the repository. Evidence kept in the tree it "
            "attests is not evidence — write it outside, or pass "
            "--allow-in-repo if you are drafting a document to move."
        )

    document: dict[str, object] = {
        "gate": args.gate,
        "evidence_type": pe.REQUIRED_EVIDENCE[args.gate],
        "scope": pe.REQUIRED_SCOPE,
    }
    document.update({name: "" for name, _ in HUMAN_FIELDS})
    document["payload"] = {}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {out}")
    print()
    print(f"gate          : {args.gate}")
    print(f"evidence_type : {pe.REQUIRED_EVIDENCE[args.gate]}   (fixed; the gate checks it)")
    print(f"scope         : {pe.REQUIRED_SCOPE}   (fixed; a pilot scope is refused)")
    print()
    print("Fill in by hand, and only with something true:")
    for name, description in HUMAN_FIELDS:
        print(f"  {name:12} {description}")
    print(f"  {'payload':12} {PAYLOAD_GUIDANCE}")
    print()
    print("The gate checks the six contract fields and the signature, never the")
    print("substance of what you wrote — that is for a human to judge.")
    print()
    print(f"Next: python3 {_self()} check --document {out}")
    return 0


def _load_document(path: pathlib.Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail(f"{path} not found")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{path} is not readable JSON: {exc}")


def _gate_for(document: object, requested: str | None) -> str:
    if requested:
        return requested
    if isinstance(document, dict) and isinstance(document.get("gate"), str):
        return document["gate"]
    _fail("cannot tell which gate this document is for; pass --gate")


def cmd_check(args: argparse.Namespace) -> int:
    """Report whether the gate would read this document — form, not truth."""
    document_path = pathlib.Path(args.document)
    document = _load_document(document_path)
    gate = _gate_for(document, args.gate)

    claims_ok, claims_reason = pe.validate_claims(gate, document)
    print(f"claims    : {'conforms' if claims_ok else 'REFUSED'}")
    print(f"            {claims_reason}")

    signature_state = "not checked (no key declared)"
    signature_path = document_path.with_suffix(document_path.suffix + ".sig")
    if not signature_path.exists():
        signature_state = f"missing ({signature_path.name})"
    else:
        key_path = _declared_key()
        if key_path is not None:
            if not key_path.exists():
                signature_state = f"not checked (declared key {key_path} not found)"
            else:
                verified = pe.verify_detached_signature(
                    key_path.read_text(encoding="utf-8"),
                    document_path.read_bytes(),
                    signature_path.read_bytes(),
                )
                signature_state = "verifies" if verified else "DOES NOT VERIFY"
    print(f"signature : {signature_state}")
    print()

    if not claims_ok:
        print("This document would be refused by the gate. Fix the claims above,")
        print("then sign it again — the signature covers the exact bytes.")
        return 1
    if signature_state != "verifies":
        print("The claims conform, but the gate also requires a verified signature.")
        print(f"  python3 {_self()} sign --document {document_path} " "--key <private-key>")
        return 1

    print("The gate would read this document.")
    print()
    print("That is a statement about FORM, not truth: it says the fields parse and")
    print("the signature matches the declared key. It is not an approval, it does")
    print("not make production ready, and it says nothing about whether the issuer")
    print("was entitled to assert this. Production also requires the terminal human")
    print("production_approved sign-off, which no script can produce.")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    """Sign a document — refusing outright if it fails the contract."""
    document_path = pathlib.Path(args.document)
    if not document_path.exists():
        _fail(f"{document_path} not found")
    key_path = pathlib.Path(args.key)
    if not key_path.exists():
        _fail(f"signing key {key_path} not found")

    document = _load_document(document_path)
    gate = _gate_for(document, args.gate)
    claims_ok, claims_reason = pe.validate_claims(gate, document)
    if not claims_ok:
        print(f"refusing to sign: {claims_reason}")
        print()
        print("A signature would only make an invalid document harder to fix. This")
        print("tool will not sign a document the gate would reject, so it cannot be")
        print("used to manufacture evidence.")
        return 1

    signature_path = pathlib.Path(str(document_path) + ".sig")
    signed = _openssl(
        "dgst",
        "-sha256",
        "-sign",
        str(key_path),
        "-out",
        str(signature_path),
        str(document_path),
    )
    if signed.returncode != 0:
        _fail(f"openssl dgst failed: {signed.stderr.strip()}")

    # Verify what was just written, using the public key derived from the signing
    # key. A signature nobody checked is a file, not evidence.
    derived = _openssl("rsa", "-in", str(key_path), "-pubout")
    if derived.returncode != 0:
        _fail(f"signed, but could not derive the public key: {derived.stderr.strip()}")
    if not pe.verify_detached_signature(
        derived.stdout, document_path.read_bytes(), signature_path.read_bytes()
    ):
        _fail("signed, but the signature did not verify against the signing key")

    print(f"signed    : {signature_path}")
    print("verified  : the signature matches the key it was made with")
    print()
    print("The gate verifies against HELIX_PRODUCTION_EVIDENCE_PUBKEY, so the")
    print("matching public key must be the declared one.")
    print(f"Next: python3 {_self()} check --document {document_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Report each gate's state and the next concrete step for it."""
    summary = pe.declared_evidence_summary()
    print("declared:")
    print(f"  evidence dir : {summary['evidence_dir'] or '(not set)'}")
    print(f"  public key   : {summary['public_key_path'] or '(not set)'}")
    print()
    if not summary["evidence_dir"] or not summary["public_key_path"]:
        print("Nothing is declared, so all nine gates refuse at the first check.")
        print("That is the fail-closed default, and it is correct until real")
        print("external evidence exists.")
        print()
        print("To begin:")
        print(f"  python3 {_self()} init-key --dir <outside-repo-dir>")
        print(f"  python3 {_self()} template --gate <gate> --out <file>")
        print()

    green = 0
    for gate in sorted(pe.REQUIRED_EVIDENCE):
        ok, reason = pe.check_gate_evidence(gate)
        green += 1 if ok else 0
        print(f"  [{'green' if ok else ' red '}] {reason}")
    print()
    print(f"{green} of {len(pe.REQUIRED_EVIDENCE)} production-only gates have verified evidence.")
    print()
    print("Even at nine of nine, production additionally requires the terminal human")
    print("production_approved sign-off (release/signoff.py) and the release manifest")
    print("regenerated by a real ceremony. This command reports evidence, not approval.")
    return 0 if green == len(pe.REQUIRED_EVIDENCE) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("gates", help="list the nine gates and their evidence types")
    p.set_defaults(func=cmd_gates)

    p = sub.add_parser("init-key", help="generate an independent signing keypair")
    p.add_argument("--dir", required=True, help="directory outside the repository")
    p.add_argument("--name", default="evidence", help="key file stem (default: evidence)")
    p.add_argument("--bits", type=int, default=DEFAULT_KEY_BITS)
    p.add_argument("--force", action="store_true", help="overwrite existing keys")
    p.set_defaults(func=cmd_init_key)

    p = sub.add_parser("template", help="write a conforming document to fill in")
    p.add_argument("--gate", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true", help="overwrite an existing file")
    p.add_argument(
        "--allow-in-repo",
        action="store_true",
        help="allow drafting inside the repo (move it out before declaring it)",
    )
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("check", help="would the gate read this document?")
    p.add_argument("--document", required=True)
    p.add_argument("--gate", help="override the gate named inside the document")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("sign", help="sign a document (refuses an invalid one)")
    p.add_argument("--document", required=True)
    p.add_argument("--key", required=True, help="PEM private key, outside the repo")
    p.add_argument("--gate", help="override the gate named inside the document")
    p.set_defaults(func=cmd_sign)

    p = sub.add_parser("status", help="per-gate evidence state and the next step")
    p.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

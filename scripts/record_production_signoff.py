#!/usr/bin/env python3
"""
Helix Prime Codex — record and check a go/no-go sign-off.

`release/signoff.py` can *validate* and *serialise* a `SignOff`, and
`import_go_no_go()` reads the local pilot-consent flag — but nothing in the tree
could *create* a sign-off record. The terminal `production_approved` step is the
one the plan calls non-outsourceable, and it had no supported path: a human had to
hand-write JSON satisfying eight cross-checked fields and find out only at gate
time whether it was accepted. That is the same last-mile gap the evidence producer
closed for the nine gates.

Usage::

    python3 scripts/record_production_signoff.py states
    python3 scripts/record_production_signoff.py template \\
        --state production_approved --out /srv/helix/signoff/production.json
    #   ...a human fills it in...
    python3 scripts/record_production_signoff.py check \\
        --record /srv/helix/signoff/production.json

What this tool deliberately does NOT do:

* It never fills in a reviewer, a decision, a timestamp, a signature reference or
  an evidence reference. `template` leaves them empty and `check` reports what is
  missing.
* It cannot manufacture an approval. The rules are `signoff.validate_signoff` —
  the same function the release gate calls — not a copy of them. In particular
  `production_approved` is refused unless all nine production-only gates are green
  *on signed external evidence*, so this tool cannot turn a well-formed document
  into an approval.
* It does not decide where a record lives, but it refuses to write inside the
  repository: the attested system must not hold the record that attests it.
* `check` passing means the record is **well-formed**, not that the approval is
  legitimate. Legitimacy is the human's and their reviewer's to establish.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import NoReturn

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release import signoff  # noqa: E402  (repo-root inserted above)

#: States a human may be asked to record, in the order the module declares them.
STATE_NOTES = {
    "unsigned": "no approval; a local automated run may produce this",
    "internal_review": "local gate consent only — never a release approval",
    "conditional": "approval held open pending recorded conditions",
    "pilot_approved": "human approval for the controlled pilot",
    "production_approved": "human approval for production — terminal, needs all nine gates green",
}


def _inside_repo(path: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return True


def _fail(message: str) -> NoReturn:
    raise SystemExit(f"error: {message}")


def _self() -> str:
    resolved = pathlib.Path(__file__).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def cmd_states(_args: argparse.Namespace) -> int:
    """List the sign-off states and which of them are human approvals."""
    print(f"{len(signoff.SIGN_OFF_STATES)} sign-off states (release/signoff.py):")
    for state in signoff.SIGN_OFF_STATES:
        if state in signoff.APPROVAL_STATES:
            kind = "human approval"
        elif state in signoff.LOCAL_ONLY_STATES:
            kind = "local only"
        else:
            kind = "held open"
        print(f"  {state:20} {kind:15} {STATE_NOTES.get(state, '')}")
    print()
    print(f"decisions: {', '.join(signoff.DECISIONS)}")
    print()
    print("Only a human approval can release anything, and only")
    print("production_approved reaches production. The other states are how a")
    print("local run records that it proved gate status, nothing more.")
    return 0


def _report(s: signoff.SignOff) -> int:
    """Validate and explain. Shared by `check` and by `template`'s echo."""
    ok, reason = signoff.validate_signoff(s)
    print(f"state       : {s.state}")
    print(f"decision    : {s.decision or '(empty)'}")
    print(f"reviewer    : {s.reviewer or '(empty)'}")
    print(f"decided_at  : {s.decided_at or '(empty)'}")
    print(
        f"evidence    : {s.evidence_pack_id or '(no pack id)'} "
        f"{'refs=' + str(len(s.evidence_refs)) if s.evidence_refs else '(no refs)'}"
    )
    if s.state == "production_approved":
        print(f"signature   : {s.signature_ref or '(no signature reference)'}")
    print()
    print(f"valid       : {'yes' if ok else 'NO'}")
    print(f"            {reason}")
    print()

    if not ok:
        print("This record would be refused. The rules above are the same function")
        print("the release gate calls, so fixing them here fixes them there. It")
        print("reports the first unmet rule, not all of them — re-run after each fix.")
        if s.state == "production_approved":
            print()
            print("production_approved additionally requires every production-only")
            print("gate green on signed external evidence. To see which are missing:")
            print("  python3 scripts/produce_production_evidence.py status")
        return 1

    print(f"release approval : {'yes' if signoff.is_release_approved(s) else 'no'}")
    print(f"local-only proof : {'yes' if signoff.can_prove_gate_locally(s) else 'no'}")
    print()
    print("Well-formed is not the same as legitimate. This says the record parses")
    print("and satisfies the gate's rules; it does not verify that the named human")
    print("is who they claim to be, that the signature reference exists, or that")
    print("the reviewer was independent. Those are the reviewer's to establish.")
    return 0


def cmd_template(args: argparse.Namespace) -> int:
    """Write an empty record for one state, then show what it still needs."""
    if not signoff.is_valid_state(args.state):
        _fail(
            f"{args.state!r} is not a sign-off state. Known states:\n  "
            + "\n  ".join(signoff.SIGN_OFF_STATES)
        )
    out = pathlib.Path(args.out)
    if out.exists() and not args.force:
        _fail(f"{out} already exists; pass --force to overwrite")
    if _inside_repo(out) and not args.allow_in_repo:
        _fail(
            f"{out} is inside the repository. The record that attests this system "
            "must not live in it — write it outside, or pass --allow-in-repo if "
            "you are drafting a record to move."
        )

    record = signoff.SignOff(state=args.state)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8")

    print(f"wrote {out}")
    print()
    print("Every field a human must supply is empty on purpose: this tool does not")
    print("invent a reviewer, a decision or a date. Here is what the gate will")
    print("demand of it as it stands.")
    print()
    code = _report(record)
    print()
    print(f"Next: fill it in, then python3 {_self()} check --record {out}")
    # The template itself is expected to be incomplete; that is not a failure.
    return 0 if code in (0, 1) else code


def cmd_check(args: argparse.Namespace) -> int:
    """Validate a record with the same function the release gate calls."""
    path = pathlib.Path(args.record)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail(f"{path} not found")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{path} is not readable JSON: {exc}")
    if not isinstance(data, dict):
        _fail(f"{path} is not a JSON object")

    unknown = sorted(set(data) - set(signoff.SignOff.__dataclass_fields__))
    if unknown:
        print(f"ignored keys: {', '.join(unknown)}")
        print()

    return _report(signoff.SignOff.from_dict(data))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("states", help="list the sign-off states and their meaning")
    p.set_defaults(func=cmd_states)

    p = sub.add_parser("template", help="write an empty record for one state")
    p.add_argument("--state", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true", help="overwrite an existing file")
    p.add_argument(
        "--allow-in-repo",
        action="store_true",
        help="allow drafting inside the repo (move it out before it counts)",
    )
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("check", help="would the gate accept this record?")
    p.add_argument("--record", required=True)
    p.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

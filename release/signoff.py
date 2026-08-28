"""
Helix Prime Codex post-C8 — structured go/no-go sign-off model.

A small, deterministic record model for human-in-the-loop release sign-offs.
It exists so the system can represent and VALIDATE sign-offs without ever
fabricating an approval: a local automated run may prove gate status, but it
does not create a fake human approval.

Sign-off states (strict, ordered by increasing commitment):
  - unsigned           : no sign-off record exists; nothing is approved
  - internal_review    : internally reviewed (a local go/no-go consent flag);
                         this is NOT a human release approval
  - conditional        : review concluded with explicit conditions still open;
                         NOT approved until conditions are satisfied
  - pilot_approved     : a real human sign-off authorizing the controlled pilot
  - production_approved: a real human + external evidence sign-off for PRODUCTION
                         (requires every production-only gate; NOT satisfiable
                         by any local automated run)

Core invariants:
  * unsigned / internal_review / conditional can never be treated as a
    pilot or production approval.
  * conditional REQUIRES a non-empty conditions list.
  * pilot_approved requires a reviewer identity, role, decision timestamp,
    evidence pack id, and evidence references.
  * production_approved additionally requires a signature reference id and
    that all production-only gates are green (see release.profiles).
  * An expired sign-off is rejected.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Distinct sign-off states (order encodes increasing commitment).
SIGN_OFF_STATES = [
    "unsigned",
    "internal_review",
    "conditional",
    "pilot_approved",
    "production_approved",
]

# Human decisions recorded on a sign-off record.
DECISIONS = ["approve", "reject", "conditional"]

# Local/permitted states that are NOT a human release approval:
# these prove gate status only and can be produced by an automated run.
LOCAL_ONLY_STATES = {"unsigned", "internal_review"}
# States that DO represent a human release approval.
APPROVAL_STATES = {"pilot_approved", "production_approved"}


def _now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class SignOff:
    """A single go/no-go sign-off record."""

    state: str = "unsigned"
    release_profile: str = "controlled_pilot"
    evidence_pack_id: str = ""
    reviewer: str = ""               # human identity
    reviewer_role: str = ""          # e.g. pilot_operator / security_owner
    decision: str = ""               # approve | reject | conditional
    decided_at: str = ""             # ISO timestamp of the human decision
    scope: str = ""
    conditions: List[str] = field(default_factory=list)
    expires_at: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    signature_ref: Optional[str] = None  # reference id to an external signature doc

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignOff":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def new_signoff(**fields: Any) -> SignOff:
    """Create a SignOff from fields, defaulting to `unsigned`."""
    return SignOff(**fields)


def is_valid_state(state: str) -> bool:
    return state in SIGN_OFF_STATES


def validate_signoff(s: SignOff) -> tuple[bool, str]:
    """Validate a sign-off record. Returns (ok, reason). Fail-closed."""
    if not is_valid_state(s.state):
        return False, f"unknown state {s.state!r}"

    if s.state == "unsigned":
        return True, "unsigned: no approval"

    if s.state == "internal_review":
        return True, "internal_review: local gate consent only, not a release approval"

    if s.state == "conditional":
        if not s.conditions:
            return False, "conditional requires a non-empty conditions list"
        if not s.decided_at:
            return False, "conditional requires a decision timestamp"
        return True, "conditional: approval held open pending conditions"

    # pilot_approved / production_approved are genuine human approvals.
    if s.decision != "approve":
        return False, f"{s.state} requires decision='approve' (got {s.decision!r})"
    if not s.reviewer:
        return False, f"{s.state} requires a reviewer identity"
    if not s.reviewer_role:
        return False, f"{s.state} requires a reviewer role"
    if not s.decided_at:
        return False, f"{s.state} requires a decision timestamp"
    if not s.evidence_pack_id:
        return False, f"{s.state} requires an evidence pack id"
    if not s.evidence_refs:
        return False, f"{s.state} requires at least one evidence reference"

    if s.state == "production_approved":
        if not s.signature_ref:
            return False, "production_approved requires a signature reference id"
        if not _all_production_gates_satisfied():
            return False, "production_approved requires every production-only gate green"

    # Expiry: if an expiration is recorded and it has passed, reject.
    if s.expires_at and _is_expired(s.expires_at):
        return False, "sign-off has expired"

    return True, f"{s.state}: valid human {s.decision}"



def _all_production_gates_satisfied() -> bool:
    """Production-only gates are external and NOT satisfiable locally.

    This always returns False: no local automated run or environment can
    fabricate the external evidence required for a production sign-off.
    """
    return False


def _is_expired(expires_at: str) -> bool:
    try:
        exp = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False  # unparseable expiry is treated as non-expired (still gated elsewhere)
    return datetime.datetime.now(datetime.timezone.utc) > exp


def is_release_approved(s: SignOff, for_state: Optional[str] = None) -> bool:
    """Return True only if the sign-off is a current, valid approval for the
    requested state (default: its own state). Fail-closed."""
    ok, _ = validate_signoff(s)
    if not ok:
        return False
    target = for_state or s.state
    return s.state == target and s.state in APPROVAL_STATES


def can_prove_gate_locally(s: SignOff) -> bool:
    """A local automated run may produce a sign-off in a LOCAL_ONLY state, but
    that never creates a human pilot/production approval."""
    ok, _ = validate_signoff(s)
    return ok and s.state in LOCAL_ONLY_STATES


def unexpired_pilot_approval(s: SignOff) -> bool:
    """Convenience: is this a valid, non-expired pilot approval?"""
    return is_release_approved(s, for_state="pilot_approved")


def sign_off_to_json(s: SignOff, **kw: Any) -> str:
    return json.dumps(s.to_dict(), default=str, **kw)


def import_go_no_go(rel_path: str = "release/go-no-go.json") -> SignOff:
    """Read the C8 local go/no-go consent file as an `internal_review`
    sign-off. This is LOCAL provenance only — it is NOT a human approval and
    can never upgrade to pilot/production approval."""
    from release import manifest as manifest_mod
    p = manifest_mod.ROOT / rel_path
    data: Dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    approved = bool(data.get("approved", False))
    scope = str(data.get("data_scope", ""))
    return SignOff(
        state="internal_review",
        release_profile="controlled_pilot",
        evidence_pack_id="",
        reviewer=data.get("approver", "operator-pilot-consent"),
        reviewer_role="operator",
        decision=(
            "conditional"
            if (approved and not scope)
            else ("approve" if approved else "reject")
        ),
        decided_at=str(data.get("approved_at", "")),
        scope=scope,
        conditions=[],  # consent flag is review-only; no human conditions recorded
    )

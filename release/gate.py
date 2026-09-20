"""
Helix Prime Codex C8 — release gate orchestrator.

Runs every gate in the requested profile, aggregates pass/fail, and emits a
deterministic classification. Final classifications allowed by C8:
    CONTROLLED_PILOT_READY  (profile=controlled_pilot, all gates green)
    PRODUCTION_CANDIDATE    (profile=production_candidate, all gates green)
    PRODUCTION              (profile=production, all 23 gates green on signed
                             external evidence plus a release_approved sign-off)

PRODUCTION became permitted on 2026-09-20, and it is reachable only by evidence:
each of the nine production-only gates demands a signature produced by a key held
outside this repository, so no local run can manufacture the label.

The gate writes a machine-readable evidence pack + release manifest under
`evidence/releases/<timestamp>/` (gitignored, not committed).

Exit code: 0 if the emitted classification is a permitted C8 outcome,
non-zero on any gate failure or disallowed classification.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional

from release import harness as harness_mod
from release import manifest as manifest_mod
from release import observability, production_evidence, profiles, security_gate

ROOT = manifest_mod.ROOT

# Gate -> implementation. Each callable returns (ok: bool, detail: str).
GATE_IMPL: Dict[str, str] = {}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, indent=2)


def _discard_scratch(path: str) -> None:
    """Remove a gate's scratch directory, and never raise doing it.

    Two reasons this is a function rather than an inline `rmtree`. First, a
    cleanup failure must not change a gate's verdict: gates that leak a temp tree
    are a hygiene defect, but a gate that turns red because a directory would not
    delete is a correctness defect, and the second is worse. Second, on Windows
    the sandbox routes deletions under a non-OS-temp path through a trash
    subprocess with a timeout, so a large or busy tree can genuinely fail.
    """
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


# ── individual gate checks ─────────────────────────────────────────────────


def _gate_repository_state() -> tuple[bool, str]:
    """A release must be able to name the commit it attests.

    This used to call `build_manifest()` for its side effect and then return `True`
    unconditionally, so it was green even with git undetectable — while reporting
    "git + runtime detectable". Nothing could fail: `build_manifest()` degrades to
    `git_commit: "unknown"` rather than raising, so the gate asserted a condition it
    never checked. Measured before the fix by making git undetectable:
    `(True, 'repository_state: git + runtime detectable')` alongside a manifest that
    said `git_commit: unknown`.

    It now checks the value the manifest actually records. The declared purpose
    ("clean-ish repo") was never true and is not implemented here: running the gate
    writes `release/release-manifest.json`, so the tree is dirty immediately
    afterwards by construction. This gate is about *attestability*, not cleanliness.
    """
    built = manifest_mod.build_manifest()
    commit = str(built.get("git_commit", "") or "")
    if not commit or commit == "unknown":
        return False, (
            "repository_state: git commit not detectable — a release cannot attest "
            "a commit it cannot name"
        )
    return True, f"repository_state: git + runtime detectable ({commit[:12]})"


# A dependency lock line that pins an exact version. An optional trailing
# environment marker is allowed, because pip-compile emits them; anything else
# (a bare name, a range, an editable path, an include directive) is not a pin.
_PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[^=\s]+(?:\s*;.*)?$")

#: The one document that claims to describe a reproducible install.
_SETUP_DOC = "docs/release/setup-guide.md"


def _lock_lines() -> List[str]:
    """Declared (non-comment, non-blank) lines of the dependency lock file.

    The comment test strips leading whitespace first. `str.startswith` alone is
    not enough: pip-compile *indents* its `# via ...` provenance comments, so
    `line.startswith("#")` silently counted them as declarations. Measured on the
    committed lock file before this fix: `reproducible_install` reported **337**
    "declared deps" against **120** real pins — 217 indented comments. One parser
    for both lock gates, because the repository's recurring defect is a rule and
    a restatement of it drifting apart.
    """
    p = ROOT / "release" / "requirements.lock.txt"
    if not p.exists():
        return []
    lines: List[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _gate_reproducible_install() -> tuple[bool, str]:
    """A documented setup path exists and the lock declares a dependency set.

    Two things were wrong before. It counted lines with `not ln.startswith("#")`,
    which does not strip leading whitespace, so pip-compile's indented comments
    were counted as declarations — 337 reported against 120 real — and a lock file
    containing nothing but an indented comment passed. And the first half of its
    declared purpose ("one setup path documented") was never checked at all.

    The second half is now checked rather than dropped, because it is checkable:
    `docs/release/setup-guide.md` is titled "Setup Guide (Reproducible Install)",
    states it is the one-document path, and names this gate. A gate whose purpose
    and behaviour disagree is the §18.2 A0.1 class, and correcting the purpose is
    only right when the check *cannot* exist — here it can.
    """
    doc = ROOT / _SETUP_DOC
    doc_ok = doc.exists() and "requirements.lock.txt" in doc.read_text(encoding="utf-8")
    lines = _lock_lines()
    ok = doc_ok and len(lines) > 0
    return ok, (
        f"reproducible_install: setup doc={doc_ok} ({_SETUP_DOC}), {len(lines)} declared deps"
    )


def _gate_dependency_locking() -> tuple[bool, str]:
    """Every declared requirement must be pinned to an exact version.

    It used to check only that the file existed and was non-empty, while its
    declared purpose is "dependency versions pinned/locked". Measured before the
    fix: a lock file containing one indented comment, and one containing the bare
    lines `requests` / `flask`, both passed. That is a nominal control — the
    §18.2 A0.1 class — and it was strictly weaker than `reproducible_install`, so
    it could never be the gate that failed.
    """
    lines = _lock_lines()
    unpinned = [line for line in lines if not _PIN_RE.match(line)]
    ok = len(lines) > 0 and not unpinned
    detail = f"dependency_locking: {len(lines) - len(unpinned)} pinned"
    if unpinned:
        detail += f", {len(unpinned)} unpinned (first: {unpinned[0]!r})"
    return ok, detail


def _gate_configuration_validation() -> tuple[bool, str]:
    """The declared profile file must agree with the code that runs it.

    Two of the three checks used to be length floors — `len(gates) >= 10` and
    `len(profiles) >= 4` — against a file that declares 14 and 6, so four gates
    and two profiles could be deleted from the source of truth and this gate
    stayed green. That is the §18.2 A0.1 pattern: a control reporting a property
    it does not measure. The floors are replaced by closure against the code,
    which is the one comparison a single-sourced file cannot satisfy by restating
    its own numbers: every declared gate must have an implementation in this
    module, and every implemented gate must be named by some declared list.
    """
    prof = profiles.load_profiles()
    declared_gates = set(prof.get("gates", profiles.GATE_NAMES))
    declared_app = set(prof.get("app_gates", profiles.APP_GATE_NAMES))
    prod_required = list(prof.get("required_gates", {}).get("production", []))
    declared_prod_only = {g for g in prod_required if g not in declared_gates}
    declared_all = declared_gates | declared_app | declared_prod_only

    unimplemented = sorted(declared_gates - set(GATE_IMPL))
    orphaned = sorted(set(GATE_IMPL) - declared_all)
    ok_gates = bool(declared_gates) and not unimplemented and not orphaned

    unevidenced = sorted(declared_prod_only - set(production_evidence.REQUIRED_EVIDENCE))
    ok_profiles = bool(prof.get("profiles", profiles.PROFILE_ORDER)) and not unevidenced

    schema_p = ROOT / "release" / "manifest.schema.json"
    try:
        ok_schema = schema_p.exists() and isinstance(
            json.loads(schema_p.read_text(encoding="utf-8")), dict
        )
    except Exception:  # noqa: BLE001
        ok_schema = False

    ok = ok_gates and ok_profiles and ok_schema
    detail = f"configuration: gates={ok_gates} profiles={ok_profiles} schema={ok_schema}"
    if unimplemented:
        detail += f", no implementation: {', '.join(unimplemented)}"
    if orphaned:
        detail += f", named by no declared list: {', '.join(orphaned)}"
    if unevidenced:
        detail += f", no evidence requirement: {', '.join(unevidenced)}"
    return ok, detail


def _gate_startup_readiness() -> tuple[bool, str]:
    """`all_ok` also folds in the storage check, so the message must name it.

    `run_observability_report` computes `all_ok` from startup AND readiness AND
    storage, but the detail string only reported the first two. A red gate caused
    entirely by an unwritable store therefore read as `startup_ok=True
    ready=True`, with no visible cause. The check is unchanged; the report now
    names every input that can turn it red.
    """
    rep = observability.run_observability_report()
    startup = rep["checks"]["startup"]
    readiness = rep["checks"]["readiness"]
    storage = rep["checks"]["storage"]
    ok = rep["all_ok"]
    return ok, (
        f"startup_readiness: all_ok={ok} startup_ok={bool(startup.get('slo_met'))} "
        f"ready={bool(readiness.get('ready'))} "
        f"storage_writable={bool(storage.get('all_writable'))}"
    )


def _gate_backup_restore() -> tuple[bool, str]:
    """Synthetic-state backup/restore (never mutates live DBs).

    `restore_state` documents that it "enforces schema compatibility (fail
    closed)" and raises when `schema_ok` is false — but this gate used to pass
    `schema_ok=True` as a literal, so the branch could never fire and the
    compatibility claim was an assertion rather than a check. The backup already
    records `schema_versions`, so the value is now computed from that record.
    Within this gate both sides are read from the same state moments apart, so
    the comparison is only falsifiable by a backup carrying different versions —
    which is exactly what the can-fail test constructs.
    """
    from release import backup

    work = tempfile.mkdtemp(prefix="hp_gate_br_")
    try:
        from control_plane.store import Store
        from security.audit import AuditRecord, AuditTrail

        db = os.path.join(work, "control_plane", "workflow.db")
        store = Store(db_path=db)
        store.close()
        audit_db = os.path.join(work, "security", "audit.db")
        trail = AuditTrail(db_path=audit_db)
        prev = None
        for _ in range(2):
            rec = AuditRecord.new(
                event_type="br",
                actor="gate",
                actor_type="service",
                decision="succeeded",
                previous_hash=prev,
            )
            trail.append(rec)
            prev = rec.current_hash
        trail.close()
        backup_dir = os.path.join(work, "backup")
        backup.backup_state(backup_dir, repo_root=work)
        restore_dir = os.path.join(work, "restored")
        recorded = json.loads(
            pathlib.Path(backup_dir, "backup-manifest.json").read_text(encoding="utf-8")
        )
        schema_ok = recorded.get("schema_versions") == manifest_mod.data_schema_versions()
        backup.restore_state(backup_dir, restore_dir, repo_root=work, schema_ok=schema_ok)
        # verify restored audit chain
        from security.audit import AuditTrail as AT2

        t2 = AT2(db_path=os.path.join(restore_dir, "security", "audit.db"))
        valid, msg = t2.verify_chain()
        t2.close()
        detail = f"backup_restore: restored audit chain valid={valid} schema_ok={schema_ok} ({msg})"
        return valid, detail
    except Exception as e:  # noqa: BLE001
        return False, f"backup_restore: {type(e).__name__}: {e}"
    finally:
        _discard_scratch(work)


def _gate_rollback() -> tuple[bool, str]:
    """Synthetic manifest rollback: previous identity restored, provenance kept.

    The manifest read used to leak an open handle (`json.load(open(...))`), which
    is what the C0 Windows SQLite-handle work exists to stop; it is closed here.
    """
    from release import backup

    prev = {"git_commit": "AAAA", "classification": "PRODUCTION_CANDIDATE", "version": "0.9.0-c8"}
    cur = {"git_commit": "BBBB", "classification": "PRODUCTION_CANDIDATE", "version": "0.9.0-c8"}

    work = tempfile.mkdtemp(prefix="hp_gate_rb_")
    try:
        path = os.path.join(work, "release-manifest.json")
        backup.rollback_manifest(prev, cur, target_path=path)
        with open(path, encoding="utf-8") as f:
            out = json.load(f)
        ok = out["git_commit"] == "AAAA" and "_rolled_back_from" in out
        return ok, f"rollback: previous identity restored ok={ok}"
    finally:
        _discard_scratch(work)


def _gate_data_isolation() -> tuple[bool, str]:
    from release import harness as h

    ti = h._check("tenant_isolation", h._check_tenant_isolation)
    cl = security_gate.check_classification()
    dbd = security_gate.check_deny_by_default()
    ok = ti["ok"] and cl["ok"] and dbd["ok"]
    return ok, f"data_isolation_ok={ti['ok']} class={cl['ok']} deny_default={dbd['ok']}"


def _gate_audit_integrity() -> tuple[bool, str]:
    probe = security_gate.check_audit_integrity()
    if not probe["ok"]:
        return False, probe["detail"]
    declared = os.environ.get("HELIX_AUDIT_DB_PATH", "").strip()
    if not declared:
        return True, (
            f"{probe['detail']}; runtime chain not declared "
            "(set HELIX_AUDIT_DB_PATH=<path> to verify the shipped audit chain)"
        )
    db_path = pathlib.Path(declared)
    if not db_path.exists():
        return False, f"audit_integrity: declared audit db {declared!r} not found"
    declared_result = security_gate.check_audit_integrity(audit_db=str(db_path))
    if not declared_result["ok"]:
        return False, declared_result["detail"]
    return True, f"{probe['detail']}; declared chain verified ({declared})"


def _gate_security_checks() -> tuple[bool, str]:
    res = security_gate.run_security_gate(scan_subdirs=None)
    ok = res["all_ok"]
    detail = "; ".join(f"{k}:{v['ok']}" for k, v in res.items() if k != "all_ok")
    return ok, f"security_checks: all_ok={ok} ({detail})"


def _gate_failure_recovery() -> tuple[bool, str]:
    h = harness_mod.run_harness(num_soak_workflows=3)
    fail_sensitive = [
        "engine_timeout",
        "unavailable_ollama",
        "unavailable_sibling",
        "corrupted_event",
        "corrupted_db",
        "interrupted_workflow",
        "c7_transport_retry_deadletter",
    ]
    ok = all(h["checks"][k]["ok"] for k in fail_sensitive) and h["all_ok"]
    return ok, f"failure_recovery: all_ok={h['all_ok']}"


def _gate_performance_limits() -> tuple[bool, str]:
    soak = harness_mod.run_bounded_soak(num_workflows=5)
    startup = observability.measure_startup()
    ok = soak["ok"] and startup.get("slo_met", False)
    return ok, f"performance_limits: soak_ok={soak['ok']} startup_slo={startup.get('slo_met')}"


def _operator_doc_has_body(rel: str) -> bool:
    """True when `rel` exists under ROOT and carries non-blank text.

    Absence and unreadability are both "not ready": an operator document that
    cannot be read cannot be followed.
    """
    try:
        return bool((ROOT / rel).read_text(encoding="utf-8").strip())
    except (OSError, UnicodeDecodeError):
        return False


def _gate_operator_readiness() -> tuple[bool, str]:
    """Each operator document must be present AND carry content.

    Presence alone is not readiness: a zero-byte runbook satisfied this gate
    before, the same defect `dependency_locking` had when it went green on a
    merely non-empty file. The bar is a non-blank body.
    """
    docs = [
        "docs/release/operator-runbook.md",
        "docs/release/incident-response.md",
        "docs/release/backup-restore-guide.md",
        "docs/release/controlled-pilot-pack.md",
    ]
    filled = [rel for rel in docs if _operator_doc_has_body(rel)]
    ok = len(filled) == len(docs)
    return ok, f"operator_readiness: {len(filled)}/{len(docs)} docs present and non-empty"


def _gate_release_approval() -> tuple[bool, str]:
    p = ROOT / "release" / "go-no-go.json"
    if not p.exists():
        return False, "release_approval: missing go-no-go.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        approved = bool(data.get("approved", False))
        scope_ok = str(data.get("data_scope", "")) == "SYNTHETIC_OR_CONSENTED_ONLY"
        # The C8 go/no-go is a LOCAL consent flag scoped to candidate/pilot
        # classification only. It is NOT a human production approval; the
        # production profile additionally requires all production-only gates.
        return approved and scope_ok, (f"release_approval: approved={approved} scope_ok={scope_ok}")
    except Exception as e:  # noqa: BLE001
        return False, f"release_approval: {type(e).__name__}: {e}"


# ── production-only gates ─────────────────────────────────────────────────
# Each gate now reads *signed evidence from outside the repository*, declared by
# HELIX_PRODUCTION_EVIDENCE_DIR / HELIX_PRODUCTION_EVIDENCE_PUBKEY and verified
# by release/production_evidence.py. The evidence type each gate demands lives
# beside that reader, so the red reason and the green check cannot drift apart.
#
# The fail-closed default is unchanged and is the first check in the reader: with
# nothing declared in the environment, every gate below still returns False with
# a reason naming what is missing. What is new is that a gate can become green
# *by evidence* instead of never — the door is openable, and only by a signature
# this repository cannot produce.
def _prod_gate(gate: str) -> tuple[bool, str]:
    return production_evidence.check_gate_evidence(gate)


def _gate_signed_production_evidence() -> tuple[bool, str]:
    return _prod_gate("signed_production_evidence")


def _gate_certified_data_isolation() -> tuple[bool, str]:
    return _prod_gate("certified_data_isolation")


def _gate_external_observer_audit() -> tuple[bool, str]:
    return _prod_gate("external_observer_audit")


def _gate_production_deployment_architecture() -> tuple[bool, str]:
    return _prod_gate("production_deployment_architecture")


def _gate_disaster_recovery_evidence() -> tuple[bool, str]:
    return _prod_gate("disaster_recovery_evidence")


def _gate_operational_ownership() -> tuple[bool, str]:
    return _prod_gate("operational_ownership")


def _gate_incident_oncall_ownership() -> tuple[bool, str]:
    return _prod_gate("incident_oncall_ownership")


def _gate_security_review() -> tuple[bool, str]:
    return _prod_gate("security_review")


def _gate_legal_privacy_review() -> tuple[bool, str]:
    return _prod_gate("legal_privacy_review")


# ── app release gates (the Helix Codex App product surface) ────────────────
# These prove the app's own invariants before a pilot claim. Each is a
# self-contained, fail-closed check over a temporary state; none touches a
# live database.


def _app_build() -> tuple[Any, Any]:
    from helix_codex_app.app import create_app
    from helix_codex_app.config import AppSettings

    return create_app(AppSettings(db_path=":memory:", cookie_secure=False)), None


def _gate_app_auth_boundary() -> tuple[bool, str]:
    """Every /app route except healthz and the static mount must run the guard."""
    try:
        app, _ = _app_build()
    except Exception as e:  # noqa: BLE001
        return False, f"app_auth_boundary: app build failed: {type(e).__name__}: {e}"
    guard_name = "current_account"
    unguarded: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None or not str(path).startswith("/app"):
            continue
        if str(path) == "/app/healthz":
            continue
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            unguarded.append(f"{path}: no dependency tree")
            continue
        deps = getattr(dependant, "dependencies", [])
        names = {getattr(getattr(d, "call", None), "__name__", "") for d in deps}
        if guard_name not in names:
            unguarded.append(path)
    ok = not unguarded
    detail = f"app_auth_boundary: {len(unguarded)} unguarded /app routes"
    if unguarded:
        detail += " (first: " + ", ".join(str(p) for p in unguarded[:3]) + ")"
    return ok, detail


def _gate_app_session_fail_closed() -> tuple[bool, str]:
    """A revoked and an expired session both fail; a live one passes."""
    import tempfile

    from helix_codex_app import db
    from helix_codex_app.config import AppSettings
    from helix_codex_app.security.accounts import AccountRepository
    from helix_codex_app.security.passwords import hash_password
    from helix_codex_app.security.sessions import SessionStore

    work = tempfile.mkdtemp(prefix="hp_gate_app_session_")
    try:
        db_path = os.path.join(work, "app.db")
        conn = db.connect(db_path=db_path)
        db._init_schema(conn)
        repo = AccountRepository(conn)
        domain = repo.create_domain(
            "gate.academy", tenant_id="tenant-gate", client_id="client-gate"
        )
        account = repo.create_account(
            domain.domain_id,
            "gateuser",
            role_id="owner",
            password_hash=hash_password("your-password"),
        )
        settings = AppSettings(db_path=db_path, cookie_secure=False)
        store = SessionStore(conn, settings)
        token, session = store.issue_session(account)
        live = store.verify(token)
        store.revoke(session.session_id)
        revoked = store.verify(token)
        token2, session2 = store.issue_session(account)
        conn.execute(
            "UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE session_id = ?",
            (session2.session_id,),
        )
        conn.commit()
        expired = store.verify(token2)
        db.close(conn)
        ok = live is not None and revoked is None and expired is None
        return (
            ok,
            f"app_session_fail_closed: live={live is not None} revoked={revoked is None} "
            f"expired={expired is None}",
        )
    except Exception as e:  # noqa: BLE001
        return False, f"app_session_fail_closed: {type(e).__name__}: {e}"
    finally:
        _discard_scratch(work)


def _gate_app_tenant_isolation() -> tuple[bool, str]:
    """Two tenants never see each other's rows; a cross-tenant login fails."""
    import tempfile

    from helix_codex_app import db
    from helix_codex_app.security.accounts import AccountRepository
    from helix_codex_app.security.passwords import hash_password

    work = tempfile.mkdtemp(prefix="hp_gate_app_tenant_")
    try:
        db_path = os.path.join(work, "app.db")
        conn = db.connect(db_path=db_path)
        db._init_schema(conn)
        repo = AccountRepository(conn)
        domain_a = repo.create_domain("a.gate", tenant_id="tenant-a", client_id="client-a")
        domain_b = repo.create_domain("b.gate", tenant_id="tenant-b", client_id="client-b")
        amira = repo.create_account(
            domain_a.domain_id,
            "amira",
            role_id="owner",
            password_hash=hash_password("your-password"),
        )
        repo.create_account(
            domain_b.domain_id,
            "omar",
            role_id="owner",
            password_hash=hash_password("your-password"),
        )
        listed_a = {a.account_id for a in repo.list_accounts(domain_a.domain_id)}
        listed_b = {a.account_id for a in repo.list_accounts(domain_b.domain_id)}
        cross = repo.get_account_by_login("b.gate", "amira")
        db.close(conn)
        ok = listed_a == {amira.account_id} and amira.account_id not in listed_b and cross is None
        return ok, f"app_tenant_isolation: scoped-read ok={ok}"
    except Exception as e:  # noqa: BLE001
        return False, f"app_tenant_isolation: {type(e).__name__}: {e}"
    finally:
        _discard_scratch(work)


def _gate_app_memory_store_isolation() -> tuple[bool, str]:
    """One account's governed memory never appears in another's store."""
    import tempfile

    from helix_codex_app import db
    from helix_codex_app.integration.memory_bridge import AccountMemoryStore
    from helix_codex_app.security.accounts import AccountRepository
    from helix_codex_app.security.passwords import hash_password

    work = tempfile.mkdtemp(prefix="hp_gate_app_memiso_")
    try:
        db_path = os.path.join(work, "app.db")
        memory_root = os.path.join(work, "memory_stores")
        conn = db.connect(db_path=db_path)
        db._init_schema(conn)
        repo = AccountRepository(conn)
        domain = repo.create_domain("a.gate", tenant_id="tenant-a", client_id="client-a")
        amira = repo.create_account(
            domain.domain_id, "amira", role_id="owner", password_hash=hash_password("your-password")
        )
        omar = repo.create_account(
            domain.domain_id,
            "omar",
            role_id="employee",
            password_hash=hash_password("your-password"),
        )
        store = AccountMemoryStore(conn=conn, memory_root=memory_root)
        mem_a = store.store_for(amira)
        mem_a.add(
            kind="recommendation",
            nature="model_inference",
            tenant_id="tenant-a",
            client_id="client-a",
            actor=amira.account_id,
            role_id="owner",
            source="helix_codex_app.release_gate",
            classification="internal",
            timestamp="2026-09-15T00:00:00+00:00",
            correlation_id="app-gate-memiso",
            confidence=0.9,
            data_mode="simulated_realistic",
            provenance={
                "correlation_id": "app-gate-memiso",
                "data_mode": "simulated_realistic",
                "basis": "release_gate_probe",
                "sources": [],
            },
        )
        tail = store.store_for(omar).retrieve(tenant_id="tenant-a")
        db.close(conn)
        ok = all(r.actor != amira.account_id for r in tail)
        return ok, f"app_memory_store_isolation: cross-account visible={not ok}"
    except Exception as e:  # noqa: BLE001
        return False, f"app_memory_store_isolation: {type(e).__name__}: {e}"
    finally:
        _discard_scratch(work)


def _gate_app_migration_drift() -> tuple[bool, str]:
    """db.py and the alembic head must agree token-for-token."""
    from helix_codex_app.scripts.check_app_migration_drift import check_drift

    try:
        errors, report = check_drift()
    except Exception as e:  # noqa: BLE001
        return False, f"app_migration_drift: could not run: {type(e).__name__}: {e}"
    ok = not errors
    return (
        ok,
        f"app_migration_drift: store={report['store_objects']} migration={report['migration_objects']} "
        f"errors={len(errors)}",
    )


def _gate_app_pwa_assets() -> tuple[bool, str]:
    """The installable shell — manifest, icons, service worker, offline page."""
    import json
    import re

    app_static = ROOT / "helix_codex_app" / "static"
    manifest_p = app_static / "manifest.webmanifest"
    sw_p = app_static / "sw.js"
    offline_p = app_static / "offline.html"
    if not (manifest_p.exists() and sw_p.exists() and offline_p.exists()):
        missing = [
            name
            for name, p in (("manifest", manifest_p), ("sw", sw_p), ("offline", offline_p))
            if not p.exists()
        ]
        return False, f"app_pwa_assets: missing {', '.join(missing)}"
    try:
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        icons = manifest.get("icons") or []
        icon_ok = all(
            (app_static / icon.get("src", "").replace("/static/", "")).is_file() for icon in icons
        )
        start_ok = manifest.get("start_url") == "/app" and manifest.get("display") == "standalone"
        sw_text = sw_p.read_text(encoding="utf-8")
        match = re.search(r'CACHE_NAME\s*=\s*"([^"]+)"', sw_text)
        sw_ok = bool(match and re.search(r"-v\d+$", match.group(1)))
        offline_ok = "offline" in offline_p.read_text(encoding="utf-8").lower()
        ok = icon_ok and start_ok and sw_ok and offline_ok
        return (
            ok,
            f"app_pwa_assets: icons={len(icons)}/valid={icon_ok} start={start_ok} "
            f"sw={sw_ok} offline={offline_ok}",
        )
    except Exception as e:  # noqa: BLE001
        return False, f"app_pwa_assets: {type(e).__name__}: {e}"


GATE_IMPL = {
    "repository_state": _gate_repository_state,
    "reproducible_install": _gate_reproducible_install,
    "configuration_validation": _gate_configuration_validation,
    "dependency_locking": _gate_dependency_locking,
    "startup_readiness": _gate_startup_readiness,
    "backup_restore": _gate_backup_restore,
    "rollback": _gate_rollback,
    "data_isolation": _gate_data_isolation,
    "audit_integrity": _gate_audit_integrity,
    "security_checks": _gate_security_checks,
    "failure_recovery": _gate_failure_recovery,
    "performance_limits": _gate_performance_limits,
    "operator_readiness": _gate_operator_readiness,
    "release_approval": _gate_release_approval,
    "signed_production_evidence": _gate_signed_production_evidence,
    "certified_data_isolation": _gate_certified_data_isolation,
    "external_observer_audit": _gate_external_observer_audit,
    "production_deployment_architecture": _gate_production_deployment_architecture,
    "disaster_recovery_evidence": _gate_disaster_recovery_evidence,
    "operational_ownership": _gate_operational_ownership,
    "incident_oncall_ownership": _gate_incident_oncall_ownership,
    "security_review": _gate_security_review,
    "legal_privacy_review": _gate_legal_privacy_review,
    "app_auth_boundary": _gate_app_auth_boundary,
    "app_session_fail_closed": _gate_app_session_fail_closed,
    "app_tenant_isolation": _gate_app_tenant_isolation,
    "app_memory_store_isolation": _gate_app_memory_store_isolation,
    "app_migration_drift": _gate_app_migration_drift,
    "app_pwa_assets": _gate_app_pwa_assets,
}


def run_gate(
    profile: str = "production_candidate",
    num_soak_workflows: int = 5,
    write_evidence: bool = True,
) -> Dict[str, Any]:
    """Run all gate checks for the profile and classify deterministically."""
    required = profiles.gates_required_for(profile)
    results: Dict[str, Any] = {}
    green: List[str] = []
    for gate in required:
        impl = GATE_IMPL.get(gate)
        if impl is None:
            results[gate] = {"ok": False, "detail": "no implementation"}
            continue
        try:
            ok, detail = impl()
            results[gate] = {"ok": bool(ok), "detail": detail}
            if ok:
                green.append(gate)
        except Exception as e:  # noqa: BLE001
            results[gate] = {"ok": False, "detail": f"{type(e).__name__}: {e}"}

    # release approval gate
    approval = results.get("release_approval", {}).get("ok", False)
    classification = profiles.classify_from_gate_results(profile, green, release_approved=approval)

    rep = observability.run_observability_report()
    harness_res = harness_mod.run_harness(num_soak_workflows=num_soak_workflows)

    manifest = manifest_mod.build_manifest(
        classification=classification,
        profile=profile,
        release_approved=approval,
    )

    summary = {
        "created_at": _now(),
        "profile": profile,
        "classification": classification,
        "all_gates_green": bool(not [g for g in required if not results.get(g, {}).get("ok")]),
        "gates": results,
        "harness": {"all_ok": harness_res["all_ok"], "summary": harness_res["summary"]},
        "observability": {"all_ok": rep["all_ok"]},
        "evidence_dir": "",
        "manifest_path": "",
    }

    if write_evidence:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ev_dir = ROOT / "evidence" / "releases" / ts
        ev_dir.mkdir(parents=True, exist_ok=True)
        _write_json(ev_dir / "release-gate-summary.json", summary)
        _write_json(ev_dir / "release-manifest.json", manifest)
        _write_json(ev_dir / "harness-results.json", harness_res)
        manifest["evidence_refs"] = [str(ev_dir.relative_to(ROOT))]
        manifest_mod.write_manifest(manifest, "release/release-manifest.json")
        summary["evidence_dir"] = str(ev_dir)
        summary["manifest_path"] = str(ROOT / "release" / "release-manifest.json")

    permitted = classification in profiles.ALLOWED_FINAL_CLASSIFICATIONS
    summary["permitted_c8_outcome"] = permitted
    summary["exit_code"] = 0 if permitted else 1
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    profile = "production_candidate"
    if "--profile" in argv:
        i = argv.index("--profile")
        if i + 1 < len(argv):
            profile = argv[i + 1]
    if "--soak" in argv:
        i = argv.index("--soak")
        if i + 1 < len(argv):
            pass  # soak count parsed in python path
    if profile not in profiles.PROFILE_ORDER:
        print(f"ERROR: unknown profile {profile!r}")
        return 2
    summary = run_gate(profile=profile)
    print(json.dumps(summary, default=str, indent=2))
    return summary["exit_code"]


if __name__ == "__main__":
    sys.exit(main())

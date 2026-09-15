"""
Helix Prime Codex C8 — release gate orchestrator.

Runs every gate in the requested profile, aggregates pass/fail, and emits a
deterministic classification. Final classifications allowed by C8:
    CONTROLLED_PILOT_READY  (profile=controlled_pilot, all gates green)
    PRODUCTION_CANDIDATE    (profile=production_candidate, all gates green)
An unqualified PRODUCTION label is NEVER emitted by this gate.

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
import sys
import tempfile
from typing import Any, Dict, List, Optional

from release import harness as harness_mod
from release import manifest as manifest_mod
from release import observability, profiles, security_gate

ROOT = manifest_mod.ROOT

# Gate -> implementation. Each callable returns (ok: bool, detail: str).
GATE_IMPL: Dict[str, str] = {}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, indent=2)


# ── individual gate checks ─────────────────────────────────────────────────


def _gate_repository_state() -> tuple[bool, str]:
    manifest_mod.build_manifest()  # ensure git + runtime detectable
    return True, "repository_state: git + runtime detectable"


def _gate_reproducible_install() -> tuple[bool, str]:
    p = ROOT / "release" / "requirements.lock.txt"
    if not p.exists():
        return False, "missing release/requirements.lock.txt"
    lines = [
        ln
        for ln in p.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    ok = len(lines) > 0
    return ok, f"reproducible_install: {len(lines)} declared deps"


def _gate_configuration_validation() -> tuple[bool, str]:
    prof = profiles.load_profiles()
    ok_gates = len(prof.get("gates", profiles.GATE_NAMES)) >= 10
    ok_profiles = len(prof.get("profiles", profiles.PROFILE_ORDER)) >= 4
    import json as _json

    schema_p = ROOT / "release" / "manifest.schema.json"
    try:
        _json.loads(schema_p.read_text(encoding="utf-8")) if schema_p.exists() else None
        ok_schema = schema_p.exists()
    except Exception:
        ok_schema = False
    ok = ok_gates and ok_profiles and ok_schema
    return ok, f"configuration: gates={ok_gates} profiles={ok_profiles} schema={ok_schema}"


def _gate_dependency_locking() -> tuple[bool, str]:
    p = ROOT / "release" / "requirements.lock.txt"
    ok = p.exists() and p.stat().st_size > 0
    return ok, f"dependency_locking: lock present={ok}"


def _gate_startup_readiness() -> tuple[bool, str]:
    rep = observability.run_observability_report()
    ok = rep["all_ok"]
    startup_ok = bool(rep["checks"]["startup"].get("slo_met"))
    ready = bool(rep["checks"]["readiness"].get("ready"))
    return ok, f"startup_readiness: all_ok={ok} startup_ok={startup_ok} ready={ready}"


def _gate_backup_restore() -> tuple[bool, str]:
    # Synthetic-state backup/restore (never mutates live DBs).
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
        backup.restore_state(backup_dir, restore_dir, repo_root=work, schema_ok=True)
        # verify restored audit chain
        from security.audit import AuditTrail as AT2

        t2 = AT2(db_path=os.path.join(restore_dir, "security", "audit.db"))
        valid, msg = t2.verify_chain()
        t2.close()
        ok = valid
        return ok, f"backup_restore: restored audit chain valid={valid} ({msg})"
    except Exception as e:  # noqa: BLE001
        return False, f"backup_restore: {type(e).__name__}: {e}"


def _gate_rollback() -> tuple[bool, str]:
    from release import backup

    prev = {"git_commit": "AAAA", "classification": "PRODUCTION_CANDIDATE", "version": "0.9.0-c8"}
    cur = {"git_commit": "BBBB", "classification": "PRODUCTION_CANDIDATE", "version": "0.9.0-c8"}
    import os
    import tempfile

    work = tempfile.mkdtemp(prefix="hp_gate_rb_")
    path = os.path.join(work, "release-manifest.json")
    backup.rollback_manifest(prev, cur, target_path=path)
    out = json.load(open(path, encoding="utf-8"))
    ok = out["git_commit"] == "AAAA" and "_rolled_back_from" in out
    return ok, f"rollback: previous identity restored ok={ok}"


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


def _gate_operator_readiness() -> tuple[bool, str]:
    docs = [
        "docs/release/operator-runbook.md",
        "docs/release/incident-response.md",
        "docs/release/backup-restore-guide.md",
        "docs/release/controlled-pilot-pack.md",
    ]
    present = [d for d in docs if (ROOT / d).exists()]
    ok = len(present) == len(docs)
    return ok, f"operator_readiness: {len(present)}/{len(docs)} docs present"


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
# These are external blockers that a local automated run CANNOT satisfy. Each
# returns red with a documented reason so the production profile fails closed
# and can never be claimed locally. They are recorded (not fabricated) here.
def _prod_gate_reason(name: str, evidence_type: str) -> tuple[bool, str]:
    return False, f"{name}: requires {evidence_type} — not present (production NOT approved)"


def _gate_signed_production_evidence() -> tuple[bool, str]:
    return _prod_gate_reason("signed_production_evidence", "external signed production evidence")


def _gate_certified_data_isolation() -> tuple[bool, str]:
    return _prod_gate_reason("certified_data_isolation", "certified tenant/data isolation")


def _gate_external_observer_audit() -> tuple[bool, str]:
    return _prod_gate_reason("external_observer_audit", "independent external observer audit")


def _gate_production_deployment_architecture() -> tuple[bool, str]:
    return _prod_gate_reason(
        "production_deployment_architecture", "reviewed deployment architecture"
    )


def _gate_disaster_recovery_evidence() -> tuple[bool, str]:
    return _prod_gate_reason(
        "disaster_recovery_evidence", "disaster-recovery evidence from production"
    )


def _gate_operational_ownership() -> tuple[bool, str]:
    return _prod_gate_reason("operational_ownership", "assigned operational ownership")


def _gate_incident_oncall_ownership() -> tuple[bool, str]:
    return _prod_gate_reason("incident_oncall_ownership", "assigned incident/on-call ownership")


def _gate_security_review() -> tuple[bool, str]:
    return _prod_gate_reason("security_review", "signed security review")


def _gate_legal_privacy_review() -> tuple[bool, str]:
    return _prod_gate_reason("legal_privacy_review", "signed legal/privacy review where applicable")


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
        )
        tail = store.store_for(omar).retrieve(tenant_id="tenant-a")
        db.close(conn)
        ok = all(r.actor != amira.account_id for r in tail)
        return ok, f"app_memory_store_isolation: cross-account visible={not ok}"
    except Exception as e:  # noqa: BLE001
        return False, f"app_memory_store_isolation: {type(e).__name__}: {e}"


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

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

from release import manifest as manifest_mod
from release import observability, profiles, security_gate
from release import harness as harness_mod

ROOT = manifest_mod.ROOT

# Gate -> implementation. Each callable returns (ok: bool, detail: str).
GATE_IMPL: Dict[str, str] = {}


def _now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


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
        ln for ln in p.read_text(encoding="utf-8").splitlines()
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
        from security.audit import AuditTrail, AuditRecord
        db = os.path.join(work, "control_plane", "workflow.db")
        store = Store(db_path=db)
        store.close()
        audit_db = os.path.join(work, "security", "audit.db")
        trail = AuditTrail(db_path=audit_db)
        prev = None
        for i in range(2):
            rec = AuditRecord.new(event_type="br", actor="gate", actor_type="service",
                                  decision="succeeded", previous_hash=prev)
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
    import tempfile
    import os
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
    from release import harness as h
    res = h._check("audit_integrity", h._check_audit_integrity)
    return bool(res["ok"]), res["detail"]


def _gate_security_checks() -> tuple[bool, str]:
    res = security_gate.run_security_gate(scan_subdirs=None)
    ok = res["all_ok"]
    detail = "; ".join(f"{k}:{v['ok']}" for k, v in res.items() if k != "all_ok")
    return ok, f"security_checks: all_ok={ok} ({detail})"


def _gate_failure_recovery() -> tuple[bool, str]:
    h = harness_mod.run_harness(num_soak_workflows=3)
    fail_sensitive = ["engine_timeout", "unavailable_ollama", "unavailable_sibling",
                      "corrupted_event", "corrupted_db", "interrupted_workflow",
                      "c7_transport_retry_deadletter"]
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
        return approved and scope_ok, (
            f"release_approval: approved={approved} scope_ok={scope_ok}"
        )
    except Exception as e:  # noqa: BLE001
        return False, f"release_approval: {type(e).__name__}: {e}"


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
    classification = profiles.classify_from_gate_results(
        profile, green, release_approved=approval
    )

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

"""
Helix Prime Codex C8 — can-fail proof for the seven unaudited core gates.

A gate that cannot be made red is a nominal control (§18.2 A0.1): it reports a
property it never measures. Every test here constructs a bad state and asserts
the gate refuses it, and where a gate used to accept that bad state the test also
pins what the old predicate would have said, so the fix is proven and not just
asserted.

Four gates — `audit_integrity`, `security_checks`, `failure_recovery`,
`performance_limits` — are frozen by policy and are not probed for
falsifiability here. Their bodies are pinned by hash instead: a body pin
survives the line renumbering that inserting code above them causes, so an
accidental edit is caught without the pin crying wolf on a harmless move.

All tests are deterministic and isolated (temp state); they never mutate the live
shared control-plane/audit DBs or the committed release artefacts.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import pathlib
import re

import pytest

from release import gate, profiles

# ── helpers ────────────────────────────────────────────────────────────────


def _serve_edited_profiles(monkeypatch, **edits):
    """Hand `configuration_validation` an edited copy of the canonical file.

    The real file is read first, so the edit is the only difference. Nested lists
    are rebound rather than mutated, so the module-level constants stay intact
    even if a caller forgets to undo the patch.
    """
    data = dict(profiles.load_profiles())
    data["gates"] = list(data["gates"])
    data["app_gates"] = list(data["app_gates"])
    data["required_gates"] = {p: list(gs) for p, gs in data["required_gates"].items()}
    data.update(edits)
    monkeypatch.setattr(gate.profiles, "load_profiles", lambda rel_path=None: data)
    return data


def _body(name: str) -> str:
    """Source text of one top-level function in `release/gate.py`, sans trailing blanks."""
    src = pathlib.Path(gate.__file__).read_text(encoding="utf-8")
    lines = src.splitlines()
    starts = {
        m.group(1): i for i, line in enumerate(lines) if (m := re.match(r"^def (\w+)\(", line))
    }
    order = sorted(starts.items(), key=lambda kv: kv[1])
    for idx, (fn, start) in enumerate(order):
        if fn == name:
            end = order[idx + 1][1] if idx + 1 < len(order) else len(lines)
            return "\n".join(lines[start:end]).rstrip()
    raise AssertionError(f"release/gate.py defines no {name}")


def _code_only(fn) -> str:
    """A function's executable source, with its docstring removed.

    A source-text assertion that also matches prose is a trap: this gate's own
    docstring names the leaking idiom it removed, so a naive `in src` check fails
    on the fix's own documentation. The docstring is dropped before matching, so
    the assertion measures code and not commentary.
    """
    node = ast.parse(inspect.getsource(fn)).body[0]
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        node.body = node.body[1:]
    return ast.unparse(node)


OPERATOR_DOCS = (
    "docs/release/operator-runbook.md",
    "docs/release/incident-response.md",
    "docs/release/backup-restore-guide.md",
    "docs/release/controlled-pilot-pack.md",
)


# ── configuration_validation ───────────────────────────────────────────────


def test_configuration_validation_is_green_on_the_committed_repo():
    ok, detail = gate.GATE_IMPL["configuration_validation"]()
    assert ok is True, detail


def test_configuration_validation_refuses_a_gate_with_no_implementation(monkeypatch):
    data = _serve_edited_profiles(monkeypatch)
    data["gates"].append("a_gate_that_was_never_written")
    ok, detail = gate.GATE_IMPL["configuration_validation"]()
    assert ok is False
    assert "a_gate_that_was_never_written" in detail


def test_configuration_validation_refuses_a_deleted_gate_whose_code_remains(monkeypatch):
    """The attack the old `len(gates) >= 10` floor could not see.

    Deleting a gate from the source of truth removes it from the set the runner
    iterates, so a release can be classified green having satisfied one fewer
    gate. The floor was 10 against a file that declares 14, so four gates could
    go before this check noticed. Closure against the implementation registry
    catches the very first deletion.
    """
    data = _serve_edited_profiles(monkeypatch)
    dropped = "backup_restore"
    data["gates"] = [g for g in data["gates"] if g != dropped]
    data["required_gates"] = {
        p: [g for g in gs if g != dropped] for p, gs in data["required_gates"].items()
    }

    assert len(data["gates"]) >= 10, "the old floor would still have been satisfied"

    ok, detail = gate.GATE_IMPL["configuration_validation"]()
    assert ok is False
    assert dropped in detail


def test_configuration_validation_refuses_a_production_gate_without_evidence(monkeypatch):
    """A production-only gate with no evidence type is a gate nothing can open.

    `app_pwa_assets` is implemented but is not a production gate, so promoting it
    into the production profile must be refused: the production path has no
    evidence requirement to satisfy for it.
    """
    data = _serve_edited_profiles(monkeypatch)
    data["required_gates"]["production"].append("app_pwa_assets")
    ok, detail = gate.GATE_IMPL["configuration_validation"]()
    assert ok is False
    assert "app_pwa_assets" in detail


def test_configuration_validation_refuses_a_malformed_manifest_schema(monkeypatch, tmp_path):
    schema_dir = tmp_path / "release"
    schema_dir.mkdir(parents=True)
    (schema_dir / "manifest.schema.json").write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["configuration_validation"]()
    assert ok is False
    assert "schema=False" in detail


def test_configuration_validation_refuses_a_schema_that_is_not_an_object(monkeypatch, tmp_path):
    schema_dir = tmp_path / "release"
    schema_dir.mkdir(parents=True)
    (schema_dir / "manifest.schema.json").write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["configuration_validation"]()
    assert ok is False
    assert "schema=False" in detail


# ── startup_readiness ──────────────────────────────────────────────────────


def test_startup_readiness_is_red_when_storage_is_unwritable(monkeypatch):
    """The red cause has to be visible; it used to be hidden.

    `run_observability_report` folds the storage check into `all_ok`, but the
    detail string reported only startup and readiness. A storage-only failure
    therefore rendered as `all_ok=False startup_ok=True ready=True` — a red gate
    that named no cause.
    """
    monkeypatch.setattr(
        gate.observability,
        "run_observability_report",
        lambda db_path=None: {
            "checks": {
                "startup": {"slo_met": True},
                "readiness": {"ready": True},
                "storage": {"all_writable": False},
            },
            "all_ok": False,
        },
    )
    ok, detail = gate.GATE_IMPL["startup_readiness"]()
    assert ok is False
    assert "storage_writable=False" in detail


def test_startup_readiness_is_red_when_the_startup_slo_is_missed(monkeypatch):
    monkeypatch.setattr(
        gate.observability,
        "run_observability_report",
        lambda db_path=None: {
            "checks": {
                "startup": {"slo_met": False},
                "readiness": {"ready": True},
                "storage": {"all_writable": True},
            },
            "all_ok": False,
        },
    )
    ok, detail = gate.GATE_IMPL["startup_readiness"]()
    assert ok is False
    assert "startup_ok=False" in detail


# ── backup_restore ─────────────────────────────────────────────────────────


def test_restore_state_really_enforces_schema_compatibility(tmp_path):
    """The enforcement the docstring promises does exist — when asked for it."""
    from release import backup

    work = tmp_path / "w"
    (work / "control_plane").mkdir(parents=True)
    backup.backup_state(str(work / "backup"), repo_root=str(work))
    with pytest.raises(backup.BackupError):
        backup.restore_state(
            str(work / "backup"),
            str(work / "restored"),
            repo_root=str(work),
            schema_ok=False,
        )


def test_a_literal_schema_ok_true_hides_an_incompatible_backup(tmp_path):
    """Can-fail proof of the fix, not merely of the gate.

    Given the same incompatible pair, restoring with the old hardcoded
    `schema_ok=True` raises nothing — which is exactly what the gate used to do,
    so its "fail closed" claim was an assertion rather than a check.
    """
    from release import backup

    work = tmp_path / "w"
    (work / "control_plane").mkdir(parents=True)
    backup.backup_state(str(work / "backup"), repo_root=str(work))
    recorded = json.loads((work / "backup" / "backup-manifest.json").read_text(encoding="utf-8"))
    assert recorded["schema_versions"] != {"incompatible": "9.9"}

    report = backup.restore_state(
        str(work / "backup"),
        str(work / "restored"),
        repo_root=str(work),
        schema_ok=True,
    )
    assert report is not None


def test_backup_restore_is_red_when_the_recorded_schema_does_not_match(monkeypatch):
    """A backup from another release must be refused, not asserted away.

    The gate passed `schema_ok=True` as a literal, so this divergence was
    invisible and `restore_state`'s fail-closed branch could never fire. The
    backup's recorded versions are rewritten here to stand for a backup taken
    under a different schema, and the gate must refuse the restore.
    """
    from release import backup

    real_backup_state = backup.backup_state

    def _records_a_foreign_schema(backup_dir, repo_root=None, state_rels=None):
        result = real_backup_state(backup_dir, repo_root=repo_root, state_rels=state_rels)
        manifest_path = pathlib.Path(backup_dir, "backup-manifest.json")
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded["schema_versions"] = {"a_schema_from_another_release": "9.9"}
        manifest_path.write_text(json.dumps(recorded, indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr(backup, "backup_state", _records_a_foreign_schema)
    ok, detail = gate.GATE_IMPL["backup_restore"]()
    assert ok is False
    assert "schema" in detail.lower()


def test_backup_restore_reports_the_schema_comparison_it_made():
    ok, detail = gate.GATE_IMPL["backup_restore"]()
    assert ok is True, detail
    assert "schema_ok=" in detail


# ── rollback ───────────────────────────────────────────────────────────────


def test_rollback_is_red_when_the_previous_identity_is_not_restored(monkeypatch):
    from release import backup

    def _writes_the_wrong_identity(prev, cur, target_path=None):
        pathlib.Path(target_path).write_text(
            json.dumps({"git_commit": "BBBB", "classification": "PRODUCTION_CANDIDATE"}),
            encoding="utf-8",
        )

    monkeypatch.setattr(backup, "rollback_manifest", _writes_the_wrong_identity)
    ok, detail = gate.GATE_IMPL["rollback"]()
    assert ok is False
    assert "ok=False" in detail


def test_rollback_is_red_when_the_provenance_marker_is_missing(monkeypatch):
    from release import backup

    def _drops_provenance(prev, cur, target_path=None):
        pathlib.Path(target_path).write_text(
            json.dumps({"git_commit": "AAAA", "classification": "PRODUCTION_CANDIDATE"}),
            encoding="utf-8",
        )

    monkeypatch.setattr(backup, "rollback_manifest", _drops_provenance)
    ok, detail = gate.GATE_IMPL["rollback"]()
    assert ok is False
    assert "ok=False" in detail


def test_rollback_closes_the_manifest_it_reads():
    """The read is a context manager, so no descriptor is left to the collector.

    `json.load(open(path))` hands the handle to the GC. This repo carries a whole
    fixture (C0) about Windows handle exhaustion, so the idiom is pinned — against
    the gate's code, not its docstring.
    """
    code = _code_only(gate._gate_rollback)
    assert "json.load(open(" not in code
    assert "with open(" in code


# ── data_isolation ─────────────────────────────────────────────────────────


def test_data_isolation_is_red_when_deny_by_default_fails(monkeypatch):
    monkeypatch.setattr(
        gate.security_gate, "check_deny_by_default", lambda: {"ok": False, "detail": "leaky"}
    )
    ok, detail = gate.GATE_IMPL["data_isolation"]()
    assert ok is False
    assert "deny_default=False" in detail


def test_data_isolation_is_red_when_classification_fails(monkeypatch):
    monkeypatch.setattr(
        gate.security_gate, "check_classification", lambda: {"ok": False, "detail": "unlabelled"}
    )
    ok, detail = gate.GATE_IMPL["data_isolation"]()
    assert ok is False
    assert "class=False" in detail


def test_data_isolation_is_red_when_tenant_isolation_fails(monkeypatch):
    from release import harness

    monkeypatch.setattr(harness, "_check_tenant_isolation", lambda: {"ok": False, "detail": "bled"})
    ok, detail = gate.GATE_IMPL["data_isolation"]()
    assert ok is False
    assert "data_isolation_ok=False" in detail


# ── operator_readiness ─────────────────────────────────────────────────────


def _lay_operator_docs(root: pathlib.Path, contents: str) -> None:
    for rel in OPERATOR_DOCS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


def test_operator_readiness_is_green_on_the_committed_repo():
    ok, detail = gate.GATE_IMPL["operator_readiness"]()
    assert ok is True, detail


def test_operator_readiness_refuses_a_present_but_empty_document(monkeypatch, tmp_path):
    """Existence is not readiness: a zero-byte runbook used to pass this gate."""
    _lay_operator_docs(tmp_path, "")
    monkeypatch.setattr(gate, "ROOT", tmp_path)

    assert all(
        (tmp_path / rel).exists() for rel in OPERATOR_DOCS
    ), "the old existence-only predicate would have been green"

    ok, detail = gate.GATE_IMPL["operator_readiness"]()
    assert ok is False
    assert "0/4" in detail


def test_operator_readiness_refuses_a_whitespace_only_document(monkeypatch, tmp_path):
    _lay_operator_docs(tmp_path, "   \n\n\t\n")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["operator_readiness"]()
    assert ok is False
    assert "0/4" in detail


def test_operator_readiness_refuses_a_missing_document(monkeypatch, tmp_path):
    _lay_operator_docs(tmp_path, "real content")
    (tmp_path / OPERATOR_DOCS[0]).unlink()
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["operator_readiness"]()
    assert ok is False
    assert "3/4" in detail


# ── release_approval ───────────────────────────────────────────────────────


def _write_go_no_go(root: pathlib.Path, payload) -> None:
    rel = root / "release"
    rel.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (rel / "go-no-go.json").write_text(text, encoding="utf-8")


def test_release_approval_is_green_on_the_committed_record():
    ok, detail = gate.GATE_IMPL["release_approval"]()
    assert ok is True, detail


def test_release_approval_is_red_when_the_file_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["release_approval"]()
    assert ok is False
    assert "missing" in detail


def test_release_approval_is_red_when_not_approved(monkeypatch, tmp_path):
    _write_go_no_go(tmp_path, {"approved": False, "data_scope": "SYNTHETIC_OR_CONSENTED_ONLY"})
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["release_approval"]()
    assert ok is False
    assert "approved=False" in detail


def test_release_approval_is_red_on_a_wrong_data_scope(monkeypatch, tmp_path):
    _write_go_no_go(tmp_path, {"approved": True, "data_scope": "LIVE_PRODUCTION_DATA"})
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["release_approval"]()
    assert ok is False
    assert "scope_ok=False" in detail


def test_release_approval_is_red_on_malformed_json(monkeypatch, tmp_path):
    _write_go_no_go(tmp_path, "{ not json")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    ok, detail = gate.GATE_IMPL["release_approval"]()
    assert ok is False
    assert "release_approval" in detail


# ── the four frozen gates, pinned by body rather than by line range ────────

#: sha256 of each frozen gate's body text. A body pin is deliberately not a
#: line-range pin: `gate.py` grows, and inserting code above a frozen gate moves
#: its line numbers while leaving the rule untouched. The plan's freeze is a
#: statement about behaviour, so it is enforced against behaviour.
_FROZEN_GATE_BODIES = {
    "_gate_audit_integrity": ("8a1101cdb3276516a516033b0c942a1e05388dd72bf65289761c1d14379013c7"),
    "_gate_security_checks": ("d54baee1fe9d28009d9b13a742f9818b1ac9748fa825cd259c14f6f9700704d2"),
    "_gate_failure_recovery": ("89de29713bfb0a30fc158dec7583d5cc8eb8f5da1100cb6ee8e410ba58018b09"),
    "_gate_performance_limits": (
        "8e40a191eeb9a4af6bd9d907c6b0a9f96fa6141bf9db1a9961334c5db4e256e3"
    ),
}


@pytest.mark.parametrize("name", sorted(_FROZEN_GATE_BODIES))
def test_frozen_gate_body_is_unchanged(name):
    digest = hashlib.sha256(_body(name).encode()).hexdigest()
    assert digest == _FROZEN_GATE_BODIES[name], (
        f"{name} is frozen by policy; if the change is intended, re-pin the digest "
        f"and record why in AGENTS.md"
    )

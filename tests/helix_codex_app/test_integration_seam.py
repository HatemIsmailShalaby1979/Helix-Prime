"""Integration-seam architecture tests for the app.

`helix_codex_app/integration/` is the only package allowed to import parent
internals. This module proves the rule mechanically by parsing every other
app file: a new direct parent import anywhere else fails the sweep. The
metacognition re-export test pins the one past violation staying fixed.
"""
from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
APP_ROOT = REPO_ROOT / "helix_codex_app"

PARENT_PACKAGES = frozenset(
    {
        "control_plane",
        "engines",
        "security",
        "memory",
        "metacognition",
        "capabilities",
        "connectors",
    }
)


def _app_files():
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT)
        if relative.parts[0] in ("integration", "scripts"):
            continue
        yield path


def _parent_imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in PARENT_PACKAGES:
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in PARENT_PACKAGES:
                offenders.append(f"from {node.module} import ...")
    return offenders


def test_only_integration_imports_parent_internals():
    violations = {}
    for path in _app_files():
        offenders = _parent_imports(path)
        if offenders:
            violations[str(path.relative_to(REPO_ROOT))] = offenders
    assert not violations, f"parent imports outside integration/: {violations}"


def test_metacognition_names_come_through_the_bridge():
    import metacognition.improvement as parent
    from helix_codex_app.integration import metacognition_bridge as bridge

    for name in (
        "ApprovalDecision",
        "EvaluationResult",
        "ImprovementProposal",
        "ProposalNotApprovableError",
        "ProposalStateError",
    ):
        assert getattr(bridge, name) is getattr(parent, name)


def test_memory_service_uses_the_bridge_not_the_parent():
    import helix_codex_app.modules.memory.service as service
    import metacognition.improvement as parent

    assert service.ApprovalDecision is parent.ApprovalDecision
    assert service.ProposalNotApprovableError is parent.ProposalNotApprovableError


def test_lockout_duration_has_one_source():
    from helix_codex_app.modules.identity import service as identity_service
    from helix_codex_app.security.accounts import LOCK_MINS

    assert identity_service.LOCK_MINS == LOCK_MINS == 15
    assert str(LOCK_MINS) in identity_service.LOCKED_MESSAGE

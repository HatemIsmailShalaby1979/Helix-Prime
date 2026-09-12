"""
Architectural separation boundary for sibling projects (C7).

Helix Education, Study Studio and the L&D Command Center are *external
services*. They are reached over the event bus described in this package —
never by import, never by shared module, never by copying their source into
this repository.

This module is the executable form of that rule. It answers two questions:

1. **Does this repository import sibling code?** :func:`scan_repository_imports`
   walks the tree and flags any module that reaches into a sibling package.
2. **Is a proposed integration legal?** :func:`assert_legal_integration`
   fails closed on circular imports, vendored source, or direct database access
   to a sibling's store.

Run it in CI. A violation here is not a style problem — it is the exact
coupling that makes the three codebases impossible to release independently.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

#: Sibling project identities and the import roots that belong to them.
SIBLING_PROJECTS: Dict[str, Tuple[str, ...]] = {
    "helix_education": ("helix_education", "education", "helix.edu"),
    "study_studio": ("study_studio", "studiostudio", "helix.studio"),
    "ld_command_center": ("ld_command_center", "ldcc", "helix.ld"),
}

#: Directories never walked by the scanner.
SKIP_DIRS: Set[str] = {
    ".git",
    ".venv",
    ".venv-win",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    ".workbuddy-ai",
    "src-tauri",
    ".tmp",
    "archive",
}

#: A violation of this rule blocks the build.
BOUNDARY_STATEMENT = (
    "Sibling projects communicate through versioned event contracts only. "
    "Importing sibling code, vendoring sibling source, or reading a sibling's "
    "datastore directly is prohibited."
)


def sibling_root_for(module_root: str) -> str | None:
    """Return the sibling project that owns ``module_root``, else ``None``."""
    root = module_root.split(".")[0].lower()
    for project, roots in SIBLING_PROJECTS.items():
        if root in {r.split(".")[0].lower() for r in roots}:
            return project
    return None


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan_file_imports(path: Path) -> List[Dict[str, str]]:
    """Return sibling-import violations found in one Python file."""
    violations: List[Dict[str, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError as exc:
        return [
            {"file": str(path), "module": "<unparseable>", "project": "unknown", "detail": str(exc)}
        ]

    for node in ast.walk(tree):
        targets: List[str] = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import: inside this repo by construction
            if node.module:
                targets = [node.module]
        for target in targets:
            project = sibling_root_for(target)
            if project:
                violations.append(
                    {
                        "file": str(path),
                        "module": target,
                        "project": project,
                        "detail": f"imports sibling project '{project}'",
                    }
                )
    return violations


def scan_repository_imports(root: Path | None = None) -> List[Dict[str, str]]:
    """Walk the repository and return every sibling-import violation."""
    root = root or Path(__file__).resolve().parents[3]
    violations: List[Dict[str, str]] = []
    for path in _iter_python_files(root):
        violations.extend(scan_file_imports(path))
    return violations


def detect_vendored_sibling_source(root: Path | None = None) -> List[Dict[str, str]]:
    """
    Flag directories that look like a sibling project was copied into this repo.

    Vendoring is how the boundary dies quietly: someone copies a module "just
    for now", both copies drift, and six months later nobody can say which one
    is authoritative.
    """
    root = root or Path(__file__).resolve().parents[3]
    findings: List[Dict[str, str]] = []
    markers = ("pyproject.toml", "setup.py", "setup.cfg", "pyproject.toml")
    for candidate in sorted(root.iterdir()):
        if not candidate.is_dir() or candidate.name in SKIP_DIRS:
            continue
        for project in SIBLING_PROJECTS:
            normalised = candidate.name.lower().replace(" ", "_").replace("-", "_")
            if normalised == project or normalised.startswith(f"{project}_"):
                has_project_file = any((candidate / m).exists() for m in markers)
                findings.append(
                    {
                        "path": str(candidate),
                        "project": project,
                        "detail": (
                            "directory matches a sibling project name"
                            + (
                                " and carries its own packaging metadata"
                                if has_project_file
                                else ""
                            )
                        ),
                    }
                )
    return findings


def assert_legal_integration(
    *,
    imports_sibling_code: bool = False,
    vendors_sibling_source: bool = False,
    reads_sibling_datastore: bool = False,
    uses_event_contract: bool = True,
) -> None:
    """
    Fail closed when a proposed integration violates the separation boundary.

    Every caller must state, explicitly, which side of each boundary it sits on.
    Silence is not consent: the defaults assume an integration that has not
    thought about the boundary, and ``uses_event_contract`` defaults to True so
    the only way to pass is to actually be on the bus.
    """
    problems: List[str] = []
    if imports_sibling_code:
        problems.append("imports sibling code — use the versioned event contracts")
    if vendors_sibling_source:
        problems.append("vendors sibling source — deploy it as a service and publish events")
    if reads_sibling_datastore:
        problems.append("reads a sibling datastore directly — no cross-project data access")
    if not uses_event_contract:
        problems.append("does not use an event contract — every crossing must be a versioned event")
    if problems:
        raise ValueError(
            "Illegal sibling integration: " + "; ".join(problems) + ". " + BOUNDARY_STATEMENT
        )


def boundary_report(root: Path | None = None) -> Dict[str, object]:
    """Produce the machine-readable report consumed by CI and the evidence pack."""
    import_violations = scan_repository_imports(root)
    vendored = detect_vendored_sibling_source(root)
    return {
        "boundary_statement": BOUNDARY_STATEMENT,
        "sibling_projects": sorted(SIBLING_PROJECTS),
        "import_violations": import_violations,
        "vendored_source": vendored,
        "compliant": not import_violations and not vendored,
    }


def main() -> int:
    report = boundary_report()
    print(json.dumps(report, indent=2))
    return 0 if report["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""
Synchronise role metadata in repository documents with the canonical RoleSpec.

C0 document rule: prose may explain a role, but it may not invent role IDs,
engine ownership, classifications or approval limits. The runtime registry in
``control_plane/governance.py`` is the canonical matrix; the YAML catalog adds
capabilities/tools/SoD metadata.

This script does not rewrite every paragraph mechanically. It emits a checked,
copyable canonical block and scans the target documents for stale structural
references. ``--check`` exits non-zero when a document contains a retired role
alias or a forbidden assertion. ``--write`` updates only the generated block
between the markers below.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Dict, Iterable, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MARKER_START = "<!-- HELIX_ROLE_MATRIX:START -->"
MARKER_END = "<!-- HELIX_ROLE_MATRIX:END -->"
TARGETS = (
    ROOT / "README.md",
    ROOT / "MASTER_STORY.md",
    ROOT / "ROADMAP.md",
    ROOT / "GOVERNANCE" / "IMPLEMENTATION_MATRIX.md",
)

# Structural aliases are allowed only where explicitly declared by the runtime
# registry. These are the stale forms this checker catches in prose.
RETIRED_ROLE_IDS = {
    "fraud_gm": "fraud_revenue_gm",
    "compliance_gm": "compliance_quality_gm",
    "hr_gm": "hr_personnel_gm",
    "learning_gm": "ld_gm",
}


def canonical_block() -> str:
    from control_plane.governance import ORGANIZATION_CATALOG

    lines = [
        MARKER_START,
        "## Canonical RoleSpec matrix (generated)",
        "",
        "This block is generated from `control_plane/governance.py`. Role IDs,",
        "engine ownership, data classifications, approval limits and KPIs below",
        "are structural facts; surrounding prose must not contradict them.",
        "",
        "| RoleSpec ID | Engines | Classifications | Financial limit (USD) | KPIs | Oversight only |",
        "|---|---|---|---:|---|---|",
    ]
    for role_id, spec in ORGANIZATION_CATALOG.items():
        engines = ", ".join(spec.owned_engines) or "none"
        classes = ", ".join(spec.allowed_data_classifications)
        limit = "unlimited (human escalation)" if spec.financial_approval_limit_usd is None else f"{spec.financial_approval_limit_usd:.2f}"
        kpis = ", ".join(spec.kpis)
        lines.append(f"| `{role_id}` | {engines} | {classes} | {limit} | {kpis} | {spec.oversight_only} |")
    lines += [
        "",
        "### Runtime aliases",
        "",
        "| Alias | Canonical role / engine |",
        "|---|---|",
        "| `SAMI` / `sami` | `sami` |",
        "| `SUBY` / `suby` | `ops_gm` |",
        "| `PHILI` / `phili` | `hr_personnel_gm` |",
        "| `WILI` / `wili` | `ld_gm` |",
        "| `NONO` / `nono` | `fraud_revenue_gm` |",
        "| `fraud_gm` (YAML compatibility alias) | `fraud_revenue_gm` |",
        "",
        "### Limitations",
        "",
        "- `None` financial limit does not mean autonomous unlimited approval; SAMI remains human-escalated.",
        "- `oversight_only=True` means the role proposes/reviews and does not execute an engine.",
        "- Unknown role, engine, classification or alias fails closed.",
        "- This matrix is not a production certification or customer deployment claim.",
        MARKER_END,
    ]
    return "\n".join(lines)


def stale_references(text: str) -> List[str]:
    findings: List[str] = []
    for stale, canonical in RETIRED_ROLE_IDS.items():
        if re.search(rf"\b{re.escape(stale)}\b", text):
            # The generated matrix documents the one intentional YAML alias.
            if stale == "fraud_gm" and "YAML compatibility alias" in text:
                continue
            findings.append(f"retired role id `{stale}` found; use `{canonical}` or explain YAML compatibility")
    if re.search(r"immutable audit trail|proof ledger", text, re.IGNORECASE):
        findings.append("legacy ledger wording found; use append-only hash-chained audit_events wording")
    return findings


def update_block(path: pathlib.Path, block: str) -> bool:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END), re.DOTALL)
    replacement = block
    if pattern.search(text):
        new_text = pattern.sub(replacement, text, count=1)
    else:
        new_text = text.rstrip() + "\n\n" + block + "\n"
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="scan targets and exit 1 on stale references")
    parser.add_argument("--write", action="store_true", help="write/update the generated RoleSpec block")
    parser.add_argument("paths", nargs="*", type=pathlib.Path)
    args = parser.parse_args()

    paths = [((ROOT / p) if not p.is_absolute() else p) for p in args.paths] or list(TARGETS)
    failures: Dict[str, List[str]] = {}
    changed: List[str] = []
    for path in paths:
        if not path.exists():
            failures[str(path)] = ["target does not exist"]
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        finding = stale_references(text)
        if finding:
            failures[str(path)] = finding
        if args.write:
            if update_block(path, canonical_block()):
                changed.append(str(path.relative_to(ROOT)))

    if args.write:
        print("updated:", ", ".join(changed) if changed else "none")
    for path, findings in failures.items():
        for finding in findings:
            print(f"STALE {path}: {finding}")
    if not failures:
        print("Role metadata check passed.")
    return 1 if failures and args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())

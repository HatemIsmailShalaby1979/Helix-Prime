#!/usr/bin/env python3
"""
Helix Prime Codex C8 — single local release-gate command.

Usage:
    python3 scripts/release_gate.py [--profile production|production_candidate|controlled_pilot] [--soak N]

Emits a deterministic classification:
    CONTROLLED_PILOT_READY  or  PRODUCTION_CANDIDATE  or  PRODUCTION

PRODUCTION became permitted on 2026-09-20, and it is reachable only on signed
external evidence: each of the nine production-only gates needs a signature made
by a key held outside this repository, so no local run can produce the label.

NOTE — this command is not a read-only check. It writes an evidence pack and
regenerates `release/release-manifest.json`, and that write records
`release_approved` from the `release_approval` gate, which reads the local pilot
consent flag. Running it against the committed artefacts therefore flips
`release_approved` from false to true. To inspect gate outcomes without touching
the committed manifest, call
`release.gate.run_gate(profile=..., write_evidence=False)` instead.

Exit code 0 only when the emitted classification is a permitted C8 outcome.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release.gate import main  # noqa: E402  (repo-root inserted above)

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Helix Prime Codex C8 — single local release-gate command.

Usage:
    python3 scripts/release_gate.py [--profile production_candidate|controlled_pilot] [--soak N]

Emits a deterministic classification:
    CONTROLLED_PILOT_READY  or  PRODUCTION_CANDIDATE
An unqualified PRODUCTION label is NEVER emitted by this gate.

Exit code 0 only when the emitted classification is a permitted C8 outcome.
"""
from __future__ import annotations

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release.gate import main  # noqa: E402  (repo-root inserted above)

if __name__ == "__main__":
    sys.exit(main())

"""
Helix Prime Codex C8 — release package.

Holds the release profiles/boundary, manifest, backup/restore/rollback,
security gate, observability/readiness, verification harness, and the
release gate orchestrator. This package produces a PRODUCTION_CANDIDATE or
CONTROLLED_PILOT_READY classification locally, and a PRODUCTION one only when
all 23 gates are green on signed external evidence plus a release_approved
sign-off — never a bare production claim.
"""

__version__ = "0.9.0-c8"

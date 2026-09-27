"""Add the route_throttle table, reproduced verbatim from helix_codex_app/db.py.

Revision ID: 0002_route_throttle
Revises: 0001_codex_app_baseline
Create Date: 2026-09-27

Rate limits for the routes a stranger can reach need their own counters. They are
kept out of ``login_throttle`` so the enterprise sign-in path's limits are not
changed as a side effect of adding limits to the public front door. The table has
the same shape because both are fixed-window counters; the bucket key carries the
route name, so the two can never collide.

CI enforces agreement between this migration and ``db.py::_init_schema`` in both
directions via helix_codex_app/scripts/check_app_migration_drift.py.
"""
from __future__ import annotations

from alembic import op

revision = "0002_route_throttle"
down_revision = "0001_codex_app_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS route_throttle (
        bucket TEXT PRIMARY KEY,
        attempts INTEGER,
        window_start TEXT
    )
    """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS route_throttle")

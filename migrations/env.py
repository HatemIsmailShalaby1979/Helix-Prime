"""
Alembic environment for the Helix Codex OS control-plane SQLite schema.

The database location is a deployment decision, never a repository fact, so no
URL is baked in. Resolution order:

1. ``alembic -x db=<path>``        (explicit per-invocation override)
2. ``HELIX_DB_PATH`` environment   (same variable server/config.py reads)
3. ``control_plane/workflow.db``   (local-first default)

The engine is SQLite (local-first; no server, no network). This environment
must fail loudly rather than silently operate on the wrong database: it prints
the resolved target at run starts and raises if the resolved directory cannot
be created.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DEFAULT_DB_PATH = "control_plane/workflow.db"


def _resolve_db_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    db_path = x_args.get("db") or os.environ.get("HELIX_DB_PATH") or DEFAULT_DB_PATH
    return f"sqlite:///{db_path}"


def _ensure_parent(db_url: str) -> None:
    db_path = db_url.removeprefix("sqlite:///")
    if not db_path or db_path == ":memory:":
        return
    parent = os.path.dirname(os.path.abspath(db_path))
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create migration target directory {parent!r}: {exc}") from exc


def run_migrations_offline() -> None:
    _ensure_parent(url := _resolve_db_url())
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    _ensure_parent(url := _resolve_db_url())
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                render_as_batch=True,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

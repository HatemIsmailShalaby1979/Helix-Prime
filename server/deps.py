"""
Lifetime-scoped dependencies.

The control-plane :class:`~control_plane.engine.Engine` owns a SQLite
connection and an audit trail, so there is exactly one per process. It is
created at startup, registered with the six engine adapters, and closed at
shutdown. Request handlers receive it through dependency injection rather than
constructing it, which is what lets the whole spine be tested against a
temporary database.

Note that :class:`Engine` is **synchronous** and stays that way: 445 sync tests
are the safety net for the control plane. Anything that must not block the event
loop (engine calls driven from SSE) is pushed to a worker thread.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator

from control_plane.engine import Engine
from server.config import Settings, get_settings
from server.models.store import NodeStore


class EngineProvider:
    """Holds the process-wide Engine and the settings that built it."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("EngineProvider.startup() has not been called")
        return self._engine

    def startup(self) -> Engine:
        from engines.registry import register_all  # local: avoids import cycle at module load
        from security.audit import AuditTrail

        engine = Engine(
            db_path=self.settings.db_path,
            audit_db_path=self.settings.audit_db_path,
            log_path=self.settings.log_path,
        )
        register_all(engine)
        trail = AuditTrail(db_path=self.settings.audit_db_path)
        trail.close()
        self._engine = engine
        return engine

    def shutdown(self) -> None:
        if self._engine is not None:
            self._engine.close()
            self._engine = None


def get_settings_dep() -> Settings:
    return get_settings()


def get_engine_dep() -> Iterator[Engine]:
    """FastAPI dependency yielding the process Engine."""
    yield _PROVIDER.engine


# Set by create_app(); imported by deps above. Module-level state is deliberate:
# FastAPI's dependency system has no place to hang process-scoped resources
# other than app.state, and app.state is not visible to plain functions.
_PROVIDER: EngineProvider | None = None


def build_provider(settings: Settings | None = None) -> EngineProvider:
    settings = settings or get_settings()
    provider = EngineProvider(settings)
    provider.startup()
    return provider


def set_provider(provider: EngineProvider) -> None:
    global _PROVIDER  # noqa: PLW0603 - documented above
    _PROVIDER = provider


def get_provider() -> EngineProvider:
    if _PROVIDER is None:
        raise RuntimeError("no EngineProvider configured")
    return _PROVIDER


def get_engine() -> Engine:
    return get_provider().engine


@contextlib.contextmanager
def node_store() -> Iterator[NodeStore]:
    db_path = Path(str(get_provider().settings.db_path)).parent / "nodes.db"
    store = NodeStore(db_path)
    store.connect()
    try:
        yield store
    finally:
        store.close()

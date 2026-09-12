"""
Cross-platform SQLite test harness — Codex C0.

Why this exists
---------------
Windows holds an exclusive lock on an open SQLite file. A test that opens a
``Store`` (or any ``sqlite3.connect``) without closing it leaves that lock
behind, and pytest's temporary-directory cleanup then dies with::

    PermissionError: [WinError 32]  The process cannot access the file because
                                    it is being used by another process.
    NotADirectoryError: [WinError 267] The directory name is invalid.

The same tests pass on Linux, so the failure looks environmental and gets
waved off. It is not environmental — it is a leaked handle, and it masks
real teardown bugs.

What to use
-----------
``sqlite_store`` — context manager that always closes the store::

    with sqlite_store(str(tmp_path / "wf.db")) as store:
        engine = Engine(store=store)
        ...
    # connection is closed here, on every platform, on every exit path

``managed_stores`` — keep several stores alive and close them all::

    stores = managed_stores()
    a = stores.open(str(tmp_path / "a.db"))
    b = stores.open(str(tmp_path / "b.db"))
    ...
    stores.close_all()   # or rely on the context manager form

``force_release`` — last-resort cleanup before deleting a directory tree.
It checkpoints WAL, closes what it can, and retries the unlink a few times
so a still-releasing handle does not fail the run.
"""
from __future__ import annotations

import gc
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

#: Windows error codes that mean "the handle has not been released yet".
_RETRY_ERRNOS = {13, 32, 267}  # EACCES, ERROR_SHARING_VIOLATION, ERROR_DIRECTORY
_DEFAULT_ATTEMPTS = 6
_DEFAULT_BACKOFF = 0.05


def is_windows() -> bool:
    return os.name == "nt"


def _retrying(
    predicate, attempts: int = _DEFAULT_ATTEMPTS, backoff: float = _DEFAULT_BACKOFF
) -> bool:
    """Run ``predicate`` until it returns True, retrying transient lock errors."""
    for attempt in range(attempts):
        try:
            if predicate():
                return True
        except OSError as exc:
            if (
                getattr(exc, "winerror", None) not in _RETRY_ERRNOS
                and exc.errno not in _RETRY_ERRNOS
            ):
                raise
        if attempt < attempts - 1:
            gc.collect()
            time.sleep(backoff * (attempt + 1))
    return False


def checkpoint(path: str | Path) -> None:
    """
    Truncate the WAL for a database file so no sidecar survives teardown.

    Best-effort: a database that is already gone, or already closed, is fine.
    """
    try:
        conn = sqlite3.connect(str(path), timeout=1.0)
    except sqlite3.Error:
        return
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def force_release(*paths: str | Path, attempts: int = _DEFAULT_ATTEMPTS) -> None:
    """
    Checkpoint and drop every sidecar file for the given database paths.

    Call this before deleting a directory that held a SQLite database. On
    platforms other than Windows it is effectively a no-op beyond the
    checkpoint, which is cheap.
    """
    for raw in paths:
        path = Path(raw)
        checkpoint(path)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            if not sidecar.exists():
                continue
            _retrying(
                lambda s=sidecar: (s.unlink() if s.exists() else True) or True,
                attempts=attempts,
            )


def rmtree(
    path: str | Path, *, database_names: Sequence[str] = (), attempts: int = _DEFAULT_ATTEMPTS
) -> None:
    """
    Delete a directory tree that may contain SQLite databases.

    ``database_names`` lets the caller name the databases inside the tree so
    their WAL sidecars are released first — the usual cause of WinError 32.
    """
    root = Path(path)
    if not root.exists():
        return
    if database_names:
        force_release(*[root / name for name in database_names], attempts=attempts)
    else:
        for candidate in root.rglob("*.db"):
            force_release(candidate, attempts=attempts)
    _retrying(
        lambda: (shutil.rmtree(root, ignore_errors=True), not root.exists())[1], attempts=attempts
    )


@contextmanager
def sqlite_store(db_path: str | Path) -> Iterator["Store"]:  # noqa: F821
    """
    Open a control-plane ``Store`` and guarantee it is closed on exit.

    This is the replacement for the bare ``Store(db_path=...)`` calls that
    leaked handles across the suite.
    """
    from control_plane.store import Store

    store = Store(db_path=str(db_path))
    try:
        yield store
    finally:
        try:
            store.close()
        finally:
            force_release(db_path, attempts=2)


@contextmanager
def sqlite_connection(db_path: str | Path, **kwargs) -> Iterator[sqlite3.Connection]:
    """Open a raw SQLite connection that is always closed and checkpointed."""
    conn = sqlite3.connect(str(db_path), **kwargs)
    try:
        yield conn
    finally:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except sqlite3.Error:
            pass
        try:
            conn.close()
        except sqlite3.Error:
            pass
        finally:
            force_release(db_path, attempts=2)


class ManagedStores:
    """
    Owns several stores (or raw connections) and closes them all on exit.

    Used by tests that need two independent databases open at once — the
    tenant-isolation and audit-integrity tests, typically.
    """

    def __init__(self) -> None:
        self._objects: List = []

    def open(self, db_path: str | Path):
        from control_plane.store import Store

        store = Store(db_path=str(db_path))
        self._objects.append((store, str(db_path)))
        return store

    def track(self, obj, db_path: Optional[str | Path] = None) -> None:
        self._objects.append((obj, str(db_path) if db_path else None))

    def close_all(self) -> None:
        for obj, _ in reversed(self._objects):
            try:
                closer = getattr(obj, "close", None)
                if callable(closer):
                    closer()
            except Exception:
                pass
        for _, db_path in self._objects:
            if db_path:
                force_release(db_path, attempts=2)
        self._objects.clear()

    def __enter__(self) -> "ManagedStores":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close_all()


def managed_stores() -> ManagedStores:
    return ManagedStores()


__all__ = [
    "ManagedStores",
    "checkpoint",
    "force_release",
    "is_windows",
    "managed_stores",
    "rmtree",
    "sqlite_connection",
    "sqlite_store",
]

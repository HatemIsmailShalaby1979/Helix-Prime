"""
Pytest configuration for Helix Prime Codex.

C0 — cross-platform SQLite handle release
-----------------------------------------
Windows keeps an exclusive lock on an open SQLite file. Any test that opens a
``Store`` (or a raw ``sqlite3`` connection) without closing it leaves that lock
behind, and the temporary-directory cleanup then fails with WinError 32 or
WinError 267 — *after* the assertions have already passed, so the suite reports
a failure for a test that actually succeeded.

The autouse fixture below closes every SQLite handle a test creates, whatever
the exit path. Individual tests can then use bare ``Store(db_path=...)``
without leaking, and new tests inherit the guarantee for free.

Tests that want this explicitly should still use
``tests.support.sqlite_harness.sqlite_store`` — it documents the intent at the
call site instead of relying on global behaviour.
"""
from __future__ import annotations

import gc
import sqlite3
import weakref
from pathlib import Path
from typing import List

import pytest

from tests.support.sqlite_harness import force_release

#: Every Store instance created during a test, held weakly so tracking itself
#: can never keep an object alive.
_LIVE_STORES: "weakref.WeakSet" = weakref.WeakSet()

#: Raw sqlite3 connections created during a test.
_LIVE_CONNECTIONS: "weakref.WeakSet" = weakref.WeakSet()

_INSTALLED = False


def _install_tracking() -> None:
    """Wrap Store.__init__ and sqlite3.connect so handles are tracked."""
    global _INSTALLED
    if _INSTALLED:
        return

    from control_plane.store import Store

    original_init = Store.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _LIVE_STORES.add(self)
        except TypeError:
            pass

    Store.__init__ = tracking_init  # type: ignore[method-assign]

    original_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        try:
            _LIVE_CONNECTIONS.add(conn)
        except TypeError:
            pass
        return conn

    sqlite3.connect = tracking_connect  # type: ignore[assignment]

    _INSTALLED = True


def _release_all(extra_paths: List[Path]) -> None:
    """Close every tracked handle, then release WAL sidecars."""
    for store in list(_LIVE_STORES):
        try:
            store.close()
        except Exception:
            pass
    for conn in list(_LIVE_CONNECTIONS):
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
    _LIVE_STORES.clear()
    _LIVE_CONNECTIONS.clear()

    gc.collect()

    for directory in extra_paths:
        try:
            if not directory.exists():
                continue
            for candidate in directory.rglob("*.db"):
                force_release(candidate, attempts=2)
        except OSError:
            continue


@pytest.fixture(autouse=True)
def release_sqlite_handles(request, tmp_path):
    """
    Guarantee every SQLite handle opened by a test is closed before teardown.

    Depends on ``tmp_path`` deliberately: dependencies tear down in reverse
    order, so this finaliser runs *before* pytest removes the temporary
    directory.
    """
    _install_tracking()

    extra: List[Path] = [Path(tmp_path)]

    # Tests that roll their own TemporaryDirectory() instead of using tmp_path
    # can declare the paths through a marker or a module-level attribute.
    for marker in request.node.iter_markers("sqlite_paths"):
        for raw in marker.args:
            extra.append(Path(str(raw)))

    yield

    _release_all(extra)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sqlite_paths(*paths): extra directories holding SQLite databases that "
        "must be released before teardown (C0 cross-platform file locking).",
    )

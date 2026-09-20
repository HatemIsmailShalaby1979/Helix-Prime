"""
Helix Prime Codex C8 — scratch-space hygiene.

One place that removes a temporary directory, for every release module that takes
one. Callers use this rather than `shutil.rmtree` directly for three reasons.

First, a cleanup failure must never change a verdict. A check that leaks a temp
tree is a hygiene defect; a check that goes red because a directory would not
delete is a correctness defect, and the second is worse — it makes a gate
untrustworthy in the direction that matters, because a red result would no longer
mean what it says.

Second, on Windows the sandbox wraps `shutil.rmtree` and routes a deletion
outside the OS temp directory through a `trash` subprocess with a five-second
timeout. That can genuinely fail, and the wrapper *re-raises* unless
`ignore_errors` is set. Passing `ignore_errors=True` makes it return instead,
which is what makes this function total.

Third, `ignore_errors=True` alone is not enough on Windows, because SQLite keeps a
handle on its database file and `rmtree` then leaves the tree behind **without
raising**. See `discard` for the remedy.

These checks run in-process during the release gate, so they are deliberately
best-effort: an unremovable directory must not abort a gate run.
"""

from __future__ import annotations

import gc
import os
import shutil

__all__ = ["discard"]


def discard(path: str) -> None:
    """Remove a scratch directory. Best effort: this never raises.

    Swallows `OSError` as well as passing `ignore_errors=True`, so it is total on
    every path — a path that does not exist, or one whose contents are still held
    open.

    The retry exists for Windows. A SQLite connection that was never closed — or
    one whose constructor raised *after* opening the file — keeps a handle on its
    database, and `rmtree` then silently leaves the whole tree behind. Measured:
    a directory holding a corrupt `wf.db` survives `rmtree(..., ignore_errors=
    True)` on the same process, and is removable only once a collection pass has
    finalised the orphaned connection. So if the first attempt did not take, one
    collection is run and the removal retried. This is the same remedy the C0
    Windows SQLite-handle work applies, and it costs nothing on the happy path,
    because a successful removal returns before the collection.
    """
    try:
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass

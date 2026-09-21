"""Shared machinery for the quarantined cockpit integration tier.

These tests spawn live servers and drive a real Streamlit script runner, so they are
held out of the 1,758-test baseline. Run them explicitly:

    python -m pytest tests/integration/ui/cockpit/ -m ui_integration

The tier is single-runner by design. Each module binds its engine to an ephemeral
loopback port, so two concurrent runs cannot collide on a port, but they will still
compete for CPU and memory on a 16 GB machine.

Every request here goes through a proxy-free opener. `urllib.request` honours
`HTTP_PROXY` exactly as `httpx` does, and this sandbox exports it, so the default
opener routes a call to `127.0.0.1:<ephemeral>` through the intermediary -- which
cannot reach the port. The symptom is a health probe that never succeeds while the
engine is demonstrably listening, so the opener is built once with an empty
`ProxyHandler` rather than left to the ambient environment.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

UI_MARKER = "ui_integration"
REPO_ROOT = Path(__file__).resolve().parents[4]
ENGINE_HEALTH_TIMEOUT_SECONDS = 30.0
PROCESS_STOP_GRACE_SECONDS = 10.0
LOG_TAIL_CHARACTERS = 2000
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect this tier unless the run names its marker.

    `addopts` cannot hold this line on its own. A `-m` on the command line replaces
    the one in `addopts`, so the documented baseline run (`-m "not smoke"`) would
    silently collect every server-spawning test in here. Deselecting at collection
    time holds for every invocation that does not ask for the marker by name,
    including runs driven from CI or from a remembered command line.
    """
    if UI_MARKER in (config.getoption("markexpr") or ""):
        return
    keep: list[pytest.Item] = []
    drop: list[pytest.Item] = []
    for item in items:
        (drop if UI_MARKER in item.keywords else keep).append(item)
    if drop:
        items[:] = keep
        config.hook.pytest_deselected(items=drop)


class CheckLog:
    """Collects the individual checks of one section so every failure is reported.

    A section keeps the granular check labels the original harnesses printed, while
    the fixture that owns the log turns any failure into a test failure.
    """

    def __init__(self) -> None:
        self.checks = 0
        self.failures: list[str] = []

    def __call__(self, label: str, condition: bool, detail: object = "") -> None:
        self.checks += 1
        suffix = f" -> {detail}" if detail != "" else ""
        if not condition:
            self.failures.append(f"{label}{suffix}")
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}{suffix}")


@pytest.fixture()
def check() -> Iterator[CheckLog]:
    """Per-test check log; the fixture fails the test if any check failed."""
    log = CheckLog()
    yield log
    assert not log.failures, f"{len(log.failures)} of {log.checks} check(s) failed: {log.failures}"


def free_port() -> int:
    """Reserve an ephemeral loopback port so concurrent runs cannot collide."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def http_get(url: str, timeout: float = 10.0) -> Any:
    """Read a JSON document from the engine, bypassing the ambient proxy."""
    with OPENER.open(url, timeout=timeout) as response:
        return json.loads(response.read())


@dataclass(frozen=True, slots=True)
class LiveEngine:
    """A running ingest engine, addressed over loopback."""

    base: str
    process: subprocess.Popen[str]
    log_path: Path

    @property
    def telemetry_url(self) -> str:
        """Ingestion endpoint for one tick."""
        return f"{self.base}/api/v1/telemetry"

    @property
    def approve_url(self) -> str:
        """Human-in-the-loop decision endpoint."""
        return f"{self.base}/api/v1/cockpit/approve"

    def state(self) -> dict[str, Any]:
        """Current cockpit summary."""
        return http_get(f"{self.base}/api/v1/cockpit/state")


def read_log(path: Path) -> str:
    """The tail of a child's log, for a failure message."""
    with suppress(OSError):
        return path.read_text(encoding="utf-8", errors="replace")[-LOG_TAIL_CHARACTERS:]
    return "<child log unavailable>"


def start_engine(port: int) -> LiveEngine:
    """Start an ingest engine and block until it answers its health probe.

    The child writes to a file rather than a pipe. A pipe nobody drains would
    deadlock the engine once its access log filled the 4 KB buffer, which is
    reachable in a single lifecycle test, and a pipe would also lose the reason a
    failed start died -- which is the one thing this harness needs to report.
    """
    handle, name = tempfile.mkstemp(prefix="cockpit-engine-", suffix=".log")
    log_path = Path(name)
    process = subprocess.Popen(
        [
            sys.executable,
            str(REPO_ROOT / "ingest_engine.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    os.close(handle)
    engine = LiveEngine(base=f"http://127.0.0.1:{port}", process=process, log_path=log_path)
    deadline = time.monotonic() + ENGINE_HEALTH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            if http_get(f"{engine.base}/healthz", timeout=2.0):
                return engine
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.3)
    diagnostic = read_log(log_path)
    stop_engine(engine)
    pytest.fail(
        f"ingest engine never became healthy on {engine.base} "
        f"(exit {process.returncode}); child said:\n{diagnostic}"
    )


def stop_engine(engine: LiveEngine) -> None:
    """Terminate an engine, escalating to kill if it does not go quietly."""
    process = engine.process
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    with suppress(OSError):
        engine.log_path.unlink()


@pytest.fixture()
def engine() -> Iterator[LiveEngine]:
    """A fresh ingest engine per test, on an ephemeral port.

    Function scope is deliberate: several tests assert on the rolling window or on
    how many interventions exist, which are only meaningful against an engine that
    has not been written to by an earlier test.
    """
    live = start_engine(free_port())
    try:
        yield live
    finally:
        stop_engine(live)

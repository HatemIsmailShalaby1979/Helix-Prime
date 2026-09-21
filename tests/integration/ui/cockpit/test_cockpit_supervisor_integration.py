"""Integration coverage for the supervisor bridge.

Reconstructed from the scratch harness whose 32 checks are recorded in AGENTS.md
§19.4, converted from script-style to pytest. The port is faithful: every check the
harness printed is asserted here under a named test.

Two of these tests are the discriminating evidence for graceful termination, and
they are not interchangeable. ``test_interrupt_terminates`` proves no zombie survives
an operator interrupt, but it is *not* proof that the supervisor's cleanup ran --
``CTRL_BREAK_EVENT`` is delivered to the whole process group, so the twin dies
whether or not the supervisor reaps it. ``test_cancellation_reaps`` is the one that
isolates the cleanup path.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import supervisor
from supervisor import PayloadContractError, Supervisor, SupervisorConfig

from .conftest import LiveEngine

pytestmark = pytest.mark.ui_integration

REPO_ROOT = Path(__file__).resolve().parents[4]
SUPERVISOR = REPO_ROOT / "supervisor.py"
SIMULATOR = REPO_ROOT / "telemetry_simulator.py"
SUPERVISOR_TIMEOUT_SECONDS = 180.0
DEAD_ENDPOINT = "http://127.0.0.1:9/api/v1/telemetry"
LONG_RUN_TICKS = 400

Check = Callable[[str, bool, object], None]


def run_supervisor(*args: str, timeout: float = SUPERVISOR_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    """Run the bridge as a subprocess, capturing its operator log."""
    return subprocess.run(
        [sys.executable, str(SUPERVISOR), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def alive(pid: int) -> bool:
    """Report whether a process id is still present in the OS process table."""
    listing = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
    ).stdout
    return str(pid) in listing


def summary(stderr: str) -> str:
    """The run's accounting line, for failure messages."""
    for line in stderr.splitlines():
        if "run complete" in line:
            return line.split("supervisor", 1)[-1].strip()
    return "no run summary"


def test_happy_path(check: Check, engine: LiveEngine) -> None:
    """Every tick reaches a live engine, and the twin's stderr is passed through."""
    result = run_supervisor(
        "--ticks", "8",
        "--spike-after", "3",
        "--tick-seconds", "0.05",
        "--endpoint", engine.telemetry_url,
    )
    check("exit code 0", result.returncode == 0, str(result.returncode))
    check("all eight ticks delivered", "delivered=8" in result.stderr, summary(result.stderr))
    check("nothing dropped", "dropped=0" in result.stderr)
    check(
        "each POST logged 200 OK",
        result.stderr.count("200 OK") == 8,
        str(result.stderr.count("200 OK")),
    )
    check("twin exit code 0", "twin_exit=0" in result.stderr)
    check(
        "twin stderr passed through",
        "[twin] volume spike armed" in result.stderr,
        "operator banner visible",
    )
    state = engine.state()
    check("engine window holds the ticks", state["window_samples"] == 8, str(state["window_samples"]))
    check(
        "spike raised interventions through the bridge",
        len(state["recommendations"]) >= 1,
        f"raised={len(state['recommendations'])}",
    )


def test_backoff_and_drop(check: Check) -> None:
    """An unreachable engine holds the payload, backs off, then drops it."""
    result = run_supervisor(
        "--ticks", "2",
        "--spike-after", "0",
        "--tick-seconds", "0.05",
        "--endpoint", DEAD_ENDPOINT,
        "--attempts", "3",
        "--base-delay", "0.1",
        "--max-delay", "0.4",
    )
    check("exit code 1", result.returncode == 1, str(result.returncode))
    check("both payloads dropped", "dropped=2" in result.stderr, summary(result.stderr))
    check("classified as unreachable", "engine unreachable" in result.stderr)
    check(
        "backoff doubled 0.10s -> 0.20s",
        "retry 2 in 0.10s" in result.stderr and "retry 3 in 0.20s" in result.stderr,
    )
    check("held through the full budget", result.stderr.count("attempt=3/3") >= 2)


def test_rejection_aborts(check: Check, engine: LiveEngine) -> None:
    """A 4xx aborts the run instead of dropping every tick."""
    result = run_supervisor(
        "--ticks", "2",
        "--spike-after", "0",
        "--tick-seconds", "0.05",
        "--endpoint", f"{engine.base}/api/v1/nope",
    )
    check("exit code 1", result.returncode == 1, str(result.returncode))
    check(
        "rejection surfaced with status",
        "404" in result.stderr and "ingest rejected tick 1" in result.stderr,
    )
    check("not retried", "retry 2" not in result.stderr)
    check(
        "abort reported as a contract failure",
        "ingest rejected tick 1 with 404" in result.stderr,
        "run stopped at the first rejection",
    )


def test_reap_isolated(check: Check) -> None:
    """Terminate reaps a live child; a clean exit is collected without signalling."""
    supervisor_instance = Supervisor(
        SupervisorConfig(
            simulator_path=SIMULATOR,
            endpoint=DEAD_ENDPOINT,
            ticks=LONG_RUN_TICKS,
            spike_after=10,
            tick_seconds=0.5,
        )
    )

    async def exercise() -> tuple[int | None, int | None]:
        process = await supervisor_instance._spawn()
        check("twin spawned for the reap test", alive(process.pid), f"pid={process.pid}")
        await asyncio.sleep(1.0)
        forced = await supervisor_instance._reap(process, graceful=False)
        check("terminate reaps a live child", not alive(process.pid), f"pid={process.pid}")
        check("return code observed", forced is not None, str(forced))

        quick = Supervisor(
            SupervisorConfig(
                simulator_path=SIMULATOR,
                endpoint=DEAD_ENDPOINT,
                ticks=1,
                spike_after=0,
                tick_seconds=0.05,
            )
        )
        quick_process = await quick._spawn()
        quick_pid = quick_process.pid
        await quick_process.wait()
        collected = await quick._reap(quick_process, graceful=True)
        check("clean exit collected without signalling", collected == 0, str(collected))
        check("process gone", not alive(quick_pid))
        return forced, collected

    asyncio.run(exercise())

    try:
        supervisor_instance._decode('{"timestamp": "2026-01-05T08:05:00Z", "calls_waiting": 10}')
        check("bare metrics line refused by the contract check", False, "no error raised")
    except PayloadContractError as error:
        check("bare metrics line refused by the contract check", "--emit-state" in str(error))
    try:
        supervisor_instance._decode("not json")
        check("non-JSON line refused", False, "no error raised")
    except PayloadContractError as error:
        check("non-JSON line refused", "not JSON" in str(error))


def test_cancellation_reaps(check: Check) -> None:
    """Cancelling the run terminates the twin -- the isolated cleanup proof."""
    spawned: list[int] = []
    original = Supervisor._spawn

    async def spy(self: Supervisor) -> Any:
        process = await original(self)
        spawned.append(process.pid)
        return process

    Supervisor._spawn = spy
    try:

        async def exercise() -> None:
            config = SupervisorConfig(
                simulator_path=SIMULATOR,
                endpoint=DEAD_ENDPOINT,
                ticks=LONG_RUN_TICKS,
                spike_after=10,
                tick_seconds=0.5,
            )
            task = asyncio.create_task(Supervisor(config).run())
            await asyncio.sleep(1.5)
            check("twin running before cancellation", bool(spawned) and alive(spawned[0]))
            task.cancel()
            try:
                await task
                check("cancellation propagated to the caller", False, "no CancelledError")
            except asyncio.CancelledError:
                check("cancellation propagated to the caller", True)
            await asyncio.sleep(0.3)
            check("twin terminated by the cancellation path", not alive(spawned[0]))

        asyncio.run(exercise())
    finally:
        Supervisor._spawn = original


def test_interrupt_exit_code(check: Check) -> None:
    """A KeyboardInterrupt surfacing at the boundary maps to exit 130.

    The mapping is tested here rather than by signalling a child: on Windows a
    console control event kills the process before Python's handler can run, so
    signalling cannot exercise this path at all.
    """
    original = supervisor.asyncio.run

    def raise_interrupt(coro: Any) -> None:
        coro.close()
        raise KeyboardInterrupt

    supervisor.asyncio.run = raise_interrupt  # type: ignore[assignment]
    try:
        code = supervisor.main(["--ticks", "1", "--spike-after", "0", "--endpoint", DEAD_ENDPOINT])
    finally:
        supervisor.asyncio.run = original
    check("KeyboardInterrupt maps to exit 130", code == 130, str(code))


def test_interrupt_terminates(check: Check, engine: LiveEngine) -> None:
    """An operator interrupt leaves no surviving twin, whatever killed it."""
    process = subprocess.Popen(
        [
            sys.executable, str(SUPERVISOR),
            "--ticks", str(LONG_RUN_TICKS),
            "--spike-after", "10",
            "--tick-seconds", "0.5",
            "--endpoint", engine.telemetry_url,
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    twin_pid: int | None = None
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        line = process.stderr.readline()
        if not line:
            break
        if "twin started pid=" in line:
            twin_pid = int(line.split("twin started pid=")[1].split()[0])
            break
    check("twin pid observed in the operator log", twin_pid is not None, str(twin_pid))
    check("twin running before the interrupt", twin_pid is not None and alive(twin_pid))
    os.kill(process.pid, signal.CTRL_BREAK_EVENT)
    process.wait(timeout=30)
    check(
        "process ended on the console control event",
        process.returncode in (130, -1073741510, 3221225786),
        f"{process.returncode} (Windows reports STATUS_CONTROL_C_EXIT when the OS, "
        "not Python, handles CTRL_BREAK)",
    )
    time.sleep(0.5)
    check(
        "no zombie twin after the supervisor exits",
        twin_pid is not None and not alive(twin_pid),
    )

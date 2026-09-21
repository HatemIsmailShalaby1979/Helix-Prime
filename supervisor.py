"""Execution and transport layer for the Helix Ops Cockpit.

Launches :mod:`telemetry_simulator` as an asynchronous subprocess, decodes its
stdout line by line, and forwards every tick to a running :mod:`ingest_engine`
over HTTP. The supervisor owns no domain state: it does not recompute velocity,
re-rank interventions, or repair payloads. It moves bytes and reports what
happened to them.

Pipeline
    twin stdout --(pipe)--> decode --> contract check --> POST /api/v1/telemetry

        |-- 2xx                   -> delivered
        |-- 5xx / 429 / transport -> held and retried on an exponential schedule
        |-- 4xx                   -> rejected; the run aborts

Contract
    The twin is launched with ``--emit-state``, so each stdout line is already the
    ``{metrics, state}`` envelope that ``POST /api/v1/telemetry`` accepts and the
    supervisor forwards it verbatim. A bare metrics line cannot be completed
    downstream: ``current_interval_volume`` is not derivable from it, so the
    transport layer would have to invent control-plane state it does not own. The
    flag is opt-in and the twin's default stdout contract is unchanged.

Ordering and backpressure
    One delivery is awaited before the next line is read, so the tick order the
    engine's rolling window depends on is preserved exactly -- velocity and the
    SLA gradient are read off the sequence, not off arrival time. Backpressure is
    the OS pipe rather than an in-process queue: while a delivery is in flight the
    supervisor is not reading, the child's stdout buffer fills, and the twin
    blocks on write. Memory stays flat however slow the engine is, and nothing is
    reordered to achieve it.

Transport
    The HTTP client ignores the ambient proxy environment (``trust_env=False``).
    This is a loopback control-plane call: on a host with ``HTTP_PROXY`` set,
    honouring it would route every tick through an intermediary, add its latency
    to a two-second cadence, and report the proxy's own 502 instead of the real
    connection error when the engine is down.

Retry policy
    A payload is held across the whole budget before it is dropped::

        delay(n) = min(base * factor ** (n - 1), cap)

    Deterministic rather than jittered: there is a single producer here, and an
    auditable schedule is worth more than herd-damping. The default budget is 8
    attempts from a 0.5 s base doubling to an 8 s cap, roughly 40 s of patience --
    enough to ride out an engine that is still booting, which is the failure this
    exists for. Transport errors, timeouts, 5xx and 429 are retryable. A 4xx is
    not: an engine rejecting the payload rejects every tick identically, so the
    run aborts with the response body logged rather than dropping a hundred
    payloads into a silent gap.

Termination
    The child is reaped in a ``finally`` block, so a clean end of stream,
    ``KeyboardInterrupt``, cancellation, or an aborting defect all terminate it. A
    twin that ended on its own is collected with ``wait()`` rather than signalled,
    because signalling a process that already exited would replace its real exit
    status. A twin that is still alive is terminated, given a grace period, then
    killed. No zombie survives the supervisor.

Exit codes
    0     twin exited cleanly and every tick was delivered
    1     a payload was dropped, a contract defect, or a non-zero twin exit
    130   interrupted by the operator (SIGINT convention)

CLI
    python supervisor.py [--ticks N] [--spike-after N] [--endpoint URL]
                         [--seed N] [--tick-seconds S] [--attempts N]
                         [--base-delay S] [--max-delay S] [--timeout S]
                         [--log-level LEVEL]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import httpx

LOG_NAME: Final[str] = "supervisor"
LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)-8s %(name)s %(message)s"

DEFAULT_ENDPOINT: Final[str] = "http://127.0.0.1:8000/api/v1/telemetry"
DEFAULT_TICKS: Final[int] = 100
DEFAULT_SPIKE_AFTER: Final[int] = 10
RETRY_ATTEMPTS: Final[int] = 8
RETRY_BASE_DELAY_SECONDS: Final[float] = 0.5
RETRY_FACTOR: Final[float] = 2.0
RETRY_MAX_DELAY_SECONDS: Final[float] = 8.0
REQUEST_TIMEOUT_SECONDS: Final[float] = 5.0
TERMINATION_GRACE_SECONDS: Final[float] = 5.0
PREVIEW_CHARACTERS: Final[int] = 160

EXIT_SUCCESS: Final[int] = 0
EXIT_FAILURE: Final[int] = 1
EXIT_INTERRUPTED: Final[int] = 130


class SupervisorError(Exception):
    """A condition the supervisor cannot continue past."""


class PayloadContractError(SupervisorError):
    """A twin stdout line is not an ingest envelope."""


class _Iso8601Formatter(logging.Formatter):
    """Formatter that keeps the local UTC offset visible on every timestamp."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """Render the record's creation time as local ISO-8601 with an offset."""
        moment = datetime.fromtimestamp(record.created).astimezone()
        return moment.isoformat(timespec="milliseconds")


def _preview(text: str, limit: int = PREVIEW_CHARACTERS) -> str:
    """Collapse whitespace and bound the length of a payload or body excerpt."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}..."


def _is_retryable_status(status_code: int) -> bool:
    """True for statuses that can clear on their own: server faults and throttling."""
    return status_code >= 500 or status_code == 429


def _is_rejection_status(status_code: int) -> bool:
    """True for client errors that will repeat identically on every tick."""
    return 400 <= status_code < 500 and not _is_retryable_status(status_code)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential backoff schedule for one payload's delivery budget."""

    attempts: int = RETRY_ATTEMPTS
    base_delay_seconds: float = RETRY_BASE_DELAY_SECONDS
    factor: float = RETRY_FACTOR
    max_delay_seconds: float = RETRY_MAX_DELAY_SECONDS

    def delay_after(self, attempt: int) -> float:
        """Backoff to wait after a failed `attempt`, capped at the ceiling."""
        grown = self.base_delay_seconds * self.factor ** (attempt - 1)
        return min(grown, self.max_delay_seconds)


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    """A fully resolved run configuration, assembled from the command line."""

    simulator_path: Path
    endpoint: str
    ticks: int = DEFAULT_TICKS
    spike_after: int = DEFAULT_SPIKE_AFTER
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    request_timeout_seconds: float = REQUEST_TIMEOUT_SECONDS
    termination_grace_seconds: float = TERMINATION_GRACE_SECONDS
    seed: int | None = None
    tick_seconds: float | None = None
    python_executable: str = field(default_factory=lambda: sys.executable)

    def __post_init__(self) -> None:
        """Normalise the simulator path, so a str and a Path are both accepted."""
        object.__setattr__(self, "simulator_path", Path(self.simulator_path))

    def simulator_args(self) -> list[str]:
        """The exact argv handed to the child, minus the interpreter."""
        arguments = [
            str(self.simulator_path),
            "--ticks",
            str(self.ticks),
            "--spike-after",
            str(self.spike_after),
            "--emit-state",
        ]
        if self.seed is not None:
            arguments += ["--seed", str(self.seed)]
        if self.tick_seconds is not None:
            arguments += ["--tick-seconds", str(self.tick_seconds)]
        return arguments


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """One POST attempt, classified for the retry policy."""

    status_code: int | None
    detail: str
    latency_seconds: float
    retryable: bool

    @property
    def delivered(self) -> bool:
        """True when the engine accepted the payload."""
        return self.status_code is not None and 200 <= self.status_code < 300


@dataclass(frozen=True, slots=True)
class DeliveryReport:
    """The result of one payload's complete retry budget."""

    delivered: bool
    rejected: bool
    attempts: int
    status_code: int | None
    detail: str
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class RunReport:
    """The supervisor's accounting for a completed run."""

    ticks_seen: int
    delivered: int
    dropped: int
    twin_exit_code: int | None
    elapsed_seconds: float
    exit_code: int


class Supervisor:
    """Spawn the twin, forward every tick, reap the child, report the accounting."""

    def __init__(self, config: SupervisorConfig) -> None:
        self._config = config
        self._log = logging.getLogger(LOG_NAME)
        self._endpoint_path = httpx.URL(config.endpoint).path
        self._ticks_seen = 0
        self._delivered = 0
        self._dropped = 0

    async def run(self) -> RunReport:
        """Execute the bridge end to end and return the run accounting."""
        started = time.monotonic()
        process = await self._spawn()
        self._log.info(
            "twin started pid=%s argv=%s", process.pid, " ".join(self._config.simulator_args())
        )
        stream_closed = False
        twin_exit_code: int | None = None
        timeout = httpx.Timeout(self._config.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            try:
                await self._pump(process, client)
                stream_closed = True
            finally:
                twin_exit_code = await self._reap(process, graceful=stream_closed)
        elapsed = time.monotonic() - started
        exit_code = self._classify(twin_exit_code)
        self._log.info(
            "run complete ticks=%d delivered=%d dropped=%d twin_exit=%s elapsed=%.1fs exit=%d",
            self._ticks_seen,
            self._delivered,
            self._dropped,
            twin_exit_code,
            elapsed,
            exit_code,
        )
        return RunReport(
            ticks_seen=self._ticks_seen,
            delivered=self._delivered,
            dropped=self._dropped,
            twin_exit_code=twin_exit_code,
            elapsed_seconds=elapsed,
            exit_code=exit_code,
        )

    async def _spawn(self) -> asyncio.subprocess.Process:
        """Start the twin with stdout piped and stderr inherited by this process."""
        config = self._config
        if not config.simulator_path.is_file():
            raise SupervisorError(f"twin not found at {config.simulator_path}")
        return await asyncio.create_subprocess_exec(
            config.python_executable,
            *config.simulator_args(),
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )

    async def _pump(
        self, process: asyncio.subprocess.Process, client: httpx.AsyncClient
    ) -> None:
        """Read stdout line by line, delivering each tick before reading the next."""
        stdout = process.stdout
        if stdout is None:
            raise SupervisorError("twin stdout was not piped")
        async for raw in stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            self._ticks_seen += 1
            payload = self._decode(line)
            report = await self._deliver(self._ticks_seen, payload, client)
            if report.delivered:
                self._delivered += 1
                continue
            if report.rejected:
                raise SupervisorError(
                    f"ingest rejected tick {self._ticks_seen} with {report.status_code}: "
                    f"{report.detail}"
                )
            self._dropped += 1
            self._log.error(
                "tick=%d payload dropped after %d attempt(s) in %.2fs: %s",
                self._ticks_seen,
                report.attempts,
                report.elapsed_seconds,
                report.detail,
            )

    def _decode(self, line: str) -> dict[str, Any]:
        """Decode one stdout line, refusing anything that is not an ingest envelope."""
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise PayloadContractError(
                f"stdout line is not JSON ({error.msg}): {_preview(line)}"
            ) from error
        if not isinstance(payload, dict) or "metrics" not in payload or "state" not in payload:
            raise PayloadContractError(
                "stdout line is not an ingest envelope; expected {metrics, state} from "
                f"--emit-state, got {_preview(line)}"
            )
        return payload

    async def _deliver(
        self, tick: int, payload: dict[str, Any], client: httpx.AsyncClient
    ) -> DeliveryReport:
        """POST one payload, holding it through the retry budget before dropping it."""
        started = time.monotonic()
        policy = self._config.retry
        for attempt in range(1, policy.attempts + 1):
            outcome = await self._attempt(tick, attempt, policy.attempts, payload, client)
            if outcome.delivered or not outcome.retryable or attempt == policy.attempts:
                return DeliveryReport(
                    delivered=outcome.delivered,
                    rejected=outcome.status_code is not None
                    and _is_rejection_status(outcome.status_code),
                    attempts=attempt,
                    status_code=outcome.status_code,
                    detail=outcome.detail,
                    elapsed_seconds=time.monotonic() - started,
                )
            delay = policy.delay_after(attempt)
            self._log.warning(
                "tick=%d attempt=%d/%d POST %s -> %s; holding payload, retry %d in %.2fs",
                tick,
                attempt,
                policy.attempts,
                self._endpoint_path,
                outcome.detail,
                attempt + 1,
                delay,
            )
            await asyncio.sleep(delay)
        raise SupervisorError(f"retry loop for tick {tick} exited without a result")

    async def _attempt(
        self,
        tick: int,
        attempt: int,
        budget: int,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> AttemptOutcome:
        """Issue a single POST and classify the response for the retry policy."""
        started = time.monotonic()
        try:
            response = await client.post(self._config.endpoint, json=payload)
        except httpx.TransportError as error:
            latency = time.monotonic() - started
            detail = f"engine unreachable ({type(error).__name__})"
            self._log.warning(
                "tick=%d attempt=%d/%d POST %s -> %s in %.1fms",
                tick,
                attempt,
                budget,
                self._endpoint_path,
                detail,
                latency * 1000.0,
            )
            return AttemptOutcome(None, detail, latency, retryable=True)
        latency = time.monotonic() - started
        status_code = response.status_code
        detail = f"{status_code} {response.reason_phrase}"
        if 200 <= status_code < 300:
            self._log.info(
                "tick=%d attempt=%d/%d POST %s -> %s in %.1fms",
                tick,
                attempt,
                budget,
                self._endpoint_path,
                detail,
                latency * 1000.0,
            )
            return AttemptOutcome(status_code, detail, latency, retryable=False)
        body = _preview(response.text)
        detail = f"{detail} {body}".strip()
        if _is_retryable_status(status_code):
            self._log.warning(
                "tick=%d attempt=%d/%d POST %s -> %s in %.1fms",
                tick,
                attempt,
                budget,
                self._endpoint_path,
                detail,
                latency * 1000.0,
            )
            return AttemptOutcome(status_code, detail, latency, retryable=True)
        self._log.error(
            "tick=%d attempt=%d/%d POST %s -> %s in %.1fms (not retryable)",
            tick,
            attempt,
            budget,
            self._endpoint_path,
            detail,
            latency * 1000.0,
        )
        return AttemptOutcome(status_code, detail, latency, retryable=False)

    async def _reap(self, process: asyncio.subprocess.Process, *, graceful: bool) -> int | None:
        """Collect the child, signalling it only if it has not exited on its own."""
        grace = self._config.termination_grace_seconds
        if process.returncode is not None:
            return process.returncode
        if graceful:
            with suppress(TimeoutError):
                return await asyncio.wait_for(process.wait(), timeout=grace)
            self._log.warning(
                "twin did not exit within %.1fs of end of stream; terminating pid=%s",
                grace,
                process.pid,
            )
        self._log.info("terminating twin pid=%s", process.pid)
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            return await asyncio.wait_for(process.wait(), timeout=grace)
        except TimeoutError:
            self._log.warning("twin ignored terminate; killing pid=%s", process.pid)
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        return process.returncode

    def _classify(self, twin_exit_code: int | None) -> int:
        """Map the run accounting onto a process exit code."""
        if twin_exit_code != 0:
            self._log.error("twin exited with code %s", twin_exit_code)
            return EXIT_FAILURE
        if self._dropped:
            self._log.error("run finished with %d dropped payload(s)", self._dropped)
            return EXIT_FAILURE
        return EXIT_SUCCESS


def _configure_logging(level: str) -> None:
    """Send formal, timestamped operator output to stderr.

    The level applies to the supervisor's own logger. Raising the root logger
    instead would switch on third-party request logging, and every POST would
    then appear twice in the operator stream.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Iso8601Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.getLogger(LOG_NAME).setLevel(level.upper())


def _parse_args(argv: list[str] | None = None) -> SupervisorConfig:
    """Resolve the command line into a run configuration."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS, help="twin ticks to forward")
    parser.add_argument(
        "--spike-after", type=int, default=DEFAULT_SPIKE_AFTER, help="twin tick that arms the spike"
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="ingest telemetry URL")
    parser.add_argument(
        "--simulator",
        type=Path,
        default=Path(__file__).with_name("telemetry_simulator.py"),
        help="path to the operations twin",
    )
    parser.add_argument("--seed", type=int, default=None, help="twin RNG seed override")
    parser.add_argument(
        "--tick-seconds", type=float, default=None, help="twin cadence override, for smoke runs"
    )
    parser.add_argument(
        "--attempts", type=int, default=RETRY_ATTEMPTS, help="delivery attempts per payload"
    )
    parser.add_argument(
        "--base-delay", type=float, default=RETRY_BASE_DELAY_SECONDS, help="first backoff, seconds"
    )
    parser.add_argument(
        "--max-delay", type=float, default=RETRY_MAX_DELAY_SECONDS, help="backoff ceiling, seconds"
    )
    parser.add_argument(
        "--timeout", type=float, default=REQUEST_TIMEOUT_SECONDS, help="per-request timeout"
    )
    parser.add_argument("--log-level", default="info", help="logging level")
    args = parser.parse_args(argv)
    if args.ticks < 1:
        parser.error("--ticks must be >= 1")
    if not 0 <= args.spike_after <= args.ticks:
        parser.error("--spike-after must fall within [0, --ticks]")
    if args.attempts < 1:
        parser.error("--attempts must be >= 1")
    if args.base_delay < 0.0 or args.max_delay < args.base_delay:
        parser.error("--base-delay must be >= 0 and --max-delay must be >= --base-delay")
    if args.tick_seconds is not None and args.tick_seconds <= 0.0:
        parser.error("--tick-seconds must be > 0")
    _configure_logging(args.log_level)
    return SupervisorConfig(
        simulator_path=args.simulator,
        endpoint=args.endpoint,
        ticks=args.ticks,
        spike_after=args.spike_after,
        retry=RetryPolicy(
            attempts=args.attempts,
            base_delay_seconds=args.base_delay,
            max_delay_seconds=args.max_delay,
        ),
        request_timeout_seconds=args.timeout,
        seed=args.seed,
        tick_seconds=args.tick_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the supervisor and translate its outcome into an exit code."""
    log = logging.getLogger(LOG_NAME)
    try:
        config = _parse_args(argv)
        report = asyncio.run(Supervisor(config).run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.warning("interrupted by the operator; twin terminated")
        return EXIT_INTERRUPTED
    except SupervisorError as error:
        log.error("%s", error)
        return EXIT_FAILURE
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

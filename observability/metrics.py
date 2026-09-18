"""
In-process Prometheus metrics for Helix Codex OS (H2.2, G22).

Local-first and stdlib-only: no client library, no exporter sidecar, no
network. Metrics live in a process-global registry; ``/metrics`` renders it
in the Prometheus text exposition format.

Security constraints, enforced structurally:

* Label values are FIXED and defined here (route templates, decision
  buckets). Application data, tenant ids, actors and free-form strings never
  become label values — the ``inc``/``observe``/``set`` entry points accept
  no caller-supplied label text. This makes cardinality bounded and keeps
  PII/secrets out of the exposition by construction.
* The registry exposes counters and gauges only — no payload data.

Metric families:

* helix_http_requests_total{route,status,method}      — request count by route
* helix_http_request_duration_seconds (histogram)     — latency by route
* helix_governance_decisions_total{decision}          — allowed/denied/held/…
* helix_audit_chain_verifications_total{result}      — ok/failure
* helix_audit_chain_verification_failures            — monotonic failure gauge
* helix_approval_queue_depth                          — awaiting_approval count
* helix_readiness_check_failures_total{check}        — readiness probe failures
* helix_auth_events_total{event}                      — sign-in outcomes
* helix_kill_switch_events_total{event}              — halt engagements
* helix_data_disk_free_bytes                          — free bytes on the data volume
"""
from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Tuple

_LOCK = threading.Lock()

HTTP_REQUESTS_METRIC = "helix_http_requests_total"
HTTP_DURATION_METRIC = "helix_http_request_duration_seconds"
GOVERNANCE_DECISIONS_METRIC = "helix_governance_decisions_total"
AUDIT_VERIFICATIONS_METRIC = "helix_audit_chain_verifications_total"
AUDIT_FAILURES_METRIC = "helix_audit_chain_verification_failures"
QUEUE_DEPTH_METRIC = "helix_approval_queue_depth"
READINESS_FAILURES_METRIC = "helix_readiness_check_failures_total"
AUTH_EVENTS_METRIC = "helix_auth_events_total"
KILL_SWITCH_EVENTS_METRIC = "helix_kill_switch_events_total"
DISK_FREE_METRIC = "helix_data_disk_free_bytes"

_READINESS_CHECKS = ("workflow_store", "audit_chain")
_AUTH_EVENTS = ("login_success", "login_failure", "login_throttled", "login_locked")
_KILL_SWITCH_EVENTS = ("engaged", "released", "denied")

_DECISION_BUCKETS = ("allowed", "denied", "held", "succeeded", "failed")
_VERIFICATION_RESULTS = ("ok", "failure")

DEFAULT_DURATION_BUCKETS: Tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_METRIC_HELP = {
    HTTP_REQUESTS_METRIC: "HTTP requests processed, by route template and status code.",
    HTTP_DURATION_METRIC: "HTTP request duration in seconds, by route template.",
    GOVERNANCE_DECISIONS_METRIC: "Governed decisions recorded in the audit trail, by decision.",
    AUDIT_VERIFICATIONS_METRIC: "Audit hash-chain verifications, by result.",
    AUDIT_FAILURES_METRIC: "Monotonic count of audit hash-chain verification failures.",
    QUEUE_DEPTH_METRIC: "Workflows currently frozen awaiting human approval.",
    READINESS_FAILURES_METRIC: "Readiness probe failures, by failed check.",
    AUTH_EVENTS_METRIC: "Sign-in outcomes, by event.",
    KILL_SWITCH_EVENTS_METRIC: "Kill-switch engagements, releases, and denials, by event.",
    DISK_FREE_METRIC: "Free bytes on the volume holding the databases.",
}


def _validate_metric_name(name: str) -> str:
    if not isinstance(name, str) or not name or not name.startswith("helix_"):
        raise ValueError(
            f"metrics: metric name must be a non-empty 'helix_'-prefixed string, got {name!r}"
        )
    return name


def _validate_label_value(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"metrics: label value must be a non-empty string, got {value!r}")
    if "\\" in value or '"' in value or "\n" in value:
        raise ValueError(
            f"metrics: label value contains a character forbidden by the exposition format: {value!r}"
        )
    return value


class _Metric:
    """One named metric family with fixed label keys."""

    def __init__(self, name: str, help_text: str, label_keys: Tuple[str, ...]) -> None:
        self.name = _validate_metric_name(name)
        self.help = help_text
        self.label_keys = label_keys
        self.values: Dict[Tuple[str, ...], float] = {}

    def _series_key(self, label_values: Iterable[str]) -> Tuple[str, ...]:
        values = tuple(label_values)
        if len(values) != len(self.label_keys):
            raise ValueError(
                f"metrics: {self.name} expects {len(self.label_keys)} label values "
                f"{self.label_keys}, got {values!r}"
            )
        return tuple(_validate_label_value(v) for v in values)


class Counter(_Metric):
    def inc(self, amount: float = 1.0, **labels: str) -> None:
        if amount < 0:
            raise ValueError(f"metrics: counter {self.name} cannot decrease (got {amount})")
        key = self._series_key(labels[k] for k in self.label_keys)
        with _LOCK:
            self.values[key] = self.values.get(key, 0.0) + amount


class Gauge(_Metric):
    def set(self, value: float, **labels: str) -> None:
        key = self._series_key(labels[k] for k in self.label_keys)
        with _LOCK:
            self.values[key] = float(value)

    def set_to_current_time(self, **labels: str) -> None:
        import time

        self.set(time.time(), **labels)


class Histogram(_Metric):
    def __init__(
        self, name: str, help_text: str, label_keys: Tuple[str, ...], buckets: Tuple[float, ...]
    ) -> None:
        super().__init__(name, help_text, label_keys)
        if not buckets or list(buckets) != sorted(set(buckets)):
            raise ValueError(f"metrics: histogram {name} requires sorted, unique buckets")
        self.buckets: Tuple[float, ...] = tuple(buckets)
        self.bucket_counts: Dict[Tuple[Tuple[str, ...], int], float] = {}
        self.sums: Dict[Tuple[str, ...], float] = {}
        self.counts: Dict[Tuple[str, ...], float] = {}

    def observe(self, value: float, **labels: str) -> None:
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(
                f"metrics: histogram {self.name} requires a non-negative number, got {value!r}"
            )
        key = self._series_key(labels[k] for k in self.label_keys)
        with _LOCK:
            self.sums[key] = self.sums.get(key, 0.0) + float(value)
            self.counts[key] = self.counts.get(key, 0.0) + 1
            for idx, bound in enumerate(self.buckets):
                if value <= bound:
                    self.bucket_counts[(key, idx)] = self.bucket_counts.get((key, idx), 0.0) + 1


class MetricsRegistry:
    """
    Process-global registry. Instantiate once; import the instance from this
    module. ``reset_for_tests()`` exists because a suite shares one process.
    """

    def __init__(self) -> None:
        self.http_requests = Counter(
            HTTP_REQUESTS_METRIC,
            _METRIC_HELP[HTTP_REQUESTS_METRIC],
            ("route", "status", "method"),
        )
        self.http_duration = Histogram(
            HTTP_DURATION_METRIC,
            _METRIC_HELP[HTTP_DURATION_METRIC],
            ("route",),
            DEFAULT_DURATION_BUCKETS,
        )
        self.governance_decisions = Counter(
            GOVERNANCE_DECISIONS_METRIC,
            _METRIC_HELP[GOVERNANCE_DECISIONS_METRIC],
            ("decision",),
        )
        self.audit_verifications = Counter(
            AUDIT_VERIFICATIONS_METRIC,
            _METRIC_HELP[AUDIT_VERIFICATIONS_METRIC],
            ("result",),
        )
        self.audit_failures = Gauge(
            AUDIT_FAILURES_METRIC,
            _METRIC_HELP[AUDIT_FAILURES_METRIC],
            (),
        )
        self.approval_queue_depth = Gauge(
            QUEUE_DEPTH_METRIC,
            _METRIC_HELP[QUEUE_DEPTH_METRIC],
            (),
        )
        self.readiness_failures = Counter(
            READINESS_FAILURES_METRIC,
            _METRIC_HELP[READINESS_FAILURES_METRIC],
            ("check",),
        )
        self.auth_events = Counter(
            AUTH_EVENTS_METRIC,
            _METRIC_HELP[AUTH_EVENTS_METRIC],
            ("event",),
        )
        self.kill_switch_events = Counter(
            KILL_SWITCH_EVENTS_METRIC,
            _METRIC_HELP[KILL_SWITCH_EVENTS_METRIC],
            ("event",),
        )
        self.disk_free_bytes = Gauge(
            DISK_FREE_METRIC,
            _METRIC_HELP[DISK_FREE_METRIC],
            (),
        )

    def record_governance_decision(self, decision: str) -> None:
        if decision not in _DECISION_BUCKETS:
            decision = "failed"
        self.governance_decisions.inc(decision=decision)

    def record_audit_verification(self, ok: bool) -> None:
        result = "ok" if ok else "failure"
        self.audit_verifications.inc(result=result)
        if not ok:
            with _LOCK:
                current = self.audit_failures.values.get((), 0.0)
                self.audit_failures.values[()] = current + 1

    def set_approval_queue_depth(self, depth: int) -> None:
        if not isinstance(depth, int) or depth < 0:
            raise ValueError(
                f"metrics: approval queue depth must be a non-negative int, got {depth!r}"
            )
        self.approval_queue_depth.set(depth)

    def record_readiness_failure(self, check: str) -> None:
        if check not in _READINESS_CHECKS:
            raise ValueError(
                f"metrics: unknown readiness check {check!r} "
                f"(expected one of {list(_READINESS_CHECKS)})"
            )
        self.readiness_failures.inc(check=check)

    def record_auth_event(self, event: str) -> None:
        if event not in _AUTH_EVENTS:
            raise ValueError(
                f"metrics: unknown auth event {event!r} " f"(expected one of {list(_AUTH_EVENTS)})"
            )
        self.auth_events.inc(event=event)

    def record_kill_switch_event(self, event: str) -> None:
        if event not in _KILL_SWITCH_EVENTS:
            raise ValueError(
                f"metrics: unknown kill-switch event {event!r} "
                f"(expected one of {list(_KILL_SWITCH_EVENTS)})"
            )
        self.kill_switch_events.inc(event=event)

    def set_data_disk_free_bytes(self, value: float) -> None:
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(
                f"metrics: disk free bytes must be a non-negative number, got {value!r}"
            )
        self.disk_free_bytes.set(float(value))

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with _LOCK:
            snapshot: Dict[str, Dict[str, float]] = {}
            for metric in self._all_metrics():
                snapshot[metric.name] = {
                    "|".join(k) if k else "": v for k, v in metric.values.items()
                }
                if isinstance(metric, Histogram):
                    for (key, idx), count in metric.bucket_counts.items():
                        snapshot.setdefault(metric.name + "_bucket", {}).setdefault(
                            f"{'|'.join(key)}|le={metric.buckets[idx]}", 0.0
                        )
                        snapshot[metric.name + "_bucket"][
                            f"{'|'.join(key)}|le={metric.buckets[idx]}"
                        ] = count
            return snapshot

    def _all_metrics(self) -> List[_Metric]:
        return [
            self.http_requests,
            self.http_duration,
            self.governance_decisions,
            self.audit_verifications,
            self.audit_failures,
            self.approval_queue_depth,
            self.readiness_failures,
            self.auth_events,
            self.kill_switch_events,
            self.disk_free_bytes,
        ]

    def reset_for_tests(self) -> None:
        with _LOCK:
            for metric in self._all_metrics():
                metric.values.clear()
                if isinstance(metric, Histogram):
                    metric.bucket_counts.clear()
                    metric.sums.clear()
                    metric.counts.clear()

    def render(self) -> str:
        """
        Render the registry in the Prometheus text exposition format.

        Only fixed label values defined by this module are emitted, so no
        application data, secrets or PII can appear in the output.
        """
        lines: List[str] = []
        with _LOCK:
            metrics = self._all_metrics()
            for metric in metrics:
                lines.append(f"# HELP {metric.name} {metric.help}")
                lines.append(
                    f"# TYPE {metric.name} {'counter' if isinstance(metric, (Counter,)) else 'gauge' if isinstance(metric, Gauge) else 'histogram'}"
                )
                if isinstance(metric, Histogram):
                    self._render_histogram(metric, lines)
                else:
                    for key in sorted(metric.values):
                        self._emit_sample(metric, key, metric.values[key], lines)
        return "\n".join(lines) + "\n"

    def _render_histogram(self, metric: Histogram, lines: List[str]) -> None:
        for key in sorted(metric.sums):
            label_pairs = list(zip(metric.label_keys, key, strict=False))
            for idx, bound in enumerate(metric.buckets):
                count = metric.bucket_counts.get((key, idx), 0.0)
                self._emit_histogram_line(
                    metric, label_pairs + [("le", _format_bucket(bound))], count, lines
                )
            self._emit_histogram_line(
                metric, label_pairs + [("le", "+Inf")], metric.counts.get(key, 0.0), lines
            )
            self._emit_named(metric.name + "_sum", label_pairs, metric.sums.get(key, 0.0), lines)
            self._emit_named(
                metric.name + "_count", label_pairs, metric.counts.get(key, 0.0), lines
            )

    def _emit_sample(
        self, metric: _Metric, key: Tuple[str, ...], value: float, lines: List[str]
    ) -> None:
        label_pairs = list(zip(metric.label_keys, key, strict=False))
        self._emit_named(metric.name, label_pairs, value, lines)

    def _emit_histogram_line(
        self,
        metric: Histogram,
        label_pairs: List[Tuple[str, str]],
        value: float,
        lines: List[str],
    ) -> None:
        self._emit_named(metric.name + "_bucket", label_pairs, value, lines)

    def _emit_named(
        self, name: str, label_pairs: List[Tuple[str, str]], value: float, lines: List[str]
    ) -> None:
        if label_pairs:
            labels = ",".join(f'{k}="{v}"' for k, v in label_pairs)
            lines.append(f"{name}{{{labels}}} {value}")
        else:
            lines.append(f"{name} {value}")


def _format_bucket(bound: float) -> str:
    if bound == int(bound):
        return str(int(bound))
    return repr(bound)


REGISTRY = MetricsRegistry()

# Monitoring wiring (H2.2, G22)

The service exposes operational telemetry at `/metrics` in the Prometheus
text exposition format. Metrics are produced in-process by
`observability/metrics.py` (stdlib-only; no exporter sidecar, no network
egress from the service itself).

## What is exposed

| Metric | Meaning |
|---|---|
| `helix_http_requests_total{route,status,method}` | request count by route template |
| `helix_http_request_duration_seconds` | latency histogram by route template |
| `helix_governance_decisions_total{decision}` | allowed/denied/held/succeeded/failed |
| `helix_audit_chain_verifications_total{result}` | audit hash-chain verification outcomes |
| `helix_audit_chain_verification_failures` | monotonic count of verification failures |
| `helix_approval_queue_depth` | workflows frozen awaiting human approval |

Label values are a fixed vocabulary defined in `observability/metrics.py`
(route templates, HTTP status codes, decision buckets). Request payloads,
tenant ids, actor names and free-form strings never become label values, so
the exposition cannot leak secrets or PII.

## Auth

`/metrics` is **behind the standard bearer-token auth** (`current_identity`),
like every other API surface. It is not exempted: the exposition reveals the
API surface shape, traffic mix, governance decision rates and approval-queue
depth — deployment-sensitive operational data. A Prometheus server scrapes
with the same token every other client uses:

```yaml
scrape_configs:
  - job_name: helix-codex-os
    scrape_interval: 15s
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials: <same token as HELIX_API_TOKEN>
    static_configs:
      - targets: ["helix-host:8000"]
```

## Alert rules

`alerts.yml` in this directory is Prometheus rule-file config (not prose):
add `rule_files: infra/monitoring/alerts.yml` to the same Prometheus config.
`tests/test_metrics.py` asserts every metric referenced by the rules is
exported by `observability/metrics.py`, so the two cannot drift.

## Sentry

Not installed. There is no DSN and no SDK dependency; error telemetry is the
structured `http_request` log lines (correlation id, route, status, duration)
plus the metrics above. If Sentry is ever added, it must ship behind a
`HELIX_SENTRY_DSN` env var that defaults to disabled — until then this
paragraph is the record of that decision.

## Verification

```
.venv-py312\Scripts\python.exe -m pytest tests/test_metrics.py -q
```

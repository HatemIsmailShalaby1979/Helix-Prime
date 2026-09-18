# Monitoring wiring (H2.2, G22)

The service exposes operational telemetry at `/metrics` in the Prometheus
text exposition format. Metrics are produced in-process by
`observability/metrics.py` (stdlib-only; no exporter sidecar, no network
egress from the service itself).

## What is exposed

| Metric | Meaning |
|---|---|
| `helix_http_requests_total{route,status,method}` | request count by route template (core and app routes) |
| `helix_http_request_duration_seconds` | latency histogram by route template |
| `helix_governance_decisions_total{decision}` | allowed/denied/held/succeeded/failed |
| `helix_audit_chain_verifications_total{result}` | audit hash-chain verification outcomes |
| `helix_audit_chain_verification_failures` | monotonic count of verification failures |
| `helix_approval_queue_depth` | workflows frozen awaiting human approval |
| `helix_readiness_check_failures_total{check}` | readiness probe failures by check (`workflow_store`, `audit_chain`) |
| `helix_auth_events_total{event}` | sign-in outcomes (`login_success`, `login_failure`, `login_throttled`, `login_locked`) |
| `helix_kill_switch_events_total{event}` | halt engagements, releases, denials (`engaged`, `released`, `denied`) |
| `helix_data_disk_free_bytes` | free bytes on the volume holding the databases |

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

## Alert catalog: meaning and response

An operator identifies a failed instance from these alerts plus the
structured logs — never by opening raw database files.

| Alert | Severity | Meaning | Response action |
|---|---|---|---|
| `HelixScrapeDown` | critical | `/metrics` unreachable for 2 min | Check the process is up (`/healthz`); check the scrape token |
| `HelixHTTP5xxRatio` | warning | >5% server errors for 10 min | Read the failing route from the `route` label and the structured `http_request` lines; fix forward, do not restart blindly |
| `HelixHTTPLatencyHigh` | warning | p95 latency >2.5 s for 10 min | Check disk pressure and queue depth; look for slow routes in the duration histogram |
| `HelixGovernanceDenialSpike` | warning | denial rate doubled vs 4 h baseline | Check whether policy/catalog changed or requests are probing; review the audit trail |
| `HelixAuditChainVerificationFailure` | critical | chain verification failed | Treat as integrity incident: export evidence, run the release gate, gate traffic away until the chain verifies |
| `HelixApprovalQueueBacklog` | warning | queue >20 for 30 min | Page the approval owners; work is piling up awaiting humans |
| `HelixApprovalQueueStarved` | info | queue drained | No action; distinguishes healthy from broken metrics |
| `HelixReadinessCheckFailing` | critical | `/readyz` failing (`{{ $labels.check }}` names the check) | Gate traffic away; `workflow_store` → check the database volume; `audit_chain` → verify the audit database file exists and is intact, then restart to re-initialize |
| `HelixAuthFailureSpike` | warning | >30 failed/throttled sign-ins per min for 15 min | Query `login_events` for source addresses; possible credential spray — confirm throttling holds, consider blocking the source at the proxy |
| `HelixKillSwitchEngaged` | warning | halt engaged in last 15 min | Verify it was intentional in the audit trail; while engaged, committal actions are denied by design |
| `HelixDiskSpaceLow` | warning | data volume below 1 GiB for 10 min | Prune aged backups (`--prune-root`, keep-newest safety); extend the volume |
| `HelixDiskSpaceCritical` | critical | data volume below 256 MiB | Stop the app cleanly now, free space or extend the volume, restart and verify `/readyz` before serving |

Beyond Prometheus, three queryable stores carry the same signals: the
structured `http_request` log lines (core `observability/logs.jsonl`,
app stdout — correlation id, route template, status, duration, tenant,
actor; secrets redacted or never logged), the app `login_events` table
(every sign-in outcome incl. throttles and locks), and the backup
manifest (`verified` flags per dimension). A failed backup or restore is
visible in its exit code and manifest without opening any database.

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

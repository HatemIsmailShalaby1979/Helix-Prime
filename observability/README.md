# Observability — Helix Prime C3

Local-first, no cloud.

## Modules

- `logging.py` — `log_structured(event_type, correlation_id, causation_id, workflow_id, task_id, tenant_id, client_id, actor, actor_type, role_id, capability, tool, duration_ms, result_status, error_code, retry_count, model_status, payload, log_path="observability/logs.jsonl")` → dict + appends JSONL (one JSON per line, `observability/logs.jsonl` gitignored via `*.log` + `*.db`). Validates required fields, `duration_ms`/`retry_count` ints.

- `health.py` — `check_health(db_path, ollama_url)` → `Dict[str, HealthStatus]` for 6 components: `control_plane_store` (Store can list), `event_replay` (replay empty), `capability_registry` (`wfm_forecast→ops_gm`), `role_catalog` (9 roles), `ollama` (`GET http://localhost:11434/api/tags` 2s timeout, `ok=False` if not reachable but not fatal unless `require_ollama=True`), `filesystem` (evidence/control_plane/security/observability/organization/contracts). `HealthStatus(ok, message, details)` + `is_healthy(results, require_ollama=False)`.

## Usage

```python
from observability.logging import log_structured
from observability.health import check_health, is_healthy

log_structured(event_type="workflow_succeeded", correlation_id="corr1", workflow_id="wf1", actor="sami", capability="wfm_forecast", result_status="succeeded", duration_ms=123)
health = check_health()
assert is_healthy(health)  # ollama optional
assert health["control_plane_store"].ok
```

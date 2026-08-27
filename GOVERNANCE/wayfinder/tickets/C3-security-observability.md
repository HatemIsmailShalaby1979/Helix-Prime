---
id: C3-security-observability
type: research
status: open
labels: [wayfinder:research]
blocked_by: [C1-organization-contracts]
blocks: [C4-engine-productization, C8-production-pack]
---

## Question

What is the enterprise-grade security, privacy, and observability design that lets Helix be trusted with real operational data — in parallel with C2?

Must deliver (C3 exit gate): tenant/client boundaries, user/role/service identities, least-privilege; secret management via env/OS store + repo/CI credential scan; data classification (public/internal/client-confidential/personnel-sensitive/financial/regulated); retention/deletion/export/backup/restore/migration policies; append-only audit with integrity + access controls (no "immutable ledger" claim until tamper-evidence proven); structured logs/metrics/traces/correlation/health checks/model telemetry/alert thresholds; prompt/tool injection defenses, model output validation, PII redaction/escalation.

## Research tasks (delegate to /research subagents)

- OS secret stores vs env for Windows local-first: which for pilot?
- SQLite → tamper-evident audit: which integrity approach without claiming blockchain?
- PII minimization patterns for personnel + CRM data on local SQLite vs future cloud.
- Ollama telemetry: what logs/metrics needed for model/provider observability?

## Expected

- `docs/C3-threat-model.md` + `security/` policy docs
- Tests: access-control, backup/restore, audit-query + incident runbook.

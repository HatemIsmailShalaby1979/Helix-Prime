# Data Retention Policy

> Elected owner: Operations (`docs/operations/README.md`)
> Status: **operable today, manual only** — no scheduler, no automatic deletion.

## 1. Principles

1. **Governed memory is tamper-evident and append-only.** Every write — create,
   correct, supersede, delete, expire — is a record appended to a SHA-256
   hash-chained ledger (`memory/governed_memory.py`). Nothing is ever physically
   removed from the chain.
2. **Retention expires liveness, not existence.** `apply_retention()` marks
   records past their `retention_until` as `expired`. Expired records remain
   retrievable when explicitly requested (`include_expired=True`) and remain in
   the audit chain; they are excluded from default reads and from `retrieve_facts`.
3. **Deletion is a soft tombstone.** `delete()` appends a tombstone record. The
   original record is retained for audit. There is no hard-delete path.
4. **Fail visible, not silent.** Retention state transitions are explicit; there
   is no background task that can quietly purge data.

## 2. Record lifecycle states

`retention_status` transitions:

| State | Meaning | Set by |
|-------|---------|--------|
| `active` | Default; live and readable | creation |
| `corrected` | Superseded by a correction of the same fact | `correct()` |
| `superseded` | Replaced by a newer record (recommendation transitions etc.) | `supersede()` |
| `deleted` | Soft-deleted tombstone; kept in the chain | `delete()` |
| `expired` | Past `retention_until`; excluded from default reads | `apply_retention()` |
| `retained` | Pinned despite expiry (legal hold / evidence pack) | operator decision |

Expiry is monotonic: once `expired`, `apply_retention` never re-activates a
record. `retained` is the explicit override for evidence holds.

## 3. Expiry mechanics

```python
expired_count = memory.apply_retention(as_of="2026-01-01T00:00:00Z")
```

- Iterates all `active` records; any record with `retention_until < as_of` is
  flagged `expired`.
- `retention_until` is optional per record (default `None` = never expires).
- **It never deletes rows, files, or chain entries.**

Entry points that surface the same primitive:

| Caller | Purpose |
|--------|---------|
| `memory/governed_memory.py::apply_retention` | Canonical implementation |
| `capabilities/restaurant/runtime.py` | Pack runtime retention hook |
| `capabilities/sports_academy/runtime.py` | Pack runtime retention hook |
| `pilot/run.py` | Pilot runbook retention hook |

## 4. Scheduling & operations

- **There is no scheduler** (no APScheduler, no cron service, no background
  worker). Retention today is an **operator-initiated manual step**.
- Recommended cadence (manual or via cron-equivalent in the deployment layer):
  **daily**, aligned with the audit-chain verification run.
- Before applying retention, run `AuditTrail.verify_chain()` /
  `GovernedMemory.verify_chain()` so the pre-expiry chain state is recorded as
  verified.
- `apply_retention` is idempotent and safe to re-run; expiry is skipped for
  already-expired/retained/deleted records.

## 5. Default retention horizons

Package and capability packs set `retention_until` at record creation. Suggested
defaults (align with the client's data-processing agreement):

| Record kind | Default horizon | Rationale |
|-------------|-----------------|-----------|
| Verified outcomes / decisions | 36 months | Contractual evidence for the client |
| Recommendations / model inference | 12 months | Churn-risk and workflow suggestions are time-bound |
| Manual fee / payment records | 7 years | Accounting statute obligations |
| Simulated/demo records | 30 days | Synthetic data must expire first |

Expiry status is a classification-aware control: `retrieve()` honours
`max_classification`, so expired records are additionally gated by
classification level.

## 6. Evidence packs and the release gate

Evidence packs embed the audit chain at export time. Retention does **not** alter
records already captured in a shipped evidence pack — expiry affects the live
store only. Regenerate evidence packs at release time per the release manifest;
expired-but-retained records (`retained`) are exempt from expiry for the duration
of the hold (e.g., open regulatory matter).
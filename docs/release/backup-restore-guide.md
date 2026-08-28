# Helix Prime Codex C8 — Backup, Restore, Rollback Guide

Status: **Production Candidate / Controlled Pilot**

This guide documents the local-first durability procedures for the C8
`backup_restore`, `rollback`, and `audit_integrity` gates. All procedures are
backed by automated verification in `release/backup.py` and its tests.

## What is backed up

- Control-plane store: `control_plane/workflow.db`
- Audit trail: `security/audit.db`
- Integration transport/file state
- Evidence artifacts under `evidence/releases/`

## Backup

The automated backup snapshots the above into a timestamped backup directory and
writes a machine-readable `backup-manifest.json` (transaction-safe SQLite copy):

```python
from release.backup import backup_state
manifest = backup_state(backup_dir="path/to/backup", repo_root=repo_root)
```

## Restore

Restore is always into a **CLEAN, empty** destination directory — never in-place
over live data:

```python
from release.backup import restore_state, verify_restored_dbs
report = restore_state(backup_dir, target_dir, schema_ok=True)
verification = verify_restored_dbs(target_dir, workflow_aggregate="agg-x")
```

`restore_state` rejects a target that is not clean and rejects incompatible
schemas (fail closed). `verify_restored_dbs` proves:
- audit chain integrity preserved across restore,
- workflow events replay in order,
- restored state supports safe re-append (idempotency).

## Rollback

Rolling back to a previous release identity writes the previous manifest's
machine identity and records a rollback marker:

```python
from release.backup import rollback_manifest
rollback_manifest(previous_manifest, active_manifest, target_path=...)
```

## Schema compatibility

`release.backup.schema_compatible` fails closed on unsupported audit/store
schema versions. A restore with an incompatible schema is refused.

## Automated proof

The release gate runs a synthetic backup→restore→verify cycle on isolated temp
state (live DBs are never mutated) and reports a pass/fail in the
`backup_restore` and `rollback` gates.

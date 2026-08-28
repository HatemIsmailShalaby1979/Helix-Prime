# Helix Prime Codex C8 — Release Manifest

The release manifest is a machine-readable document describing the candidate/
pilot identity and boundary. Schema: `release/manifest.schema.json`.
Built by `release/manifest.py`.

## Fields

- `manifest_schema_version` (const `1.0`)
- `product` (const `Helix-Prime-Codex`)
- `release_profile` / `classification` / `release_approved`
- `version` (e.g., `0.9.0-c8`)
- `git_commit` / `git_branch` (resolved from the working tree)
- `build_timestamp`
- `python_version` / `platform` / `supported_python`
- `dependency_lock_ref` / `dependency_lock_count`
- `enabled_capabilities` / `disabled_capabilities`
- `data_schema_versions` (audit/store schema)
- `known_limitations`
- `evidence_refs` (path(s) to the generated evidence pack)

## Classification values

Allowed C8 final classifications: `CONTROLLED_PILOT_READY`,
`PRODUCTION_CANDIDATE`. `PRODUCTION` is permitted by the schema but is not
emitted by the C8 gate (production-only gates are not satisfied).

## Known limitations (recorded)

- Local SQLite only; no cloud redundancy/HA.
- Local filesystem permissions assumed; no external IdP.
- Ollama model trust assumed; no remote model attestation.
- Sibling transport local/in-process only.
- No autonomous irreversible/financial/personnel/compliance/ICT/external-
  communication actions.
- Pilot data limited to synthetic or consented data.

## Location of the committed artifact

The manifest is written to `release/release-manifest.json` on each gate run and
an evidence copy under `evidence/releases/<timestamp>/` (gitignored).

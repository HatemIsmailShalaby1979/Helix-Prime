# Helix Codex OS — Execution Status

**Execution profile:** C0 environmental alignment + C4–C8 productization

**Status language:** this document records what is implemented and smoke-verified
in the repository. It does not claim production approval, live data validity, or
external sibling-service deployment.

## Delivered controls

| Phase | Delivered | Evidence |
|---|---|---|
| C0 | Canonical dependency manifests and drift checker | `requirements.txt`, `requirements-dev.txt`, `scripts/check_dependencies.py` |
| C0 | Cross-platform SQLite lifecycle harness | `tests/support/sqlite_harness.py`, `tests/conftest.py`, `Store` context manager |
| C4 | Universal immutable request/result adapter contract | `engines/base_adapter.py`, `engines/adapters.py` |
| C4 | Six registered adapters | WFM, RTA, CX, CRM, Personnel, B2B; every adapter emits `TaskResult` + `ComputationEvidence` |
| C4 | Sample/live separation | `sample_data_mode=False` is the runtime default; sample payloads are refused unless explicitly enabled |
| C5 | Contact-centre seam | `control_plane/control_seam.py` implements RTA breach → OPS_GM recommendation → compliance gate → WFM recalculation |
| C5 | Cockpit operator surfaces | `cockpit/cockpit.py` adds Control Plane page with AWAITING_APPROVAL queue and audit timeline/hash display |
| C6 | GM activation manifest | `organization/gm_activation.py` validates seven remaining GMs against runtime RoleSpec + YAML catalog; all seven are active |
| C7 | Sibling-service boundary | `control_plane/schemas/sibling_events/boundary.py` prohibits imports/vendoring/direct stores |
| C7 | Versioned event contracts | `control_plane/schemas/sibling_events/` defines four v1 events + sealed envelope + published JSON Schema |
| C8 | Tenant-scoped storage | **Not implemented at the driver level.** Isolation is enforced by `security/policy.py::authorize` (policy seam), which denies cross-tenant requests. `control_plane/tenancy.py` claimed SQL-level scoping but was never invoked; removed 2026-09-11. |
| C8 | Local-first deployment profile | `infra/docker/Dockerfile`, `infra/docker/entrypoint.sh`, `infra/docker/docker-compose.yml` |
| C8 | Accelerator configuration | `config-files/acceleration.yaml` describes CUDA, DirectML and CPU fallback for Ollama |
| C8 | Governance evidence pack | `scripts/export_evidence_pack.py` exports uptime, communication history and hash validation trails |

## The control seam

```text
RTA breach alert
    ↓ measured fact + computation evidence
OPS_GM recommendation
    ↓ calculated proposal, never treated as a decision
Compliance verification gate
    ├─ awaiting_approval → run freezes; no recalculation
    ├─ denied            → run cancels; no recalculation
    └─ approved          → WFM recalculation
```

All four hops carry the same tenant, client and correlation context. Each hop
records its predecessor as `causation_id`. This is the minimum trace needed to
answer “why did staffing change?” without trusting a summary generated after the
fact.

## Runtime boundaries

- `sample_data_mode` is an explicit structural toggle. The default is `False`.
- `sqlite3` is a Python standard-library dependency and is intentionally not an
  installable package.
- `audit_events` is append-only and hash-chained. The evidence exporter returns
  a non-zero exit code when the chain is invalid.
- Sibling projects are external services. They exchange JSON events; they do not
  import, vendor, or directly query one another.
- Tenant isolation is enforced at the policy seam (`security/policy.py::authorize`)
  before a request reaches storage — not applied to a result set after retrieval.
  SQL-level (driver-level) partition filters are **not** implemented.
- GPU acceleration affects only optional Ollama model execution; deterministic
  engines and their evidence do not depend on it.

## Verification notes

- Python compilation passed for the new C4–C8 modules and the cockpit panel.
- The C0 dependency drift check passes against the canonical single manifest
  (`requirements.txt` + `requirements-dev.txt`; CI lock in `release/requirements.lock.txt`).
  The historical per-package `cockpit/requirements.txt` and `engines/*/requirements.txt`
  shims are gone — dependency declarations are consolidated at the repo root.
- The RTA/WFM seam smoke path passes for no-breach, awaiting-approval,
  approved/recalculated and denied branches.
- A full historical suite run exposed unrelated legacy teardown assumptions; the
  C0 fixture now closes tracked stores and raw connections before temporary
  directories are removed. Re-run the suite in CI after the remaining legacy
  fixtures migrate to `sqlite_store`.

## Not claimed

This execution does **not** claim that:

1. an external Helix Education, Study Studio or L&D Command Center endpoint is
   deployed;
2. an Ollama model is available on every host;
3. a human has signed a commercial production approval;
4. sample data is operational data;
5. the repository has zero pre-existing dirty worktree changes.

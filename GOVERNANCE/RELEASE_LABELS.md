# Helix Prime — Codex Release Labels

**Canonical source** for release gate definitions. No status may be claimed without the evidence listed.

| Label | Meaning | Entry gate | Evidence required | Who signs |
|---|---|---|---|---|
| `alpha` | Public alpha, real repo, no production claims | C0 baseline complete | `GOVERNANCE/capability-matrix.json` + `evidence/baseline/smoke.log` + README/ROADMAP truth-locked | Maintainer (you) + reviewer |
| `internal pilot` | Single-tenant local run with real data, human-supervised | C1 contracts + C2 workflow runner seam | Typed `TaskRequest/Result` contracts + one durable WFM→OPS→Compliance workflow with restart/timeout/duplicate/deny tests | ICT GM + Compliance GM |
| `controlled pilot` | Narrow client/ synthetic data pilot, approval-gated actions | C3 security + C4 engine productization + C5 vertical slice | Security threat model, backup/restore evidence, audit query evidence, KPI provenance, failure injection report | All 8 GMs + executive sign-off |
| `production candidate` | Ready for controlled production consideration | C8 pack | Load/soak/failure/security/data-integrity/upgrade tests + SLOs + runbooks + verified tenant isolation + synthetic pilot outcomes | External review + explicit go/no-go |
| `production` | Enterprise production | Production gate | No critical security issue, reproducible deploy, tested recovery, complete audit trail, bounded autonomy, owner per alert | Board/executive + Compliance & Quality |

## Evidence before status (non-negotiable)

- `implemented` = code imports, no evidence needed beyond file exists.
- `verified` = evidenced run in `evidence/runs/<id>/` with input/output/version/timestamp.
- `pilot` / `production-ready` require release evidence pack per `evidence/releases/<label>/` with input version, model, data classification, approvals.

## Versioning

`Cargo.toml`/`CHANGELOG.md` remain semver for code; labels above are governance gates orthogonal to semver.

## C0 baseline

Current label: **alpha** (README badge, ROADMAP). Do not advance without C0 exit gate signed.

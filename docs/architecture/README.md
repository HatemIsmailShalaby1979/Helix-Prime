# Architecture Documentation

This directory contains architecture and design documentation for the Helix Prime Ecosystem.

## Core Architecture Documents (in `docs/` root)

| Document | Audience | Description |
|----------|----------|-------------|
| `SYSTEM_ARCHITECTURE.md` | All | High-level system design — AI organization, engines, infrastructure, deployment |
| `ENGINEERING_SPECIFICATION.md` | Developers | Technical spec — repo structure, engine specs, API contracts, security posture |
| `PRODUCT_DEFINITION.md` | Product | Product requirements, buyer personas, capabilities, pricing, deployment phases |
| `COMMERCIAL_STORY.md` | Business | Business narrative — ROI, competitive positioning, churn prevention scenarios |
| `archive/GAP_ANALYSIS.md` | Engineering | Architecture compliance gap analysis — archived 2026-09-12 ("ALL GAPS RESOLVED"); superseded by the master blueprint |

## Deep-Dive Architecture References

| Document | Path | Description |
|----------|------|-------------|
| System Analysis & Design | `docs/archive/SYSTEM_AUDIT_2026-07-16.md` | Historical deep system analysis (archived) |
| Master Blueprint | `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` | Architectural + commercial record; governs implementation |
| Repository Graph | `architecture/REPO_GRAPH.md` | Live filesystem dependency topology |

## Supporting Documentation

| Folder | Contents |
|--------|----------|
| `archive/` | Historical analysis, MAP files, system audits, technical handoffs (read-only) |
| `operations/` | Runbooks, deployment guides, monitoring/alerting reference |
| `audits/` | Audit records and production-hardening plans (read-only, dated) |
| `portfolio/` | Client-facing architecture/security/evidence documents |

## Workspace Structure Reference

The authoritative source of truth for the workspace physical structure:

- **`00_CONSTITUTION.md`** (repo root) — governs authority; wins over any doc on conflict
- **`docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md`** — architecture + commercial record (implementation authority below the constitution)
- **`architecture/REPO_GRAPH.md`** — dependency graph with LOC counts
- **`AGENTS.md`** — build ledger: current step, completed steps, environment facts, git protocol

## ADRs (Architecture Decision Records)

To record an architectural decision, create a file here using the format:

```
adr-XXXX-title.md
```

Example: `adr-0001-use-chromadb-for-vector-store.md`

### Existing ADRs

*(No ADRs recorded yet. The architecture decisions are documented in `00_CONSTITUTION.md` and the master blueprint.)*

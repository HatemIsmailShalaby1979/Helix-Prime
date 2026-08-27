# Architecture Documentation

This directory contains architecture and design documentation for the Helix Prime Ecosystem.

## Core Architecture Documents (in `docs/` root)

| Document | Audience | Description |
|----------|----------|-------------|
| `SYSTEM_ARCHITECTURE.md` | All | High-level system design — AI organization, engines, infrastructure, deployment |
| `ENGINEERING_SPECIFICATION.md` | Developers | Technical spec — repo structure, engine specs, API contracts, security posture |
| `PRODUCT_DEFINITION.md` | Product | Product requirements, buyer personas, capabilities, pricing, deployment phases |
| `COMMERCIAL_STORY.md` | Business | Business narrative — ROI, competitive positioning, churn prevention scenarios |
| `GAP_ANALYSIS.md` | Engineering | Architecture compliance gap analysis — tracks recovery of lost engine code |

## Deep-Dive Architecture References

| Document | Path | Description |
|----------|------|-------------|
| System Analysis & Design | `AI OPS Engineering/HELIX_ECOSYSTEM_SYSTEM_ANALYSIS_AND_DESIGN.md` | Deep system analysis (v2.0) |
| Wiki Architecture | `AI OPS Engineering/Wiki/SYSTEM_ANALYSIS.md` | Architecture deep-dive |
| Repository Graph | `architecture/REPO_GRAPH.md` | Live filesystem dependency topology (generated 2026-07-20) |

## Supporting Documentation

| Folder | Contents |
|--------|----------|
| `archive/` | Historical analysis, MAP files, system audits, technical handoffs (read-only) |
| `operations/` | Runbooks, deployment guides, monitoring/alerting reference |
| `presentations/` | Stakeholder decks (Helix_Operators_Deck.pptx, Helix_Stakeholder_Deck.pptx) |
| `assets/` | Diagrams, images, and media assets (for embedding in architecture docs) |

## Workspace Structure Reference

The authoritative source of truth for the workspace physical structure is:

- **`ROOT_BOOT.md`** (repo root) — Constitution, check-in/out protocol, project registry, naming rules
- **`architecture/REPO_GRAPH.md`** — Mermaid dependency graph with LOC counts
- **`WORKSPACE_AUDIT_REPORT.md`** (repo root) — Full workspace audit

## ADRs (Architecture Decision Records)

To record an architectural decision, create a file here using the format:

```
adr-XXXX-title.md
```

Example: `adr-0001-use-chromadb-for-vector-store.md`

### Existing ADRs

*(No ADRs recorded yet. The architecture decisions are documented in `ROOT_BOOT.md` (Constitution) and the system analysis documents.)*

# Helix Prime — Roadmap

> **Classification:** PROJECT DOCUMENT
> **Rule:** No claim in this document may exceed what is verified in `MASTER_STORY.md`. This roadmap is replaced by this file when the previous draft is found to contradict verified reality. See `CHANGELOG.md` for the audit trail.

---

## Where the project actually stands

Helix Prime is a governed operations platform. It is `CONTROLLED_PILOT_READY`, not a product: it has no customers, no revenue, and makes no deployment claims.

**What is real today (verified):**

- 6 business engines: WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, CRM
- 9 AI agents: SAMI, SUBY, PHILI, WILI, ANDY (Compliance & Quality), NONO (Fraud), MAYA (Marketing), LIZA (Sales), TOMY (ICT), connected to a local Ollama model
- An orchestrator with content-based request routing
- **`helix-api`** — the governed FastAPI spine (`127.0.0.1:8000`), the one deployable artifact: identity, RBAC, approvals, kill switch, metrics, audit chain. The Streamlit cockpit is now a **read-only secondary diagnostic surface**.
- **Helix Codex App** — the first daily-use product layer (`helix_codex_app/`): identity, chat, documents, tasks, calendar, attendance, governed memory, and a low-code capability loader
- **2 vertical capability packs**: `capabilities/restaurant/` (the reference pattern) and `capabilities/sports_academy/` (first real vertical, built for Scoach Academy Hub)
- **C8 release gate** — `release/gate.py`, 29 gate implementations (14 core + 6 app + 9 production-only) across 5 named profiles
- A public repository at `github.com/HatemIsmailShalaby1979/Helix-Prime`
- **CI pipeline green** — `.github/workflows/ci.yml`, **all 17 steps passing** on `main` (run [`36497766876`](https://github.com/HatemIsmailShalaby1979/Helix-Prime/actions/runs/36497766876), 2026-09-29): ruff check, ruff format check, mypy, the full suite (**1,897 passed, 19 deselected**, coverage **86.91%** against an 80% floor), bandit, pip-audit, the six drift/registry/governance checks, package build, and both container steps. It had failed at step 5 on **every push from 2026-09-20 to 2026-09-28**, so steps 6–17 were never exercised until this run; see `AGENTS.md` for the repair record.

**What is explicitly NOT real yet — do not claim otherwise:**

- No client deployments and no production enterprise usage
- No pilot has ever run on real data; every pack runs `DATA_MODE = "simulated_realistic"`
- No revenue, no pricing model, no budget of a team that does not exist
- No certifications: no SOC 2, no ISO, no independent audit
- The 9 production-only gates remain red by design — they require external humans, external auditors, and legal review that do not exist
- No patent filings, no blockchain integration, no quantum-computing work

The control-plane `audit_events` ledger is append-only and hash-chained; it is implemented and exportable through `scripts/export_evidence_pack.py`. It is a local evidence mechanism, not a claim of production certification.

---

## Working agreements

This is a **one-person** effort. Everything below is sized for that reality.

1. **Truth over appearance** — a feature is "done" only when it has been run and observed in this session. A plan is a plan until it is executed.
2. **Filesystem over summary** — verify claims with commands, not with descriptions.
3. **Small, honest increments** — one working improvement shipped is worth more than a roadmap of promises.
4. **Anything fabricated is removed** — documents that overstate the project are corrected the same week they are found.

---

## Now (current focus)

1. ~~**Push the last commits.**~~ — **closed 2026-09-29.** `main` is level with `origin/main` at `1830f30`; there is no backlog. This item previously recorded that the owner had made the repository **private** on 2026-09-21 — that record was superseded. The repository is **public** (measured 2026-09-25; the owner confirmed public is the intended state), and an unauthenticated GitHub API request returns `"private": false`. Never trust a SHA or a backlog count written here; re-measure with `git ls-remote --heads origin main`, then `git rev-list --count <sha>..HEAD`.
2. **Run the pilot.** Turn Scoach Academy Hub from a named design partner into a dated pilot with a named operator and a consent record. This is the one gate that unlocks every commercial conversation.
3. **Close the external production gap (Classes 2–5)** — 21 external verification items that require humans or external parties, tracked in `docs/release/handoff/production-blockers-checklist.md`. These cannot be closed by engineering.

## Next (once the above is stable)

1. ~~**Demo assets**~~ — **resolved 2026-09-29.** The stale render was withdrawn
   from the distribution path: removed from the working tree (quarantined at
   `E:/_quarantine_2026-09-29/`) and excluded from both the Azure bundle
   (`marketing/azure.yaml`) and the Docker build context (`marketing/.dockerignore`).
   `index.html` never referenced it. This item previously said the `.vtt` also
   carried the retracted narration — **it did not**; the captions were regenerated
   from the corrected script in `c5a88ef` and are current. Closes issue #3. See
   `CHANGELOG.md`.
2. **Build the container** — the Docker daemon was unavailable during validation, so the first real `docker build` may surface problems that the 32 static packaging tests cannot see.
3. **Documentation consistency** — sweep remaining docs and screens for claims that exceed `MASTER_STORY.md`, and correct them the way this roadmap was corrected.
4. **Decide the public product name** — the repository says Helix Prime, the commercial layer says Helix Codex OS, and the manifest says Helix-Prime-Codex.

## Not on the roadmap

- No marketing of features that do not run yet.
- No invented team structure, budgets, or revenue targets.
- No fabricated customer names or "accounts exercised."

---

## Contact

Helix Prime is built and maintained by Hatem Shalaby. Public contact is via the GitHub profile: `github.com/HatemIsmailShalaby1979`.

*Any email addresses ending in `helixprime.io` found in older versions of this repository are fabricated and void.*

<!-- HELIX_ROLE_MATRIX:START -->
## Canonical RoleSpec matrix (generated)

This block is generated from `control_plane/governance.py`. Role IDs,
engine ownership, data classifications, approval limits and KPIs below
are structural facts; surrounding prose must not contradict them.

| RoleSpec ID | Engines | Classifications | Financial limit (USD) | KPIs | Oversight only |
|---|---|---|---:|---|---|
| `sami` | wfm, rta, cx, crm, b2b, personnel, control_plane | public, internal, client_confidential, personnel_sensitive, financial, regulated_high_risk | unlimited (human escalation) | system_health, operational_margin | False |
| `ops_gm` | wfm, rta, cx | internal, client_confidential | 500.00 | sla, service_level, occupancy, adherence, aht | False |
| `compliance_quality_gm` | none | public, internal, client_confidential, personnel_sensitive, financial, regulated_high_risk | 0.00 | quality_score, compliance_drift | True |
| `fraud_revenue_gm` | crm, b2b | internal, client_confidential, financial | 0.00 | leakage, anomaly_delta | False |
| `hr_personnel_gm` | personnel, wfm | internal, personnel_sensitive | 1000.00 | turnover_rate, time_to_hire | False |
| `ld_gm` | wfm | internal, personnel_sensitive | 200.00 | competency_score, time_to_competency | False |
| `sales_gm` | crm, b2b | internal, client_confidential | 2500.00 | pipeline_value, win_rate | False |
| `marketing_gm` | crm | public, internal | 500.00 | cac, lead_volume | False |
| `ict_gm` | control_plane | internal, regulated_high_risk | 5000.00 | engine_latency, model_timeout | False |

### Runtime aliases

| Alias | Canonical role / engine |
|---|---|
| `SAMI` / `sami` | `sami` |
| `SUBY` / `suby` | `ops_gm` |
| `PHILI` / `phili` | `hr_personnel_gm` |
| `WILI` / `wili` | `ld_gm` |
| `NONO` / `nono` | `fraud_revenue_gm` |
| `fraud_gm` (YAML compatibility alias) | `fraud_revenue_gm` |

### Limitations

- `None` financial limit does not mean autonomous unlimited approval; SAMI remains human-escalated.
- `oversight_only=True` means the role proposes/reviews and does not execute an engine.
- Unknown role, engine, classification or alias fails closed.
- This matrix is not a production certification or customer deployment claim.
<!-- HELIX_ROLE_MATRIX:END -->

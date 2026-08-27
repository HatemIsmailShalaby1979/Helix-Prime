# Helix Prime — Product Definition

> **Classification:** PROJECT DOCUMENT
> **Rule:** Every claim here must be traceable to `MASTER_STORY.md`. This version supersedes earlier drafts that contained a fabricated "proof ledger," invented customer accounts, and unverified commercial numbers.

---

## What Helix Prime is

Helix Prime is a **public alpha** operations system: six business engines (WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, CRM) and four AI agents (SAMI, SUBY, PHILI, WILI) connected to a local Ollama model, with content-based request routing and a Streamlit Operations Cockpit.

It is built by one person, Hatem Shalaby, after 28 years working on the operations floor — contact-centre forecasting, scheduling, onboarding, and floor management. It is the direct result of that experience: the system models the workflows he ran.

## What it is NOT (verified, per MASTER_STORY.md)

- ❌ **No production product.** It is alpha software. Nothing in it is described as "production-ready" without being run and observed in the same session.
- ❌ **No client deployments.** There are no customers, no "accounts exercised," and no production enterprise usage. Any document claiming otherwise is void.
- ❌ **No proof ledger.** There is no cryptographic proof ledger and no "immutable audit trail" in the codebase. No claim may reference "57 proof-ledger entries" — that figure was fabricated and has been removed.
- ❌ **No invented commercial numbers.** There are no validated ROI, waste, or savings figures. The "$1M/year," "$480K," "$320K," and similar figures in earlier drafts were invented and are void.
- ❌ **Not a finished agentic system.** Agent mechanisms exist and are proven in isolation; full inter-agent communication through the live UI is still pending.
- ❌ **Not a company.** There is no 10-15 person team, no engineering leadership, no budget, no patents, no revenue. Any roadmap or staffing document describing such a team is fabricated and void.

## What it is today

| Component | Status (verified) |
|---|---|
| WFM / Erlang C engine | Present |
| RTA engine | Present |
| CX Churn Sentinel | Present |
| B2B Onboarding | Present |
| Personnel engine | Present |
| CRM engine | Present |
| 4 AI agents (SAMI, SUBY, PHILI, WILI) | Present, connected to local Ollama |
| Orchestrator | Content-based routing |
| Operations Cockpit | Streamlit dashboard |
| CI pipeline | Live with pre-commit linting |
| Automated test coverage | Ongoing work |
| Inter-agent communication through live UI | Pending |

## Design principles

1. **Local-first, cloud-optional** — runs on consumer hardware with no mandatory cloud dependency.
2. **Crash isolation** — one failing component should not take down the system.
3. **No hardcoded configuration** — settings resolve through environment → config → safe default.
4. **Human-supervised autonomy** — the system proposes; humans approve and steer.
5. **Truth over appearance** — a feature is "done" only when run and observed in the same session.

## Deployment

Alpha, run locally. See the repository README for how to launch the cockpit. There is no supported deployment model beyond running the code yourself; the cloud configuration files in this repo (`render.yaml`, `azure.yaml`, `Dockerfile`) are scaffolding, not proof of a hosted service.

## Contact

Built and maintained by Hatem Shalaby. Public contact is via `github.com/HatemShelby/HatemShelby`.

*Built from 28 years on the operations floor, encoded into software — honestly, one verified increment at a time.*

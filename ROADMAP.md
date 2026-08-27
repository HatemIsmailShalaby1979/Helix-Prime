# Helix Prime — Roadmap

> **Classification:** PROJECT DOCUMENT
> **Rule:** No claim in this document may exceed what is verified in `MASTER_STORY.md`. This roadmap is replaced by this file when the previous draft is found to contradict verified reality. See `CHANGE_LOG.md` for the audit trail.

---

## Where the project actually stands

Helix Prime is a **solo-built, public alpha** operations system. It is not yet a product, has no customers, and makes no deployment claims.

**What is real today (verified):**

- 6 business engines: WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, CRM
- 4 AI agents: SAMI (CEO), SUBY (Operations), PHILI (Personnel), WILI (Learning & Development), connected to a local Ollama model
- An orchestrator with content-based request routing
- A Streamlit Operations Cockpit (dashboard)
- A public repository at `github.com/HatemShelby/Helix-Prime`
- CI pipeline live with pre-commit linting

**What is explicitly NOT real yet — do not claim otherwise:**

- No client deployments and no production enterprise usage
- No verified inter-agent calling proven through the live UI (the mechanism is proven in isolation; full UI proof is pending)
- No "proof ledger" and no "immutable audit trail" — such a thing does not exist in this codebase
- No revenue, no pricing model, no budget of a team that does not exist
- No patent filings, no blockchain integration, no quantum-computing work

---

## Working agreements

This is a **one-person** effort. Everything below is sized for that reality.

1. **Truth over appearance** — a feature is "done" only when it has been run and observed in this session. A plan is a plan until it is executed.
2. **Filesystem over summary** — verify claims with commands, not with descriptions.
3. **Small, honest increments** — one working improvement shipped is worth more than a roadmap of promises.
4. **Anything fabricated is removed** — documents that overstate the project are corrected the same week they are found.

---

## Now (current focus)

1. **Agent inter-communication through the live UI** — the orchestrator and agent mechanisms exist and are proven in isolation; the remaining work is demonstrating a full agent-to-agent flow through the actual cockpit UI.
2. **Automated test coverage** — build and grow the test suite so the alpha's claims are continuously verified by CI.
3. **CI polish** — keep the pre-commit linting pipeline green and extend it where it adds real protection.

## Next (once the above is stable)

1. **Lint and style debt** — Helix Prime carries its own backlog of lint findings (predominantly line-length and style). Cleaning it is real but low-priority, non-functional work.
2. **Documentation consistency** — sweep remaining docs and screens for claims that exceed `MASTER_STORY.md`, and correct them the way this roadmap was corrected.
3. **Demo assets** — rebuild or remove marketing audio/video assets whose scripts contain claims that are not verified (see `CHANGE_LOG.md`).

## Not on the roadmap

- No marketing of features that do not run yet.
- No invented team structure, budgets, or revenue targets.
- No fabricated customer names or "accounts exercised."

---

## Contact

Helix Prime is built and maintained by Hatem Shalaby. Public contact is via the GitHub profile: `github.com/HatemShelby/HatemShelby`.

*Any email addresses ending in `helixprime.io` found in older versions of this repository are fabricated and void.*

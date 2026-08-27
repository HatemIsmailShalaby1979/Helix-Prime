# Helix Prime — System Architecture

**An AI Organization.** Not a tool. Not a chatbot. Not a dashboard.

> **Engineers trust diagrams. Managers trust stories. Investors trust proof.**
> **Truth note:** This document was corrected against `MASTER_STORY.md`. Claims in
> earlier drafts about a "proof ledger" (57 entries), "every component runs today,"
> and a Flask webapp at port 5000 were fabricated or unverified and have been
> removed. Helix Prime is a **public alpha**; the architecture below reflects what
> exists in the repository, not what is proven to run end-to-end.

---

## One Diagram — The Helix Ecosystem

```mermaid
graph TB
    subgraph "HELIX PRIME - AI Organization"
        SAMI["SAMI - CEO / Strategist"]
        WILI["WILI - Learning & Development"]
        PHILI["PHILI - Personnel Director"]
        SUBY["SUBY - Operations Executive"]
    end

    subgraph "Business Engines"
        WFM["WFM Forecasting - Erlang C Staffing"]
        RTA["RTA Command Center - Real-Time Adherence"]
        CX["CX Churn Sentinel - Risk Scoring"]
        B2B["B2B Onboarding - SOP Generation"]
        PERS["Personnel Engine - Talent & Hiring"]
        CRM["CRM Engine - Sales Pipeline + Support"]
    end

    subgraph "Shared Infrastructure"
        MEM["Metacognitive Memory - TMK Loop"]
        DASH["Operations Cockpit - Streamlit"]
        ORCH["Orchestration - Content-based Router"]
    end

    subgraph "Security & Deployment"
        LOCAL["Local-First - Ollama + SQLite"]
        CLOUD["Cloud Optional - Scaffolding only"]
        SEC["Zero Secrets On Disk"]
    end

    SAMI -->|approves strategy| WFM
    SAMI -->|directs| PERS
    SAMI -->|reviews risk| CX
    SUBY -->|executes ops| RTA
    SUBY -->|manages| B2B
    SUBY -->|directs CRM| CRM
    PHILI -->|drives hiring| PERS
    WILI -->|generates training| MEM

    WFM -->|forecasts| MEM
    RTA -->|adherence data| MEM
    CX -->|risk scores| MEM
    B2B -->|onboarding status| MEM
    PERS -->|hiring pipeline| MEM
    CRM -->|pipeline & support| MEM

    MEM -->|learned patterns| DASH
    DASH -->|displays| MEM

    ORCH -->|runs on| LOCAL
    LOCAL -->|can extend to| CLOUD
    SEC -->|protects| ORCH
```

## How It Works — Plain Language

**Helix Prime** is a four-member AI leadership team that directs six operational engines, running on shared infrastructure that learns over time.

### The Leadership Team
- **SAMI** — The CEO. Sets strategy, approves staffing decisions, owns the system's north star. Reviews churn risks and directs the personnel strategy.
- **SUBY** — The Operations Executive. Runs real-time operations, monitors adherence, and manages client onboarding workflows.
- **PHILI** — The Personnel Director. Owns talent acquisition, candidate scoring, and hiring pipeline management.
- **WILI** — The Learning & Development Director. Creates training content and feeds lessons back into the system's memory.

### The Six Engines
Each engine is a specialized module that solves one operational domain. They are integrated but independently runnable.

### The Shared Infrastructure
- **Metacognitive Memory (TMK Loop)** — The system's long-term memory layer, storing results and detecting patterns across engines.
- **Operations Cockpit** — A Streamlit dashboard that gives human operators visibility into the engines and agents.
- **Orchestration Layer** — Routes requests to agents/engines according to content. The mechanism exists and is proven in isolation; full inter-agent communication through the live UI is still pending.

### Deployment
- **Local-First**: Runs on a standard laptop with Ollama for local inference and SQLite for storage. Zero cloud required.
- **Cloud-Optional**: The `marketing/` folder contains Render/Azure/Docker scaffolding for the marketing site. This is scaffolding, not evidence of a hosted service.
- **Security**: No secrets on disk, environment-var based configuration, hardened .gitignore.

### What is NOT running or proven
- No "proof ledger" and no "immutable audit trail" exists in the codebase.
- No Flask webapp at port 5000 is a current, verified service.
- No client deployments, no production enterprise usage, no customer accounts.

---

*Architecture designed and implemented by **Hatem Shalaby**. Constitution 000: Architecture serves as the expression of truth.*

---

## Access

| Service | URL | Description |
|---|---|---|
| **Dashboard (Streamlit Cockpit)** | http://localhost:8501 | Unified operational dashboard with all 6 engines |

# Helix Prime — Codex Upgrade Plan

**Status:** Proposed execution plan  
**Date:** 2026-08-27  
**Scope:** Additive expansion of the existing Helix Prime project  
**Target:** A dynamic, human-supervised, enterprise-grade AI organization for contact-centre and business operations

## 1. Executive decision

Helix Prime should enter a **Codex phase**, but it must not be described as production-ready yet.

The current repository is a real public alpha with:

- six engines: WFM/Erlang C, RTA, CX Churn Sentinel, B2B Onboarding, Personnel, and CRM;
- four agent implementations: SAMI, SUBY, PHILI, and WILI;
- a Streamlit Operations Cockpit;
- content-based orchestration, local Ollama inference, and cognitive logging;
- a large amount of implementation history recorded in governance documents.

The production gap is not simply “add four more agents.” The required upgrade is to build the missing **organization operating system** around the existing engines: typed contracts, durable workflows, authority boundaries, evidence, integrations, security, observability, deployment, and verification.

The eight requested GMs become the business leadership layer:

| GM | Primary accountability | Initial system ownership |
|---|---|---|
| HR & Personnel GM | People lifecycle, hiring, workforce policy | Personnel + WFM inputs |
| Marketing GM | Market intelligence, campaigns, positioning, demand | CRM/Sales data and approved content |
| Sales GM | Pipeline, qualification, proposals, revenue execution | CRM + B2B onboarding |
| Compliance & Quality GM | Policy, QA, risk controls, evidence, escalation | Cross-system control plane |
| ICT GM | Platform, integrations, security, reliability, release operations | Runtime and infrastructure |
| Fraud Analysis & Revenue Assurance GM | Leakage, abuse, anomaly detection, revenue protection | CRM/B2B/operations signals |
| L&D GM | Competency, training, assessment, knowledge transfer | WILI + Education/Study Studio/LDCC |
| OPS GM | Contact-centre execution and service performance | SUBY + WFM/RTA/CX |

SAMI remains the executive coordinator/CEO role. PHILI maps to HR & Personnel, WILI to L&D, and SUBY to OPS. The new GMs must be added through the same registry and contract as the existing agents; they must not become isolated scripts with bespoke behavior.

## 2. Current-state findings that drive the backlog

1. **Architecture is domain-rich but platform-light.** Engines are present and independently runnable, while the agent layer does not yet expose a stable typed tool/action interface to those engines.
2. **Routing is keyword-based.** It is a useful alpha seam, but it cannot safely handle multi-step workflows, conflicting ownership, confidence, policy checks, or approvals.
3. **Inter-agent calling exists, but is not yet an enterprise workflow runtime.** Calls are model-text driven, have a fixed recursion limit, and need structured requests, timeouts, idempotency, authorization, and durable state.
4. **The cockpit is an operator surface, not yet a control plane.** It needs workflow/task state, approvals, audit evidence, role-based access, tenant/client separation, and operational recovery.
5. **The system is local-first, not deployment-ready.** Ollama plus local files/SQLite are suitable for development and private pilots; enterprise operation requires backup, migration, secrets, observability, upgrade/rollback, and an explicit deployment profile.
6. **Evidence and repository hygiene are incomplete.** Git contains only two commits while governance logs describe later work; the tracked `.venv` creates a large noisy diff. No production claim should pass until the repository and evidence chain are reconciled.
7. **Sibling projects are valuable capabilities, not yet Helix Prime production dependencies.** Helix Education explicitly reports alpha status and no production connection. Study Studio has a provider-agnostic AI runtime and desktop experience. L&D Command Center has a more advanced local generation/export/playground stack and a pending Windows build. These should connect through contracts, not copied code or circular imports.

## 3. Non-negotiable Codex principles

- **Expand, do not erase:** retain all six engines, four agents, cockpit flows, and local-first behavior while placing stable interfaces around them.
- **Human-supervised autonomy:** agents may recommend and prepare actions; irreversible, financial, personnel, compliance, or external-communication actions require policy approval.
- **Every action is typed and attributable:** actor, tenant/client, authority, input version, tool, decision, outcome, timestamp, and evidence reference.
- **Fail closed for control decisions:** missing data, low confidence, policy conflict, or unavailable services produce a review queue—not silent execution.
- **One source of truth:** contracts, role catalog, policy catalog, data classifications, and release gates each have one canonical file/location.
- **Evidence before status:** `implemented`, `verified`, `pilot`, and `production-ready` are different states and require different evidence.

## 4. Ruthless execution order

### Phase C0 — Truth lock and baseline (P0, first 1–2 days)

**Outcome:** a trustworthy starting point and a clean execution board.

- Reconcile `README.md`, `ROADMAP.md`, `MASTER_STORY.md`, `GOVERNANCE/CHANGE_LOG.md`, and the actual source tree.
- Record one machine-readable capability matrix for agents, engines, UI flows, dependencies, and evidence.
- Reconcile the two-commit Git history with the claimed implementation history; preserve history where possible and record any imported/unverified work explicitly.
- Remove the virtual environment from version control through a reviewed, recoverable repository-hygiene change; do not delete the local environment until replacement setup is verified.
- Establish one test command that works on the supported platform(s), one smoke command, and one evidence directory convention.
- Define the Codex release labels: alpha, internal pilot, controlled pilot, production candidate, production.

**Exit gate:** clean status except intentional work, reproducible setup, baseline test/smoke results, and a signed capability matrix.

### Phase C1 — Organization model and contracts (P0, 3–5 days)

**Outcome:** all eight GMs can exist as governed roles without duplicating agent code.

- Add a canonical organization/role catalog: GM name, mission, capabilities, tools, data access, approval limits, escalation owner, KPIs, and allowed peer calls.
- Add an agent contract with structured `TaskRequest`, `TaskResult`, `Recommendation`, `Action`, `Approval`, `EvidenceRef`, `Error`, and `CorrelationContext` models.
- Replace model-invented `call_agent(...)` text as the primary mechanism with structured tool calls; retain the text path only as a compatibility adapter during migration.
- Add capability-based discovery rather than hardcoded name-only routing.
- Add workflow ownership and segregation-of-duties rules. Compliance & Quality must be able to review decisions made by OPS, Sales, HR, and Fraud.
- Define shared KPI vocabulary: SLA, service level, occupancy, adherence, AHT, FCR, CSAT, churn risk, pipeline value, leakage, quality score, competency, and time-to-competency.

**Exit gate:** every GM has a contract, a permission set, a test fixture, and a deterministic routing/ownership result for representative tasks.

### Phase C2 — Control plane and workflow runtime (P0, 1–2 weeks)

**Outcome:** Helix can run a durable business process, not only a chat request.

- Build a workflow/task runtime with states: proposed → validated → awaiting approval → executing → succeeded/failed/compensated → closed.
- Add durable correlation IDs, idempotency keys, deadlines, retries, cancellation, dead-letter/review queues, and compensation hooks.
- Add an event envelope and event store abstraction. Keep the initial implementation local-first; make storage replaceable without changing business engines.
- Add tool registry and adapters for each existing engine. An engine call must return a typed result and evidence, not console output or dashboard-generated placeholder data.
- Add policy evaluation before sensitive actions and approval capture in the cockpit.
- Add unified run history: task timeline, agent handoffs, engine calls, decisions, approvals, failures, and outputs.

**Exit gate:** a full WFM → OPS → Compliance review → HR/L&D escalation workflow runs from the cockpit with a restart, timeout, duplicate-request, and denied-approval test.

### Phase C3 — Enterprise data, security, and observability (P0, parallel with C2)

**Outcome:** the organization can be trusted with real operational data.

- Define tenant/client boundaries, user identities, roles, service identities, and least-privilege access.
- Introduce secret management through environment/OS secret stores; scan the repository and CI artifacts for credentials and sensitive data.
- Classify data: public, internal, client-confidential, personnel-sensitive, financial, and regulated/high-risk.
- Add retention, deletion, export, backup, restore, and migration policies.
- Implement append-only audit records with integrity protection and access controls. Do not call this an immutable ledger until tamper evidence and restore verification are proven.
- Add structured logs, metrics, traces/correlation, health/readiness checks, model/provider telemetry, and alert thresholds.
- Add prompt/tool injection defenses, model output validation, PII minimization/redaction, and human escalation for unsafe or uncertain outputs.

**Exit gate:** a security/privacy threat model, access-control tests, backup/restore evidence, audit-query evidence, and incident runbook exist and pass review.

### Phase C4 — Six-engine productization (P1, 2–3 weeks)

**Outcome:** the existing six engines become reliable services in the organization.

For each engine, add the same package of work:

- typed input/output contract and version;
- validation and data-quality checks;
- deterministic unit and property tests for domain calculations;
- engine adapter registered in the control plane;
- sample-data and real-data modes clearly separated;
- provenance/evidence for every recommendation;
- timeout, dependency, and partial-data behavior;
- operational KPIs and owner (GM);
- cockpit view for status, inputs, outputs, exceptions, and approvals.

Priority order: **WFM + RTA first**, then **CX + CRM**, then **Personnel + B2B**. This gives OPS a usable contact-centre vertical slice before broadening into sales and HR.

### Phase C5 — First enterprise vertical slice: contact-centre command (P0/P1, 1–2 weeks)

**Outcome:** one narrow scenario proves the organization model end to end.

Scenario: ingest interval/contact data → WFM forecast → RTA adherence signal → OPS recommendation → Compliance & Quality review → Personnel/L&D action → CRM/CX impact note → executive summary by SAMI.

Required proof:

- real engine outputs, not cockpit-side fabricated metrics;
- agent-to-agent handoffs visible in the run timeline;
- approvals and rejected actions visible;
- replayable run using the same input version;
- failure injection for missing data, unavailable Ollama, engine error, and policy denial;
- KPI report that distinguishes calculated values, model recommendations, and human decisions.

This is the Codex milestone that deserves a controlled pilot review.

### Phase C6 — GM expansion and business automation (P1, after C5)

Deliver in this order:

1. **Compliance & Quality GM:** QA sampling, policy checks, calibration, corrective actions, evidence packs.
2. **Fraud & Revenue Assurance GM:** anomaly rules, leakage cases, investigation workflow, financial-action approval.
3. **HR & Personnel GM:** requisition → screening → interview → hiring decision → onboarding, with bias/privacy controls.
4. **L&D GM:** competency gap → learning plan → content generation → assessment → certification → performance feedback.
5. **Sales GM:** lead → qualification → proposal → approval → handoff to B2B onboarding.
6. **Marketing GM:** approved market intelligence, campaigns, content review, attribution, and CRM feedback loop.
7. **ICT GM:** incident, change, release, access, integration, and platform health workflows.

Each GM ships only with a bounded mission, tools, approval matrix, measurable KPIs, and one end-to-end workflow. “Agent exists” is not a completion criterion.

### Phase C7 — Sibling-project integration (P1, designed in C1; implemented after contracts)

**Target relationship:** Helix Prime Codex is the parent organization/control plane; the sibling projects are specialized products/services.

```text
Helix Prime Codex
├── Organization, identity, policy, workflow, evidence, and executive coordination
├── Operations engines: WFM, RTA, CX, B2B, Personnel, CRM
├── Helix Education: learning-state and competency service
├── Study Studio: learner/content experience and provider-agnostic AI runtime
└── L&D Command Center: content production, media/export, career, and L&D operations tooling
```

Integration rules:

- **Helix Education** owns event-sourced learning state, competency, progress, sealed assessment keys, and adaptive paths. Helix Prime consumes/provides versioned competency and workforce-learning events; it does not copy Education’s state core.
- **Study Studio** owns the learner-facing experience and neutral provider runtime. Helix Prime may request approved content or provider capability through an adapter; Study Studio must not become a hidden dependency for core OPS execution.
- **L&D Command Center** is the production-workbench candidate for lesson/media/export/career workflows. Its existing typed pipeline, storage, connector hub, and desktop shell should be exposed through versioned service/CLI contracts after its Windows build and live integration gates are complete.
- **L&D GM/WILI** is the business owner and coordinator; the three sibling products remain implementation boundaries.
- Start with contract tests and file/event exchange locally. Add network services only after schemas, identity, retries, and ownership are proven.

First shared contract: `CompetencyGapDetected`, `LearningPlanRequested`, `LearningArtifactReady`, `AssessmentCompleted`, and `CompetencyUpdated`, all carrying tenant/client, employee, source, version, evidence, and correlation IDs.

### Phase C8 — Production candidate and controlled pilot (P0 gate, 2–4 weeks)

**Outcome:** evidence supports a real pilot decision.

- Package supported deployments: local single-node, private-network pilot, and optional cloud profile.
- Automate build, dependency lock, schema migration, backup, restore, rollback, and health checks.
- Run load, soak, failure, security, data-integrity, and upgrade tests.
- Establish SLOs for cockpit availability, workflow completion, engine latency, model timeout, and recovery.
- Create operator runbooks, on-call/escalation ownership, user training, release checklist, and incident process.
- Run synthetic or consented pilot data before any client data.
- Produce a release evidence pack and obtain explicit human approval for production-candidate status.

**Production gate:** no critical security issue, reproducible deployment, tested recovery, complete audit trail, bounded autonomy, verified data isolation, and an owner for every operational alert.

## 5. First sprint backlog — time-efficient starting cut

The first sprint should be small enough to finish and strong enough to unlock the rest:

| Priority | Deliverable | Acceptance proof |
|---|---|---|
| P0 | Codex capability matrix and canonical role catalog | Eight GMs + SAMI/PHILI/WILI/SUBY mapped to capabilities, tools, owners, approvals |
| P0 | Typed task/result/action contracts | Contract tests for success, refusal, timeout, invalid output |
| P0 | Structured workflow runner seam | One durable WFM/RTA workflow with correlation and idempotency |
| P0 | Engine adapter interface | WFM and RTA return typed results from actual engine code |
| P0 | Approval/policy seam | Compliance can approve/deny a proposed action; denial prevents execution |
| P0 | Baseline hygiene | Reproducible test/smoke commands; `.venv` and generated artifacts excluded from Git |
| P1 | Cockpit run timeline | Shows handoffs, tools, evidence, approvals, and failures |
| P1 | Truth/evidence record | One report states exactly what ran, with model, input, output, and environment |
| P1 | Sibling integration schemas | Competency/learning event contract drafted and contract-tested without live coupling |

Do not spend the first sprint on branding, speculative integrations, more dashboards, or adding agent personalities without authority/tool contracts.

## 6. Definition of done for “Helix Prime Codex”

Helix Prime may use the Codex name for the upgrade phase when C0–C5 are complete and the system can demonstrate the contact-centre vertical slice under failure injection.

It may be called **enterprise production-ready** only after C8’s release evidence pack is accepted. The bar is operational evidence, not code volume or the number of GMs.

Minimum evidence pack:

- architecture and data-flow diagrams;
- role/capability/approval matrix;
- versioned contracts and migration policy;
- test, coverage, load, security, and failure-injection results;
- deployment, backup/restore, rollback, and incident evidence;
- audit and data-isolation verification;
- pilot outcomes and explicit go/no-go decision.

## 7. Strategic conclusion

The fastest credible route is to make one complete, governed contact-centre workflow real, then reuse its contracts and control plane across the other GMs. The existing six engines and four agents are valuable foundations. The next value is not breadth; it is turning those foundations into a dependable organization that can observe, decide, act within authority, explain itself, recover, and teach its workforce across the Helix family.

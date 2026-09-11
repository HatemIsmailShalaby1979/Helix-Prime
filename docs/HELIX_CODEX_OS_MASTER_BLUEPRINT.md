# Helix Codex OS — Master Execution & Commercial Blueprint

**Subject:** Refactor + commercialize **Helix Prime** into **Helix Codex OS**
**Baseline audited:** 2026-09-07 · 174 `.py` files · 47,244 LOC · 26 test modules · ~445 tests
**Status of baseline:** `CONTROLLED_PILOT_READY` (production profile fails closed on 9 external gates — by design)
**Authority:** Sections 1–6 are the architectural + commercial record. Section 7 is the executable Phase 1 plan.

> This document is governed by `00_CONSTITUTION.md`. Where the two conflict, the constitution wins.
> Every claim below was verified by reading the source, not inferred from docs. Corrections to the
> original brief are recorded in §0 — they are deliberate and should not be "re-corrected" later.

---

## 0. Decisions Locked (confirmed with user)

| Decision | Choice | Consequence |
| --- | --- | --- |
| Frontend stack | **FastAPI + HTMX/Alpine.js**, server-rendered, SSE streaming | Python-only, no Node build step. `api/*.ts`, Tauri/Rust are dead — delete. |
| Ship vehicle | **Docker Compose first** (reuse `infra/docker/`), desktop app deferred | Fastest to revenue; `infra/` is currently *untracked* — must be committed. |
| Beachhead ICP | **Privacy-conscious, ops-heavy SMBs** (contact centres, BPOs, clinics, restaurants) | Existing WFM/RTA/CX engines are directly relevant. |
| Deliverable | Blueprint + **executable Phase 1 plan** (§7) | Phase 1 is ready to run on approval. |


### Three corrections to the brief's premises

1. **"C4–C8 adapters" is a misnomer.** C1–C8 are *phase codes*, not adapter types (`docs/HELIX_CODEX_UPGRADE_PLAN.md`). C4 = engine-adapter boundary, C5 = contact-centre vertical slice, C6 = GM expansion, C7 = sibling integration, C8 = production candidate. There are exactly **two** adapter generations (C4 live, C5 near-dead), not five.
2. **No local LLM abstraction exists to build on.** All 9 agents hardcode `model = "qwen3:8b"` and POST to `http://localhost:11434/api/generate`. `cloud/interfaces.py::ModelProvider` exists but is unimplemented. Local-first is currently *hardcoded*, not *architected*.
3. **The repo has no LICENSE file** (`MASTER_STORY.md`: "LICENSE: missing"). This is a **P0 blocker for commercialization** — an unlicensed repo cannot be sold, and open-core is undefined without one.

---

## SECTION 1 — Repository Audit & Baseline Mapping

### 1.1 Subsystem inventory

| Subsystem | LOC | Reality | Verdict |
| --- | --- | --- | --- |
| `engines/` (6 engines) | 13,041 | Deterministic **and real**: Erlang-C, RTA adherence, CX risk scoring, CRM pipeline, personnel, B2B onboarding. Zero `NotImplementedError`. | **Keep.** Genuine asset. |
| `control_plane/` | 6,611 | `Engine` (orchestrator, 47 KB) + `governance.py` bounded-autonomy gate + hash-chained `audit_events`. (`TenantScopedStore` was listed here but never existed as wired code — removed 2026-09-11; isolation lives in `security/policy.py`.) | **Keep, refactor.** |
| `memory/governed_memory.py` | 471 | JSONL append-only, SHA-256 hash chain, 6 natures × 9 kinds, tenant-scoped, retention. | **Keep, fix 1 defect.** |
| `metacognition/improvement.py` | 419 | Proposal → isolated evaluation → SOD-enforced approval → rollback. Never self-applies. | **Keep.** Constitutionally correct. |
| `connectors/` | ~1,000 | Excellent **contract layer**, but fakes only (`KNOWN_PROVIDERS = salesforce, zendesk, clay`; `SUPPORTED_MODES = ("fake",)`; `request_write` always returns `executed=False`). | **Extend.** No write path. |
| `cloud/` | ~600 | 8 provider-neutral ABCs (Database, ObjectStorage, EventTransport, SecretsStore, IdentityProvider, Observability, Scheduler, ModelProvider) + local adapters. Fail-safe config. | **Seam, not a feature.** Nothing to sync yet. |
| `cockpit/cockpit.py` | 80 KB monolith | Streamlit, 8 pages. Read-only command centre. | **Replace**, keep 1 release. |
| `capabilities/` | ~1,200 | Restaurant pack = 9 modules. **No base class, no manifest, no loader, no versioning.** Convention only. | **Formalize** (§2.3). |
| `app/command_center/agents/` | 31 KB | 9 agents. Inter-agent dispatch via **regex over LLM free text**. | **Rewrite dispatch** (§7 W6). |


### 1.2 Agent roster → super-app operational domain

Source of truth conflict: three definitions exist — `app/.../base_agent.py` (runtime), `organization/role-catalog.yaml` (C1 canonical), `control_plane/governance.py::ORGANIZATION_CATALOG` (enforced). **Money limits disagree by ~2 orders of magnitude** (e.g. `ops_gm`: YAML `20,000` vs RoleSpec `500.00`).

| Agent | Role ID | Domain | Super-App Surface | Engine |
| --- | --- | --- | --- | --- |
| SAMI | `sami` | CEO / strategist, escalation owner | **Inbox & Approvals** — triage, delegation | — |
| SUBY | `ops_gm` | Operations | **Ops Workspace** — forecasting, scheduling, adherence | WFM, RTA, CX |
| PHILI | `hr_personnel_gm` | Personnel | **People Workspace** — hiring, attrition | personnel |
| WILI | `ld_gm` | Learning & Dev | **People** — competency, curriculum | personnel |
| ANDY | `compliance_quality_gm` | Compliance & Quality | **Governance Rail** — mandatory reviewer | all (reviewer) |
| NONO | `fraud_revenue_gm` | Fraud / revenue assurance | **Risk Desk** — leakage, anomalies | CX, CRM |
| MAYA | `marketing_gm` | Marketing | **Growth Workspace** — campaigns, attribution | — (new) |
| LIZA | `sales_gm` | Sales | **CRM / Pipeline** — deals, B2B handoff | CRM, B2B |
| TOMY | `ict_gm` | Platform / ICT | **Admin Console** — integrations, releases | — |


SOD invariant already enforced: ANDY `can_review` ⊇ {ops_gm, sales_gm, hr_personnel_gm, fraud_gm}.

### 1.3 Technical debt register

| # | Debt | Severity | Disposition |
| --- | --- | --- | --- |
| D1 | Two adapter generations; C5 (`engines/base_adapter.py` 799 L + `adapters.py` 773 L) imported **only** by `control_seam.py`, **zero tests** | **High** | Harvest 4 ideas, delete both (§7 W2) |
| D2 | `role-catalog.yaml` vs `ORGANIZATION_CATALOG` authority divergence | **High** | Single source + generated catalog + drift test; **numbers unchanged** (policy decision, needs a signed record) |
| D3 | No packaging (`python -m build` cannot succeed); no real lock file | **High** | §7 W1 |
| D4 | Empty `requirements.txt` shims break `setup.bat`, `launch.bat`, `engines/b2b/Dockerfile`, CI | **High** | §7 W1 |
| D5 | `static.yml` publishes **entire repo** to GitHub Pages | **High** (leak) | Delete |
| D6 | `call_agent` regex dispatch, depth-capped 5 | **High** | §7 W6 |
| D7 | `Engine.submit` repeats an identical ~20-line error block ×8; `_audit` re-reads 10,000 rows per call | Medium | §7 W3 |
| D8 | 67 `except Exception`, 27 swallowed with `pass`; control flow by substring (`if "unauthorized" in str(e).lower()`) | Medium | Typed `EngineFailure(code, message)` |
| D9 | Zero `async def` in 47 K LOC | Medium | Async confined to `server/sse.py` only |
| D10 | Three storage systems (SQLite, JSONL, `security/audit.db`); no migrations | Medium | Consolidate audit; add migration tooling |
| D11 | `GovernedMemory.correct/supersede/delete` mutate in-memory flags but **never rewrite the persisted JSONL line** — flags lost on reload | Medium | Fix in Phase 3 |
| D12 | `_APPROVABLE = (EVALUATED, DRAFT)` lets **unevaluated** drafts be approved | Medium | Tighten to `(EVALUATED,)` in Phase 3 |
| D13 | Python version split 3.10/3.11/3.12/3.13 across 8 files | Low | Converge to **3.12** |
| D14 | No encryption at rest (zero hits for `encrypt | aes | fernet`) | Medium | Deferred, logged (§4.3) |


### 1.4 Gaps blocking the super-app

| Gap | Today | Needed |
| --- | --- | --- |
| Real frontend | Streamlit monolith | FastAPI + HTMX/Alpine (§2.2) |
| Real-time | none | SSE + HTMX out-of-band swaps |
| Docs editing | none | CRDT-ish or OT block store (Phase 2) |
| Connector write path | `executed=False` constant | `plan_write → approve → apply` (§7 W5) |
| Capability manifest | none | `capability.yaml` + loader + validator (§2.3) |
| AuthN/AuthZ for humans | none (agents only) | Session/JWT + role mapping to `RoleSpec` |
| Billing | none | Phase 4 |


---

## SECTION 2 — Product & Collaboration Architecture

### 2.1 The unifying insight

> Chat, docs, tasks, and workflows are **the same object** viewed through four lenses.

Model everything as a **`Node`** with an invariant envelope. This is what makes the metacognitive memory work — every user action is already a governance event.

```python
@dataclass(frozen=True)
class NodeEnvelope:
    node_id: str
    tenant_id: str              # never optional
    client_id: str | None
    correlation_id: str         # survives every boundary (constitution)
    causation_id: str | None
    classification: Literal["public","internal","client_confidential","restricted"]
    provenance: Provenance      # source, data_mode, retrieved_at
    nature: Literal["verified_fact","user_claim","model_inference",
                    "simulated_event","historical_event","verified_outcome"]
    created_by: str             # human user_id OR agent role_id — same field
    created_at: str

@dataclass
class Node:
    envelope: NodeEnvelope
    kind: Literal["message","document","block","task","workflow","decision","proposal"]
    body: dict                  # kind-specific payload
```

`created_by` accepting **either** a human or an agent role is the keystone: agents and humans write through the same store, through the same gate, producing the same audit trail. No separate "AI side-channel."

### 2.2 Surface architecture

```
┌───────────────────────────────────────────────────────────────────┐
│  Shell  (HTMX: hx-get/hx-post, Alpine for local UI state)         │
│  ┌──────────┬────────────────────────────────┬──────────────────┐ │
│  │ Rail     │  Workspace                     │  Agent Panel     │ │
│  │ Spaces   │  ┌──────────────────────────┐  │  Active agent    │ │
│  │ Channels │  │  Surface switch:         │  │  Visible         │ │
│  │ Docs     │  │  Chat │ Docs │ Tasks │   │  │  reasoning (SSE) │ │
│  │ Tasks    │  │  Flows                   │  │  Tool calls      │ │
│  │ Flows    │  └──────────────────────────┘  │  Proposals       │ │
│  │ Approvals│  Body: server-rendered partial │  Approval queue  │ │
│  └──────────┴────────────────────────────────┴──────────────────┘ │
│  Governance Rail: every mutating action → Engine.submit → gate     │
└───────────────────────────────────────────────────────────────────┘
```

**Transport strategy (solo-dev-appropriate):**

| Need | Mechanism |
| --- | --- |
| Page/partial updates | HTMX `hx-get`/`hx-post` → server-rendered Jinja fragments |
| Local UI state (modals, tabs) | Alpine.js, ~15 KB |
| Agent streaming, live notifications | **SSE** (`text/event-stream`) + HTMX `sse-swap` |
| Multi-user presence | SSE broadcast via in-process `asyncio.Queue` per `tenant_id` |
| Chat typing indicators | SSE; **defer WebSocket** until collaborative cursors are needed |


Rationale: SSE + HTMX gives 90% of "real-time collaboration" feel at ~10% of the cost of a CRDT/WebSocket stack. Yjs/Automerge is explicitly deferred to Phase 2+ and only for the Docs surface.

### 2.3 Low-code capability engine

`capabilities/` today is a convention, not a system. Formalize it — this is the Tier-3 revenue vehicle, so it must not require touching core code.

```
# capabilities/<pack>/capability.yaml   (new, required)
schema_version: "1.0"
id: restaurant
name: Restaurant Operations
version: 1.4.0
domain: food_service
min_core_version: "0.9.0"

read_only_start: true
synthetic_data_only: true
production_readiness: NOT_ESTABLISHED   # gate refuses live data below ESTABLISHED

ontology:                       # → generates SQLite tables + Node kinds
  - Employee
  - Shift
  - InventoryItem
  - Supplier
  - Complaint
  - DailySummary

roles:                          # → merged into RoleSpec catalog at load
  - id: restaurant_manager
    maps_to_agent: SUBY
    owned_capabilities: [schedule.shift, inventory.reorder]
    approval_limits: { tier: 2, max_financial_amount: 500.00 }

workflows:                      # → declarative triggers
  - id: low_stock_detect
    trigger: { on: schedule, cron: "0 6 * * *" }
    detector: metrics.low_stock
    action: propose_reorder
    risk_tier: 2                # → governance.evaluate_gate
    requires_approval_from: ops_gm

policies:
  authority_for: { reorder: ops_gm, refund: compliance_quality_gm }

connector_contracts:
  - { provider: local.pos, ops: [read_sales], mode: read_only }

data_classifications: [internal, client_confidential]
metrics: [food_cost_pct, labor_pct, complaint_rate]
failure_modes: [stale_inventory_feed, shift_overlap]
```

**Loader contract (new):**

```python
class CapabilityPack(Protocol):
    manifest: CapabilityManifest
    def ontology(self) -> dict[str, type]: ...
    def roles(self) -> list[RoleSpec]: ...
    def workflows(self) -> list[WorkflowDef]: ...
    def metrics(self) -> dict[str, MetricFn]: ...
    def runtime(self, memory: GovernedMemory, *, phase: Phase) -> CapabilityRuntime: ...

def load_pack(path: Path) -> CapabilityPack: ...        # validates manifest
def register_pack(pack: CapabilityPack) -> None: ...    # role/ontology/workflow merge
def validate_pack(pack: CapabilityPack) -> list[Violation]: ...   # fails closed
```

**Invariants the loader must enforce** (each is a test):

1. Pack roles cannot widen an existing core role's `max_financial_amount`.
2. Pack cannot register a capability already owned by another pack.
3. `production_readiness != ESTABLISHED` ⇒ live `data_mode` refused.
4. Manifests are semver-versioned; a pack declaring `min_core_version` above runtime refuses to load.
5. SOD: a pack role cannot review its own actions.

### 2.4 Competitive differentiation

| Dimension | Lark / Teams | Notion | Asana | Zapier | **Helix Codex OS** |
| --- | --- | --- | --- | --- | --- |
| Chat + Docs + Tasks + Workflows | ✅ | partial | tasks only | glue only | ✅ one object model |
| Native AI autonomy (agents that *act*) | assistant only | assistant | rules | triggers | ✅ 9 agents behind a governance gate |
| **Cost at 25 seats / yr** | ~$9k–$18k | ~$6k | ~$7k | ~$3k | **$0 self-hosted** / ~$2.7k cloud |
| Data residency | vendor cloud | vendor cloud | vendor cloud | vendor cloud | **customer's machine** |
| Runs offline | ❌ | ❌ | ❌ | ❌ | ✅ |
| Immutable audit trail | ❌ | ❌ | ❌ | ❌ | ✅ hash-chained |
| Self-improving ops | ❌ | ❌ | ❌ | ❌ | ✅ proposal + isolated eval + rollback |
| Domain engines (Erlang-C, adherence) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Vendor lock-in / exit | high | high | high | high | **low** — SQLite + JSONL |


**The honest positioning:** Helix Codex OS does **not** beat Lark on polish or Notion on document editing. It wins on **(a) total cost + data sovereignty** and **(b) AI that executes inside a governance boundary instead of just suggesting**. The wedge is the ops-heavy SMB already paying for 4–5 subscriptions and uneasy about where their data lives.

---

## SECTION 3 — Metacognitive Memory & Operational Engines

### 3.1 Success memory architecture

`GovernedMemory` is already well-designed. Extend, don't rebuild.

```python
CLASSIFICATION_LEVELS = ("public","internal","client_confidential","restricted")
NATURES = ("verified_fact","user_claim","model_inference",
           "simulated_event","historical_event","verified_outcome")
KINDS   = ("decision","recommendation","approval","outcome","failure",
           "correction","policy","customer_context","workflow_history")
```

**Write-path ownership** — every super-app action must emit a record:

| Actor | Emits | Nature | Writes to |
| --- | --- | --- | --- |
| Human user | `decision`, `approval` | `verified_fact` / `verified_outcome` | Governor (via `Engine`) |
| Agent | `recommendation` | `model_inference` | Agent runtime |
| Engine | `outcome` + metrics | `verified_outcome` (real) / `simulated_event` (sample) | Engine adapter |
| Gate | `approval` / `failure` | `verified_fact` | `Engine._audit` |
| Metacognition | `correction`, `policy` | `verified_fact` (post-approval) | `improvement.py` |
| Connector | `customer_context` | per `data_mode` | `connectors/gateway.py` |


**Critical rule (constitution: "simulated, historical, and live data remain visibly distinct"):** an engine running in `sample` data mode may **only** emit `simulated_event`. Never `verified_outcome`. Enforce with an assertion in `EngineResult.success()`.

**Retrieval for agent context** — GovernedMemory becomes the agent's long-term memory:

```python
memory.retrieve(
    tenant_id=..., client_id=...,
    kinds=("decision","outcome","policy"),
    max_classification="client_confidential",   # ceiling, not equality
    verified_only=True,                          # only verified_fact / verified_outcome
)
```

`verified_only=True` is the difference between a business brain and a hallucination amplifier.

### 3.2 Continuous improvement loop

Current engine is constitutionally correct — it never self-applies. Target loop:

```
 1. DETECT    detect_repeated_failures(records, threshold=3)  → FailureSignal
              detect_performance_drift(metric, baseline, recent, threshold=0.05) → DriftSignal
 2. PROPOSE   propose(kind ∈ workflow|policy|permission|memory_rule) → DRAFT
 3. EVALUATE  evaluate(proposal, historical_cases, simulated_cases, simulate) → EvaluationResult
              passed = delta >= min_improvement          # isolated, pure function
 4. REVIEW    approve(proposal_id, reviewer, approver_role, requester_actor, requester_role)
              SOD: reviewer == requester_actor ⇒ DENY
                   approver_role == requester_role ⇒ DENY
 5. DEPLOY    apply_proposal(runtime, proposal, actor, role_id)   # external; raises unless APPROVED
 6. OBSERVE   new outcomes → memory → back to 1
 7. ROLLBACK  rollback(proposal_id) — always available
```

**Two defects to fix in Phase 3:**

- **D11:** `correct`/`supersede`/`delete` set in-memory flags but never rewrite the persisted JSONL line. Fix: append a new tombstone record *and* rewrite the line, or make flags derive from the chain at load.
- **D12:** `_APPROVABLE = (EVALUATED, DRAFT)` permits approving an unevaluated proposal. Fix: `_APPROVABLE = (EVALUATED,)`.

**Human-in-the-loop surfaced in UI:** the Approvals rail shows proposals with their `EvaluationResult` (baseline rate, candidate rate, delta, cases evaluated), not just a yes/no. The approver sees the evidence — that is the product.

### 3.3 Engine autonomy within the workspace

| Engine | Entry point | Trigger | Autonomy target | Gate |
| --- | --- | --- | --- | --- |
| WFM | `ErlangCEngine.optimize_agents()` | schedule cron / forecast drift | propose schedule → human approves | `ops_gm`, tier 2 |
| RTA | `RTACalculator.calculate_adherence()` | real-time adherence breach | auto-detect + alert; propose remedy | `ops_gm` |
| CX | `RiskScorerEngine.score_customers()` | new signal batch | propose outreach; **never** auto-contact customer | `ops_gm` + `compliance_quality_gm` |
| CRM | `SalesPipeline` | stage change | update forecast, propose next action | `sales_gm` |
| Personnel | `PipelineManager` | attrition risk threshold | propose retention action | `hr_personnel_gm` |
| B2B | `OnboardingAutomator` | new client | draft SOP + staffing plan → approve | `sales_gm` → `compliance_quality_gm` |


**Autonomy ladder (per role, per capability):** `SUGGEST → PROPOSE → DRY_RUN → SUPERVISED (auto-execute + audit) → AUTONOMOUS`. The restaurant pack already declares `phase=SUPERVISED` with a `read_only_start` + `read_only_period` — generalize that pattern. No capability starts above SUPERVISED.

---

## SECTION 4 — Local-First, Privacy-Preserving Infrastructure

### 4.1 Zero-cost deployment topology

```
# infra/docker/docker-compose.yml  (exists; extend)
services:
  helix:
    build: .                      # python:3.12-slim, non-root uid 10001
    command: uvicorn server.app:create_app --factory --host 0.0.0.0 --port 8000
    environment:
      HELIX_ENV: local            # local | pilot | production
      HELIX_DB_PATH: /data/helix.db
      HELIX_AUDIT_DB_PATH: /data/audit.db
      HELIX_SAMPLE_DATA_MODE: "true"
      OLLAMA_HOST: http://ollama:11434
    volumes: [helix-data:/data]
    healthcheck:
      test: ["CMD","python","scripts/health_check.py"]
  ollama:
    image: ollama/ollama
    volumes: [ollama-models:/root/.ollama]
```

**Resource floor:** 2 vCPU / 4 GB RAM without Ollama; +4 GB and optionally a 6 GB GPU with `qwen3:8b`. Runs on a mini-PC, NAS, or a €5/mo VPS. `config-files/acceleration.yaml` already handles `auto|cuda|directml|cpu`.

**Fail-closed model policy (already in config, must be preserved):** *"If the model runtime is unavailable, fail the recommendation path closed; do not fabricate output."* Offline marker `[OFFLINE]` → `DEAD_LETTER`, never a plausible-sounding substitute.

### 4.2 Tenant isolation — what is real vs missing

**Already real (do not rebuild):**

- `security/policy.py::authorize` — **the single enforcement point** for tenant/client
  isolation; cross-tenant requests are denied before reaching storage
- ~~`TenantScopedStore` / `TenantViolation`~~ — **removed 2026-09-11.** Listed here as if
  real, but never referenced by any code path. Driver-level (SQL) partition filters are
  NOT implemented and are deliberately deferred; if required, implement inside `Store`.
- `connectors/base.py::_assert_scope` — cross-tenant enrich denied
- `security/secrets.py` redaction (`api_key`, `bearer`, `password`, `secret` → `[REDACTED]`)
- Hash-chained `audit_events` with no-update/no-delete triggers
- ~~`verify_isolation()` + `ensure_tenant_indexes()`~~ — removed with `tenancy.py`
  (2026-09-11); never invoked. Isolation is verified by
  `release/harness.py::_check_tenant_isolation`, which exercises
  `security/policy.py::authorize` and is wired into the `data_isolation` release gate.

**Missing → Phase 2/4:**

- Encryption at rest (none) — **deferred with rationale** (below)
- KMS / key management
- `pilot/scope.py` currently excludes raw transcripts, payment instruments, government IDs **by policy only**, not by mechanism
- Release gate correctly blocks: `certified_data_isolation`, `external_observer_audit`, `signed_production_evidence`

**Zero-knowledge boundary rule:** `tenant_id` + `classification` + `correlation_id` are attached at the *edge* (HTTP middleware) and carried by a context object through every layer. A function that cannot see tenant context cannot write.

### 4.3 Encryption decision (deliberate deferral)

Encryption at rest is **deferred to Phase 2**, and this must be a written decision, not an omission:

- It conflicts with keyless unattended start on a self-hosted box (someone must supply the key).
- It is not demanded by the constitution.
- The controls that matter most to the ICP — data never leaving their machine — are already delivered by local-first.

**Interim:** full-disk encryption is the deployment's responsibility, documented in the operator runbook. **Phase 2 design:** OS keyring (DPAPI / Keychain / `libsecret`) → envelope encryption for `restricted` columns only. Log as `docs/SECURITY-DEBT.md`.

### 4.4 Cloud-ready sync (the optional path)

`cloud/interfaces.py` already defines 8 provider-neutral ABCs with local adapters — the seam is right. Build sync **on that seam only**:

```python
class SyncAdapter(Protocol):
    def push(self, tenant_id: str, since: str) -> PushReceipt: ...
    def pull(self, tenant_id: str, since: str) -> PullReceipt: ...
    def reconcile(self, tenant_id: str) -> ReconciliationReport: ...
```

**Design constraints:**

- **`GovernedMemory` is append-only and hash-chained → sync is trivially safe.** Replicas sync by exchanging tails and verifying the chain. This is the single biggest architectural payoff of the existing design.
- **SQLite is *not* CRDT-safe.** Do not multi-master it. Use single-writer + read replicas; workspace state is authoritative on one node.
- Encrypted blobs only; `CloudConfig.resolve()` already fails closed if any `cloud_services` value ≠ `"local"` or if `cloud_demo` carries credentials. **Preserve this.**
- Sync is **opt-in and off by default**; `HELIX_ENV=local` must never touch the network.

---

## SECTION 5 — Commercialization & Monetization (Solo Developer)

### 5.1 Validation — does this deserve to be built?

**Problem Assessment (ICP: privacy-conscious ops-heavy SMB, 10–100 seats)**

| Dimension | Rating | Impact |
| --- | --- | --- |
| Frequency | Daily — fragmented tooling is a constant tax | **High** |
| Severity | Important — cost + compliance exposure, not existential | Med |
| Awareness | Aware of the pain, **not actively shopping** | Med |
| Budget | Has budget — already paying for Lark/Notion/Asana/Zapier | **High** |


2 High + 2 Medium → **moderate-to-strong**. The weakness is *awareness*: nobody is searching for "self-hosted governed AI ops OS." GTM must create the category in a narrow niche, not capture existing demand.

**PCV Score**

| Dimension | Current problem | Our improvement | Points |
| --- | --- | --- | --- |
| Price | Serious (per-seat stacking: 4–5 tools) | Serious (zero marginal cost) | 3 + 3 = **6** |
| Quality | A problem (fragmented, no single truth) | Some | 1 + 1 = **2** |
| Performance | Not a problem | Some (local = no latency, offline) | 0 + 1 = **1** |
| Convenience | Serious (context-switching) | Some — **self-hosting is less convenient than SaaS** | 3 + 1 = **4** |


**Total: 13 / 24 → "Strong — worth pursuing."**

The convenience penalty is real and is the #1 GTM risk. Mitigation: the managed-cloud tier must be one click, and the installer must reach a working workspace in **under 10 minutes**.

### 5.2 Tiered monetization

**Open-core boundary (the only decision that really matters):**

| In Community (free, self-host) | In Paid (cloud / packs / enterprise) |
| --- | --- |
| Chat, Docs, Tasks, Flows (unlimited users) | Managed hosting + offsite backup |
| All 6 engines, sample data mode | **Live `data_mode`** + live connectors |
| GovernedMemory + audit trail | Multi-node sync |
| 9 agents, local LLM | Cloud AI fallback (when Ollama unavailable) |
| Single tenant | Capability packs (restaurant, clinic, logistics, B2B) |
| Community support | Compliance/compliance-evidence module, SSO, priority support |


> **The sharpest line: sample data is free, live data is paid.** It is technically enforceable (`data_mode` is already in every contract), honest, and gives away real value while keeping the revenue lever.

| Tier | Price | Contents |
| --- | --- | --- |
| **T1 Community** | **$0** | Self-hosted, unlimited seats, sample mode, core surfaces + engines. AGPL-style or BSL-1.1 (see §5.5). |
| **T2 Helix Cloud** | **$9/seat/mo** annual, **$12** monthly (min 5 seats) | Hosting, encrypted offsite backup, sync, cloud AI fallback, live connectors. |
| **T3 Capability Packs** | **$49–$499/mo** per pack, or **$1,500–$5,000** one-time perpetual | Restaurant, clinic, logistics, B2B onboarding. Compliance module: +$199/mo. |
| **T4 Enterprise** | **$15k–$50k/yr** | SSO/SAML, audit export, certified isolation program, SLA, named support. **Not before Phase 4 + compliance work.** |


**Revenue math for a solo dev:** 40 cloud customers × 15 seats × $9 = **$5,400 MRR** (~$65k ARR) at ~95% gross margin before the founder's time. Plus 10 pack licenses ≈ $25k one-time. That is a sustainable solo business. 400 customers = ~$650k ARR and the point where hiring is required.

### 5.3 GTM — 0 to 1 for one person

**Phase A — Design partners (months 0–3, target 3–5 paying):**

1. Do **not** build the marketplace first. Sell the outcome: *"Replace Lark + Notion + Zapier + your WFM tool with one box you own."*
2. Where to find them: r/selfhosted, r/sysadmin, Lemmy self-hosted communities, local BPO/contact-centre owner groups, restaurant-owner Discord/Facebook groups, EU data-residency and GDPR forums, Indie Hackers / Hacker News "Show HN".
3. Offer: **free migration + 50%-off-for-life** in exchange for a public case study and a weekly feedback call.
4. Lead with the **cost teardown**: a one-page per-seat comparison against their current stack. This is the single highest-converting asset.

**Phase B — Funnel (months 3–9):**

- Top: `Show HN` + a public **live demo instance** (sample data) — safe to expose because sample mode is enforced.
- Middle: **"Self-host cost calculator"** interactive page (this is where the `ab-test-setup` playbook applies — see §5.4).
- Bottom: 10-minute installer + 20-minute guided onboarding call.
- Content: one deep post per month on *governed AI autonomy* — the differentiator nobody else has.

**Phase C — Expansion (months 9+):** capability packs as the upsell; agency reseller channel (agencies host for clients and keep margin).

**Positioning statement:**

> Helix Codex OS is the operations OS for teams that can't put their data in someone else's cloud. Chat, docs, tasks, and AI agents that actually execute — behind an audit trail, on your own hardware, for a fraction of your current subscription stack.

### 5.4 Experimentation (lightweight, solo-appropriate)

Do not build an A/B framework. Run **two** tests, sequentially, on the top-of-funnel page:

| Test | Hypothesis | Variants | Duration |
| --- | --- | --- | --- |
| Positioning | "Own your data" outperforms "Save money" | A: privacy/sovereignty headline · B: cost-teardown headline | 3–4 weeks |
| Pricing anchor | Per-seat undercuts a flat workspace fee for <25 seats | A: $9/seat · B: $149/workspace flat | 4 weeks |


Measure signup→install→activated-workspace. With solo-dev traffic, 4 weeks gives directional but not significant results — **treat these as qualitative signal, not statistical proof**, and say so publicly.

### 5.5 Packaging & onboarding automation

**Installer must be one command:**

```
curl -fsSL https://get.helixcodex.os/install.sh | bash
# → checks Docker + Compose, writes .env, pulls images, runs migrations,
#   seeds sample workspace, prints http://localhost:8000 and a one-time admin token
```

**In-product onboarding (zero-touch):**

1. **Workspace wizard** — name, industry → auto-suggests a capability pack.
2. **Sample-data tour** — every surface pre-populated, `data_mode=simulated_realistic` banner visible at all times (constitution requirement, and it doubles as a trust signal).
3. **First real action** — "Connect one data source" (CSV upload first; live connectors later).
4. **Agent activation ladder** — start every agent at `SUGGEST`; the UI prompts to promote to `PROPOSE` after N accepted suggestions. Autonomy is earned, which is both safer and better marketing.

**Support overhead control:** in-app evidence export (`scripts/export_evidence_pack.py` already exists) → one file, one click, full diagnostics. This is the highest-leverage support investment a solo dev can make.

### 5.6 P0 blocker

**There is no LICENSE file.** No commercialization is possible until this is resolved. Recommended: **BSL 1.1** (source-available, converts to Apache-2.0 after 4 years) for the core — it permits self-hosting while protecting the managed-cloud tier from a competitor. Community sentiment will prefer AGPL-3.0, but BSL protects the revenue model. Resolve before Phase 4.

---

## SECTION 6 — Phased Roadmap

| Phase | Goal | Duration | Exit gate (all must pass) |
| --- | --- | --- | --- |
| **1 — Foundation & Core Refactoring** | Packageable, service spine, dead code gone, connector write path, structured agent dispatch | 4–6 wks | `python -m build` green · full suite green (≥ baseline) · ruff + mypy clean on `server/`+`connectors/` · `docker compose up` → `/readyz` 200 |
| **2 — Super-App Collaboration Suite** | Chat, Docs, Tasks, Flows + agent rail on HTMX/SSE; human auth; capability loader | 10–14 wks | 3 design partners complete a real workflow end-to-end with zero developer hand-holding · SSE latency p95 < 500 ms |
| **3 — Metacognitive Memory & Autonomous Ops** | Close the self-learning loop; fix D11/D12; engine autonomy ladder | 8–10 wks | ≥1 approved improvement proposal measurably improves a metric in production · audit chain verification 100% over 90 days |
| **4 — Commercialization Launch** | Billing, installer, pack marketplace, GTM release | 8–10 wks | First paying customer · 10 unassisted installs in 30 days · LICENSE committed |


**Sequencing principle:** Phase 1 creates no user-visible value — it exists to make Phases 2–4 possible without rewriting. Resist the urge to build UI first; the `call_agent` regex and the missing write path will poison anything built on top of them.

---

## SECTION 7 — Phase 1 Implementation Plan (ready to execute)

### W0 — Pre-flight (blocking)

**Do not start W1 until `git status` is clean.** 15 modified + 21 untracked paths carry the newest load-bearing code (`control_plane/{control_seam,governance,tenancy}.py`, `control_plane/schemas/`, `engines/{adapters,base_adapter}.py`, `requirements*.txt`, `tests/conftest.py`, `tests/support/`, `scripts/`, `infra/`, `organization/gm_activation.py`). Refactoring with half the system uncommitted means no diff and no revert.

1. Commit untracked work: `chore: land untracked C5/C8 work before Phase 1`
2. `git rm --cached control_plane/workflow.db`; add to `.gitignore`: `.venv/`, `.venv-win/`, `__pycache__/`, `*.db*`, `.pytest-tmp/`, `.tmp/`
3. Record baseline: `python -m pytest tests/ -q -m "not smoke"` → **count in `docs/PHASE1_BASELINE.md`**. Every later gate = "count ≥ baseline, 0 failures".

**DoD:** clean `git status`; tracked DB gone; baseline recorded.

---

### W1 — Packaging & reproducibility

**Create `pyproject.toml`:**

- Build backend **`hatchling`**; explicit package list, **not** auto-discovery (auto-discovery would swallow `demo/`, `marketing/`, `tests/`):
`control_plane, engines, organization, security, observability, contracts, connectors, metacognition, memory, capabilities, pilot, customer_success, integrations, server`
- `requires-python = ">=3.12,<3.13"` — **canonical 3.12** (matches `mypy.ini` and the shipping `infra/docker/Dockerfile`)
- `[project.dependencies]` = the 14 existing runtime deps verbatim; `[project.optional-dependencies] dev` = `requirements-dev.txt`; **`web`** = `fastapi>=0.115, uvicorn[standard]>=0.30, jinja2>=3.1, sse-starlette>=2.1, pydantic-settings>=2.5, httpx>=0.27`
- Consolidate `ruff.toml` → `[tool.ruff]`, `mypy.ini` → `[tool.mypy]`, `pytest.ini` → `[tool.pytest.ini_options]` (keep `pythonpath = ["."]` — 26 test modules depend on it)

**Lock:** `uv pip compile pyproject.toml -o requirements.lock.txt --generate-hashes`. Delete `release/requirements.lock.txt` (fake lock); repoint `RELEASE_PROCESS.md`. CI installs the lock.

**Version convergence to 3.12:** `setup.bat:11`, `setup.sh:11,14,22`, `README.md:54`, `DEVELOPMENT.md:18`, `CONTRIBUTING.md:30`, `cockpit/RELEASE_README.md:8`, `engines/b2b/Dockerfile:3`, `marketing/Dockerfile:7`, `.github/workflows/{python-app,python-publish}.yml`.

**Empty shims — delete + fix 4 consumers in the same commit:**

- Delete `cockpit/requirements.txt`, `engines/b2b/requirements.txt`, `engines/cx/requirements.txt`
- `setup.bat` → install from root `requirements.txt`
- `engines/b2b/Dockerfile` → remove the `COPY engines/b2b/requirements.txt` line
- `python-app.yml` → replace the `-f cockpit/requirements.txt` block with root requirements

**CI:** **delete** `static.yml` (publishes the whole repo to Pages — source leak); **delete** `pylint.yml` (`--exit-zero` is theatre); **rewrite** `python-publish.yml` to build-only + attach `dist/` to the GitHub Release (**do not publish to PyPI** — this is an app, not a library).

**DoD:** `python -m build` produces sdist + wheel; clean install from the lock on 3.12; `scripts/check_dependencies.py` exits 0 in CI; no `3.10`/`3.11` reference survives outside CHANGELOG.

---

### W2 — Dead code excision (strict order: fix consumers → delete producer → test)

| Delete | Rationale |
| --- | --- |
| `api/` (4 `.ts`), `verify-generate.js`, `Cargo.toml`, `src-tauri/` (keep `icons/source-icon.png`), `tauri.conf.json` | Zero Python importers; no `package.json` exists |
| `.pre-commit-config.yaml` gofmt hook | 0 `.go` files |
| `orchestration/registry.py`, `orchestration/discovery.py` | Nothing imports them |
| 3 requirements shims | See W1 |


**`orchestration/orchestrator.py` — DO NOT DELETE.** *Verified:* imported by `tests/test_c1_contracts.py:944`, `tests/test_c1a_capability_discovery.py:143,226`, `tests/test_call_centre_proving_workflow.py:30`, `scripts/smoke.py:89`. Defer to Phase 2 with a capability-routing replacement.

**Retiring the C5 adapter generation.** *Verified:* `engines/base_adapter.py` + `engines/adapters.py` are imported **only** by `control_plane/control_seam.py:49,606` and have **zero tests**; C4 (`engines/registry.py`, `engines/contracts.py`) is tracked and covered by `test_c4_engines.py`. So: **keep C4, harvest C5, delete C5.**

Port four ideas C4:

1. `FrozenMapping` immutable request → `engines/contracts.py`
2. `ComputationEvidence` → optional field on `EngineResult` (parameters, inputs_used, assumptions)
3. Per-engine `baseline_payload()` declared as data — directly serves "simulated vs live visibly distinct"
4. `EngineResult.refusal(code, msg)` alongside `success()/failure()`

Then: delete `engines/base_adapter.py` + `engines/adapters.py` (~1,572 LOC); rewrite `control_seam.py` to use a `Port` protocol in `control_plane/ports.py` + a ~40-line `C4AdapterBridge` in `engines/registry.py`. **Add the 3 seam tests that don't exist** (happy arc, gate freeze, RTA failure → `DEAD_LETTER`).

**DoD:** full suite green; `grep -r "base_adapter\|engines\.adapters" .` → nothing; LOC ↓ ~1,600.

---

### W3 — Engine hygiene (before HTTP; HTTP maps these codes)

`control_plane/engine.py`:

- `_audit` (L116–152): stop `list_records(limit=10000)` per call — cache `prev_hash` on the instance, or `SELECT ... ORDER BY rowid DESC LIMIT 1`
- `submit` (L184–608): extract the 8 duplicated ~20-line error blocks into one `_fail(workflow, exc, stage)`. **Do not change emitted `error_code` values** — tests assert on them.
- Replace `if "unauthorized" in str(e).lower()` with typed `EngineFailure(code, message)` in `engines/contracts.py` (registry already smuggles codes via `RuntimeError(f"[{code}] {msg}")`)
- Convert the 27 `except Exception: pass` to structured logging at `result_status="degraded"` — silent swallowing violates "evidence survives review"

**DoD:** new test `tests/test_engine_audit_perf.py` asserts `_audit` issues ≤1 query (via `sqlite3.set_trace_callback`); `grep -c "except Exception" control_plane/engine.py` ≤ 12.

---

### W4 — Service spine (feature-first: router → service → repository)

Create `server/` as a new top-level package (**no `src/` migration** — it would invalidate `pythonpath`, all 26 test modules, and 3 Dockerfiles for zero gain):

```
server/app.py                 # create_app() factory, lifespan, middleware, error handlers
server/config.py              # Settings(BaseSettings), env prefix HELIX_, fail-fast
server/errors.py              # AppError hierarchy + handlers
server/deps.py                # Engine / Store / ConnectorGateway providers (lifespan-scoped)
server/sse.py                 # the ONLY async module in the repo
server/features/health/{router,schemas}.py
server/features/workflows/{router,service,repository,schemas}.py
server/features/approvals/{router,service,repository,schemas}.py
server/features/stream/router.py     # SSE
server/features/console/router.py    # HTMX pages + static
server/templates/  server/static/
```

- **Reuse, don't replace:** `deps.get_engine()` builds `Engine(...)`, calls `engines.registry.register_all(engine)`, holds it for process lifetime, `close()` on shutdown. `Engine.submit/approve/execute/to_task_result` are the service layer's **only** entry points.
- **Config:** reuse env names the Dockerfile already sets (`HELIX_ENV`, `HELIX_DB_PATH`, `HELIX_AUDIT_DB_PATH`, `HELIX_SAMPLE_DATA_MODE`, `OLLAMA_HOST`). `profile ∈ {local,pilot,production}`; **`production` refuses to start** unless external gates are satisfiable. No default for any secret.
- **Errors:** `AppError(code, http_status, retryable)` → `ValidationAppError(422)`, `NotFound(404)`, `AuthorizationRefused(403)`, `GateAwaitingApproval(409, payload=decision.to_dict())`, `UpstreamUnavailable(503)`. Substring matching banned at this boundary.
- **Request-ID middleware:** read/generate `X-Request-ID` → bind to `CorrelationContext.correlation_id` → emit in every log line and response header. Enforces "context survives every boundary" in one place.
- **SSE:** `asyncio.Queue` per `correlation_id`, fed by sync workers via `anyio.to_thread.run_sync(engine.submit, ...)`. **Do not async-ify `Engine`** (445 sync tests).
- **Endpoints:** `GET /healthz`, `GET /readyz`, `POST /api/workflows`, `GET /api/workflows/{id}`, `POST /api/workflows/{id}/approve`, `GET /api/stream/{id}`, `GET /`.
- **Compose:** `EXPOSE 8000`; `CMD uvicorn server.app:create_app --factory`. Keep the Streamlit cockpit as a second service for one release.

**DoD:** boots on 3.12; `/healthz` 200, `/readyz` 200 on a fresh `/data`; integration test `tests/test_server_spine.py` covers submit → SSE `awaiting_approval` → approve → `closed`; `docker compose up` reaches healthy.

---

### W5 — Connector write path

Today `request_write` returns a constant `executed=False` ("read_only_first_version_disallows_writes"). A super-app cannot be built on a constant.

**Create:**

- `connectors/ports.py` — `ConnectorPort`: `read(op, ctx)`, `plan_write(intent, ctx) -> WritePlan`, `apply_write(plan_id, approval_ref, ctx) -> WriteReceipt`
- `connectors/policy.py` — capability → risk tier → `governance.evaluate_gate(...)`; writes return `AWAITING_APPROVAL`, never a silent boolean
- `connectors/gateway.py` — the only surface services call. Order: tenant scope (`_assert_scope`) → `data_mode` check (a `sample` context may never address a live target) → idempotency (receipt table keyed by `IdempotencyKey`) → dry-run default → outbox
- `connectors/local/{docs,tasks,chat}.py` — **first-party domain connectors implementing the same port.** Chat/docs/tasks then become connectors with uniform provenance; third-party providers slot in later with no app-code change.

**Modify `connectors/contracts.py`:** add `WriteIntent`, `WritePlan(diff, risk_tier, requires_approval, idempotency_key, compensating_op?)`, `WriteReceipt(external_id, written_at, source_of_truth, reversibility)`. Keep `Provenance` mandatory on reads **and** receipts. Keep `SUPPORTED_MODES=("fake",)`; `live` valid only with an explicit per-provider activation record — unactivated providers return `requires_approval`.

**DoD — `tests/test_connectors_write_path.py`:** (1) cross-tenant write raises before any I/O; (2) sample→live write denied; (3) unactivated provider → `requires_approval`, nothing executed; (4) replayed idempotency key returns the first receipt, no second side effect; (5) every read carries non-null `Provenance` with `correlation_id`.

---

### W6 — Replace the `call_agent` regex

`app/command_center/agents/base_agent.py:248` parses free text with `r'call_agent\((["\'])([A-Z_]+)\1,\s*(["\'])(.*?)\3\)'`, depth-capped 5; `qwen3:8b` hardcoded in 9 classes; `localhost:11434` hardcoded at L133.

**Create** `app/command_center/agents/dispatch.py` + `contracts/toolcall.py`:

- `ToolCallEnvelope(content, tool_calls)` / `ToolCall(call_id, tool, args, idempotency_key?)`; request via Ollama `format=<JSON Schema>`; validate with pydantic
- **No regex fallback.** Parse failure → `DEAD_LETTER` with `reason_code="unparsable_tool_call"` + an SSE review-queue event. This is "fail closed" applied to the model.
- `TOOLS` registry: name, pydantic arg model, owning_role, capability, `side_effect ∈ {none, local_write, external_write}`. Initial tools: `call_agent`, `submit_task`, `request_approval`, `read_document`
- **Governance stays in the loop:** the dispatcher does not execute. It builds a `TaskRequest` (tenant/client/correlation/causation inherited) → `Engine.submit` → gate freezes at `awaiting_approval` → UI resumes via `Engine.approve`. Identical path to a human request.
- Depth/cycle: `hop` counter + visited-agent set on the envelope; >5 hops → typed refusal. Peer replies appended as `ToolResult` records, **not** string-substituted into the parent's text.
- `model`/`host` from `server/config.py`; delete the 9 hardcoded literals.
- Migration: keep `contracts/adapter.py::parse_legacy_calls` behind `HELIX_LEGACY_CALL_PARSING=1` (default off).

**DoD — 4 tests + 1 golden transcript:** structured round-trip; malformed output → review queue with **zero** tool executions (assert no `Engine.submit`); depth-6 → typed refusal; `submit_task` freezes at `awaiting_approval` and completes only after `approve`.

---

### W7 — Testing & CI baseline (the Phase 2 gate)

- **One** `.github/workflows/ci.yml`, Python **3.12 only**: ruff (real exit code) → `mypy server connectors control_plane` → `pytest -m "not smoke" --cov=server --cov=connectors --cov-fail-under=80` → `check_dependencies.py` → `python -m build`
- **No repo-wide coverage target** — 47 K LOC against 445 tests makes a global percentage a gaming target. Gate **new** code (`server/`, `connectors/`) at 80%; `control_plane/` advisory.
- `pytest.ini` → `[tool.pytest.ini_options]`: add `timeout = 120`, `--durations=20`; CI runs `-m "not smoke"`, a nightly job runs smoke against Compose + Ollama.

**Phase 2 gate:** 0 failures on the full non-smoke suite (count ≥ W0 baseline) · ruff clean · mypy clean on `server/`+`connectors/` · `python -m build` green · `docker compose up` → `/readyz` 200.

---

## Appendix A — Deliberate non-goals in Phase 1

| Deferred | Why |
| --- | --- |
| `src/` layout migration | Invalidates `pythonpath`, 26 test modules, 3 Dockerfiles — zero functional gain |
| Async-ifying `Engine` | 445 sync tests are the only safety net; async confined to `server/sse.py` |
| Resolving the role authority conflict by picking a number | ops_gm 20 000 vs 500 is a **policy** decision needing a signed record. Phase 1 does: YAML as single source → `sync_role_metadata.py` generates `ORGANIZATION_CATALOG` → drift test fails on divergence. **Numbers unchanged.** |
| Encryption at rest | Not constitutionally required; fights keyless self-hosted start. Logged in `docs/SECURITY-DEBT.md` |
| "Fixing" the production gate | It **must** fail closed. Add a test asserting the service refuses writes on `production` so nobody "fixes" it later |
| PyPI publication | It's an app, not a library; ship the wheel as a GitHub Release artifact |


## Appendix B — Top risks

1. **W0 is the biggest risk, not the code.** Half the newest system is uncommitted. Do not start W1 until `git status` is clean.
2. **No LICENSE** — blocks all commercialization. Resolve before Phase 4.
3. **Convenience penalty** (PCV: self-hosting is *less* convenient). Installer must be <10 minutes or the ICP won't convert.
4. **Solo-dev throughput.** Phase 2 (10–14 wks) is the real crunch; consider cutting Docs editing to a block-based MVP.
5. **Local LLM quality.** `qwen3:8b` regex-tool-calling is being replaced by structured output — verify JSON-schema adherence on the target hardware early, or the whole agent rail stalls.
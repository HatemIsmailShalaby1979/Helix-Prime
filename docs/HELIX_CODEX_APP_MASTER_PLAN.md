# Helix Codex App — Master Plan & Build Plan

**Prepared:** 2026-09-13 · **For:** Hatem Shalaby (solo builder) · **Repo:** `E:\Helix-Prime`

---

## 0. What this document is, and how to read it

This is the architecture and phased build plan for the Helix Codex App. Its companion is
`docs/HELIX_CODEX_APP_AGENT_PROMPTS.md`, which turns this plan into a sequence of prompts a coding
agent runs one commit at a time.

| # | Document | Path | Purpose |
| --- | --- | --- | --- |
| 1 | Master plan | `docs/HELIX_CODEX_APP_MASTER_PLAN.md` | The reasoning: architecture, data model, phases, risks. This document. |
| 2 | Coding-agent prompt pack | `docs/HELIX_CODEX_APP_AGENT_PROMPTS.md` | The doing: sequenced, engineered prompts, one commit each. |


**Authority.** These two documents are subordinate to `00_CONSTITUTION.md` (authority) and
`docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture + commercial record). The parent `AGENTS.md`
stays the build ledger for the ops core; the app keeps its own ledger at `helix_codex_app/agents.md`
once P0 creates it. Neither ledger duplicates the other, and both point at the same constitution.

**How to use it.** Read §1–§2 for what is being built and what was decided. Read §3–§11 for the
design. Read §12–§13 for the order of work and what "done" means. Read §14 before agreeing to any
scope addition.

---

## 1. What we are building

**Helix Codex App** is an all-in-one productivity and unified collaboration platform — the honest
comparison is ByteDance's Lark — with a governed operations engine and an owner/manager cockpit built
in as a privileged section rather than bolted on.

Every employee, manager, and owner uses it daily: punch in/out, chat, on-calls, documents, KB and
SOPs, tasks, calendar, notifications, video rooms, and email. Managers and owners additionally see an
**Operations** section and a **Cockpit** section that no ordinary employee can reach. Every account
carries a governed metacognitive memory that improves with use, under human approval — the same
promise Helix Prime makes, made per user.

**Positioning (from the existing blueprint, unchanged):** *the operations OS for teams that can't put
their data in someone else's cloud.* Chat, docs, tasks, and AI agents that actually execute — behind
an audit trail, on your own hardware, for a fraction of the subscription stack it replaces.

**Honest gap statement.** Today the repo has the governance core, six engines, nine agent roles, a
release gate system, and a Streamlit cockpit that is localhost-only with no authentication. It has no
user accounts, no messaging, no documents, no mobile surface, and no product shell. This plan builds
the product layer on top of the core that already exists. It does not rebuild the core.

---

## 2. Decisions locked (2026-09-13)

| # | Decision | Consequence |
| --- | --- | --- |
| 1 | Deliverables go in `E:\Helix-Prime\docs` | No new folders. Two files only. |
| 2 | Frontend = server-rendered PWA (FastAPI + HTMX + Alpine) | No JS build step, no SPA, no npm. One language. |
| 3 | Deployment = hybrid (self-host now, cloud-portable later) | One process, one SQLite file, one compose file. |
| 4 | v1 = collab core **plus** ops section and cockpit section | v1 is the whole daily-use product, minus mail and video. |
| 5 | `username@domain` where **one domain = one tenant** | Domain maps to `tenant_id`. Login is domain-scoped. |
| 6 | **Per-user memory is a truly isolated store** | One governed memory store + metacognition engine per account, plus one org store. See §6. |
| 7 | Mail and video deferred to v2 | v1 has no MTA, no WebRTC. Both are specialist problems. |
| 8 | Package name = `helix_codex_app/` | Console script `helix-app`. `helix-api` stays untouched. |


---

## 3. Where it lives, and how it comes apart later

### 3.1 One process, two factories

A new top-level package `helix_codex_app/` inside `E:\Helix-Prime`, composed into a single FastAPI
process. Not an extension of `server/`, and not a second service.

- `server/app.py::create_app()` — unchanged. The ops-only surface. The existing 621-test suite keeps
passing against it.
- `helix_codex_app/app.py::create_app()` — **the product factory.** Builds the shared lifespan through
the existing `server/deps.py` provider, mounts the app routers under `/app/*`, serves the PWA shell,
and mounts the authenticated cockpit section. It includes the existing ops routers unchanged.
- New entry point `helix-app = helix_codex_app.cli:main`. In the hybrid deploy you run **only**
`helix-app`.

Why not a second service: two processes means two ports, two auth systems, and cross-service calls —
exactly the operational burden a solo builder cannot afford to carry.

### 3.2 The extraction seam

`helix_codex_app/integration/` is the **only** package that imports parent internals
(`control_plane`, `engines`, `security`, `memory`, `metacognition`, `capabilities`, `connectors`).

To move the app into its own repo later: replace the five bridge modules, drop the parent packages,
move `tests/helix_codex_app/` into the new repo, change the `pyproject` package list. Nothing else
changes. A module that imports a parent package directly is a defect, and the prompt pack says so.

### 3.3 Subtree

```
helix_codex_app/
  __init__.py
  app.py              # create_app() product factory — mounts shell, routers, ops passthrough
  cli.py              # helix-app entrypoint (uvicorn)
  config.py           # AppSettings(BaseSettings), env prefix HELIX_APP_, secrets fail closed
  deps.py             # AccountStore, CollabStore, EngineProvider, memory + metacognition providers
  db.py               # sqlite3 factory + schema bootstrap + record_node()
  errors.py           # AppError hierarchy: AuthError, PermissionDenied, LimitExceeded
  security/
    accounts.py       # Domain, OrgUnit, Account dataclasses + repository
    passwords.py      # hashlib.scrypt hash/verify (stdlib — no new dependency)
    sessions.py       # opaque session id, token hashing, CSRF, cookie issue/verify
    permissions.py    # app permission catalog + role→permission map
    limits.py         # per-account capability + quota gating
    guard.py          # FastAPI deps: current_account, require_permission, require_capability, require_csrf
  integration/        # THE ONLY parent-importing package
    engine_bridge.py  policy_bridge.py  memory_bridge.py  metacognition_bridge.py
    cockpit_bridge.py  packs.py
  modules/
    identity/  messaging/  docs/  tasks/  calendar/  notifications/
    attendance/  memory/  ops/  cockpit/  admin/  lowcode/
    (rooms/ and mail/ are v2 stubs, created empty in P0)
  templates/          # base.html, shell/, auth/, partials/
  static/             # css/, js/, vendor/, manifest.webmanifest, sw.js, offline.html, icons/
  migrations/         # APP-LOCAL alembic env
  alembic.ini         # script_location = helix_codex_app/migrations
  governance.md  agents.md  repomap.md
```

Every module follows the proven `router → service → repository` shape from
`server/features/workflows/`.

### 3.4 Packaging changes required

| File | Change |
| --- | --- |
| `pyproject.toml` `[tool.hatch.build.targets.wheel].packages` | add `"helix_codex_app"` |
| `pyproject.toml` `[tool.hatch.build.targets.sdist].include` | add `"/helix_codex_app"` (must mirror the wheel list) |
| `pyproject.toml` `[project.scripts]` | add `helix-app = "helix_codex_app.cli:main"` |
| `pyproject.toml` `[project.optional-dependencies].web` | add `python-multipart` (FastAPI needs it for HTMX form posts — the only new runtime dependency) |


**Why app-local migrations:** `scripts/check_migration_drift.py` compares a store-built schema against
`alembic upgrade head` and would break if app tables joined the root migration head. A separate
`helix_codex_app/alembic.ini` + `helix_codex_app/migrations/` keeps the parent gate green and travels
with the app on extraction.

---

## 4. Domain decomposition

All app routes sit under `/app`. Ops passthrough routes keep their existing paths.

| Module | Responsibility | Key tables | Route surface | Reuses |
| --- | --- | --- | --- | --- |
| **identity** | Domains, org units, accounts, sessions | `domains`, `org_units`, `accounts`, `sessions`, `login_events` | `POST /app/auth/login`·`logout`·`password`, `GET /app/auth/me`, `GET/POST /app/admin/users`, `PATCH /app/admin/users/{id}`, `POST /app/admin/users/{id}/capabilities`·`/limits`, `GET/POST /app/admin/domains`·`/org-units` | `security/identity.py`, `security/policy.py`, `organization/role_catalog.py` (read-only) |
| **messaging** | Conversations, threads, presence | `conversations`, `conversation_members`, `messages` | `GET/POST /app/api/conversations`, `GET/POST /app/api/conversations/{id}/messages`, `POST .../read`, `GET .../stream` (SSE) | `server/sse.py::EventBus`, `server/models/node.py` |
| **docs & KB/SOP** | Block documents, versions, KB index | `documents`, `doc_blocks`, `document_versions` | `GET /app/docs`, `GET /app/docs/{id}`, `GET /app/kb`, `POST /app/api/documents`, `PUT /app/api/documents/{id}/blocks/{block_id}`, `POST .../versions/{n}/restore` | `NodeKind.DOCUMENT/BLOCK`, governed memory |
| **tasks** | Board, assignment, comments | `tasks`, `task_comments` | `GET /app/tasks`, `GET /app/tasks/{id}`, `POST /app/api/tasks`, `PUT /app/api/tasks/{id}`, `POST .../status`, `POST .../comments` | `NodeKind.TASK`, engine bridge |
| **calendar & on-calls** | Events, attendees, on-call rosters | `events`, `event_attendees`, `oncall_shifts` | `GET /app/calendar`, `GET/POST /app/api/events`, `PUT /app/api/events/{id}`, `POST .../respond`, `GET /app/api/oncall` | `engines/wfm` (shifts, rosters) |
| **notifications** | In-app centre + SSE fan-out | `notifications` | `GET /app/api/notifications`, `POST .../{id}/read`, `GET /app/notifications/stream` | `server/sse.py`, bus keyed by `account_id` |
| **attendance / punch** | Punch in/out, attendance summary | `punch_records` | `GET /app/attendance`, `POST /app/api/attendance/punch`, `GET .../records`·`/summary` | `engines/rta`, `engines/wfm` |
| **memory** | Per-user governed memory + proposals + promotions | `memory_stores`, `proposals`, `proposal_reviews`, `promotions` | `GET /app/memory`, `GET /app/memory/proposals`, `POST /app/api/memory/proposals`, `POST .../{id}/evaluate`·`/approve`·`/reject`·`/rollback`, `POST /app/api/memory/promotions`, `GET /app/memory/ledger/verify` | `memory/governed_memory.py`, `metacognition/improvement.py` |
| **ops / AI** | Engine overview + governed workflow submission | parent `workflows`, `audit_events` | `GET /app/ops`, `GET /app/ops/{engine}`, `POST /app/api/ops/workflows`, `GET .../{id}`, `POST .../{id}/approve`, `GET .../stream/{id}` | `control_plane.engine.Engine`, `server/features/workflows`, `server/features/approvals` |
| **cockpit** | Manager/owner-only operations cockpit | engine + pack data | `GET /app/cockpit`, `/owner`, `/coach`, `/parent`, `/control-plane`, `GET /app/api/cockpit/summary` | `cockpit_bridge` → `compute_*` functions |
| **low-code** | Sections + capability-pack registry | `sections`, `capability_packs` | `GET /app/api/sections`, `POST /app/admin/sections`, `GET /app/api/packs`, `POST /app/admin/packs/reload` | `capabilities/*/register.py`, `organization/capability_registry.py` |
| **admin** | Domains, org, users, limits, evidence export | identity tables | `GET /app/admin`, `GET /app/admin/evidence/export` | `scripts/export_evidence_pack.py` |


---

## 5. Identity, auth, tenancy, and per-account limits

### 5.1 The role problem, solved without touching the catalog

The nine roles in `organization/role-catalog.yaml` are GM and executive roles. Every employee will not
have one, and the file must never be edited. So:

- Read the catalog through `organization/role_catalog.py` for the nine privileged roles.
- Add an **app-local role layer** in `helix_codex_app/security/permissions.py`:
`owner`, `manager`, `employee`, `contractor`, `external`.
- Bridge: `policy_bridge.py` maps an `AccountContext` to a `security.identity.Identity`
(`actor=account_id`, `actor_type="human"`, `tenant_id`, `client_id`, `role_id`). An app role with no
catalog equivalent gets `role_id=None` — and `security/policy.py::authorize` then denies by
construction. That is the fail-closed guarantee: **an employee cannot reach ops because the policy
engine has never heard of them.**

### 5.2 Tables

```sql
domains(domain_id PK, name UNIQUE, tenant_id NOT NULL, client_id, status, created_at)
org_units(unit_id PK, domain_id, parent_unit_id, name, kind, path, created_at)
accounts(account_id PK, domain_id, username, username_normalized, display_name, email,
         password_hash, password_algo, password_params, role_id, org_unit_id, actor_type,
         status, must_change_password, failed_attempts, locked_until,
         created_at, updated_at, last_login_at, UNIQUE(domain_id, username_normalized))
sessions(session_id PK, account_id, token_hash UNIQUE, csrf_token, issued_at, expires_at,
         last_seen_at, ip, user_agent, revoked_at)
account_capabilities(account_id, capability_key, enabled, granted_by, granted_at,
                     PRIMARY KEY(account_id, capability_key))
account_limits(account_id, limit_key, limit_value, window, PRIMARY KEY(account_id, limit_key))
login_events(event_id PK, account_id, domain_id, outcome, reason, ip, user_agent, created_at)
```

### 5.3 Passwords

`hashlib.scrypt`, 16-byte per-account salt, `n=2**14, r=8, p=1`, stored as
`scrypt$n$r$p$salt_b64$hash_b64`; verified with `hmac.compare_digest`. Stdlib only — no new
dependency, no hand-rolled crypto. `password_algo` and `password_params` are stored so the cost
parameters can be raised later without invalidating existing hashes.

### 5.4 Sessions and CSRF

- Login verifies the password, then issues a random 256-bit opaque session id
(`secrets.token_urlsafe(32)`). Only its SHA-256 hash is stored in `sessions.token_hash`. The cookie
`helix_session` is `HttpOnly`, `Secure`, `SameSite=Lax`.
- Every request: `guard.current_account` hashes the cookie, looks up the session, rejects if missing,
expired, revoked, or locked → 401.
- CSRF: double-submit. `sessions.csrf_token` is rendered into the shell as `<meta name="csrf-token">`;
`guard.require_csrf` (on every non-GET `/app/*`) compares the `X-CSRF-Token` header with
`compare_digest` → 403 on mismatch.
- No JWTs. One lookup table is simpler to reason about and revoke, and revocation is a hard
requirement for "manager disables an account".
- Sliding expiry: 12h idle, 30d absolute, refreshed in `last_seen_at`.

### 5.5 Permission matrix

| Permission | owner | manager | employee | contractor | external | catalog GM roles |
| --- | --- | --- | --- | --- | --- | --- |
| `chat.use` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `docs.read` | ✅ | ✅ | ✅ | ✅ | scoped | ✅ |
| `docs.write` | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| `tasks.use` | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| `calendar.use` | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| `attendance.punch` | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| `notifications.use` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `memory.propose` | ✅ | ✅ | ✅ | — | — | ✅ |
| `memory.review` | ✅ | ✅ | — | — | — | ✅ (SOD-checked) |
| `ops.view` | ✅ | ✅ | — | — | — | ✅ |
| **`cockpit.view`** | ✅ | ✅ | — | — | — | ✅ |
| `admin.users` | ✅ | scoped | — | — | — | — |
| `packs.manage` | ✅ | — | — | — | — | — |


### 5.6 Enforcing the manager/owner-only cockpit — three layers

1. **Router boundary.** The cockpit router is included with
`dependencies=[Depends(require_permission("cockpit.view"))]`. Not a template `{% if %}` — a 403 at
the boundary.
2. **Service check.** `cockpit/service.py` re-checks the account's permissions before calling the
bridge, so a future route added without the dependency still fails closed.
3. **Data check.** `policy_bridge` calls `security.policy.authorize` for any engine action, using the
account's own `tenant_id`/`client_id` — cross-tenant access denied at the single policy seam.

Tests: `test_cockpit_requires_permission` (employee session → 403 on every cockpit route) and
`test_cockpit_cross_tenant_denied`.

### 5.7 Limits

`require_capability("docs.write")` guards mutating routes. `limits.check_and_consume(account, key, 1)`
runs before a write and raises `LimitExceeded` (429) when a quota is spent. Defaults are seeded at
account creation from the role — employee `storage_mb=500`, `messages_per_day=2000`; manager higher;
owner unlimited. Gating is server-side only; the UI hiding a control is cosmetic.

### 5.8 Built new vs reused

| Built new | Reused untouched |
| --- | --- |
| `helix_codex_app/security/*` (accounts, passwords, sessions, permissions, limits, guard) | `security/identity.py` |
| `accounts`, `sessions`, `account_capabilities`, `account_limits`, `login_events` | `security/policy.py::authorize` |
| CSRF, cookie sessions, login lockout, Account→Identity mapping | `organization/role_catalog.py` (read-only), `server/auth.py` (left alone for headless ops) |


---

## 6. Per-user metacognitive memory — the isolated design

This is decision #6, and it is the most distinctive promise of the product. Each account gets its own
physically separate governed memory store and its own metacognition engine, plus one org-wide store
that managers and owners curate. Nothing is shared silently.

### 6.1 Store layout

```
helix_codex_app/memory_stores/<tenant_id>/<account_id>/governed_memory.jsonl
helix_codex_app/memory_stores/<tenant_id>/<account_id>/audit.jsonl
helix_codex_app/memory_stores/<tenant_id>/_org/governed_memory.jsonl
helix_codex_app/memory_stores/<tenant_id>/_org/audit.jsonl
```

`memory_bridge.py` resolves a store from the **authenticated** `account_id` — never from a request
parameter. A request cannot name another account's store, because no endpoint accepts a foreign
`account_id` for memory reads. That is isolation by construction, not by filter.

### 6.2 The promise, stated honestly

Every user gets: their own memory that accrues from their own work; the ability to *propose* an
improvement; a review that shows the evidence rather than a yes/no; human approval before anything
applies; versioning; and rollback. What they do **not** get is a private place to hide — managers see
the org store and promotion queue, and every record still carries tenant, classification, provenance,
correlation, and evidence references. This distinction goes in `governance.md` in plain words, because
over-claiming here would break the constitution's first principle.

### 6.3 Write path

`helix_codex_app/db.py::record_node(...)` is the single writer. Every mutating service call appends a
`Node` with the full envelope — `tenant_id` non-null, `correlation_id`, `classification`, `nature`,
`provenance{source, data_mode, retrieved_at}`, `created_by` — and, for notable actions, a
`memory_bridge.record(...)` line into that account's store. This mirrors `server/models/store.py` and
the blueprint's "no separate AI side-channel" rule.

### 6.4 Proposal → review → approve → version → rollback

`MetacognitionEngine` is reused verbatim, one instance per store. New seams in
`metacognition_bridge.py`: `propose()`, `evaluate()`, `approve()`, `reject()`, `rollback()`,
`generate_evidence_report()`, `verify_chain()`.

The proposal screen at `/app/memory/proposals/{id}` renders the `EvaluationResult` — baseline rate,
candidate rate, delta, `n_historical`, `n_simulated` — not just a verdict, plus risk assessment,
evidence, the rollback plan, and the audit-chain status. Approve, reject, and rollback are HTMX form
posts. Separation of duties is enforced by the engine and surfaced as a typed `AuthorizationRefused`.

**Two parent defects to fix first**, each with its own test, before the UI is wired: tighten
`_APPROVABLE` to `(EVALUATED,)` only, and make the `correct`/`supersede`/`delete` flags survive
reload. These are small, contained changes in the parent.

### 6.5 Promotion into org memory

The elegant part, and what makes per-user isolation useful instead of siloed: a proposal that proves
out in one account's store can be **promoted**.

`POST /app/api/memory/promotions` creates a proposal in the org store that references the source
account's evidence. A promotion requires a **second, independent approver** — a manager or owner. The
user's own approval is never sufficient. Provenance records `promoted_from_account_id`,
`source_proposal_id`, and `evidence_refs`. Rolling back a promotion removes the org rule and records
the reversal in both stores.

### 6.6 Cost, stated plainly

N accounts means N stores. This buys real isolation and real simplicity per user, and it costs an
index. So: a `memory_stores` table for enumeration, a `GET /app/memory/ledger/verify` endpoint that
verifies one store's hash chain, and a bounded sweep that verifies a rotating batch rather than all
stores at once. Flagged as a known operational cost, not hidden.

---

## 7. Data model

Two layers. A **governance layer** (`nodes`) where every action lands as one row, kind-discriminated —
this is the unified memory and audit feed. And a **working layer** of ordinary relational tables per
module, which are easy to query and index. Every working-table write goes through `record_node()`, so
the invariant cannot be bypassed.

```sql
nodes(node_id PK, tenant_id NOT NULL, client_id, domain_id, correlation_id NOT NULL, causation_id,
      classification NOT NULL, nature NOT NULL, kind NOT NULL, created_by NOT NULL, created_at NOT NULL,
      body TEXT, provenance_source, provenance_data_mode, provenance_retrieved_at,
      parent_node_id, thread_id)

conversations(conversation_id PK, tenant_id, domain_id, kind, title, classification, created_by,
              created_at, correlation_id)
conversation_members(conversation_id, account_id, member_role, joined_at, last_read_at,
                     PRIMARY KEY(conversation_id, account_id))
messages(message_id PK, conversation_id, sender_account_id, body, classification, created_at,
         edited_at, deleted_at, node_id)

documents(document_id PK, tenant_id, domain_id, title, doc_type, owner_account_id, classification,
          status, current_version, created_at, updated_at)
doc_blocks(block_id PK, document_id, ordinal, block_type, content, updated_by, updated_at)
document_versions(version_id PK, document_id, version_no, snapshot, created_by, created_at)

tasks(task_id PK, tenant_id, domain_id, title, description, status, priority, assignee_account_id,
      creator_account_id, due_at, completed_at, parent_task_id, created_at, updated_at)
task_comments(comment_id PK, task_id, account_id, body, created_at)

events(event_id PK, tenant_id, domain_id, title, kind, starts_at, ends_at, all_day, location, room_id,
       creator_account_id, recurrence_rule, created_at, updated_at)
event_attendees(event_id, account_id, response, PRIMARY KEY(event_id, account_id))
oncall_shifts(shift_id PK, tenant_id, domain_id, roster, starts_at, ends_at, primary_account_id,
              backup_account_id)

notifications(notification_id PK, account_id, kind, title, body, link, read_at, created_at, correlation_id)
punch_records(punch_id PK, account_id, domain_id, tenant_id, punch_type, punched_at, source, geo, note,
              device_id, correlation_id)
files(file_id PK, tenant_id, domain_id, owner_account_id, filename, content_type, size_bytes, sha256,
      storage_path, classification, created_at)

memory_stores(store_id PK, tenant_id, account_id NULL, kind, path, record_count, chain_head, updated_at)
proposals(proposal_id PK, store_id, tenant_id, domain_id, kind, target, state, version, created_by,
          role_id, correlation_id, classification, data_mode, created_at, updated_at)
proposal_reviews(review_id PK, proposal_id, reviewer_account_id, reviewer_role, decision, reason, created_at)
promotions(promotion_id PK, source_store_id, org_store_id, source_proposal_id, state, approved_by,
           created_at, updated_at)

sections(section_id PK, domain_id, key, label, icon, route, position, required_capability, enabled,
         source_pack)
capability_packs(pack_id PK, name, version, domain, production_readiness, min_core_version,
                 manifest_path, enabled, registered_at)
```

**Invariants enforced by `record_node()` and proven by tests:** `tenant_id` non-null;
`correlation_id` non-empty; `classification` one of the four levels; `nature` explicit;
`provenance.data_mode` present; `created_by` is an account id or an agent role id.

**Database:** SQLite at `helix_codex_app/app.db`, separate from `control_plane/workflow.db`,
`security/audit.db`, and `nodes.db`. Raw `sqlite3`, matching the parent style — no ORM. Postgres later
through a thin connection abstraction; keep the new SQL ANSI-ish and avoid SQLite-only syntax.

---

## 8. UI/UX design system

### 8.1 Tokens — `helix_codex_app/static/css/tokens.css`

```css
:root {
  --accent: #e94560;            /* Helix red — brand, primary actions */
  --accent-strong: #c73350;
  --ink: #14161c;  --ink-2: #3b3f4a;  --muted: #7a7f8c;
  --surface: #ffffff; --surface-2: #f6f7f9; --surface-3: #eceef2;
  --border: #dfe2e8; --danger: #c0392b; --success: #1e8e5a; --warn: #b7791f;
  --radius-sm: 6px; --radius-md: 10px; --radius-lg: 16px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-5: 24px; --space-6: 32px;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --text-xs: 12px; --text-sm: 13px; --text-md: 15px; --text-lg: 18px; --text-xl: 22px; --text-2xl: 28px;
  --tap-min: 44px;              /* mobile touch target floor */
  --nav-h: 56px;
}
```

System font stack — zero download, offline-safe, instant first paint. Mobile-first: base styles target
≤480px, and `@media (min-width: 768px)` adds the desktop rail.

### 8.2 Components

| Component | File | Notes |
| --- | --- | --- |
| App shell | `templates/base.html` | head (manifest, tokens, vendored HTMX/Alpine), content slot, bottom nav, toast host |
| Bottom nav (mobile) | `partials/nav_bottom.html` | Home · Chat · Tasks · Calendar · More |
| Rail (desktop) | `partials/nav_rail.html` | all sections, grouped |
| Auth screens | `templates/auth/login.html` | domain + username + password |
| Chat list / thread | `partials/chat_list.html`, `partials/chat_thread.html` | SSE append, optimistic send |
| Doc editor | `partials/doc_editor.html` | block-based `contenteditable`, debounced autosave via HTMX |
| Task board | `partials/task_board.html` | open / doing / done columns, Alpine drag |
| Calendar | `partials/calendar.html` | month view, agenda list on mobile |
| Notification centre | `partials/notifications.html` | badge + list, SSE-fed |
| Punch clock | `partials/punch.html` | large tap target, in/out, today's total |
| Cockpit card | `partials/cockpit_card.html` | metric card + data-mode badge |
| Memory proposal | `partials/proposal_card.html` | state chip, evidence table, approve / reject / rollback |
| Data-mode badge | `partials/data_mode_badge.html` | always visible on simulated data — a constitution requirement |


**Elegance rule:** one accent colour, one radius scale, no gradients, no icon font (an inline SVG
sprite), no CSS framework, no build step. The test for a new component is whether a non-technical user
can complete the task one-handed on a phone.

### 8.3 PWA

- `static/manifest.webmanifest` — `name`, `short_name`, `start_url=/app`, `display=standalone`,
`theme_color=#e94560`, 192/512 icons plus a maskable 512.
- `static/sw.js` — precache the shell, tokens, app.css, vendored HTMX/Alpine, and icons;
network-first for `/app/api/*`, cache-first for static; `offline.html` fallback; versioned cache
name; skip waiting on update.
- `static/js/pwa.js` — register the service worker, capture `beforeinstallprompt`, render an install
banner.
- **Vendor HTMX and Alpine locally** in `static/vendor/` instead of the CDN references currently in
`server/templates/index.html`. This is required for offline use and for data sovereignty — a
self-hosted box must not depend on a third-party CDN.
- Offline behaviour in v1: the shell and last-viewed pages are readable. Queued offline mutations are
**out of v1** — background sync is genuinely hard and is a v2 item.

---

## 9. Cockpit integration

### 9.1 Recommendation: reimplement the cockpit section in HTMX; keep Streamlit for one release

| Approach | Verdict | Why |
| --- | --- | --- |
| iframe the Streamlit app | Stopgap only | Separate port, no session propagation, no mobile, no auth — it would violate "manager/owner-only, enforced server-side" |
| Rewrite Streamlit wholesale | Reject for v1 | Weeks of work for no new capability |
| **HTMX using the existing `compute_*` functions** | **Recommended** | The pack already separates compute from render, so the work is presentation only |


The evidence is concrete: `capabilities/sports_academy/cockpit_views/owner_dashboard.py` exposes
`compute_owner_dashboard(ctx, connectors, as_of) -> dict` and a thin `render_owner_dashboard(st, ...)`.
`cockpit_bridge.py` calls the `compute_*` functions and hands the dicts to Jinja templates.
`coach_dashboard.py` and `parent_portal.py` follow the same shape; if any view lacks a `compute_*`
entry point, extract one first — a small, contained refactor.

### 9.2 Migration path

1. **P6a (v1):** read-only HTMX cockpit cards for the highest-value views — the owner dashboard (five
KPIs, attendance, at-risk), the approval queue (reusing `server/features/approvals`), and engine
status. Gated behind `cockpit.view`.
2. **P6b:** port the coach and parent dashboards, then add the control-plane panel.
3. **Later:** retire the Streamlit app (`helix-cockpit`) one release after parity, as the blueprint
already anticipated.

**Auth:** the cockpit section is served by the app process and uses the account session. It calls the
engine **in-process** through `engine_bridge`, which sidesteps the shared-`HELIX_API_TOKEN` problem
entirely. `policy_bridge` builds an `Identity` from the `AccountContext` and calls `authorize()`
before any engine call. The existing `/api/*` bearer routes stay untouched for headless clients.

---

## 10. Low-code extensibility

`capabilities/<pack>/capability.yaml` is formalized per blueprint §2.3 and loaded by
`modules/lowcode/pack_loader.py`:

```
schema_version: "1.0"
id: sports_academy
name: Sports Academy Operations
version: 1.0.0
domain: sports_academy
min_core_version: "0.9.0"
read_only_start: true
synthetic_data_only: true
production_readiness: NOT_ESTABLISHED
ontology: [Athlete, Session, Checkin, FacilitySlot, Program]
sections:
  - { key: owner, label: Owner, route: /app/cockpit/owner, required_capability: cockpit.view }
  - { key: coach, label: Coach, route: /app/cockpit/coach, required_capability: cockpit.view }
roles: []  workflows: []  policies: []  connector_contracts: []
data_classifications: [internal, client_confidential]
metrics: []  failure_modes: []
```

The `CapabilityPack` Protocol (`manifest`, `ontology()`, `roles()`, `workflows()`, `metrics()`,
`runtime()`) with `load_pack`, `register_pack`, `validate_pack` matches blueprint §2.3 exactly.

**Five invariants the loader must enforce, each with a test:**

1. A pack role cannot widen an existing core role's `max_financial_amount`.
2. A pack cannot register a capability already owned by another pack.
3. `production_readiness != ESTABLISHED` ⇒ live `data_mode` is refused.
4. Manifests are semver-versioned; a `min_core_version` above the runtime refuses to load.
5. Separation of duties: a pack role cannot review its own actions.

Sections are data in the `sections` table, registered from `capability.yaml` on load, and rendered by
the shell. A third party adds a section without touching core code, and the `required_capability` field
means an unpermitted account never sees it — and gets a 403 if they hit the route directly.

---

## 11. Governance artifacts to create in the new project

All three live in `helix_codex_app/`. They are **subordinate** to `00_CONSTITUTION.md` (authority) and
`docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture). They reference parent rules rather than
restating them, so there is one source of truth and no drift.

### `helix_codex_app/governance.md`

The app's operating rules and decision log.
**Sections:** (1) a one-line subordination statement naming the authority chain; (2) scope — what the
app is and is not; (3) inherited invariants *by reference* — tenant/classification/provenance/
correlation survive every boundary, fail closed, simulated vs live stay visibly distinct,
self-improvement stays a proposal until evaluated, reviewed, approved, versioned, rollback-able;
(4) app-specific rules — session and CSRF handling, `cockpit.view` enforced in three places, the
app-local role layer never edits `role-catalog.yaml`, `integration/` is the only parent-importing
package, the honest statement of what per-user memory isolation does and does not mean;
(5) an append-only decision log where each entry reveals its assumption.
**Update rule:** append a dated entry whenever an invariant, permission, or the integration seam
changes, and cite a test for every invariant change.

### `helix_codex_app/agents.md`

The build ledger for the app, mirroring the parent `AGENTS.md` format exactly.
**Sections:** project context; non-negotiables (inherit parent §0 by reference, plus app-specific:
never edit parent catalog files, never bypass `record_node`, never add a JS build step, never commit
a memory store); a step ledger with P0–P8 checkboxes and a status table carrying the current step, the
baseline test count, and the last commit; the git protocol (`feat(app):`, `test(app):`, `fix(app):`,
`docs:`; never `git add -A`; never commit `.db`, `__pycache__`, `.venv*`, or `memory_stores/`).
**Update rule:** update immediately after each step; never restart a completed step; record the exact
test count after every phase.

### `helix_codex_app/repomap.md`

Where everything lives and where to add new things.
**Sections:** folder-by-folder purpose; the integration seam explained; route groups; the table list;
"How to add a module", "How to add a section", "How to add a capability pack"; the extraction
checklist (replace `integration/`, drop parent imports, move migrations and tests).
**Update rule:** update whenever a top-level folder, route group, table, or the seam changes.

**Relationship to the parent:** the parent `AGENTS.md` stays the ledger for the ops core;
`helix_codex_app/agents.md` is the ledger for the app. Neither duplicates the other's step list, and
both point at the same constitution.

---

## 12. Phased build plan

Each phase is independently shippable, ends with tests at or above the baseline, ruff clean on new
files, `agents.md` updated, and one commit.

| Phase | Goal | Deliverables | Exit gate |
| --- | --- | --- | --- |
| **P0 — Scaffold + governance** | A booting app shell with its own governance files | `helix_codex_app/` skeleton; `app.py::create_app()`; `cli.py` (`helix-app`); `config.py`; `db.py`; `/app/healthz`; `base.html` + tokens + vendored HTMX/Alpine; **`governance.md`, `agents.md`, `repomap.md`**; pyproject wiring | `helix-app` boots; `/app/healthz` returns 200; pytest ≥ baseline; ruff clean; commit `feat(app): scaffold codex app` |
| **P1 — Identity, auth, shell, PWA** | Real accounts, domain login, installable shell | identity module; `passwords.py`, `sessions.py`, `permissions.py`, `limits.py`, `guard.py`; login/logout/me; admin users/domains/org-units; manifest + service worker + offline page + install prompt | login/logout/CSRF/lockout tests green; employee → cockpit 403; PWA installs on a phone; tenant isolation test |
| **P2 — Messaging + notifications + SSE** | Daily chat with live delivery | messaging + notifications modules; SSE per conversation and per account; mention → notification | two accounts exchange messages; SSE p95 < 500 ms; read receipts; SSE reconnect test |
| **P3 — Docs/KB + tasks** | Documents and work tracking | docs + tasks modules; block editor; versions; task board; comments | create/edit/version/restore a doc; task lifecycle and assignment; every write emits a `nodes` row |
| **P4 — Calendar + on-calls + attendance** | Scheduling and time | calendar + attendance modules; event CRUD and RSVP; on-call roster; punch in/out | one open punch record per account enforced; attendance summary correct; event range query correct |
| **P5 — Per-user metacognitive memory** | The promise, made visible | memory module; per-account stores; proposal lifecycle UI with evidence; promotion flow; ledger verify | proposal → evaluate → approve (SOD denial proven) → rollback end to end; chain verifies; parent defects fixed with tests |
| **P6 — Ops section + cockpit** | Manager/owner operations | ops module (bridge + governed submit/approve); cockpit module (owner/coach/parent cards, approval queue) | employee 403 on every cockpit route; owner sees five KPIs; ops submit → awaiting approval → approve → closed |
| **P7 — Hardening + packaging + release** | First client shippable | app release gates; evidence export; backup/restore; compose profile running `helix-app`; installer path; offline verified | app gate emits a `CONTROLLED_PILOT_READY`-class outcome; fresh `docker compose up` → `/app/healthz` 200; 10-minute install verified |
| **P8 — Deferred** | Mail, video, sync, billing | `mail/`, `rooms/`, multi-node sync on `cloud/interfaces.py`, billing | Not in v1 |


**Sequencing principle:** P1 before P2, because every other module needs accounts. P5 before P6,
because the cockpit surfaces proposals. The cockpit is never built before auth exists — that is exactly
how the Streamlit app ended up unauthenticated.

---

## 13. Test and release strategy

**"Done" per phase:** tests at or above the baseline (currently 621), zero failures; ruff clean on new
files; `agents.md` updated; one commit. This mirrors the parent `AGENTS.md` non-negotiable exactly.

**Where app tests live:** `tests/helix_codex_app/`. Zero config change — the root `testpaths=["tests"]`
already covers it — and it reuses `tests/conftest.py` (whose SQLite handle-release fixture matters on
Windows) and `tests/support/sqlite_harness.py`. On extraction, move the folder into the new repo and
add it to `testpaths`.

**Required test families:** auth boundary (401 / 403 / CSRF / lockout / revocation); the permission
matrix per role; tenant isolation per module; memory-store isolation per account; `record_node`
invariants; proposal lifecycle including SOD denial and rollback; promotion requiring a second
approver; app migration drift; PWA assets present and valid; cockpit 403 for employees.

**Release gates:** add app gates as functions in `release/gate.py` using the same `(ok, detail)`
contract, and add a profile to `release/release-profiles.yaml` named `app_pilot` requiring
`repository_state`, `configuration_validation`, `startup_readiness`, `data_isolation`,
`audit_integrity`, plus new `app_auth_boundary`, `app_session_fail_closed`, `app_tenant_isolation`,
`app_memory_store_isolation`, `app_migration_drift`, `app_pwa_assets`. Preserve the fail-closed design:
the bare `PRODUCTION` label stays unreachable, and the app gate can only emit `CONTROLLED_PILOT_READY`
or `PRODUCTION_CANDIDATE`.

**Definition of shippable v1, first client:** a coach on a phone installs the PWA, logs in as
`username@academy`, punches in, chats with the team, reads an SOP, completes a task, and sees the
calendar. A manager does all of that plus reviews a governed improvement proposal with its evidence. The
owner sees the read-only cockpit — five KPIs, attendance, at-risk athletes, the approval queue. Every
action appears in the audit trail and the evidence export. It runs from one `docker compose up` on the
client's own hardware. An employee account receives 403 on every cockpit route.

---

## 14. Risks and non-goals

| # | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| 1 | Scope explosion — twelve modules is a lot for one person | High | Phases are independently shippable; P1–P4 alone is a usable product |
| 2 | Auth security — hand-rolled sessions fail often | High | Stdlib scrypt, opaque cookie, hashed tokens, CSRF; explicit tests for fixation, CSRF, lockout, revocation; no JWT, no crypto written by hand |
| 3 | Tenant isolation — one missing `tenant_id` filter leaks data | High | `record_node()` makes `tenant_id` non-null; every query takes `tenant_id`; `authorize()` at the bridge; a cross-tenant test per module |
| 4 | Per-user memory store sprawl | Medium | A `memory_stores` index, per-store verify endpoint, bounded rotating sweep; the cost is stated in `governance.md` rather than hidden |
| 5 | Realtime infrastructure — SSE is single-process | Medium | Fine for self-host (one node). `server/sse.py::EventBus` stays the seam; a broker is a managed-cloud problem, deferred |
| 6 | Video rooms — WebRTC is genuinely hard | High | Do not write WebRTC. Embed a self-hostable Jitsi room by URL, or defer. Post-v1 |
| 7 | Mail deliverability — self-hosted mail gets blacklisted | High | Never run an MTA. Integrate the client's own IMAP/SMTP or an API later. Post-v1 |
| 8 | Mobile app stores — review, signing, cost | Medium | The PWA avoids stores entirely; this is why the frontend decision is PWA |
| 9 | Ops burden — more services means more to run | Medium | One process, one database, one compose file. No Redis, no broker, no separate frontend host |
| 10 | Maintenance — two codebases drifting | Medium | The `integration/` seam is the only coupling; app-local migrations and tests; extraction path documented in `repomap.md` |
| 11 | Collaborative editing — CRDT is a rabbit hole | Medium | Block-based single-writer with optimistic concurrency in v1; CRDT deferred |
| 12 | Cockpit parity gap — Streamlit has several pages | Low | Read-only HTMX cards first; retire Streamlit one release after parity |


**v1 will not do:** collaborative CRDT editing; WebSockets; native mobile apps; video or WebRTC; mail
delivery; SSO/SAML; billing and payments; multi-node sync; multi-region; encryption at rest; Postgres;
app-store distribution; an offline mutation queue; a public third-party API.

---

## 15. The two deliverables, in detail

### 15.1 `docs/HELIX_CODEX_APP_MASTER_PLAN.md`

This document, adapted for the repo: sections 1–14 above, plus a short "how to read this alongside
`AGENTS.md`" note. Written in plain, human prose — no filler, no marketing adjectives, no "delve",
no rule-of-three padding. Every claim traceable to a file in the repo or to a test.

### 15.2 `docs/HELIX_CODEX_APP_AGENT_PROMPTS.md`

The operational file your coding agent runs. Structure:

1. **How to use this file** — run prompts in order, one commit each; prepend the PREAMBLE to every
prompt; after each prompt verify, commit, and start the next in a fresh turn; if verification fails,
re-send the same prompt with the error output appended and do not move on.
2. **The PREAMBLE** (pasted before every prompt), containing: environment facts (Python 3.12 venv, the
exact pytest command, the ruff command, the Windows SQLite teardown gotcha); reusable primitives
(`security/identity.py`, `security/policy.py`, `memory/governed_memory.py`,
`metacognition/improvement.py`, `control_plane/engine.py`, `server/sse.py`,
`capabilities/sports_academy/cockpit_views/*`); the non-negotiables (fail closed and raise, never
regress the suite, never edit the parent catalog files, never bypass `record_node`, no comments
except module docstrings, no new dependencies without saying so, minimal diff); the commit style;
and the required end-of-run report.
3. **The check-in / check-out protocol** — before starting a prompt the agent reads `agents.md`,
`governance.md`, and `repomap.md`, and states the current step and the test baseline; after
finishing it updates all three files, records the exact test count, makes one commit, and reports
files changed, test result, ruff result, and commit SHA in under fifteen lines.
4. **~35–40 numbered prompts**, grouped by phase (P0 → P7), each in the proven shape:
`GOAL` / `CONTEXT` / `CHANGES (file-scoped)` / `CONSTRAINTS` / `VERIFY` / `COMMIT`. Every prompt is
scoped to one commit-sized change and names the exact files to touch.
5. **A writing rule block**, repeated in the preamble, so every file the agent writes — code
docstrings, `governance.md`, `agents.md`, `repomap.md`, UI copy — is written in plain human English:
no generic AI phrasing, no "seamlessly", no "leverage", no "in today's fast-paced world", no
em-dash chains, no bulleted list where a sentence reads better. Short sentences. Concrete nouns.
6. **A failure playbook** — what to do when a test fails, when the baseline regresses, when a
dependency is missing, and when a prompt's premise turns out to be wrong (stop, report, do not
improvise a redesign).

---

## 16. Critical files to create or modify

| Action | Path |
| --- | --- |
| Create (new package) | `helix_codex_app/**` — the subtree in §3.3 |
| Create (governance) | `helix_codex_app/governance.md`, `helix_codex_app/agents.md`, `helix_codex_app/repomap.md` |
| Modify (packaging) | `pyproject.toml` — add `helix_codex_app` to wheel packages and sdist include, add the `helix-app` script, add `python-multipart` to the `web` extra |
| Create (deploy) | `infra/docker/docker-compose.app.yml` with the `helix-app` command |
| Modify (release) | `release/gate.py`, `release/release-profiles.yaml` — app gates and the `app_pilot` profile |
| Modify (parent defect fix) | `metacognition/improvement.py` — tighten `_APPROVABLE`, preserve correction flags; each with a test |
| Read-only (reuse) | `server/deps.py`, `server/sse.py`, `security/identity.py`, `security/policy.py`, `memory/governed_memory.py`, `control_plane/engine.py`, `capabilities/sports_academy/cockpit_views/*` |
| Never edit | `organization/role-catalog.yaml`, `control_plane/governance.py`, `organization/capability-registry.yaml` and mirrors |


---

## 17. Writing and tone rules for every file this project creates

These apply to code docstrings, all three governance files, UI copy, and both deliverables.

- Plain human English. Short sentences. Concrete nouns. Say the thing.
- No generic AI phrasing: no "seamlessly", "leverage", "robust", "cutting-edge", "in today's
fast-paced world", "it's not just X, it's Y", "let's dive in".
- No em-dash chains and no rule-of-three padding. One idea per sentence.
- Prefer a sentence over a bulleted list when the sentence reads better.
- Every claim is traceable to a file in the repo or to a test that was run and observed. If it cannot
be verified, say so plainly.
- Brand rules from `marketing/README.md` still hold: tagline *An AI Organization. Not a tool. Not a
chatbot. Not a dashboard.*, accent `#e94560`, author credit Hatem Shalaby, and no invented proof
ledgers.

---

## 18. Open items to confirm during P0 (not blockers)

1. Confirm `coach_dashboard.py` and `parent_portal.py` each expose a `compute_*` entry point; if not,
extract one before P6.
2. Confirm the exact venv to use for the app (`helix_codex_app` follows the parent's `.venv-py312`).
3. Decide the first client's domain name (e.g. `scoach.academy`) before P1 seeds accounts.
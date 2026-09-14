# AGENTS.md: Helix Codex App Build Ledger

> **Purpose:** any agent (or human) can pick up exactly where the last one stopped. Read this file
> top-to-bottom, then work only on the next incomplete step. Update it immediately after completing
> each step.

## Project context (read first)

The Helix Codex App is the daily-use product layer on top of the governed Helix Codex OS core. It is
an all-in-one collaboration platform: chat, documents, tasks, calendar, attendance, notifications, and
a manager-only cockpit, with a governed per-user memory under human approval. It lives in its own
top-level package `helix_codex_app/`, reuses the parent core through the `integration/` seam, and
never edits parent internals.

Its plan lives at `docs/HELIX_CODEX_APP_MASTER_PLAN.md`. The step-by-step prompts live at
`docs/HELIX_CODEX_APP_AGENT_PROMPTS.md`.

**Authority chain:** `00_CONSTITUTION.md` (authority) →
`docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (architecture) → `helix_codex_app/governance.md` (app rules)
→ this file and `helix_codex_app/repomap.md` (ledger and map). The constitution wins on any conflict.

## Non-negotiables

The parent's non-negotiables apply as well. They are stated once in `E:\Helix-Prime\AGENTS.md`
section 0 and are not repeated here. The plain summary: the restaurant pack is the reference pattern;
data runs in `simulated_realistic` mode with read-only connectors; every governed-memory record
carries tenant_id, client_id, provenance, evidence_refs, and classification; no code comments except
module docstrings; every step ends with tests at or above baseline, ruff clean, this file updated, and
a commit.

App-specific rules:

1. Never edit `organization/role-catalog.yaml`, `control_plane/governance.py` (ORGANIZATION_CATALOG),
   `organization/capability-registry.yaml`, or their mirrors. App roles live in
   `helix_codex_app/security/permissions.py`.
2. Never bypass `helix_codex_app/db.py::record_node()`. Every mutating write goes through it with the
   full envelope: tenant_id, correlation_id, classification, nature, provenance, created_by.
3. Never add a JavaScript build step. HTMX and Alpine.js are vendored files in
   `helix_codex_app/static/vendor/`.
4. Never commit `helix_codex_app/app.db`, `memory_stores/`, `__pycache__`, `.venv*`, or `evidence/`.
5. `helix_codex_app/integration/` is the only package allowed to import parent internals
   (`control_plane`, `engines`, `security`, `memory`, `metacognition`, `capabilities`, `connectors`).
   Any other module under `helix_codex_app/` that does is a defect.
6. `server/` stays untouched. `create_app()` there keeps serving the ops-only surface.

## Status

| Field | Value |
|---|---|
| Current step | P3 — Documents, KB, tasks (next prompt P3.2) |
| Baseline test count | 954 |
| Last commit | `02700f8` feat(app): add block documents and inline editor |
| Completed steps | P0.1–P0.4, P1.1–P1.7, P2.1–P2.4, P3.1 |

## Step ledger

### P0 — Scaffold and governance (status: COMPLETE)

- [x] P0.1 Scaffold the package and boot the shell (Prompt 1) — commit `822402e`
- [x] P0.2 The mobile-first PWA shell (Prompt 2) — commit `3887079`
- [x] P0.3 governance.md (Prompt 3) — commit `0b3765c`
- [x] P0.4 agents.md and repomap.md (Prompt 4) — commit `50bba63`, 621 passed

### P1 — Identity, auth, org, limits (status: COMPLETE)

- [x] P1.1 App database and the single writer (Prompt 5) — commit `781b0b3`, 629 passed
- [x] P1.2 Accounts, domains, and passwords (Prompt 6) — commit `f8cccb5`, 663 passed
- [x] P1.3 Sessions, cookies, and CSRF (Prompt 7) — commit `5631717`,
      `helix_codex_app/security/sessions.py`
      (SessionStore: opaque `secrets.token_urlsafe(32)` token, only its SHA-256 hash + a separate
      CSRF token stored; `verify()` joins the account and rejects missing/revoked/expired/
      idle-expired/locked-account sessions; `touch`, `revoke`, `revoke_all_for`;
      `set_session_cookie` HttpOnly + SameSite=Lax + path=/ + Secure behind `cookie_secure`)
      and `helix_codex_app/security/guard.py` (`current_account` reads the `helix_session` cookie
      and raises `AuthError`; `require_csrf` compares the X-CSRF-Token header with the session
      token via `compare_digest`; `require_scope`, `require_capability`; `require_permission` is a
      **deny-by-default placeholder** until the P1.4 catalog lands). `app.py` wires the guard once
      at the router boundary: `app_router` (read `/app/*`) behind `current_account`, `csrf_router`
      (mutating `/app/*`) behind `current_account` + `require_csrf`; `/`, `/app/healthz`, and the
      static mount stay public; `render()` injects the session CSRF token; lifespan bootstraps the
      app schema; an `AppError` handler maps `AuthError`→401 and `PermissionDenied`→403.
      Tests: `tests/helix_codex_app/test_sessions_and_guard.py` (23) cover all six VERIFY cases,
      revocation/expiry/idle, locked accounts, token-hash-only storage, cookie attributes, tenant
      scope, capabilities, and deny-by-default permissions. Full suite 686 passed / 0 failed;
      ruff check + format clean.
- [x] P1.4 The permission catalog and role mapping (Prompt 8) — commit `c244872`,
      `helix_codex_app/security/permissions.py`
      (PERMISSION_MATRIX mirroring master plan §5.5 across owner/manager/employee/contractor/
      external plus a `catalog` column with True/"scoped"/False values; `permissions_for`,
      `has_permission`; `PRIVILEGED_CATALOG_ROLE_IDS` = the nine ids read from
      `organization/role_catalog.py` at import time; unknown keys and unknown roles deny) and
      `helix_codex_app/integration/policy_bridge.py`
      (`to_identity`: `security.identity.Identity` with actor=account_id, actor_type="human",
      tenant_id/client_id from the account, role_id set ONLY for the nine catalog roles — every
      app role maps to None and the policy engine denies by construction; `authorize_engine_action`:
      calls `security.policy.authorize` with the account's own tenant/client and raises
      `PermissionDenied` on any deny, never defaulting to allow). `guard.require_permission` now
      enforces the catalog instead of the P1.3 deny-placeholder. Tests:
      `tests/helix_codex_app/test_permissions_and_policy_bridge.py` (88) cover every (role,
      permission) pair across the 5 app roles (65) and all 9 catalog roles (117 assertions), the
      nine-ids constant, deny-by-default for unknown roles/keys, scoped grants, to_identity role
      passthrough/None, employee-denied and catalog-owner-passed engine authorization, policy-deny
      raising, invalid-request denial, and no scope widening through the bridge. Full suite
      774 passed / 0 failed (686 + 88); ruff check + format clean.
- [x] P1.5 Login, logout, and the auth screens (Prompt 9) — commit `39e58ff`,
      `helix_codex_app/modules/identity/service.py`
      (LoginService: `login(domain_name, username, password, ip, user_agent)` resolves
      username@domain and turns a verified password into a session; wrong domain, unknown
      account, wrong password, a non-active account, and locked all share ONE user-facing
      message while the machine code (`no_such_domain` / `no_such_account` / `bad_password` /
      `unusable_account` / `locked` / `success`) goes only to the `login_events` audit row —
      no enumeration through the page; `MAX_FAILED_ATTEMPTS=5` consecutive failures lock the
      account for `LOCK_MINUTES=15` (the lock itself is recorded), an expired lock unlocks on
      the next attempt, success resets the counter and stamps `last_login_at`; every outcome
      writes a row, including a nonexistent domain/account with NULL ids; `logout(session_id)`
      revokes; `change_password(account, old, new)` verifies old, enforces
      `MIN_PASSWORD_LENGTH=8`, clears `must_change_password`) and `helix_codex_app/modules/
      identity/router.py` (identity_router under `/app/auth`; public GET/POST `/login`,
      guarded GET `/me`, POST `/logout`, GET/POST `/password` behind `current_account` +
      `require_csrf`; answers are redirects, full pages, or HTMX fragments — never JSON-only;
      success redirects to `/app/` or, when `must_change_password`, to `/app/auth/password`).
      `helix_codex_app/templating.py` (one shared `render()` injecting the session CSRF token
      and settings — the P1.3 render logic leaves `app.py`), `helix_codex_app/templates/auth/
      {login,password,me}.html` (standalone, no shell inheritance), `templates/shell/home.html`
      (greets by display name, shows the role, HTMX sign-out form carrying X-CSRF-Token),
      `security/accounts.py` `set_password()`, auth CSS in `app.css`. `app.py` includes
      `identity_router` and passes the account to the home page. Tests:
      `tests/helix_codex_app/test_login_and_auth.py` (20) cover the cookie attributes, the
      no-enumeration page message, the 5-fail→lock→locked-cannot-login progression, expired-
      lock re-login, logout + CSRF rejection, the must-change password redirect and change
      flow, short-password and wrong-current rejection, the /me fragment, the home greeting,
      and the unknown-domain audit rows. `TestClient` is driven with `follow_redirects=False`
      so the 303 login redirects are asserted directly. Full suite 794 passed / 0 failed
      (774 + 20); ruff check + format clean.
- [x] P1.6 Admin: users, domains, org units, capabilities, limits (Prompt 10) — commit
      `67d6961`,
      `helix_codex_app/modules/admin/service.py`
      (AdminService: `create_user`, `update_user`, `set_user_status`, `grant_capability`,
      `revoke_capability`, `set_limit`, `create_domain`, `create_org_unit`, `list_users`,
      plus `list_domains`, `list_org_units`, `get_managed_user`, `capabilities_of`,
      `limits_of`. Owner acts on the whole domain; a manager acts only inside their own
      org unit (`_require_managed_account`, `_require_create_scope`); a manager with no
      org unit manages nothing. An account can never change its own role or status, move
      its own org unit, or grant/revoke its own capability. `set_user_status` to a
      non-active value also revokes the target's live sessions. Domain creation is owner
      only. Every write calls `record_node()` with tenant/client/domain ids, a fresh
      `admin-*` correlation id, classification internal, nature historical_event, kind
      admin, provenance `helix_codex_app.admin` / `app_runtime`.) and
      `helix_codex_app/modules/admin/router.py`
      (admin_router under `/app/admin`, included with `require_permission("admin.users")`
      at the router boundary; GET `` (landing), `/users`, `/users/{id}`, `/domains`,
      `/org-units`; POST `/users`, `/users/{id}/capabilities`, `/users/{id}/limits`,
      `/domains`, `/org-units`; PATCH `/users/{id}` — every mutating route also carries
      `require_csrf`; answers are 303 redirects with a flash query param; form errors
      redirect back with `?error=`). Templates `templates/admin/{index,users,user_detail,
      domains,org_units}.html` — cards on mobile, tables at ≥768px. **Permission semantics
      change (the prompt's VERIFY case):** `permissions_for`/`has_permission` gained an
      optional `conn`; when passed, enabled `account_capabilities` rows are unioned into
      the role-matrix result, so an admin grant takes effect at the very next request.
      `guard.require_permission` and `AdminService._require_admin` pass the conn.
      `templating.render` gained an optional `status_code`. `security/accounts.py` gained
      a read-only `get_org_unit`. Nav partials show Admin for owner/manager. Tests:
      `tests/helix_codex_app/test_admin.py` (26) cover owner create + audit envelope,
      UI create → login round-trip, manager org-unit scoping (create/list/update/status/
      capability/limit/domain), manager-cannot-manage-owner, unit-less manager manages
      nothing, employee 403 on every admin route (GET + mutating), the admin screens
      render, grant→`has_permission` immediate + revoke, grant→route-access immediate,
      self-grant/self-role/self-status/self-org-unit-move denied, status-change revokes
      sessions + audits, unknown status/role rejection, set-limit-below-usage no-crash
      (LimitExceeded on next consume, per check_and_consume), duplicate domain, weak
      password, cross-domain NotFound, CSRF-required on admin POST. **One existing test
      was updated deliberately:** `test_sessions_and_guard.py::test_permission_gate_denies_
      until_catalog` now probes omar (no capability rows) instead of amira (who holds a
      granted `test.punch` capability) — under the new grant semantics amira's permission
      gate legitimately passes; the deny-by-default intent is unchanged. App-dir suite
      191 passed / 0 failed; ruff check + format clean. **Test-secret-scan lesson:** the
      admin tests first used a long invented password literal in test code, which tripped the
      parent `release/security_gate.py` secrets scan (7 findings) and failed the 5
      release-gate tests; the literals now use the allowlisted `your-password`, and the
      gate tests pass. The committed feature SHA is `67d6961` (amended once for this fix).
- [x] P1.7 Close out P1: isolation, PWA assets, ledger (Prompt 11) — commit `bc24190`,
      `tests/helix_codex_app/test_tenant_isolation.py`
      (7 tests: account/domain/org-unit reads stay scoped; sessions of tenant B never
      verify inside tenant A; the same username in two tenants is two accounts;
      record_node's tenant column is enforced NOT NULL and every tenant-carrying table
      declares tenant_id; login resolves the domain first, so a tenant A username cannot
      be logged into through tenant B's domain name),
      `tests/helix_codex_app/test_cockpit_exclusion.py`
      (5 tests: no cockpit route is mounted before P6; an employee, a contractor, an
      external, and an unknown-role session all get 403 through a probe route registered
      behind `require_permission("cockpit.view")` on the real app_router — the P1.3
      probe pattern; the owner passes; the module is re-pointed at the live cockpit
      routes in P6),
      `tests/helix_codex_app/test_pwa_assets.py`
      (4 tests: the manifest parses, lists exactly three icons including a maskable one,
      start_url=/app, standalone display; every icon file exists and is non-empty; sw.js
      defines a versioned CACHE_NAME; offline.html exists),
      `tests/helix_codex_app/test_app_migration_drift.py`
      (3 tests: the drift check passes at head; the check CAN FAIL (a table added to the
      db.py side is reported); normalisation ignores indentation, not tokens. Named
      `test_app_migration_drift.py`, not `test_migration_drift.py`, to avoid the pytest
      module-name collision with the parent `tests/test_migration_drift.py` — both dirs
      have no `__init__.py`). No isolation bug was found: every scoped read resolved its
      domain first, exactly as the P1.2 repository promised. Full suite **839 passed,
      0 failed** (794 baseline + 26 admin + 19 close-out); ruff check + format clean on
      helix_codex_app/ and tests/helix_codex_app/.

### P2 — Messaging, notifications, SSE (status: COMPLETE)

- [x] P2.1 Conversations and messages (Prompt 12) — commit `48c75ab`,
      `helix_codex_app/modules/messaging/repository.py`
      (slots for conversations, members, and messages; `get_conversation(
      conversation_id, account_id)` raises `NotFoundError` with ONE message
      shape for missing conversation, non-member, and foreign tenant, so a
      caller cannot learn which part was wrong; `list_conversations` joins
      membership in the SQL, so a conversation the caller is not in is absent
      rather than filtered; `find_direct_conversation` treats the pair as
      unordered; `list_messages(conversation_id, before, limit)` pages
      newest-first by `created_at < before`, cursor-safe, bounded 1..200),
      `helix_codex_app/modules/messaging/service.py`
      (MessagingService: `create_direct(a, b)` same-tenant-only and
      idempotent (second call returns the existing conversation, either
      argument order); `create_group(creator, name, members)` dedupes,
      caps at MAX_GROUP_MEMBERS=64, cross-tenant member denied; `send_message`
      validates body (non-blank, ≤8000), then writes ONE message row and ONE
      governed node through `record_node()` with kind `message`,
      classification `internal`, nature `user_claim`, provenance
      `helix_codex_app.messaging` / `app_runtime`, and the conversation's OWN
      correlation_id — a thread reads as one story in the audit trail;
      `mark_read` stamps only the caller's membership row and never creates
      membership; `remove_member` returns False when the row was already
      gone), `helix_codex_app/modules/messaging/schemas.py`
      (pydantic request/response models: `MessageOut`, `ConversationOut`,
      `MessagePage` with the `next_before` cursor, `SendMessageRequest`,
      `CreateGroupRequest`, `CreateDirectRequest`, `MarkReadRequest`,
      `AddMemberRequest` — the wire shape is pinned before any client
      exists). No router yet: P2.1 is the service layer only (Prompt 12 has
      no route). Tables already existed in `db.py::_init_schema` and the
      app alembic baseline since P1.1; this step changed no DDL and no
      migration. Tests: `tests/helix_codex_app/test_messaging.py` (18) cover
      non-member read/post/member-management all raising `NotFoundError`,
      create_direct idempotence in both argument orders, one-pair-per-direct
      (not one channel), exactly one `nodes` row per message with the full
      envelope and the conversation correlation_id, pagination + newest-first
      ordering + member scoping, group shape/dedupe, cross-tenant membership
      denied at service level AND invisible even with a foreign id, same-
      tenant-different-domain still allowed, remove/read-receipt semantics,
      empty/oversized message rejection, blank group name, direct-with-self,
      no edit/delete write paths (columns exist, methods do not), schema
      round-trip, and list ordering by latest activity with message_count and
      preview. Full suite **857 passed, 0 failed** (839 baseline + 18);
      ruff check + format clean on the new paths; app-dir suite 228 passed.
- [x] P2.2 The chat UI and the SSE stream (Prompt 13) — commit `7989e33`,
      `helix_codex_app/modules/messaging/router.py`
      (messaging_router under `/app`, guard + per-route membership; GET `/chat` and
      `/chat/{id}` screens; GET+POST `/api/conversations`, GET+POST
      `/api/conversations/{id}/messages`, POST `/api/conversations/{id}/read`,
      GET `/api/conversations/{id}/stream`. Every mutating route reads a JSON body OR
      an HTMX urlencoded form through `_payload()` — repeated `member_ids` fields
      collapse into a list — and carries `require_csrf`. HTMX answers are fragments:
      create re-renders `chat_list.html` (root `id="chat-section"`, swapped via
      `hx-target` outerHTML) INSIDE the connection try so it never reads a closed
      DB, send re-renders the single `message_row.html` bubble; JSON answers are
      `ConversationOut`/`MessageOut`/`MessagePage`. The SSE route checks membership
      first and refuses non-members with a **403** (`PermissionDenied` — carried as
      code `permission_denied`) instead of 404, so no observer learns a foreign
      conversation exists; every other route's non-member answer stays 404.
      `conversation_event_stream` is split out for direct driving in tests:
      subscribe → 15 s heartbeat keep-alive comment → `encode` each bus frame →
      unsubscribe in `finally`.), `helix_codex_app/integration/sse_bridge.py`
      (the app's only window onto the parent bus: `server.sse.EventBus` wrapped as
      `subscribe`/`unsubscribe`/`publish`/`publish_sync`/`subscriber_count` + `encode`
      — one bus per process, a broker is a documented v2 decision),
      `helix_codex_app/static/js/sse.js` (EventSource client with exponential backoff
      `[1s,2s,4s,8s]`, re-dispatches frames as `helix:chat-message` CustomEvents,
      `HelixChat.append` dedupes on `data-message-id` and skips while a
      `[data-pending]` bubble exists so an SSE arrival never fights the optimistic
      HTMX write, `ChatComposer.optimistic/reconcile`, auto-boots on
      `[data-messages][data-conversation-id]`), `helix_codex_app/static/sw.js`
      (the `/app/api/` cache handler now skips paths ending in `/stream` — a live
      stream must never be cached), templates `chat/{list,thread}.html` and partials
      `{chat_list,chat_thread,composer,message_row}.html` (mobile-first composer
      pinned above the keyboard with `bottom: var(--nav-h)`, desktop `0`), chat CSS
      in `app.css`, Chat nav entries enabled in both nav partials, `app.py` mounts
      `messaging_router` between admin and app. Tests:
      `tests/helix_codex_app/test_messaging_routes.py` (20) cover screens (list
      renders peers + titles, thread oldest-first with `data-messages`/
      `data-conversation-id`/`data-self`, non-member 404, unauth 401), conversations
      (direct idempotent 201, unknown account 404, create-hx fragment returns the
      `chat-section` list, group 201 with membership, no-CSRF 403), messages (JSON
      201 + one `nodes` row + matching `messages.node_id`, send-hx fragment = one
      `chat-bubble--me`, non-member 404, cursor `next_before` paging, mark_read
      stamps only the caller, non-member list 404), and the stream (member-open is
      pinned at the handler level — `conversation_stream` returns a StreamingResponse
      with event-stream media type + the three headers, because a test client cannot
      drain an infinite body; the earlier `client.stream` variant HUNG TestClient and
      was replaced; non-member 403 parametrized over a same-tenant outsider and an
      other-tenant account; the generator emits a posted frame and returns to zero
      subscribers on disconnect). **Measured round-trip:** send-message POST median
      117 ms (max 169 ms), thread screen GET 58 ms on this machine — under the 1 s
      local target. App-dir suite 248 passed / 0 failed; full suite
      **877 passed, 0 failed** (857 baseline + 20); ruff check + format clean on
      helix_codex_app/ and tests/helix_codex_app/.
- [x] P2.3 Notifications (Prompt 14) — commit `bd3e406`,
      `helix_codex_app/modules/notifications/repository.py`
      (per-account `notifications` rows with sender/recipient/kind/body/link/
      read_at; `create`, `list_for(account_id)` newest-first, `unread_count`,
      `mark_read` idempotent — `UPDATE ... WHERE read_at IS NULL` — and
      `mark_all_read` returning the number newly stamped), `schemas.py`
      (`NotificationOut`: id, kind, body_preview, link, created_at, read_at),
      `service.py` (NotificationService: `create` writes the row, records a
      governed node (`kind="notification"`, `nature="system_event"`,
      classification internal, provenance `helix_codex_app.notifications` /
      `app_runtime`, `created_by` the SENDER, `correlation_id` shared across
      the batch from one send via `notif-<uuid4>`), then `_publish_badge`
      pushes a fresh `unread_count` frame to the recipient's stream channel;
      `notify_message_sent(sender, conversation_id, tenant, domain, kind,
      title, body, member_ids)` fires DMs (one per other direct member) and
      mentions (`@username` matches resolved lowercased against the same
      domain's accounts, sender excluded, `MAX_PREVIEW=120`, link
      `/app/chat/{conversation_id}`)), and `router.py` (notifications_router:
      GET `/notifications` screen, GET `/api/notifications`, POST
      `/api/notifications/read-all`, POST `/api/notifications/{id}/read` every
      mutating route behind `require_csrf`, and GET `/api/notifications/stream`
      — the badge SSE stream, account-scoped via `notifications-event-stream`
      read of the session). Every route reads the account from the session,
      never the path, so a foreign id is a plain 404. `MessagingService.
      send_message` now triggers `notify_message_sent` AFTER its commit, so a
      send that fails its governed write never notifies; the recipient stream
      is reached through the existing `sse_bridge` channels (still in-process,
      one bus per process). The shell gained a Bell link in the header
      (`templates/base.html`) with a `data-notification-badge` count element
      updated by `static/js/notifications.js` (exactly one EventSource, retry
      backoff `[1s,2s,4s,8s]`, applies on `unread_count` frames), and Notifications
      nav entries in both nav partials. **The stream is `/app/api/notifications/
      stream`, not `/app/notifications/stream`:** `sw.js` already excludes paths
      ending in `/stream` inside its `/app/api/` cache handler, so the badge
      stream inherits that rule and is never cached (sw.js itself is unchanged).
      Tests: `tests/helix_codex_app/test_notifications.py` (12) cover the mention
      trigger, sender-never-notified, dm trigger, unread counting, idempotent
      read, cross-account isolation, node envelope + shared correlation_id,
      no-notify-on-group-without-mention, self-mention no-op, mark_all_read,
      and empty-body no-op; `test_notifications_routes.py` (13) cover the
      screen (empty/list/401), the JSON list (own items + isolation), mark_read
      idempotent + 404-for-foreign + CSRF, read-all, and the stream pinned at
      the handler level (StreamingResponse + three headers, initial
      `unread_count` frame, bus `notification` frame delivery, cleanup to zero
      subscribers on disconnect — a test client cannot drain an infinite body,
      the P2.2 lesson). **Two P2.1 messaging tests were updated deliberately:**
      `test_send_message_creates_exactly_one_nodes_row` and
      `test_send_message_route_json_writes_and_audits` now expect `before + 2`
      node rows (message node + dm notification node) and the former selects
      the message row `WHERE kind = 'message'` — a governed write that actually
      happens is a changed behavior, and the P1.6 precedent applies. Full suite
      **902 passed, 0 failed** (877 baseline + 12 + 13); ruff check + format
      clean on helix_codex_app/ and tests/helix_codex_app/.
- [x] P2.4 Close out P2 (Prompt 15) — commit `e3f6a8d`,
      `tests/helix_codex_app/test_messaging_isolation.py` (12 tests: foreign
      conversations absent from list; get_conversation/list_messages/send_message
      raise NotFoundError; mark_read no-op with no membership row; foreign
      notifications invisible; HTTP: conversations API empty, thread/messages/
      send API 404, notifications API empty + screen "No notifications yet"),
      `tests/helix_codex_app/test_sse_isolation.py` (6 items: conversation
      stream 403 for any non-member parametrized over same-tenant outsider and
      foreign-tenant account; member-open StreamingResponse + headers pinned at
      handler level; per-conversation key isolation via call_later wrong-then-
      right publish; notification stream owner-only frame delivery; owner-scoped
      initial unread count), `tests/helix_codex_app/test_notification_triggers.py`
      (9 tests: one DM → one dm; each DM fires its own dm (unread 2); repeated
      @omar → exactly 1; @omar @layla → 1 each; @nobody → nothing; no-mention →
      nothing; @ghada foreign-domain → nothing; DM with @omar body → exactly 1 dm,
      never a mention; sender never notified). Full suite **929 passed, 0 failed**
      (902 baseline + 27); ruff check + format clean on all three new modules.

### P3 — Documents, KB, tasks (status: NOT STARTED)

- [x] P3.1 Documents and the block editor (Prompt 16) — commit `02700f8`,
      `helix_codex_app/modules/docs/{__init__,repository,service,router}.py`
      (repository: `Document`/`Block` frozen dataclasses with `to_dict()`,
      `DocsRepository` tenant-scoped — `get_document` raises `NotFoundError`
      with ONE message shape for missing OR foreign; `list_documents(q, status)`
      newest-update-first; `set_status`; `list_blocks`; `get_block` scoped by
      `block_id AND document_id` so a block never leaks through the wrong
      document; `append_block` takes the next ordinal; `insert_block` shifts
      later blocks; `update_block` rowcount-0 → `NotFoundError`; `delete_block`
      renumbers the gap; `reorder_blocks` refuses any list that is not exactly
      the document's blocks; `MAX_TITLE_LENGTH=200`, `MAX_BLOCK_LENGTH=20000`.
      service: `DocsService.create_document/list_documents/get_document/
      insert_block/update_block/delete_block/reorder_blocks/archive_document` —
      every write calls `record_node()` with kind `document` or `block`, nature
      `user_claim`, classification internal, provenance `helix_codex_app.docs` /
      `app_runtime`, fresh `doc-<uuid4>` correlation per write, tenant/client/
      domain from the account record, never from the request. router: `docs_router`
      under `/app` with `docs.read` at the boundary; GET `/docs` (screen, or
      `partials/doc_list.html` fragment under HX-Request), GET `/docs/{id}`
      (editor screen), GET/POST `/api/documents`, GET `/api/documents/{id}`,
      PUT `/api/documents/{id}/blocks/{block_id}`, POST
      `/api/documents/{id}/blocks` — mutating routes carry `docs.write` +
      `require_csrf`, read a JSON body or an HTMX urlencoded form, answer JSON
      or an HTMX fragment (create re-renders the list, add-block re-renders the
      editor) inside the connection try). Templates `templates/{docs.html,
      docs/editor.html}` and partials `{doc_list,doc_editor}.html`
      (contenteditable blocks render server-side, so reading works with JS
      off; saving posts on blur + a 1.5 s debounce through `static/js/docs.js`
      via `htmx.ajax` PUT with a small Saved indicator; add-block posts empty
      content and swaps the editor). `app.py` mounts `docs_router`; Docs nav
      entries enabled in both nav partials; doc/list/editor CSS in `app.css`.
      Tests: `tests/helix_codex_app/test_docs.py` (25) prove the P3.1
      invariants — create writes exactly one `document` node; edit updates the
      row and writes one `block` node; a block of another document is refused
      through this document's route at service and HTTP level (`NotFoundError`,
      404) with the source block untouched; reorder preserves order with
      contiguous ordinals; delete renumbers; reorder refuses partial lists;
      archive drops the doc from the active list; blank/oversized content
      rejected; search filters titles; foreign-tenant document read/edit are
      404 with no row leakage; screens render (empty state, editor with
      contenteditable, 401 unauth, foreign-doc 404); the JSON API contract
      (201 + one node, CSRF 403, blank title 400, doc+blocks payload, foreign
      404); block PUT (update + one node = insert+update total 2, wrong-doc
      404, no-CSRF 403); create/add-block HTMX fragments. Full suite
      **954 passed, 0 failed** (929 baseline + 25); ruff check + format clean
      on helix_codex_app/ and tests/helix_codex_app/.
- [ ] P3.2 Versions and the knowledge base (Prompt 17)
- [ ] P3.3 Tasks (Prompt 18)
- [ ] P3.4 Close out P3 (Prompt 19)

### P4 — Calendar, on-calls, attendance (status: NOT STARTED)

- [ ] P4.1 Calendar and events (Prompt 20)
- [ ] P4.2 On-call rosters (Prompt 21)
- [ ] P4.3 Attendance and punch in/out (Prompt 22)
- [ ] P4.4 Close out P4 (Prompt 23)

### P5 — Per-user metacognitive memory (status: NOT STARTED)

- [ ] P5.1 Fix the two parent defects (Prompt 24)
- [ ] P5.2 The per-account memory store (Prompt 25)
- [ ] P5.3 Proposals, reviews, and the projection tables (Prompt 26)
- [ ] P5.4 The memory screen (Prompt 27)
- [ ] P5.5 Promotion into org memory (Prompt 28)
- [ ] P5.6 Close out P5 (Prompt 29)

### P6 — Operations and the cockpit (status: NOT STARTED)

- [ ] P6.1 The engine bridge, done properly (Prompt 30)
- [ ] P6.2 The Operations section (Prompt 31)
- [ ] P6.3 The cockpit, part one: owner cards (Prompt 32)
- [ ] P6.4 The cockpit, part two: coach, parent, control plane (Prompt 33)
- [ ] P6.5 Close out P6 (Prompt 34)

### P7 — Low-code, release, packaging, signoff (status: NOT STARTED)

- [ ] P7.1 The low-code capability loader (Prompt 35)
- [ ] P7.2 App release gates (Prompt 36)
- [ ] P7.3 Evidence export, backup, and restore (Prompt 37)
- [ ] P7.4 Package and deploy (Prompt 38)
- [ ] P7.5 Signoff: the full gate and the v1 record (Prompt 39)

## Git protocol

- One commit per prompt. Style: `feat(app):`, `test(app):`, `fix(app):`, `docs:`, `chore(app):`.
- NEVER `git add -A`. Stage only the files the prompt names.
- NEVER commit `.db` files, `__pycache__`, `.venv*`, `memory_stores/`, or `evidence/`.
- Write the commit message in plain English.

## Check-in / check-out protocol (from the prompt pack, section 3)

**Check in, before you write anything:**

1. Read this file and state which step is current.
2. Read `helix_codex_app/governance.md` and `helix_codex_app/repomap.md`.
3. State the test baseline you expect (`621 passed` at the start of this pack, then whatever the
   previous prompt recorded).
4. Confirm the files this prompt names actually exist, or do not exist, as the prompt claims. Say so.

**Check out, before you finish:**

1. Run the full suite. Record the exact count.
2. Run ruff on every file you touched.
3. Update `helix_codex_app/agents.md` — tick the step, record the new test count and the commit SHA.
4. Update `helix_codex_app/repomap.md` if you added a top-level folder, a route group, or a table.
5. Update `helix_codex_app/governance.md` if you changed an invariant, a permission, or the
   integration seam. Cite the test that proves it.
6. Make exactly one commit.
7. Report in under 15 lines.

If the check-out count is below the baseline, fix it before committing. Do not commit a regression
and promise to fix it next time.
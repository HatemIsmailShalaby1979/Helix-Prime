# helix_codex_app/: repo map

What lives where in the app package, what the route groups and tables are, and how to add things.
Folders marked "planned" do not exist yet. Create them only under the prompt that names them.

## Purposes, folder by folder

- `__init__.py` — package marker; module docstring only.
- `app.py` — `create_app()` product factory. Mounts the shell, the static mount, and the feature
  routers. `app_router` (read `/app/*`, behind `current_account`) and `csrf_router` (mutating
  `/app/*`, behind `current_account` + `require_csrf`) are wired once at the router boundary;
  `/`, `/app/healthz`, and `/static` stay public.
- `cli.py` — `helix-app` console entrypoint. Runs uvicorn on `settings.host` and `settings.port`.
- `config.py` — `AppSettings`, env prefix `HELIX_APP_`, loopback-only default host, fail-closed
  settings check.
- `errors.py` — `AppError` base; `AuthError`, `PermissionDenied`, `LimitExceeded`, `NotFoundError`,
  and `EngineUnavailableError` (503, `engine_unavailable`, the engine-bridge fail-closed signal).
- `deps.py` — providers that hand out services bound to the authenticated account
  (`memory_store_for`, the `AccountMemoryStore` provider). Each provider takes the
  account the guard resolved, never anything from the request body, so a caller cannot
  widen its own scope by asking.
- `db.py` — Sqlite3 connection factory, schema bootstrap, and `record_node()`, the single
  writer for governed events.
- `governance.md` — the app's operating rules and decision log.
- `agents.md` — the build ledger.
- `repomap.md` — this file.
- `alembic.ini` and `migrations/` — The app-local alembic env, so app tables never join the
  parent migration head.
- `scripts/check_app_migration_drift.py` — builds one database via `db.py` and one via
  `alembic upgrade head` and proves their `sqlite_master` contents agree, exit 0 or 1.
- `scripts/backup_app.py` and `scripts/restore_app.py` (P7.3) — backup copies `app.db` +
  `memory_stores/` into `target/state/helix_codex_app/` with a `backup-manifest.json`
  (node count + memory-chain hashes), reusing `release/backup._sqlite_backup`;
  restore copies the backup into a CLEAN target, then re-verifies the node count
  and each memory chain via `integration.memory_bridge.verify_store_file`, failing
  loudly (exit 1) on any mismatch.
- `security/` — the app-local identity and permission layer. `passwords.py` (stdlib scrypt, SOC-less
  `scrypt$n$r$p$salt$hash` envelope), `accounts.py` (Domain, OrgUnit, Account dataclasses plus
  `AccountRepository`; every account read takes tenant scope from the owning domain, never the
  caller), `limits.py` (role defaults + `check_and_consume`, `LimitExceeded`), `sessions.py`
  (SessionStore: opaque tokens stored as SHA-256 only + a CSRF token; `verify` rejects revoked/
  expired/idle/locked-account sessions; `set_session_cookie`), `permissions.py` (the app permission
  catalog mirroring master plan §5.5 —   `PERMISSION_MATRIX` over owner/manager/employee/contractor/
  external plus a `catalog` column, `permissions_for`, `has_permission`, `capabilities_for`,
  and `PRIVILEGED_CATALOG_ROLE_IDS` read from `organization/role_catalog.py` at import
  time; unknown keys and unknown roles deny; with a connection passed, enabled
  `account_capabilities` rows are unioned in so an admin grant is effective immediately),
  `guard.py` (FastAPI deps: `current_account`, `require_csrf`,
  `require_scope`, `require_capability`, and `require_permission` — enforced against the
  catalog plus live capability rows).
  This layer never edits the parent catalog.
- `integration/` — the only package allowed to import parent internals. `policy_bridge.py` (live:
  `to_identity` maps an account to a `security.identity.Identity` with `role_id` set only for the
  nine catalog roles — every app role maps to `None` and is denied by construction;
  `authorize_engine_action` calls `security.policy.authorize` with the account's own tenant/client
  and raises `PermissionDenied` on any deny). `sse_bridge.py` (live, P2.2: the app's only window
  onto `server.sse.EventBus` — `subscribe`/`unsubscribe`/`publish`/`publish_sync`/
  `subscriber_count` + `encode`, one bus per process). `engine_bridge.py` (live, P4.2: the app's
  first engine read — `wfm_coverage` calls `engines.wfm.adapter.adapt` on the canonical sample
  baseline with `owning_role_id="ops_gm"`, lazily imported at call time, and raises
  `EngineUnavailableError` on import failure, a non-None `result.error`, or a missing
  `optimal_agents` figure — an unavailable engine never yields an empty/degraded answer).
  `memory_bridge.py` (live, P5.3 + P7.3: `AccountMemoryStore`, the per-account governed memory
  provider — `resolve_store_path`, `safe_component`, the store's read/verify/record/
  rollback surface; the org store is the same class with `account_id=None`. `verify_store_file`
  is the one function that opens a `GovernedMemory` by explicit path without an Account — it
  serves the evidence export and backup/restore verification, keeping all other memory access
  behind the Account scoping).
  `metacognition_bridge.py` (live, P5.3: `AccountMetacognition`, the per-account proposal
  engine — `propose`, `evaluate`, `approve`, `reject`, `rollback`,
  `generate_evidence_report`, `verify_chain`).
  `cockpit_bridge.py` (live, P6.3: `owner_summary`, `coach_summary`, `parent_summary`,
  `picker_options`, `as_of_now`, `_context` — calls the pack's own `compute_*` functions
  and hands the dicts to Jinja, so no dashboard logic is rewritten; the data-mode badge
  is the pack's responsibility and the bridge never fabricates a live figure).
  `packs.py` (live, P6.1 + P7.1: `pack_names`, `pack_metadata`, `list_packs`,
  `pack_sections`, `all_sections` — discovers packs by reading each pack's own metadata
  function and derives a section per cockpit view, each gated by `cockpit.view`; P7.1 adds
  the manifest surface `pack_manifest_path`, `manifest_packs`, `packs_without_manifest`,
  and `core_role_financial_limit(role_id)` reading `organization/role_catalog.py` for the
  loader's limit invariant).
- `templating.py` — the one shared template renderer. Reads the CSRF token from
  `request.state.session` and the settings off `request.app.state`, so every route renders with
  the same context instead of re-assembling it. `templates/auth/` uses it too (standalone pages,
  no shell inheritance) because the login screen must work before a session exists.
- `modules/` — the feature modules, one folder per vertical. `identity` (live: the `/app/auth`
  login/me/logout/password surface plus LoginService), `admin` (live: the `/app/admin`
  users/domains/org-units/capabilities/limits surface plus AdminService, owner whole-domain,
  manager own-org-unit only, every write through record_node; plus `evidence.py` (P7.3):
  `build_evidence_zip(conn, *, tenant_id, db_path)` builds the owner-only
  `/app/admin/evidence/export` dossier — the tenant's governed `nodes` audit trail
  (insertion-ordered), node counts by kind, every registered memory store's chain
  verification through `verify_store_file`, and the release manifest, zipped with a
  plain-text README; never a password hash, session token, or raw secret), `messaging` (live, P2.2:
  the `/app/chat` list + thread screens, the conversations/messages/read JSON API, and the
  conversation SSE stream, all `router → service → repository` over the P2.1 schemas) and
  `notifications` (live, P2.3: the `/app/notifications` screen, the notifications/read/read-all
  JSON API, the account-scoped SSE badge stream, and the mention/dm trigger hooks that
  `messaging.service.send_message` calls after its commit) exist; `tasks` (live, P3.3:
  the `/app/tasks` board screen (open/doing/done columns, draggable cards +
  mobile status selects) + `/app/tasks/{id}` detail screen + the tasks/status/
  comments JSON API and HTMX fragments, all `router → service → repository`,
  one governed `task` node per write with a fresh `task-<uuid4>` correlation
  id, assignment notifications through `NotificationService`, a steward gate
  (creator, assignee, or manager may change status/assignment), and the
  archived soft-delete), `calendar` (live, P4.1: the `/app/calendar`
  agenda-first screen (agenda list <768px, month grid ≥768px) + the
  events/respond JSON API and HTMX calendar-view fragment, all
  `router → service → repository`; events are visible only to the creator
  and invited attendees, `[from, to)` range queries with recurrence
  (one text rule daily/weekly) expanded on read never materialised as rows,
  RSVP yes/no/maybe, soft cancellation (`confirmed → cancelled`), a steward
  gate (creator or manager may edit/cancel), one governed
  `event`/`event_response` node per write with a fresh `event-<uuid4>`
  correlation id, and exactly-one `event_invite` notification per new
  attendee; all times are stored and rendered UTC; on-call rosters (P4.2):
  assignments live in `oncall_shifts` with a primary and a backup —
  `create_shift` is manager-only and records one `oncall_shift` node,
  `current_oncall(tenant, at)` reports a covered shift or a `gap`
  (`OnCallCoverage`), never an empty list, and the roster is always app
  data while the WFM staffing figure is read through the engine bridge),
   `attendance` (live, P4.3: the `/app/attendance` punch-clock
   screen, the punch toggle and records/summary JSON API, all
   `router → service → repository`; punches are append-only rows with
   the server deciding `punched_at`, one open punch per account, one
   governed `punch` node per tap sharing the punch correlation_id, an
   org-unit-visible summary (owner whole-domain, manager own-org-unit
   else self, everyone else self) that counts only completed in/out
   pairs bucketed to the punch-in UTC date),
  `docs` (live, P3.2: the `/app/docs` list screen +
  block editor screen, the documents/blocks JSON API, document versions —
  snapshot/list/get/restore, append-only history with `current_version` on
  documents — the `/app/kb` knowledge base screen (sop+kb grouped, SOPs
  first), doc_type note/sop/kb/policy with manager-only sop/policy and note
  owner/manager visibility; router → service → repository, one governed
  `document`/`block`/`version` node per write with a fresh `doc-<uuid4>`
  correlation id. Also `lowcode` (live, P7.1: the capability loader — `pack_loader.py`
  parses `capability.yaml` manifests into `CapabilityManifest` and enforces the five
  invariants before registration, `section_registry.py` serves `sections_for_permissions`
  from the `sections` + `capability_packs` tables (the table-driven section list the cockpit
  now reads), `router.py` exposes GET `/app/api/sections`, GET `/app/api/packs`, POST
  `/app/admin/sections` and POST `/app/admin/packs/reload` — the two writes gated
  `packs.manage`, owner-only — and the first real manifest
  `capabilities/sports_academy/capability.yaml` registers `owner` + `coach`). Leaves
  `memory`, `ops`, `cockpit`
  arriving with their phases. `rooms/` and `mail/` are v2 stubs.
- `templates/` — the Jinja shell. `base.html`, `shell/`, `partials/`, `auth/` (login,
  password, me), and `admin/` (index, users, user_detail, domains, org_units) exist. The
  per-module pages: `tasks.html` + `task_detail.html`, `calendar.html` +
  `partials/event_form.html` + `partials/calendar_view.html`, `docs.html` + `docs/editor.html`,
  `kb.html`, `attendance.html` + `partials/punch.html`, chat and notifications pages. The remaining per-module pages arrive with their phases.
- `static/` — `css/` (tokens and shell), `js/` (PWA and SSE helpers: `pwa.js`, live in P2.2
  `sse.js` — the EventSource client with backoff, per-message dedupe, and the optimistic
  composer — and live in P3.1 `docs.js` — the block editor autosave: debounced `htmx.ajax`
  PUTs on input + blur, small Saved indicator, re-wires after an HTMX add-block swap —
  and live in P3.3 `tasks.js` — the `task_board` Alpine component: HTML5 drag-and-drop
  posts the status via `htmx.ajax` and swaps the board, plus the per-card status
  `<select>` move for touch devices),
  `vendor/` (vendored HTMX and Alpine), `manifest.webmanifest`, `sw.js`, `offline.html`, `icons/`.
  `sw.js` excludes `/stream` paths from its `/app/api/` cache handler on purpose: a live stream is
  never cached.

## The integration seam

`helix_codex_app/integration/` is the only package that may import parent internals: `control_plane`,
`engines`, `security`, `memory`, `metacognition`, `capabilities`, `connectors`. Any other module
under `helix_codex_app/` that imports one of those packages is a defect. This seam is what lets the
app move into its own repo one day: replace the bridges, drop the parent imports, and nothing else
changes.

## Route groups

All app routes sit under `/app`. Ops passthrough routes keep their existing parent paths.

| Group | Prefix | Gate |
| --- | --- | --- |
| Shell and health (live) | `/`, `/app/healthz` | none |
| App home (live) | `/app` | session |
| Static (live) | `/static` | none |
| Auth (live) | `/app/auth/login`, `/me`, `/logout`, `/password` | none for GET/POST `/login`; session + CSRF for the rest |
| Admin (live, P1.6; evidence P7.3) | `/app/admin`, `/users`, `/users/{id}`, `/domains`, `/org-units`, `/evidence/export` | `admin.users`; the evidence export is owner-only (inline role check → `PermissionDenied`, no new permission key) |
| Messaging (live, P2.2) | `/app/chat`, `/app/chat/{id}`, `/app/api/conversations`, `/app/api/conversations/{id}/messages`, `/app/api/conversations/{id}/read`, `/app/api/conversations/{id}/stream` | session; CSRF on posts; membership per route (stream = 403 for non-members) |
| Notifications (live, P2.3) | `/app/notifications`, `/app/api/notifications`, `/app/api/notifications/read-all`, `/app/api/notifications/{id}/read`, `/app/api/notifications/stream` | session; CSRF on the read/read-all posts |
| Docs (live, P3.2) | `/app/docs`, `/app/kb`, `/app/api/documents`, `/app/api/documents/{id}`, `/app/api/documents/{id}/blocks`, `/app/api/documents/{id}/blocks/{block_id}`, `/app/api/documents/{id}/versions`, `/app/api/documents/{id}/versions/{n}/restore` | `docs.read` at the boundary; `docs.write` + CSRF on the mutating routes; sop/policy doc_type is manager-or-owner only; published (sop/kb/policy) visible to all tenant members, notes owner/manager only |
| Tasks (live, P3.3) | `/app/tasks`, `/app/tasks/{id}`, `/app/api/tasks`, `/app/api/tasks/{id}`, `/app/api/tasks/{id}/status`, `/app/api/tasks/{id}/comments` | `tasks.use` at the boundary; `tasks.use` + CSRF on the mutating routes; status/assignment changes need creator, assignee, or manager |
| Calendar (live, P4.1) | `/app/calendar`, `/app/api/events`, `/app/api/events/{id}`, `/app/api/events/{id}/respond` | `calendar.use` at the boundary; `calendar.use` + CSRF on the mutating routes; update/cancel need creator or manager; RSVP requires being an attendee |
| On-call (live, P4.2) | `/app/api/oncall`, `/app/api/oncall/shifts` | `calendar.use` at the boundary + CSRF on the create route; the status route reads the roster (`OnCallCoverage`, covered-or-gap) and fails closed with a typed 503 `engine_unavailable` when the WFM engine read raises; shift creation is manager-only (owner/manager) |
| Attendance (live, P4.3) | `/app/attendance`, `/app/api/attendance/punch`, `/app/api/attendance/records`, `/app/api/attendance/summary` | `attendance.punch` at the boundary; CSRF on the punch toggle; records/summary read APIs apply the same boundary gate |
| Memory (live, P5.3–P5.6) | `/app/memory`, `/app/memory/proposals`, `/app/memory/proposals/{id}`, `/app/memory/ledger/verify`, `/app/memory/promotions`, `/app/api/memory/proposals`, `/app/api/memory/proposals/{id}/evaluate`, `/approve`, `/reject`, `/rollback`, `/app/api/memory/promotions`, `/app/api/memory/promotions/{id}/approve`, `/reject`, `/rollback` | `memory.propose` at the boundary; `memory.review` + CSRF on the review and promotion routes. A proposal is only readable by its author, or by a reviewer in a different role; a same-role peer is told it does not exist. Promotion needs a manager or owner who is not the author |
| Ops (live, P6.2) | `/app/ops`, `/app/ops/{engine}`, `/app/api/ops/workflows`, `/app/api/ops/workflows/{id}`, `/app/api/ops/workflows/{id}/approve`, `/app/api/ops/stream/{id}` | `ops.view` at the boundary; CSRF on the submit and decide routes; the stream is a tenant check before it opens, then a keep-alive loop |
| Cockpit (live, P6.3–P6.4) | `/app/cockpit`, `/app/cockpit/owner`, `/app/cockpit/coach`, `/app/cockpit/parent`, `/app/cockpit/control-plane`, `/app/api/cockpit/summary` | `cockpit.view` at the boundary, re-checked in the service, and enforced by the bridge's own `policy_bridge` call |
| Low-code (live, P7.1) | `/app/api/sections`, `/app/api/packs`, `/app/admin/sections`, `/app/admin/packs/reload` | session at the router boundary; the two admin POSTs also carry `packs.manage` (owner-only) + CSRF |

Every `/app` route except health and static runs the account guard. Every non-GET `/app` route runs
the CSRF check. Both are wired once at the router boundary, not per handler.

## Tables

Governance layer: `nodes`. Working layer: `conversations`, `conversation_members`, `messages`,
`documents`, `doc_blocks`, `document_versions`, `tasks`, `task_comments`, `events`,
`event_attendees`, `oncall_shifts`, `notifications`, `punch_records`, `files`, `memory_stores`,
`proposals`, `proposal_reviews`, `promotions`, `sections`, `capability_packs`. Identity tables:
`domains`, `org_units`, `accounts`, `sessions`, `account_capabilities`, `account_limits`,
`login_events`, `login_throttle`.

All are created by `db.py::_init_schema()` and the app-local alembic baseline `0001_codex_app_baseline` (P1.1).

`promotions` carries `org_proposal_id`, which links a promotion to the org-level proposal it created; without it a rollback could not find what to undo. The column sits last in the `CREATE TABLE`, in both `db.py` and the baseline, because the drift check compares the DDL text and an `ALTER TABLE ADD COLUMN` would land it in a different position.

## Tests

`tests/helix_codex_app/` holds the app suite: `test_passwords.py` (P1.2),
`test_accounts.py` (P1.2), `test_sessions_and_guard.py` (P1.3),
`test_permissions_and_policy_bridge.py` (P1.4), `test_login_and_auth.py` (P1.5),
`test_admin.py` (P1.6), and the four P1.7 boundary modules:
`test_tenant_isolation.py`, `test_cockpit_exclusion.py` (re-pointed at the live
cockpit routes in P6), `test_pwa_assets.py`, and `test_app_migration_drift.py`
(named to avoid the module-name collision with the parent
`tests/test_migration_drift.py`). P2.1 added `test_messaging.py` (service
layer); P2.2 added `test_messaging_routes.py` (screens, JSON contract, HTMX
fragments, CSRF, and the SSE stream — the stream's member-open case is pinned
at the handler level because a test client cannot drain an infinite body).
P2.3 added `test_notifications.py` (service layer: mention/dm triggers, unread
counting, mark-read idempotency, isolation, governed node per batch) and
`test_notifications_routes.py` (screen, JSON contract, CSRF, and the badge SSE
stream pinned at the handler level). P2.4 added `test_messaging_isolation.py`
(service + HTTP: foreign-tenant conversations, messages, and notifications
never leak; `test_sse_isolation.py` (conversation stream 403 for any non-
member, per-conversation key isolation, notification stream owner-only frame
delivery, owner-scoped initial count) and `test_notification_triggers.py`
(once-only semantics: each DM fires one dm, each @mention fires one mention,
repeated names collapse, unknown/foreign-domain/self-mention produce nothing,
sender never notified). P3.1 added `test_docs.py` (25: the four prompt
invariants — one node per create, one node per block edit, a foreign-document
block refused through the wrong route at service and HTTP level, order kept
after reorder — plus delete/archive/search/reject rules, foreign-tenant 404
isolation, and the screens + JSON API + HTMX fragments + CSRF surface). P3.2
added `test_doc_versions_and_kb.py` (26: restore appends — restoring version 2
of four produces version 5 with version 2's content; a snapshot is immutable;
an employee cannot publish sop/policy; a note is invisible to a peer employee
but visible to its owner and managers; kb list = sop+kb only; the versions
JSON/CSRF/HTMX surface and the `/app/kb` screen with type filter, search, and
SOPs-first grouping). P3.3 added `test_tasks.py` (30: one egoverned node per
create/status/comment/assign write; blank-title/blank-body/bad-status
rejection; archived tasks excluded from the default list; done stamps
`completed_at`; the steward gate admits the creator, the assignee, and a
manager and denies an unrelated employee; assignment notifies exactly once on
create-with-assignee and on a changed assignee, never on a no-op re-assign;
comments oldest-first; board + detail screens render and a foreign-tenant task
is a 404; the JSON contract (201 + CSRF 403) and the HTMX board/comments
fragments under HX-Request; unauthenticated 401). P3.4 closed
out P3 with `test_docs_isolation.py` (10: a document in tenant A is
invisible in tenant B at service and HTTP level with no governed write ever
recorded for a foreign document, and a private note is invisible to a peer
employee but visible to its owner and managers), `test_node_invariants.py`
(11: every P3 write path — documents, blocks, versions, tasks, comments —
appends a governed node with a non-null tenant_id, a non-empty `doc-`/
`task-` correlation_id, a known classification, and provenance data_mode
`app_runtime`, plus a full-session sweep finding no un-enveloped node), and
`test_version_restore.py` (7: restore appends a NEW version row whose bytes
equal the restored snapshot and never rewrites any prior row, restores
chain, and each restore records its own governed version node). P4.1 added
`test_calendar.py` (41: one `event` node per create; visibility limited to
the creator and invited attendees (outside/foreign reads are NotFoundError);
`[from, to)` start-inclusive end-exclusive semantics; cancellation hides the
event from listings while the row and its `status: cancelled` node stay; RSVP
updates the attendee row, writes an `event_response` node, and is
NotFoundError for a non-attendee; the steward gate (creator or manager) on
update/cancel; the update node records every changed field; event_invite
notifications fire exactly once per new attendee, never for self or a no-op
re-run; daily/weekly recurrence expansion and single-event non-expansion;
rejection of invalid recurrence/times/titles/unknown attendees; the screens +
JSON contract + CSRF + HTMX fragment + foreign-tenant 404 surface). P4.2
added `test_oncall.py` (26: current_oncall returns the primary for the
current window; a gap is reported as `OnCallCoverage(covered=False,
status="gap")` — never an empty list; all three engine-unavailable modes
raise `EngineUnavailableError` at the bridge (package missing, result
error, missing staff figure); create writes exactly one `oncall_shift`
node with the full envelope and is manager-only; distinct/unknown/
foreign-account/bad-window rejection; tenant scoping with a foreign tenant
seeing nothing; next_shifts lists only the account's own upcoming windows;
the on-call API returns roster coverage + WFM staffing (63 required agents,
is_sample) + own shifts and 503s typed `engine_unavailable` when the engine
is unavailable; create-shift API 201/CSRF-403/manager-403/foreign-400; 401
unauthenticated; the home screen shows the on-call person inside her tenant
and hides a foreign tenant's shifts). P4.3 added `test_attendance.py` (38:
double punch-in raises; punch-out with nothing open raises; one row + one
governed node per punch sharing the punch correlation_id; the server decides
the timestamp; append-only rows with no update/delete path; employee
self-only visible scope, manager org-unit scope (and self-only for a manager
with no org unit), owner whole-domain, foreign tenant nothing — at service,
summary, and records-API level; day-boundary summary math (in 23:30 UTC D,
out 00:30 UTC D+1 → 60 minutes on day D), window-excluded pairs, open punch
contributes zero, inverted window rejected; today_minutes for zero/nothing,
a closed pair, and an open punch under a pinned `_FakeDatetime` clock; the
HTTP surface — screen renders/401/403-external, punch 201 + audit + CSRF-403
+ double-in 400 + out-with-nothing 400 + omitted-action toggle, the HTMX
fragment swapping the label to "Punch out", records/summary APIs rejecting a
lone range edge and an inverted range, manager records API scoping). P4.4
closed out P4 with `test_calendar_isolation.py` (16: events and on-call
shifts never cross tenants at service and HTTP level — foreign
read/update/cancel/respond are NotFoundError, foreign lists are empty,
foreign coverage is a gap never a leaked roster, a shift cannot name a
foreign account, each tenant's writes land in its own rows + governed nodes),
`test_attendance_rules.py` (17: the one-open-punch rule is per account;
punches are append-only rows with no update/delete path; manager-org-unit
visibility — owner whole domain, manager own org unit or just self, everyone
else self, foreign tenant nothing — at service, summary, and records-API
level), and `test_engine_bridge_failclosed.py` (6: a healthy `wfm_coverage`
run returns a full figure and each of the bridge's three failure modes —
engine missing, engine error, missing staffing figure — raises
`EngineUnavailableError`, a raised engine exception propagates as-is, and no
failure mode returns an empty result). Suite: 1182 passed / 0 failed.

The P5 modules prove the memory promise end to end: `test_memory_store.py` (P5.2 — store
resolution, per-account isolation, the index, chain integrity), `test_memory_proposals.py` (P5.3 —
the lifecycle and its refusals), `test_memory_screen.py` (P5.4 — the card partial: evidence numbers
present, rollback only once applied, no approve button on your own proposal), `test_memory_promotion.py`
(P5.5 — promotion and its second approver), plus the four P5.6 close-out modules
`test_memory_store_isolation.py`, `test_proposal_lifecycle.py`, `test_promotion_second_approver.py`,
and `test_ledger_verify.py`. The two parent defects fixed in P5.1 are covered by
`tests/test_metacognition.py` and `tests/test_governed_memory.py`.

P6 added `test_ops.py` (P6.2: the ops section's submit/decide/stream surface and the
correlation-id contract), `test_cockpit_owner.py` (P6.3: the five owner KPIs, the
at-risk list, the approval queue, the data-mode badge, and the foreign-tenant empty
queue), `test_cockpit_views.py` (P6.4: coach, parent, and control-plane selectors and
the audit panel's tenant filter), and the three P6.5 close-out modules:
`test_cockpit_requires_permission.py` (4: every cockpit route returns 403 for an
employee, a contractor, and an external account, and 200 for a manager and an owner;
a refused role gets the same refusal with or without a session and on every path
shape), `test_cockpit_cross_tenant.py` (4: the connector context is built from the
caller's own account, a foreign owner sees an empty approval queue, a foreign owner
gets 404 on another tenant's workflow, and the control-plane audit panel is filtered
by tenant id), and `test_ops_lifecycle.py` (6: submit → approve → close keeps the
correlation id, a refusal stops the workflow to dead_letter with the id intact, a
refused workflow cannot be executed, the submitter cannot decide their own, each
workflow gets its own correlation id, and the correlation id lands in the audit
trail). Suite at the P6.5 checkpoint: **1326 passed, 0 failed**.

P7 added `test_pack_loader.py` (P7.1: 16 — every loader invariant raises its typed error
and loads on its positive case; ownership clash; manifest structure refusals; register-node
envelope; the real sports_academy manifest gating owner/coach; the two admin POSTs)
and `test_evidence_backup_restore.py` (P7.3: 18 — the zip contains all expected entries
with the schema-version README and never a password hash/session token/raw secret;
the audit trail round-trips insertion-ordered with envelope + run + workflow fields intact;
node counts match; the memory-store verification section reports chain results per store,
the release manifest is present, an empty tenant still gets a valid dossier; the HTTP route
is 200 with the right Content-Disposition for an owner, 403 for a manager, 401 unauth;
`verify_store_file` handles an intact chain, a missing file (trivially verifies as empty),
and a tampered chain (fails); backup writes `backup-manifest.json` with the node count and
reports every memory chain verified; restore round-trips the node count and the backup
created under a pre-existing target dir still has its manifest readable). Suite at the
P7.3 checkpoint: **1377 passed, 0 failed** (740 in `tests/helix_codex_app/`, 637 parent).

## How to add a module
Follow the proven `router → service → repository` shape from `server/features/workflows/`. Add
`helix_codex_app/modules/<name>/` with `repository.py`, `service.py`, and `router.py`. Every mutating
path calls `record_node()` with the full envelope. If the module needs the core, add a function to the
matching module inside `integration/` and call that. Register the router in `app.py` under `/app`. Add
the nav entry to the shell. Write the tests in `tests/helix_codex_app/`.

## How to add a section

Sections are data in the `sections` table, not code. A section declares a key, a label, a route, and a
`required_capability`. The shell renders nav entries from the table, filtered by the account's
permissions. An account without the capability never sees the entry, and a direct hit on its route
returns 403 through the same `require_permission` mechanism. The loader lands in P7.1; until then
sections ship as part of their own phase.

## How to add a capability pack

Write `capabilities/<pack>/capability.yaml` per blueprint section 2.3. Implement the `CapabilityPack`
Protocol: `manifest`, `ontology`, `roles`, `workflows`, `metrics`, `runtime`. The loader in
`modules/lowcode` enforces five invariants, each with a test: a pack role cannot widen a core role's
`max_financial_amount`; a pack cannot register a capability another pack owns; a pack without
`production_readiness` of `ESTABLISHED` cannot declare a live `data_mode`; a `min_core_version` above
the runtime refuses to load; a pack role cannot review its own actions. The pack declares sections,
the loader registers them, and the shell renders them.

## Extraction checklist

To move the app into its own repo one day: replace `integration/` with the target platform's own
bindings, drop the parent imports from the wheel and the tests, move `helix_codex_app/migrations/` and
`tests/helix_codex_app/` into the new repo, and change the pyproject package list. Nothing else moves.
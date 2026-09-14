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
- `errors.py` — `AppError` base; `AuthError`, `PermissionDenied`, `LimitExceeded`, `NotFoundError`.
- `deps.py` — planned. `AccountStore`, `CollabStore`, `EngineProvider`, and the memory and
  metacognition providers.
- `db.py` — Sqlite3 connection factory, schema bootstrap, and `record_node()`, the single
  writer for governed events.
- `governance.md` — the app's operating rules and decision log.
- `agents.md` — the build ledger.
- `repomap.md` — this file.
- `alembic.ini` and `migrations/` — The app-local alembic env, so app tables never join the
  parent migration head.
- `scripts/check_app_migration_drift.py` — builds one database via `db.py` and one via
  `alembic upgrade head` and proves their `sqlite_master` contents agree, exit 0 or 1.
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
  `subscriber_count` + `encode`, one bus per process). `engine_bridge.py`, `memory_bridge.py`,
  `metacognition_bridge.py`, `cockpit_bridge.py`, and `packs.py` are planned with their phases.
- `templating.py` — the one shared template renderer. Reads the CSRF token from
  `request.state.session` and the settings off `request.app.state`, so every route renders with
  the same context instead of re-assembling it. `templates/auth/` uses it too (standalone pages,
  no shell inheritance) because the login screen must work before a session exists.
- `modules/` — the feature modules, one folder per vertical. `identity` (live: the `/app/auth`
  login/me/logout/password surface plus LoginService), `admin` (live: the `/app/admin`
  users/domains/org-units/capabilities/limits surface plus AdminService, owner whole-domain,
  manager own-org-unit only, every write through record_node), and `messaging` (live, P2.2:
  the `/app/chat` list + thread screens, the conversations/messages/read JSON API, and the
  conversation SSE stream, all `router → service → repository` over the P2.1 schemas) exist;
  `docs`, `tasks`, `calendar`, `notifications`, `attendance`, `memory`, `ops`, `cockpit`,
  `lowcode` arrive with their phases. `rooms/` and `mail/` are v2 stubs.
- `templates/` — the Jinja shell. `base.html`, `shell/`, `partials/`, `auth/` (login,
  password, me), and `admin/` (index, users, user_detail, domains, org_units) exist. The
  remaining per-module pages arrive with their phases.
- `static/` — `css/` (tokens and shell), `js/` (PWA and SSE helpers: `pwa.js` and, live in P2.2,
  `sse.js` — the EventSource client with backoff, per-message dedupe, and the optimistic composer),
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
| Admin (live, P1.6) | `/app/admin`, `/users`, `/users/{id}`, `/domains`, `/org-units` | `admin.users` |
| Messaging (live, P2.2) | `/app/chat`, `/app/chat/{id}`, `/app/api/conversations`, `/app/api/conversations/{id}/messages`, `/app/api/conversations/{id}/read`, `/app/api/conversations/{id}/stream` | session; CSRF on posts; membership per route (stream = 403 for non-members) |
| Docs and KB (planned, P3) | `/app/docs`, `/app/kb`, `/app/api/documents` | `docs.read` and `docs.write` |
| Tasks (planned, P3) | `/app/tasks`, `/app/api/tasks` | `tasks.use` |
| Calendar, on-call, attendance (planned, P4) | `/app/calendar`, `/app/api/oncall`, `/app/attendance` | `calendar.use`, `attendance.punch` |
| Memory (planned, P5) | `/app/memory`, `/app/memory/proposals`, `/app/api/memory` | `memory.review` for reviews |
| Ops (planned, P6) | `/app/ops`, `/app/api/ops` | `ops.view` |
| Cockpit (planned, P6) | `/app/cockpit/owner`, `/coach`, `/parent`, `/control-plane` | `cockpit.view` |
| Low-code (planned, P7) | `/app/api/sections`, `/app/api/packs` | `packs.manage` for writes |

Every `/app` route except health and static runs the account guard. Every non-GET `/app` route runs
the CSRF check. Both are wired once at the router boundary, not per handler.

## Tables

Governance layer: `nodes`. Working layer: `conversations`, `conversation_members`, `messages`,
`documents`, `doc_blocks`, `document_versions`, `tasks`, `task_comments`, `events`,
`event_attendees`, `oncall_shifts`, `notifications`, `punch_records`, `files`, `memory_stores`,
`proposals`, `proposal_reviews`, `promotions`, `sections`, `capability_packs`. Identity tables:
`domains`, `org_units`, `accounts`, `sessions`, `account_capabilities`, `account_limits`,
`login_events`.

All are created by `db.py::_init_schema()` and the app-local alembic baseline `0001_codex_app_baseline` (P1.1).

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
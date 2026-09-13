# helix_codex_app/: repo map

What lives where in the app package, what the route groups and tables are, and how to add things.
Folders marked "planned" do not exist yet. Create them only under the prompt that names them.

## Purposes, folder by folder

- `__init__.py` — package marker; module docstring only.
- `app.py` — `create_app()` product factory. Mounts the shell, the static mount, and the feature
  routers.
- `cli.py` — `helix-app` console entrypoint. Runs uvicorn on `settings.host` and `settings.port`.
- `config.py` — `AppSettings`, env prefix `HELIX_APP_`, loopback-only default host, fail-closed
  settings check.
- `errors.py` — `AppError` base; `AuthError`, `PermissionDenied`, `LimitExceeded`, `NotFoundError`.
- `deps.py` — planned. `AccountStore`, `CollabStore`, `EngineProvider`, and the memory and
  metacognition providers.
- `db.py` — planned. Sqlite3 connection factory, schema bootstrap, and `record_node()`, the single
  writer for governed events.
- `governance.md` — the app's operating rules and decision log.
- `agents.md` — the build ledger.
- `repomap.md` — this file.
- `alembic.ini` and `migrations/` — planned. The app-local alembic env, so app tables never join the
  parent migration head.
- `security/` — planned. `accounts.py`, `passwords.py`, `sessions.py`, `permissions.py`, `limits.py`,
  `guard.py`. This is the app-local role and auth layer; it never edits the parent catalog.
- `integration/` — planned until its phases fill it. The only package allowed to import parent
  internals. `engine_bridge.py`, `policy_bridge.py`, `memory_bridge.py`, `metacognition_bridge.py`,
  `cockpit_bridge.py`, `packs.py`.
- `modules/` — planned. `identity`, `messaging`, `docs`, `tasks`, `calendar`, `notifications`,
  `attendance`, `memory`, `ops`, `cockpit`, `admin`, `lowcode`. `rooms/` and `mail/` are v2 stubs.
- `templates/` — the Jinja shell. `base.html`, `shell/`, `partials/` exist. `auth/`, `admin/`, and
  the per-module pages arrive with their phases.
- `static/` — `css/` (tokens and shell), `js/` (PWA and SSE helpers), `vendor/` (vendored HTMX and
  Alpine), `manifest.webmanifest`, `sw.js`, `offline.html`, `icons/`.

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
| Shell and health (live) | `/`, `/app`, `/app/healthz` | none for health and static |
| Static (live) | `/static` | none |
| Auth (planned, P1) | `/app/auth/login`, `/logout`, `/me`, `/password` | none for login |
| Admin (planned, P1) | `/app/admin/users`, `/domains`, `/org-units` | `admin.users` |
| Messaging and notifications (planned, P2) | `/app/chat`, `/app/api/conversations`, `/app/notifications` | session |
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

All are created by `db.py::_init_schema()` and the app-local alembic baseline in P1.1. None exist
before then.

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
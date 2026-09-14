# Helix Codex App: Operating Rules and Decision Log

This file is the operating rules for the Helix Codex App and the log of the decisions that set its course.

## 1. What this file is for

A future agent reads this file to know the app's rules without reading the code. It records only what is specific to the app. The parent documents stay the single source of truth for everything else.

## 2. Subordination

On any conflict, 00_CONSTITUTION.md wins, then docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md, then this file, which never restates the parent documents and only records what is specific to the app.

## 3. Scope

The Helix Codex App is an all-in-one productivity and collaboration platform: chat, documents, tasks, calendar, attendance, notifications, a governed operations section, and a manager-only cockpit, with a governed per-user memory under human approval. It is built on the existing governance core, not as a rewrite of it (master plan §1).

What it is not:

- A second service. One process, one SQLite file, one compose file (master plan §3.1).
- An extension of `server/`. The ops surface keeps its own `create_app()` and stays untouched.
- A private place to hide data. Memory isolation is technical, never an exemption from governance. See section 6.
- A place to invent product claims. If a feature is not in this repo or in a passing test, this file does not say it exists.

Deferred, so nobody re-litigates it (master plan §14): collaborative CRDT editing; WebSockets; native mobile apps; video or WebRTC; mail delivery; SSO/SAML; billing and payments; multi-node sync; multi-region; encryption at rest; Postgres; app-store distribution; an offline mutation queue; a public third-party API.

## 4. Inherited invariants (by reference)

These come from 00_CONSTITUTION.md. Each is named here with a pointer, so the parent rule stays the single source of truth.

- Tenant, client, classification, provenance, and correlation context survive every boundary. Parent rule: 00_CONSTITUTION.md, "What this means in practice". In the app this means every governed event and every store is scoped by tenant_id, and no endpoint accepts a foreign tenant or account to read from (master plan §6.1).
- Sensitive actions fail closed. Parent rule: 00_CONSTITUTION.md, "What this means in practice". In the app an app role with no catalog equivalent gets `role_id=None`, and `security/policy.py::authorize` then denies by construction (master plan §5.1).
- Simulated, historical, and live data stay visibly distinct. Parent rule: 00_CONSTITUTION.md, "What this means in practice". In the app every cockpit card that shows simulated data carries the data-mode badge (master plan §8.2).
- Self-improvement is a proposal until isolated evaluation, review, approval, versioning, and rollback exist. Parent rule: 00_CONSTITUTION.md, "What this means in practice". In the app the memory module implements the full lifecycle and nothing applies by itself (master plan §6.4).
- Every decision reveals its assumptions. Parent rule: 00_CONSTITUTION.md, rule 3. The decision log in section 7 is where the app records them.

## 5. App-specific rules

Each rule names where it is enforced so it can be checked in tests.

1. Sessions are opaque cookies with hashed tokens and CSRF double-submit. The `helix_session` cookie is `HttpOnly`, `Secure`, `SameSite=Lax`. Only the SHA-256 hash of the token is stored. `guard.require_csrf` compares the `X-CSRF-Token` header with the session token using `compare_digest` on every non-GET `/app/*` route. Enforced by `helix_codex_app/security/sessions.py` and `guard.py`, checked by the P1 auth boundary tests (master plan §5.4, §13).

2. `cockpit.view` is enforced in three places, so a future route that skips one still fails closed:
   - Router dependency: the cockpit router is included behind `Depends(require_permission("cockpit.view"))`. A session without the permission gets a 403 at the boundary, not a hidden template.
   - Service check: `cockpit/service.py` re-checks the account's permissions before it calls the bridge.
   - Policy bridge: `policy_bridge` calls `security/policy.authorize` for any engine action, using the account's own tenant and client.
   Checked by `test_cockpit_requires_permission` and `test_cockpit_cross_tenant_denied` (master plan §5.6).

3. The app-local role layer lives in `helix_codex_app/security/permissions.py` and never edits the parent role catalog. App roles (`owner`, `manager`, `employee`, `contractor`, `external`) map to `organization/role-catalog.yaml` roles where an equivalent exists. A role with no equivalent gets `role_id=None` and is denied at the policy seam. Checked by the permission-matrix tests and the deny-by-construction test in `tests/helix_codex_app/test_permissions_and_policy_bridge.py` (master plan §5.1).

4. `helix_codex_app/integration/` is the only package that imports parent internals (`control_plane`, `engines`, `security`, `memory`, `metacognition`, `capabilities`, `connectors`). Any other module under `helix_codex_app/` that imports a parent package is a defect (master plan §3.2).

5. `helix_codex_app/db.py::record_node()` is the only writer of governed events. Every mutating service call goes through it with the full envelope: `tenant_id` non-null, `correlation_id`, `classification`, `nature`, `provenance`, `created_by`. Checked by the `record_node` invariants test family (master plan §6.3, §13).

6. Admin is owner-and-manager only, and the gate is two-layered. The admin router is included behind `require_permission("admin.users")` at the boundary, and `AdminService._require_admin` re-checks the same permission (role matrix plus live capability rows) before every write. A manager's scope is their own org unit: `_require_managed_account` and `_require_create_scope` reject anything outside it, and a manager with no org unit manages nothing. An account can never change its own role or status, move its own org unit, or grant or revoke its own capability. Disabling an account revokes its live sessions in the same call. Checked by `tests/helix_codex_app/test_admin.py` (employee-403-on-every-route, manager scoping, self-change denial, session revocation on status change).

7. An admin capability grant is effective at the very next request. `permissions_for`/`has_permission` union enabled `account_capabilities` rows into the role-matrix result when given a connection, and both `guard.require_permission` and `AdminService._require_admin` pass one. No row, no grant: the deny-by-default matrix alone answers when no capability row exists. Checked by `test_granted_capability_is_reflected_in_has_permission_immediately` and `test_grant_widens_route_access_immediately` in `tests/helix_codex_app/test_admin.py`.

## 6. Per-user memory, stated honestly

Each account has its own governed memory store and its own metacognition engine, plus one org-wide store that managers and owners curate. The user proposes an improvement and a human approves it. Nothing applies by itself. Managers and owners can see the org store and the promotion queue, and a promotion needs a second, independent approver.

What this does not mean: per-user memory is not a private place to hide. Every record still carries tenant, classification, provenance, correlation, and evidence references, and a request can never name another account's store. This paragraph exists because over-claiming isolation would break the constitution's truth requirement (00_CONSTITUTION.md, "Truth is paramount").

## 7. Decision log

The decisions locked for the app (2026-09-13 onward; master plan §2). Each entry states the
assumption behind it, per constitution rule 3. Append a new dated entry whenever an invariant,
permission, or the integration seam changes, and cite a test for every invariant change.

1. 2026-09-13. Deliverables go in `E:\Helix-Prime\docs`. Assumption: one repo, one git history, one place to look. A separate folder would fragment the record.
2. 2026-09-13. Frontend is a server-rendered PWA (FastAPI, HTMX, Alpine). Assumption: one language and no build tooling keep the operational cost low, and a PWA avoids app stores.
3. 2026-09-13. Deployment is hybrid: self-hosted now, cloud-portable later. Assumption: the first client runs on its own hardware, and a second service is more operational weight than a solo builder can carry.
4. 2026-09-13. v1 is the whole daily-use product: collab core plus ops and cockpit. Assumption: a product with only a few daily surfaces is not sellable, and phases keep the build manageable.
5. 2026-09-13. Username is `username@domain`, and one domain maps to one tenant. Assumption: a small business maps cleanly to a domain, which gives a simpler login and simpler scoping.
6. 2026-09-13. Per-user memory is a truly isolated store. Assumption: real isolation is the product promise and is worth paying the index cost for, so a rotating verification sweep keeps it honest (master plan §6.6).
7. 2026-09-13. Mail and video are deferred to v2. Assumption: self-hosted mail is blacklist-prone and WebRTC is genuinely hard. Both are specialist problems (master plan §14, items 6 and 7).
8. 2026-09-13. Package name is `helix_codex_app/`, console script `helix-app`. Assumption: one process with two factories, and `helix-api` stays untouched for headless clients (master plan §3.1).
9. 2026-09-14. `helix_codex_app/security/permissions.py` reads `organization/role_catalog.py` at import time for the nine privileged role ids. Assumption: the role catalog is public read-only data, not a parent internal; rule 4's parenthetical list does not name `organization`, and master plan §5.1 explicitly sanctions the read. The catalog file is never edited. Proven by `test_privileged_catalog_role_ids_match_the_organization_catalog` (P1.4).
10. 2026-09-14. Admin capability grants widen `has_permission` immediately. Assumption: an admin-granted capability row is exactly the mechanism the prompt set P1.6 names for granting app permissions to a single account, so the permission check unions enabled rows on every read that passes a connection; the role matrix stays the floor and nothing is granted without a row. Proven by `test_granted_capability_is_reflected_in_has_permission_immediately` and `test_grant_widens_route_access_immediately` (P1.6).
10. 2026-09-14. Lockout and no-enumeration on sign-in. After MAX_FAILED_ATTEMPTS (5) consecutive failures an account locks for LOCK_MINUTES (15); an expired lock unlocks on the next attempt; every attempt writes a `login_events` row, including when the domain or account does not exist (ids NULL); the page shows exactly one message for a wrong domain, a wrong username, or a wrong password, and the machine code stays in the audit row. Assumption: rate-limiting real accounts only still slows a brute-force attacker, and a shared message protects real accounts from enumeration through the login form. Proven by `test_sixth_attempt_is_locked_and_lock_is_recorded`, `test_unknown_domain_is_recorded_without_enumeration`, and `test_expired_lock_allows_login_again` (P1.5).
11. 2026-09-14. Live chat events are delivered in-process over the parent EventBus, not a second wire. The app reaches `server.sse.EventBus` only through `helix_codex_app/integration/sse_bridge.py` (rule 4 holds; the seam now has a second member). A message POST writes its governed node (rule 5) and then `publish`es the one frame; the conversation stream generator subscribes, heartbeats every 15 seconds, and unsubscribes on disconnect. Assumption: one process, one bus is exactly the "one process" decision from entry 8, and a real broker is a v2 problem. Proven by `test_conversation_event_stream_emits_a_posted_message` and `test_conversation_event_stream_closes_cleanly_on_disconnect` (P2.2).
12. 2026-09-14. The conversation stream refuses non-members with a 403, not a 404, while everywhere else in messaging a non-member gets 404. Assumption: the stream is an open observable endpoint, so acting as if the conversation exists is fine and rejecting is what matters; on the read/write endpoints acting as if nothing exists beats confirming a guess. Both answers are the same `NotFoundError`/`PermissionDenied` family and the membership check is identical. Proven by `test_stream_is_403_for_any_non_member` (same-tenant outsider and other-tenant both 403) and `test_thread_screen_is_404_for_a_non_member` (P2.2).
13. 2026-09-14. Notifications live. A `notifications` table (per-account rows, sender/recipient/kind/body/link/read_at) plus `NotificationService` and `NotificationRepository` (create/list_for/unread_count/mark_read/mark_all_read); the screen at `/app/notifications`; the JSON API under `/app/api/notifications`; a Bell icon in the shell with a live count fed by an account-scoped SSE stream; and mention/dm triggers at the end of `MessagingService.send_message`, after its commit, so a send that fails its governed write never notifies. Every notification row writes a governed node (`kind="notification"`, `nature="system_event"`, `correlation_id` shared across the batch from one send, `created_by` the sender) through `record_node()` (rule 5). The stream is under `/app/api/notifications/stream`, not `/app/notifications/stream`, on purpose: `sw.js` already skips paths ending in `/stream` inside its `/app/api/` cache handler, so the badge stream inherits that exclusion and is never cached. The badge is a DOM element `data-notification-badge` updated by `static/js/notifications.js`, which opens exactly one `EventSource` and reconnects with backoff; mention triggers fire only for lowercased `@username` matches whose account is a member of the same domain, and the sender is never notified of their own message. Assumption: in-process delivery is exactly the "one process, one bus" decision from entry 8 (the badge is emitted by the same subscriber channels `subscribe`/`publish` already provide), and a push outbox to real devices is a v2 problem. Proven by `tests/helix_codex_app/test_notifications.py` (12) and `test_notifications_routes.py` (13), including `test_mention_creates_one_notification_for_the_named_account`, `test_dm_creates_notification_for_the_other_member`, `test_mention_of_self_does_not_notify`, and the stream's initial-frame and disconnect-cleanup cases (P2.3).
14. 2026-09-14. `send_message` completing is now a governed reality with one extra node per recipient, so two P2.1 messaging tests were updated to match instead of frozen: `test_send_message_creates_exactly_one_nodes_row` and `test_send_message_route_json_writes_and_audits` now expect `before + 2` node rows (the message node plus the dm notification node). Assumption: a governed write that actually happens is a changed behavior, and the P2.1 assertions were counting "sender's node only" by the mistake of ignoring later phases; the P1.6 precedent of adjusting a test when a new governed feature starts writing is the honest way to keep the suite green. Proven by the updated assertions themselves (P2.3).
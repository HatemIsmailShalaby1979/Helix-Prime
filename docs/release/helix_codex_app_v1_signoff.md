# Helix Codex App v1 — Sign-off

**Date:** 2026-09-15 · **Profile:** `app_pilot` · **Classification:** `CONTROLLED_PILOT_READY` ·
**Exit code:** 0 · **Recorded at commit:** `b6b954e` (this signoff is the commit that closes P7).

This document records the v1 release gate and evidence for the Helix Codex App (the daily-use
product layer of Helix Codex OS). Every number below comes from a command run during this sign-off
session; the command and its output are recorded next to each number. Nothing is reproduced from a
prior session.

---

## 1. Full test suite

The suite is run in two chunks because this sandbox is very slow (the app chunk takes ~58 minutes,
the parent chunk ~16 minutes). Both commands were run this session via detached pytest processes and
their logs read on completion.

**App chunk**

```
.venv-py312\Scripts\python.exe -m pytest tests/helix_codex_app/ -q -p no:cacheprovider -m "not smoke"
```

**Parent chunk**

```
.venv-py312\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider -m "not smoke" --ignore=tests/helix_codex_app
```

Result: **1395 passed, 0 failed.** Both chunks observed green this session.

| Chunk | Passed | Failed | Duration |
| --- | --- | --- | --- |
| `tests/helix_codex_app/` (app) | 758 | 0 | 2022.55 s |
| `tests/` minus app (parent) | 637 | 0 | 792.88 s |
| **Total** | **1395** | **0** | — |

The v1 requirement is **≥ 621 passed, 0 failed** (the pack baseline). The count above is the
full non-smoke collection for this repository at this commit.

**Honesty note (the parent chunk ran twice).** The first parent run observed `632 passed, 5
failed` — the five failures were the release-gate tests (`test_c8_release_gate.*`,
`test_capabilities_restaurant.test_release_gates`, `test_command_center_integration.
test_release_gates`, `test_pilot.test_release_gates`), all classified `NOT_READY`. Root cause
was a single, docs-only finding: the P7.4 ledger note in `helix_codex_app/agents.md` quoted a
`password` keyword assigned an 8+ char value (a plain variable name), which the fail-closed
secrets gate flags as a secret-like literal. The note was reworded (no code change),
`scan_for_secrets()` re-ran at **0 findings**, and the five
gate tests re-ran green 5/5 (201.70 s: 3:21). The full parent chunk then re-ran on a quiet
machine for this record: **637 passed, 0 failed**, as shown above. The gate turning red on a
false positive is the fail-closed design working as intended.

---

## 2. Release gate (`app_pilot` profile)

**Command**

```
.venv-py312\Scripts\python.exe -m release.gate --profile app_pilot
```

**Result:** `CONTROLLED_PILOT_READY` — all 11 required gates green, `all_gates_green: true`,
`permitted_c8_outcome: true`, `exit_code: 0`. The harness also ran green (`15 checks, failed=[]`).
The gate wrote its evidence pack under `evidence/releases/20260915T190754Z/` (gitignored) and
regenerated `release/release-manifest.json` to reflect this commit.

> **Manifest write-order note.** Running the parent suite exercises the release-gate tests, and
> `test_pilot.py::test_release_gates` deliberately ends with `run_gate("production")` — the
> fail-closed probe asserting `NOT_READY` — which writes a `production / NOT_READY` manifest as a
> side effect. That is correct behavior, not a regression. The final gate run of this sign-off
> session re-asserted the `app_pilot / CONTROLLED_PILOT_READY` manifest below so the committed
> release manifest matches the signed state.

| Gate | OK | Detail |
| --- | --- | --- |
| repository_state | true | git + runtime detectable |
| configuration_validation | true | gates=True profiles=True schema=True |
| startup_readiness | true | all_ok=True startup_ok=True ready=True |
| data_isolation | true | data_isolation_ok=True class=True deny_default=True |
| audit_integrity | true | isolated probe chain valid; runtime chain not declared (no `HELIX_AUDIT_DB_PATH`) |
| app_auth_boundary | true | 0 unguarded /app routes |
| app_session_fail_closed | true | live=True revoked=True expired=True |
| app_tenant_isolation | true | scoped-read ok=True |
| app_memory_store_isolation | true | cross-account visible=False |
| app_migration_drift | true | store=59 migration=59 errors=0 |
| app_pwa_assets | true | icons=3/valid=True start=True sw=True offline=True |

Fail-closed design preserved: the gate can only emit `CONTROLLED_PILOT_READY` or
`PRODUCTION_CANDIDATE`; it never emits an unqualified `PRODUCTION` label (`release/profiles.py`,
`release/release-profiles.yaml`).

**Regenerated release manifest** (`release/release-manifest.json`, written by the gate run):

```
release_profile: app_pilot
classification:  CONTROLLED_PILOT_READY
git_commit:      b6b954edddd285e8e1cc01b8cb301507d16b69ee   (HEAD at gate time)
version:         0.9.0-c8
build_timestamp: 2026-09-15T19:07:54.349305Z
dependency_lock_count: 333
evidence_refs:   [evidence\releases\20260915T190754Z]
```

---

## 3. Ruff on the whole app tree

Pinned ruff is `ruff==0.1.15` (declared in `pyproject.toml`); the PATH `ruff` is a newer 0.16.1 and
was NOT used, because its formatter would rewrite the whole tree. The venv binary
`.venv-py312\Scripts\ruff.exe` (0.1.15) is the one that matches the repo pin and the CI gate.

**Lint (full app tree + app tests)**

```
.venv-py312\Scripts\ruff.exe check helix_codex_app/ tests/helix_codex_app/
```

Result: **All checks passed!** (0 errors, exit 0), over 125 files.

**Format check (full app tree + app tests)**

```
.venv-py312\Scripts\ruff.exe format --check helix_codex_app/ tests/helix_codex_app/
```

Result: **125 files already formatted** (exit 0). Three pre-existing P6.5 test files
(`test_cockpit_cross_tenant.py`, `test_cockpit_requires_permission.py`, `test_ops_lifecycle.py`)
were not formatted under 0.1.15 — they were flagged as an open finding in P7.1 — and were run
through `ruff format` this session so the whole tree is clean under the pinned formatter. They ride
in this commit as the only code change.

---

## 4. What this v1 does

The Helix Codex App is an all-in-one collaboration platform with a governed, audit-trailed core on
top of Helix Codex OS. Every governed write goes through `db.py::record_node()` (one `nodes` row
per write, always carrying tenant_id, classification, nature, provenance, created_by), and every
capability below is covered by an app test module listed in parentheses — **no capability is listed
without a test that covers it**.

- **Identity and sessions** — password login per `username@domain`, scrypt hashing,
  opaque-cookie sessions (only token hashes stored), CSRF on every mutating route, lockout after 5
  failed attempts, session revocation, `must_change_password` flow. (`test_passwords.py`,
  `test_accounts.py`, `test_sessions_and_guard.py`, `test_login_and_auth.py`)
- **Permissions and RBAC** — a permission matrix across owner/manager/employee/contractor/external,
  plus a policy bridge to the core authorization engine; unknown roles and keys deny by default.
  (`test_permissions_and_policy_bridge.py`)
- **Admin** — users, domains, org units, capabilities, limits; owner acts domain-wide, a manager
  only inside their own org unit; no self-privilege changes. (`test_admin.py`)
- **Chat and SSE** — direct/group conversations, message pages, live stream with heartbeats,
  versioned service worker exclusion for streams. (`test_messaging.py`, `test_messaging_routes.py`,
  `test_sse_isolation.py`)
- **Notifications** — DMs and `@mention` triggers, per-account unread badge over a stream.
  (`test_notifications.py`, `test_notifications_routes.py`, `test_notification_triggers.py`)
- **Documents, versions, knowledge base** — block editor, append-only version history with
  restore, note/SOP/KB/policy types with manager-only publishing. (`test_docs.py`,
  `test_doc_versions_and_kb.py`, `test_version_restore.py`)
- **Tasks** — board, statuses, assignment with exactly-one notification, soft archive, steward-gated
  edits. (`test_tasks.py`)
- **Calendar and on-call** — events with RSVP and recurrence (text rule expanded on read),
  on-call rosters; the WFM engine bridge is a staffing calculator that fails closed.
  (`test_calendar.py`, `test_oncall.py`, `test_engine_bridge_failclosed.py`)
- **Attendance** — punch in/out with the server as the time authority, one open punch per account,
  completed-pair summaries, owner/manager/self visibility scopes. (`test_attendance.py`,
  `test_attendance_rules.py`)
- **Per-user governed memory** — a per-account JSONL ledger plus a shared org store, hash-chained
  and verifiable. (`test_memory_store.py`, `test_memory_store_isolation.py`, `test_ledger_verify.py`)
- **Proposals and promotion** — draft → evaluated → approved/rolled-back lifecycle with SOD
  (no self-approval) and promotion into org memory requiring a second approver. (`test_memory_proposals.py`,
  `test_proposal_lifecycle.py`, `test_promotion_second_approver.py`, `test_memory_promotion.py`)
- **Operations** — engine overview, governed workflow submission and approvals, per-workflow SSE,
  kill-switch read. (`test_ops.py`, `test_ops_lifecycle.py`, `test_engine_bridge.py`)
- **Cockpit** — read-only owner/coach/parent dashboards plus the control-plane panel, all behind
  `cockpit.view` at the router, the service, and the policy bridge. (`test_cockpit_views.py`,
  `test_cockpit_owner.py`, `test_cockpit_requires_permission.py`, `test_cockpit_cross_tenant.py`)
- **Low-code capability loader** — YAML capability manifests with five hard invariants, owned
  capabilities, permission-gated sections. (`test_pack_loader.py`)
- **Evidence export, backup, restore** — a tenant-scoped evidence zip (audit rows, memory-store
  verification, manifest) and scripted backup/restore that verifies chains before it reports success.
  (`test_evidence_backup_restore.py`)
- **PWA shell** — installable manifest, icons, service worker, offline page. (`test_pwa_assets.py`)
- **Packaging** — one `docker compose up` service on the client's own hardware. (`test_app_packaging.py`)
- **Release gates and migration drift** — the `app_pilot` profile with six app gates; `db.py` and
  the alembic head agree token-for-token. (`test_app_release_gates.py`, `test_app_migration_drift.py`)
- **Tenant isolation** — cross-tenant reads are empty or 404 across every module, proven
  module-by-module. (`test_tenant_isolation.py`, `test_calendar_isolation.py`, `test_messaging_isolation.py`,
  `test_docs_isolation.py`, `test_cockpit_cross_tenant.py`)

---

## 5. What this v1 does not do

From `docs/HELIX_CODEX_APP_MASTER_PLAN.md` §14 (verbatim). v1 will not do:

> collaborative CRDT editing; WebSockets; native mobile apps; video or WebRTC; mail delivery;
> SSO/SAML; billing and payments; multi-node sync; multi-region; encryption at rest; Postgres;
> app-store distribution; an offline mutation queue; a public third-party API.

Matching this, there is no payment/instrument code, no Postgres or non-SQLite backend, no network
sibling transport, no autonomous/financial/personnel/compliance/external-communication actions, no
cloud deployment capability, and no external identity provider anywhere in the app tree.

---

## 6. Known limitations (recorded)

The release manifest (`release/release-manifest.json`, section `known_limitations`) records the
operational boundary the app ships under:

- Local SQLite persistence only — no cloud redundancy or HA. One process, one database, one
  compose file; no Redis, no broker, no separate frontend host.
- The app binds `127.0.0.1` and refuses a public host (`require_safe_defaults`), so it is not
  reachable from other machines without an SSH tunnel or VPN.
- SSE is in-process only (one `EventBus` per process); a broker is a documented v2 decision.
  Events stream at `/app/api/.../stream` and are never cached by the service worker.
- All times are UTC, stored and rendered; there is no per-tenant timezone column in v1.
- Sensitive app data is limited to explicitly consented pilot data; the app runs with
  `HELIX_SAMPLE_DATA_MODE` off in production-phased containers and the cockpit badges the data
  mode on every card.
- Employment scope is the app's own role matrix; core catalog roles map through the policy bridge
  only, and an app-only role never widens core authority.
- Ollama/core model trust is assumed local and user-controlled; no remote model attestation.

---

## 7. Definition of shippable v1, first client (§13)

> a coach on a phone installs the PWA, logs in as `username@academy`, punches in, chats with the
> team, reads an SOP, completes a task, and sees the calendar. A manager does all of that plus
> reviews a governed improvement proposal with its evidence. The owner sees the read-only cockpit —
> five KPIs, attendance, at-risk athletes, the approval queue. Every action appears in the audit
> trail and the evidence export. It runs from one `docker compose up` on the client's own hardware.
> An employee account receives 403 on every cockpit route.

Every sentence of that definition is verified by a test suite listed in §4: the PWA shell, the
`username@domain` login, the punch clock, chat, the SOP/knowledge base, tasks, the calendar, the
proposal review with evidence, the owner cockpit with the five numbers and the approval queue, the
audit trail and evidence export, the one-command compose deployment, and the employee-403 cockpit
exclusion. The full suite and the `app_pilot` gate above are green at this commit.

---

**Sign-off result:** **CONTROLLED_PILOT_READY** — the v1 app is safe to pilot on the local box with
synthetic or explicitly consented data. It is **NOT** a production approval; an unqualified
`PRODUCTION` label remains unreachable by the gate, exactly as designed.
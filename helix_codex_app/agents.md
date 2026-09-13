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
| Current step | P1 — Identity, auth, org, limits (next prompt P1.2) |
| Baseline test count | 629 |
| Last commit | `781b0b3` feat(app): add app database, schema bootstrap, and governed node writer |
| Completed steps | P0.1, P0.2, P0.3, P0.4, P1.1 |

## Step ledger

### P0 — Scaffold and governance (status: COMPLETE)

- [x] P0.1 Scaffold the package and boot the shell (Prompt 1) — commit `822402e`
- [x] P0.2 The mobile-first PWA shell (Prompt 2) — commit `3887079`
- [x] P0.3 governance.md (Prompt 3) — commit `0b3765c`
- [x] P0.4 agents.md and repomap.md (Prompt 4) — commit `50bba63`, 621 passed

### P1 — Identity, auth, org, limits (status: IN PROGRESS, next prompt P1.2)

- [x] P1.1 App database and the single writer (Prompt 5) — commit `781b0b3`, 629 passed
- [ ] P1.2 Accounts, domains, and passwords (Prompt 6)
- [ ] P1.3 Sessions, cookies, and CSRF (Prompt 7)
- [ ] P1.4 The permission catalog and role mapping (Prompt 8)
- [ ] P1.5 Login, logout, and the auth screens (Prompt 9)
- [ ] P1.6 Admin: users, domains, org units, capabilities, limits (Prompt 10)
- [ ] P1.7 Close out P1: isolation, PWA assets, ledger (Prompt 11)

### P2 — Messaging, notifications, SSE (status: NOT STARTED)

- [ ] P2.1 Conversations and messages (Prompt 12)
- [ ] P2.2 The chat UI and the SSE stream (Prompt 13)
- [ ] P2.3 Notifications (Prompt 14)
- [ ] P2.4 Close out P2 (Prompt 15)

### P3 — Documents, KB, tasks (status: NOT STARTED)

- [ ] P3.1 Documents and the block editor (Prompt 16)
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
# Prompt Sequence — Ruthless Fix Execution (Helix-Prime P0–P3)

**For:** a fresh coding agent (Agnes 2.5 Flash / Claude Code) landing in `E:\Helix-Prime`
**Recorded:** 2026-09-10 · **Source audit:** `docs/audits/2026-09-10_full_audit_production_plan.md`
**Task ledger:** `AGENTS.md` §0 (H-steps) — the agent must update it after every prompt

## How to use this file

1. Run the prompts **in order**. Each is scoped to one commit-sized change.
2. **Prepend `PREAMBLE` to every prompt** (below). The agent has no memory of earlier
   turns — without it, it will re-derive facts and drift.
3. After each prompt: verify, commit, then send the next prompt in a **fresh** turn
   (fresh context beats a long polluted one at this size).
4. If a prompt fails verification, do **not** move on. Send `PREAMBLE` + the prompt again
   with the error output appended.
5. **Prompt 6 (H1.4) is blocked** on a user decision — skip it and continue, or ask first.

---

## PREAMBLE (paste before EVERY prompt)

```
You are working in the repository E:\Helix-Prime ("Helix Codex OS") — a Python 3.12
governed-autonomy platform. Read AGENTS.md section §0 (the ACTIVE task) and §0B before
writing anything. AGENTS.md §0B onward is a COMPLETED historical ledger — do not restart it.

ENVIRONMENT (verified — do not re-derive):
- Venv: .venv-py312\Scripts\python.exe  (Python 3.12.10; has pytest + pytest-cov)
  .venv312 has NO pytest. .venv-win is 3.10 — never use it.
- Test:  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke"
  Baseline: 571 passed, 0 failed. Collection ~5s; full run ~20 min.
  NOTE: the -m "not smoke" filter is a no-op (no test carries markers) — keep using it for consistency.
- Lint:  .venv-py312\Scripts\ruff.exe check <paths>
  Config pyproject.toml: line-length=100, select=E4/E7/E9,F
- Windows gotcha: tests opening SQLite inside tempfile.TemporaryDirectory() MUST close
  stores/connections before the `with` block exits, else teardown fails with WinError 32.

REUSABLE PRIMITIVES — reuse, never reinvent:
- security/identity.py::Identity          (deny-by-default; tenant/client/role scoped)
- security/policy.py::authorize(req)      (AuthorizationRequest -> AuthorizationDecision)
- release/gate.py                         (14 core + 9 production gates)
- scripts/export_evidence_pack.py         (evidence exporter — ALREADY EXISTS, read-only)
- tests/support/sqlite_harness.py::sqlite_store

NON-NEGOTIABLE:
1. Fail closed, never silently. When a control cannot be evaluated: deny and RAISE.
   Never `pass`, never bare `return`, never `except: pass`.
2. Never regress the suite: after your change it must still be >= 571 passed, 0 failed.
3. Do not edit organization/role-catalog.yaml, organization/capability-registry.yaml,
   or their mirrors unless this prompt explicitly instructs you to.
4. PRESERVE release/gate.py:218-258 — the 9 production gates are hardcoded False with
   documented reasons. Correct fail-closed design. Never make them pass locally.
5. No comments in code except module docstrings.
6. No new dependencies unless this prompt says so (then also update requirements.txt).
7. Minimal diff. Do not refactor, reformat, or "improve" anything outside the listed files.

COMMIT: one commit per prompt. Style: fix(sec): / fix(gov): / test(sec): / test(gov): /
docs: / chore(ci): . NEVER `git add -A` — stage only files you touched. NEVER commit
.db, __pycache__, .venv*, or evidence/ artifacts.

REPORT at the end (under 15 lines): files changed, test result (X passed / Y failed),
ruff result, commit SHA, and anything you could not do.
```

---

## Prompt 0 — Orient (send this first, alone)

```
PREAMBLE

GOAL: Orient yourself and confirm the baseline. Do not change any code yet.

1. Read AGENTS.md §0 and §0B.
2. Read docs/audits/2026-09-10_full_audit_production_plan.md (the audit behind this task).
3. Confirm HEAD: git log --oneline -5
4. Run the suite and record the baseline:
   .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -5
5. Confirm these findings still exist (quote the exact line for each):
   - engines/rta/src/app.py:269   app.run(host="0.0.0.0", port=5000, debug=True)
   - engines/rta/src/app.py:32    CORS(app)
   - server/config.py:52          host default "0.0.0.0"
   - control_plane/engine.py:137  audit silently skipped
   - control_plane/engine.py:687  except KeyError: pass  (SOD bypass)
   - .github/workflows/ci.yml:24  pip install -r requirements.lock.txt (no such root file)

REPORT: baseline test count and each finding with file:line. If any finding is already
fixed, say so explicitly. Do not fix anything in this step. No commit.
```

---

# PHASE P0 — Make it safe to run

## Prompt 1 — H0.1: RTA Flask hardening (G01, G03)

```
PREAMBLE

GOAL: Remove the remote-code-execution exposure in the RTA Flask service.

CONTEXT: engines/rta/src/app.py is a Flask app. Line 269 runs
`app.run(host="0.0.0.0", port=5000, debug=True)`. Werkzeug's debug console allows
arbitrary code execution; bound to 0.0.0.0 it is reachable by anyone on the network.
The debug PIN is not an auth boundary. Line 32 `CORS(app)` is a wildcard
Access-Control-Allow-Origin: * on every route.

CHANGES (file: engines/rta/src/app.py ONLY):
1. Line 269 — remove `debug=True` entirely. Change the bind to `127.0.0.1`.
   Keep the port. If the module is used as a WSGI entrypoint elsewhere, keep the
   `if __name__ == "__main__":` guard shape; do not restructure the file.
2. Line 32 — replace bare `CORS(app)` with an explicit origin allowlist driven by an
   environment variable (e.g. RTA_CORS_ORIGINS, comma-separated), defaulting to EMPTY
   (no origins) when unset. Deny-by-default: an unset variable must allow nothing.
3. Mirror the existing convention in server/config.py:55-56 which already defaults
   cors_origins to an empty list — match its style and env-naming pattern.

CONSTRAINTS:
- Do not add authentication in this step (that is Prompt 3 / H0.3).
- Do not change any route logic or response shape: 9 routes must behave identically.
- If any test asserts the old bind or CORS behaviour, update the test and say so.

VERIFY:
  .venv-py312\Scripts\ruff.exe check engines/rta/src/app.py
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -3
  grep -n "debug=\|host=\|CORS(" engines/rta/src/app.py

COMMIT: fix(sec): bind RTA Flask to loopback, disable debug, explicit CORS origins
Then update AGENTS.md §0.4 (check H0.1) and §1.
```

## Prompt 2 — H0.2: Server bind default (G08)

```
PREAMBLE

GOAL: Stop the FastAPI server from defaulting to all interfaces.

CONTEXT: server/config.py:52 declares `host: str = "0.0.0.0"` with a
`# noqa: S104 - container default, overridable` suppression. Nothing in the repo
provides a reverse proxy or auth layer that justifies it, so the default is unsafe.

CHANGE (file: server/config.py ONLY):
- Line 52: default `host` to "127.0.0.1". Keep it overridable by the existing
  HELIX_* environment variable. Update the comment to state that 0.0.0.0 must be an
  explicit opt-in for container deployment.

CONSTRAINTS:
- Do not change the env var name; docker-compose must keep working when it sets it.
- Check infra/docker/docker-compose.yml and infra/docker/entrypoint.sh: if they rely on
  the in-code default (rather than setting the env var), set the env var there explicitly.
- Do NOT change the port.

VERIFY:
  .venv-py312\Scripts\ruff.exe check server/config.py
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -3
  grep -rn "0.0.0.0" server/ infra/docker/

COMMIT: fix(sec): default API server bind to loopback, require explicit opt-in
Then update AGENTS.md §0.4 (check H0.2).
```

## Prompt 3 — H0.3: Authentication + RBAC on the API (G02) — LARGEST STEP

```
PREAMBLE

GOAL: Every /api route on the FastAPI server must require an authenticated identity
with an authorized role. /healthz (and only /healthz) stays public.

CONTEXT: server/app.py:102-109 mounts 8 routers — health, workflows, approvals, stream,
console, chat, tasks, docs. Today all of them accept anonymous requests. Two routers are
especially dangerous: /api/approvals (governance approvals) and /api/chat (agent
execution). This is a governance product; unauthenticated approval endpoints are the
single worst finding in the audit.

REUSE — do not invent a new auth model:
- security/identity.py::Identity  (actor, actor_type, tenant_id, client_id, role_id;
  validates itself in __post_init__)
- security/policy.py::authorize(req: AuthorizationRequest) -> AuthorizationDecision
  (deny-by-default; returns .allowed / .reason / .code)
Build the FastAPI dependency around these two. The role catalog is
organization/role-catalog.yaml (read-only — do not edit it).

CHANGES:
1. New module server/auth.py:
   - `current_identity(...)` FastAPI dependency: reads a bearer token from the
     Authorization header, resolves it to an Identity, raises HTTP 401 on missing/
     invalid token and HTTP 403 on unauthorized role.
   - Token source: environment-configured. For this step, a single operator token from
     env `HELIX_API_TOKEN` compared with hmac.compare_digest (constant time) is
     acceptable; map it to a configurable role via `HELIX_API_TOKEN_ROLE`
     (default "sami"). Keep the resolution seam clean so a real IdP can replace it.
   - NEVER log the token. Never accept a token in a query string.
2. server/app.py: apply the dependency to all routers EXCEPT health. `/static` stays
   public. Use a router-level dependency — do not decorate handlers one by one.
3. Add tests in tests/test_server_auth.py:
   - no token -> 401 on /api/approvals and /api/chat
   - wrong token -> 401
   - valid token, unauthorized role -> 403
   - valid token, authorized role -> 200 (or the route's normal status)
   - /healthz reachable with NO token (200)
   Use fastapi.testclient (the repo already uses `pytest.importorskip("fastapi.testclient")`
   — see tests/test_server_spine.py:22; follow that pattern).

CONSTRAINTS:
- Do not change business logic in any router.
- Do not edit security/identity.py or security/policy.py.
- Do not add a dependency; use stdlib + fastapi only.
- If a route legitimately needs public access, list it explicitly in your report and
  justify it — do not silently leave routes open.

VERIFY:
  .venv-py312\Scripts\ruff.exe check server/auth.py server/app.py tests/test_server_auth.py
  .venv-py312\Scripts\python.exe -m pytest tests/test_server_auth.py -q
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -3
  (must be >= 571 passed — your new tests ADD to that)

COMMIT: fix(sec): require authenticated identity on all /api routes, /healthz excepted
Then update AGENTS.md §0.4 (check H0.3).
```

## Prompt 4 — H0.4: Repair CI (G04, G05, G07)

```
PREAMBLE

GOAL: Make .github/workflows/ci.yml actually able to run. It currently cannot.

CONTEXT — three defects, all verified:
1. ci.yml:24 runs `pip install -r requirements.lock.txt` from the repository root.
   That file does not exist at root; the real lock is release/requirements.lock.txt
   (164 KB, 96 pinned packages).
2. ci.yml:35 passes `--cov=server --cov=connectors --cov-fail-under=80`, but
   pytest-cov is NOT declared in requirements-dev.txt. On a clean runner pytest exits
   with "unrecognized arguments: --cov".
3. ci.yml:29/32 lint and type-check only `server/ connectors/ control_plane/`. The
   P0 security findings live in engines/ — which CI never inspects.

CHANGES:
1. .github/workflows/ci.yml:
   - install from `release/requirements.lock.txt`
   - extend the ruff and mypy steps to include: engines/ capabilities/ security/
     pilot/ (add these to the existing paths; keep server/ connectors/ control_plane/)
   - keep the coverage flags (see change 2)
2. requirements-dev.txt: add `pytest-cov>=4.1` under the Test section.
3. Verify scripts/check_dependencies.py (referenced at ci.yml's "Check dependencies"
   step) exists and runs: .venv-py312\Scripts\python.exe scripts/check_dependencies.py
   If it fails, fix the MINIMAL thing that makes it pass and report what you changed.

CONSTRAINTS:
- Do NOT lower --cov-fail-under below 80 and do NOT remove the coverage flags to make
  CI green. If real coverage is below 80, report the actual number and leave the gate
  failing — that is a real signal, not noise to silence.
- Do not add engines/ to mypy if it produces a flood of errors: report the count first
  and leave mypy scoped as-is for this step; ruff coverage is the priority.
- Do not reformat ci.yml beyond what these changes require.

VERIFY (run the CI steps LOCALLY, in order, and paste results):
  .venv-py312\Scripts\ruff.exe check server/ connectors/ control_plane/ engines/ capabilities/ security/ pilot/
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" --cov=server --cov=connectors --cov-fail-under=80 2>&1 | tail -12
Report the measured coverage percentage.

COMMIT: chore(ci): fix lockfile path, declare pytest-cov, widen lint scope to engines/capabilities/security
Then update AGENTS.md §0.4 (check H0.4).
```

## Prompt 5 — H0.5: Vulnerability + dependency scanning (G06)

```
PREAMBLE

GOAL: Make SECURITY.md's claims true. It mandates bandit, safety, and Dependabot.
None of the three is configured anywhere in the repo.

CHANGES:
1. requirements-dev.txt — add under a new "Security" section:
   `bandit>=1.7` and `pip-audit>=2.6`
2. .github/workflows/ci.yml — add a `security` step (or job) that runs:
   - `bandit -r server/ connectors/ control_plane/ engines/ capabilities/ security/ -ll`
     (-ll = report medium severity and above, fail on findings)
   - `pip-audit -r release/requirements.lock.txt`
   Do not let it fail the build yet if it produces a flood: make it `continue-on-error:
   true` ONLY for pip-audit on the first run, and report the finding count. bandit -ll
   must be blocking.
3. New file .github/dependabot.yml — weekly updates for pip (root) and github-actions.

CONSTRAINTS:
- Do not suppress bandit findings with `# nosec` to make it pass. If a finding is a
  genuine false positive, add it to a `bandit` skip list in pyproject.toml with a
  one-line justification, and report it.
- Report EVERY bandit finding (file:line, severity, testid) even if you fix it.

VERIFY:
  .venv-py312\Scripts\python.exe -m pip install bandit pip-audit
  .venv-py312\Scripts\python.exe -m bandit -r server/ connectors/ control_plane/ engines/ capabilities/ security/ -ll
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -3

COMMIT: chore(ci): add bandit + pip-audit scanning and dependabot
Then update AGENTS.md §0.4 (check H0.5).
```

## Prompt 6 — H0.6: Release manifest + worktree cleanup (G09, G10)

```
PREAMBLE

GOAL: Make the release manifest describe the current tree, and close 5 dead worktrees.

CONTEXT:
1. release/release-manifest.json is MODIFIED but uncommitted, and its "git_commit" is
   7b1bda0 — three commits behind HEAD (c3c4abf). The committed manifest describes a
   tree that no longer exists.
2. Five git worktrees are checked out inside .claude/worktrees/. Verified with
   `git merge-base --is-ancestor`: worktree-phase1-constitution-fix,
   worktree-phase1-smoke-fix, worktree-phase1-w5-w6 and phase2/super-app are ALL
   ancestors of main — fully integrated, zero work at risk.
   worktree-desktop-app has 1 unique commit (adds desktop.py), BUT desktop.py already
   exists on main via commit 1dd6eb0.

CHANGES:
1. Regenerate the manifest with the correct HEAD. Prefer the repo's own generator
   (release/manifest.py build_manifest) over hand-editing JSON. Run it, then confirm
   the new file's git_commit == current HEAD (git rev-parse HEAD).
   Also fix: pyproject.toml:19 says `license = "See LICENSE — none committed yet"`
   though LICENSE.md exists at root — correct that claim.
2. Before deleting anything, PROVE worktree-desktop-app is redundant:
   git diff main worktree-desktop-app -- desktop.py
   If the diff is empty (or main's version is a superset), proceed. If the worktree has
   changes main lacks, STOP and report — do not delete.

VERIFY (before deleting, print and inspect):
  git worktree list
  git diff main worktree-desktop-app -- desktop.py
Only if safe:
  git worktree remove .claude/worktrees/desktop-app
  git worktree remove .claude/worktrees/phase1-constitution-fix
  git worktree remove .claude/worktrees/phase1-smoke-fix
  git worktree remove .claude/worktrees/phase1-w5-w6
  git worktree remove .claude/worktrees/phase2-collaboration
  git branch -d worktree-desktop-app worktree-phase1-constitution-fix worktree-phase1-smoke-fix worktree-phase1-w5-w6 phase2/super-app
If any `branch -d` refuses (unmerged), STOP and report — do NOT use -D.

VERIFY after:
  git worktree list        (should show only the main checkout)
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -3

COMMIT: chore(repo): regenerate release manifest at HEAD, close 5 integrated worktrees, fix license claim
Then update AGENTS.md §0.4 (check H0.6).
```

---

# PHASE P1 — Make the governance claims true

## Prompt 7 — H1.1: Silent degradation → fail closed (G11–G13)

```
PREAMBLE

GOAL: Remove every path where a governance control silently disables itself.

CONTEXT — the product claims fail-closed, but four paths fail OPEN. Verified:
- control_plane/engine.py:137-138
    `if AuditTrail is None or AuditRecord is None: return`
  The audit record is silently skipped. Docstring on :136 even says "best-effort".
- control_plane/engine.py:235
    `if validate_no_secrets:` — the secret scan is skipped when the validator is
    unavailable. The comment on :234 claims "fail-closed". It is not.
- control_plane/engine.py:346-347
    `except Exception: pass` — injection-detection failure is swallowed and execution
    continues to the authorization request below.
- control_plane/engine.py:19-36
    The entire C3 security stack (classification, identity, authorize, secrets, audit,
    injection) is imported in a try/except ImportError and set to None.

CHANGES (file: control_plane/engine.py):
1. Define a typed error, e.g. `class GovernanceControlUnavailable(RuntimeError)`, in
   control_plane/engine.py (or control_plane/errors.py if that module exists — prefer
   the existing location if one does).
2. Replace each silent path: when a required control is unavailable, RAISE
   GovernanceControlUnavailable with the control name. Do not return, do not pass.
3. At module import: if the C3 stack cannot be imported, fail loudly at engine
   construction time rather than degrading per-call. Constructor raises; no partial engine.
4. Add tests (tests/test_governance_fail_closed.py):
   - audit unavailable -> raises (monkeypatch AuditTrail to None)
   - secret validator unavailable -> raises
   - injection detector raises -> propagates (does NOT continue to authorize)
   - one test asserting no `except Exception: pass` and no `except KeyError: pass`
     remains in engine.py (read the source with ast and assert)

CONSTRAINTS:
- Do not change any control's behaviour when it IS available — only when it is not.
- Do not edit security/ modules.
- Expect existing tests that relied on the degraded path to fail: fix them by making
  the control available, never by reintroducing the silent pass.

VERIFY:
  .venv-py312\Scripts\ruff.exe check control_plane/engine.py tests/test_governance_fail_closed.py
  .venv-py312\Scripts\python.exe -m pytest tests/test_governance_fail_closed.py -q
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -5

COMMIT: fix(gov): fail closed when governance controls are unavailable (was silently skipped)
Then update AGENTS.md §0.4 (check H1.1).
```

## Prompt 8 — H1.2: Separation-of-duties integrity (G14, G15)

```
PREAMBLE

GOAL: Close a SOD bypass and remove hardcoded super-roles from the engine.

CONTEXT — verified:
- control_plane/engine.py:687-688:
    `except KeyError: pass  # if catalog lookup fails, allow but log`
  A missing catalog lookup means the segregation-of-duties check is skipped and the
  approval proceeds. The comment claims it logs; there is no logging statement.
- control_plane/engine.py:680 and :683:
    `allowed_approvers = set(must_review) | {"sami", "compliance_quality_gm"}`
    `if approval.approver_role_id not in ("sami", "compliance_quality_gm"):`
  Two role ids are hardcoded in the engine instead of being declared in the role catalog.

CHANGES:
1. engine.py:687-688 — on KeyError/catalog miss: DENY (raise) and log with the role id
   and workflow id. "Cannot verify authority" must never mean "allow".
2. engine.py:680/683 — move the super-role set out of the engine. Add a declared field
   to the role catalog (e.g. a `can_approve_any` flag or an explicit
   `universal_approvers` list) and read it from there.
   *** This requires editing organization/role-catalog.yaml — you are EXPLICITLY
   authorized for this change only. Add the minimum field needed, and add a mirror-drift
   test if the catalog has mirrors (check organization/ and contracts/ for mirrors).
3. Add tests (tests/test_sod_integrity.py):
   - unknown approver role -> denied (was: silently allowed)
   - unknown owning role -> denied
   - an AST test asserting the literals "sami" and "compliance_quality_gm" do NOT
     appear in control_plane/engine.py
   - super-role authority now comes from the catalog: removing it from the catalog
     removes the authority (test with a temp catalog if the loader allows)

CONSTRAINTS:
- Do not grant any role more authority than it has today — this is a refactor to a
  declared source, not a permission change.
- Do not edit control_plane/governance.py's ORGANIZATION_CATALOG.

VERIFY:
  .venv-py312\Scripts\ruff.exe check control_plane/engine.py tests/test_sod_integrity.py
  .venv-py312\Scripts\python.exe -m pytest tests/test_sod_integrity.py -q
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -5
  grep -n "sami\|compliance_quality_gm" control_plane/engine.py   (must return nothing)

COMMIT: fix(gov): deny on unverifiable SOD lookup, move super-roles to role catalog
Then update AGENTS.md §0.4 (check H1.2).
```

## Prompt 9 — H1.3: Registry drift must be able to fail (G16)

```
PREAMBLE

GOAL: Make catalog drift detectable in CI. Today it can never fail.

CONTEXT — verified:
- control_plane/governance.py:418 `detect_catalog_drift()` docstring (lines 422-423)
  claims it covers "capabilities, tools, peer calls and segregation-of-duties".
  The body compares exactly ONE field: `max_financial_amount` (two comparisons).
- tests/test_c1_contracts.py:1099-1105 `test_catalog_drift_detector_reports_without_raising`
  asserts only that the return value is a list and that entries have certain keys.
  It never asserts the list is empty — so drift exists, is detected, and CI stays green.

CHANGES:
1. control_plane/governance.py:418 — extend detect_catalog_drift() to actually compare
   all four declared dimensions between the YAML catalog and the Python runtime catalog:
   capabilities, tools, peer calls, segregation-of-duties (in addition to
   max_financial_amount). Keep the existing entry shape
   {role_id, field, runtime, yaml, detail} — other code depends on it.
2. tests/test_c1_contracts.py — change the drift test so it FAILS on real drift:
   assert the returned list is EMPTY (or assert on specific known-good roles). If genuine
   drift exists right now, do not hide it: report every drifted field in your summary and
   decide per case whether the YAML or the Python is canonical (YAML is source of truth).
3. Add a regression test that injects drift into a temp catalog copy and asserts
   detect_catalog_drift() reports it — proving the detector still works after your change.

CONSTRAINTS:
- YAML is the source of truth. Fix the Python side, not the YAML, unless the YAML is
  demonstrably wrong — then report it and ask.
- Do not edit organization/role-catalog.yaml in this step.
- Do not change ORGANIZATION_CATALOG's semantics.

VERIFY:
  .venv-py312\Scripts\ruff.exe check control_plane/governance.py
  .venv-py312\Scripts\python.exe -m pytest tests/test_c1_contracts.py -q -k drift
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -5

COMMIT: test(gov): make catalog drift able to fail CI; extend detector to all 4 declared dimensions
Then update AGENTS.md §0.4 (check H1.3).
```

## Prompt 10 — H1.4: Tenant isolation — ⛔ BLOCKED, ASK THE USER FIRST

```
PREAMBLE

GOAL: Resolve control_plane/tenancy.py. DO NOT IMPLEMENT — this is a product decision.

CONTEXT — verified:
- control_plane/tenancy.py is 12 KB implementing TenantContext, TenantScopedStore,
  TenantViolation, ensure_tenant_indexes, verify_isolation, partition_key.
- It has ZERO references anywhere outside its own module and ZERO tests. It is dead.
- Yet 00_CONSTITUTION.md declares tenant/client isolation as a governing clause, and
  GOVERNANCE/IMPLEMENTATION_MATRIX.md attributes tenant isolation to security/policy.py
  instead — tenancy.py is not mentioned.
- security/policy.py::authorize DOES enforce tenant/client isolation at the policy layer
  (checks identity tenant/client against target).

TASK: Do NOT write code. Produce a decision brief, under 300 words, with:
  A) What it would take to wire tenancy.py into control_plane/engine.py — which call
     sites, roughly how many, and what breaks.
  B) What deleting it would require (amend 00_CONSTITUTION.md? the matrix?).
  C) Your recommendation, with the one sentence that justifies it.
Then STOP and wait for the user's decision. No commit.
```

## Prompt 11 — H1.5: Kill switch (G18) ⏭ run next if 10 is blocked

```
PREAMBLE

GOAL: Add an emergency stop. There is none anywhere in the repo (verified: no
kill_switch / killswitch / circuit_breaker symbol exists).

CONTEXT: A platform whose entire value proposition is "provable restraint" has no way to
halt itself. This is a standard enterprise objection and a governance gap.

CHANGES:
1. Add a halt mechanism to control_plane — a module-level, persisted flag (reuse the
   existing store/audit pattern; do not add Redis or any new dependency) with:
   - `engage(reason, actor)` / `release(actor)` / `is_engaged()`
   - optional tenant scoping: halt one tenant without halting all (the platform is
     multi-tenant by design — see security/identity.py tenant_id)
2. control_plane/engine.py — check the flag BEFORE every committal action (the same
   seam where approval is required). When engaged: deny, write an audit record, and
   raise. The audit write must still succeed while halted (the halt itself must be
   auditable) — think about this and get it right.
3. Expose it: an HTTP route on server/app.py (protected by the auth dependency you added
   in Prompt 3, and restricted to a privileged role), plus a CLI entry in scripts/.
4. Tests (tests/test_kill_switch.py):
   - engaged -> committal action denied and audited
   - engaged -> read-only actions still allowed
   - release -> committal allowed again
   - tenant-scoped halt does not affect other tenants
   - the halt engagement itself is auditable

CONSTRAINTS:
- Do not add dependencies.
- The kill switch must fail CLOSED: if the flag cannot be read, treat it as engaged.

VERIFY:
  .venv-py312\Scripts\ruff.exe check control_plane/ server/ scripts/ tests/test_kill_switch.py
  .venv-py312\Scripts\python.exe -m pytest tests/test_kill_switch.py -q
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -5

COMMIT: feat(gov): add fail-closed kill switch honoured before committal actions
Then update AGENTS.md §0.4 (check H1.5).
```

## Prompt 12 — H1.6: Evidence integrity + readiness enforcement (G19, G20)

```
PREAMBLE

GOAL: Wire the audit-integrity gate, and enforce production_readiness centrally.

CONTEXT — verified:
- release/security_gate.py:160 `check_audit_integrity` exists but is NEVER called from
  anywhere. The one gate that would verify the hash chain at release time is dead.
- scripts/export_evidence_pack.py ALREADY EXISTS and is a read-only evidence exporter.
  DO NOT write a new CLI.
- `production_readiness` is hardcoded per pack (capabilities/restaurant/register.py:25,
  capabilities/sports_academy/register.py:25, and their runtimes). Nothing enforces that
  a NEW pack declares it — a future pack can silently omit it.
- .gitignore:61-63 excludes evidence/* (except README), so evidence artifacts are not
  reproducible from the repo.

CHANGES:
1. release/gate.py — invoke check_audit_integrity as a core gate (it is currently
   orphaned). It must FAIL the gate run when the chain is broken, not warn.
2. Add a registry-level test (tests/test_pack_readiness_contract.py): for every
   registered capability pack, assert that metadata declares `production_readiness`
   and that its value is one of the allowed set (see AGENTS.md: "NOT_ESTABLISHED").
   Enumerate packs from the registration mechanism rather than hardcoding a list.
3. Verify the evidence exporter still runs:
   .venv-py312\Scripts\python.exe scripts/export_evidence_pack.py --help
   and report its integrity field. Do not modify it unless it is broken.

CONSTRAINTS:
- Do NOT create a new evidence CLI — scripts/export_evidence_pack.py is the one.
- Do not change .gitignore in this step (evidence reproducibility is tracked separately);
  just report whether evidence packs should be committed or regenerated.

VERIFY:
  .venv-py312\Scripts\ruff.exe check release/gate.py tests/test_pack_readiness_contract.py
  .venv-py312\Scripts\python.exe -m pytest tests/test_pack_readiness_contract.py -q
  .venv-py312\Scripts\python.exe -m pytest tests/ -q -m "not smoke" 2>&1 | tail -5
  .venv-py312\Scripts\python.exe -m release.gate   (or the documented entrypoint) — report result

COMMIT: fix(gov): wire audit-integrity into release gate, enforce production_readiness at registry level
Then update AGENTS.md §0.4 (check H1.6).
```

---

# PHASE P2 — Make it operable

## Prompt 13 — H2.1: Database migrations (G21)

```
PREAMBLE

GOAL: Introduce schema migrations. There are none — schema is implicit in
control_plane/store.py and applied by hand.

Add alembic, create migrations/ with an initial migration that reproduces the CURRENT
schema exactly (do not change the schema), and a CI check that fails when the models and
the migration head disagree. Add `alembic>=1.13` to requirements.txt.

CONSTRAINTS:
- The initial migration must be a no-op on an existing database. Verify by running
  `alembic upgrade head` against a copy of an existing DB and diffing the schema before
  and after — they must be identical.
- Do not change any schema in this step. Schema changes are a separate decision.
- Tests must not require a live migration run; keep them fast.

VERIFY: full suite >= 571; ruff clean; `alembic upgrade head` on a fresh DB succeeds.
COMMIT: feat(infra): add alembic migrations and CI drift check
Then update AGENTS.md §0.4 (check H2.1).
```

## Prompt 14 — H2.2: Monitoring and alerting (G22)

```
PREAMBLE

GOAL: Add the observability that does not exist: no Prometheus, Grafana, Sentry, or
OpenTelemetry anywhere in the repo.

Add a /metrics endpoint (Prometheus text format or OTel) covering: request count/latency
by route, approval-queue depth, denied-vs-allowed governance decisions, audit-chain
verification failures. Wire structured logging with a correlation id (reuse the existing
CORRELATION_HEADER convention in server/app.py). Add alert rules as config files, not prose.

CONSTRAINTS:
- Do not log secrets, tokens, or PII. Reuse security/secrets.py redaction helpers.
- /metrics must be excluded from the auth dependency ONLY if it exposes no sensitive
  data — prefer protecting it and documenting why.
- Do not add Sentry without a DSN env var that defaults to disabled.

VERIFY: full suite >= 571; ruff clean; curl /metrics after starting the server locally.
COMMIT: feat(obs): add /metrics, correlation-id logging, and alert rules
Then update AGENTS.md §0.4 (check H2.2).
```

## Prompt 15 — H2.3: One deployable artifact (G23, G24, G25)

```
PREAMBLE

GOAL: Declare ONE canonical entry point. Today there are three, none declared:
launch.py/launch.bat (Streamlit :8501), desktop.py (pywebview + uvicorn :8080), and
infra/docker/docker-compose.yml (uvicorn :8000 + :8501 + ollama).

1. pyproject.toml: add [project.scripts] with the canonical console script(s).
2. Align [tool.hatch.build.targets.sdist] include with the wheel package list — the sdist
   currently OMITS server, capabilities, pilot, security, customer_success, metacognition.
3. README.md: state which artifact is canonical and how to run it; explicitly label the
   others as secondary/legacy. Do not delete any entry point in this step.
4. Report your recommendation for which artifact SHOULD be canonical and why — do not
   decide silently.

VERIFY: `python -m build` produces both sdist and wheel; install the wheel in a temp venv
and run the console script; full suite >= 571.
COMMIT: chore(pkg): declare console scripts, align sdist/wheel includes
Then update AGENTS.md §0.4 (check H2.3).
```

## Prompt 16 — H2.4 + H2.5: CI quality, retention policy, version (G26–G30)

```
PREAMBLE

GOAL: Five small correctness fixes.
1. (G27) Delete .github/workflows/python-app.yml — it duplicates ci.yml (same trigger,
   same pytest) and both run on every push. Confirm ci.yml covers everything it did first.
2. (G28) Add `ruff format --check .` to CI (pre-commit already runs ruff-format repo-wide
   but CI never checks it — run `ruff format .` first if needed, as its own commit).
   Widen [tool.ruff] select to add I (import sorting), B (bugbear), S (bandit) — report
   the finding count; do not fix findings beyond the trivial ones in this step.
3. (G29) Report how many mypy errors appear if you remove each of the 8 disabled error
   codes in pyproject.toml. Do not remove them yet.
4. (G26) Write docs/operations/data-retention.md documenting what
   memory/governed_memory.py:415 apply_retention() does (it FLAGS, never deletes) and the
   retention period per record class. Wire apply_retention to a scheduled job ONLY if a
   scheduler already exists; otherwise report that it is manual today.
5. (G30) Single-source the version: release/manifest.py:108 hardcodes "0.9.0-c8".
   Make it read from pyproject.toml (or a single shared constant).

VERIFY: full suite >= 571; ruff clean on touched paths; `ruff format --check .` clean.
COMMIT: one commit per numbered item (5 commits).
Then update AGENTS.md §0.4 (check H2.4, H2.5).
```

---

# PHASE P3 — Make it sellable

## Prompt 17 — H3.1: Single authority chain (G31, G39)

```
PREAMBLE

GOAL: End the 7-doc authority conflict. Today MASTER_STORY.md, ROADMAP.md,
docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md, docs/HELIX_CODEX_EXECUTION_STATUS.md,
docs/HELIX_CODEX_UPGRADE_PLAN.md, docs/PHASE1_BASELINE.md and docs/GAP_ANALYSIS.md all
restate implementation status, and MASTER_STORY.md / ROADMAP.md cross-delegate authority.

CHANGES:
1. Declare the chain: 00_CONSTITUTION.md (authority) ->
   docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md (architecture + commercial record) ->
   implementation. Put this declaration at the top of README.md and in AGENTS.md.
2. Move to docs/archive/ (do NOT delete): docs/GAP_ANALYSIS.md (its own header says
   "ALL GAPS RESOLVED") and docs/HELIX_CODEX_UPGRADE_PLAN.md (marked "Proposed").
3. Delete docs/archive/MAP_B2B.md, MAP_CX.md, MAP_RTA.md, MAP_WFM.md — all four share
   five identical headings with docs/archive/PROJECT_MAP.md, which is the superset.
   Verify they are strict subsets BEFORE deleting; if any has unique content, keep it.
4. Merge GOVERNANCE/CHANGE_LOG.md into CHANGELOG.md (or vice versa — pick user-facing
   CHANGELOG.md as canonical) and GOVERNANCE/wayfinder/map.md into
   GOVERNANCE/WORKSPACE_MAP.md. Leave a pointer, not duplicate content.
5. Add a stale-fact test if cheap: assert no tracked .md outside docs/archive/ contains
   a stale test-count claim. Optional — report if you skip it.

VERIFY: no broken relative markdown links anywhere (crawl every ](...) in tracked .md and
assert the target exists); full suite >= 571.
COMMIT: docs: establish single authority chain, archive superseded status docs
Then update AGENTS.md §0.4 (check H3.1).
```

## Prompt 18 — H3.2: Correct the stale facts (G32–G35)

```
PREAMBLE

GOAL: Four documented facts are wrong. Fix exactly these, no rewriting.
1. GOVERNANCE/IMPLEMENTATION_MATRIX.md:198 and :235 say "445 tests" / "Test suite: 445
   tests pass". Actual collection is 571. Update both, and add the date + commit.
2. docs/PRODUCT_DEFINITION.md:11 says "four AI agents (SAMI, SUBY, PHILI, WILI)".
   docs/ENGINEERING_SPECIFICATION.md has a "The nine agents" heading and CHANGELOG
   records the change to 9. Update PRODUCT_DEFINITION.md to match reality — verify the
   real count first (check the agent registry, do not assume nine).
3. docs/PHASE1_BASELINE.md:9 records the baseline environment as Python 3.10.11 with
   13 failing tests. pyproject.toml:19 requires >=3.12,<3.13. Re-baseline it or mark it
   explicitly as a historical 2026-08 record that no longer applies.
4. pyproject.toml:19 says `license = "See LICENSE — none committed yet"` while
   LICENSE.md exists at root. Correct it and set the real license identifier.

CONSTRAINTS: Do not rewrite any of these documents. Minimal, factual edits only.
VERIFY: grep for "445" and "four AI agents" across tracked .md — must be gone except in
archive/. Full suite >= 571.
COMMIT: docs: correct stale test count, agent count, python baseline, license claim
Then update AGENTS.md §0.4 (check H3.2).
```

## Prompt 19 — H3.3 + H3.4: Security docs, changelog, hygiene (G36–G38, G40, G41)

```
PREAMBLE

GOAL: Make the security documentation honest and current.
1. (G36) SECURITY.md:23 currently states that its own contact address "was fabricated
   and is void". Replace with a real contact or a role alias (e.g. security@<your-domain>)
   and remove the self-contradicting sentence. Also correct SECURITY.md:41-43: it claims
   bandit, safety and Dependabot are in use — after Prompt 5 bandit + pip-audit +
   dependabot ARE real, so update the wording to match exactly what CI runs.
2. (G37) docs/C3-threat-model.md (last touched 2026-08-27) predates engines/rta and
   server/ — the two services with the P0 findings. Extend the threat model to cover
   both, and record the review date.
3. (G38) CHANGELOG.md: last entry is 2026-09-10?? No — last entry is 2026-08-29 and the
   entire sports-academy pack (commits d5dcb45..c3c4abf, 44 tests, 2026-09-10) is
   undocumented. Add it. Also note the version sequence regressed 2.1.0 -> 0.9.0-c8,
   violating the SemVer claim in the file's own header — add a note explaining the
   renumbering rather than hiding it.
4. (G40) Move marketing/assets/fonts/*.ttf (3 files, ~1.8 MB) to Git LFS, or vendor them
   at build time. Report which you chose and why.
5. (G41) Rename overview.md — it is not a repo overview, it is the Scoach client report
   summary. Use `git mv` and update every inbound link.

VERIFY: no broken relative links; full suite >= 571; `git status` clean of stray binaries.
COMMIT: one commit per numbered item (5 commits).
Then update AGENTS.md §0.4 (check H3.3, H3.4) and mark the program complete in §1.
```

---

## After the last prompt

Run the audit again from the top (re-verify each of the 41 gaps), then update
`docs/audits/2026-09-10_full_audit_production_plan.md` with a "post-fix verification"
section, and set `AGENTS.md` §1 `Current step` to the next program.

**Hard rule carried from the audit:** the Scoach pilot (H4) must not start until H0 is
complete. No real academy data behind an unauthenticated endpoint.

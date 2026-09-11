# Helix-Prime — Full Repository Audit & Production Plan

**Date:** 2026-09-10 · **HEAD:** `c3c4abf` (main) · **Scope:** read-only audit, no code changed
**Auditor:** AI agent (WorkBuddy) · **Method:** static analysis + targeted verification of every headline claim

> **Verdict up front:** the *engineering* is better than the *packaging*. The governed
> core (approval gating, SOD, hash-chained memory, fail-closed release gates) is real and
> tested. What blocks production is a security surface that was never hardened, a CI
> pipeline that cannot pass, and a documentation layer with 7 competing "source of truth"
> files. None of the blockers are architectural — all are fixable in 3–5 focused weeks.

---

## 0. Executive summary

| Domain | Grade | Headline |
|---|---|---|
| Code / governed core | **B+** | 571 tests, hash-chained memory, real SOD, fail-closed release gates |
| Security | **D** | Zero auth anywhere; Flask debug+RCE; wildcard CORS; no scanning |
| Governance enforcement | **C+** | Good primitives, but silent-fallback paths contradict "fail-closed" |
| Testing & CI | **C** | 571 tests pass locally; **CI cannot run at all** (2 hard blockers) |
| Documentation | **D+** | 7 competing authority docs; stale counts; 2 changelogs |
| Repo hygiene | **B** | Clean gitignore, no secrets ever committed; 5 dead worktrees |
| Production readiness | **F (by design)** | All 9 production gates correctly hard-fail — accurate, not a bug |

**Count of gaps: 41** — 10 blockers, 14 high, 12 medium, 5 low. Full register in §IV.

### The five things that actually stop a launch

1. **Nothing is authenticated.** `server/app.py` (8 routers incl. `/api/approvals`,
   `/api/chat`), `engines/rta/src/app.py` (9 routes), and the 82 KB Streamlit cockpit all
   accept anonymous requests. Unauthenticated approval endpoints are a governance
   product's worst look.
2. **`engines/rta/src/app.py:269` — `app.run(host="0.0.0.0", port=5000, debug=True)`**
   plus `CORS(app)` at `:32`. Werkzeug debug console on all interfaces = remote code
   execution. The debug PIN is not an auth boundary.
3. **CI is dead.** `.github/workflows/ci.yml:24` installs `requirements.lock.txt` from the
   repo root (file is at `release/requirements.lock.txt`), and `:35` passes `--cov` while
   `pytest-cov` is undeclared. Every push to main has been running a pipeline that fails
   at install.
4. **The governance core silently degrades.** `control_plane/engine.py:137` returns early
   when the audit trail is unavailable (comment says "best-effort"), `:687` swallows
   `except KeyError: pass` on a *segregation-of-duties* lookup with a comment claiming it
   logs (it does not), `:346-347` swallows injection-detection failures. The product
   claims fail-closed; these paths fail open.
5. **Constitutional enforcement is three substring checks.** `GOVERNANCE/governance_check.py:17-21`
   asserts that three sentences still exist in `00_CONSTITUTION.md`. Deleting any of the
   five numbered rules passes. Tenant isolation — a constitutional clause — is enforced by
   `control_plane/tenancy.py`, which has **zero references outside its own module and zero
   tests**: 12 KB of dead code.

---

# PART I — SWE AUDIT

## 1. Architecture & structure

### What works

- **Layering is genuinely clean.** `capabilities/sports_academy/` is textbook
  feature-first: `ontology → contracts → adapters → workflows → kpis → runtime → cockpit_views`,
  with YAML declarations mirrored by Python and drift-tested. The restaurant pack set the
  pattern; the academy pack followed it exactly. That discipline is real.
- **Pure-function separation is consistent.** Every adapter exposes a pure `compute_*`
  and a governed `record_*`. The cockpit views (`capabilities/sports_academy/cockpit_views/`)
  import no Streamlit — they are reusable by the future HTMX console as designed.
- **Engine reuse is genuine, not claimed.** Attendance → `engines.rta.adapter.adapt`;
  churn → `engines.cx.churn_risk_scoring`. No new capabilities were registered.

### Structural gaps

| # | Gap | Evidence | Fix |
|---|---|---|---|
| S-1 | **Three competing deployable artifacts, none declared** | `launch.py`/`launch.bat` → Streamlit `:8501`; `desktop.py` → pywebview + uvicorn `:8080`; `infra/docker/docker-compose.yml` → uvicorn `:8000` + `:8501` + ollama | Declare ONE canonical entry point in `pyproject.toml [project.scripts]`. Subordinate the rest explicitly in README. |
| S-2 | **No `[project.scripts]` entry point** | `pyproject.toml` has none | Add `helix-cockpit`, `helix-api` console scripts |
| S-3 | **sdist ≠ wheel package list** | `[tool.hatch.build.targets.wheel]` lists 18 packages incl. `server`; **sdist `include` omits `server`, `capabilities`, `pilot`, `security`, `customer_success`, `metacognition`** | Make sdist include list match the wheel |
| S-4 | **No DB migrations** | No alembic, no `migrations/`; schema implicit in `control_plane/store.py` | Introduce Alembic; first migration = current schema; CI checks no drift |
| S-5 | **`app/` is nearly empty** (only `command_center/`) | 6 `.py` files | Either fold into `server/features/` or document as legacy |
| S-6 | **Pack registration goes into a module-global dict, not the canonical registry** | `capabilities/sports_academy/register.py:15` `REGISTRY: dict = {}` | Decision needed: keep pack-local (document it) or integrate with `organization/capability-registry.yaml` |
| S-7 | **`production_readiness` is a per-pack convention, not enforced** | hardcoded in `capabilities/*/register.py:25`; no registry check | Add a registry-level assertion test: every registered pack must declare `production_readiness` |

### Dead code (verified: zero external references)

| Location | Symbol | Note |
|---|---|---|
| `control_plane/tenancy.py` (entire 12 KB) | `TenantContext`, `TenantScopedStore`, `verify_isolation`, … | **Constitutional clause with no runtime path** |
| `control_plane/governance.py:167` | `RoleSpec.can_read` | classification read-gate never called |
| `organization/role_catalog.py:302,308` | `is_peer_call_allowed`, `requires_compliance_review` | SOD helpers never called |
| `release/security_gate.py:160` | `check_audit_integrity` | **the release gate that verifies the hash chain is never invoked** |
| `security/classification.py:130` | `classify_for_tenant_client` | — |
| `observability/health.py:52,66,79` | `check_capability_registry`, `check_role_catalog`, `check_event_replay` | health checks defined but never wired |
| `connectors/policy.py:21` | `get_risk_tier` | — |

## 2. Security

### Good (credit where due)

- **No secret has ever been committed.** `git log --all -- .env` is empty. `.gitignore`
  correctly covers `.env`, `*.db`, `*.sqlite`, `*.pyc`, `evidence/*`, `.venv*/`.
- `security/secrets.py:117-134` `get_secret()` reads env only and **fails closed**.
- Redaction covers API keys, bearer tokens, passwords, cookies, emails, SSN, phone
  (`security/secrets.py:36-43`).
- **Zero** `eval`/`exec`/`pickle.loads`/`shell=True`/`os.system`/`verify=False` repo-wide.
- **SQL is parameterised** throughout `control_plane/store.py`. The one f-string in
  `cockpit/memory/cognitive_log.py:164` uses hardcoded literals — not injectable.
- No unsafe `yaml.load` anywhere.
- **No PII.** All fixtures are explicitly synthetic (`DATA_MODE = "simulated_realistic"`,
  `parent{i}@example.com`, `+1-555-01{i}`).

### Blockers

| # | Finding | Location | Fix |
|---|---|---|---|
| **B1** | Flask debug on 0.0.0.0 → **RCE** | `engines/rta/src/app.py:269` | `debug=False`, bind `127.0.0.1`, drive via WSGI/gunicorn |
| **B2** | **Zero authentication** on any surface | `server/app.py:102-109`, `engines/rta/src/app.py`, `cockpit/cockpit.py` | Auth middleware + RBAC from the existing role catalog |
| **B3** | Wildcard CORS | `engines/rta/src/app.py:32` `CORS(app)` | Explicit origins (mirror `server/config.py:55-56`, which does this right) |
| **B4** | `host = "0.0.0.0"` default | `server/config.py:52` | Default `127.0.0.1`; require env opt-in for container |
| **B5** | No dependency/vuln scanning despite `SECURITY.md` mandating it | `SECURITY.md:41-43` claims bandit + safety + Dependabot — **none configured** | Add `pip-audit` + `bandit` to CI, add `.github/dependabot.yml` |
| — | CI never lints/tests `engines/`, `capabilities/`, `security/` | `ci.yml:29,32,36` | Extend scope — B1–B3 live in `engines/` |

### Security documentation

| File | Size | Last mod | Status |
|---|---|---|---|
| `SECURITY.md` | 5.9 KB | 2026-08-27 | **Stale** — predates both capability packs and the RTA service |
| `docs/C3-threat-model.md` | 9.3 KB | 2026-08-27 | **Stale** — 14 days behind active code |
| `docs/operations/C3-security-runbook.md` | 7.4 KB | 2026-08-27 | **Stale** |
| `docs/release/incident-response.md` | 2.1 KB | 2026-08-28 | Thinnest doc; needs contact + severity SLA |
| `docs/portfolio/04_security_model.md` | 2.2 KB | 2026-08-29 | Investor-facing; must not contradict SECURITY.md |
| `GOVERNANCE/IMPLEMENTATION_MATRIX.md` | 65 KB | 2026-09-07 | **Stale fact**: line 235 says "445 tests pass"; actual 571 |

- **Doc-01:** `SECURITY.md:23` states its own contact address "was fabricated and is
  void." A published security policy admitting fake contact details is a credibility
  problem in enterprise due diligence. Replace with real (or role-alias) contacts.
- **Doc-02:** Threat model must be extended to cover `engines/rta` + `server/` (currently
  unmodelled) and re-dated at every release.
- **Doc-03:** No data-retention policy exists anywhere, though
  `memory/governed_memory.py:415 apply_retention()` implements flagging. Document it.

## 3. Governance

### Enforcement primitives

| Primitive | Exists | Tested | Live in runtime |
|---|---|---|---|
| Approval queue | ✅ | ✅ `test_c1_contracts.py:1263` | ✅ |
| Separation of duties | ✅ | ✅ | ⚠️ see G-2 |
| Policy engine (`security/policy.py`) | ✅ | ✅ | ✅ `engine.py:357` |
| Hash-chained audit | ✅ | ✅ incl. tamper test | ✅ |
| Capability registry + drift test | ✅ | ⚠️ see G-3 | partial |
| Role catalog | ✅ | ✅ | ✅ |
| Rate limiting | ⚠️ connectors only | — | not governance-grade |
| **Kill switch / circuit breaker** | ❌ **absent** | — | — |
| Tenant isolation | ❌ **dead module** | ❌ | ❌ |

### Gaps

- **G-1 — Silent degradation contradicts "fail-closed"** (highest governance risk):
  - `engine.py:137-138`: `if AuditTrail is None or AuditRecord is None: return` — audit
    silently skipped.
  - `engine.py:235`: secret scan skipped when validator unavailable (comment says
    "fail-closed").
  - `engine.py:346-347`: `except Exception: pass` swallows injection-detection failure.
  - `engine.py:687-688`: `except KeyError: pass  # if catalog lookup fails, allow but log`
    — **SOD bypassed on catalog miss, and it does not log despite the comment.**
  **Fix:** replace every silent path with a typed `GovernanceUnavailableError`; make
  "cannot verify ⇒ deny" the invariant; add a test per path.
- **G-2 — SOD has hardcoded super-roles:** `engine.py:680,683` —
  `allowed_approvers = set(must_review) | {"sami", "compliance_quality_gm"}`. Super-roles
  are hardcoded in the engine rather than declared in the role catalog. **Fix:** move to
  catalog, add a test asserting no hardcoded role ids in `engine.py`.
- **G-3 — Registry drift can never fail CI:** `tests/test_c1_contracts.py:1099-1105`
  asserts only the *shape* of the drift list (`isinstance(drift, list)` + key set).
  Meanwhile `governance.py:418 detect_catalog_drift()` compares **only
  `max_financial_amount`** despite its docstring claiming coverage of "capabilities,
  tools, peer calls and segregation-of-duties". **Fix:** extend to all four fields; add
  `assert drift == []`.
- **G-4 — No kill switch.** A governance platform without an emergency stop is a hard
  enterprise objection. Add a tenant/global halt flag honoured by `engine.py` before any
  committal action.
- **G-5 — Constitutional enforcement is cosmetic.** `governance_check.py:17-21` = 3
  substring checks. Map each of the 5 rules to a mechanical check or downgrade the claim.
- **G-6 — Evidence is not reproducible.** `.gitignore:61-63` excludes `evidence/*`;
  `git ls-files evidence/` returns **1 file**. 18 pilot run dirs exist on disk untracked,
  and `release/security_gate.py:160 check_audit_integrity` (which would verify the chain)
  is never called. **Fix:** ship an evidence export/verify CLI; wire the gate.
- **G-7 — `NOT_READY` + `release_approved: true` naming collision.** Verified benign
  (`go-no-go.json` `approved` is documented as *"a LOCAL consent flag … NOT a human
  production approval"*, and `release/profiles.py:139-152` returns `NOT_READY` for the
  production profile). Still, rename to `pilot_consent` / `classification_profile`.

### Credit

`release/gate.py:218-258` hardcodes all **9 production gates to `False`** with documented
reasons ("requires external signed evidence — not present"). This is **correct fail-closed
design** and is the single most impressive governance artefact in the repo. Preserve it.

## 4. Testing & CI

- **571 tests collected**, 31 files, all passing locally (AGENTS.md S7: 571/571).
- **Markers are dead:** only `@pytest.mark.parametrize` is used. `smoke`, `unit`,
  `integration` are registered but unused ⇒ `-m "not smoke"` is a **no-op**.
- **`--strict-markers` + `--durations=20` + `timeout=120`** are configured — good.
- **CI blockers:** missing root `requirements.lock.txt` (`ci.yml:24`), `pytest-cov`
  undeclared (`ci.yml:35`).
- **CI lint scope too narrow:** only `server/ connectors/ control_plane/` — `engines/`,
  `capabilities/`, `security/` are never checked, which is where B1–B3 live.
- **mypy is cosmetic:** `pyproject.toml` disables 8 error codes and
  `ignore_missing_imports = true`.
- **`python-app.yml` duplicates `ci.yml`** — both run on every push. Remove one.
- **Pre-commit runs `ruff-format` repo-wide but CI never checks formatting.**

## 5. Documentation

**Corrected counts:** root `*.md` = 13 · `docs/**/*.md` = 57 · `GOVERNANCE/**/*.md` = 17.

### Duplication clusters (merge or archive)

| Cluster | Files | Action |
|---|---|---|
| **Status/"master" (7 docs restating state)** | `MASTER_STORY.md` (36 KB), `ROADMAP.md`, `docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md` (48 KB), `docs/HELIX_CODEX_EXECUTION_STATUS.md`, `docs/HELIX_CODEX_UPGRADE_PLAN.md`, `docs/PHASE1_BASELINE.md`, `docs/GAP_ANALYSIS.md` | **Canonical = `00_CONSTITUTION.md` (authority) + MASTER_BLUEPRINT (architecture).** Archive `GAP_ANALYSIS.md` (header literally says "ALL GAPS RESOLVED") and `UPGRADE_PLAN.md` (marked "Proposed"). Pick ONE of `MASTER_STORY.md`/`ROADMAP.md` — they currently cross-delegate authority. |
| **`docs/archive/` map slices** | `PROJECT_MAP.md` (229 KB) + `MAP_B2B/CX/RTA/WFM.md` share **5 identical headings verbatim** | Delete the 4 slices; `PROJECT_MAP.md` is the superset |
| **"What Helix is" intros (4)** | `PRODUCT_DEFINITION.md`, `SYSTEM_ARCHITECTURE.md`, `ENGINEERING_SPECIFICATION.md`, `README.md` | Keep `ENGINEERING_SPECIFICATION.md`; reduce others to pointers |
| **Two changelogs** | `CHANGELOG.md` (root) + `GOVERNANCE/CHANGE_LOG.md` | Single source |
| **Two workspace maps** | `GOVERNANCE/WORKSPACE_MAP.md` + `GOVERNANCE/wayfinder/map.md` | Merge |

### Stale facts (each has a fix)

- `docs/PRODUCT_DEFINITION.md:11` says **"four AI agents"**; spec says nine; CHANGELOG
  records the change — `PRODUCT_DEFINITION.md` was never updated.
- `docs/PHASE1_BASELINE.md:9` records baseline as **Python 3.10.11 / 13 failing tests**
  while `pyproject.toml:19` requires `>=3.12,<3.13`. This is the document every later
  Phase-1 gate compares against.
- `GOVERNANCE/IMPLEMENTATION_MATRIX.md:198,235` — "445 tests"; actual 571.
- `pyproject.toml:19` — `license = "See LICENSE — none committed yet"`, but
  `LICENSE.md` (1,076 B) exists at root. **Blocks commercialization.**
- `overview.md` is not a repo overview — it is the Scoach client report summary. Rename.
- **CHANGELOG is 12 days behind**: last entry 2026-08-29; the entire sports-academy pack
  (15 commits, 2026-09-10, 44 tests) is undocumented. Also **non-monotonic**: 2.1.0 → 0.9.0-c8.

**Good:** zero broken relative markdown links across all tracked `.md` files.

### Version consistency

| Version | Where |
|---|---|
| `0.9.0` | `pyproject.toml:18`, `server/app.py:60`, blueprint `min_core_version` |
| `0.9.0-c8` | `release/__init__.py:10`, `release/manifest.py:108` (**hardcoded literal**), `release-manifest.json`, `go-no-go.json` |
| `1.0.0` | `capabilities/sports_academy/register.py:24` (pack version — fine, separate namespace) |

`release/manifest.py:108` hardcodes the version instead of reading `pyproject.toml` ⇒
**single-source the version**.

## 6. Repo hygiene

- **Uncommitted:** 1 file — `release/release-manifest.json`, whose `git_commit` is
  `7b1bda0`, **3 commits behind HEAD**. The committed manifest describes a different tree.
- **Worktrees: all 5 closable, no lost work.** Verified `git merge-base --is-ancestor`:
  `worktree-phase1-constitution-fix`, `worktree-phase1-smoke-fix`, `worktree-phase1-w5-w6`,
  `phase2/super-app` are all **ancestors of main** (fully integrated).
  `worktree-desktop-app` has 1 unique commit adding `desktop.py`, but `desktop.py` already
  exists on main (`1dd6eb0`). ⇒ `git worktree remove` ×5 + `git branch -d` ×5, zero risk.
- **TODO/FIXME/XXX/HACK in tracked source: 7** — 5 in `app/command_center/agents/dispatch.py`,
  1 `server/features/chat/router.py`, 1 `connectors/gateway.py`.
- **Binary blobs in git:** 3 DejaVu TTF fonts, 1.8 MB total
  (`marketing/assets/fonts/`). Move to Git LFS or vendor at build time.
- `docs/archive/PROJECT_MAP.md` 229 KB, `release/requirements.lock.txt` 164 KB (legitimate).
- **Dependencies:** `requirements.txt` uses compatible-release ranges (loosest:
  `flask-cors>=4.0.0,<7.0.0` spanning a major). `release/requirements.lock.txt` pins 96
  packages — use *that* in CI.

---

# PART II — PRODUCTION PLANNER

## Readiness scorecard

| Capability | State | Blocker? |
|---|---|---|
| Health/readiness endpoints | ✅ `server/features/health/router.py` | no |
| Config management | ✅ `server/config.py` (pydantic-settings, `HELIX_*`) | no |
| Structured errors | ✅ `server/errors.py` | no |
| Structured logging | ✅ `observability/logging.py` | no |
| Backup/restore | ✅ `release/backup.py` + runbook | no |
| Runbooks | ✅ 8 docs in `docs/release/` | no |
| Container | ✅ `infra/docker/` multi-stage + healthcheck | no |
| Release gates (fail-closed) | ✅ **exemplary** — 9 prod gates hard-fail | no |
| **Authentication / RBAC** | ❌ **none** | **YES** |
| **Network hardening** | ❌ debug + 0.0.0.0 + `CORS(*)` | **YES** |
| **Working CI** | ❌ cannot install | **YES** |
| **Dependency scanning** | ❌ none | **YES** |
| **DB migrations** | ❌ none | **YES** |
| **Monitoring / alerting** | ❌ no Prometheus/Grafana/Sentry/OTel | **YES** |
| **k8s / Helm** | ❌ none | medium |
| **Kill switch** | ❌ none | **YES** |
| **Data-retention policy** | ❌ undocumented | medium |

**Current honest label: CONTROLLED_PILOT_READY (at best) — and only after P0.**
The `production` profile is unreachable by construction and must stay that way until the
9 external-evidence gates are genuinely satisfied.

## Phased plan

### P0 — Make it safe to run (1 week) · *non-negotiable*

1. `engines/rta/src/app.py`: `debug=False`, host `127.0.0.1`, explicit CORS origins.
2. Auth middleware on `server/app.py` (all 8 routers) + RBAC bound to the existing role
   catalog; `/healthz` stays public.
3. `server/config.py:52` → default `127.0.0.1`.
4. Auth on the RTA Flask service (or bind to loopback only, if internal).
5. Fix `ci.yml`: point to `release/requirements.lock.txt`, add `pytest-cov` to
   `requirements-dev.txt`, extend lint/test scope to `engines/ capabilities/ security/`.
6. Add `pip-audit` + `bandit` to CI; add `.github/dependabot.yml`.
7. Commit/refresh `release/release-manifest.json`; regenerate with correct `git_commit`.
8. Close 5 worktrees + branches.

**Exit gate:** CI green on a clean container; no unauthenticated route; no high finding
from bandit/pip-audit.

### P1 — Make the governance claims true (2 weeks)

9. Replace all 4 silent-degradation paths in `engine.py` with fail-closed typed errors
   + one test each.
10. Move hardcoded `sami`/`compliance_quality_gm` super-roles into the role catalog;
    add an AST test forbidding hardcoded role ids in `engine.py`.
11. Extend `detect_catalog_drift()` to capabilities/tools/peer-calls/SOD; change the test
    to `assert drift == []`.
12. Decide `tenancy.py`: wire it in, or delete it and remove the constitutional clause.
    Leaving it orphaned is the worst option.
13. Add a kill switch honoured before every committal action.
14. Wire `check_audit_integrity` into the release gate; ship an evidence
    export/verify CLI so evidence is reproducible.
15. Enforce `production_readiness` at registry level.

### P2 — Make it operable (1–2 weeks)

16. Alembic migrations; CI drift check.
17. Monitoring: OTel/Prometheus exporter + `/metrics`; alert rules; Sentry (or equivalent).
18. Single deployable artifact + `[project.scripts]`; align sdist/wheel includes.
19. Remove `python-app.yml`; add `ruff-format --check`; widen ruff ruleset
    (add `I`, `B`, `S`); reduce mypy suppressions over time.
20. Data-retention policy doc; wire `apply_retention()` to a scheduled job.

### P3 — Make it sellable (1 week) · *documentation integrity*

21. **Single authority chain:** `00_CONSTITUTION.md` → `MASTER_BLUEPRINT.md` →
    implementation. Archive `GAP_ANALYSIS.md`, `UPGRADE_PLAN.md`, 4 `MAP_*` slices.
22. Refresh `SECURITY.md` (real contacts, correct dates, scanning claims now true),
    re-date the threat model to cover `engines/rta` + `server/`.
23. Fix stale facts: 445→571 tests, 4→9 agents, Python 3.10→3.12 baseline, LICENSE.
24. One CHANGELOG; add the 2026-09-10 academy release; fix SemVer monotonicity.
25. Single-source version (`manifest.py` reads `pyproject.toml`).
26. Add `docs/SECURITY_CONTACTS.md` + incident SLA; reconcile
    `docs/portfolio/04_security_model.md` with `SECURITY.md`.
27. Move fonts to LFS; rename `overview.md`.

### Then (not before) — the client pilot

Only after P0: Scoach roster CSV import, real-data adapter swap, KPI target calibration.

---

# PART III — CAREER COACH

*Assumption: you are the founder-engineer commercialising Helix Codex OS. If you are
instead a hired lead, substitute "your team" for "you" below — the technical order is
unchanged.*

### What this repo says about you (honestly)

The strengths are *unusual*: you built fail-closed release gates that refuse to let you
claim production, hash-chained memory with a real tamper test, and a capability pack that
copies an established pattern instead of inventing one. That is the work of someone who
thinks about **proof**, not features. Most engineers shipping "AI agent platforms" cannot
produce a verification artefacts at all.

The weakness is equally diagnostic: **the governance discipline was applied to the
product's internals but not to the product's delivery.** Dead CI, no auth, 7 competing
authority docs, a manifest describing a 3-commit-old tree. That is the classic
founder-engineer asymmetry — rigour where the work is interesting, drift where it is
administrative. Buyers do not experience your internals; they experience the drift.

### The reframe that matters

You are not selling an AI platform. You are selling **verifiable restraint** — a system
that can prove what it did and refuse what it should not. That is a compliance product
with an AI surface, and it is worth more than another agent framework. But it only holds
if your own house is auditable. **Right now the strongest thing in the repo
(`release/gate.py` refusing to approve production) is undermined by the weakest
(`SECURITY.md` listing controls that do not exist).**

### Sequence for you personally

1. **Fix CI first, before any feature.** A green pipeline is the cheapest credibility you
   can buy, and right now it is broken in a way that means *no* commit on main has ever
   been verified. Do this today, not this month.
2. **Write the security story only after the controls exist.** Do not let a doc claim a
   control you have not built — that is the one mistake that turns a technical gap into a
   trust gap.
3. **Close the 5 worktrees this week.** Zero-risk, and it removes a chronic source of
   "which branch is real" doubt.
4. **Then, and only then, hire/partner for the two things you evidently avoid:**
   (a) infra/DevOps — migrations, monitoring, k8s, on-call; (b) technical writing — one
   owner for the authority chain. Your comparative advantage is the governed core;
   everything in P2/P3 is delegatable and currently bottlenecked on you.
5. **For the Scoach pilot, sell the pilot, not the platform.** Your gates already say
   `CONTROLLED_PILOT_READY`. That is a defensible, honest offer. Do not let commercial
   pressure push you to claim `PRODUCTION` while `SECURITY.md` admits to fabricated
   contact details.

### Skills to invest in next (highest leverage per hour)

| Skill | Why, given this audit |
|---|---|
| CI/CD + release engineering | Highest-leverage gap; ~1 week converts the repo from unverified to continuously verified |
| Applied AppSec (authn/authz, CORS, secrets, SAST) | B1–B5 are all one afternoon of fixes each, but only if you know the checklist |
| Observability (OTel, SLOs, alerting) | Missing entirely; it is the difference between pilot and production |
| Technical writing / doc architecture | 7 competing authority docs is a writing problem, not a coding problem |
| Threat modelling | Your threat model predates the services it should cover |

---

# PART IV — MASTER GAP REGISTER

Severity: **P0** = blocks launch · **P1** = blocks enterprise sale · **P2** = blocks scale · **P3** = hygiene

| ID | Sev | Gap | Location | Fix | Est. |
|---|---|---|---|---|---|
| G01 | P0 | Flask debug + 0.0.0.0 (RCE) | `engines/rta/src/app.py:269` | debug=False, bind loopback, WSGI host | 1 h |
| G02 | P0 | No auth on any surface | `server/app.py:102`, rta app, cockpit | Auth middleware + RBAC | 2–3 d |
| G03 | P0 | Wildcard CORS | `engines/rta/src/app.py:32` | Explicit origin list | 30 m |
| G04 | P0 | CI cannot install (lock path) | `ci.yml:24` | `release/requirements.lock.txt` | 15 m |
| G05 | P0 | CI `--cov` undeclared | `ci.yml:35` | Add `pytest-cov` to dev reqs | 15 m |
| G06 | P0 | No SAST/dep scanning | — | pip-audit + bandit + dependabot | 4 h |
| G07 | P0 | CI omits engines/capabilities/security | `ci.yml:29-36` | Extend scope | 1 h |
| G08 | P0 | `host=0.0.0.0` default | `server/config.py:52` | Default loopback | 15 m |
| G09 | P0 | Manifest stale + uncommitted | `release/release-manifest.json` | Regenerate + commit | 30 m |
| G10 | P0 | 5 dead worktrees/branches | — | `worktree remove` + `branch -d` | 30 m |
| G11 | P1 | Audit silently skipped | `engine.py:137` | Fail-closed error + test | 4 h |
| G12 | P1 | Secret scan skipped | `engine.py:235` | Fail-closed + test | 2 h |
| G13 | P1 | Injection detect swallowed | `engine.py:346` | Fail-closed + test | 2 h |
| G14 | P1 | SOD bypass on KeyError | `engine.py:687` | Deny + log; test | 3 h |
| G15 | P1 | Hardcoded super-roles | `engine.py:680,683` | Move to catalog + AST test | 4 h |
| G16 | P1 | Drift test can never fail | `test_c1_contracts.py:1099` | `assert drift == []`; widen to 4 fields | 4 h |
| G17 | P1 | `tenancy.py` 100% dead | `control_plane/tenancy.py` | Wire in or delete + amend constitution | 1–2 d |
| G18 | P1 | No kill switch | — | Global halt flag honoured pre-committal | 1 d |
| G19 | P1 | Evidence not reproducible | `.gitignore:61`, `security_gate.py:160` | Export/verify CLI + wire gate | 1 d |
| G20 | P1 | `production_readiness` unenforced | `capabilities/*/register.py:25` | Registry-level assertion | 2 h |
| G21 | P2 | No DB migrations | — | Alembic + drift check | 1–2 d |
| G22 | P2 | No monitoring/alerting | — | OTel/Prometheus + Sentry | 2–3 d |
| G23 | P2 | 3 deployable artifacts | launch.py, desktop.py, compose | Declare one; subordinate rest | 1 d |
| G24 | P2 | No `[project.scripts]` | `pyproject.toml` | Add console scripts | 1 h |
| G25 | P2 | sdist ≠ wheel includes | `pyproject.toml` | Align | 30 m |
| G26 | P2 | No data-retention policy | — | Write policy; schedule retention | 4 h |
| G27 | P2 | `python-app.yml` duplicates ci | — | Delete | 10 m |
| G28 | P2 | No `ruff-format --check` in CI | — | Add; widen rules to I/B/S | 2 h |
| G29 | P2 | mypy 8 suppressions | `pyproject.toml` | Reduce over time | 1 d |
| G30 | P2 | Version hardcoded ×2 | `release/manifest.py:108` | Read from pyproject | 1 h |
| G31 | P3 | 7 competing authority docs | docs/, GOVERNANCE/ | Single chain; archive 6 | 1 d |
| G32 | P3 | Stale: 445 tests | `IMPLEMENTATION_MATRIX.md:198,235` | Update to 571 | 10 m |
| G33 | P3 | Stale: 4 agents | `PRODUCT_DEFINITION.md:11` | → 9 agents | 10 m |
| G34 | P3 | Stale: Py3.10 baseline | `PHASE1_BASELINE.md:9` | Re-baseline | 1 h |
| G35 | P3 | LICENSE claim wrong | `pyproject.toml:19` | Fix | 10 m |
| G36 | P3 | SECURITY.md fabricated contacts | `SECURITY.md:23` | Real/alias contacts | 1 h |
| G37 | P3 | Threat model stale | `docs/C3-threat-model.md` | Cover rta+server; re-date | 1 d |
| G38 | P3 | CHANGELOG 12 days stale | — | Add academy release; fix SemVer | 2 h |
| G39 | P3 | 2 changelogs / 2 maps | — | Merge | 1 h |
| G40 | P3 | Fonts in git (1.8 MB) | `marketing/assets/fonts/` | Git LFS | 1 h |
| G41 | P3 | `overview.md` misnamed | root | Rename to scoach summary | 5 m |

**Totals:** P0 = 10 · P1 = 10 · P2 = 11 · P3 = 10.
**Effort:** P0 ≈ 1 week · P1 ≈ 2 weeks · P2 ≈ 1.5 weeks · P3 ≈ 1 week.

---

## Recommended execution order

```
Week 1   P0 (G01–G10)      → repo becomes safe + verifiably green
Week 2-3 P1 (G11–G20)      → governance claims become true
Week 4   P2 (G21–G30)      → operable
Week 5   P3 (G31–G41)      → sellable / due-diligence-ready
Week 6+  Scoach pilot (CSV import, real adapter, KPI calibration)
```

**Hard rule:** do not touch the Scoach pilot scope until P0 is complete. A pilot that puts
real academy data behind an unauthenticated endpoint is worse than no pilot.

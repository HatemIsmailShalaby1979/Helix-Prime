# Post-hardening re-evaluation — H0–H3

**Date:** 2026-09-12 · **HEAD:** `6d68228` · **Branch:** `h02-server-bind`
**Scope:** independent re-verification of every claim in `AGENTS.md §1`. Nothing below
is taken from the ledger; every number was produced by re-running the command.

---

## 1. Verdict

The hardening work is **substantially real and materially better than the pre-audit
baseline** — 620 tests pass, ruff is clean repo-wide, and the controlled-pilot gate is
green for the first time. The ledger is honest about what is done.

But **"all prompts executed" ≠ "done"**. Three things are outstanding, and two of them
mean **CI would still be red today** — which was H0's stated exit gate.

| # | Finding | Severity | Effort |
|---|---|---|---|
| F1 | `mypy` fails — 20 errors, no mypy config in repo | **CI red** | 0.5–1 d |
| F2 | `bandit` fails — 8 medium issues; `bandit.yaml` never wired into CI | **CI red** | 5 min |
| F3 | H1.3 / G16 still open, and worse than described | Governance | 1–2 d |
| F4 | All 34 commits unmerged to `main`; CI has never run on them | Process | 30 min |
| F5 | Stale uncommitted release manifest | Hygiene | 5 min |

---

## 2. What is genuinely done (verified)

- **Tests: 620 passed, 0 failed** (baseline was 571). Run with `--basetemp` outside
  AppData; 7m38s.
- **Lint: `ruff check` on all 7 CI directories → 0 findings.** This is a real
  turnaround — the pre-hardening state had ~429 findings across `engines/` alone.
- **`ruff format --check .` → 249 files already formatted, 0 to reformat.**
- **`run_gate('controlled_pilot')` → `CONTROLLED_PILOT_READY`, 14/14 gates green**,
  including `security_checks` (`secrets_scan:True`) and `data_isolation`.
- **`run_gate('production')` → `NOT_READY`.** This is correct behaviour, not a defect:
  the 10 failing gates are external-evidence gates (signed security review, certified
  isolation, DR evidence, on-call ownership, …) that no code change can satisfy.
- **Migration drift: exit 0**, 19 store objects vs 19 migration objects.
- **H0.1 / H0.2 / H0.3 verified in code:** `server/config.py:53` `host = "127.0.0.1"`;
  nine routers carry `Depends(current_identity)` and `health_router` is the only
  unauthenticated one; RTA uses `CORS(app, origins=...)` and `debug=True` is gone.
- **H1.1 fail-closed** — 15 `GovernanceControlUnavailable` references.
- **H1.5 kill switch** — module + CLI + 12 tests, wired into `Engine`
  submit/approve/execute.
- **H1.4 / G17 tenancy deletion** — fully landed. Zero `.py` references. The only
  remaining mentions are in the audit prompt doc, which is correct (it is the
  historical instruction record). `security/policy.py` carries the deferral note.
- **AGENTS.md de-duplication** (`6d68228`) — single active status section.

---

## 3. F1 — `mypy` fails: 20 errors (CI red)

```
mypy server/ connectors/ control_plane/   → exit 1
Found 20 errors in 5 files (checked 58 source files)
```

| File | Count | Code |
|---|---|---|
| `control_plane/control_seam.py` | 8 | `union-attr` (`AgentError \| None`) |
| `control_plane/engine.py` | 7 | `truthy-function` |
| `server/models/node.py` | 3 | `index` (TypedDict literal keys) |
| `control_plane/governance.py:540` | 1 | `override` (signature vs `contracts.task.CorrelationContext`) |
| `server/deps.py:60` | 1 | `union-attr` (`EngineProvider \| None`) |

**Root cause: there is no mypy config file in the repo at all** — no `mypy.ini`,
`setup.cfg`, or `[tool.mypy]` in `pyproject.toml`. CI invokes bare `mypy`, which
defaults to a stricter-than-expected baseline for this codebase.

Note the `engine.py` `truthy-function` errors are the **H1.1 fail-closed import
guards** (`if not authorize: raise`). mypy correctly observes these functions are
always truthy. Do **not** "fix" them by deleting the guards — the guards are the
control. They need a targeted `# type: ignore[truthy-function]` with a comment, or a
narrowing helper, not removal.

---

## 4. F2 — `bandit` fails: 8 medium issues (CI red)

```
bandit -r server/ connectors/ control_plane/ engines/ capabilities/ security/ -ll   → exit 1
  Total lines skipped (#nosec): 0
  Total potential issues skipped ... (e.g. #nosec BXXX): 0
  7 × B113 request_without_timeout
  1 × B310 urllib.urlopen
```

`bandit.yaml` already exists and already documents the intended skips:

```yaml
skips:
  - B113  # requests without timeout — internal APIs, hang expected
  - B310  # urllib.urlopen with hardcoded https URL + timeout arg
  - B608  # SQL string construction — parameterized, no user input
```

**But `.github/workflows/ci.yml` runs `bandit -r ... -ll` with no `-c` flag, and
bandit does not auto-discover `bandit.yaml`.** The skips are therefore inert — hence
`nosec skipped: 0`. H0.5 is recorded as ✅ ("skips for B113/B310/B608 with
justification"), and the justification file genuinely exists; it was just never
connected.

Proven fix:

```
bandit -c bandit.yaml -r server/ connectors/ control_plane/ engines/ capabilities/ security/ -ll
  → exit 0, Medium: 0
```

This is a **one-line change** that turns a red CI step green.

---

## 5. F3 — H1.3 / G16 still open, and worse than the audit described

The audit said: *"Drift test can never fail — widen to 4 fields, 4 h."* The
"widen to 4 fields" instruction was **not executed**. Current state:

`detect_catalog_drift()` (`control_plane/governance.py:440`) compares exactly **one**
field — `financial_approval_limit_usd`. Its own docstring claims it covers
"capabilities, tools, peer calls and segregation-of-duties". It does not.

Worse, the four structural `RoleSpec` fields are **empty for every role at runtime**:

```
role                 owned_cap  tools  peer  sod
sami                         0      0     0    0
ops_gm                       0      0     0    0
compliance_quality_gm        0      0     0    0
fraud_revenue_gm             0      0     0    0
hr_personnel_gm              0      0     0    0
ld_gm                        0      0     0    0
sales_gm                     0      0     0    0
marketing_gm                 0      0     0    0
ict_gm                       0      0     0    0
```

…while `organization/role-catalog.yaml` **does** populate them (`sami` has 5
`owned_capabilities`, 6 `allowed_tools`, plus `allowed_peer_calls` and
`segregation_of_duties`). The `RoleSpec` docstring states these are "sourced from
organization/role-catalog.yaml and used by `detect_catalog_drift()`". **Both halves
of that sentence are false.**

This is the same failure class as `tenancy.py` (G17): a control that exists only as a
declaration. It is arguably more dangerous here, because the declaration is attached
to a live dataclass that authorisation reads.

**Consequence for the fix:** naively widening `detect_catalog_drift()` to four fields
would immediately fail CI with ~36 findings (9 roles × 4 fields) of empty-vs-populated
mismatch. The runtime catalog must be **populated from YAML first**, then the
comparison widened. Budget accordingly — this is not 4 hours.

Two coherent resolutions, mirroring the tenancy decision:

- **A — Make it real:** populate the four fields on all 9 `ORGANIZATION_CATALOG`
  entries, then widen `detect_catalog_drift()` to compare all five fields, and add a
  can-fail test. Keeps the two-declaration design so drift is detectable.
- **B — Delete it:** remove the four dead fields and fix the docstrings, if the
  runtime catalog is never meant to mirror YAML.

Recommendation: **A**, because `security/policy.py` already enforces
"allowed capability" and "allowed tool" — so these fields describe a control the
system claims to have.

---

## 6. F4 — Everything is on an unmerged branch

```
main          c3c4abf   (2026-09-10)
h02-server-bind  6d68228  (34 commits ahead of main)
origin/main   1ab9bea
```

CI triggers only on push/PR to `main`, so **CI has never executed on any of the H0–H3
work.** That is precisely why F1 and F2 survived: they are both red, and nobody's CI
ever told them.

Good news: `origin/main` (`1ab9bea`) **is** an ancestor of `HEAD` — zero commits in
`HEAD..origin/main` — so there is no divergence and the merge is safe.

Also stale: `h01-rta-hardening` (identical to `main`) and
`worktree-phase2-collaboration` (identical to `origin/main`, last touched 2026-08-29).

---

## 7. F5 — Stale uncommitted manifest

`release/release-manifest.json` is modified but uncommitted, and points at `a14ce81`
while HEAD is `6d68228`. Regenerate and commit, or revert.

Minor inconsistency worth a look: it carries `"release_profile": "production"` and
`"release_approved": true` alongside `"classification": "NOT_READY"`. Defensible
(approved for pilot, not for production) but confusing to a reader.

---

## 8. Not verified — environment limitation

The CI step `--cov=server --cov=connectors --cov-fail-under=80` **could not be
verified locally.** The sandbox this audit ran in intercepts `os.remove`, which kills
`coverage.combine()` (and pytest's tmpdir cleanup) once a turn-scoped delete counter
is exceeded. Every attempt aborted partway; the one partial result (21%) reflects ~50
tests, not the suite, and must be disregarded.

**Verify this gate in a clean container, not locally.** Also clean up two gitignored
strays in the repo root: `.coverage` and `.coverage.ThomasShalaby.*`.

Also unverified: `pip-audit` (needs network).

---

## 9. Suggested order

1. **F2** — one line, turns CI green, zero risk. Do it now.
2. **F4** — merge to `main` so CI actually runs and reports F1/F3 honestly.
3. **F1** — add a mypy config; fix or narrowly suppress 20 errors.
4. **F3** — decide A or B, then implement.
5. **F5** — regenerate the manifest.

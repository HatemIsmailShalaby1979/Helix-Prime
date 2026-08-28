# Helix Prime Codex C8 — Sign-off Model

Status: sign-off rules for the controlled pilot. Machine implementation:
`release/signoff.py`. Local file: `release/go-no-go.json`.

## Purpose

`release/go-no-go.json` records LOCAL consent for a controlled pilot — it is an
`internal_review`/`pilot_approved` sign-off, NOT a fabricated human acceptance
and NOT a production approval. It can never satisfy `production_approved` by
itself.

## Sign-off states

| State | Meaning | Satisfiable locally? |
|-------|---------|----------------------|
| `unsigned` | No decision recorded | yes |
| `internal_review` | Local pilot consent recorded | yes |
| `conditional` | Approval pending listed conditions | yes (conditions must close) |
| `pilot_approved` | Pilot go/no-go approved | yes |
| `production_approved` | Full production approval | **NO — never** |

## Rules enforced by `release/signoff.py`

- `validate_signoff(s: SignOff)` returns `(ok, reason)`. It takes a single
  `SignOff` whose state is `s.state`; it does not take a `(state, go_no_go)`
  pair. (Corrected to match `release/signoff.py`.)
- `unsigned` and `internal_review` require no decision; `pilot_approved` and
  `production_approved` require `decision == "approve"`, a reviewer identity and
  role, a decision timestamp, an evidence pack id, and at least one evidence
  reference.
- `conditional` requires a non-empty `conditions` list; every listed condition
  must be met (evidence that each condition is closed) before it can count as
  approval.
- A sign-off with a recorded `expires_at` that has passed is rejected.
- `production_approved` additionally requires a signature reference AND
  `_all_production_gates_satisfied()`; the latter is always `False` locally
  (fail-closed), so `production_approved` can never be reached locally.
- `is_release_approved(state)`: only `pilot_approved` (or `conditional` with all
  conditions met) counts as a local go for the pilot. `production_approved` is
  NOT reachable.
- `can_prove_gate_locally(gate)`: only the pilot-relevant gates are locally
  provable; production-only gates are not.
- `import_go_no_go()` reads `release/go-no-go.json` and maps its
  `data_scope`/`approved`/approver fields into a `SignOff`; `approved: true`
  with approver `operator-pilot-consent` is treated as local `internal_review`
  consent only.

## Rule of thumb

If a change makes `production_approved` satisfiable locally, or lets
`go-no-go.json` bypass `validation`, it is a defect. Reject it.

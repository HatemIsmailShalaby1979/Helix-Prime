# 4. Security Model

Security is enforced in code and verified by the release security gate
(`release.security_gate.run_security_gate()` → `all_ok=True`).

## Checks (all passing)
| Check | Result | Notes |
|-------|--------|-------|
| Secrets scan | 0 findings | source scanned for secret-like patterns; synthetic placeholders allowed |
| Classification vocabulary | present | canonical set: public/internal/client_confidential/personnel_sensitive/financial/regulated_high_risk |
| Deny-by-default | denied | unknown capability is denied, not allowed |
| Redaction | works | secret values removed, `[REDACTED…]` present |
| Malformed output | typed failure | engine failures map to a typed `EngineResult` error, not a crash |
| Audit integrity | valid | isolated audit-chain probe verifies |

## Authorization
- `security.identity.Identity` carries actor/type/tenant/client/role.
- `security.policy.authorize` is deny-by-default; unknown capabilities are refused.
- Connectors enforce tenant/client scope on every read (`_assert_scope`); cross-tenant
  enrichment is denied.

## Approval security (separation of duties)
- `pilot.approval.evaluate_approval_decision` rejects self-approval and same-role approval.
- `metacognition.improvement.MetacognitionEngine.approve` rejects self/same-role approval
  and rejects proposals that failed evaluation.
- The first real pilot begins in a **read-only period**; committal approvals are blocked
  until it is explicitly exited (audited).

## Data protection
- Minimum necessary data: the pilot and restaurant pack collect only required fields;
  personnel-sensitive and financial fields are classified and excluded from operational
  recommendations unless consented.
- Three data modes are distinguished: `historical_consented`, `simulated_realistic`,
  `live_customer` (the last is **not activated** in this build).
- Connectors are read-only: `request_write` returns `executed=False` even with a valid
  approval, because no live adapter is activated.

## What is NOT claimed
- No real penetration test, no certified isolation audit, no external security review.
  These are required production gates and are intentionally red (see
  [11_known_limitations.md](11_known_limitations.md)).

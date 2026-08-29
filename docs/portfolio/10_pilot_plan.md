# 10. Pilot Plan

A single, controlled, read-only-first pilot plan covers both demonstrated wedges (call-centre and
restaurant). It is the operational expression of the governance model.

## Controls (all implemented and tested)
1. **Scope & objectives** — `pilot.scope.PilotScope` (objectives, policies, review checklist).
2. **Customer consent** — `pilot.consent.ConsentRecord` + `validate_consent` (granted / expiry /
   permitted-data-mode checks; live data rejected).
3. **Data classification & minimum data** — `DataClassificationPolicy`, `MinimumDataPolicy`; excluded
   sensitive fields are never collected.
4. **Read-only connectors** — `ReadOnlyConnectorConfig`; `request_write` disabled by design.
5. **Connector permissions** — `ConnectorPermissions` (read allowed, write denied, validated).
6. **Tenant isolation** — governed-memory tenant scope; verified by tests.
7. **Read-only period (first real pilot)** — `prepare_first_real_pilot` enters a read-only period;
   committal approvals are blocked until explicitly exited (audited).
8. **Manual approval for every committal action** — `approval` records (draft → approved/denied/
   rolled_back) with owner + SOD.
9. **Retention & deletion** — `RetentionDeletionPolicy` + `apply_retention` (flag, never drop).
10. **Incident & rollback** — `rollback_action` appends an incident and marks `rolled_back`.
11. **Baseline measurement** — `dry_run` records baseline metrics in governed memory.
12. **Success metrics** — response-time reduction, escalation accuracy, unresolved-risk age,
    customer-health visibility, missed follow-ups, recommendation acceptance, correction rate.
13. **Customer review checklist** — `PilotScope.review_checklist` (10 items).
14. **Evidence pack** — `build_evidence_pack` with explicit final status.

## Three data modes
`historical_consented`, `simulated_realistic`, `live_customer` — explicitly separated; live is not
activated in this build.

## Status
- Pilot package ready: **TRUE**.
- First restaurant capability pack ready: **TRUE**.
- Real design-partner approval: **PENDING**.
- Production readiness: **NOT_ESTABLISHED**.

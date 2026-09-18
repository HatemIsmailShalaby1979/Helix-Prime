# Sports-Academy Capability Pack (v1)

> **Classification:** PROJECT DOCUMENT — capability pack record
> **Status:** Read-only, synthetic data only, `production_readiness: NOT_ESTABLISHED`
> **Client context:** first design partner (Scoach Academy Hub, private sports
> academy, one location). Business case: `docs/scoach_academy_hub_opportunity_report.md`.

## What this pack is

`capabilities/sports_academy/` is the second vertical capability pack (after
`restaurant`) and the first for the sports-academy vertical. It reuses the
governed Helix Codex core — identity, tenant isolation, governed memory with
hash-chained audit, approval workflows with separation of duties, read-only
phases — and maps academy operations onto existing engines rather than
registering new capabilities.

## Core reuse map (no new engine capabilities registered)

| Academy concern | Reused core | Mechanism |
|---|---|---|
| Check-in/check-out, session adherence | `engines/rta` (RTA Command Center) | `schedule` vs `actual` DataFrames, `agent_id` = athlete |
| Churn / at-risk athletes | `engines/cx` (CX Churn Sentinel) | `customers=[{customer_id, csat=attendance_rate}]`, capability `churn_risk_scoring` |
| KPI computation from governed memory | pack-local `kpis.py` (pattern: `restaurant/metrics.py`) | YAML-declared targets, Python compute |
| Approvals, SOD, read-only phase | `pilot/approval.py`, `pilot/phases.py` | identical to restaurant pack |
| Synthetic fixtures | `connectors.contracts.SourceRef` | `data_mode=simulated_realistic` everywhere |

## Contents

- **Ontology** — Athlete, Family, Coach, Program, Session, CheckIn,
  FacilitySlot, FeePayment, EnrollmentRecord (frozen, tenant/client scoped)
- **Adapters** — attendance (RTA reuse), athlete profiles (CRM + churn),
  facility (conflicts + utilization), payments (manual records only)
- **KPIs** — academy: attendance, churn, facility utilization, MRR, active
  athletes; coach: session adherence, athlete attendance, on-time delivery,
  parent satisfaction (progression deliberately deferred — needs curriculum)
- **Roles** — academy_owner, head_coach, coach, academy_admin, parent
  (pack-local; NOT merged into the core role catalog; parent holds no
  approval authority)
- **Workflows** — enrollment (inquiry → trial → enroll → pay), attendance
  (check-in → adherence report → escalation), renewal (term-end → reminder →
  renew/churn); declared in `declarations/*.yaml`, mirrored in Python,
  drift-tested
- **Cockpit views** — owner dashboard (5 numbers), coach dashboard (today +
  4 KPIs), parent portal (read-only family view); pure compute + thin
  Streamlit render, wired as the "Sports Academy" cockpit page
- **Runtime** — `AcademyCapabilityPack`: dry_run over synthetic fixtures,
  diagnoses + recommendations + approval drafts, approve/deny/rollback with
  SOD + required-approver-role, read-only period gating, evidence pack with
  audit-chain verification, metacognitive proposals (never self-applied)

## Governance invariants (enforced by tests)

1. Every governed-memory record carries tenant/client, provenance
   (correlation_id, data_mode, basis, sources), evidence_refs, classification.
2. Sample data is recorded as `simulated_event`/`model_inference`, never
   `verified_outcome` for computed results; `data_mode=simulated_realistic`
   everywhere; zero `live_customer` records.
3. Read-only period blocks all committal approvals (enrollment, fee_record,
   renewal) until explicitly exited.
4. Self-approval and same-actor approval are denied (SOD).
5. Wrong approver role is refused (authority boundaries in `roles.py`).
6. Connectors are read-only; `request_write` returns `executed=False`
   (inherited from `BaseConnector`).
7. Fees store no payment instruments — amount/date/method-note only.
8. Pack roles never widen core roles and do not appear in the core catalog.
9. The connector funnel refuses any record not stamped `simulated_realistic`
   (`AcademyConnector._reject_live_data`); no live Scoach connector exists
   and the pack tree carries no network client imports.

Production readiness of this pack is separate from production readiness of
the app: see `docs/release/production-data-boundary.md`. This pack stays
synthetic, read-only, and `NOT_ESTABLISHED`; graduation needs a consented
roster import, a client-defined curriculum, an explicit readiness review,
and the same production gates as the app.

## Not in v1 (deliberate)

- Parent mobile app (web portal only)
- Payment processing/integration (manual records only; PCI scope deferred)
- Athlete progression tracking (requires curriculum definition first)
- Multi-location support (pilot is one location)
- Live data mode (`production_readiness` stays NOT_ESTABLISHED until a
  design partner approves a controlled pilot)

## Verification

`tests/test_capabilities_sports_academy.py` — 44 tests covering connectors,
attendance math + RTA reuse, KPI drift + computation, profiles + churn,
roles + flows, cockpit compute functions, facility + fees, and the full
runtime (registration, walkthrough, evidence pack, approval gating, SOD,
deny/rollback, metacognition). Run:

```
python -m pytest tests/test_capabilities_sports_academy.py -q
```

Demo path (owner): cockpit → Sports Academy → Owner tab shows the 5 numbers;
Coach tab shows today's sessions + KPIs vs targets; Parent tab shows one
family's read-only view. Every recommendation in the runtime dry-run lands in
an approval draft behind SOD — nothing executes without a human.

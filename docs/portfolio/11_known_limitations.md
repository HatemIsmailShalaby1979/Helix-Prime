# 11. Known Limitations (Unfinished Items)

These are stated separately from completed work. None are hidden; each maps to a red production
gate or an explicit out-of-scope decision.

## Not implemented / not established
- **Production readiness** — `NOT_ESTABLISHED`. The `production` release profile is intentionally
  `NOT_READY`; its gates require external evidence this build does not have.
- **Live connectors / external writes** — not activated. Connectors are read-only; `request_write`
  returns `executed=False`. No data leaves the process.
- **Live customer data** — the `live_customer` data mode is defined but never used in this build.
- **Automatic self-improvement / deployment** — the metacognitive engine proposes and evaluates but
  never deploys; no automated behavior change occurs.
- **Durable memory persistence in the pilot runtime** — `GovernedMemory` is in-memory by default
  (`in_memory_not_persisted`). A hardened store exists at the release-gate level but is not wired
  into the pilot/capability runtime.
- **Universal business coverage** — only call-centre and one small-restaurant workflow are
  demonstrated. Helix Codex is **not** claimed to work for every business.
- **Real cloud deployment** — the cloud boundary is synthetic-only; no production infrastructure.
- **External audits/reviews** — certified tenant/data isolation, external observer audit, signed
  production evidence, security review, legal/privacy review, operational/on-call ownership, and
  disaster-recovery evidence are **not** performed. These are the red production gates.
- **Single-location restaurant ontology** — one location, simplified roles; not a multi-site model.
- **Measured production cost** — no billed usage; cost is assumption + guardrail only (see 09).
- **Human-facing UI** — the cockpit is a separate web shell; the governed core runs headless.
  No operator console is bundled with the pilot runtime here.

## Scope boundaries (by design, not defects)
- Read-only-first is intentional; committal actions require explicit, gated human approval.
- Tenant isolation, SOD, and deny-by-default are enforced, not optional.

## What IS completed (for contrast)
See [`00_INDEX.md`](00_INDEX.md) and [`15_verified_test_results.md`](15_verified_test_results.md):
the governed core, the controlled pilot, the restaurant capability pack, the synthetic demo, 445
passing tests, `governance=PASS`, security `all_ok=True`, and the release gates.

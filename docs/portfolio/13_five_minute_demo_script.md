# 13. Five-Minute Demo Script

Goal: show an accountable, governed system — business context in, governed workflow, remembered
outcomes, evidence-based improvement, no silent control. Run everything live; all output is real.

## 0:00 — Positioning (30s)
> "Helix Codex is an accountable AI operating organization that understands business context,
> coordinates governed workflows, remembers decisions and outcomes, and improves through evidence
> without silently taking control."

State upfront: read-only, synthetic, no external writes, production readiness NOT established.

## 0:30 — Architecture (30s)
Walk [`01_architecture_overview.md`](01_architecture_overview.md): identity → connectors (read-only)
→ workflow diagnosis → recommendation + approval (SOD) → governed memory (hash-chained) → evidence pack.

## 1:00 — Governance (30s)
```bash
python3 -m GOVERNANCE.governance_check check
```
Expect `governance=PASS`. Point at `GOVERNANCE/IMPLEMENTATION_MATRIX.md` (every claim tied to a test).

## 1:30 — Security (30s)
```bash
python3 -c "from release.security_gate import run_security_gate; r=run_security_gate(); print('all_ok =', r['all_ok'])"
```
Expect `all_ok = True` (0 secret findings, deny-by-default, redaction, audit integrity).

## 2:00 — Synthetic demo (60s)
```bash
python3 demo/synthetic_demo.py
```
Show: call-centre tenant + restaurant tenant in one memory; `audit_chain_intact=True`;
`live_customer_records: 0`; `request_write` disabled. Highlight the restaurant metrics line.

## 3:00 — Evidence pack (30s)
Show the final-status block from the demo output:
`pilot_package_ready=TRUE`, `real_design_partner_approval_pending=TRUE`,
`production_readiness=NOT_ESTABLISHED`.

## 3:30 — Metacognition (30s)
Show `capabilities/restaurant` records a `policy` proposal with `applied=False` — improvement is
proposed and evaluated, never silently deployed ([`07_metacognitive_improvement_model.md`](07_metacognitive_improvement_model.md)).

## 4:00 — Limitations & roadmap (30s)
Read [`11_known_limitations.md`](11_known_limitations.md) honestly: production NOT established, no
live writes, not universal. Then [`12_roadmap.md`](12_roadmap.md).

## 4:30 — Close (30s)
Re-state positioning. Offer the test suite as proof:
```bash
python3 -m pytest tests/ -q -p no:cacheprovider   # expect: 445 passed
```

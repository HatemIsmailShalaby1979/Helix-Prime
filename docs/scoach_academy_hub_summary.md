# Scoach Academy Hub — Opportunity Report Summary

## What was done
A comprehensive opportunity validation report was created for Helix Codex OS's first potential client — Scoach Academy Hub, a private sports academy. The report applies the Hexa Opportunity Memo framework (PCV scoring) and includes deep research on the sports academy business domain, competitive landscape, pricing strategy, and a 90-day client onboarding playbook.

**Status: the sports-academy capability pack is now BUILT (v1.0.0, 2026-09-10).** The opportunity-report recommendation became reality: `capabilities/sports_academy/` — attendance (RTA reuse), coach KPIs, athlete profiles (CX reuse), owner/coach/parent cockpit views, roles, workflows, and governance-approved writes — all on `simulated_realistic` data with `production_readiness = "NOT_ESTABLISHED"`. See `docs/sports_academy_pack.md`.

## Key findings
- **PCV Score: 18/24 (Strong opportunity)** — the client's pain (no CRM, no KPIs, no adherence control, no hierarchy) maps directly to Helix Codex's six engines
- **Competitive pricing landscape**: $50-200/month or $2-5/player for existing solutions; Helix Codex should price at $350-600/month (value-based, not per-player)
- **Recommended strategy**: Position as a pilot partner (free 60 days), build a sports-academy capability pack, turn the client into the first case study
- **Build priority**: Start with RTA (attendance tracking) → CRM (athlete profiles) → Personnel (coach KPIs) — one engine at a time

## Deliverables
- Full report at `docs/scoach_academy_hub_opportunity_report.md` (10 sections + 3 appendices)
- 3 inline visuals: solution mapping diagram, pricing comparison chart, 90-day onboarding timeline

## Next steps (pack built — move to the pilot)
1. Read the report (especially sections 3, 6, 8)
2. Conduct the discovery meeting using the 7 questions in section 6.2
3. Import the real roster (CSV import, then swap the fixture source for connectors)
4. Configure Scoach roles + KPI targets and calibrate against real data
5. Do NOT pitch the product until after discovery

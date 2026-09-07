# 17. Revised Strategy Plan — Two Tracks, Not One Founder Bet

**Supersedes:** the founder-bootstrap framing in `16_market_research_strategy_roadmap.md`.
**Core correction:** you are not a solo founder deciding between bootstrap/seed/employment.
You are an employed engineer (ByteDance/TikTok LIVE) running an active 60-day job search
(Project Phoenix) with two shipped portfolio assets — Helix ecosystem and L&D Command Center
v1.0.0 — as evidence. The plan below is sequenced for that reality: two tracks running at
different speeds, not one 12-week sprint that assumes full-time founder bandwidth you don't have.

---

## Why the original plan needs restructuring, not just trimming

1. **It assumed a resource you don't have.** §7 Path A costs "$5–15k out of pocket" and 12
   weeks of full-time-equivalent sprint work (durable memory + design partner + operator
   console + live connectors, all in weeks 1–4 alone). You have evenings/weekends against a
   day job and an active job search — call it 8–12 hrs/week, not 40.
2. **It buried your actual near-term lever.** Path C (portfolio-as-leverage for a role) was
   listed third, as a fallback if "a multi-year solo build isn't the right risk profile *yet*."
   But you're already running that path right now, on a 60-day clock. It should be Track 1,
   not an escape hatch.
3. **It leaned on shaky headline stats.** The "Claude Enterprise 0%→5.7% market share" line is
   sourced to a blog aggregator, not a named analyst firm, and it's doing outsized rhetorical
   work in §3.2. A revised plan should keep the *directionally solid* claims (HITL governance as
   a buying criterion — that one's corroborated across CB Insights, Deloitte, and G2 feedback
   independently) and drop the single unverifiable number.
4. **It had no exit from indefinite open-core limbo.** "Publish, then see if a community forms"
   has no clock and no kill criterion — it can absorb unlimited weekend hours with zero signal
   for months. A revised plan needs a hard stop.

---

## Track 1 — Job search (Project Phoenix), active now, 60-day clock

This is the priority track. Nothing on Track 2 should slow this down.

- **Use what's already built, don't build more.** Helix-Prime, helix-education (447 tests),
  study-studio, live-support-assistant, and the now-shipped **L&D Command Center v1.0.0**
  (730 tests, 93.62% coverage, packaged Windows/Linux release) are already a strong evidence
  set for Senior Backend/AI Engineer / Platform Engineer roles. The job is to *package and
  narrate* this work, not add scope to it.
- **This week:** finalize the three resume variants (PRODUCTION/ATS/EXECUTIVE) against this
  actual portfolio — the LDCC release is a concrete, finished, metrics-backed shipping story
  ("730 tests, 93.6% coverage, cross-platform release") that's stronger than anything in the
  original roadmap's speculative market sizing.
- **Weeks 1–4:** run the ~100-application blitz as planned in SURVIVAL_PLAN.md. No new repo
  work competes for this time.
- **Gate:** interviews booked or not by week 4 tells you whether the portfolio narrative is
  landing. If it isn't, that's a resume/positioning problem to fix before touching Track 2 at all.

---

## Track 2 — Helix Codex, background track, no clock pressure, capped hours

Reframed from "12-week founder sprint" to "evidence-building side project that either compounds
or gets shelved — decided by a checkpoint, not by momentum."

### Step 1 (ongoing, low-effort): make the existing work externally legible
- Publish the Apache-2.0 core and CONTRIBUTING doc — this is a few hours of packaging work you
  already know how to do (you just did it for LDCC), not a sprint deliverable.
- Skip the whitepaper and MCP/A2A demo for now — they're nice-to-haves that assume an audience
  that doesn't exist yet. Publish first, write the whitepaper only if someone external asks
  a question the whitepaper would answer.

### Step 2 (checkpoint, ~8–12 weeks of background effort, not calendar weeks)
- **Single gate, not three:** did anyone outside your own accounts engage — a star from a
  non-bot account, an issue, a fork, a DM? This replaces Gate-1/2/3's design-partner and MRR
  targets, which require founder-level time you're not spending yet.
- **If yes:** worth another checkpoint cycle — maybe a design partner conversation, still no
  capital or pricing decisions.
- **If no after two cycles:** shelve the commercialization angle explicitly. The code and tests
  remain valid portfolio evidence for Track 1 either way — nothing is lost, per the original
  doc's own §10 logic, which is the one part worth keeping unchanged.

### What gets dropped from the original plan (for now)
- Design-partner onboarding, paid tier, pricing ($150–400/mo), and MRR targets — these assume
  founder bandwidth and a validated audience neither of which exist yet. Revisit only if Step 2
  produces real external signal.
- The seed-raise path (Path B) — premature by a wide margin; nothing changes here until Step 2
  produces evidence, and even then it's a multi-month-away decision, not a 2027 milestone to
  plan around today.
- The financial scenario table (§7) — six-figure MRR projections built on unvalidated demand are
  noise at this stage; replace with the single binary checkpoint above.

---

## What to keep from the original document as-is

- **§10 "What this plan explicitly does NOT claim."** This discipline is good and should
  survive into any revised version — carry it forward for Track 2's step 1 publication too:
  no revenue claimed, no customers claimed, pre-checkpoint.
- **The core market observation**, stated more conservatively: multiple independent sources
  (CB Insights' trust pillars, Deloitte's autonomy-spectrum framing, G2's SDK-flexibility-vs-
  governance-gap feedback) converge on human-in-the-loop governance as a real, cited industry
  concern in 2025–2026 — useful as *narrative context* for why Helix Codex is a credible
  portfolio artifact, not as a market-sizing basis for a business plan.
- **Apache-2.0 first, re-license only if a hyperscaler cannibalizes** — sound, standard, cheap
  to commit to now, doesn't require the rest of the founder apparatus around it.

---

## One-page summary of the change

| | Original plan | Revised plan |
|---|---|---|
| Primary track | Solo-founder bootstrap (Path A default) | Job search (Track 1), active now |
| Helix Codex role | Central commercial bet | Background evidence-builder, capped hours |
| Timeline | 12-week founder sprint | Job search: 60 days. Helix Codex: no clock, one checkpoint |
| Success gate | 3–5 paying tenants / $15k MRR | Interviews booked (Track 1); any real external signal (Track 2) |
| Capital | $5–15k out of pocket | $0 — no spend until a role or real demand signal exists |
| Market data | Used as planning inputs (MRR tables, seed sizing) | Used as narrative context only, not a forecast |
| Risk register | Seed dynamics, licensing churn, big-tech commoditization | Time double-booking (Track 2 eating Track 1's hours) is the top risk |

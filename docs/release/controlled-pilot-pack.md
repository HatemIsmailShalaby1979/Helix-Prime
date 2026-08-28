# Helix Prime Codex C8 — Controlled Pilot Pack

Status: ready for a **controlled pilot** (AND production candidate), NOT production.

## What the controlled pilot is

A human-supervised pilot limited to **synthetic or explicitly consented data**.
It exercises the real control plane, six engines, nine agents, GM aliases,
C7 sibling contracts, audit, classification, authorization, persistence, and
backup/restore — without any irreversible, financial, personnel, compliance,
ICT, or external-communication action.

## Scope (what is included)

- Six engines (WFM, RTA, CX, B2B, Personnel, CRM) via the engine registry.
- Nine agents (SAMI, SUBY, PHILI, WILI, ANDY, NONO, MAYA, LIZA, TOMY) + five
  legacy aliases.
- Vertical-slice end-to-end run with approval (SAMI-approval gate).
- Local persistence, replay, idempotency, audit chain, backup/restore/rollback.
- C7 contracts and in-process sibling transport.

## Scope (what is explicitly excluded / deferred)

- No customer deployment, no production client data, no cloud deployment.
- No external IdP, no cloud observability, no network sibling transport.
- No autonomous irreversible actions; no commercial/scalability claims.
- No L&D Command Center Windows build.

## Pilot data / consent

- Pilot data MUST be synthetic or explicitly consented.
- The `release/go-no-go.json` records `data_scope: SYNTHETIC_OR_CONSENTED_ONLY`.
- Any use of non-synthetic, non-consented data is out of scope and prohibited.

## Pilot exit criteria

- All release-gate checks green (`PRODUCTION_CANDIDATE` / `CONTROLLED_PILOT_READY`).
- Operator reviews the evidence pack under `evidence/releases/<timestamp>/`.
- A separate go/no-go sign-off precedes any broader rollout; production label
  is NOT claimed by this pack.

## Evidence pack

Each gate run writes `evidence/releases/<timestamp>/` containing:
- `release-gate-summary.json`, `release-manifest.json`, `harness-results.json`.

These are gitignored generated artifacts (not committed); the committed source
of truth is `release/` and `docs/release/`.

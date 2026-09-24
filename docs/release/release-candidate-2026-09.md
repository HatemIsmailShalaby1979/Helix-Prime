# Helix Prime release-candidate record

**Status:** stabilization in progress
**Target profile:** `controlled_pilot`
**Canonical surface:** `helix-api`
**Data boundary:** synthetic or explicitly consented data only

## Candidate boundary

The candidate is intentionally narrow: one tenant, read-only integrations,
human approval for consequential actions, independent peer review, audit-chain
verification, tenant/client scope enforcement, and a tested kill switch. The
cockpit, desktop shell, `helix-app`, Ollama sidecar, and standalone engine
surfaces are diagnostic or separate deployment paths and are not implicitly
promoted with the API candidate.

## Required evidence

Run the commands in `.github/copilot-instructions.md` from a clean candidate
checkout. The evidence pack must record the exact commit SHA, dependency-lock
hash, package/image digests, test output, security scans, readiness result,
backup/restore result, and release profile. Historical test counts and prior
manifest SHAs are not candidate evidence.

The production-only gates remain hard blockers:

- signed production evidence
- certified data isolation
- external observer audit
- production deployment architecture
- disaster recovery evidence
- operational ownership
- incident/on-call ownership
- security review
- legal/privacy review

No local pilot run, self-approval, or documentation change can satisfy those
gates. A failed Docker or optional-dependency check must be recorded as
unverified or blocked, never converted into a release claim.

## Operator path

1. Restore `release/requirements.lock.txt`.
2. Run release profile, security, governance, package, and Docker checks.
3. Build and smoke-test the API image; verify `/readyz`, not only `/healthz`.
4. Run the synthetic pilot dry-run and backup/restore evidence.
5. Review generated evidence against the exact candidate SHA.
6. Promote only to the narrow controlled-pilot scope unless the independent
   production gates have genuine external evidence.

This record replaces stale narrative snapshots for the candidate process; dated
audit documents remain historical records.

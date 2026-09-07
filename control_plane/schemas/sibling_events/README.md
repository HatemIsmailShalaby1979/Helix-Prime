# Sibling Event Bus — C7

Helix Education, Study Studio and the L&D Command Center are **external services**.
They are not libraries. This directory is the entire integration surface between
them and the Helix Codex OS core.

## The boundary rule

> Sibling projects communicate through versioned event contracts only.
> Importing sibling code, vendoring sibling source, or reading a sibling's
> datastore directly is prohibited.

`boundary.py` is the executable form of that sentence. `scan_repository_imports()`
walks the tree and fails CI on any import of a sibling package.
`detect_vendored_sibling_source()` flags directories that look like a sibling was
copied in. `assert_legal_integration()` makes a new integration state, in code,
which side of each boundary it sits on — silence is not consent.

Run it:

```bash
python -m control_plane.schemas.sibling_events.boundary
```

Exit code `0` means the boundary holds.

## The four events

| Event | Direction | Owner | Meaning |
|---|---|---|---|
| `CompetencyGapDetected` | outbound | helix_prime | An operational KPI degraded and the degradation is attributable to agent performance. |
| `LearningPlanRequested` | outbound | helix_prime | Asks Helix Education to build a personalised study map for that gap. |
| `LearningArtifactReady` | inbound | ld_command_center | Training content for the request now exists. |
| `AssessmentCompleted` | inbound | study_studio | The agent was assessed; a qualification token comes back. |

The loop: a gap is detected, a plan is requested, content is produced, the agent
is assessed, and the resulting competency token feeds back into WFM staffing and
L&D coaching decisions. Each hop carries the same `correlation_id`, so a staffing
change six weeks later can still be traced to the queue breach that caused it.

## Envelope

Everything travels as a `SiblingEventEnvelope`:

```json
{
  "event_id": "sev_…",
  "event_type": "CompetencyGapDetected",
  "envelope_version": "1.0",
  "source_system": "helix_prime",
  "target_system": null,
  "tenant_id": "tenant-a",
  "client_id": "client-1",
  "correlation_id": "corr-…",
  "causation_id": null,
  "data_mode": "live",
  "data_classification": "internal",
  "occurred_at": "2026-09-07T02:00:00Z",
  "payload": { "…": "…" },
  "payload_digest": "sha256-of-canonical-json-payload"
}
```

`tenant_id`, `client_id` and `correlation_id` are mandatory. An event that cannot
say whose data it carries is dropped, not guessed at. `data_mode` travels with the
event so a plan built on sample data is never mistaken for one built on measured
operational data.

`payload_digest` is a SHA-256 over the canonical JSON of `payload` alone. A
receiver recomputes it and rejects the event on mismatch — the transport layer is
never trusted.

## JSON Schema

Published schemas live in `schemas/` and are generated from `registry.py`:

```bash
python -c "from control_plane.schemas.sibling_events import registry; print(registry.export_schemas())"
```

CI regenerates them and fails if the tree is dirty, so the published contract can
never silently drift from the Python contract. Sibling teams copy the JSON files;
they do not need this repository.

Every schema sets `additionalProperties: false`. Unknown fields are a contract
violation. Silently ignoring them is how two systems drift apart without either
one ever failing.

## Versioning

Schema version `1.0` is frozen for its lifetime. A breaking change increments the
version; consumers accept every version they were built against and reject the
rest loudly. There is no "mostly compatible" — `receive()` raises rather than
repairing a malformed event.

## Usage

```python
from control_plane.schemas.sibling_events import (
    CompetencyGapDetected, dispatch, receive,
)

gap = CompetencyGapDetected(
    gap_id="gap_001",
    tenant_id="tenant-a",
    client_id="client-1",
    agent_ref="agent-17",
    capability="aht_management",
    measured_value=0.71,
    target_value=0.85,
    severity="high",
    attribution_confidence=0.88,
    kpis_affected=["service_level"],
)
wire = dispatch(gap, correlation_id="corr-1").to_json()
# … across the bus …
event = receive(wire)
```

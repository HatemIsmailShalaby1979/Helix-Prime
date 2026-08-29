# 8. Local/Cloud Deployment Strategy

Strategy: **local-first, cloud-optional and synthetic-only**. The system runs entirely on a
developer/operator machine with no external dependencies; cloud is a constrained, opt-in
demonstration surface, not a production path.

## Local-first (default)
- No network, no credentials, no cloud calls required.
- Connectors are read-only and synthetic by construction (`mode="fake"`; restaurant connectors
  read synthetic fixtures). Writes are disabled by design (`request_write` → `executed=False`).
- The synthetic demo (`demo/synthetic_demo.py`) runs from a clean in-memory setup.

## Cloud boundary (`cloud/`, Prompt 9)
- Provider-neutral interfaces (db, object-storage, queue, secrets, identity, observability,
  scheduler, model) with **local in-memory adapters**.
- A **synthetic-only** cloud-demo profile: no live credentials, restricted API surface, usage
  limits, demo reset/shutdown, monitoring, and spend documentation.
- Missing-cloud behavior fails **safe closed** (live creds / non-synthetic / restricted-op /
  shutdown all blocked).
- Cockpit, governed memory, and metacognition are **not** migrated to cloud; local-first remains
  primary.

## Controlled pilot deployment
- The pilot/capability runtime is instantiated in-process against a `GovernedMemory`. There is no
  standalone server in this build (the cockpit shell is a separate web app that injects its own boot
  context and is not required to run the governed core).

## What is NOT claimed
- No real cloud deployment, no production infrastructure, no live multi-tenant hosting. The
  `production` release profile is intentionally `NOT_READY` (external production gates red).

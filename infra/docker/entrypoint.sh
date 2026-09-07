#!/usr/bin/env sh
set -eu

# C8: schema initialization is explicit and idempotent. The cockpit cannot
# start against an uninitialised or half-created ledger.
DB_PATH="${HELIX_DB_PATH:-/data/workflow.db}"
AUDIT_PATH="${HELIX_AUDIT_DB_PATH:-/data/audit.db}"
export DB_PATH AUDIT_PATH

python - <<'PY'
import os
from control_plane.store import Store

# Store initialization creates workflow, task and append-only audit schemas.
with Store(os.environ["DB_PATH"]) as store:
    if not store.verify_audit_chain():
        raise SystemExit("audit ledger integrity check failed during startup")
PY

exec "$@"

# Helix Codex OS — local-first enterprise runtime (C8)
#
# One image runs the deterministic control plane and Streamlit cockpit. The
# multi-stage build keeps compiler/build artifacts out of the final footprint.
# SQLite stays local by design; mount /data as the durable tenant-isolated volume.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt requirements-dev.txt pyproject.toml ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip install hatchling

# Phase 1 W4 service spine: fastapi, uvicorn, jinja2, sse-starlette, pydantic-settings, httpx.
# Installing via the pyproject extra ensures the declared bounds are respected.
COPY . .
RUN /opt/venv/bin/pip install '.[web]' \
    && /opt/venv/bin/python -m compileall -q -f . || true

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HELIX_ENV=local \
    HELIX_DB_PATH=/data/workflow.db \
    HELIX_AUDIT_DB_PATH=/data/audit.db \
    HELIX_SAMPLE_DATA_MODE=false \
    OLLAMA_HOST=http://ollama:11434 \
    HELIX_OLLAMA_ACCELERATOR=auto

RUN useradd --create-home --uid 10001 helix \
    && mkdir -p /app /data \
    && chown -R helix:helix /app /data

COPY --from=builder --chown=helix:helix /opt/venv /opt/venv
WORKDIR /app
COPY --from=builder --chown=helix:helix /build /app

# The entrypoint initializes SQLite schemas before Streamlit starts. The
# process stays unprivileged, and /data is the only writable application path.
COPY --chown=helix:helix infra/docker/entrypoint.sh /usr/local/bin/helix-entrypoint
RUN chmod 0555 /usr/local/bin/helix-entrypoint

USER helix
VOLUME ["/data"]
EXPOSE 8501 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python scripts/health_check.py --db-path "$HELIX_DB_PATH" || exit 1

ENTRYPOINT ["/usr/local/bin/helix-entrypoint"]
CMD ["streamlit", "run", "cockpit/cockpit.py", "--server.address=0.0.0.0", "--server.port=8501"]

# Helix Codex App — self-hosted deployment image (P7.4)
#
# Multi-stage build: compile dependencies in a builder stage, run the app
# as a non-root user on loopback only. SQLite stays local; /data is the
# only writable path.
#
# The app binds 127.0.0.1 by default (require_safe_defaults). Use
# network_mode: host in compose so the operator reaches
# http://127.0.0.1:8100 on the host.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt pyproject.toml ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip install hatchling

COPY . .
RUN /opt/venv/bin/pip install '.[web]' \
    && /opt/venv/bin/python -m compileall -q -f . || true

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HELIX_APP_HOST=127.0.0.1 \
    HELIX_APP_PORT=8100 \
    HELIX_APP_DB_PATH=/data/app.db \
    HELIX_APP_MEMORY_ROOT=/data/memory_stores \
    HELIX_ENV=local \
    HELIX_SAMPLE_DATA_MODE=false \
    HELIX_DB_PATH=/data/workflow.db \
    HELIX_AUDIT_DB_PATH=/data/audit.db

RUN useradd --create-home --uid 10001 helix \
    && mkdir -p /app /data \
    && chown -R helix:helix /app /data

COPY --from=builder --chown=helix:helix /opt/venv /opt/venv
WORKDIR /app
COPY --from=builder --chown=helix:helix /build /app

USER helix
VOLUME ["/data"]
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/app/healthz')"

CMD ["helix-app"]

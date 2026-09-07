# B2B Client Onboarding Automator — container image
# Local-first; Notion credentials are injected via environment at run time.
FROM python:3.12-slim

WORKDIR /app

# System deps required by pandas / scipy on slim images
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# NOTE: requirements.txt shim removed (Phase 1 W1). Install deps from root
# requirements.txt or use the unified infra/docker/Dockerfile.

COPY src/ ./src/
COPY notion_adapter/ ./notion_adapter/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Default entrypoint: the onboarding CLI (see src/main.py for commands).
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--help"]

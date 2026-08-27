# =============================================================================
# Helix Prime Ecosystem — Marketing Site
# Multi-stage: build the 5-min demo mp4 from DEMO_SCRIPT.md, then nginx-serve.
# =============================================================================

# ---- Stage 1: builder -------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /work

# Install Python deps first for better layer caching
COPY requirements-demo.txt /work/requirements-demo.txt
RUN pip install --no-cache-dir -r /work/requirements-demo.txt

# Copy the marketing site source
COPY . /work/marketing/

# Build the demo video + captions
RUN python /work/marketing/assets/build_demo.py

# ---- Stage 2: runtime (nginx static) ---------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace default config
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/conf.d/default.conf.template 2>/dev/null || true

# Copy the static site + built demo
COPY --from=builder /work/marketing/index.html /usr/share/nginx/html/index.html
COPY --from=builder /work/marketing/assets/ /usr/share/nginx/html/assets/

EXPOSE 8080

# nginx:alpine's default CMD already runs nginx in the foreground.
# Override the listen port via the conf (8080), keep the default CMD.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/index.html || exit 1

CMD ["nginx", "-g", "daemon off;"]

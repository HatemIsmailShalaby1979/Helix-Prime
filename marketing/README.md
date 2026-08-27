# Helix Prime — Marketing Portfolio

This folder markets **Helix Prime** as a digital operations team that solves real business problems.

## Contents

| Path | Purpose |
|------|---------|
| `index.html` | Marketing website (open in browser) |
| `assets/style.css` | Site styling (dark, red-accent brand theme) |
| `assets/screenshots/` | Real screenshots from test & deployment runs |
| `assets/Helix_Prime_5Min_Demo.mp4` | 5-minute demo video (built from `DEMO_SCRIPT.md`) |
| `assets/Helix_Prime_5Min_Demo.vtt` | WebVTT captions for the demo |
| `assets/screenshots/demo-poster.svg` | Poster frame for the `<video>` element |
| `assets/build_demo.py` | Builder: parses `DEMO_SCRIPT.md`, renders slides, TTS, muxes mp4 |
| `assets/build_demo.sh` | Bash wrapper around `build_demo.py` |
| `requirements-demo.txt` | Python deps for the builder (edge-tts, imageio-ffmpeg, Pillow) |
| `DEMO_SCRIPT.md` | Storytelling script for the 5-min demo |
| `Dockerfile` | Multi-stage: build the mp4, then nginx serves the static site |
| `nginx.conf` | nginx config for the static site (port 8080, gzip, caching) |
| `render.yaml` | Render.com Docker web service config |
| `azure.yaml` | Azure Developer CLI (azd) entry point |
| `infra/main.bicep` | Bicep template: Azure Static Web Apps free tier |
| `.dockerignore` | Excludes `_build/`, `.git/`, etc. from the image |
| `.env.example` | Empty template (no secrets required) |
| `README.md` | This file |

## How to View

Open `marketing/index.html` in any browser. No build step required for the site itself.

## How to (Re)build the 5-Minute Demo

```bash
cd marketing
pip install -r requirements-demo.txt
python assets/build_demo.py
```

Produces:
- `assets/Helix_Prime_5Min_Demo.mp4` (1920×1080, 5:00, ~6-8 MB)
- `assets/Helix_Prime_5Min_Demo.vtt` (chapter cue timings)

The builder:
1. Parses `DEMO_SCRIPT.md` into 5 chapters of 60 s each.
2. Renders one branded slide per chapter-second (Pillow).
3. Synthesizes narration with `edge-tts` (voice: `en-GB-RyanNeural`).
4. Muxes per-chapter mp4 + mp3 with `tpad`/`apad` to lock 60 s per chapter.
5. Concatenates into the final mp4 and emits WebVTT captions.

The Dockerfile runs the same pipeline inside the container so the deployed
artifact is regenerated from `DEMO_SCRIPT.md` on every build — no stale mp4.

## Brand Rules (from Constitution 000)

- Tagline: **"An AI Organization. Not a tool. Not a chatbot. Not a dashboard."**
- Accent colour: `#e94560` (Helix red)
- Author credit mandatory: **Hatem Shalaby**
- Every claim must be traceable to `MASTER_STORY.md` or to a test run executed and observed in the same session. No claim may reference a "proof ledger" — no such thing exists. (See `CHANGE_LOG.md` for the removal of fabricated proof-ledger and customer claims.)

## Screenshots

> **Truth note:** Four SVG "screenshots" that presented fabricated test runs
> (`tests-command-center.svg`, `tests-helix-story.svg`, 42/38 passed) and fabricated
> deployment configs (`deploy-render.svg`, `deploy-azure.svg`) were deleted on
> 2026-08-04. They showed paths and services that do not exist in this repository.
> Only `demo-poster.svg` (a brand poster frame) remains. Screenshots may be added
> back only from real, executed runs in this repository.

## Deployment (Standalone Static Site)

### Render.com
```bash
cd marketing
# Push the repo, then in Render dashboard: New -> Blueprint -> point at render.yaml
```
Health check: `GET /index.html` (returns 200 OK).
Video: `GET /assets/Helix_Prime_5Min_Demo.mp4` (returns 200 OK, ~6-8 MB).

### Azure Static Web Apps (free tier)
```bash
cd marketing
azd up
```
Provisions Azure Static Web Apps, deploys the static bundle, returns the
public URL. Health check via the SWA default `200 OK` on `/`.

### Local Docker
```bash
docker build -t helix-prime-marketing marketing/
docker run --rm -p 8080:8080 helix-prime-marketing
# Open http://localhost:8080
curl -I http://localhost:8080/assets/Helix_Prime_5Min_Demo.mp4   # expect 200
```

## Demo Video

5-minute script in `DEMO_SCRIPT.md`. Chapters: Story → Team → Engines → Proof → Deployment.

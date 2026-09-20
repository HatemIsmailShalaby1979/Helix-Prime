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
| `helix-codex-deck/video/Helix_Codex_5Min_Animated.html` | 5-minute animated film — one file, plays in any browser, narration built in |
| `helix-codex-deck/video/Helix_Codex_5Min_Animated.vtt` | WebVTT captions for the animated film |
| `helix-codex-deck/video/build_captions.py` | Regenerates the caption track from the film's own scene data |
| `helix-codex-deck/video/build_voice.py` | Renders the narration pack (`audio/beat-NNN.mp3`) |
| `helix-codex-deck/video/retime_beats.py` | Spaces the film's beats to match the narration |
| `helix-codex-deck/video/export_video.py` | Renders the film to `Helix_Codex_5Min_Animated.mp4` |
| `helix-codex-deck/video/capture_frames.mjs` | Headless frame capture used by the exporter |
| `helix-codex-deck/video/verify_audio.mjs` | Headless-Chrome check of the film's sound, start gate and deep links |
| `helix-codex-deck/video/verify_sync.py` | Checks the exported MP4's narration against its caption track |
| `helix-codex-deck/images/0N-*.html` | Three 1920×1080 stills drawn from the deck's own content |
| `helix-codex-deck/images/0N-*.png` | The same three stills rendered at 3840×2160 (4K) |
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

## The 5-Minute Animated Film

`helix-codex-deck/video/Helix_Codex_5Min_Animated.html` is a second, newer 5-minute
film: 17 scenes across 5 acts, 1920×1080, animated in the browser. It is a single
self-contained file with no build step and no dependencies — open it and it plays.
It is **not** the same artifact as `assets/Helix_Prime_5Min_Demo.mp4`; that one is
chapter-based slides, this one is a motion film.

Controls: `Space` play/pause · `←` `→` scenes · `M` sound · `R` restart ·
`C` hide the chrome · `S` script and storyboard · `F` fullscreen.

Deep links jump to a moment and hold, which is how the layout is verified:
`…Animated.html#t=125` (seconds) or `…#s=7` (scene).

**Narration.** The film ships with a voice. It looks for `audio/beat-NNN.mp3` — one
clip per narration beat — and falls back to the browser's own speech synthesis for
any clip that is missing, so the film always narrates. Render the pack with:

```bash
cd marketing/helix-codex-deck/video
python build_voice.py            # edge-tts, no API key, voice en-GB-RyanNeural
python build_voice.py --check    # measure the pack and flag clips that overrun
python build_voice.py --auto     # render so every scene's narration fits its duration
python retime_beats.py --apply   # space the beats to match the narration
python build_voice.py --engine eleven   # ElevenLabs instead (needs ELEVENLABS_API_KEY)
```

`build_voice.py` reads the beats straight out of the film, so the clips can never
drift from the script. `build_captions.py` does the same for the caption track.

**Pacing.** The film's scene lengths are fixed by its acts, so the narration has to
fit them — and a scene's beats can only all fit if that scene's total narration is
no longer than the scene itself. `--auto` picks the speech rate per scene (scenes
with room stay natural, over-written ones are read faster by exactly their
overrun), and `retime_beats.py` then sets each beat time proportional to its clip
length, `t_i = D · cumsum(L) / sum(L)`. That gives every line a window matching its
own delivery, so reveals land on the words instead of a stopwatch. Both scripts
refuse to write a film that breaks its timing invariants.

`verify_audio.mjs` drives headless Chrome to confirm the start gate, the sound
toggle, the mp3-first-then-synthesis fallback and the deep links.

**MP4 export.** The film is a browser artifact; to share or upload it, render it to
a file:

```bash
python export_video.py                  # full 5:00 -> Helix_Codex_5Min_Animated.mp4
python export_video.py --max-seconds 20 --out test.mp4   # smoke test
python export_video.py --skip-capture   # re-mux existing frames
```

`export_video.py` builds the audio bed by placing every narration clip at its beat's
absolute time (plus the scene-change chime, which is generated rather than captured
because the browser makes it with WebAudio and it never reaches an audio device in
headless mode), drives the real film through `capture_frames.mjs` to record a
variable-rate frame sequence with per-frame timestamps, then resamples to 30 fps and
muxes H.264 + AAC. Capture starts *before* playback so frame one is 0:00 and the bed
lines up — the capture reports its own drift, which lands around 0.1 s over the full
five minutes. The film exposes `window.__film` for this (and for the test harness).

The delivered `Helix_Codex_5Min_Animated.mp4` is **300.00 s, 1920×1080, H.264 30 fps,
AAC 44.1 kHz stereo, 62 MB**, mixed to −16.4 LUFS with a −4.3 dB peak — the streaming
loudness target, so it plays at a sensible level without touching the volume. It carries
the 78-cue caption track as **soft English subtitles**, so the file stands on its own
for someone who never sees the `.vtt` beside it; players leave them off unless asked.
The file is a build output and is not committed; one command rebuilds it.

The export verifies what it produced. `--skip-capture` re-muxes an existing frame
directory, and every run ends by probing the output and refusing to hand over a file
whose *picture* is shorter than the film — a container duration alone is satisfied by
the audio track, so a video that stops early still reports full length. Capture
stopped early, or frames lost to a denied write, are reported rather than quietly
trimmed; a missing frame is held for its recorded duration so the film keeps its
timing.

`verify_sync.py` is a separate check on the delivered file, comparing two pipelines
that were built independently: the caption track comes from the film's beat times,
while the audio is rendered from the script and then placed at those same times. If
either drifted, the two would stop agreeing. It decodes the MP4's own audio into a
100 ms level envelope and asserts that every caption window contains speech and that
no speech runs uncaptioned:

```bash
python verify_sync.py
# audio: 300.0s in 100ms frames, speech threshold -46.6 dBFS, 205.3s above it
# captions: 78 cues, 0.00s to 300.00s
# narration onset vs caption start: median +0.10s, worst +0.45s
# PASS: every caption has speech under it, and no speech runs uncaptioned
```

That check is what caught the caption splitter producing orphan fragments — a cue
reading just `to.` with a 0.15 s window. `build_captions.py` now balances a wrapped
sentence instead of filling each line greedily, and merges any chunk too short to
read, so the shortest cue in the track is 1.65 s.

## Three Stills from the Deck

`helix-codex-deck/images/` holds three 1920×1080 stills that carry the deck's message
in one frame each — for a README header, a social card, a slide, or a pitch PDF:

| File | Claim |
|---|---|
| `01-one-app.html` | **One app for the whole company** — the eight surfaces, plus the two restricted ones |
| `02-ai-organization.html` | **An AI organization, not a chatbot** — all nine roles with their real titles |
| `03-governance.html` | **Governance you can point at** — the five-step rail, the three principles, the cockpit numbers |

They are typographic compositions built from the deck's own palette (`#e94560`), type
scale and figures — not AI-generated illustrations — so every number on them is a
number the project actually produces. Each is one self-contained HTML file; the PNG
is a 4K render of it:

```bash
cd marketing/helix-codex-deck/images
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu \
  --hide-scrollbars --run-all-compositor-stages-before-draw --virtual-time-budget=2500 \
  --window-size=1920,1080 --force-device-scale-factor=2 \
  --user-data-dir="$PWD/_chrome" --screenshot="$PWD/01-one-app.png" \
  "file:///$PWD/01-one-app.html"
```

Edit the HTML, re-run that one command, and the PNG updates.

## Brand Rules (from Constitution 000)

- Tagline: **"An AI Organization. Not a tool. Not a chatbot. Not a dashboard."**
- Accent colour: `#e94560` (Helix red)
- Author credit mandatory: **Hatem Shalaby**
- Every claim must be traceable to `MASTER_STORY.md` or to a test run executed and observed in the same session. No claim may reference a "proof ledger" — no such thing exists. (See `CHANGELOG.md` for the removal of fabricated proof-ledger and customer claims.)

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

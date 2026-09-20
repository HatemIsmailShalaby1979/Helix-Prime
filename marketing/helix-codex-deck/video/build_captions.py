"""
Build a WebVTT caption track for Helix_Codex_5Min_Animated.html.

The film's scene/beat data is the single source of truth, so captions are read
straight out of the HTML rather than retyped. Extraction is delegated to Node
because the data is a JavaScript array literal.

Pipeline:
  1. Extract the SCENES array from the film via `node -e`.
  2. Give every narration beat the time window that runs to the next beat.
  3. Split each beat into readable caption chunks (sentences, then word wrap).
  4. Distribute the window across the chunks in proportion to their length.
  5. Write Helix_Codex_5Min_Animated.vtt.

Output:
  marketing/helix-codex-deck/video/Helix_Codex_5Min_Animated.vtt
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILM = HERE / "Helix_Codex_5Min_Animated.html"
OUT = HERE / "Helix_Codex_5Min_Animated.vtt"

MAX_CHARS = 84  # roughly two 42-character caption lines
MIN_CUE = 1.2  # seconds; a shorter cue is a flash, not a caption


def extract_scenes() -> list[dict]:
    """Evaluate the SCENES array in the film and return it as JSON."""
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        raise RuntimeError("node is required to extract the scene data (the film's data is JS)")

    js = (
        "const fs=require('fs');"
        "const src=fs.readFileSync(process.argv[1],'utf8');"
        "const a=src.indexOf('const SCENES = [');"
        "const b=src.indexOf('/* ============================== engine');"
        "const SCENES=eval(src.slice(a,b).trim().replace('const SCENES =',''));"
        "process.stdout.write(JSON.stringify(SCENES.map(s=>({id:s.id,act:s.act,"
        "start:s.start,dur:s.dur,title:s.title,beats:s.beats}))));"
    )
    res = subprocess.run(
        [node, "-e", js, str(FILM)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"scene extraction failed: {res.stderr[-1500:]}")
    return json.loads(res.stdout)


def split_sentences(text: str) -> list[str]:
    """Split on sentence enders, keeping the punctuation attached."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def wrap_words(text: str, limit: int) -> list[str]:
    """Wrap a sentence into as few lines as fit `limit`, balanced rather than greedy.

    Greedy wrapping leaves a short orphan tail: a 87-character sentence becomes an
    83-character cue followed by a 3-character one ("to."). Cue timing below is
    proportional to length, so that orphan is shown for a tenth of a second - an
    unreadable flash, and the one cue in the track whose timing is furthest from
    what the narrator actually says. Splitting near the middle keeps every cue
    long enough to read and lands the proportional split nearer the real speech.
    """
    if len(text) <= limit:
        return [text]

    parts = math.ceil(len(text) / limit)
    target = len(text) / parts
    out: list[str] = []
    cur = ""
    for word in text.split():
        if not cur:
            cur = word
            continue
        candidate = f"{cur} {word}"
        if len(candidate) <= target:
            cur = candidate
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def merge_short_chunks(chunks: list[str], span: float) -> list[str]:
    """Merge any cue too short to read into its neighbour.

    A cue's share of the window is its share of the beat's characters, so a very
    short chunk becomes a very short cue. Merge the shortest into the previous
    chunk and repeat, so no cue in the track is a flash.
    """
    out = list(chunks)
    while len(out) > 1:
        total = sum(len(c) for c in out) or 1
        idx = min(range(len(out)), key=lambda i: len(out[i]))
        if span * len(out[idx]) / total >= MIN_CUE:
            break
        if idx == 0:
            out[1] = f"{out[0]} {out[1]}"
            del out[0]
        else:
            out[idx - 1] = f"{out[idx - 1]} {out[idx]}"
            del out[idx]
    return out


def to_chunks(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Sentences merged up to `limit`, then hard-wrapped where a sentence is too long."""
    chunks: list[str] = []
    cur = ""
    for sentence in split_sentences(text):
        if len(sentence) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(wrap_words(sentence, limit))
            continue
        candidate = f"{cur} {sentence}".strip()
        if len(candidate) <= limit:
            cur = candidate
        else:
            if cur:
                chunks.append(cur)
            cur = sentence
    if cur:
        chunks.append(cur)
    return chunks or [text]


def fmt(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def build() -> int:
    scenes = extract_scenes()
    total = max(s["start"] + s["dur"] for s in scenes)

    lines = [
        "WEBVTT",
        "",
        "NOTE Helix Codex - 5-Minute Animated Film",
        "NOTE Hatem Shalaby - Helix Codex OS - 2026",
        f"NOTE {len(scenes)} scenes across 5 acts, runtime {int(total // 60)}:{int(total % 60):02d}",
        "NOTE Generated by build_captions.py from the film's own scene data. Do not hand-edit.",
        "",
    ]

    cue_count = 0
    durations: list[float] = []
    for scene_index, scene in enumerate(scenes):
        beats = scene["beats"]
        lines.append(f"NOTE SCENE {scene_index + 1:02d} · ACT {scene['act']} · {scene['title']}")
        lines.append("")

        for i, beat in enumerate(beats):
            window_start = scene["start"] + beat["t"]
            window_end = (
                scene["start"] + beats[i + 1]["t"]
                if i + 1 < len(beats)
                else scene["start"] + scene["dur"]
            )
            span = max(0.8, window_end - window_start)
            chunks = merge_short_chunks(to_chunks(beat["line"]), span)

            weights = [len(c) for c in chunks]
            total_weight = sum(weights) or 1
            cursor = window_start
            for chunk, weight in zip(chunks, weights, strict=True):
                duration = span * (weight / total_weight)
                start, end = cursor, cursor + duration
                cursor = end
                cue_count += 1
                durations.append(duration)
                lines.append(str(cue_count))
                lines.append(f"{fmt(start)} --> {fmt(end)}")
                lines.append(chunk)
                lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"scenes: {len(scenes)} | cues: {cue_count} | runtime {int(total // 60)}:{int(total % 60):02d}"
    )
    print(
        f"cue duration: shortest {min(durations):.2f}s, median {sorted(durations)[len(durations) // 2]:.2f}s "
        f"(floor is {MIN_CUE:.1f}s)"
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())

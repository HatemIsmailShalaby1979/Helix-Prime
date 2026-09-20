"""
Re-space the film's narration beats proportionally to how long each line takes.

Why this exists
---------------
Helix_Codex_5Min_Animated.html spaces its beats by visual choreography: each
beat has a hand-picked `t` inside its scene. The narration does not care about
choreography - a line takes as long as it takes. When a beat's window is shorter
than its line, the line gets cut off mid-sentence.

The fix is to derive the beat times from the narration instead of guessing them.
Within a scene of duration D and beats of clip length L, set

    t_i = D * (L_0 + ... + L_(i-1)) / sum(L)

which gives every beat a window of exactly D * L_i / sum(L). Every line then has
a window proportional to its own delivery, and the whole scene is compressed by
one uniform factor (sum(L) / D) rather than squeezing a single unlucky line.

The window a beat *shows* is unchanged in meaning - it still reveals the same
content at the same beat - it just happens on the narration's clock.

Run `build_voice.py --auto` first: it renders each scene so its total narration
fits its duration, which is the precondition for this spacing to fit.

Usage:
  python retime_beats.py              # show the plan, change nothing
  python retime_beats.py --apply      # rewrite the beat times and the captions
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from build_captions import FILM, build as build_captions, extract_scenes
from build_voice import AUDIO, clip_name, ffprobe_seconds, flatten_beats

SCENE_RE = re.compile(r'id:"([^"]+)",\s*act:(\d+),\s*start:([\d.]+),\s*dur:([\d.]+),\s*title:"([^"]+)"')
BEAT_RE = re.compile(r"^(\s*\{t:)([\d.]+)(, line:.*)$")


def read_plan(lines: list[str]) -> list[dict]:
    """Walk the SCENES array and group each scene with the beat lines it owns."""
    scenes: list[dict] = []
    current: dict | None = None
    for i, line in enumerate(lines):
        beat = BEAT_RE.match(line)
        if beat:
            if current is None:
                raise SystemExit(f"beat outside any scene at line {i + 1}")
            current["beats"].append((i, float(beat.group(2))))
            continue
        scene = SCENE_RE.search(line)
        if scene:
            current = {
                "title": scene.group(5),
                "dur": float(scene.group(4)),
                "beats": [],
            }
            scenes.append(current)
    return scenes


def new_times(lengths: list[float], duration: float) -> list[float]:
    """Proportional beat times: t_i = D * cumsum(L[:i]) / sum(L)."""
    total = sum(lengths)
    if total <= 0:
        raise SystemExit("no clip lengths - render the narration pack first")
    times, cum = [], 0.0
    for length in lengths:
        times.append(round(duration * cum / total, 1))
        cum += length
    times[0] = 0.0
    for i in range(1, len(times)):
        if times[i] <= times[i - 1]:
            times[i] = round(times[i - 1] + 0.1, 1)
    if times[-1] >= duration:
        times[-1] = round(duration - 0.1, 1)
    return times


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="rewrite the film and regenerate the captions")
    args = ap.parse_args()

    source = FILM.read_text(encoding="utf-8")
    lines = source.splitlines()

    scenes_in_file = read_plan(lines)
    beats = flatten_beats(extract_scenes())
    if sum(len(s["beats"]) for s in scenes_in_file) != len(beats):
        raise SystemExit(
            f"the film has {sum(len(s['beats']) for s in scenes_in_file)} beats but the "
            f"scene data reports {len(beats)} - refusing to guess"
        )

    # clip lengths in the same order as the beats appear in the file
    lengths = [ffprobe_seconds(AUDIO / clip_name(b["n"])) or 0.0 for b in beats]

    cursor = 0
    worst_before = worst_after = 0.0
    edits: list[tuple[int, str]] = []

    print(f"{'scene':44s} {'dur':>5s} {'narr':>6s} {'ratio':>6s}  {'worst window overrun':>21s}")
    for scene in scenes_in_file:
        count = len(scene["beats"])
        group = lengths[cursor : cursor + count]
        group_beats = beats[cursor : cursor + count]
        cursor += count

        old = [t for _, t in scene["beats"]]
        new = new_times(group, scene["dur"])

        # window each beat gets, old vs new, against the clip it must hold
        def worst(times: list[float]) -> float:
            out = 0.0
            for i, (beat, length) in enumerate(zip(group_beats, group, strict=True)):
                end = times[i + 1] if i + 1 < len(times) else scene["dur"]
                out = max(out, length - (end - times[i]))
            return out

        wb, wa = worst(old), worst(new)
        worst_before, worst_after = max(worst_before, wb), max(worst_after, wa)

        total = sum(group)
        flag = "OK" if wa <= 0.25 else "OVER"
        print(f"{scene['title'][:44]:44s} {scene['dur']:4.0f}s {total:5.1f}s "
              f"{total / scene['dur']:5.2f}x  {wb:6.2f}s -> {wa:5.2f}s  {flag}")

        for (line_index, _), value in zip(scene["beats"], new, strict=True):
            match = BEAT_RE.match(lines[line_index])
            edits.append((line_index, f"{match.group(1)}{value:.1f}{match.group(3)}"))

    print(f"\nworst window overrun across the film: {worst_before:.2f}s -> {worst_after:.2f}s")

    problems = []
    for scene in scenes_in_file:
        times = [t for _, t in scene["beats"]]
        if any(t < 0 for t in times):
            problems.append(f"{scene['title']}: negative beat time")
        if any(t >= scene["dur"] for t in times):
            problems.append(f"{scene['title']}: a beat starts at or after the scene ends")
        if any(b <= a for a, b in zip(times, times[1:])):
            problems.append(f"{scene['title']}: beat times are not strictly increasing")
    if problems:
        for problem in problems:
            print(f"  INVALID  {problem}")
        raise SystemExit("refusing to write an invalid film")

    if not args.apply:
        print("\ndry run - re-run with --apply to rewrite the film")
        return 0

    for line_index, replacement in edits:
        lines[line_index] = replacement
    FILM.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rewrote {len(edits)} beat times in {FILM.name}")

    build_captions()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

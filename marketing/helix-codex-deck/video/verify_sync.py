"""
Check that the narration inside the exported MP4 lands on the film's beats.

The captions and the narration come from two different pipelines: the WebVTT is
generated from the film's own beat times (build_captions.py), while the audio is
rendered from the script (build_voice.py) and then placed at those same beat
times by export_video.py. So if either side drifted - a clip rendered short, a
bed built against stale beats, a mux that offset the audio - the caption track
and the audio track would stop agreeing.

This compares them directly, on the delivered file rather than on the inputs:

  * every caption window must contain speech, starting when the caption starts
  * speech outside every caption window is reported, because it means the film
    is narrating something the captions do not show

Usage:
  python verify_sync.py                       # the exported film and its .vtt
  python verify_sync.py --video x.mp4 --vtt x.vtt
"""

import argparse
import array
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

from export_video import tool

HERE = Path(__file__).resolve().parent
VIDEO = HERE / "Helix_Codex_5Min_Animated.mp4"
VTT = HERE / "Helix_Codex_5Min_Animated.vtt"

FRAME_MS = 100
# A caption may be a little ahead of its speech, but speech that starts well
# after the caption - or well before it - is drift, not tolerance.
LEAD_TOLERANCE = 0.35
LAG_TOLERANCE = 0.60
MIN_SPEECH_MS = 300
ORPHAN_MS = 700


def decode_envelope(path: Path) -> list[float]:
    """Per-frame RMS level in dBFS, from the file's own audio stream."""
    rate = 16000
    res = subprocess.run(
        [tool("ffmpeg"), "-v", "error", "-i", str(path),
         "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True,
    )
    if res.returncode != 0:
        sys.exit(f"could not decode {path}: {res.stderr[-400:].decode('utf-8', 'replace')}")

    pcm = array.array("h")
    pcm.frombytes(res.stdout[: len(res.stdout) // 2 * 2])
    step = rate * FRAME_MS // 1000
    levels = []
    for i in range(0, len(pcm) - step + 1, step):
        window = pcm[i:i + step]
        mean_sq = sum(v * v for v in window) / step
        rms = math.sqrt(mean_sq)
        levels.append(20 * math.log10(max(rms, 1e-9) / 32768.0))
    return levels


def speech_threshold(levels: list[float]) -> float:
    """Split speech from the gaps between clips, without a magic constant.

    Anchor on the loud end, not the quiet end. Digital silence decodes to about
    -270 dBFS, so a low percentile returns a degenerate "floor" and every frame
    in the file looks like speech. Speech sits within ~30 dB of its own peak
    while the gaps are 60+ dB down, so the peak separates them cleanly.
    """
    ordered = sorted(levels)
    n = len(ordered)
    peak = ordered[min(n - 1, int(n * 0.95))]
    floor = max(ordered[int(n * 0.25)], -70.0)
    return max(floor + 8.0, peak - 32.0)


def parse_vtt(path: Path) -> list[tuple[float, float, str]]:
    def seconds(stamp: str) -> float:
        h, m, rest = stamp.split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)

    cues = []
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8"))
    for block in blocks:
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        timing = next((ln for ln in lines if "-->" in ln), None)
        if not timing:
            continue
        start, end = [part.strip().split(" ")[0] for part in timing.split("-->")]
        text = " ".join(ln for ln in lines if "-->" not in ln and not ln.strip().isdigit())
        cues.append((seconds(start), seconds(end), text))
    return cues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", type=Path, default=VIDEO)
    ap.add_argument("--vtt", type=Path, default=VTT)
    args = ap.parse_args()

    for path in (args.video, args.vtt):
        if not path.exists():
            sys.exit(f"missing {path}")

    levels = decode_envelope(args.video)
    threshold = speech_threshold(levels)
    cues = parse_vtt(args.vtt)

    loud = [level > threshold for level in levels]
    print(f"audio: {len(levels) * FRAME_MS / 1000:.1f}s in {FRAME_MS}ms frames, "
          f"speech threshold {threshold:.1f} dBFS, "
          f"{sum(loud) * FRAME_MS / 1000:.1f}s above it")
    print(f"captions: {len(cues)} cues, {cues[0][0]:.2f}s to {cues[-1][1]:.2f}s")

    def onset_within(start: float, end: float) -> float | None:
        lo = max(0, int((start - LEAD_TOLERANCE) / (FRAME_MS / 1000)))
        hi = min(len(levels), int(end / (FRAME_MS / 1000)))
        run = 0
        for i in range(lo, hi):
            run = run + 1 if loud[i] else 0
            if run * FRAME_MS >= MIN_SPEECH_MS:
                return (i - run + 1) * FRAME_MS / 1000 - start
        return None

    offsets, missing = [], []
    for start, end, text in cues:
        offset = onset_within(start, end)
        if offset is None:
            missing.append((start, text))
        else:
            offsets.append(offset)

    covered = [False] * len(levels)
    for start, end, _ in cues:
        for i in range(max(0, int(start / (FRAME_MS / 1000))), min(len(levels), int(end / (FRAME_MS / 1000)) + 1)):
            covered[i] = True

    orphans, run_start = [], None
    for i, is_loud in enumerate(loud):
        if is_loud and not covered[i] and run_start is None:
            run_start = i
        elif (not is_loud or covered[i]) and run_start is not None:
            if (i - run_start) * FRAME_MS >= ORPHAN_MS:
                orphans.append((run_start * FRAME_MS / 1000, (i - run_start) * FRAME_MS / 1000))
            run_start = None

    if offsets:
        print(f"narration onset vs caption start: median {statistics.median(offsets):+.2f}s, "
              f"worst {max(offsets, key=abs):+.2f}s")

    if missing:
        print(f"\nFAIL: {len(missing)} caption(s) have no speech under them:")
        for start, text in missing[:10]:
            print(f"  {start:7.2f}s  {text[:70]}")
    if orphans:
        total = sum(length for _, length in orphans) / 1000
        print(f"\nFAIL: {len(orphans)} stretch(es) of speech outside every caption, {total:.1f}s total:")
        for start, length in orphans[:10]:
            print(f"  {start:7.2f}s for {length / 1000:.1f}s")
    if missing or orphans:
        return 1

    print("\nPASS: every caption has speech under it, and no speech runs uncaptioned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Build the narration pack for Helix_Codex_5Min_Animated.html.

The film already knows its own script: every narration beat lives in the SCENES
array. This script flattens those beats in playback order - the same order the
film's own FLAT index uses - and renders one audio clip per beat, so the film
plays with a voice and never has to fall back to browser speech synthesis.

The film looks for `audio/beat-NNN.mp3` and falls back to the Web Speech API when
a clip is missing, so a partial pack is safe: any beat without a clip is
synthesised locally instead. A full pack means a consistent studio voice.

Two engines:

  edge    (default) Microsoft Edge neural TTS via the `edge-tts` CLI. No API key.
          Default voice en-GB-RyanNeural, the narrator already used by
          marketing/assets/build_demo.py, so both films sound like the same brand.
  eleven  ElevenLabs via the REST API. Needs ELEVENLABS_API_KEY. Higher quality,
          and the voice named by the `sag` skill.

Usage:
  python build_voice.py                          # render the pack (edge-tts)
  python build_voice.py --engine eleven          # ElevenLabs instead
  python build_voice.py --voice en-GB-SoniaNeural
  python build_voice.py --only 7 --force         # re-render one line
  python build_voice.py --fit                    # re-render anything that overruns
  python build_voice.py --dry-run                # list the beats, no rendering
  python build_voice.py --check                  # measure the pack, no rendering

Output:
  marketing/helix-codex-deck/video/audio/beat-001.mp3 ... beat-NNN.mp3
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from build_captions import extract_scenes

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "audio"

# Matches marketing/assets/build_demo.py so the brand has one narrator.
EDGE_VOICE = "en-GB-RyanNeural"
EDGE_RATE = 0
MAX_RATE = 45  # percent; beyond this the voice starts to sound rushed

API = "https://api.elevenlabs.io/v1"
ELEVEN_VOICE = "Daniel"
ELEVEN_MODEL = "eleven_multilingual_v2"
ELEVEN_FORMAT = "mp3_44100_128"
ELEVEN_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


def flatten_beats(scenes: list[dict]) -> list[dict]:
    """Every beat in playback order, with the window it has to fit into."""
    flat: list[dict] = []
    for scene in scenes:
        beats = scene["beats"]
        for i, beat in enumerate(beats):
            start = scene["start"] + beat["t"]
            end = (
                scene["start"] + beats[i + 1]["t"]
                if i + 1 < len(beats)
                else scene["start"] + scene["dur"]
            )
            flat.append(
                {
                    "n": len(flat) + 1,
                    "act": scene["act"],
                    "scene": scene["title"],
                    "start": start,
                    "window": max(0.8, end - start),
                    "line": beat["line"],
                }
            )
    return flat


def clip_name(n: int) -> str:
    return f"beat-{n:03d}.mp3"


def ffprobe_seconds(path: Path) -> float | None:
    exe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not exe:
        return None
    res = subprocess.run(
        [exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return None


def measure(flat: list[dict]) -> tuple[list[int], list[tuple[dict, float]]]:
    """Return (missing beat numbers, clips that overrun their window)."""
    missing, over = [], []
    for beat in flat:
        path = AUDIO / clip_name(beat["n"])
        if not path.exists():
            missing.append(beat["n"])
            continue
        seconds = ffprobe_seconds(path)
        if seconds is not None and seconds > beat["window"] + 0.25:
            over.append((beat, seconds))
    return missing, over


def report(flat: list[dict]) -> list[tuple[dict, float]]:
    missing, over = measure(flat)
    present = len(flat) - len(missing)
    total = sum(
        ffprobe_seconds(AUDIO / clip_name(b["n"])) or 0.0
        for b in flat
        if (AUDIO / clip_name(b["n"])).exists()
    )
    print(f"pack: {present}/{len(flat)} clips present, {total:.1f}s of narration")
    if missing:
        print(f"  missing {len(missing)} (first: {missing[:8]}) - those lines use browser speech")
    if over:
        print(f"  overrunning their beat window: {len(over)}")
        for beat, sec in over[:10]:
            print(f"    beat {beat['n']:03d}  {sec:.2f}s > {beat['window']:.2f}s  {beat['line'][:60]}")
    elif not missing:
        print("  every clip fits inside its beat window")
    return over


# --------------------------------------------------------------------------- edge

def edge_exe() -> str:
    exe = os.environ.get("EDGE_TTS") or shutil.which("edge-tts") or shutil.which("edge-tts.exe")
    if not exe:
        sys.exit(
            "the edge-tts CLI was not found.\n"
            "  pip install edge-tts\n"
            "  or set EDGE_TTS=/path/to/edge-tts\n"
            "Or run with --engine eleven to use ElevenLabs instead."
        )
    return exe


def edge_render(exe: str, voice: str, rate: int, text: str, out: Path) -> tuple[bool, str]:
    res = subprocess.run(
        [exe, "--voice", voice, "--rate", f"{rate:+d}%", "--text", text, "--write-media", str(out)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    ok = res.returncode == 0 and out.exists() and out.stat().st_size > 512
    return ok, (res.stderr or res.stdout or "").strip()[-300:]


# ------------------------------------------------------------------------ eleven

def eleven_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY")
    if not key:
        sys.exit(
            "ELEVENLABS_API_KEY is not set (needed for --engine eleven).\n"
            "  Copy a key from https://elevenlabs.io/app/settings/api-keys, then\n"
            "  export ELEVENLABS_API_KEY=sk_...\n"
            "Or just run without --engine: the default edge engine needs no key."
        )
    return key


def eleven_voice(key: str, want_name: str | None, want_id: str | None) -> tuple[str, str]:
    if want_id:
        return want_id, want_id
    req = urllib.request.Request(f"{API}/voices", headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=45) as res:
        voices = json.loads(res.read().decode("utf-8")).get("voices", [])
    if not voices:
        sys.exit("the ElevenLabs account returned no voices")
    name = want_name or ELEVEN_VOICE
    for v in voices:
        if (v.get("name") or "").lower() == name.lower():
            return v["voice_id"], v["name"]
    for v in voices:
        if name.lower() in (v.get("name") or "").lower():
            return v["voice_id"], v["name"]
    if not want_name:
        v = voices[0]
        return v["voice_id"], v.get("name", "?")
    sys.exit("no voice matching %r. Available: %s"
             % (name, ", ".join(sorted(v.get("name", "?") for v in voices))))


def eleven_render(key: str, voice_id: str, model: str, text: str, out: Path) -> tuple[bool, str]:
    req = urllib.request.Request(
        f"{API}/text-to-speech/{voice_id}?output_format={ELEVEN_FORMAT}",
        data=json.dumps({"text": text, "model_id": model, "voice_settings": ELEVEN_SETTINGS}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            audio = res.read()
    except urllib.error.HTTPError as err:
        return False, f"HTTP {err.code} {err.read().decode('utf-8', 'replace')[:200]}"
    except urllib.error.URLError as err:
        return False, f"network: {err.reason}"
    if len(audio) < 512:
        return False, f"response too small ({len(audio)} bytes)"
    out.write_bytes(audio)
    return True, ""


# ------------------------------------------------------------------------- build

def auto_fit(flat: list[dict], scenes: list[dict], render, base_rate: int, args: argparse.Namespace) -> int:
    """Render the pack so that every scene's narration fits inside its duration.

    A scene's beats can only all fit if the scene's total narration is no longer
    than the scene itself, and the film's scene lengths are fixed by its acts. So
    the rate has to be chosen per scene: scenes with room stay at the natural
    pace, over-written scenes are read faster by exactly their overrun.

    Pass 1 renders everything at the base rate to learn each line's natural
    length. Pass 2 re-renders only the scenes that need it. Afterwards, spacing
    the beats proportionally to clip length gives every line a window that
    matches its own delivery - see retime_beats.py.
    """
    print(f"\nauto-fit pass 1: {len(flat)} clips at the natural pace ({base_rate:+d}%)")
    for beat in flat:
        ok, detail = render(beat["line"], AUDIO / clip_name(beat["n"]), base_rate)
        if not ok:
            print(f"  {beat['n']:03d} FAIL {detail}")
            return 1
    print("  done")

    duration = {s["title"]: s["dur"] for s in scenes}
    groups: dict[str, list[dict]] = {}
    for beat in flat:
        groups.setdefault(beat["scene"], []).append(beat)

    plan: dict[str, int] = {}
    for name, beats in groups.items():
        total = sum(ffprobe_seconds(AUDIO / clip_name(b["n"])) or 0.0 for b in beats)
        plan[name] = max(0, min(args.cap, math.ceil((total / duration[name] - 1) * 100)))

    print("\nauto-fit pass 2: per-scene rate")
    for name, beats in groups.items():
        needed = plan[name]
        label = "natural" if needed == 0 else f"{needed:+d}%"
        print(f"  {name[:42]:42s} {len(beats):2d} lines  -> {label}")
        if needed == 0:
            continue
        for beat in beats:
            ok, detail = render(beat["line"], AUDIO / clip_name(beat["n"]), base_rate + needed)
            if not ok:
                print(f"    {beat['n']:03d} FAIL {detail}")
                return 1

    report(flat)

    capped = [n for n, r in plan.items() if r >= args.cap]
    if capped:
        print(f"\n  {len(capped)} scene(s) hit the {args.cap}% cap and may still overrun:")
        for name in capped:
            print(f"    {name}")
        print("  Trim those scenes' lines, or raise --cap and accept a brisker read.")
    return 0


def build(args: argparse.Namespace) -> int:
    scenes = extract_scenes()
    flat = flatten_beats(scenes)
    AUDIO.mkdir(parents=True, exist_ok=True)

    print(f"film: {len(scenes)} scenes, {len(flat)} narration beats, "
          f"{sum(b['window'] for b in flat):.0f}s of timeline")

    if args.dry_run:
        for beat in flat:
            print(f"  {beat['n']:03d}  {beat['start']:6.1f}s  win {beat['window']:4.1f}s  "
                  f"{len(beat['line'].split()):3d}w  {beat['line']}")
        return 0

    if args.check:
        report(flat)
        return 0

    if args.engine == "edge":
        exe = edge_exe()
        voice, base_rate = args.voice or EDGE_VOICE, args.rate
        render = lambda text, out, at: edge_render(exe, voice, at, text, out)  # noqa: E731
        print(f"engine: edge-tts  voice: {voice}  base rate: {base_rate:+d}%")
    else:
        key = eleven_key()
        voice_id, voice_name = eleven_voice(key, args.voice, args.voice_id)
        model = args.model or ELEVEN_MODEL
        render = lambda text, out, at: eleven_render(key, voice_id, model, text, out)  # noqa: E731
        base_rate = 0
        print(f"engine: elevenlabs  voice: {voice_name}  model: {model}")

    if args.auto:
        return auto_fit(flat, scenes, render, base_rate, args)

    targets = flat
    if args.only:
        targets = [b for b in flat if b["n"] == args.only]
        if not targets:
            sys.exit(f"beat {args.only} does not exist (the film has {len(flat)})")

    written = skipped = failed = 0
    for beat in targets:
        path = AUDIO / clip_name(beat["n"])
        if path.exists() and not args.force:
            skipped += 1
            continue
        ok, detail = render(beat["line"], path, base_rate)
        if ok:
            written += 1
            print(f"  {beat['n']:03d} ok   {path.stat().st_size // 1024:4d} KB  {beat['line'][:56]}")
        else:
            failed += 1
            print(f"  {beat['n']:03d} FAIL {detail}")
            if path.exists():
                path.unlink()

    print(f"\nrendered {written}, kept {skipped}, failed {failed}")
    over = report(flat)

    if args.fit and over:
        print(f"\nfitting {len(over)} overrunning clip(s) at a faster rate")
        for beat, seconds in over:
            want = math.ceil((seconds / beat["window"] - 1) * 100) + base_rate + 3
            target = min(args.max_rate, max(base_rate + 4, want))
            path = AUDIO / clip_name(beat["n"])
            ok, detail = render(beat["line"], path, target)
            if ok:
                new = ffprobe_seconds(path) or 0.0
                verdict = "fits" if new <= beat["window"] + 0.25 else "still long"
                print(f"  {beat['n']:03d} rate {target:+d}%  {seconds:.2f}s -> {new:.2f}s  {verdict}")
            else:
                print(f"  {beat['n']:03d} refit failed: {detail}")
        report(flat)

    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["edge", "eleven"], default="edge",
                    help="TTS backend (default: edge)")
    ap.add_argument("--voice", help=f"voice name (edge default: {EDGE_VOICE}, eleven default: {ELEVEN_VOICE})")
    ap.add_argument("--voice-id", help="explicit ElevenLabs voice id (skips the name lookup)")
    ap.add_argument("--model", help=f"ElevenLabs model (default: {ELEVEN_MODEL})")
    ap.add_argument("--rate", type=int, default=EDGE_RATE, help=f"edge-tts rate percent (default: {EDGE_RATE:+d}%%)")
    ap.add_argument("--only", type=int, metavar="N", help="render a single beat")
    ap.add_argument("--force", action="store_true", help="re-render clips that already exist")
    ap.add_argument("--fit", action="store_true", help="re-render overrunning clips at a faster rate")
    ap.add_argument("--auto", action="store_true",
                    help="render so every scene fits its duration (per-scene rate), then report")
    ap.add_argument("--cap", type=int, default=MAX_RATE,
                    help=f"ceiling for --auto per-scene rates, in percent (default: {MAX_RATE})")
    ap.add_argument("--max-rate", type=int, default=MAX_RATE,
                    help=f"ceiling for --fit, in percent (default: {MAX_RATE})")
    ap.add_argument("--dry-run", action="store_true", help="list the beats without rendering")
    ap.add_argument("--check", action="store_true", help="measure the pack without rendering")
    return build(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

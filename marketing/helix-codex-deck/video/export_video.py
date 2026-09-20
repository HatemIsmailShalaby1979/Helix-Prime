"""
Export Helix_Codex_5Min_Animated.html to a shareable MP4.

The film is a browser artifact: 1920x1080, animated in CSS, narrated from
audio/beat-NNN.mp3. To hand it to someone who will not open a browser - or to
upload it - it has to become a video file. This does that in three steps:

  1. Bed    - place every narration clip at its beat's absolute time and mix in
              the scene-change chime, producing one 300 s audio track. The chime
              is generated here rather than captured, because the browser makes it
              with WebAudio and it never reaches an audio device in headless mode.
  2. Frames - drive the real film in headless Chrome with `#auto` and record a
              variable-rate JPEG sequence with per-frame timestamps
              (capture_frames.mjs). Capture starts before playback so frame one
              is 0:00 and the bed lines up.
  3. Mux    - resample the frames to 30 fps, mux with the bed, and embed the
              caption track as soft subtitles so the file stands on its own.

Usage:
  python export_video.py                 # full 5-minute export
  python export_video.py --max-seconds 20 --out test.mp4    # quick smoke test
  python export_video.py --skip-capture  # re-mux an existing frames/ directory

Output:
  marketing/helix-codex-deck/video/Helix_Codex_5Min_Animated.mp4
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import wave
from array import array
from pathlib import Path

from build_captions import extract_scenes
from build_voice import AUDIO, clip_name, flatten_beats

HERE = Path(__file__).resolve().parent
OUT = HERE / "Helix_Codex_5Min_Animated.mp4"
CAPTIONS = HERE / "Helix_Codex_5Min_Animated.vtt"
BUILD = HERE / "_export"
RATE = 44100
FPS = 30

# Mirrors transitionSound() in the film: a rising sine with a low triangle under it.
CHIME_HZ_FROM, CHIME_HZ_TO, CHIME_SWEEP = 523.25, 1046.5, 0.275
CHIME_DUR, CHIME_SINE_GAIN, CHIME_TRI_GAIN = 0.55, 0.085, 0.05


def tool(name: str) -> str:
    exe = shutil.which(name) or shutil.which(f"{name}.exe")
    if not exe:
        sys.exit(f"{name} is required but was not found on PATH")
    return exe


def run(cmd: list[str], label: str) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr[-2000:])
        sys.exit(f"{label} failed")


def make_chime(path: Path) -> None:
    """Write the scene-change chime as a mono 16-bit WAV."""
    n = int(RATE * CHIME_DUR)
    samples = array("h", bytes(2 * n))
    for i in range(n):
        t = i / RATE
        sweep = min(1.0, t / CHIME_SWEEP)
        freq = CHIME_HZ_FROM * (CHIME_HZ_TO / CHIME_HZ_FROM) ** sweep
        attack = min(1.0, t / 0.03)
        value = CHIME_SINE_GAIN * attack * math.exp(-t * 9) * math.sin(2 * math.pi * freq * t)
        value += CHIME_TRI_GAIN * min(1.0, t / 0.02) * math.exp(-t * 14) * math.sin(2 * math.pi * 110 * t)
        samples[i] = max(-32768, min(32767, int(value * 32767)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())


def chime_track(path: Path, chime_path: Path, starts: list[float], total: float) -> None:
    """A full-length silent track with the chime stamped in at each scene start."""
    with wave.open(str(chime_path), "rb") as w:
        chime = w.readframes(w.getnframes())
    length = int(RATE * total) * 2
    track = bytearray(length)
    for start in starts:
        offset = int(start * RATE) * 2
        end = min(length, offset + len(chime))
        if offset < length:
            track[offset:end] = chime[: end - offset]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(track))


def build_bed(beats: list[dict], starts: list[float], total: float, out: Path) -> None:
    """Mix every narration clip and the chime track into one audio bed."""
    chime_path = BUILD / "chime.wav"
    make_chime(chime_path)
    chime_track(BUILD / "chimes.wav", chime_path, starts, total)

    cmd = [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    for beat in beats:
        cmd += ["-i", str(AUDIO / clip_name(beat["n"]))]
    cmd += ["-i", str(BUILD / "chimes.wav")]

    graph = []
    for i, beat in enumerate(beats):
        graph.append(f"[{i}:a]adelay={int(round(beat['start'] * 1000))}:all=1[n{i}]")
    graph.append(f"[{len(beats)}:a]anull[c]")
    mix = "".join(f"[n{i}]" for i in range(len(beats))) + "[c]"
    # normalize=0 keeps the narration at full level instead of amix's 1/N; loudnorm
    # then brings the finished bed to the -16 LUFS that web video expects.
    graph.append(
        f"{mix}amix=inputs={len(beats) + 1}:normalize=0,"
        f"alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    )

    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", "[out]",
        "-ar", str(RATE), "-ac", "2", "-t", f"{total:.3f}",
        str(out),
    ]
    print(f"  mixing {len(beats)} narration clips + {len(starts)} chimes")
    run(cmd, "audio bed")


def capture(frames_dir: Path, max_seconds: int, quality: int) -> dict:
    node = tool("node")
    script = HERE / "capture_frames.mjs"
    # Both positionals are always passed, in order. Passing them conditionally
    # shifts quality into the max-seconds slot, which silently truncates the
    # capture to `quality` seconds (78 by default) instead of the whole film.
    cmd = [node, str(script), str(frames_dir), str(max_seconds), str(quality)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE))
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        print(res.stderr[-2000:])
        sys.exit("frame capture failed")
    return json.loads((frames_dir / "frames.json").read_text(encoding="utf-8"))


def concat_list(frames_dir: Path, info: dict) -> Path:
    """Frame durations from the capture timestamps, so motion keeps its real speed.

    Paths must be absolute: the concat demuxer resolves relative entries against
    the list file's own directory, not the working directory.

    A missing frame is held rather than dropped. If the list names a file that is
    not on disk, ffmpeg stops the video stream there and muxes the rest as audio
    only - a 300 s file whose picture ends at 4:10, with no error to show for it.
    The capture timestamps still give the gap its correct duration, so pointing
    the entry at the previous frame preserves the film's timing exactly.
    """
    frames_dir = frames_dir.resolve()
    stamps = info["timestamps"]
    fallback = 1 / FPS
    lines = []
    filled = []
    last_ok = None

    for i, stamp in enumerate(stamps):
        if i + 1 < len(stamps):
            end = stamps[i + 1]
        elif len(stamps) > 1:
            end = stamp + (stamps[-1] - stamps[-2])
        else:
            end = stamp + fallback
        frame = frames_dir / f"frame-{i + 1:06d}.jpg"
        if frame.exists():
            last_ok = frame
        elif last_ok is not None:
            filled.append(i + 1)
            frame = last_ok
        else:
            sys.exit(f"the first captured frame is missing: {frame}")
        lines.append(f"file '{frame.as_posix()}'")
        lines.append(f"duration {max(1 / 240, end - stamp):.6f}")

    lines.append(f"file '{last_ok.as_posix()}'")

    if filled:
        print(f"  warning: {len(filled)} captured frame(s) missing on disk, held the previous "
              f"frame to keep the film's timing: {filled[:10]}")

    path = BUILD / "frames.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def assemble(frames_dir: Path, info: dict, bed: Path, out: Path, max_seconds: int,
             captions: bool = True) -> None:
    listing = concat_list(frames_dir, info)
    has_subs = captions and CAPTIONS.exists()
    cmd = [
        tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-i", str(bed),
    ]
    if has_subs:
        cmd += ["-i", str(CAPTIONS)]
    cmd += [
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", f"scale=1920:1080:flags=lanczos,fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
        "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE),
    ]
    if has_subs:
        # Soft subtitles, so the film is self-contained for someone who will never
        # see the .vtt next to it. Players leave them off unless asked.
        cmd += ["-map", "2:s:0", "-c:s", "mov_text",
                "-metadata:s:s:0", "language=eng", "-metadata:s:s:0", "title=English"]
    cmd += [
        "-movflags", "+faststart",
        "-t", f"{max_seconds if max_seconds else info.get('elapsed', 300):.3f}",
        str(out),
    ]
    print(f"  encoding H.264 + AAC{', embedding captions' if has_subs else ''}")
    run(cmd, "encode")


def verify(out: Path, expected: float, want_subs: bool = True) -> dict:
    """Probe the delivered file. The pipeline succeeding is not the film being right.

    Checks the video stream's own duration, not just the container's: a container
    duration is satisfied by the audio track alone, so a picture that stops early
    still reports a full-length file.
    """
    res = subprocess.run(
        [tool("ffprobe"), "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(out)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        sys.exit(f"ffprobe could not read the output: {res.stderr[-500:]}")

    probe = json.loads(res.stdout)
    video = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    if video is None or audio is None:
        sys.exit("the output is missing a video or an audio stream")

    got = float(probe["format"]["duration"])
    vdur = float(video.get("duration") or 0)
    print(f"  {video['width']}x{video['height']} {video['codec_name']} @ {video['r_frame_rate']} "
          f"+ {audio['codec_name']} {audio['sample_rate']} Hz {audio['channels']}ch")
    print(f"  container {got:.2f}s · picture {vdur:.2f}s · expected {expected:.2f}s")

    subs = [s for s in probe["streams"] if s["codec_type"] == "subtitle"]
    if subs:
        print(f"  captions {subs[0]['codec_name']} ({subs[0].get('tags', {}).get('language', 'und')})")
    elif want_subs:
        sys.exit("the captions were not embedded in the output")

    if vdur < expected - 0.5:
        sys.exit(f"the picture ends at {vdur:.2f}s but the film is {expected:.2f}s "
                 f"- {expected - vdur:.1f}s of the film has no video")
    if got < expected - 0.5:
        sys.exit(f"the file is {got:.2f}s but the film is {expected:.2f}s")
    return probe


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--frames", type=Path, default=BUILD / "frames")
    ap.add_argument("--max-seconds", type=int, default=0, help="capture only the first N seconds")
    ap.add_argument("--quality", type=int, default=78, help="JPEG quality for the captured frames")
    ap.add_argument("--skip-capture", action="store_true", help="reuse an existing frames directory")
    ap.add_argument("--no-captions", action="store_true", help="do not embed the .vtt as a subtitle track")
    args = ap.parse_args()

    for name in ("ffmpeg", "ffprobe", "node"):
        tool(name)

    scenes = extract_scenes()
    beats = flatten_beats(scenes)
    total = max(s["start"] + s["dur"] for s in scenes)
    BUILD.mkdir(parents=True, exist_ok=True)

    print(f"film: {len(scenes)} scenes, {len(beats)} narration beats, {total:.0f}s")

    # Capture first. Building the bed writes ~80 MB of WAV, and the disk flush that
    # follows starves the frame writes - measured 13 fps capture when the bed was
    # built first, against 45 fps when it was not.
    if args.skip_capture:
        info = json.loads((args.frames / "frames.json").read_text(encoding="utf-8"))
        print(f"1/3 frames: reusing {info['count']} captured frames")
    else:
        print(f"1/3 frames: capturing {'the full film' if not args.max_seconds else str(args.max_seconds) + 's'}")
        info = capture(args.frames, args.max_seconds, args.quality)

    # A full-film export that stopped early is a truncated film, not a short one.
    # Fail loudly rather than mux 78 s of footage and call it the 5-minute cut.
    if not args.max_seconds:
        reached = float(info.get("elapsed") or 0)
        if not info.get("sawEndcard") or reached < total - 1:
            sys.exit(
                f"refusing to mux a truncated film: capture stopped at {reached:.1f}s of {total:.0f}s "
                f"(sawEndcard={info.get('sawEndcard')})"
            )

    print("2/3 audio bed")
    bed = BUILD / "bed.wav"
    # The chime fires on scene change, so scene 1 (the cold open) has none.
    build_bed(beats, [s["start"] for s in scenes[1:]], total, bed)

    print("3/3 mux")
    assemble(args.frames, info, bed, args.out, args.max_seconds, captions=not args.no_captions)

    print("checking the delivered file")
    verify(args.out, args.max_seconds or total, want_subs=not args.no_captions)

    size = args.out.stat().st_size / 1024 / 1024
    print(f"\nwrote {args.out}  ({size:.1f} MB, {info['count']} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

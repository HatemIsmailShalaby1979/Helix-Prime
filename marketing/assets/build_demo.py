"""
Build the Helix Prime 5-minute demo video from DEMO_SCRIPT.md.

Pipeline:
  1. Parse DEMO_SCRIPT.md into 5 chapters (60s each).
  2. Render one PNG slide per second (5 * 60 = 300 frames) using Pillow.
  3. Synthesize narration MP3 per chapter with edge-tts.
  4. Mux slide frames into a per-chapter silent MP4, then audio-tracked MP4.
  5. Concatenate the 5 chapter MP4s into the final Helix_Prime_5Min_Demo.mp4.
  6. Emit a WebVTT captions file with chapter timestamps.

Output:
  marketing/assets/Helix_Prime_5Min_Demo.mp4
  marketing/assets/Helix_Prime_5Min_Demo.vtt
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]  # marketing/
SCRIPT_MD = ROOT / "DEMO_SCRIPT.md"
ASSETS = ROOT / "assets"
BUILD = ASSETS / "_build"
FINAL_MP4 = ASSETS / "Helix_Prime_5Min_Demo.mp4"
FINAL_VTT = ASSETS / "Helix_Prime_5Min_Demo.vtt"

WIDTH, HEIGHT = 1920, 1080
FPS = 30
CHAPTER_SECONDS = 60
TOTAL_CHAPTERS = 5

# Brand palette
BG = (11, 11, 20)
BG_ALT = (18, 18, 31)
ORG = (233, 69, 96)  # Helix red
TEXT = (232, 232, 240)
MUTED = (154, 154, 176)
BORDER = (42, 42, 68)

# TTS
TTS_VOICE = "en-GB-RyanNeural"
TTS_RATE = "-5%"

# Font fallbacks — prefer bundled DejaVu for cross-platform (Vercel Linux),
# fall back to Windows system fonts for local development.
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"

FONT_CANDIDATES = {
    "bold": [
        _FONTS_DIR / "DejaVuSans-Bold.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "reg": [
        _FONTS_DIR / "DejaVuSans.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "mono": [
        _FONTS_DIR / "DejaVuSansMono.ttf",
        r"C:\Windows\Fonts\consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ],
}


def _resolve_font(key: str) -> str:
    """Return the first existing font path from the candidate list."""
    for candidate in FONT_CANDIDATES[key]:
        p = str(candidate)
        if os.path.exists(p):
            return p
    raise RuntimeError(
        f"No font found for '{key}'. Searched: {[str(c) for c in FONT_CANDIDATES[key]]}"
    )


FONT_BOLD = _resolve_font("bold")
FONT_REG = _resolve_font("reg")
FONT_MONO = _resolve_font("mono")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class Chapter:
    index: int  # 1..5
    title: str  # "The Story of Helix"
    visual: str  # "Dark hero screen, Helix logo glows..."
    narration: str  # Full narrator text (no quotes)

    @property
    def start_s(self) -> int:
        return (self.index - 1) * CHAPTER_SECONDS

    @property
    def end_s(self) -> int:
        return self.index * CHAPTER_SECONDS


# ---------------------------------------------------------------------------
# Script parsing
# ---------------------------------------------------------------------------

CHAPTER_HEADER = re.compile(
    r"^##\s*🎬\s*(\d+):(\d{2})\s*[–-]\s*(\d+):(\d{2})\s*[—–-]\s*(.+?)\s*$",
    re.MULTILINE | re.UNICODE,
)
QUOTE_LINE = re.compile(r"^\s*>\s*\[Visual:[^\]]*\]\s*$", re.MULTILINE)


def parse_chapters(text: str) -> list[Chapter]:
    headers = list(CHAPTER_HEADER.finditer(text))
    if len(headers) != TOTAL_CHAPTERS:
        raise RuntimeError(
            f"Expected {TOTAL_CHAPTERS} chapter headers in {SCRIPT_MD}, found {len(headers)}"
        )

    chapters: list[Chapter] = []
    for i, m in enumerate(headers):
        idx = i + 1
        start_min, start_sec = int(m.group(1)), int(m.group(2))
        title = m.group(5).strip()

        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end]

        # Visual hint is the first > [Visual: ...] line
        vmatch = re.search(r"^\s*>\s*\[Visual:\s*([^\]]+)\]\s*$", body, re.MULTILINE)
        visual = vmatch.group(1).strip() if vmatch else ""

        # Narration: lines after the visual hint, joined, stopping at next "---" or "##".
        # Paragraph continuation lines may not start with "> ".
        quote_lines: list[str] = []
        past_visual = False
        for line in body.splitlines():
            stripped = line.strip()
            if not past_visual:
                if stripped.startswith((">[Visual:", "> [Visual:")):
                    past_visual = True
                continue
            if not stripped:
                # blank line — separator inside the quote, skip
                continue
            if stripped.startswith("---"):
                break
            if stripped.startswith("## "):
                break
            # Strip a single leading ">" if present, and matching outer quotes.
            content = stripped
            if content.startswith(">"):
                content = content.lstrip(">").strip()
            # If a line is the *closing* line of a multi-line quote that ends with a `"`,
            # keep it; otherwise strip a leading and trailing quote.
            if content.startswith('"') and not content.endswith('"'):
                content = content[1:]
            if content.endswith('"') and not content.startswith('"'):
                content = content[:-1]
            if content:
                quote_lines.append(content)
        narration = " ".join(quote_lines).strip()
        if not narration:
            raise RuntimeError(f"Chapter {idx} ({title}) has empty narration")

        # Sanity check: start time matches
        if start_min * 60 + start_sec != (idx - 1) * CHAPTER_SECONDS:
            raise RuntimeError(
                f"Chapter {idx} start time {start_min}:{start_sec} does not match expected "
                f"{(idx - 1) * CHAPTER_SECONDS // 60}:{(idx - 1) * CHAPTER_SECONDS % 60:02d}"
            )

        chapters.append(
            Chapter(index=idx, title=title, visual=visual, narration=narration)
        )

    return chapters


# ---------------------------------------------------------------------------
# Slide rendering
# ---------------------------------------------------------------------------


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    if not os.path.exists(path):
        raise RuntimeError(f"Font not found: {path}")
    return ImageFont.truetype(path, size)


def draw_slide(
    chapter: Chapter, second_in_chapter: int, total_seconds: int
) -> Image.Image:
    """Render a single 1920x1080 frame for the given chapter at the given second."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Subtle radial glow (top center) using concentric alpha-blended ellipses
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = WIDTH // 2, 250
    for r, a in [(560, 28), (420, 22), (300, 18), (200, 14)]:
        gd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(233, 69, 96, a))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Brand bar (top)
    draw.rectangle((0, 0, WIDTH, 6), fill=ORG)
    f_brand = load_font(FONT_BOLD, 28)
    draw.text((60, 36), "HELIX  PRIME", font=f_brand, fill=ORG)

    # Chapter label
    f_chap = load_font(FONT_REG, 22)
    label = f"CHAPTER 0{chapter.index}  ·  {chapter.start_s // 60}:{chapter.start_s % 60:02d} – {chapter.end_s // 60}:{chapter.end_s % 60:02d}"
    draw.text((60, 90), label, font=f_chap, fill=MUTED)

    # Title
    f_title = load_font(FONT_BOLD, 88)
    title_bbox = draw.textbbox((0, 0), chapter.title, font=f_title)
    title_w = title_bbox[2] - title_bbox[0]
    title_x = (WIDTH - title_w) // 2
    draw.text((title_x, 280), chapter.title, font=f_title, fill=TEXT)
    # Red underline
    draw.rectangle((title_x, 380, title_x + title_w, 388), fill=ORG)

    # Visual hint (one short line, truncated)
    f_visual = load_font(FONT_REG, 28)
    visual_short = chapter.visual
    if len(visual_short) > 110:
        visual_short = visual_short[:107] + "..."
    vbox = draw.textbbox((0, 0), "[Visual] " + visual_short, font=f_visual)
    vw = vbox[2] - vbox[0]
    draw.text(
        ((WIDTH - vw) // 2, 430), "[Visual] " + visual_short, font=f_visual, fill=MUTED
    )

    # Narration excerpt (word-by-word reveal over 60s, all on screen at this point)
    # We render the full narration, wrapped, on the slide. The voiceover carries timing.
    f_narr = load_font(FONT_REG, 30)
    max_chars = 88
    words = chapter.narration.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip()
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    # Trim to ~8 lines, ellipsize
    if len(lines) > 8:
        lines = lines[:8]
        lines[-1] = lines[-1][:85] + "..."
    line_h = 44
    block_h = line_h * len(lines)
    y0 = (HEIGHT - block_h) // 2 + 60
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=f_narr)
        lw = bbox[2] - bbox[0]
        x = (WIDTH - lw) // 2
        draw.text((x, y0 + i * line_h), line, font=f_narr, fill=TEXT)

    # Progress bar (chapter)
    bar_x, bar_y, bar_w, bar_h = 120, HEIGHT - 90, WIDTH - 240, 6
    draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill=BORDER)
    progress = (second_in_chapter + 1) / max(total_seconds, 1)
    fill_w = int(bar_w * progress)
    draw.rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), fill=ORG)

    # Time labels
    f_time = load_font(FONT_MONO, 22)
    elapsed = chapter.start_s + second_in_chapter
    draw.text(
        (bar_x, bar_y + 18),
        f"{elapsed // 60}:{elapsed % 60:02d}",
        font=f_time,
        fill=MUTED,
    )
    total = TOTAL_CHAPTERS * CHAPTER_SECONDS
    end_label = f"{total // 60}:{total % 60:02d}"
    end_bbox = draw.textbbox((0, 0), end_label, font=f_time)
    draw.text(
        (bar_x + bar_w - (end_bbox[2] - end_bbox[0]), bar_y + 18),
        end_label,
        font=f_time,
        fill=MUTED,
    )

    # Footer brand
    f_foot = load_font(FONT_REG, 20)
    draw.text(
        (60, HEIGHT - 50),
        "Helix Prime Ecosystem  ·  An AI Organization",
        font=f_foot,
        fill=MUTED,
    )
    draw.text(
        (WIDTH - 60 - 220, HEIGHT - 50),
        "Constitution 000  ·  hatem-shalaby",
        font=f_foot,
        fill=MUTED,
    )

    return img


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------


async def synth_chapter(chapter: Chapter, out_mp3: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(chapter.narration, TTS_VOICE, rate=TTS_RATE)
    await communicate.save(str(out_mp3))


def synth_all(chapters: list[Chapter]) -> list[Path]:
    BUILD.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for ch in chapters:
        out = BUILD / f"chapter_{ch.index:02d}.mp3"
        if not out.exists():
            print(f"  TTS: chapter {ch.index} -> {out.name}", flush=True)
            asyncio.run(synth_chapter(ch, out))
        paths.append(out)
    return paths


# ---------------------------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------------------------


def ffmpeg_bin() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration(mp4: Path) -> float:
    out = subprocess.run(
        [ffmpeg_bin(), "-i", str(mp4)],
        capture_output=True,
        text=True,
    )
    # ffmpeg prints "Duration: HH:MM:SS.xx" to stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out.stderr)
    if not m:
        return 0.0
    h, mi, s = m.group(1), m.group(2), m.group(3)
    return int(h) * 3600 + int(mi) * 60 + float(s)


def render_chapter_video(chapter: Chapter) -> Path:
    """Render the chapter's slide frames into a per-second-image sequence, then encode to MP4."""
    frames_dir = BUILD / f"frames_{chapter.index:02d}"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Render FRAMES_PER_CHAPTER unique frames (1 per second-of-chapter) so the video
    # runs for 60s at 30fps. ffmpeg's -framerate repeats each PNG FPS times.
    for s in range(CHAPTER_SECONDS):
        img = draw_slide(chapter, s, CHAPTER_SECONDS)
        img.save(frames_dir / f"frame_{s:03d}.png", "PNG", optimize=False)

    seq_pattern = str(frames_dir / "frame_%03d.png")
    chapter_mp4 = BUILD / f"chapter_{chapter.index:02d}.mp4"

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-framerate",
        "1",  # 1 input frame per second-of-source
        "-i",
        seq_pattern,
        "-r",
        str(FPS),  # output 30 fps by repeating each source frame FPS times
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=1920:1080",
        str(chapter_mp4),
    ]
    print(
        f"  encode: chapter {chapter.index} ({CHAPTER_SECONDS} frames @ {FPS}fps = {CHAPTER_SECONDS}s) -> mp4",
        flush=True,
    )
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg frame encode failed: {res.stderr[-2000:]}")

    # Cleanup frames to save disk
    shutil.rmtree(frames_dir, ignore_errors=True)
    return chapter_mp4


def mux_audio(chapter: Chapter, silent_mp4: Path, audio_mp3: Path) -> Path:
    """Combine chapter video with its TTS audio. Pads/clamps to exactly 60s.

    - If audio is shorter than 60s: extend video to 60s (tpad), then trim audio to 60s with apad.
    - If audio is longer than 60s: just use the audio as-is (rare).
    """
    out = BUILD / f"chapter_{chapter.index:02d}_audio.mp4"
    target = CHAPTER_SECONDS  # 60

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(silent_mp4),
        "-i",
        str(audio_mp3),
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={target}[v];"
        f"[1:a]apad=whole_dur={target}[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-t",
        str(target),
        str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed: {res.stderr[-2000:]}")
    return out


def probe_duration_via(media: Path) -> float:
    out = subprocess.run(
        [ffmpeg_bin(), "-i", str(media)],
        capture_output=True,
        text=True,
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out.stderr)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def concat_chapters(chapter_videos: list[Path]) -> Path:
    list_file = BUILD / "chapters.txt"
    with list_file.open("w", encoding="utf-8") as f:
        for p in chapter_videos:
            f.write(f"file '{p.as_posix()}'\n")
    out = BUILD / "final_concat.mp4"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {res.stderr[-2000:]}")
    return out


# ---------------------------------------------------------------------------
# VTT
# ---------------------------------------------------------------------------


def write_vtt(chapters: list[Chapter]) -> Path:
    def fmt(t: int) -> str:
        h = t // 3600
        m = (t % 3600) // 60
        s = t % 60
        return f"{h:02d}:{m:02d}:{s:02d}.000"

    lines = ["WEBVTT", ""]
    for ch in chapters:
        lines.append(str(ch.index))
        lines.append(f"{fmt(ch.start_s)} --> {fmt(ch.end_s)}")
        # One cue per line of narration, max 80 chars
        words = ch.narration.split()
        chunk: list[str] = []
        chunk_len = 0
        cue_idx = 0
        chunk_start = ch.start_s
        for w in words:
            if chunk_len + len(w) + 1 > 80 and chunk:
                cue_text = " ".join(chunk)
                chunk_dur = max(2, len(" ".join(chunk)) // 18)
                cs = chunk_start
                ce = min(ch.end_s, cs + chunk_dur)
                lines.append(f"{fmt(cs)} --> {fmt(ce)}")
                lines.append(cue_text)
                lines.append("")
                chunk = [w]
                chunk_len = len(w)
                chunk_start = ce
                cue_idx += 1
            else:
                chunk.append(w)
                chunk_len += len(w) + 1
        if chunk:
            lines.append(f"{fmt(chunk_start)} --> {fmt(ch.end_s)}")
            lines.append(" ".join(chunk))
            lines.append("")

    FINAL_VTT.write_text("\n".join(lines), encoding="utf-8")
    return FINAL_VTT


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("== Helix Prime 5-min demo builder ==", flush=True)
    print(f"script: {SCRIPT_MD}")
    print(f"ffmpeg: {ffmpeg_bin()}")
    BUILD.mkdir(parents=True, exist_ok=True)

    if not SCRIPT_MD.exists():
        print(f"ERROR: {SCRIPT_MD} not found", file=sys.stderr)
        return 2

    text = SCRIPT_MD.read_text(encoding="utf-8")
    chapters = parse_chapters(text)
    print(f"parsed {len(chapters)} chapters:")
    for ch in chapters:
        print(f"  {ch.index}. {ch.title} ({len(ch.narration)} chars narration)")

    # 1. TTS
    print("\n[1/4] Synthesising narration...")
    audio_files = synth_all(chapters)

    # 2. Per-chapter video (silent, slides only)
    print("\n[2/4] Rendering chapter videos...")
    silent_videos = [render_chapter_video(ch) for ch in chapters]

    # 3. Mux audio
    print("\n[3/4] Muxing narration audio...")
    muxed = [
        mux_audio(ch, sv, au)
        for ch, sv, au in zip(chapters, silent_videos, audio_files)
    ]

    # 4. Concatenate
    print("\n[4/4] Concatenating final video...")
    final = concat_chapters(muxed)
    shutil.copy2(final, FINAL_MP4)
    print(f"\nFINAL: {FINAL_MP4} ({FINAL_MP4.stat().st_size / 1024 / 1024:.1f} MB)")

    # VTT
    write_vtt(chapters)
    print(f"CAPTIONS: {FINAL_VTT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

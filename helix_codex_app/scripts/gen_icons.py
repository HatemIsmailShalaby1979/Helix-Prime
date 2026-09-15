"""Cut the Helix Codex PWA icons from the mark geometry.

Design-time helper, run by hand when the mark changes:

    python helix_codex_app/scripts/gen_icons.py

It writes icon-192.png, icon-512.png and maskable-512.png into
helix_codex_app/static/icons/. The manifest pins those three filenames, so the
output names must not drift.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ICON_DIR = Path(__file__).resolve().parents[1] / "static" / "icons"

TOP, BOTTOM = 3.4, 20.6
CENTRE, AMP = 12.0, 7.0
K1, K2, K3 = 0.3642, 0.6358, 1.3333
STROKE = 2.1
SS = 8

PLATE_TOP = (44, 27, 37)
PLATE_BOTTOM = (13, 11, 15)
MARK_TOP = (255, 158, 176)
MARK_BOTTOM = (216, 42, 80)


def strand(signs: list[int]):
    span = (BOTTOM - TOP) / len(signs)
    segs, y = [], TOP
    for sign in signs:
        d = sign * AMP
        segs.append(
            (
                (CENTRE, y),
                (CENTRE + K3 * d, y + K1 * span),
                (CENTRE + K3 * d, y + K2 * span),
                (CENTRE, y + span),
            )
        )
        y += span
    return segs


STRANDS = (strand([1, -1, 1]), strand([-1, 1, -1]))


def bezier(p0, p1, p2, p3, steps=200):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append(
            (
                u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
            )
        )
    return pts


def mark_mask(size: int, scale: float) -> Image.Image:
    """White mark on transparent, drawn into a `size` px square."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    inner = size * scale
    off = (size - inner) / 2.0
    s = inner / 24.0
    w = max(2, int(round(STROKE * s)))
    r = w / 2.0

    def mp(p):
        return (off + p[0] * s, off + p[1] * s)

    for family in STRANDS:
        for seg in family:
            poly = [mp(p) for p in bezier(*seg)]
            d.line(poly, fill=255, width=w, joint="curve")
            for end in (poly[0], poly[-1]):
                d.ellipse([end[0] - r, end[1] - r, end[0] + r, end[1] + r], fill=255)
    return mask


def vertical_gradient(
    size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(3))
    return grad.resize((size, size), Image.BILINEAR)


def build(size: int, *, bleed: bool, mark_scale: float) -> Image.Image:
    s = size * SS
    radius = 0 if bleed else int(s * 0.225)

    plate = vertical_gradient(s, PLATE_TOP, PLATE_BOTTOM).convert("RGBA")
    if radius:
        alpha = Image.new("L", (s, s), 0)
        ImageDraw.Draw(alpha).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
        plate.putalpha(alpha)

    # soft rose bloom behind the mark so the mark separates from the plate
    mask = mark_mask(s, mark_scale)
    bloom = mask.filter(ImageFilter.GaussianBlur(s * 0.055)).point(lambda v: int(v * 0.42))
    glow = Image.new("RGBA", (s, s), (233, 69, 96, 0))
    glow.putalpha(bloom)
    plate = Image.alpha_composite(plate, glow)

    ink = vertical_gradient(s, MARK_TOP, MARK_BOTTOM).convert("RGBA")
    ink.putalpha(mask)
    plate = Image.alpha_composite(plate, ink)

    return plate.resize((size, size), Image.LANCZOS)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    build(512, bleed=False, mark_scale=0.58).save(ICON_DIR / "icon-512.png")
    build(192, bleed=False, mark_scale=0.58).save(ICON_DIR / "icon-192.png")
    # maskable: full bleed, mark inside the 80% safe circle
    build(512, bleed=True, mark_scale=0.46).save(ICON_DIR / "maskable-512.png")
    for name in ("icon-192.png", "icon-512.png", "maskable-512.png"):
        print(f"{name}: {(ICON_DIR / name).stat().st_size} bytes")


if __name__ == "__main__":
    main()

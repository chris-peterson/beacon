#!/usr/bin/env python3
"""Shared slate-watermark pipeline for the beacon mode profiles (RENDER-05).

Every mode watermark (pause / release / retro / done) is derived from a source
illustration (iterm/resources/<phase>-src.png) and recolored to a single on-palette slate
(THEME-01) so the four marks read as one family. iTerm2 fits the square asset to
the pane, centered, and composites it over the mode background at a low Blend, so
the mark reads as a faint watermark.

Real-world source art doesn't arrive uniform, so a phase declares a *treatment*
(make-bg.py's table) — the human labels each source; nothing is auto-detected:

  tonal       Filled illustration with its own transparency (rocket, pause). Keep
              the alpha shape and per-pixel tone: light areas -> LIGHT, dark
              outlines -> DARK, so internal detail (a porthole, a rim) stays
              legible rather than flattening to a solid blob.
  silhouette  Dark line-art on a light background (done's checkered flag). The
              ink IS the mark: darkness -> opacity, painted a single flat LIGHT so
              it reads on a near-black pane where a dark ramp would vanish.

Plus source-cleanup / orientation modifiers, since not every source is a clean,
upright cutout:

  drop_bg     Flood-fill the border-connected background to transparent (retro's
              clipboard arrived fully opaque — a solid white field). Interior
              regions walled off by darker outlines (the board face) are kept.
  erase       Blank fractional rects before processing (for a source that carries
              a stock watermark to remove).
  rotate      Turn the mark clockwise by N degrees (retro's clipboard reads better
              tilted). Applied after drop_bg so the removed background doesn't get
              trapped behind the rotation's transparent corners.

This module is the one place the treatment lives; make-bg.py drives it over the
phase->config table so all four marks stay tunable here.
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps

SIZE = 1200
# The slate the mark's brightest source pixels reach (LIGHT) and its darkest fall
# to (DARK); silhouettes are painted flat LIGHT. The profile's low Blend dials the
# whole thing down to a faint watermark, so the asset stays crisp and tunable from
# one place (Blend).
LIGHT = (200, 206, 224)
DARK = (28, 31, 44)
# Source alpha below this is background (stays transparent); anti-aliased edges
# keep their partial alpha.
ALPHA_CUTOFF = 24
# Transparent margin around the trimmed mark, as a fraction of SIZE, so it doesn't
# run edge to edge once iTerm2 fits it to the pane.
PAD_FRAC = 0.10
# drop_bg: color distance from a corner seed that still counts as background.
BG_FLOOD_THRESH = 60
# silhouette: source luma below (255 - FLOOR) starts to register as ink; GAIN
# steepens the ramp so mid-grays (JPEG ringing around the flag) don't haze in.
SILHOUETTE_FLOOR = 40
SILHOUETTE_GAIN = 1.6
_SENTINEL = (255, 0, 255)


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def _erase(rgba: Image.Image, rects) -> None:
    """Zero the alpha inside each fractional (x0, y0, x1, y1) rect."""
    w, h = rgba.size
    a = rgba.getchannel("A")
    for x0, y0, x1, y1 in rects:
        box = (round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h))
        a.paste(0, box)
    rgba.putalpha(a)


def _drop_border_bg(rgba: Image.Image, thresh: int = BG_FLOOD_THRESH) -> None:
    """Make the border-connected background transparent via a flood fill from each
    corner. Interior regions fenced off by darker outlines are left opaque."""
    w, h = rgba.size
    rgb = rgba.convert("RGB")
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(rgb, corner, _SENTINEL, thresh=thresh)
    a = rgba.getchannel("A")
    a_px, rgb_px = a.load(), rgb.load()
    for y in range(h):
        for x in range(w):
            if rgb_px[x, y] == _SENTINEL:
                a_px[x, y] = 0
    rgba.putalpha(a)


def _slate_ramp(rgba: Image.Image) -> Image.Image:
    """Tonal treatment: recolor by per-pixel luminance onto the DARK..LIGHT ramp,
    preserving the source alpha. Autocontrast so the source's tonal range fills the
    ramp regardless of how washed-out its whites are."""
    alpha = rgba.getchannel("A")
    luma = ImageOps.autocontrast(rgba.convert("L"))
    w, h = rgba.size
    mark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    luma_px, a_px, dst_px = luma.load(), alpha.load(), mark.load()
    for y in range(h):
        for x in range(w):
            a = a_px[x, y]
            if a < ALPHA_CUTOFF:
                continue
            t = luma_px[x, y] / 255.0
            dst_px[x, y] = (
                _lerp(DARK[0], LIGHT[0], t),
                _lerp(DARK[1], LIGHT[1], t),
                _lerp(DARK[2], LIGHT[2], t),
                a,
            )
    return mark


def _silhouette(rgba: Image.Image) -> Image.Image:
    """Silhouette treatment: darkness -> opacity, painted flat LIGHT. Any existing
    source transparency is honored (a genuinely transparent silhouette stays cut
    out) by taking the min of the two alphas."""
    src_a = rgba.getchannel("A")
    ink = rgba.convert("L").point(
        lambda l: min(255, int(max(0, 255 - l - SILHOUETTE_FLOOR) * SILHOUETTE_GAIN))
    )
    alpha = ImageChops.darker(ink, src_a)
    mark = Image.new("RGBA", rgba.size, LIGHT + (0,))
    mark.putalpha(alpha)
    return mark


def _fit_center(mark: Image.Image) -> Image.Image:
    """Trim to the mark's opaque bounds, then fit it centered into a SIZE square
    with a transparent margin so iTerm2's fit-to-pane scaling leaves breathing
    room."""
    bbox = mark.getchannel("A").point(lambda a: 255 if a >= ALPHA_CUTOFF else 0).getbbox()
    if bbox is None:
        raise ValueError("mark has no opaque pixels above ALPHA_CUTOFF")
    mark = mark.crop(bbox)
    w, h = mark.size
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    box = round(SIZE * (1 - 2 * PAD_FRAC))
    scale = min(box / w, box / h)
    fitted = mark.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    canvas.alpha_composite(
        fitted, ((SIZE - fitted.width) // 2, (SIZE - fitted.height) // 2)
    )
    return canvas


def slate_watermark(src_path: Path, *, treatment: str = "tonal",
                    drop_bg: bool = False, erase=(), rotate: float = 0) -> Image.Image:
    """Translate a source illustration into the SIZE-square slate watermark PNG
    (transparent background) baked into a mode profile. See the module docstring
    for `treatment` / `drop_bg` / `erase` / `rotate`."""
    src = Image.open(src_path).convert("RGBA")
    if erase:
        _erase(src, erase)
    if drop_bg:
        _drop_border_bg(src)
    if rotate:
        # PIL rotates counter-clockwise for a positive angle; negate so `rotate`
        # reads as clockwise degrees. expand keeps the whole mark; the new corners
        # fill transparent (drop_bg has already run, so no background is trapped).
        src = src.rotate(-rotate, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))
    if treatment == "tonal":
        mark = _slate_ramp(src)
    elif treatment == "silhouette":
        mark = _silhouette(src)
    else:
        raise ValueError(f"unknown treatment: {treatment!r} (tonal | silhouette)")
    return _fit_center(mark)

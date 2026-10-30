#!/usr/bin/env python3
"""Drawn watermark sources for the beacon mode and block profiles (RENDER-05,
RENDER-07).

The drawn marks are one family: monoline strokes on a shared 24-unit grid, one
stroke weight, round caps and joins, no container, held to the same live area in
the middle of the grid so none runs the pane's full height. Every enclosed space
is at least as wide as the stroke, so detail (a porthole, a keyhole, a check)
stays open instead of filling in. At watermark opacity a large
filled area reads as a UI panel, while a stroke keeps its shape however faint it
gets. Each mark keeps only what its tab glyph shows, so the tab and the pane say
the same thing.

`make-bg.py` writes each drawing to `resources/<phase>-src.png` and paints it
flat through `watermark.py`, so the color lives in one place and the geometry in
another. Marks are drawn opaque black on transparency; only the alpha survives.
The whole grid is what gets scaled to the pane, never a mark's own bounds, so
every mark keeps the same stroke weight and optical size.
"""

import math

from PIL import Image, ImageDraw

# Drawn larger than the 1200px the pipeline emits, so curves are antialiased
# down rather than up.
SIZE = 2400
GRID = 24
UNIT = SIZE / GRID
STROKE = 1.75
DOT = 1.3
INK = (0, 0, 0, 255)


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _px(p: tuple[float, float]) -> tuple[float, float]:
    return (p[0] * UNIT, p[1] * UNIT)


def _dot(d: ImageDraw.ImageDraw, center, radius: float) -> None:
    x, y = _px(center)
    r = radius * UNIT
    d.ellipse([x - r, y - r, x + r, y + r], fill=INK)


def _stroke(d: ImageDraw.ImageDraw, points, closed: bool = False, width: float = STROKE) -> None:
    """A round-capped, round-joined polyline through grid points, drawn as one
    quad per segment and a disc per vertex: PIL's own `joint="curve"` seams a
    densely sampled arc."""
    pts = list(points) + ([points[0]] if closed else [])
    half = width / 2
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        if not length:
            continue
        nx, ny = -(y1 - y0) / length * half, (x1 - x0) / length * half
        quad = [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]
        d.polygon([_px(p) for p in quad], fill=INK)
    for p in pts:
        _dot(d, p, half)


def _arc(center, radius: float, start: float, end: float, steps: int = 96):
    """Points along a circle, angles in degrees, screen y down."""
    cx, cy = center
    return [
        (cx + radius * math.cos(math.radians(a)), cy + radius * math.sin(math.radians(a)))
        for a in (start + (end - start) * i / steps for i in range(steps + 1))
    ]


def _cubic(p0, p1, p2, p3, steps: int = 48):
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append(tuple(
            u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * e
            for a, b, c, e in zip(p0, p1, p2, p3)
        ))
    return out


def pause() -> Image.Image:
    """`pause`: two upright bars."""
    img, d = _canvas()
    _stroke(d, [(9.5, 7), (9.5, 17)])
    _stroke(d, [(14.5, 7), (14.5, 17)])
    return img


def release() -> Image.Image:
    """`release`: a rocket climbing to the upper right, as 🚀 does. Drawn upright
    and turned, so the body stays symmetric; the porthole is a dot because a ring
    at this stroke weight closes up."""
    img, d = _canvas()
    body = (
        _cubic((8.5, 15.5), (8.5, 9.5), (9.5, 5.6), (12, 3))
        + _cubic((12, 3), (14.5, 5.6), (15.5, 9.5), (15.5, 15.5))[1:]
    )
    _stroke(d, body, closed=True)
    _dot(d, (12, 9.6), 1.2)
    _stroke(d, [(8.5, 11.6), (5, 15), (5, 18.6), (8.5, 18.2), (8.5, 15.5)])
    _stroke(d, [(15.5, 11.6), (19, 15), (19, 18.6), (15.5, 18.2), (15.5, 15.5)])
    _stroke(d, [(12, 18.6), (12, 20.6)])
    return img.rotate(-45, resample=Image.BICUBIC)


def done() -> Image.Image:
    """`done`: a checkered flag on its pole. The checks are the one filled area,
    small enough to read as pattern rather than panel, and tile the inside of the
    outline so the outline never covers them."""
    img, d = _canvas()
    x0, x1, top, height = 5.5, 19.5, 4.5, 10.0
    inset = STROKE / 2
    cols, rows = 4, 3

    def edge(x: float, y: float) -> tuple[float, float]:
        return (x, y + 0.8 * math.sin(math.pi * 2 * (x - x0) / (x1 - x0)))

    def span(a: float, b: float, n: int = 24):
        return [a + (b - a) * k / n for k in range(n + 1)]

    cell_w = (x1 - x0 - 2 * inset) / cols
    cell_h = (height - 2 * inset) / rows
    for c in range(cols):
        for r in range(rows):
            if (c + r) % 2:
                continue
            xa = x0 + inset + c * cell_w
            ya = top + inset + r * cell_h
            xs = span(xa, xa + cell_w)
            poly = [edge(x, ya) for x in xs] + [edge(x, ya + cell_h) for x in reversed(xs)]
            d.polygon([_px(p) for p in poly], fill=INK)

    xs = span(x0, x1)
    outline = [edge(x, top) for x in xs] + [edge(x, top + height) for x in reversed(xs)]
    _stroke(d, outline, closed=True)
    _stroke(d, [(x0, 3.5), (x0, 20.5)])
    return img


def question() -> Image.Image:
    """The blocked-on-a-question mark: a geometric `?`, an arc that turns into
    its stem, over a dot."""
    img, d = _canvas()
    hook = _arc((12, 8.5), 3.5, 180, 405)
    turn = _cubic(hook[-1], (13.4, 12), (12, 12.4), (12, 13.6))
    _stroke(d, hook + turn[1:] + [(12, 14)])
    _dot(d, (12, 18), DOT)
    return img


def permission() -> Image.Image:
    """The blocked-on-a-permission mark: a padlock, since the session is held
    until you grant access rather than asked something."""
    img, d = _canvas()
    _stroke(d, [(6.5, 11), (17.5, 11), (17.5, 19.5), (6.5, 19.5)], closed=True)
    _stroke(d, [(8.6, 11)] + _arc((12, 7.8), 3.4, 180, 360) + [(15.4, 11)])
    _dot(d, (12, 15.25), DOT)
    return img


# phase -> the function that draws it.
MARKS = {
    "pause": pause,
    "release": release,
    "done": done,
    "question": question,
    "permission": permission,
}

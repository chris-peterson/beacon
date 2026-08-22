#!/usr/bin/env python3
"""Drawn watermark sources for the beacon mode profiles (RENDER-05).

Most mode marks come from a found illustration committed as
`resources/<phase>-src.png`. These are the ones drawn instead, because the shape
wanted is a geometric primitive rather than a picture — `make-bg.py` calls the
function named by a phase's `draw=` key and feeds the result through the same
slate pipeline (`watermark.py`), so a drawn mark and a found one are treated
identically downstream.

Drawing them keeps the source reproducible: a committed PNG whose generator lives
nowhere means the next tweak to a tick's weight is a redraw from memory.

Marks are drawn in grayscale on transparency. `watermark.py`'s `tonal` treatment
autocontrasts luminance onto the DARK..LIGHT slate ramp, so the *relative* tones
here are what survive — brighter draws lighter, darker draws darker — and the
absolute values don't matter. Flat single-tone geometry comes out flat, which is
why each mark varies its tones deliberately.
"""

from PIL import Image, ImageDraw

# Source resolution. Larger than the 1200px the pipeline emits, so curves and
# tick joins are antialiased down rather than up.
SIZE = 1600


def _canvas() -> Image.Image:
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def _tone(t: float) -> tuple[int, int, int, int]:
    """An opaque gray at `t` along the ramp (0 = darkest, 1 = lightest)."""
    v = round(40 + 215 * max(0.0, min(1.0, t)))
    return (v, v, v, 255)


def clipboard() -> Image.Image:
    """`retro` — an upright clipboard with three ticked rules.

    Replaces a found illustration that read as noise at watermark opacity: a
    tilted board with internal linework, a pen, and paper texture, none of which
    survives being faded to a backdrop. This keeps only what the 📋 glyph on the
    tab also shows, so the two surfaces say the same thing.

    The board is **outlined, not filled.** A filled one is a large flat
    rectangle, and at watermark opacity a flat rectangle reads as a UI element —
    a panel or an input — rather than as a mark. The other marks get away with
    solid areas because their silhouettes are *shapes* (a rocket, two bars); a
    board's silhouette is exactly the thing a card is already made of. Linework
    also survives fading better, which is the whole job here.
    """
    img = _canvas()
    d = ImageDraw.Draw(img)

    board_w, board_h = SIZE * 0.52, SIZE * 0.68
    x0 = (SIZE - board_w) / 2
    y0 = (SIZE - board_h) / 2 + SIZE * 0.035
    edge = round(SIZE * 0.022)
    d.rounded_rectangle([x0, y0, x0 + board_w, y0 + board_h],
                        radius=SIZE * 0.045, outline=_tone(0.72), width=edge)

    # The clip straddles the top edge, half on the board and half above it. Solid,
    # because it is small and it is the mark's one point of emphasis.
    clip_w, clip_h = board_w * 0.34, SIZE * 0.09
    clip_x = SIZE / 2 - clip_w / 2
    d.rounded_rectangle([clip_x, y0 - clip_h * 0.62, clip_x + clip_w, y0 + clip_h * 0.38],
                        radius=SIZE * 0.020, fill=_tone(1.0))

    stroke = round(SIZE * 0.026)
    for i in range(3):
        line_y = y0 + board_h * (0.33 + i * 0.19)
        tick_x = x0 + board_w * 0.15
        d.line([(tick_x, line_y + SIZE * 0.012),
                (tick_x + SIZE * 0.030, line_y + SIZE * 0.036),
                (tick_x + SIZE * 0.082, line_y - SIZE * 0.026)],
               fill=_tone(0.85), width=stroke, joint="curve")
        rule_x = tick_x + SIZE * 0.115
        d.rounded_rectangle([rule_x, line_y + SIZE * 0.006,
                             x0 + board_w * 0.85, line_y + SIZE * 0.030],
                            radius=SIZE * 0.012, fill=_tone(0.55))
    return img


# phase `draw=` key -> the function that draws it.
MARKS = {
    "clipboard": clipboard,
}

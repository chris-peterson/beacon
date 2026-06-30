#!/usr/bin/env python3
"""Generate iterm/done-bg.png — the faint `⏻` power-symbol watermark baked into
the beacon-done dynamic profile (RENDER-05). Re-run to regenerate the asset:

    python3 iterm/make-done-bg.py

The image is a transparent square with a centered power symbol: a ring open at
the top and a vertical bar rising through the gap. iTerm2 scales it to fit
(centered) and composites it over the near-black `done` background at a low
Blend, so it reads as a faint "powered off" watermark — the same `⏻` glyph that
anchors a completed session on the badge (BADGE-11) and in the fleet view
(WIP-12), at pane scale."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1200
STROKE = 130           # ring + bar thickness
RING_R = 320           # ring radius (center to stroke centerline)
GAP_DEG = 80           # angular size of the top opening
BAR_TOP = 230          # bar's top y
BAR_BOTTOM = 660       # bar's bottom y (overlaps into the ring)
# Light slate, fully opaque — the profile's low Blend dials it down to a faint
# watermark, so the asset itself stays crisp and tunable from one place (Blend).
MARK_RGBA = (200, 206, 224, 255)


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2

    # Ring open at the top. PIL arc angles run clockwise from 3 o'clock (0°), so
    # 12 o'clock is 270°; draw from just past the gap, clockwise all the way
    # around to just before it, leaving GAP_DEG centered on top.
    bbox = [cx - RING_R, cy - RING_R, cx + RING_R, cy + RING_R]
    start = 270 + GAP_DEG / 2
    end = 270 - GAP_DEG / 2 + 360
    draw.arc(bbox, start=start, end=end, fill=MARK_RGBA, width=STROKE)

    # Vertical bar rising through the gap.
    half = STROKE // 2
    draw.rounded_rectangle(
        [cx - half, BAR_TOP, cx + half, BAR_BOTTOM], radius=half, fill=MARK_RGBA
    )

    out = Path(__file__).resolve().parent / "done-bg.png"
    img.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

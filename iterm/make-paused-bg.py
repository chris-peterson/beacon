#!/usr/bin/env python3
"""Generate iterm/paused-bg.png — the faint `||` pause watermark baked into the
beacon-paused dynamic profile (RENDER-05). Re-run to regenerate the asset:

    python3 iterm/make-paused-bg.py

The image is a transparent square with two rounded vertical bars centered. iTerm2
scales it to fit (centered) and composites it over the paused background color at
a low Blend, so the bars read as a faint watermark — the same `||` pause glyph
that anchors the badge (BADGE-11) and the fleet view (WIP-12), at pane scale."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1200
BAR_W = 150
BAR_H = 560
GAP = 150
RADIUS = 60
# Light slate, fully opaque — the profile's low Blend dials it down to a faint
# watermark, so the asset itself stays crisp and tunable from one place (Blend).
BAR_RGBA = (200, 206, 224, 255)


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    top, bottom = cy - BAR_H // 2, cy + BAR_H // 2
    left_x = cx - GAP // 2 - BAR_W
    right_x = cx + GAP // 2
    for x in (left_x, right_x):
        draw.rounded_rectangle([x, top, x + BAR_W, bottom], radius=RADIUS, fill=BAR_RGBA)
    out = Path(__file__).resolve().parent / "paused-bg.png"
    img.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

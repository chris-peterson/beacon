#!/usr/bin/env python3
"""Generate iterm/release-bg.png — the faint rocket watermark baked into the
beacon-release dynamic profile (RENDER-05). Re-run to regenerate the asset:

    python3 iterm/make-release-bg.py

The image is a transparent square with a centered rocket rising: a pointed nose
cone over a rounded body (with the launch-sky background showing through a
punched porthole), two swept fins, and a tapering exhaust plume lifting off
beneath it. iTerm2 scales it to fit (centered) and composites it over the deep
navy `release` background at a low Blend, so the rocket reads as a faint "launch
in progress" watermark — the mode's cue that a ship-it flow is in progress."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1200
# Light slate, fully opaque — the profile's low Blend dials it down to a faint
# watermark, so the asset itself stays crisp and tunable from one place (Blend).
MARK_RGBA = (200, 206, 224, 255)


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = SIZE // 2

    # Rounded body.
    draw.rounded_rectangle([cx - 95, 380, cx + 95, 720], radius=42, fill=MARK_RGBA)
    # Pointed nose cone over the body's top.
    draw.polygon([(cx, 200), (cx - 95, 405), (cx + 95, 405)], fill=MARK_RGBA)
    # Swept fins flanking the base.
    draw.polygon([(cx - 95, 600), (cx - 95, 760), (cx - 180, 790)], fill=MARK_RGBA)
    draw.polygon([(cx + 95, 600), (cx + 95, 760), (cx + 180, 790)], fill=MARK_RGBA)
    # Exhaust plume lifting off beneath, with a small gap so it reads as thrust.
    draw.polygon([(cx - 55, 760), (cx + 55, 760), (cx, 940)], fill=MARK_RGBA)

    # Punch the porthole out to transparency so the amber background shows
    # through it — a single-color silhouette can't otherwise render the ring.
    alpha = img.getchannel("A")
    hole = ImageDraw.Draw(alpha)
    hole.ellipse([cx - 58, 452, cx + 58, 568], fill=0)
    img.putalpha(alpha)

    out = Path(__file__).resolve().parent / "release-bg.png"
    img.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

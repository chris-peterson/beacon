#!/usr/bin/env python3
"""Regenerate the watermark PNGs from their sources. Re-run after changing (or
adding) a mark in marks.py:

    python3 iterm/make-bg.py            # every phase
    python3 iterm/make-bg.py release    # one phase

Each phase writes three artifacts:

  iterm/resources/<phase>-src.png  the drawing, so the committed tree shows what
                                   went into every mark.
  iterm/resources/<phase>-bg.png   the full-size mark iTerm2 paints (MODE_SPECS /
                                   ATTENTION_SPECS `image`) and serve streams at
                                   /mode-bg/<mode>.
  docs/images/wm-<phase>.png       a thumbnail the palette doc embeds. The
                                   static docs site has no serve, so it needs a
                                   committed snapshot, regenerated here so it
                                   can't drift from the real mark."""

import sys
from pathlib import Path

from marks import MARKS
from watermark import render_watermark

HERE = Path(__file__).resolve().parent
RESOURCES = HERE / "resources"
DOCS_IMAGES = HERE.parent / "docs" / "images"
THUMB_SIZE = 240

def main(argv: list[str]) -> None:
    phases = argv or list(MARKS)
    unknown = [p for p in phases if p not in MARKS]
    if unknown:
        raise SystemExit(f"unknown phase(s): {', '.join(unknown)}; choose from {', '.join(MARKS)}")
    for phase in phases:
        src = RESOURCES / f"{phase}-src.png"
        MARKS[phase]().save(src, optimize=True)
        bg = RESOURCES / f"{phase}-bg.png"
        render_watermark(src).save(bg, optimize=True)
        thumb = DOCS_IMAGES / f"wm-{phase}.png"
        render_watermark(src, size=THUMB_SIZE).save(thumb, optimize=True)
        print(f"wrote {src} + {bg} + {thumb}")


if __name__ == "__main__":
    main(sys.argv[1:])

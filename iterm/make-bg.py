#!/usr/bin/env python3
"""Regenerate the mode watermark PNGs from their source art. Re-run after
changing (or adding) any source illustration:

    python3 iterm/make-bg.py            # every phase
    python3 iterm/make-bg.py release    # one phase

A phase's source is either a committed illustration at
iterm/resources/<phase>-src.png, or drawn by the marks.py function its `draw=`
key names — for a mark that wants a geometric primitive rather than a picture.
Either way, running it writes two artifacts:

  iterm/resources/<phase>-bg.png  the full-size mark iTerm2 paints (MODE_SPECS
                             `image`) and serve streams at /mode-bg/<mode>.
  docs/images/wm-<phase>.png a trimmed thumbnail the palette doc embeds (both
                             the pane and the dashboard consume the -bg.png via
                             serve, but the static docs site has no serve, so it
                             needs a committed snapshot — regenerated here so it
                             can't drift from the real mark).

PHASES below declares each source's treatment (see watermark.py) — the human
labels how a given source should translate; nothing is auto-detected. Found
sources are committed alongside so regeneration never depends on a network
fetch; drawn ones regenerate from marks.py, so their `-src.png` is an output
rather than an input."""

import sys
from pathlib import Path

from PIL import Image

from marks import MARKS
from watermark import ALPHA_CUTOFF, slate_watermark

HERE = Path(__file__).resolve().parent
RESOURCES = HERE / "resources"
DOCS_IMAGES = HERE.parent / "docs" / "images"
THUMB_MAX = 240

# phase -> config. `treatment` and the source-cleanup modifiers go to
# slate_watermark() (see watermark.py); `draw` names a marks.py function and
# means the source is generated rather than committed art. tonal (filled art
# with its own alpha) is the default; done's source arrived as a dark silhouette
# on a flattened checkerboard.
PHASES = {
    "pause": dict(treatment="tonal"),
    "release": dict(treatment="tonal"),
    "done": dict(treatment="silhouette"),
    "retro": dict(treatment="tonal", draw="clipboard"),
}


def _write_thumbnail(mark: Image.Image, phase: str) -> Path:
    """Trim the mark to its opaque bounds and downscale it for the palette doc."""
    m = mark.copy()
    bbox = m.getchannel("A").point(lambda a: 255 if a >= ALPHA_CUTOFF else 0).getbbox()
    if bbox:
        m = m.crop(bbox)
    m.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
    out = DOCS_IMAGES / f"wm-{phase}.png"
    m.save(out, optimize=True)
    return out


def main(argv: list[str]) -> None:
    phases = argv or list(PHASES)
    unknown = [p for p in phases if p not in PHASES]
    if unknown:
        raise SystemExit(f"unknown phase(s): {', '.join(unknown)}; choose from {', '.join(PHASES)}")
    for phase in phases:
        config = dict(PHASES[phase])
        draw = config.pop("draw", None)
        src = RESOURCES / f"{phase}-src.png"
        if draw:
            # A drawn source is written to the same path a found one occupies, so
            # the committed tree shows what went into every mark either way.
            MARKS[draw]().save(src)
        elif not src.exists():
            raise SystemExit(f"missing source art: {src}")
        mark = slate_watermark(src, **config)
        bg = RESOURCES / f"{phase}-bg.png"
        mark.save(bg)
        thumb = _write_thumbnail(mark, phase)
        print(f"wrote {bg} + {thumb}")


if __name__ == "__main__":
    main(sys.argv[1:])

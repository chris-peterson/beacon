#!/usr/bin/env python3
"""Shared watermark pipeline for the beacon mode and block profiles
(RENDER-05, RENDER-07).

Every pane watermark is a drawn source (marks.py, saved as
iterm/resources/<phase>-src.png) whose alpha is painted one flat slate
(THEME-02b), the same for every mode and block kind.
iTerm2 fits the square asset to the pane, centered, and composites it over the
pane background at a low Blend, so the mark reads as a faint watermark.
"""

from pathlib import Path

from PIL import Image

SIZE = 1200
# The slate every mark is painted. The profile's low Blend dials it down to a
# faint watermark, so the asset stays crisp and tunable from one place (Blend).
SLATE = "c8cee0"


def _rgb(hexstr: str) -> tuple[int, int, int]:
    return tuple(int(hexstr[i:i + 2], 16) for i in (0, 2, 4))


def render_watermark(src_path: Path, *, size: int = SIZE) -> Image.Image:
    """Paint a source's alpha flat in SLATE as a `size`-square PNG with a
    transparent background. The source's grid margin is the mark's margin, so it
    is scaled whole rather than trimmed, and every mark keeps one stroke weight."""
    alpha = Image.open(src_path).convert("RGBA").getchannel("A")
    mark = Image.new("RGBA", alpha.size, _rgb(SLATE) + (0,))
    mark.putalpha(alpha)
    return mark.resize((size, size), Image.LANCZOS)

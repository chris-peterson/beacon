"""beacon-iterm post-it composition.

Renders a yellow sticky-note shaped card with a folded bottom-right corner,
a subtle adhesive crease near the top, and centered text. The canvas
surrounding the card is fully transparent so iTerm2's per-pane background
color fills uniformly regardless of "Scale to Fit" / "Scale to Fill".

Requires Pillow (https://python-pillow.org), the standard Python image
library — `pip install Pillow`. Pillow is the only third-party dependency
in the entire beacon codebase, and only the post-it overlay needs it; the
rest of beacon is stdlib-only.
"""
from __future__ import annotations

from pathlib import Path

W, H = 1440, 1080

MAX_LINES = 4
NOTE_WRAP = 22
MASK_SS = 2

PAPER = (254, 224, 102, 255)
PAPER_EDGE = (212, 170, 40, 255)
PAPER_BACK = (224, 188, 70, 255)
INK = (44, 36, 18, 255)

FONT_PATHS = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFNS.ttf",
)


def has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _load_font(size: int):
    from PIL import ImageFont
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_chars: int, max_lines: int):
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur = f"{cur} {w}"
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines and len(words) > sum(len(l.split()) for l in lines):
        last = lines[-1]
        if len(last) > max_chars - 1:
            last = last[: max_chars - 1]
        lines[-1] = last + "…"
    return lines


def _fit_font(draw, lines, max_w: int, start_pt: int):
    pt = start_pt
    while pt >= 18:
        font = _load_font(pt)
        widest = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            widest = max(widest, bbox[2] - bbox[0])
        if widest <= max_w:
            return font, pt
        pt -= 2
    return _load_font(18), 18


def compose_note(text: str, out: Path, w: int = W, h: int = H) -> None:
    from PIL import Image, ImageDraw

    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    note_w = max(280, int(w * 0.92))
    note_h = max(200, int(h * 0.89))
    short = min(note_w, note_h)
    note_radius = max(12, int(short * 0.025))
    note_fold = max(50, int(short * 0.18))
    fold_inset = max(6, note_fold // 6)
    base_font_pt = max(28, int(note_h * 0.105))
    line_gap = max(8, int(base_font_pt * 0.35))
    note_wrap = max(NOTE_WRAP, int(note_w / max(1, base_font_pt) * 1.6))
    text_pad = max(20, int(short * 0.06))

    ss = MASK_SS
    mw, mh = note_w * ss, note_h * ss
    mask_hi = Image.new("L", (mw, mh), 0)
    mhd = ImageDraw.Draw(mask_hi)
    mhd.rounded_rectangle((0, 0, mw - 1, mh - 1), radius=note_radius * ss, fill=255)
    mhd.polygon([
        (mw - note_fold * ss, mh - 1),
        (mw - 1, mh - 1 - note_fold * ss),
        (mw - 1, mh - 1),
    ], fill=0)
    mask = mask_hi.resize((note_w, note_h), Image.LANCZOS)

    note = Image.new("RGBA", (note_w, note_h), (0, 0, 0, 0))
    paper_layer = Image.new("RGBA", (note_w, note_h), PAPER)
    note.paste(paper_layer, (0, 0), mask)

    nd = ImageDraw.Draw(note)

    fold_back = [
        (note_w - note_fold, note_h - 1),
        (note_w - 1, note_h - 1 - note_fold),
        (note_w - note_fold + fold_inset, note_h - 1 - note_fold + fold_inset),
    ]
    nd.polygon(fold_back, fill=PAPER_BACK)
    nd.line(
        [(note_w - note_fold, note_h - 1), (note_w - 1, note_h - 1 - note_fold)],
        fill=PAPER_EDGE, width=max(2, short // 300),
    )

    crease_y = int(note_h * 0.13)
    crease_inset = int(short * 0.03)
    crease_w = max(2, short // 350)
    nd.line(
        [(crease_inset, crease_y), (note_w - crease_inset, crease_y)],
        fill=(190, 152, 40, 200), width=crease_w,
    )
    nd.line(
        [(crease_inset, crease_y + crease_w + 2),
         (note_w - crease_inset, crease_y + crease_w + 2)],
        fill=(255, 240, 160, 130), width=max(1, crease_w // 2),
    )

    text_left = text_pad
    text_right = note_w - text_pad
    lines = _wrap_text(text, note_wrap, MAX_LINES) or [""]
    font, pt = _fit_font(nd, lines, text_right - text_left, base_font_pt)
    line_h = pt + line_gap
    text_h = line_h * len(lines)
    ty = max(text_pad, (note_h - text_h) // 2)
    for line in lines:
        bbox = nd.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        tx = text_left + ((text_right - text_left) - line_w) // 2
        nd.text((tx, ty), line, fill=INK, font=font)
        ty += line_h

    nx = (w - note.size[0]) // 2
    ny = (h - note.size[1]) // 2
    base.alpha_composite(note, (nx, ny))

    base.save(out)

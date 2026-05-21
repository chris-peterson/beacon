"""beacon-iterm pause-overlay composition.

Renders the pause overlay (OVERLAY-01) as a left-anchored marginalia card
on an otherwise transparent canvas, Dracula-themed:

    ┌──────────────┐
    │█ PAUSED · 14:23
    │█ ───
    │█
    │█ deferring until I
    │█ can interact with
    │█ each step
    │█
    └──────────────┘

A vertical pink accent stripe runs the full height of the card on the
left edge (the "marginalia" marker). The right ~60% of the canvas is
transparent so iTerm2's per-pane background color fills it uniformly
and terminal content under the right portion of the pane stays legible
when the user comes back.

Requires Pillow (https://python-pillow.org), the standard Python image
library — `pip install Pillow`. Pillow is the only third-party dependency
in the entire beacon codebase, and only the pause overlay needs it; the
rest of beacon is stdlib-only.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

W, H = 1440, 1080

CARD_LEFT_FRAC = 0.05
CARD_WIDTH_FRAC = 0.38
CARD_HEIGHT_FRAC = 0.78
CARD_RADIUS = 18
STRIPE_W = 8
PAD_X = 50
PAD_Y = 56
MASK_SS = 2
LABEL_TRACKING = 6
LABEL_PT = 54
META_PT = 28
BODY_START_PT = 38
BODY_FLOOR_PT = 22

# Dracula palette (THEME-01..03 — same hues, different roles).
#
# Card bg is the Dracula CURRENT LINE color — one notch lifted from the
# terminal bg, so the card reads as a distinct surface without shouting.
# OVERLAY-01's plugin path clears the visible viewport before paint, so the
# bg image has a clean canvas and a dark editorial card can read without
# competing with overlaid terminal text. Profile-side Blend = 1.0 lets the
# card render opaque so the chosen tone is the tone the user sees.
CARD_BG = (68, 71, 90, 255)      # #44475a — Dracula current line, lifted dark
ACCENT = (255, 121, 198, 255)    # #ff79c6 — pink, action/affordance accent
LABEL_HUE = (255, 121, 198, 255) # pink — sits crisply on the lifted-dark card
META_HUE = (98, 114, 164, 255)   # #6272a4 — comment, de-emphasized timestamp
RULE_HUE = (98, 114, 164, 180)   # comment @ ~70% alpha — short editorial rule
BODY_HUE = (248, 248, 242, 255)  # #f8f8f2 — Dracula foreground, body ink

BODY_MAX_LINES = 10
BODY_WRAP = 22

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
    """Greedy word-wrap. Last line truncates with an ellipsis if the source
    text doesn't fit in max_lines."""
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


def _fit_body(draw, lines, max_w: int, start_pt: int):
    """Shrink the body font until every line fits within max_w; floors at
    BODY_FLOOR_PT. Below the floor we accept overflow rather than render
    unreadable text — the wrap step already capped line length, so this
    only fires on extreme aspect ratios where pad eats most of the card."""
    pt = start_pt
    while pt >= BODY_FLOOR_PT:
        font = _load_font(pt)
        widest = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            widest = max(widest, bbox[2] - bbox[0])
        if widest <= max_w:
            return font, pt
        pt -= 2
    return _load_font(BODY_FLOOR_PT), BODY_FLOOR_PT


def _draw_tracked(draw, text: str, xy, font, fill, *, tracking: int = 0) -> int:
    """Draw text with manual per-glyph letter-spacing — Pillow has no tracking
    parameter. Returns the x just past the last glyph so callers can position
    follow-on text without recomputing the tracked width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), ch, font=font)
        x += (bbox[2] - bbox[0]) + tracking
    return x


def compose_note(text: str, out: Path, w: int = W, h: int = H) -> None:
    from PIL import Image, ImageDraw

    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    card_w = int(w * CARD_WIDTH_FRAC)
    card_h = int(h * CARD_HEIGHT_FRAC)
    card_x = int(w * CARD_LEFT_FRAC)
    card_y = (h - card_h) // 2

    # Build the card's filled interior: bg field + accent stripe baked in.
    # We then mask it with a rounded rectangle so the stripe's top-left and
    # bottom-left corners follow the card's curve instead of poking past it.
    fill = Image.new("RGBA", (card_w, card_h), CARD_BG)
    ImageDraw.Draw(fill).rectangle((0, 0, STRIPE_W, card_h), fill=ACCENT)

    ss = MASK_SS
    hi_mask = Image.new("L", (card_w * ss, card_h * ss), 0)
    ImageDraw.Draw(hi_mask).rounded_rectangle(
        (0, 0, card_w * ss - 1, card_h * ss - 1),
        radius=CARD_RADIUS * ss, fill=255,
    )
    mask = hi_mask.resize((card_w, card_h), Image.LANCZOS)

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    card.paste(fill, (0, 0), mask)

    cd = ImageDraw.Draw(card)

    text_left = STRIPE_W + PAD_X
    text_right = card_w - PAD_X
    cursor_y = PAD_Y

    label_font = _load_font(LABEL_PT)
    label_bbox = cd.textbbox((0, 0), "PAUSED", font=label_font)
    label_h = label_bbox[3] - label_bbox[1]
    label_end_x = _draw_tracked(
        cd, "PAUSED", (text_left, cursor_y), label_font, LABEL_HUE,
        tracking=LABEL_TRACKING,
    )

    meta_font = _load_font(META_PT)
    meta_text = f"  ·  {datetime.now().strftime('%H:%M')}"
    meta_bbox = cd.textbbox((0, 0), meta_text, font=meta_font)
    meta_h = meta_bbox[3] - meta_bbox[1]
    cd.text(
        (label_end_x, cursor_y + (label_h - meta_h)),
        meta_text, font=meta_font, fill=META_HUE,
    )

    cursor_y += label_h + 22

    cd.line(
        [(text_left, cursor_y), (text_left + 64, cursor_y)],
        fill=RULE_HUE, width=2,
    )
    cursor_y += 42

    body_max_w = text_right - text_left
    lines = _wrap_text(text, BODY_WRAP, BODY_MAX_LINES) or [""]
    body_font, body_pt = _fit_body(cd, lines, body_max_w, start_pt=BODY_START_PT)
    line_h = int(body_pt * 1.42)
    for line in lines:
        cd.text((text_left, cursor_y), line, font=body_font, fill=BODY_HUE)
        cursor_y += line_h

    base.alpha_composite(card, (card_x, card_y))
    base.save(out)

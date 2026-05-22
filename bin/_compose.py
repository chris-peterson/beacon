"""beacon-iterm marginalia-overlay composition.

Renders the marginalia overlay (OVERLAY-01) as a right-anchored card
sitting just below the iTerm2 status bar — Dracula-themed:

                                ╭──────────────────╮
                                │ █                  │
                                │ █ <LABEL> · 14:23  │
                                │ █                  │
                                │ █ description      │
                                │ █ body…            │
                                │ █                  │
                                ╰──────────────────╯

The label is the uppercased status name (PAUSED, WAITING, etc.) passed
in by the caller, so the same compose path serves any user-set status
with a description.

A vertical pink accent stripe runs the full height of the card on the
inner (left) edge — the "marginalia" marker that separates body content
in the pane from the card. The card has a small top inset so it doesn't
butt up against the iTerm2 status bar (the bg image fills the entire
pane area, and a y=0 card visually merges with the status bar above it).
The badge — at its profile-configured top margin — sits in the corner
above the card. The left ~60% of the canvas is transparent so the
underlying pane content stays legible when the user comes back.

The note text supports a small markdown subset:
- When the note has multiple lines, the first line renders as a bold
  subhead between the `PAUSED` label and the body; remaining lines
  flatten into one body paragraph.
- Any run of `*` chars toggles **bold**; any run of `_` chars toggles
  *italic*. Quantity doesn't matter — `*x*` and `**x**` are equivalent,
  and so are `_x_` and `__x__`. Markers can nest (`*_x_*` → bold italic).

Requires Pillow (https://python-pillow.org), the standard Python image
library — `pip install Pillow`. Pillow is the only third-party dependency
in the entire beacon codebase, and only the pause overlay needs it; the
rest of beacon is stdlib-only.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

W, H = 1440, 1080

CARD_GUTTER_FRAC = 0.04
CARD_TOP_FRAC = 0.05
CARD_WIDTH_FRAC = 0.38
CARD_HEIGHT_FRAC = 0.55
CARD_RADIUS = 18
STRIPE_W = 8
PAD_X = 50
PAD_Y = 56
MASK_SS = 2
LABEL_TRACKING = 6
LABEL_PT = 54
META_PT = 28
HEADING_PT = 40
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
HEADING_HUE = (248, 248, 242, 255)  # body fg for headings, weight carries emphasis
BODY_HUE = (248, 248, 242, 255)  # #f8f8f2 — Dracula foreground, body ink

BODY_MAX_LINES = 9
BODY_WRAP = 24
HEADING_WRAP = 22

# (path, face_index) candidates per weight. HelveticaNeue ships separate
# faces for Medium and Bold (and italic variants of both), so the body
# can lift off Regular without using full Bold — useful for a marginalia
# card meant to be read from a half-focused pane. Helvetica.ttc lacks a
# Medium face, so the fallback collapses Medium → Bold there.
FONT_CANDIDATES = {
    "regular": (
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 0),
    ),
    "medium": (
        ("/System/Library/Fonts/HelveticaNeue.ttc", 10),
        ("/System/Library/Fonts/Helvetica.ttc", 1),
    ),
    "medium-italic": (
        ("/System/Library/Fonts/HelveticaNeue.ttc", 11),
        ("/System/Library/Fonts/Helvetica.ttc", 2),
    ),
    "bold": (
        ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
        ("/System/Library/Fonts/Helvetica.ttc", 1),
    ),
    "bold-italic": (
        ("/System/Library/Fonts/HelveticaNeue.ttc", 3),
        ("/System/Library/Fonts/Helvetica.ttc", 3),
    ),
}


def has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _load_font(size: int, *, weight: str = "regular"):
    from PIL import ImageFont
    for path, idx in FONT_CANDIDATES.get(weight, FONT_CANDIDATES["regular"]):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


Segment = tuple[str, bool, bool]
Word = list[Segment]


def _parse_to_words(text: str) -> list[Word]:
    """Walk `text`, applying markdown markers, and emit a list of words.

    A run of `*` chars toggles bold; a run of `_` chars toggles italic.
    Quantity within a run doesn't matter — `*x*` and `**x**` both render
    as bold "x". Markers can nest (`*_x_*` → bold italic "x"). Markers
    are not emitted in the output.

    Each output word is a list of `(text, bold, italic)` segments that
    render adjacently without inter-segment spaces, so a marker boundary
    inside a non-whitespace token (e.g. `**users**,`) stays glued — the
    bold "users" and the medium "," ship as one word, not two.
    """
    words: list[Word] = []
    current: Word = []
    seg: list[str] = []
    bold = False
    italic = False

    def flush_seg() -> None:
        if seg:
            current.append(("".join(seg), bold, italic))
            seg.clear()

    def flush_word() -> None:
        flush_seg()
        if current:
            words.append(current[:])
            current.clear()

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "*" or ch == "_":
            flush_seg()
            while i < n and text[i] == ch:
                i += 1
            if ch == "*":
                bold = not bold
            else:
                italic = not italic
        elif ch.isspace():
            flush_word()
            while i < n and text[i].isspace():
                i += 1
        else:
            seg.append(ch)
            i += 1
    flush_word()
    return words


def _parse_markdown(text: str) -> tuple[list[Word] | None, list[Word]]:
    """Parse the note text into (heading_words, body_words).

    When the input is a single line, there is no heading and the line
    becomes the body. When the input has multiple lines, the first
    non-empty line is the heading and the remaining lines flatten into
    a single body paragraph. Inline `*`/`_` markers (see _parse_to_words)
    are honored in both heading and body.
    """
    text = (text or "").strip()
    if not text:
        return None, []

    nl = text.find("\n")
    if nl < 0:
        return None, _parse_to_words(text)

    heading_text = text[:nl].strip()
    rest = text[nl + 1:]
    heading_words = _parse_to_words(heading_text) if heading_text else None

    body = " ".join(line.strip() for line in rest.split("\n") if line.strip())
    if not body:
        return heading_words, []
    return heading_words, _parse_to_words(body)


def _word_len(word: Word) -> int:
    return sum(len(text) for text, _, _ in word)


def _wrap_words(
    words: list[Word], max_chars: int, max_lines: int,
) -> list[list[Word]]:
    """Greedy word-wrap by character count. Returns lines, each a list of
    Words. A Word is multi-segment so its style transitions stay glued
    inside the word and don't get broken by the wrap. Last line truncates
    with an ellipsis on overflow."""
    lines: list[list[Word]] = []
    cur: list[Word] = []
    cur_len = 0
    overflow = False
    for word in words:
        wl = _word_len(word)
        if not cur:
            cur = [word]
            cur_len = wl
        elif cur_len + 1 + wl <= max_chars:
            cur.append(word)
            cur_len += 1 + wl
        else:
            lines.append(cur)
            if len(lines) >= max_lines:
                overflow = True
                break
            cur = [word]
            cur_len = wl
    if not overflow and cur and len(lines) < max_lines:
        lines.append(cur)

    if overflow and lines:
        last_words = lines[-1]
        if last_words:
            tail_word = last_words[-1]
            if tail_word:
                tail_text, tail_bold, tail_italic = tail_word[-1]
                pre_len = sum(
                    _word_len(w) + (1 if i > 0 else 0)
                    for i, w in enumerate(last_words[:-1])
                )
                ellipsis_budget = max_chars - pre_len
                if ellipsis_budget < len(tail_text) + 1:
                    tail_text = tail_text[: max(0, ellipsis_budget - 1)]
                tail_text = tail_text.rstrip(",.;:") + "…"
                tail_word[-1] = (tail_text, tail_bold, tail_italic)
    return lines


def _build_fonts(pt: int) -> dict[tuple[bool, bool], object]:
    """Build the per-style font dict at a given point size. Keyed by
    (bold, italic) so callers don't have to branch over weight strings."""
    return {
        (False, False): _load_font(pt, weight="medium"),
        (False, True): _load_font(pt, weight="medium-italic"),
        (True, False): _load_font(pt, weight="bold"),
        (True, True): _load_font(pt, weight="bold-italic"),
    }


def _space_width(draw, fonts) -> int:
    """Width of a space glyph in the default (medium) face. Used to
    space words inside a wrapped line, independent of each word's
    weight — keeps inter-word gaps visually consistent across styles."""
    return draw.textbbox((0, 0), " ", font=fonts[(False, False)])[2]


def _line_pixel_width(draw, line_words: list[Word], fonts) -> int:
    """Pixel width of a wrapped line, summing per-segment widths under
    the appropriate face plus a space between adjacent words. Segments
    inside a single word render adjacent with no inter-segment space."""
    space_w = _space_width(draw, fonts)
    total = 0
    for i, word in enumerate(line_words):
        if i > 0:
            total += space_w
        for seg_text, bold, italic in word:
            font = fonts[(bold, italic)]
            bbox = draw.textbbox((0, 0), seg_text, font=font)
            total += bbox[2] - bbox[0]
    return total


def _fit_body_runs(draw, lines, max_w: int, start_pt: int):
    """Shrink the body font until every wrapped line fits within max_w.
    Floors at BODY_FLOOR_PT — below that we accept overflow rather than
    render unreadable text on extreme aspect ratios."""
    pt = start_pt
    while pt >= BODY_FLOOR_PT:
        fonts = _build_fonts(pt)
        widest = max(
            (_line_pixel_width(draw, line, fonts) for line in lines),
            default=0,
        )
        if widest <= max_w:
            return fonts, pt
        pt -= 2
    return _build_fonts(BODY_FLOOR_PT), BODY_FLOOR_PT


def _draw_runs_line(draw, line_words: list[Word], xy, fonts, fill) -> int:
    """Render a wrapped line, swapping faces per segment style within a
    word. Words are space-separated; segments inside a word render
    adjacent with no space."""
    x, y = xy
    space_w = _space_width(draw, fonts)
    for i, word in enumerate(line_words):
        if i > 0:
            x += space_w
        for seg_text, bold, italic in word:
            font = fonts[(bold, italic)]
            draw.text((x, y), seg_text, font=font, fill=fill)
            bbox = draw.textbbox((0, 0), seg_text, font=font)
            x += bbox[2] - bbox[0]
    return x


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


def compose_note(label: str, text: str, out: Path, w: int = W, h: int = H) -> None:
    from PIL import Image, ImageDraw

    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    card_w = int(w * CARD_WIDTH_FRAC)
    card_h = int(h * CARD_HEIGHT_FRAC)
    card_x = w - card_w - int(w * CARD_GUTTER_FRAC)
    card_y = int(h * CARD_TOP_FRAC)

    # Build the filled interior: bg field + accent stripe baked on the
    # inner (left) edge of the card so the right edge stays clean and
    # the badge above the card has uninterrupted backdrop.
    fill = Image.new("RGBA", (card_w, card_h), CARD_BG)
    ImageDraw.Draw(fill).rectangle((0, 0, STRIPE_W, card_h), fill=ACCENT)

    ss = MASK_SS
    hi_mask = Image.new("L", (card_w * ss, card_h * ss), 0)
    ImageDraw.Draw(hi_mask).rounded_rectangle(
        (0, 0, card_w * ss - 1, card_h * ss - 1),
        radius=CARD_RADIUS * ss,
        fill=255,
    )
    mask = hi_mask.resize((card_w, card_h), Image.LANCZOS)

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    card.paste(fill, (0, 0), mask)

    cd = ImageDraw.Draw(card)

    text_left = STRIPE_W + PAD_X
    text_right = card_w - PAD_X
    cursor_y = PAD_Y

    heading_words, body_words = _parse_markdown(text)

    label_text = (label or "PAUSED").upper()
    label_font = _load_font(LABEL_PT, weight="bold")
    label_bbox = cd.textbbox((0, 0), label_text, font=label_font)
    label_h = label_bbox[3] - label_bbox[1]
    label_end_x = _draw_tracked(
        cd, label_text, (text_left, cursor_y), label_font, LABEL_HUE,
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

    if heading_words:
        heading_lines = _wrap_words(heading_words, HEADING_WRAP, max_lines=2)
        # Headings stay bold regardless of inline markers — bold-italic
        # when the run is italic, plain bold otherwise. Italic inside a
        # heading still differentiates from non-italic spans.
        heading_fonts = {
            (False, False): _load_font(HEADING_PT, weight="bold"),
            (False, True): _load_font(HEADING_PT, weight="bold-italic"),
            (True, False): _load_font(HEADING_PT, weight="bold"),
            (True, True): _load_font(HEADING_PT, weight="bold-italic"),
        }
        heading_line_h = int(HEADING_PT * 1.32)
        for line in heading_lines:
            _draw_runs_line(cd, line, (text_left, cursor_y), heading_fonts, HEADING_HUE)
            cursor_y += heading_line_h
        cursor_y += 16

    body_max_w = text_right - text_left
    body_lines = _wrap_words(body_words, BODY_WRAP, BODY_MAX_LINES)
    if body_lines:
        body_fonts, body_pt = _fit_body_runs(cd, body_lines, body_max_w, BODY_START_PT)
        line_h = int(body_pt * 1.42)
        for line in body_lines:
            _draw_runs_line(cd, line, (text_left, cursor_y), body_fonts, BODY_HUE)
            cursor_y += line_h

    base.alpha_composite(card, (card_x, card_y))
    base.save(out)

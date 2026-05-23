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
  subhead between the `PAUSED` label and the body; remaining body lines
  coalesce into one paragraph except where a `* `-prefixed list breaks
  them up (see below).
- Any run of `*` chars toggles **bold**; any run of `_` chars toggles
  *italic*; any run of `~` chars toggles ~strikethrough~. Quantity
  doesn't matter — `*x*` and `**x**` are equivalent. Markers compose
  (`*_x_*` → bold italic).
- In the body, a line beginning with `* ` (asterisk + space) renders
  as a bulleted list item. Consecutive non-list lines join into one
  paragraph; list items render with a bullet glyph and hang indent.
  Inline `*` runs inside a list item still toggle bold as usual.

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
BODY_PT = 38

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
HEADING_MAX_LINES = 2

# Pixels of vertical breathing room reserved between the last body line
# and the card's rounded bottom edge. compose_note caps the effective
# line count at card_h - cursor_y - BODY_BOTTOM_PAD divided by line_h,
# so content past the visible card area truncates with ellipsis instead
# of bleeding into the transparent rounded-corner region.
BODY_BOTTOM_PAD = 40

BULLET_CHAR = "•"
# Pixels added to text_left for list-item rows — clears the bullet
# glyph + a small visual gap at BODY_PT.
BULLET_INDENT = 28

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


Segment = tuple[str, bool, bool, bool]  # (text, bold, italic, strike)
Word = list[Segment]
Block = tuple[str, list[Word]]  # ("para" | "li", words)


def _parse_to_words(text: str) -> list[Word]:
    """Walk `text`, applying inline markdown markers, and emit a list of words.

    A run of `*` chars toggles bold; a run of `_` chars toggles italic;
    a run of `~` chars toggles strikethrough. Quantity within a run
    doesn't matter — `*x*` and `**x**` both render as bold "x". Markers
    compose (`*_x_*` → bold italic). Markers are not emitted in output.

    Each output word is a list of `(text, bold, italic, strike)` segments
    that render adjacently without inter-segment spaces, so a marker
    boundary inside a non-whitespace token (e.g. `**users**,`) stays
    glued — the bold "users" and the medium "," ship as one word.
    """
    words: list[Word] = []
    current: Word = []
    seg: list[str] = []
    bold = False
    italic = False
    strike = False

    def flush_seg() -> None:
        if seg:
            current.append(("".join(seg), bold, italic, strike))
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
        if ch in ("*", "_", "~"):
            flush_seg()
            while i < n and text[i] == ch:
                i += 1
            if ch == "*":
                bold = not bold
            elif ch == "_":
                italic = not italic
            else:
                strike = not strike
        elif ch.isspace():
            flush_word()
            while i < n and text[i].isspace():
                i += 1
        else:
            seg.append(ch)
            i += 1
    flush_word()
    return words


def _split_blocks(lines: list[str]) -> list[Block]:
    """Split body lines into paragraph and list-item blocks.

    Consecutive non-list lines coalesce into a single paragraph block;
    each `* `-prefixed line becomes a list-item block. The leading
    `* ` is consumed as the list marker so the item text is parsed
    by `_parse_to_words` without the prefix re-triggering bold.
    """
    blocks: list[Block] = []
    para_buf: list[str] = []

    def flush_para() -> None:
        if para_buf:
            joined = " ".join(para_buf)
            blocks.append(("para", _parse_to_words(joined)))
            para_buf.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("* "):
            flush_para()
            blocks.append(("li", _parse_to_words(line[2:])))
        else:
            para_buf.append(line)
    flush_para()
    return blocks


def _parse_markdown(text: str) -> tuple[list[Word] | None, list[Block]]:
    """Parse the note text into (heading_words, body_blocks).

    Single-line input has no heading and the line becomes one body
    block (paragraph, or list-item when the line starts with `* `).
    Multi-line input treats the first non-empty line as the heading
    and the remainder as body blocks per `_split_blocks`. The heading
    line is parsed verbatim — `* ` at the heading's start does not
    promote it to a list item; the heading is the heading.
    """
    text = (text or "").strip()
    if not text:
        return None, []

    lines = text.split("\n")
    if len(lines) == 1:
        return None, _split_blocks(lines)

    heading_idx = next((i for i, l in enumerate(lines) if l.strip()), None)
    if heading_idx is None:
        return None, []
    heading_text = lines[heading_idx].strip()
    heading_words = _parse_to_words(heading_text) if heading_text else None
    return heading_words, _split_blocks(lines[heading_idx + 1:])


def _word_pixel_width(draw, word: Word, fonts) -> int:
    """Pixel width of a single word — sum of per-segment glyph widths
    under the appropriate face. Segments inside a word render adjacent
    with no inter-segment space."""
    total = 0
    for seg_text, bold, italic, _strike in word:
        font = fonts[(bold, italic)]
        bbox = draw.textbbox((0, 0), seg_text, font=font)
        total += bbox[2] - bbox[0]
    return total


def _line_pixel_width(draw, line_words: list[Word], fonts) -> int:
    """Pixel width of a wrapped line — sum of word widths plus an
    inter-word space between adjacent words."""
    space_w = _space_width(draw, fonts)
    total = 0
    for i, word in enumerate(line_words):
        if i > 0:
            total += space_w
        total += _word_pixel_width(draw, word, fonts)
    return total


def _wrap_by_pixels(
    draw, words: list[Word], max_w_px: int, max_lines: int, fonts,
) -> list[list[Word]]:
    """Greedy pixel-based word wrap. A Word's multi-segment style stays
    glued inside the word; wrap only happens between words.

    Two truncation paths kick in when content doesn't fit:
    - Regular overflow (more words than fit in `max_lines`): drop tail
      words from the last visible line until the line plus '…' fits.
    - Oversized single word (one Word wider than `max_w_px`): trim the
      word's tail text until the word with '…' suffix fits, then stop
      wrapping. The trimmed form carries the ellipsis itself, so no
      outer truncation pass is needed on that line.
    """
    space_w = _space_width(draw, fonts)
    lines: list[list[Word]] = []
    cur: list[Word] = []
    cur_w = 0
    overflow = False

    for word in words:
        ww = _word_pixel_width(draw, word, fonts)
        if ww > max_w_px:
            truncated = _truncate_oversized_word(draw, word, max_w_px, fonts)
            if cur:
                lines.append(cur)
                cur = []
                cur_w = 0
            if len(lines) < max_lines:
                lines.append([truncated])
            overflow = True
            break
        if not cur:
            cur = [word]
            cur_w = ww
        elif cur_w + space_w + ww <= max_w_px:
            cur.append(word)
            cur_w += space_w + ww
        else:
            lines.append(cur)
            if len(lines) >= max_lines:
                overflow = True
                break
            cur = [word]
            cur_w = ww

    if not overflow and cur and len(lines) < max_lines:
        lines.append(cur)

    if overflow and lines:
        last_text = lines[-1][-1][-1][0]
        if not last_text.endswith("…"):
            _truncate_with_ellipsis(draw, lines[-1], max_w_px, fonts)
    return lines


def _truncate_with_ellipsis(
    draw, line_words: list[Word], max_w_px: int, fonts,
) -> None:
    """Mutate `line_words` to end with `<tail>…`, dropping tail words
    until the line fits within max_w_px. Mutates the tail Word's last
    Segment in place; preserves its style (bold/italic/strike).

    When popping would empty the line — i.e. even the final word with
    an ellipsis suffix is wider than max_w_px — fall through to the
    in-word truncation path on that last word so the line always
    carries a visible '…' rather than rendering as a blank slot.
    """
    while line_words:
        tail_word = line_words[-1]
        original = tail_word[-1]
        text, bold, italic, strike = original
        tail_word[-1] = (text.rstrip(",.;:") + "…", bold, italic, strike)
        if _line_pixel_width(draw, line_words, fonts) <= max_w_px:
            return
        tail_word[-1] = original
        if len(line_words) == 1:
            line_words[-1] = _truncate_oversized_word(
                draw, tail_word, max_w_px, fonts,
            )
            return
        line_words.pop()


def _truncate_oversized_word(
    draw, word: Word, max_w_px: int, fonts,
) -> Word:
    """Trim a too-wide word so the truncated form (with '…' suffix)
    fits within max_w_px. Operates on the tail segment first; if it
    exhausts, drops the segment and recurses on the head. Returns a new
    Word; leaves the input untouched."""
    if not word:
        return word
    text, bold, italic, strike = word[-1]
    head = list(word[:-1])
    while text:
        candidate = head + [(text.rstrip("-_.,;:") + "…", bold, italic, strike)]
        if _word_pixel_width(draw, candidate, fonts) <= max_w_px:
            return candidate
        text = text[:-1]
    if head:
        return _truncate_oversized_word(draw, head, max_w_px, fonts)
    return [("…", False, False, False)]


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


# Row carries the wrapped line plus the per-row x-offset added to text_left
# at render time (0 for paragraph lines, BULLET_INDENT for list-item lines)
# and whether this row should draw a bullet glyph in the gutter (true only
# on the first wrapped row of a list item).
Row = tuple[list[Word], int, bool]


def _layout_body(
    draw, blocks: list[Block], fonts, body_max_w: int, max_lines: int,
) -> list[Row]:
    """Compose body rows from blocks, capping the total at `max_lines`.

    Paragraph blocks wrap at body_max_w and render flush-left. List-item
    blocks wrap at body_max_w - BULLET_INDENT and render at x_offset
    BULLET_INDENT so the bullet glyph + gap fits in the gutter. Only the
    first wrapped row of a list item carries the bullet — continuation
    rows hang-indent with no glyph. When the body would exceed
    max_lines, the last visible line is truncated with an ellipsis.
    """
    rows: list[Row] = []
    remaining = max_lines
    for kind, words in blocks:
        if remaining <= 0:
            break
        if kind == "li":
            wrap_w = body_max_w - BULLET_INDENT
            x_off = BULLET_INDENT
        else:
            wrap_w = body_max_w
            x_off = 0
        lines = _wrap_by_pixels(draw, words, wrap_w, remaining, fonts)
        for i, line in enumerate(lines):
            rows.append((line, x_off, kind == "li" and i == 0))
        remaining -= len(lines)
    return rows


def _compute_strike_runs(
    draw, line_words: list[Word], x0: int, fonts,
) -> list[tuple[int, int, object]]:
    """Walk `line_words` starting at x0 and return a list of (start_x,
    end_x, font) tuples — one per contiguous run of strikethrough
    segments, including inter-word spaces when both adjacent words are
    struck. The font is the run's first-segment face, used by the
    caller to pick a consistent y from `font.getmetrics().ascent`.

    Factored out of `_draw_runs_line` so the merging logic is testable
    without driving a real ImageDraw render.
    """
    x = x0
    space_w = _space_width(draw, fonts)
    runs: list[tuple[int, int, object]] = []
    run_start: int | None = None
    run_font = None

    for word_i, word in enumerate(line_words):
        if word_i > 0:
            next_strike = word[0][3]
            if run_start is not None and next_strike:
                x += space_w
            else:
                if run_start is not None:
                    runs.append((run_start, x, run_font))
                    run_start = None
                    run_font = None
                x += space_w

        for seg_text, bold, italic, strike in word:
            font = fonts[(bold, italic)]
            advance = draw.textbbox((0, 0), seg_text, font=font)
            seg_w = advance[2] - advance[0]
            if strike:
                if run_start is None:
                    run_start = x
                    run_font = font
            else:
                if run_start is not None:
                    runs.append((run_start, x, run_font))
                    run_start = None
                    run_font = None
            x += seg_w

    if run_start is not None:
        runs.append((run_start, x, run_font))
    return runs


def _draw_runs_line(draw, line_words: list[Word], xy, fonts, fill) -> int:
    """Render a wrapped line, swapping faces per segment style within a
    word. Words are space-separated; segments inside a word render
    adjacent with no space.

    Strikethrough is drawn as a continuous run spanning all contiguous
    struck segments — including the inter-word spaces inside the run
    (see `_compute_strike_runs`). The strike y is anchored to the run's
    first-segment font ascent rather than per-glyph bbox, so the line
    doesn't jog between letters with different x-heights.
    """
    x, y = xy
    space_w = _space_width(draw, fonts)

    strike_runs = _compute_strike_runs(draw, line_words, x, fonts)

    for word_i, word in enumerate(line_words):
        if word_i > 0:
            x += space_w
        for seg_text, bold, italic, _strike in word:
            font = fonts[(bold, italic)]
            draw.text((x, y), seg_text, font=font, fill=fill)
            advance = draw.textbbox((0, 0), seg_text, font=font)
            x += advance[2] - advance[0]

    for start_x, end_x, font in strike_runs:
        ascent, _descent = font.getmetrics()
        strike_y = y + int(ascent * 0.62)
        strike_h = max(2, int(font.size * 0.08))
        draw.line(
            [(start_x, strike_y), (end_x, strike_y)],
            fill=fill, width=strike_h,
        )

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

    heading_words, body_blocks = _parse_markdown(text)

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

    body_max_w = text_right - text_left

    if heading_words:
        # Headings stay bold regardless of inline markers — bold-italic
        # when the run is italic, plain bold otherwise. Italic inside a
        # heading still differentiates from non-italic spans.
        heading_fonts = {
            (False, False): _load_font(HEADING_PT, weight="bold"),
            (False, True): _load_font(HEADING_PT, weight="bold-italic"),
            (True, False): _load_font(HEADING_PT, weight="bold"),
            (True, True): _load_font(HEADING_PT, weight="bold-italic"),
        }
        heading_lines = _wrap_by_pixels(
            cd, heading_words, body_max_w, HEADING_MAX_LINES, heading_fonts,
        )
        heading_line_h = int(HEADING_PT * 1.32)
        for line in heading_lines:
            _draw_runs_line(cd, line, (text_left, cursor_y), heading_fonts, HEADING_HUE)
            cursor_y += heading_line_h
        cursor_y += 16

    body_fonts = _build_fonts(BODY_PT)
    line_h = int(BODY_PT * 1.42)
    available_body_h = card_h - cursor_y - BODY_BOTTOM_PAD
    effective_max_lines = max(0, min(BODY_MAX_LINES, available_body_h // line_h))
    body_rows = _layout_body(cd, body_blocks, body_fonts, body_max_w, effective_max_lines)
    if body_rows:
        bullet_font = body_fonts[(False, False)]
        for line, x_off, render_bullet in body_rows:
            if render_bullet:
                cd.text((text_left, cursor_y), BULLET_CHAR, font=bullet_font, fill=BODY_HUE)
            _draw_runs_line(cd, line, (text_left + x_off, cursor_y), body_fonts, BODY_HUE)
            cursor_y += line_h

    base.alpha_composite(card, (card_x, card_y))
    base.save(out)

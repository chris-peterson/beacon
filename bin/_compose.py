"""beacon-iterm marginalia-overlay composition.

Renders the marginalia overlay (OVERLAY-01) as a compact card tucked
into the top-right corner, resting a little under twice the badge's
height — Dracula-themed:

                                      ╭──────────────╮
                                      │ █ <LABEL>      │
                                      │ █ description… │
                                      ╰──────────────╯

The label is the uppercased status name (PAUSED, WAITING, etc.) passed
in by the caller, so the same compose path serves any user-set status
with a description.

A vertical pink accent stripe runs the full height of the card on the
inner (left) edge — the "marginalia" marker that separates body content
in the pane from the card. The card sits below the badge with a top
inset large enough to clear aspect-fill's vertical crop (see
CARD_TOP_FRAC). The badge — at its profile-configured top margin — sits
above the card. The rest of the canvas is transparent so the underlying
pane content stays legible, and so foreground terminal text redrawn over
the bg image only competes with the card's small footprint.

A long note grows the card downward (up to CARD_MAX_GROWTH x the resting
height) and then shrinks the body font before it truncates, so more of a
long note survives without enlarging the common short-note case.

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

from pathlib import Path

W, H = 1440, 1080

# The overlay is a full-pane background image displayed under iTerm2's
# aspect-fill mode (Background Image Mode 2), so the "card" is a small
# panel in the top-right corner of an otherwise transparent canvas. Sizes
# are fractions of the canvas so the card keeps its on-pane proportions
# across pane sizes; per-card type and padding scale from card_h in
# _card_metrics so the whole card shrinks as one unit.
#
# CARD_TOP_FRAC clears two things: the badge (profile Badge Max Height
# ~0.06, top-right) and aspect-fill's vertical crop. The canvas aspect is
# a guess — cols x cell_w by lines x cell_h — and when the real cell is
# wider than the 7:16 estimate the pane is wider than the canvas, so
# aspect-fill scales to width and crops top + bottom (centered). A card
# flush to the top loses its label to that crop; the inset sits the card
# below the cropped band. 0.14 absorbs the worst-case top crop for
# realistic monospace cell ratios (~0.42–0.60); the deliberately narrow
# 7:16 guess keeps the crop axis vertical (raising the guess toward 0.5
# would instead crop the right edge and clip the card's outer corner), so
# the matching horizontal risk stays under CARD_GUTTER_FRAC.
CARD_WIDTH_FRAC = 0.28
CARD_HEIGHT_FRAC = 0.13
CARD_TOP_FRAC = 0.14
CARD_GUTTER_FRAC = 0.05
MASK_SS = 2

# CARD_HEIGHT_FRAC is the resting height. A long note grows the card down to
# CARD_MAX_GROWTH x that before any text is dropped; once the grown card is
# full, the body font shrinks (down to CARD_MIN_FONT_SCALE of its resting
# size) to pack more in, and only then does the body truncate. Short notes
# never leave the resting height or the resting font.
CARD_MAX_GROWTH = 2.0
CARD_MIN_FONT_SCALE = 0.6

# Reference body size and list indent for the layout/wrap helpers (and the
# tests that drive them directly). compose_note renders at a card-scaled
# size from _card_metrics, not these — these only set the helper defaults.
BODY_PT = 38
BULLET_INDENT = 28

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
HEADING_HUE = (248, 248, 242, 255)  # body fg for headings, weight carries emphasis
BODY_HUE = (248, 248, 242, 255)  # #f8f8f2 — Dracula foreground, body ink

BODY_MAX_LINES = 9
HEADING_MAX_LINES = 2

BULLET_CHAR = "•"

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
    bullet_indent: int = BULLET_INDENT,
) -> list[Row]:
    """Compose body rows from blocks, capping the total at `max_lines`.

    Paragraph blocks wrap at body_max_w and render flush-left. List-item
    blocks wrap at body_max_w - bullet_indent and render at x_offset
    bullet_indent so the bullet glyph + gap fits in the gutter. Only the
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
            wrap_w = body_max_w - bullet_indent
            x_off = bullet_indent
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


def _card_metrics(card_h: int) -> dict[str, int]:
    """Derive the frame, label, and resting body size from the resting card
    height.

    Every value is a fixed fraction of the resting height (CARD_HEIGHT_FRAC),
    so the card reads at consistent proportions across pane sizes. Floors keep
    the smallest panes legible. The label anchors the card and stays this size
    even when a long note shrinks the body font (compose_note scales
    `body_pt` down from here). Heading shares the body size — on a card this
    small a separate large subhead would eat the whole height, so the first
    line differentiates by weight (bold) alone, set off by generous margins
    above and below.
    """
    body_pt = max(10, round(card_h * 0.17))
    return {
        "pad_x": max(6, round(card_h * 0.15)),
        "pad_top": max(5, round(card_h * 0.12)),
        "pad_bottom": max(4, round(card_h * 0.10)),
        "stripe_w": max(3, round(card_h * 0.05)),
        "radius": max(4, round(card_h * 0.11)),
        "label_pt": max(11, round(card_h * 0.22)),
        "body_pt": body_pt,
        "label_tracking": max(1, round(card_h * 0.045)),
        "label_gap": max(3, round(card_h * 0.05)),
        "heading_gap_above": max(6, round(card_h * 0.14)),
        "heading_gap_below": max(5, round(card_h * 0.12)),
        "bullet_indent": max(10, round(body_pt * 0.8)),
    }


def _heading_fonts(pt: int) -> dict[tuple[bool, bool], object]:
    """Heading faces at `pt` — always bold (bold-italic when the run is
    italic) so the subhead reads as emphasis regardless of inline markers."""
    bold = _load_font(pt, weight="bold")
    bold_italic = _load_font(pt, weight="bold-italic")
    return {
        (False, False): bold,
        (False, True): bold_italic,
        (True, False): bold,
        (True, True): bold_italic,
    }


def _line_height(body_pt: int) -> int:
    return round(body_pt * 1.35)


def _copy_blocks(blocks: list[Block]) -> list[Block]:
    """Deep-enough copy for re-layout: each Word becomes a fresh list so the
    in-place truncation in `_wrap_by_pixels` can't bleed a stray `…` from one
    layout pass into the next. Segments are immutable tuples, so the words
    themselves don't need copying — only the lists that hold them."""
    return [(kind, [list(word) for word in words]) for kind, words in blocks]


def compose_note(label: str, text: str, out: Path, w: int = W, h: int = H) -> None:
    from PIL import Image, ImageDraw

    card_w = int(w * CARD_WIDTH_FRAC)
    rest_h = int(h * CARD_HEIGHT_FRAC)
    max_h = int(rest_h * CARD_MAX_GROWTH)
    card_x = w - card_w - int(w * CARD_GUTTER_FRAC)
    card_y = int(h * CARD_TOP_FRAC)

    # Frame, label, and resting body size all derive from the resting height;
    # the card grows from there and the body font shrinks within it, so the
    # frame stays put while only the body type adapts to the note's length.
    m = _card_metrics(rest_h)
    text_left = m["stripe_w"] + m["pad_x"]
    body_max_w = card_w - m["pad_x"] - text_left

    heading_words, body_blocks = _parse_markdown(text)

    label_text = (label or "PAUSED").upper()
    label_font = _load_font(m["label_pt"], weight="bold")

    # Measure on a scratch canvas before we know the final card height.
    scratch = ImageDraw.Draw(Image.new("RGBA", (max(1, card_w), max(1, max_h))))
    label_bbox = scratch.textbbox((0, 0), label_text, font=label_font)
    label_h = label_bbox[3] - label_bbox[1]

    gap_above = m["heading_gap_above"] if heading_words else m["label_gap"]
    gap_below = m["heading_gap_below"] if heading_words else 0

    def fixed_overhead(heading_line_count: int, line_h: int) -> int:
        """Vertical space the body does not get: label, heading, every gap,
        and both pads."""
        return (m["pad_top"] + label_h + gap_above
                + heading_line_count * line_h + gap_below + m["pad_bottom"])

    # Pick the largest body font (resting size down to CARD_MIN_FONT_SCALE) at
    # which the whole note fits the grown-to-max card. Short notes settle at
    # the resting font on the first pass; a long note steps the font down so
    # more of it survives before the truncation cap applies.
    scale = 1.0
    while True:
        body_pt = max(8, round(m["body_pt"] * scale))
        line_h = _line_height(body_pt)
        body_fonts = _build_fonts(body_pt)
        heading_fonts = _heading_fonts(body_pt) if heading_words else None
        heading_lines = (
            _wrap_by_pixels(scratch, heading_words, body_max_w,
                            HEADING_MAX_LINES, heading_fonts)
            if heading_words else []
        )
        full_rows = _layout_body(
            scratch, _copy_blocks(body_blocks), body_fonts, body_max_w,
            BODY_MAX_LINES, bullet_indent=m["bullet_indent"],
        )
        needed = fixed_overhead(len(heading_lines), line_h) + len(full_rows) * line_h
        if needed <= max_h or scale <= CARD_MIN_FONT_SCALE:
            break
        scale = round(scale - 0.1, 2)

    # Cap the body to what the grown card holds at the chosen font, then size
    # the card to its actual content (resting height floor, max-growth ceiling).
    # The overhead is fixed once the font scale is settled.
    overhead = fixed_overhead(len(heading_lines), line_h)
    max_body_lines = max(0, min(BODY_MAX_LINES, (max_h - overhead) // line_h))
    body_rows = _layout_body(
        scratch, _copy_blocks(body_blocks), body_fonts, body_max_w,
        max_body_lines, bullet_indent=m["bullet_indent"],
    )
    card_h = max(rest_h, min(max_h, overhead + len(body_rows) * line_h))

    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # Build the filled interior: bg field + accent stripe baked on the
    # inner (left) edge of the card so the right edge stays clean and
    # the badge above the card has uninterrupted backdrop.
    fill = Image.new("RGBA", (card_w, card_h), CARD_BG)
    ImageDraw.Draw(fill).rectangle((0, 0, m["stripe_w"], card_h), fill=ACCENT)

    ss = MASK_SS
    hi_mask = Image.new("L", (card_w * ss, card_h * ss), 0)
    ImageDraw.Draw(hi_mask).rounded_rectangle(
        (0, 0, card_w * ss - 1, card_h * ss - 1),
        radius=m["radius"] * ss,
        fill=255,
    )
    mask = hi_mask.resize((card_w, card_h), Image.LANCZOS)

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    card.paste(fill, (0, 0), mask)

    cd = ImageDraw.Draw(card)
    cursor_y = m["pad_top"]

    _draw_tracked(
        cd, label_text, (text_left, cursor_y), label_font, LABEL_HUE,
        tracking=m["label_tracking"],
    )
    cursor_y += label_h + gap_above

    if heading_lines:
        for line in heading_lines:
            _draw_runs_line(cd, line, (text_left, cursor_y), heading_fonts, HEADING_HUE)
            cursor_y += line_h
        cursor_y += gap_below

    if body_rows:
        bullet_font = body_fonts[(False, False)]
        for line, x_off, render_bullet in body_rows:
            if render_bullet:
                cd.text((text_left, cursor_y), BULLET_CHAR, font=bullet_font, fill=BODY_HUE)
            _draw_runs_line(cd, line, (text_left + x_off, cursor_y), body_fonts, BODY_HUE)
            cursor_y += line_h

    base.alpha_composite(card, (card_x, card_y))
    base.save(out)

"""Tests for bin/_compose.py — parser, block splitting, layout, and a
smoke render via compose_note.

Parser and layout tests are pure-Python and stdlib-only. The smoke
render tests skip when Pillow isn't installed (Pillow is only required
for the actual marginalia composition; the rest of beacon is stdlib).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "bin"))

from _compose import (  # noqa: E402
    BODY_MAX_LINES,
    BODY_PT,
    BULLET_INDENT,
    _build_fonts,
    _compute_strike_runs,
    _layout_body,
    _parse_markdown,
    _parse_to_words,
    _split_blocks,
    _truncate_oversized_word,
    compose_note,
    has_pillow,
)


def _word_text(word):
    return "".join(seg[0] for seg in word)


def _line_text(line):
    return " ".join(_word_text(w) for w in line)


class ParserInlineEmphasis(unittest.TestCase):
    def test_bold_italic_strike(self):
        words = _parse_to_words("plain *bold* _italic_ ~strike~ end")
        flat = [seg for w in words for seg in w]
        self.assertEqual(
            flat,
            [
                ("plain", False, False, False),
                ("bold", True, False, False),
                ("italic", False, True, False),
                ("strike", False, False, True),
                ("end", False, False, False),
            ],
        )

    def test_markers_compose(self):
        [word] = _parse_to_words("*_x_*")
        self.assertEqual(word, [("x", True, True, False)])

    def test_strike_composes_with_bold(self):
        [word] = _parse_to_words("*~x~*")
        self.assertEqual(word, [("x", True, False, True)])

    def test_quantity_within_run_is_irrelevant(self):
        self.assertEqual(_parse_to_words("*x*"), _parse_to_words("**x**"))
        self.assertEqual(_parse_to_words("~x~"), _parse_to_words("~~x~~"))

    def test_emphasis_persists_across_whitespace(self):
        # Spaces flush words but do not reset toggles — `*two words*`
        # is two bold words.
        words = _parse_to_words("*two words*")
        flat = [seg for w in words for seg in w]
        self.assertEqual(
            flat,
            [
                ("two", True, False, False),
                ("words", True, False, False),
            ],
        )

    def test_glued_boundary_stays_one_word(self):
        # `**users**,` — bold "users" and trailing "," ship in the same
        # Word so wrap can't break the styling boundary.
        [word] = _parse_to_words("**users**,")
        self.assertEqual(
            word,
            [
                ("users", True, False, False),
                (",", False, False, False),
            ],
        )


class BlockSplitting(unittest.TestCase):
    def test_single_line_paragraph(self):
        blocks = _split_blocks(["hello world"])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][0], "para")

    def test_single_line_list_item(self):
        blocks = _split_blocks(["* hello"])
        self.assertEqual(
            blocks, [("li", [[("hello", False, False, False)]])],
        )

    def test_consecutive_non_list_lines_coalesce(self):
        blocks = _split_blocks(["foo", "bar", "baz"])
        self.assertEqual(len(blocks), 1)
        kind, words = blocks[0]
        self.assertEqual(kind, "para")
        self.assertEqual([_word_text(w) for w in words], ["foo", "bar", "baz"])

    def test_list_items_each_separate(self):
        blocks = _split_blocks(["* one", "* two", "* three"])
        self.assertEqual([b[0] for b in blocks], ["li", "li", "li"])

    def test_blank_lines_skipped(self):
        blocks = _split_blocks(["foo", "", "* item", "", "bar"])
        self.assertEqual([b[0] for b in blocks], ["para", "li", "para"])

    def test_leading_whitespace_on_list_line(self):
        blocks = _split_blocks(["  * indented"])
        self.assertEqual(blocks[0][0], "li")

    def test_list_marker_consumed_inline_emphasis_preserved(self):
        # The leading `* ` is consumed as the list marker; inner `*`
        # runs inside the item still toggle bold.
        blocks = _split_blocks(["* visit *example*"])
        kind, words = blocks[0]
        self.assertEqual(kind, "li")
        flat = [seg for w in words for seg in w]
        self.assertEqual(
            flat,
            [
                ("visit", False, False, False),
                ("example", True, False, False),
            ],
        )


class ParseMarkdownHeading(unittest.TestCase):
    def test_single_line_no_heading(self):
        h, blocks = _parse_markdown("hello world")
        self.assertIsNone(h)
        self.assertEqual([b[0] for b in blocks], ["para"])

    def test_single_line_list(self):
        h, blocks = _parse_markdown("* foo")
        self.assertIsNone(h)
        self.assertEqual([b[0] for b in blocks], ["li"])

    def test_multi_line_first_line_is_heading(self):
        h, blocks = _parse_markdown("the heading\nbody line one\nbody line two")
        self.assertIsNotNone(h)
        self.assertEqual(_line_text(h), "the heading")
        self.assertEqual([b[0] for b in blocks], ["para"])

    def test_heading_then_list(self):
        h, blocks = _parse_markdown("heading\n* one\n* two")
        self.assertIsNotNone(h)
        self.assertEqual([b[0] for b in blocks], ["li", "li"])

    def test_heading_then_para_then_list_then_para(self):
        text = "heading\nintro para\n* item one\n* item two\nconclusion"
        h, blocks = _parse_markdown(text)
        self.assertIsNotNone(h)
        self.assertEqual([b[0] for b in blocks], ["para", "li", "li", "para"])

    def test_heading_consumes_first_line_even_if_star_prefixed(self):
        # The first line is the heading regardless of its prefix; only
        # body lines are eligible to become list items.
        h, blocks = _parse_markdown("* my title\nbody")
        self.assertIsNotNone(h)
        self.assertEqual([b[0] for b in blocks], ["para"])

    def test_empty_input(self):
        self.assertEqual(_parse_markdown(""), (None, []))
        self.assertEqual(_parse_markdown("   \n  "), (None, []))


@unittest.skipUnless(has_pillow(), "Pillow not installed")
class LayoutRows(unittest.TestCase):
    # Approximates body_max_w in the default card at W=1440. The exact
    # pixel value matters less than that it's stable across tests so
    # wrap math is deterministic.
    BODY_MAX_W = 440

    def setUp(self):
        from PIL import Image, ImageDraw

        self.img = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)
        self.fonts = _build_fonts(BODY_PT)

    def _layout(self, blocks, max_lines=BODY_MAX_LINES):
        return _layout_body(
            self.draw, blocks, self.fonts, self.BODY_MAX_W, max_lines,
        )

    def test_paragraph_rows_flush_left(self):
        _h, blocks = _parse_markdown("a b c d")
        rows = self._layout(blocks)
        for _line, x_off, bullet in rows:
            self.assertEqual(x_off, 0)
            self.assertFalse(bullet)

    def test_list_first_row_has_bullet_and_indent(self):
        # Multi-line input — first line is the heading per OVERLAY-01,
        # so we lead with one to put both list items in the body.
        _h, blocks = _parse_markdown("items\n* item one\n* item two")
        rows = self._layout(blocks)
        self.assertEqual(len(rows), 2)
        for _line, x_off, bullet in rows:
            self.assertEqual(x_off, BULLET_INDENT)
            self.assertTrue(bullet)

    def test_list_continuation_drops_bullet_keeps_indent(self):
        # Long list item forced to wrap: first row carries the bullet,
        # continuation rows do not, but the indent persists.
        long_item = "* " + ("word " * 20).strip()
        _h, blocks = _parse_markdown(long_item)
        rows = self._layout(blocks)
        self.assertGreater(len(rows), 1)
        self.assertTrue(rows[0][2])
        for _line, x_off, bullet in rows[1:]:
            self.assertEqual(x_off, BULLET_INDENT)
            self.assertFalse(bullet)

    def test_truncation_caps_total_rows_with_ellipsis(self):
        # Enough words to overflow the line cap at BODY_PT given the
        # BODY_MAX_W budget — 300 single-char words exceeds nine lines
        # and forces the ellipsis path on the last wrapped row.
        _h, blocks = _parse_markdown(" ".join(["w"] * 300))
        rows = self._layout(blocks)
        self.assertEqual(len(rows), BODY_MAX_LINES)
        last_line, _, _ = rows[-1]
        last_seg_text = last_line[-1][-1][0]
        self.assertTrue(
            last_seg_text.endswith("…"),
            f"expected ellipsis on truncated tail, got {last_seg_text!r}",
        )

    def test_layout_respects_block_order(self):
        _h, blocks = _parse_markdown("heading\npara one\n* item\npara two")
        rows = self._layout(blocks)
        # First row is the leading paragraph; middle row is the list
        # item (carries bullet); last row is the trailing paragraph.
        self.assertFalse(rows[0][2])
        self.assertTrue(rows[1][2])
        self.assertFalse(rows[-1][2])

    def test_truncation_respects_block_budget_across_blocks(self):
        text = "\n".join(f"* item{i}" for i in range(30))
        _h, blocks = _parse_markdown(text)
        rows = self._layout(blocks)
        self.assertLessEqual(len(rows), BODY_MAX_LINES)

    def test_oversized_single_word_truncates_in_place(self):
        # A word wider than BODY_MAX_W ends the wrap and lands as a
        # truncated line with an inline ellipsis (no outer ellipsis
        # appended on top).
        long_word = "release/ecommerce-infrastructure-patterns-2026"
        _h, blocks = _parse_markdown(long_word)
        rows = self._layout(blocks)
        self.assertEqual(len(rows), 1)
        line, _, _ = rows[0]
        rendered = "".join(seg[0] for word in line for seg in word)
        self.assertTrue(rendered.endswith("…"))
        self.assertNotEqual(rendered, long_word)
        # Sanity: the truncated form shouldn't be the full word with a
        # double ellipsis tacked on.
        self.assertFalse(rendered.endswith("……"))


@unittest.skipUnless(has_pillow(), "Pillow not installed")
class StrikeRuns(unittest.TestCase):
    def setUp(self):
        from PIL import Image, ImageDraw

        self.img = Image.new("RGBA", (800, 200), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)
        self.fonts = _build_fonts(BODY_PT)

    def test_no_strike_yields_no_runs(self):
        words = _parse_to_words("hello world")
        self.assertEqual(_compute_strike_runs(self.draw, words, 0, self.fonts), [])

    def test_single_word_strike_one_run(self):
        words = _parse_to_words("~hello~")
        runs = _compute_strike_runs(self.draw, words, 0, self.fonts)
        self.assertEqual(len(runs), 1)
        start, end, _font = runs[0]
        self.assertLess(start, end)

    def test_strike_across_words_is_one_continuous_run(self):
        # `~hello world~` — both words carry strike=True, so the run
        # merger draws one line spanning both words and the space
        # between them. This is the fix for the per-word-gap rendering
        # the previous implementation produced.
        words = _parse_to_words("~hello world~")
        runs = _compute_strike_runs(self.draw, words, 0, self.fonts)
        self.assertEqual(len(runs), 1)

    def test_unstruck_word_between_struck_words_splits_runs(self):
        words = _parse_to_words("~hello~ world ~again~")
        runs = _compute_strike_runs(self.draw, words, 0, self.fonts)
        # Two separate runs — the un-struck "world" closes the first
        # and the new strike re-opens for "again".
        self.assertEqual(len(runs), 2)

    def test_run_starts_at_x0(self):
        # The first struck segment's start_x equals the passed-in x0;
        # we don't accidentally pre-advance past the run start.
        words = _parse_to_words("~hello~")
        runs = _compute_strike_runs(self.draw, words, 100, self.fonts)
        start, _end, _font = runs[0]
        self.assertEqual(start, 100)


@unittest.skipUnless(has_pillow(), "Pillow not installed")
class OversizedWordTruncation(unittest.TestCase):
    def setUp(self):
        from PIL import Image, ImageDraw

        self.img = Image.new("RGBA", (800, 200), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)
        self.fonts = _build_fonts(BODY_PT)

    def test_oversized_word_returns_ellipsis_suffixed(self):
        [word] = _parse_to_words("ecommerce-infrastructure-patterns-2026")
        result = _truncate_oversized_word(self.draw, word, 200, self.fonts)
        text = "".join(seg[0] for seg in result)
        self.assertTrue(text.endswith("…"))
        self.assertLess(len(text), len("ecommerce-infrastructure-patterns-2026"))

    def test_oversized_word_preserves_style(self):
        # The truncated tail should inherit the original tail segment's
        # bold/italic/strike flags so styling doesn't reset mid-word.
        words = _parse_to_words("*reallyreallyreallylongboldwordthatwillnotfit*")
        [word] = words
        result = _truncate_oversized_word(self.draw, word, 150, self.fonts)
        # All segments should still be bold (the original word was
        # entirely bold; truncation only chops text, not style).
        for _text, bold, _italic, _strike in result:
            self.assertTrue(bold)


@unittest.skipUnless(has_pillow(), "Pillow not installed")
class ComposeSmoke(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "note.png"

    def tearDown(self):
        self._tmp.cleanup()

    def _compose(self, label, text, **kwargs):
        compose_note(label, text, self.out, **kwargs)
        self.assertTrue(self.out.exists())
        self.assertGreater(self.out.stat().st_size, 0)

    def test_simple_inline(self):
        self._compose("PAUSED", "thinking about this *carefully*")

    def test_multi_line_with_heading(self):
        self._compose("WORKING", "Refreshing\nbackground data refresh in progress")

    def test_list_items(self):
        self._compose(
            "WORKING",
            "decision needed\n* option one\n* option ~old plan~\n* option three",
        )

    def test_strikethrough(self):
        self._compose("PAUSED", "old plan: ~scrap it~ — going with the new one")

    def test_long_text_truncates_without_raising(self):
        body = "\n".join(["heading"] + [f"word{i}" for i in range(200)])
        self._compose("WORKING", body)

    def test_image_dimensions_match_request(self):
        from PIL import Image

        compose_note("PAUSED", "small note", self.out, w=800, h=600)
        with Image.open(self.out) as img:
            self.assertEqual(img.size, (800, 600))


if __name__ == "__main__":
    unittest.main()

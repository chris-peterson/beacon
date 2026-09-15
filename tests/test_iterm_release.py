"""Tests for dev/iterm-release.py — the iTerm2 release watch.

The scan's whole value is that a hit means something. Both halves of the
preference match were wrong when first written: a bare-word match reported
every `Name` and `Guid` in the codebase, and the string-literal match that
replaced it silently missed every advanced setting, which is where the
defaults beacon's layout is tuned against actually live.
"""
import importlib.machinery
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    path = REPO / "dev" / "iterm-release.py"
    loader = importlib.machinery.SourceFileLoader("iterm_release", str(path))
    spec = importlib.util.spec_from_loader("iterm_release", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


iterm_release = _load()


class PreferenceKeyMatching(unittest.TestCase):
    """A preference reaches iTerm2 as a literal or as a DEFINE_ macro."""

    def match(self, key, line):
        return bool(iterm_release._pattern(key, "prefkey").search(line))

    def test_matches_the_string_literal_form(self):
        self.assertTrue(self.match(
            "LeftTabBarWidth",
            'NSString *const kPreferenceKeyLeftTabBarWidth = @"LeftTabBarWidth";'))

    def test_matches_an_advanced_setting_declaration(self):
        # iTerm2 derives the defaults key by capitalizing the identifier, so
        # CompactMinimalTabBarHeight appears in the source only like this.
        self.assertTrue(self.match(
            "CompactMinimalTabBarHeight",
            'DEFINE_FLOAT(compactMinimalTabBarHeight, 38, SECTION_TABS @"Height.");'))
        self.assertTrue(self.match(
            "DisableTabBarTooltips",
            'DEFINE_BOOL(disableTabBarTooltips, NO, SECTION_TABS @"Disable?");'))

    def test_ignores_a_local_variable_of_the_same_name(self):
        self.assertFalse(self.match(
            "StatusBarHeight",
            "    const CGFloat statusBarHeight = "
            "sessionView.showBottomStatusBar ? iTermGetStatusBarHeight() : 0;"))


class ProfileKeyMatching(unittest.TestCase):
    """A profile key is only ever a literal, so nothing else may match it."""

    def match(self, key, line):
        return bool(iterm_release._pattern(key, "quoted").search(line))

    def test_matches_the_literal(self):
        self.assertTrue(self.match("Name", '#define KEY_NAME @"Name"'))
        self.assertTrue(self.match("Badge Text", '    profile[@"Badge Text"] = text;'))

    def test_ignores_an_identifier_of_the_same_name(self):
        self.assertFalse(self.match("Name", "    let Name = session.name"))
        self.assertFalse(self.match("Guid", "    NSString *Guid = profile.guid;"))


class NoiseFiltering(unittest.TestCase):
    """Generated and vendored files carry every symbol at once."""

    def test_skips_generated_and_vendored_paths(self):
        for path in ("api/library/python/iterm2/iterm2/api_pb2.py",
                     "ThirdParty/CoreParse.framework.dSYM/Contents/Info.plist",
                     "docs/notes-3.7.txt",
                     "BetterFontPicker/X.swiftmodule/arm64-apple-macos.swiftinterface"):
            self.assertTrue(iterm_release.NOISE.search(path), path)

    def test_keeps_source_and_tests(self):
        for path in ("sources/Settings/Profiles/iTermDynamicProfileManager.m",
                     "ModernTests/DynamicProfileRewriteCrashTests.m",
                     "iTerm2.sdef"):
            self.assertFalse(iterm_release.NOISE.search(path), path)


class ReleaseTagParsing(unittest.TestCase):
    """Betas and nightlies share the `v` prefix and are not releases."""

    def test_accepts_only_a_three_part_release(self):
        for tag in ("v3.7.2", "v3.10.0"):
            self.assertTrue(iterm_release.RELEASE_TAG.match(tag), tag)
        for tag in ("v3.7.1beta1", "v20260915-nightly", "v3.7"):
            self.assertFalse(iterm_release.RELEASE_TAG.match(tag), tag)


class WatchedSymbols(unittest.TestCase):
    """The watch set is derived from beacon's sources, not restated."""

    def test_layout_keys_come_from_the_cli_tables(self):
        keys = iterm_release._layout_keys()
        self.assertIn("CompactMinimalTabBarHeight", keys)
        self.assertIn("StatusBarHeight", keys)

    def test_profile_keys_come_from_the_template(self):
        keys = iterm_release._profile_keys()
        self.assertIn("Badge Text", keys)
        self.assertIn("Title Components", keys)
        self.assertIn("Background Image Location", keys)


if __name__ == "__main__":
    unittest.main()

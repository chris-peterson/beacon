"""Behavior tests for scripts/beacon.

The plugin script has no .py extension, so we load it via importlib. Each test
gets a fresh DATA_DIR (tempdir) and a mocked `_cli` so we can assert which OSC
calls would have fired.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
BEACON_PATH = REPO_ROOT / "scripts" / "beacon"


def _load_beacon(data_dir: Path):
    os.environ["CLAUDE_PLUGIN_DATA"] = str(data_dir)
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
    os.environ["ITERM_SESSION_ID"] = "test-session"
    sys.modules.pop("beacon", None)
    # The script has no .py extension, so spec_from_file_location can't infer
    # a loader. Construct a SourceFileLoader explicitly.
    loader = importlib.machinery.SourceFileLoader("beacon", str(BEACON_PATH))
    spec = importlib.util.spec_from_loader("beacon", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _uservar_emits(calls, slot):
    return [c for c in calls if c[:2] == ("uservar", slot)]


# The install-time placeholder values a test renders the profile template with.
# Kept in one place so a new placeholder is added once rather than in each test
# that parses the profile — an unsubstituted `__BEACON_*__` still parses as JSON,
# so a missed one shows up as a puzzling string mismatch instead of an error.
PROFILE_SUBSTITUTIONS = {
    "__BEACON_SCRIPT__": "/x/scripts/beacon",
    "__BEACON_PYTHON__": "/x/python3",
    "__BEACON_CACHE_DIR__": "/x/cache",
    "__BEACON_WEB_LABEL__": "↖ web",
    "__BEACON_CODE_LABEL__": "↗ code",
}


def _render_profile_template(**overrides) -> dict:
    """The base profile as iTerm2 would load it — the template with every
    placeholder filled. Overrides replace a placeholder's value by its bare name
    (`web_label="↖ repo"`)."""
    raw = (REPO_ROOT / "iterm" / "profile.json.template").read_text(encoding="utf-8")
    values = dict(PROFILE_SUBSTITUTIONS)
    for name, value in overrides.items():
        values[f"__BEACON_{name.upper()}__"] = value
    for placeholder, value in values.items():
        raw = raw.replace(placeholder, value)
    return json.loads(raw)["Profiles"][0]


class BeaconTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.beacon = _load_beacon(self.data_dir)

        self.cli_calls: list[tuple] = []
        patcher = mock.patch.object(
            self.beacon, "_cli",
            side_effect=lambda *args, **kwargs: self.cli_calls.append(args),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # The pane badge is opt-in and off by default (BADGE-15); these tests
        # exercise the render's badge-painting capability, so enable it here.
        # The default-off path has its own test (BadgeToggle).
        badge_patcher = mock.patch.object(self.beacon, "_badge_enabled", return_value=True)
        badge_patcher.start()
        self.addCleanup(badge_patcher.stop)

        # Pin resolved project to a known value so tests don't depend on git
        # state of the working tree they happen to run in.
        proj_patcher = mock.patch.object(
            self.beacon, "_project_name_at", return_value="acme/widget",
        )
        proj_patcher.start()
        self.addCleanup(proj_patcher.stop)

        pkg_patcher = mock.patch.object(
            self.beacon, "p_package_name", return_value="",
        )
        pkg_patcher.start()
        self.addCleanup(pkg_patcher.stop)

        remote_patcher = mock.patch.object(
            self.beacon, "p_git_remote", return_value="acme/widget",
        )
        remote_patcher.start()
        self.addCleanup(remote_patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()


class ApplyRepublishesBadgeText(BeaconTest):
    """BADGE-12: apply() must republish beacon_project when the resolved
    project value changes."""

    def test_change_emits_uservar(self):
        self.beacon.apply({
            **_base_state(), "project": "acme/widget",
        })
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "project": "custom-label",
        })

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "custom-label")],
        )

    def test_first_render_emits_beacon_project(self):
        # BADGE-02 (revised): the plugin is the sole writer of beacon_project.
        # First render MUST publish so CLI engagement (`beacon set project foo`
        # in an interactive shell with no prior render) lands on the badge.
        # The shell snippet no longer republishes from cwd, so without this
        # the badge stays empty until a project change occurs.
        self.beacon.apply({**_base_state(), "project": "acme/widget"})

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "First render must publish beacon_project — plugin is sole writer",
        )

    def test_task_only_change_emits_beacon_task_not_beacon_project(self):
        self.beacon.apply({**_base_state(), "project": "acme/widget"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "project": "acme/widget", "task": "different",
        })

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"), [],
            "Task change must not republish beacon_project",
        )
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", " · different")],
            "Task change must publish beacon_task with leading ' · ' separator",
        )

    def test_first_render_emits_empty_beacon_task_when_task_absent(self):
        self.beacon.apply({**_base_state(), "project": "acme/widget"})

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", "")],
            "First render with no task must emit empty beacon_task so the slot "
            "collapses cleanly in the badge format",
        )

    def test_first_render_emits_beacon_task_when_task_present(self):
        self.beacon.apply({
            **_base_state(), "project": "acme/widget", "task": "my work",
        })

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", " · my work")],
        )

    def test_unchanged_task_does_not_republish_beacon_task(self):
        self.beacon.apply({
            **_base_state(), "project": "acme/widget", "task": "stable",
        })
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "project": "acme/widget", "task": "stable",
        })

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"), [],
            "Identical resolved task must not re-emit",
        )


class CmdSetPropagatesToBadge(BeaconTest):
    """Integration: `beacon set project X` must paint the badge, not just
    write override state."""

    def test_set_project_lands_on_badge(self):
        # Prime: simulate SessionStart's first render so `prev` is non-empty
        # (mirrors the real flow — _publish_anchor → render → apply)
        self.beacon.render()
        self.cli_calls.clear()

        args = mock.Mock(field="project", value=["ai-sdlc: perms"])
        self.beacon.cmd_set(args)

        emits = _uservar_emits(self.cli_calls, "beacon_project")
        self.assertEqual(emits, [("uservar", "beacon_project", "ai-sdlc: perms")])

    def test_clear_project_reverts_badge_to_derived(self):
        self.beacon.render()
        self.beacon.cmd_set(mock.Mock(field="project", value=["override"]))
        self.cli_calls.clear()

        self.beacon.cmd_clear(mock.Mock(field="project"))

        emits = _uservar_emits(self.cli_calls, "beacon_project")
        self.assertEqual(emits, [("uservar", "beacon_project", "acme/widget")])

    def test_set_task_emits_beacon_task_not_beacon_project(self):
        self.beacon.render()
        self.cli_calls.clear()

        args = mock.Mock(field="task", value=["my-task"])
        self.beacon.cmd_set(args)

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"), [],
            "set task must not republish beacon_project — only the task slot moved",
        )
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", " · my-task")],
            "set task must publish beacon_task so the badge shows the new value",
        )


class ApplyEmitsBaseProfileAndColor(BeaconTest):
    """RENDER-04 / §6.6: the first render switches into the base `beacon`
    profile and sets the badge format; for ready/busy/blocked, state color is
    delivered by OSC badge-color/tab-color with no per-state profile (paused is
    the one exception — see PausedSwapsProfile, RENDER-05). Subsequent
    non-paused renders repaint color only when the logical state changes."""

    def test_first_render_switches_base_profile_and_sets_ready_color(self):
        self.beacon.apply({**_base_state(), "status": "idle"})

        self.assertIn(("set-profile", "beacon-dev"), self.cli_calls,
                      "First render must switch into the base beacon-dev profile")
        ready = self.beacon.BADGE_COLOR_PALETTE["ready"]
        self.assertIn(("badge-color", ready), self.cli_calls)
        self.assertIn(("tab-color", ready), self.cli_calls)

    def test_status_transition_emits_color_not_profile(self):
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "working"})

        busy = self.beacon.BADGE_COLOR_PALETTE["busy"]
        self.assertIn(("badge-color", busy), self.cli_calls)
        self.assertIn(("tab-color", busy), self.cli_calls)
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile"], [],
            "A state transition repaints via OSC color, never a profile switch",
        )

    def test_unchanged_state_emits_no_color(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "working"})

        self.assertEqual(
            [c for c in self.cli_calls
             if c[0] in ("badge-color", "tab-color", "set-profile")],
            [],
            "Identical logical state must not repaint color or switch profiles",
        )


class WindowTitleSetName(BeaconTest):
    """TITLE-01..04: on a profile swap (including the first render, and every
    mode entry/exit that resets the name) beacon sets the session name to the
    interpolated badge template via set-name — but only for real iTerm sessions
    (an addressable GUID), single-sourced with the badge (BADGE_FORMAT). A
    non-swap state change leaves the name in place; a non-iTerm session gets
    none, and that is not an error. cmd_hook additionally re-asserts the name on
    the once-per-turn boundaries so the shell's backgrounded source-time
    set-name can't leave an engaged pane on the shell's project_full template."""

    def _set_iterm_id(self, value):
        p = mock.patch.dict(os.environ, {"ITERM_SESSION_ID": value})
        p.start()
        self.addCleanup(p.stop)

    def test_first_render_sets_name_to_badge_template(self):
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.assertIn(
            ("set-name", "w0t0p0:ABC-123", self.beacon.TITLE_FORMAT),
            self.cli_calls,
            "first render (a swap) must set the session name to the badge template",
        )

    def test_mode_swap_resets_name(self):
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()
        self.beacon.apply({**_base_state(), "status": "paused"})
        self.assertIn(
            ("set-name", "w0t0p0:ABC-123", self.beacon.TITLE_FORMAT),
            self.cli_calls,
            "a mode swap resets the session name, so it must be re-set (TITLE-04)",
        )

    def test_non_swap_render_leaves_name_alone(self):
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()
        self.beacon.apply({**_base_state(), "status": "working"})  # ready→busy, no swap
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-name"], [],
            "a non-swap state change must not re-set the name — it persists",
        )

    def test_non_iterm_session_gets_no_title(self):
        self._set_iterm_id("claude-session:xyz")
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-name"], [],
            "a synthesized claude-session id has no addressable surface — no set-name",
        )

    def test_prompt_reasserts_name(self):
        self._set_iterm_id("w0t0p0:ABC-123")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "hi"}))):
            self.beacon.cmd_hook(args)
        self.assertIn(
            ("set-name", "w0t0p0:ABC-123", self.beacon.TITLE_FORMAT),
            self.cli_calls,
            "UserPromptSubmit must re-assert the title to beat the shell's launch write",
        )

    def test_stop_reasserts_name(self):
        self._set_iterm_id("w0t0p0:ABC-123")
        args = mock.Mock(event="Stop")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"stop_hook_active": False}))):
            self.beacon.cmd_hook(args)
        self.assertIn(
            ("set-name", "w0t0p0:ABC-123", self.beacon.TITLE_FORMAT),
            self.cli_calls,
            "Stop must re-assert the title to beat the shell's launch write",
        )

    def test_reassert_is_one_shot(self):
        # The re-assert exists to beat the shell's launch-time write; after the
        # first turn boundary nothing re-clobbers, so a persisted flag keeps it
        # off every subsequent turn (no per-turn Apple Event).
        self._set_iterm_id("w0t0p0:ABC-123")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "hi"}))):
            self.beacon.cmd_hook(args)
        self.cli_calls.clear()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "again"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-name"], [],
            "a second turn boundary must not re-set the name — the re-assert is one-shot",
        )

    def test_fresh_start_rearms_reassert(self):
        # A fresh-start wipe clears the flag so the next engagement reclaims the
        # title after its own launch race.
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.write_state("title_reasserted", "1")
        self.beacon._wipe_session_for_fresh_start()
        self.assertIsNone(self.beacon.read_state("title_reasserted"))

    def test_tool_hook_does_not_reassert_name(self):
        # PreToolUse/PostToolUse fire many times per turn; re-asserting there
        # would spawn an osascript each time (the NFR-perf reason TITLE-04 cites).
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.apply({**_base_state(), "status": "working"})  # prime a snapshot
        self.cli_calls.clear()
        args = mock.Mock(event="PostToolUse")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-name"], [],
            "a high-frequency tool hook must not re-assert the name",
        )


class PausedSwapsProfile(BeaconTest):
    """RENDER-05 / BADGE-11: paused is a mode state with its own profile. The
    pause⇄resume transition swaps profiles (beacon-dev ↔ beacon-pause) and,
    because SetProfile wipes session OSC (§6.10), re-emits the badge format, user
    vars, and badge/tab color. No mode decorates the badge text (BADGE-11)."""

    def test_pause_swaps_to_paused_profile_and_reemits(self):
        self.beacon.apply({**_base_state(), "status": "idle", "task": "wiring"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "paused", "task": "wiring"})

        self.assertIn(("set-profile", "beacon-pause"), self.cli_calls,
                      "entering paused must swap into the beacon-pause profile")
        self.assertIn(("badge-format", self.beacon.BADGE_FORMAT), self.cli_calls,
                      "a swap must re-emit the badge format (SetProfile wipes it)")
        paused_hex = self.beacon.BADGE_COLOR_PALETTE["paused"]
        self.assertIn(("badge-color", paused_hex), self.cli_calls)
        self.assertIn(("tab-color", paused_hex), self.cli_calls)
        # The user vars are re-emitted because the swap wiped them; the badge text
        # is the raw project (no glyph, BADGE-11), the (unchanged) task restored.
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
        )
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", " · wiring")],
        )

    def test_resume_swaps_back_to_base(self):
        self.beacon.apply({**_base_state(), "status": "paused"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "idle"})

        self.assertIn(("set-profile", "beacon-dev"), self.cli_calls,
                      "leaving paused must swap back to the base beacon-dev profile")
        ready = self.beacon.BADGE_COLOR_PALETTE["ready"]
        self.assertIn(("badge-color", ready), self.cli_calls)

    def test_non_mode_transitions_never_swap(self):
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "working"})
        self.beacon.apply({**_base_state(), "status": "waiting"})

        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile"], [],
            "ready/busy/blocked (dev) stay OSC overlays on the base profile — no swap",
        )

    def test_snapshot_records_active_profile(self):
        self.beacon.apply({**_base_state(), "status": "paused"})
        snap = self.beacon.read_state_json("resolved", {})
        self.assertEqual(snap.get("profile"), "beacon-pause")
        self.assertEqual(snap.get("project"), "acme/widget",
                         "snapshot keeps the raw project")

        self.beacon.apply({**_base_state(), "status": "idle"})
        snap = self.beacon.read_state_json("resolved", {})
        self.assertEqual(snap.get("profile"), "beacon-dev")


class RetroMode(BeaconTest):
    """RENDER-05 / STATE-08: retro is a mode state with its own profile
    (beacon-retro, muted green + white badge), set via `retro`. Unlike paused it
    freezes no identity and persists across a prompt; no mode carries a glyph."""

    def test_retro_swaps_to_retro_profile_and_color(self):
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "retro"})

        self.assertIn(("set-profile", "beacon-retro"), self.cli_calls,
                      "entering retro must swap into the beacon-retro profile")
        retro_hex = self.beacon.BADGE_COLOR_PALETTE["retro"]
        self.assertIn(("badge-color", retro_hex), self.cli_calls)
        self.assertIn(("tab-color", retro_hex), self.cli_calls)

    def test_retro_badge_has_no_glyph(self):
        self.beacon.apply({**_base_state(), "status": "retro"})
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "retro carries its cue in the profile/color, not a badge glyph",
        )

    def test_retro_command_sets_status_without_freezing_identity(self):
        # Unlike pause (STATE-03), retro does not snapshot project/task overrides.
        self.beacon.write_state("resolved", json.dumps({
            "project": "shown-proj", "project_provider": "git-remote",
            "task": "shown-task", "task_provider": "pr",
        }))
        self.beacon.cmd_retro(mock.Mock(note=["lessons", "learned"]))
        self.assertEqual(self.beacon.read_state("override.status"), "retro")
        self.assertEqual(self.beacon.read_state("description"), "lessons learned")
        self.assertIsNone(self.beacon.read_state("override.project"),
                          "retro must not freeze the badge identity (paused-only)")
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_retro_persists_across_prompt(self):
        # STATE-04 auto-resume is paused-only; a returning prompt must not clear retro.
        self.beacon.write_state("override.status", "retro")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "next step"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_state("override.status"), "retro",
                         "retro is a deliberate mode — it persists until cleared")


class DoneMode(BeaconTest):
    """RENDER-05: done is the terminal "session complete, ready to hand off" mode
    with its own profile (beacon-done, near-black "powered off"), set via `done`.
    Like retro it freezes no identity, persists across a prompt, and carries no
    badge glyph — its cue is the powered-off background and dim-gray color. It
    additionally suppresses the task slot (STATE-12)."""

    def test_done_swaps_to_done_profile_and_color(self):
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "done"})

        self.assertIn(("set-profile", "beacon-done"), self.cli_calls,
                      "entering done must swap into the beacon-done profile")
        done_hex = self.beacon.BADGE_COLOR_PALETTE["done"]
        self.assertIn(("badge-color", done_hex), self.cli_calls)
        self.assertIn(("tab-color", done_hex), self.cli_calls)

    def test_done_badge_has_no_glyph(self):
        self.beacon.apply({**_base_state(), "status": "done"})
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "done carries its cue in the profile/background, not a badge glyph",
        )

    def test_done_suppresses_task_keeps_project(self):
        # STATE-12: a done session shows its project alone — the task slot is
        # blanked at resolve time (even with a task override set), project kept.
        self.beacon.write_state("override.status", "done")
        self.beacon.write_state("override.project", "acme/widget")
        self.beacon.write_state("override.task", "shipping v2")
        r = self.beacon.resolve()
        self.assertEqual(r["task"], "", "done suppresses the task (STATE-12)")
        self.assertEqual(r["task_provider"], "done")
        self.assertEqual(r["project"], "acme/widget", "done keeps the project")

    def test_done_command_sets_status_without_freezing_identity(self):
        # Like retro (and unlike pause/STATE-03), done does not snapshot overrides.
        self.beacon.write_state("resolved", json.dumps({
            "project": "shown-proj", "project_provider": "git-remote",
            "task": "shown-task", "task_provider": "pr",
        }))
        self.beacon.cmd_done(mock.Mock(note=["handing", "off"]))
        self.assertEqual(self.beacon.read_state("override.status"), "done")
        self.assertEqual(self.beacon.read_state("description"), "handing off")
        self.assertIsNone(self.beacon.read_state("override.project"),
                          "done must not freeze the badge identity (paused-only)")
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_done_persists_across_prompt(self):
        # STATE-04 auto-resume is paused-only; a returning prompt must not clear
        # done (a handed-off session stays complete until explicitly resumed).
        self.beacon.write_state("override.status", "done")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "one more thing"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_state("override.status"), "done",
                         "done is a deliberate terminal mode — it persists until cleared")


class ReleaseMode(BeaconTest):
    """RENDER-05 / STATE-10: release is the active "ship-it flow in progress" mode
    with its own profile (beacon-release, launch-sky navy + rocket watermark), set via
    `release`. Like retro it freezes no identity, persists across a prompt, and
    carries no badge glyph — its cue is the profile background and green badge."""

    def test_release_swaps_to_release_profile_and_color(self):
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "release"})

        self.assertIn(("set-profile", "beacon-release"), self.cli_calls,
                      "entering release must swap into the beacon-release profile")
        release_hex = self.beacon.BADGE_COLOR_PALETTE["release"]
        self.assertIn(("badge-color", release_hex), self.cli_calls)
        self.assertIn(("tab-color", release_hex), self.cli_calls)

    def test_release_badge_has_no_glyph(self):
        self.beacon.apply({**_base_state(), "status": "release"})
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "release carries its cue in the profile/background, not a badge glyph",
        )

    def test_release_command_sets_status_without_freezing_identity(self):
        # Like retro (and unlike pause/STATE-03), release does not snapshot overrides.
        self.beacon.write_state("resolved", json.dumps({
            "project": "shown-proj", "project_provider": "git-remote",
            "task": "shown-task", "task_provider": "pr",
        }))
        self.beacon.cmd_release(mock.Mock(note=["v2", "ship"]))
        self.assertEqual(self.beacon.read_state("override.status"), "release")
        self.assertEqual(self.beacon.read_state("description"), "v2 ship")
        self.assertIsNone(self.beacon.read_state("override.project"),
                          "release must not freeze the badge identity (paused-only)")
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_release_persists_across_prompt(self):
        # STATE-04 auto-resume is paused-only; a returning prompt must not clear
        # release (a shipping session stays in flight until explicitly resumed).
        self.beacon.write_state("override.status", "release")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "one more thing"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_state("override.status"), "release",
                         "release is a deliberate mode — it persists until cleared")


class ModeProfileDerivation(unittest.TestCase):
    """RENDER-05 / §6.6: install derives one mode profile per MODE_PROFILES entry
    from the rendered base — same layout, a de-emphasized Dracula background (and,
    for paused, a faint background image) — so they never drift. THEME-01: hexes
    are single-sourced in MODE_PROFILES."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.beacon = _load_beacon(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)
        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)
        home_patcher = mock.patch("pathlib.Path.home", return_value=Path(self._home.name))
        home_patcher.start()
        self.addCleanup(home_patcher.stop)

    def test_hex_to_color_components(self):
        comps = self.beacon._hex_to_color_components("44475a")
        self.assertAlmostEqual(comps["Red Component"], 0x44 / 255.0)
        self.assertAlmostEqual(comps["Green Component"], 0x47 / 255.0)
        self.assertAlmostEqual(comps["Blue Component"], 0x5a / 255.0)
        self.assertEqual(comps["Color Space"], "sRGB")
        self.assertEqual(comps["Alpha Component"], 1.0)

    def test_install_derives_each_mode_profile_from_base(self):
        ok, msg = self.beacon.install_dynamic_profile()
        self.assertTrue(ok, msg)
        profiles_dir = (Path(self._home.name) / "Library" / "Application Support"
                        / "iTerm2" / "DynamicProfiles")
        base = json.loads((profiles_dir / "beacon-dev.json").read_text())["Profiles"][0]
        self.assertNotIn("Background Color", base, "base inherits its background")

        seen_guids = {base["Guid"]}
        for mode, spec in self.beacon.MODE_PROFILES.items():
            prof = json.loads((profiles_dir / f"{spec['profile']}.json").read_text())["Profiles"][0]
            self.assertEqual(prof["Name"], spec["profile"])
            self.assertEqual(prof["Guid"], spec["guid"])
            self.assertNotIn(prof["Guid"], seen_guids, f"{mode} needs a distinct Guid")
            seen_guids.add(prof["Guid"])
            # Same layout (single-sourced) — a mode profile differs only by background.
            self.assertEqual(prof["Status Bar Layout"], base["Status Bar Layout"])
            self.assertAlmostEqual(
                prof["Background Color"]["Red Component"],
                int(spec["background"][0:2], 16) / 255.0,
            )
            if spec["image"]:
                self.assertTrue(prof["Background Image Location"].endswith(spec["image"]))
                self.assertEqual(prof["Background Image Mode"], 3)
                self.assertEqual(prof["Blend"], spec["blend"])
            else:
                self.assertNotIn("Background Image Location", prof)

    def test_mode_images_match_their_cue(self):
        # Every mode carries a slate watermark now (paused ||-button, release
        # rocket, retro checklist clipboard, done checkered flag), all derived from
        # their <phase>-src.png through iterm/make-bg.py; each with a blend.
        for mode in ("paused", "release", "retro", "done"):
            self.assertTrue(self.beacon.MODE_PROFILES[mode]["image"],
                            f"{mode} should carry a watermark image")
            self.assertIsNotNone(self.beacon.MODE_PROFILES[mode]["blend"])

    def test_mode_image_files_exist(self):
        # The watermark assets each mode names must be present on disk: they back
        # both the profile background (install) and the /mode-bg/<state> serve
        # route the dashboard card renders (WIP-17). A rename that misses one
        # would 404 the card and blank the pane background.
        for mode, spec in self.beacon.MODE_PROFILES.items():
            p = self.beacon.PLUGIN_ROOT / "iterm" / "resources" / spec["image"]
            self.assertTrue(p.is_file(), f"{mode} watermark asset missing: {p}")


class CustomizableStatusBarButtons(unittest.TestCase):
    """STATUS-BAR-09 / CMD-23: the `↖ web` and `↗ code` buttons take their label
    and their command from `statusbar.buttons.<name>`. The command is read on the
    click; the label is baked into the profile, so it applies on a re-render."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.beacon = _load_beacon(Path(self._tmp.name))
        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)
        home_patcher = mock.patch("pathlib.Path.home", return_value=Path(self._home.name))
        home_patcher.start()
        self.addCleanup(home_patcher.stop)
        self._cfg_dir = Path(self._tmp.name) / "cfg"
        (self._cfg_dir / "beacon").mkdir(parents=True, exist_ok=True)

    def _config(self, **keys):
        (self._cfg_dir / "beacon" / "config.json").write_text(json.dumps(keys))
        return mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self._cfg_dir)})

    def _buttons(self, **by_name):
        return self._config(statusbar={"buttons": by_name})

    def _profiles_dir(self):
        return (Path(self._home.name) / "Library" / "Application Support"
                / "iTerm2" / "DynamicProfiles")

    def _rendered_titles(self):
        base = json.loads((self._profiles_dir() / "beacon-dev.json").read_text())["Profiles"][0]
        return [c["configuration"]["knobs"]["action"]["title"]
                for c in base["Status Bar Layout"]["components"]
                if c["class"] == "iTermStatusBarActionComponent"]

    def test_defaults_when_no_config_is_present(self):
        with self._config():
            self.assertEqual(self.beacon._statusbar_button("web"),
                             {"label": "↖ web", "cmd": ""})
            self.assertEqual(self.beacon._statusbar_button("code"),
                             {"label": "↗ code", "cmd": "code --maximized"})

    def test_label_and_cmd_are_read_from_the_block(self):
        with self._buttons(web={"label": "↖ repo", "cmd": "git web"}):
            self.assertEqual(self.beacon._statusbar_button("web"),
                             {"label": "↖ repo", "cmd": "git web"})

    def test_one_field_set_leaves_the_other_at_its_default(self):
        with self._buttons(code={"label": "↗ edit"}):
            self.assertEqual(self.beacon._statusbar_button("code"),
                             {"label": "↗ edit", "cmd": "code --maximized"})

    def test_a_blank_value_falls_back_rather_than_disabling(self):
        # A whitespace-only label would render an invisible button, and a blank
        # code cmd has nothing to launch — both mean "the default" instead.
        with self._buttons(code={"label": "   ", "cmd": ""}):
            self.assertEqual(self.beacon._statusbar_button("code"),
                             {"label": "↗ code", "cmd": "code --maximized"})

    def test_a_non_dict_block_is_ignored(self):
        # A hand-edited config can put a string where the block goes; defaults
        # are the answer, not a crash on a click.
        with self._config(statusbar={"buttons": {"web": "git web"}}):
            self.assertEqual(self.beacon._statusbar_button("web")["label"], "↖ web")
        with self._config(statusbar="buttons"):
            self.assertEqual(self.beacon._statusbar_button("web")["label"], "↖ web")

    def test_rendered_profile_carries_the_configured_labels(self):
        with self._buttons(web={"label": "↖ repo"}, code={"label": "↗ edit"}):
            ok, msg = self.beacon.install_dynamic_profile()
        self.assertTrue(ok, msg)
        self.assertEqual(self._rendered_titles(), ["↖ repo", "↗ edit"])

    def test_every_mode_profile_carries_the_configured_labels(self):
        # The mode profiles are deep copies of the base, so a customized label
        # must survive into each of them — otherwise a paused pane silently
        # reverts to the shipped title.
        with self._buttons(web={"label": "↖ repo"}):
            ok, msg = self.beacon.install_dynamic_profile()
        self.assertTrue(ok, msg)
        for spec in self.beacon.MODE_PROFILES.values():
            prof = json.loads(
                (self._profiles_dir() / f"{spec['profile']}.json").read_text())["Profiles"][0]
            titles = [c["configuration"]["knobs"]["action"]["title"]
                      for c in prof["Status Bar Layout"]["components"]
                      if c["class"] == "iTermStatusBarActionComponent"]
            self.assertEqual(titles, ["↖ repo", "↗ code"])

    def test_no_placeholder_survives_into_the_written_profile(self):
        # An unsubstituted placeholder still parses as JSON, so it ships as a
        # literal `__BEACON_…__` button title rather than failing the install.
        with self._config():
            ok, msg = self.beacon.install_dynamic_profile()
        self.assertTrue(ok, msg)
        for path in self._profiles_dir().glob("beacon-*.json"):
            with self.subTest(profile=path.name):
                self.assertNotIn("__BEACON_", path.read_text())

    def test_a_cmd_is_argv_not_a_shell_line(self):
        # No shell=True anywhere on the click path: a config value must reach
        # the program as literal argv, so metacharacters can't be evaluated.
        calls = []

        def fake_run(argv, **kw):
            calls.append((argv, kw.get("shell")))
            return types.SimpleNamespace(returncode=0, stderr=b"", stdout="")

        with self._buttons(code={"cmd": "ed '$(touch /tmp/pwned)' >out"}), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/bin/ed"), \
             mock.patch.object(self.beacon.subprocess, "run", fake_run):
            self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir="/work/repo"))
        argv, shell = calls[0]
        self.assertIsNot(shell, True)
        self.assertEqual(argv, ["/bin/ed", "$(touch /tmp/pwned)", ">out", "/work/repo"])

    def test_the_code_directory_is_appended_last(self):
        calls = []
        with mock.patch.object(self.beacon, "_resolve_editor", return_value="/bin/code"), \
             mock.patch.object(self.beacon.subprocess, "run",
                               side_effect=lambda a, **k: calls.append(a) or types.SimpleNamespace(
                                   returncode=0, stderr=b"")):
            with self._config():
                self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir="/work/repo"))
        self.assertEqual(calls[0][-1], "/work/repo")

    def test_the_web_cmd_gets_the_directory_as_its_cwd_not_an_argument(self):
        calls = []
        with self._buttons(web={"cmd": "git web"}), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/usr/bin/git"), \
             mock.patch.object(self.beacon.subprocess, "run",
                               side_effect=lambda a, **k: calls.append((a, k.get("cwd"))) or types.SimpleNamespace(
                                   returncode=0, stderr="", stdout="")):
            self.beacon.cmd_open_url(self.beacon.argparse.Namespace(dir="/work/repo"))
        argv, cwd = calls[0]
        self.assertEqual(argv, ["/usr/bin/git", "web"])
        self.assertEqual(cwd, str(Path("/work/repo")))

    def _launch(self, cmd, cwd="/work/repo", branch="topic", project="widgets"):
        """Run the code button with `cmd` configured, returning the argv it
        launched. Token *values* are stubbed so the captured subprocess call is
        the editor's and not a git probe's; `_cmd_token_values` has its own test."""
        calls = []
        with self._buttons(code={"cmd": cmd}), \
             mock.patch.object(self.beacon, "_cmd_token_values",
                               return_value={"dir": cwd, "project": project, "branch": branch}), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/bin/ed"), \
             mock.patch.object(self.beacon.subprocess, "run",
                               side_effect=lambda a, **k: calls.append(a) or types.SimpleNamespace(
                                   returncode=0, stderr=b"")):
            self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir=cwd))
        return calls[0]

    def test_token_values_come_from_the_clicked_directory(self):
        with mock.patch.object(self.beacon, "_project_name_at", return_value="widgets"), \
             mock.patch.object(self.beacon, "p_branch", return_value="topic"):
            self.assertEqual(self.beacon._cmd_token_values(Path("/work/repo")),
                             {"dir": str(Path("/work/repo")), "project": "widgets", "branch": "topic"})

    def test_token_values_are_empty_strings_when_unresolvable(self):
        with mock.patch.object(self.beacon, "_project_name_at", return_value=""), \
             mock.patch.object(self.beacon, "p_branch", return_value=None):
            values = self.beacon._cmd_token_values(Path("/tmp"))
        self.assertEqual(values["project"], "")
        self.assertEqual(values["branch"], "")

    def test_dir_token_positions_the_path_and_suppresses_the_append(self):
        argv = self._launch("ed --goto {dir}/README.md")
        self.assertEqual(argv, ["/bin/ed", "--goto", "/work/repo/README.md"])

    def test_a_token_free_cmd_still_gets_the_append(self):
        self.assertEqual(self._launch("ed -n"), ["/bin/ed", "-n", "/work/repo"])

    def test_a_non_dir_token_does_not_suppress_the_append(self):
        # `{branch}` says nothing about where the path goes, so the directory
        # still needs appending — otherwise the editor opens nothing.
        argv = self._launch("ed --branch {branch}")
        self.assertEqual(argv, ["/bin/ed", "--branch", "topic", "/work/repo"])

    def test_a_value_with_spaces_stays_one_argument(self):
        # The reason substitution is per-argument rather than on the command
        # string: re-splitting would turn one path into two arguments.
        argv = self._launch("ed {dir}", cwd="/work/My Repo")
        self.assertEqual(argv, ["/bin/ed", "/work/My Repo"])

    def test_an_argument_that_expands_to_nothing_is_dropped(self):
        self.assertEqual(self._launch("ed {branch}", branch=""), ["/bin/ed", "/work/repo"])

    def test_doubled_braces_are_literal_and_bare_braces_pass_through(self):
        argv = self._launch("ed {{literal}} {} {dir}")
        self.assertEqual(argv, ["/bin/ed", "{literal}", "{}", "/work/repo"])

    def test_an_unknown_placeholder_names_the_known_ones(self):
        with self._buttons(code={"cmd": "ed {nope}"}), \
             mock.patch.object(self.beacon, "_cmd_token_values",
                               return_value={"dir": "/work/repo", "project": "widgets", "branch": "topic"}), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/bin/ed"):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir="/work/repo"))
        msg = str(cm.exception)
        self.assertIn("{nope}", msg)
        self.assertIn("{dir}", msg)

    def test_a_substituted_value_cannot_introduce_an_argument(self):
        # A directory whose name looks like a flag must arrive as one argv
        # entry, not be re-split into a flag the user never wrote.
        argv = self._launch("ed {dir}", cwd="/work/--rm -rf")
        self.assertEqual(argv, ["/bin/ed", "/work/--rm -rf"])

    def test_tokens_expand_for_the_web_button_too(self):
        calls = []
        with self._buttons(web={"cmd": "gh browse --repo {project}"}), \
             mock.patch.object(self.beacon, "_cmd_token_values",
                               return_value={"dir": "/work/repo", "project": "widgets", "branch": "topic"}), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/usr/bin/gh"), \
             mock.patch.object(self.beacon.subprocess, "run",
                               side_effect=lambda a, **k: calls.append((a, k.get("cwd"))) or types.SimpleNamespace(
                                   returncode=0, stderr="", stdout="")):
            self.beacon.cmd_open_url(self.beacon.argparse.Namespace(dir="/work/repo"))
        argv, cwd = calls[0]
        self.assertEqual(argv, ["/usr/bin/gh", "browse", "--repo", "widgets"])
        # The cwd handoff is unconditional for web — there is no append to suppress.
        self.assertEqual(cwd, str(Path("/work/repo")))

    def test_no_git_work_when_the_cmd_has_no_placeholder(self):
        # Resolving the token values costs two git probes; a cmd referencing
        # none of them must not pay for them on every click.
        calls = []
        with self._buttons(code={"cmd": "ed -n"}), \
             mock.patch.object(self.beacon, "_cmd_token_values",
                               side_effect=AssertionError("must not resolve token values")), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/bin/ed"), \
             mock.patch.object(self.beacon.subprocess, "run",
                               side_effect=lambda a, **k: calls.append(a) or types.SimpleNamespace(
                                   returncode=0, stderr=b"")):
            self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir="/work/repo"))
        self.assertEqual(calls[0], ["/bin/ed", "-n", "/work/repo"])

    def test_install_profile_requires_iterm(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_install_profile(self.beacon.argparse.Namespace())
        self.assertIn("iTerm2", str(cm.exception))

    def test_install_profile_rerenders_without_the_rest_of_the_bootstrap(self):
        calls = []
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True), \
             mock.patch.object(self.beacon, "install_dynamic_profile",
                               side_effect=lambda: (calls.append("profile") or (True, "wrote it"))), \
             mock.patch.object(self.beacon, "_install_cli_wrapper",
                               side_effect=AssertionError("must not run the wrapper step")), \
             mock.patch.object(self.beacon, "_install_shell_source",
                               side_effect=AssertionError("must not run the shell step")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.beacon.cmd_install_profile(self.beacon.argparse.Namespace())
        self.assertEqual(calls, ["profile"])

    def test_install_profile_exits_nonzero_when_the_write_fails(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True), \
             mock.patch.object(self.beacon, "install_dynamic_profile",
                               return_value=(False, "failed to write")):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_install_profile(self.beacon.argparse.Namespace())
        self.assertIn("failed to write", str(cm.exception))


class TemplatePlaceholdersAreAllSubstituted(unittest.TestCase):
    """Every `__BEACON_*__` in the profile template needs a matching `.replace`
    in `install_dynamic_profile`. A placeholder added to the template alone
    parses fine and ships as a literal button title or shell path, so nothing
    else catches it."""

    def test_template_and_installer_agree_on_the_placeholder_set(self):
        template = (REPO_ROOT / "iterm" / "profile.json.template").read_text(encoding="utf-8")
        src = (REPO_ROOT / "scripts" / "beacon").read_text(encoding="utf-8")
        in_template = set(re.findall(r"__BEACON_[A-Z_]+__", template))
        self.assertTrue(in_template, "template has no placeholders — did they move?")
        for name in sorted(in_template):
            with self.subTest(placeholder=name):
                self.assertIn(f'.replace("{name}"', src,
                              f"{name} is in the template but never substituted")

    def test_the_test_helper_covers_every_placeholder(self):
        template = (REPO_ROOT / "iterm" / "profile.json.template").read_text(encoding="utf-8")
        in_template = set(re.findall(r"__BEACON_[A-Z_]+__", template))
        self.assertEqual(in_template, set(PROFILE_SUBSTITUTIONS),
                         "PROFILE_SUBSTITUTIONS is out of step with the template")


class PendingAttentionPaintsBlocked(BeaconTest):
    """BADGE-09a: the pending-attention marker forces the blocked (red) color
    state via OSC, regardless of the prompt subtype — beacon no longer
    distinguishes permission from idle on the pane (the watermark is gone)."""

    def test_pending_attention_emits_blocked_hex(self):
        self.beacon.apply({
            **_base_state(), "status": "waiting", "pending_attention": True,
        })
        red = self.beacon.BADGE_COLOR_PALETTE["blocked"]
        self.assertIn(("badge-color", red), self.cli_calls)
        self.assertIn(("tab-color", red), self.cli_calls)
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile" and c[1] != "beacon-dev"],
            [],
            "No per-state profile switch — blocked is an OSC color",
        )


class DescriptionIsFleetData(BeaconTest):
    """STATE-02: a description is persisted and surfaced in the fleet view; the
    pane paints no reason text of its own (the badge was a bad home for it, so the
    reason now rides the Claude Code status line, STATUSLINE-01). While paused the
    title/tab lead with the ⏸ glyph (TITLE-06); the pane still paints only the
    paused color + profile, never a retired bg-image/note/clear-screen overlay."""

    def test_paused_leads_title_glyph_and_paints_only_color(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()
        self.beacon.apply({
            **_base_state(), "status": "paused", "description": "leaving for lunch",
        })
        paused_hex = self.beacon.BADGE_COLOR_PALETTE["paused"]
        self.assertIn(("tab-color", paused_hex), self.cli_calls)
        # TITLE-06: the paused glyph leads line 1.
        self.assertIn(("uservar", "beacon_title_prefix", self.beacon.PAUSED_TITLE_GLYPH), self.cli_calls)
        # The description paints no reason text on the pane and no retired overlay.
        for verb in ("bg-image", "note", "clear-screen"):
            self.assertEqual(
                [c for c in self.cli_calls if c[0] == verb], [],
                f"a description must not emit {verb} (overlay retired)",
            )

    def test_resume_clears_title_glyph(self):
        self.beacon.apply({**_base_state(), "status": "paused", "description": "brb"})
        self.cli_calls.clear()
        self.beacon.apply({**_base_state(), "status": "working"})
        self.assertIn(("uservar", "beacon_title_prefix", ""), self.cli_calls)

    def test_description_alone_does_not_repaint(self):
        # Adding a description without a logical-state change is data-only.
        self.beacon.apply({**_base_state(), "status": "waiting"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "status": "waiting",
            "description": "bg refresh ~30 min",
        })

        self.assertEqual(
            [c for c in self.cli_calls if c[0] in ("badge-color", "tab-color")], [],
            "logical state unchanged → no color repaint; description is data",
        )


class PauseSnapshotIsNetworkFree(BeaconTest):
    """STATE-03: pause freezes the project/task the badge is currently showing.
    It reads the last-rendered `resolved` snapshot rather than re-resolving, so
    the hot pause path never runs the task chain's gh/glab PR-title provider —
    and an active label override survives the pause instead of being discarded."""

    def test_pause_freezes_displayed_identity_from_snapshot(self):
        self.beacon.write_state("resolved", json.dumps({
            "project": "frozen-proj", "project_provider": "git-remote",
            "task": "frozen-task", "task_provider": "pr",
        }))
        # If pause re-resolved, this would blow up — there's no live PR to fetch
        # and the providers are pinned to acme/widget, not the frozen values.
        with mock.patch.object(self.beacon, "resolve",
                               side_effect=AssertionError("pause must not re-resolve")):
            self.beacon._apply_status("paused", "")
        self.assertEqual(self.beacon.read_state("override.project"), "frozen-proj")
        self.assertEqual(self.beacon.read_state("override.task"), "frozen-task")
        self.assertEqual(self.beacon.read_state("override.status"), "paused")

    def test_pause_preserves_active_label_override(self):
        # The old re-resolve dropped overrides and snapshotted git-derived
        # values, so a labeled pane silently relabeled on pause. Freezing what
        # is shown keeps the label.
        self.beacon.write_state("resolved", json.dumps({
            "project": "mylabel", "project_provider": "override",
            "task": "", "task_provider": "default",
        }))
        self.beacon._apply_status("paused", "")
        self.assertEqual(self.beacon.read_state("override.project"), "mylabel")
        # An empty/default task is not frozen as an override.
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_pause_falls_back_to_resolve_when_never_rendered(self):
        # No `resolved` snapshot yet (badge never painted this session) → fall
        # back to a live resolve so the freeze still captures current identity.
        with mock.patch.object(self.beacon, "p_pr_title", return_value=""):
            self.beacon._apply_status("paused", "")
        self.assertEqual(self.beacon.read_state("override.project"), "acme/widget")


class EngagementMarker(BeaconTest):
    """BADGE-14: any apply() call places the per-pane engagement marker.
    `beacon clear` (no field) removes it and disengages the pane."""

    def test_apply_places_marker(self):
        marker = self.beacon._engagement_marker_path()
        self.assertIsNotNone(marker)
        self.assertFalse(marker.exists(), "marker should be absent pre-engagement")

        self.beacon.apply({**_base_state(), "status": "idle"})

        self.assertTrue(marker.exists(), "apply() must place the engagement marker")

    def test_clear_no_field_disengages(self):
        # Engage first
        self.beacon.apply({**_base_state(), "status": "working"})
        marker = self.beacon._engagement_marker_path()
        self.assertTrue(marker.exists())
        self.cli_calls.clear()

        self.beacon.cmd_clear(mock.Mock(field=None))

        self.assertFalse(marker.exists(), "clear (no field) must remove the engagement marker")
        self.assertIn(("clear",), self.cli_calls,
                      "clear (no field) must reset badge + tab color to default")
        self.assertIn(("uservar", "beacon_project", ""), self.cli_calls,
                      "clear (no field) must empty the badge text")
        self.assertIn(("uservar", "beacon_task", ""), self.cli_calls,
                      "clear (no field) must empty the task slot so a stale "
                      "task doesn't linger on the badge after disengagement")

    def test_clear_mid_mode_reverts_profile(self):
        # Clearing while in a mode state must swap back to the base profile —
        # the color-only `clear` OSC can't undo the mode profile's background.
        self.beacon.apply({**_base_state(), "status": "paused"})
        self.cli_calls.clear()
        self.beacon.cmd_clear(mock.Mock(field=None))
        self.assertIn(("set-profile", "beacon-dev"), self.cli_calls,
                      "clear (no field) mid-mode must swap back to the base beacon-dev profile")

    def test_clear_with_field_keeps_engagement(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        marker = self.beacon._engagement_marker_path()
        self.assertTrue(marker.exists())

        self.beacon.cmd_clear(mock.Mock(field="project"))

        self.assertTrue(
            marker.exists(),
            "per-field clear must NOT disengage — engagement persists across overrides",
        )


class ResolveUrlForgeFallback(BeaconTest):
    """When tack has no link for the current branch but a forge knows of an
    MR/PR for that branch, resolve_url prefers the forge URL over the branch
    tree fallback. Without this step the chip never lands on an MR/Issue when
    the user hasn't populated tack manually."""

    def _patch_chain(self, branch: str, remote_url: str, fake_run, which=None):
        """Common patches: no override, no tack, fixed branch + remote, all
        subprocess calls routed through fake_run. `which` defaults to "gh and
        glab present"; pass `lambda _: False` to simulate neither installed."""
        if which is None:
            which = lambda x: f"/usr/local/bin/{x}" if x in ("gh", "glab") else None
        return [
            mock.patch.object(self.beacon, "p_override", return_value=""),
            mock.patch.object(self.beacon, "_tack_url_for", return_value=("", "")),
            mock.patch.object(self.beacon, "p_branch", return_value=branch),
            mock.patch.object(self.beacon, "_git_remote_url_normalized",
                              return_value=remote_url),
            mock.patch.object(self.beacon, "_which", side_effect=which),
            mock.patch("subprocess.run", side_effect=fake_run),
        ]

    def test_returns_gh_pr_url_when_tack_empty_and_pr_exists(self):
        pr_url = "https://github.com/chris-peterson/beacon/pull/42"
        gh_out = f'[{{"url":"{pr_url}","number":42,"title":"chip best url"}}]\n'

        def fake_run(cmd, *args, **kwargs):
            if cmd[:2] == ["gh", "pr"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=gh_out, stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

        patches = self._patch_chain(
            "chip-best-url", "https://github.com/chris-peterson/beacon", fake_run,
        )
        for p in patches: p.start()
        try:
            url, _ = self.beacon.resolve_url(Path("/tmp/fake"))
        finally:
            for p in patches: p.stop()

        self.assertEqual(url, pr_url)

    def test_returns_glab_mr_url_on_gitlab_remote(self):
        mr_url = "https://gitlab.example.com/team/repo/-/merge_requests/17"
        glab_out = f'[{{"web_url":"{mr_url}","iid":17,"title":"some MR"}}]\n'

        def fake_run(cmd, *args, **kwargs):
            if cmd[:2] == ["glab", "mr"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=glab_out, stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

        patches = self._patch_chain(
            "feature-x", "https://gitlab.example.com/team/repo", fake_run,
        )
        for p in patches: p.start()
        try:
            url, _ = self.beacon.resolve_url(Path("/tmp/fake"))
        finally:
            for p in patches: p.stop()

        self.assertEqual(url, mr_url)

    def test_falls_through_to_branch_url_when_forge_tool_missing(self):
        def fake_run(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

        patches = self._patch_chain(
            "chip-best-url", "https://github.com/chris-peterson/beacon",
            fake_run, which=lambda _: False,
        )
        for p in patches: p.start()
        try:
            url, _ = self.beacon.resolve_url(Path("/tmp/fake"))
        finally:
            for p in patches: p.stop()

        self.assertEqual(url, "https://github.com/chris-peterson/beacon/tree/chip-best-url")


class TackUrlHonorsSessionPin(BeaconTest):
    """_tack_url_for resolves the route via the session→route pin, not the
    branch slug alone, so the status-line link and the fleet-view chip read the
    same route. A route pinned to the session whose slug differs from the
    branch (a pin, not a branch-slug match) must still surface its deliverable
    URL; location correlation (via _tack_route_for) is the fallback."""

    ISSUE = "https://gitlab.getty.cloud/ecommerce/elasticache-toolbox/-/issues/2"

    def _tack_url(self, routes, *, sid, branch, tack_route=("", None)):
        def fake_run(cmd, *a, **k):
            if cmd[:2] == ["tack", "list"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=json.dumps(routes), stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        patches = [
            mock.patch.object(self.beacon, "_which",
                              side_effect=lambda x: "/bin/tack" if x == "tack" else None),
            mock.patch.object(self.beacon, "read_state",
                              side_effect=lambda f: (sid or None) if f == "claude_session_id" else None),
            mock.patch.object(self.beacon, "_tack_route_for", return_value=tack_route),
            mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": ""}, clear=False),
            mock.patch("subprocess.run", side_effect=fake_run),
        ]
        for p in patches: p.start()
        try:
            return self.beacon._tack_url_for(Path("/tmp/fake"), branch, "elasticache-toolbox")
        finally:
            for p in patches: p.stop()

    def test_pin_resolves_even_when_slug_differs_from_branch(self):
        routes = [{
            "slug": "elasticache-maintenance-component",
            "sessions": [{"id": "sid-1", "started_at": "2026-07-08T22:24:34Z"}],
            "tacks": [{"status": "in_progress",
                       "deliverable": {"label": "elasticache-toolbox#2", "url": self.ISSUE}}],
        }]
        url, _ = self._tack_url(routes, sid="sid-1",
                                branch="add-maintenance-cicd-component")
        self.assertEqual(url, self.ISSUE)

    def test_most_recently_started_pin_wins(self):
        routes = [
            {"slug": "old", "sessions": [{"id": "sid-1", "started_at": "2026-07-01T00:00:00Z"}],
             "tacks": [{"status": "in_progress", "deliverable": {"url": "https://x/old"}}]},
            {"slug": "new", "sessions": [{"id": "sid-1", "started_at": "2026-07-08T00:00:00Z"}],
             "tacks": [{"status": "in_progress", "deliverable": {"url": self.ISSUE}}]},
        ]
        url, _ = self._tack_url(routes, sid="sid-1", branch="whatever")
        self.assertEqual(url, self.ISSUE)

    def test_falls_back_to_location_route_when_no_pin(self):
        routes = [{
            "slug": "add-maintenance-cicd-component",
            "sessions": [],
            "tacks": [{"status": "in_progress", "deliverable": {"url": self.ISSUE}}],
        }]
        url, _ = self._tack_url(
            routes, sid="", branch="add-maintenance-cicd-component",
            tack_route=("add-maintenance-cicd-component", None))
        self.assertEqual(url, self.ISSUE)


class CacheKeyIsPaneStable(BeaconTest):
    """The handoff cache files (cwd / url) and the engagement marker key on the
    pane GUID, not the full ITERM_SESSION_ID: the `wNtNpN` positional prefix
    changes when a pane is moved between windows/tabs/splits, and keying on it
    left the `↗ code` button reading a file written under the pane's old
    position, so it silently no-op'd."""

    def _key(self, iterm_id):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": iterm_id}):
            return self.beacon._iterm_cache_key()

    def test_strips_positional_prefix_to_guid(self):
        self.assertEqual(self._key("w2t0p1:AB30E8DC-1234"), "AB30E8DC-1234")

    def test_key_is_invariant_across_pane_moves(self):
        self.assertEqual(self._key("w2t0p1:GUID-X"), self._key("w1t0p0:GUID-X"))

    def test_synthesized_non_iterm_id_survives(self):
        self.assertEqual(self._key("claude-session:uuid-9"), "uuid-9")

    def test_no_pane_id_yields_none(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ITERM_SESSION_ID", None)
            self.assertIsNone(self.beacon._iterm_cache_key())

    def test_engagement_marker_found_after_pane_move(self):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w2t0p1:GUID-Z"}):
            self.beacon.place_engagement_marker()
        # Pane moved: same GUID, new positional prefix.
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w0t3p2:GUID-Z"}):
            self.assertTrue(
                self.beacon._engagement_marker_path().exists(),
                "engagement marker must survive a pane move (keyed on GUID)")


class SessionSeedIsPaneStable(BeaconTest):
    """The session seed (and thus the state-bucket hash) keys on the pane GUID,
    not the full ITERM_SESSION_ID: iTerm2 rewrites the `wNtNpN` positional
    prefix when a pane is moved, so seeding on the full id fragmented a pane's
    state into a fresh bucket on every move. The synthesized `claude-session:`
    form is kept whole so a bare `beacon set` and the hooks converge on it."""

    def test_seed_strips_positional_prefix(self):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w2t0p1:GUID-A"}):
            self.assertEqual(self.beacon._session_seed(), "GUID-A")

    def test_seed_is_invariant_across_pane_moves(self):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w2t0p1:GUID-A"}):
            moved_a = self.beacon.session_hash()
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w1t3p0:GUID-A"}):
            moved_b = self.beacon.session_hash()
        self.assertEqual(moved_a, moved_b)

    def test_seed_keeps_synthesized_form_whole(self):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "claude-session:xyz"}):
            self.assertEqual(self.beacon._session_seed(), "claude-session:xyz")


class BadgeFormatReferencesTaskSlot(BeaconTest):
    """BADGE-03: the badge text must reflect the resolved task value, not just
    the project. The format string is the contract between the plugin (writer
    of beacon_task) and iTerm2 (renderer of the slot)."""

    def test_badge_format_includes_beacon_task(self):
        self.assertIn(
            r"\(user.beacon_task)", self.beacon.BADGE_FORMAT,
            "BADGE_FORMAT must reference user.beacon_task so the slot lands "
            "on the badge",
        )

    def test_profile_template_badge_text_is_empty(self):
        # BADGE-15: the badge is opt-in and off by default, so the profile's
        # static "Badge Text" backstop is empty — the plugin/shell only emit
        # SetBadgeFormat when the user enables the badge in config.
        template = json.loads((REPO_ROOT / "iterm" / "profile.json.template").read_text(encoding="utf-8"))
        self.assertEqual(template["Profiles"][0]["Badge Text"], "")


class BadgeToggle(BeaconTest):
    """BADGE-15: the pane badge is opt-in and off by default. The render always
    paints the tab color (the primary state signal); it emits the badge OSCs
    only when the user config enables the badge."""

    def test_default_off_paints_tab_not_badge(self):
        with mock.patch.object(self.beacon, "_badge_enabled", return_value=False):
            self.beacon.apply({**_base_state(), "status": "working"})
        kinds = [c[0] for c in self.cli_calls]
        self.assertIn("tab-color", kinds)
        self.assertNotIn("badge-color", kinds)
        self.assertNotIn("badge-format", kinds)

    def test_enabled_paints_badge(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        kinds = [c[0] for c in self.cli_calls]
        self.assertIn("badge-color", kinds)
        self.assertIn("badge-format", kinds)


class BadgeConfigToggle(unittest.TestCase):
    """BADGE-15: _badge_enabled reads the user config's `badge` key (default
    off). Loaded without BeaconTest's badge mock so the real gate runs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.beacon = _load_beacon(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)

    def test_toggle_reads_config(self):
        for val in ("on", "true", "1", "yes", True):
            with mock.patch.object(self.beacon, "_load_config", return_value={"badge": val}):
                self.assertTrue(self.beacon._badge_enabled(), val)
        for cfg in ({}, {"badge": "off"}, {"badge": False}, {"badge": "no"}):
            with mock.patch.object(self.beacon, "_load_config", return_value=cfg):
                self.assertFalse(self.beacon._badge_enabled(), cfg)


class TwoLineTitle(BeaconTest):
    """TITLE-05: the tab / window-title Name carries the task on a second line
    via beacon_task_nl (newline-prefixed), while BADGE_FORMAT stays a single
    " · "-joined line."""

    def test_title_format_uses_task_nl(self):
        self.assertIn(r"\(user.beacon_task_nl)", self.beacon.TITLE_FORMAT)
        self.assertNotIn(r"\(user.beacon_task)", self.beacon.TITLE_FORMAT)

    def test_title_format_leads_with_prefix(self):
        # TITLE-06: the paused mode lead prefixes line 1, ahead of the project.
        self.assertIn(r"\(user.beacon_title_prefix)", self.beacon.TITLE_FORMAT)
        self.assertLess(
            self.beacon.TITLE_FORMAT.index(r"\(user.beacon_title_prefix)"),
            self.beacon.TITLE_FORMAT.index(r"\(user.beacon_project)"),
        )

    def test_apply_publishes_newline_prefixed_task(self):
        self.beacon.apply({**_base_state(), "task": "fix bug"})
        self.assertIn(("uservar", "beacon_task_nl", "\n  fix bug"), self.cli_calls)

    def test_empty_task_collapses(self):
        self.beacon.apply({**_base_state(), "task": ""})
        self.assertIn(("uservar", "beacon_task_nl", ""), self.cli_calls)


class HybridBranchSlots(BeaconTest):
    """STATUS-BAR-03 (#20): _publish_chips routes the branch to exactly one
    slot — the de-emphasized default slot for the repo's default branch, else
    the feature branch's sync-state slot — so the profile's fixed-color
    components resolve to a single visible chip."""

    def _publish(self, detected):
        self.beacon._LAST_CHIP_SIGNATURE = None
        with mock.patch.object(self.beacon, "_detect_branch_info", return_value=detected), \
             mock.patch.object(self.beacon, "_project_full_at", return_value="gh:acme/widget"), \
             mock.patch.object(self.beacon, "resolve_url", return_value=("", "")):
            self.beacon._publish_chips(Path("/x"))
        batch = next(c for c in self.cli_calls if c[0] == "uservar-batch")
        return dict(p.split("=", 1) for p in batch[1:])

    def test_default_branch_fills_default_slot_only(self):
        slots = self._publish(("main", "clean", "", "default"))
        self.assertEqual(slots["beacon_branch_default"], "main")
        self.assertEqual(slots["beacon_branch_clean"], "")
        self.assertEqual(slots["beacon_branch_diverged"], "")
        self.assertEqual(slots["beacon_branch_untracked"], "")

    def test_feature_branch_routes_to_state_slot(self):
        slots = self._publish(("↑1 topic", "diverged", "↑1", "feature"))
        self.assertEqual(slots["beacon_branch_default"], "")
        self.assertEqual(slots["beacon_branch_diverged"], "↑1 topic")
        self.assertEqual(slots["beacon_branch_clean"], "")


class ResolvedUrlPersistence(BeaconTest):
    """STATUSLINE-02: _publish_chips persists the resolved URL so the status line
    can render it without re-running resolve_url (git, and possibly gh/glab) on
    every prompt. The `url-<pane-guid>.txt` handoff file the `↖ web` button read
    is retired with the button — the persisted state is the single source."""

    def _publish(self, url, label, cwd="/x"):
        self.beacon._LAST_CHIP_SIGNATURE = None
        with mock.patch.object(self.beacon, "_detect_branch_info",
                               return_value=("main", "clean", "", "default")), \
             mock.patch.object(self.beacon, "_project_full_at", return_value="gh:acme/widget"), \
             mock.patch.object(self.beacon, "_iterm_cache_key", return_value="GUID"), \
             mock.patch.object(self.beacon, "resolve_url", return_value=(url, label)):
            self.beacon._publish_chips(Path(cwd))

    def test_resolution_is_persisted(self):
        self._publish("https://gh.test/acme/widget/pull/7", "acme/widget#7")
        self.assertEqual(self.beacon.read_state("resolved.url"),
                         "https://gh.test/acme/widget/pull/7")
        self.assertEqual(self.beacon.read_state("resolved.url_label"), "acme/widget#7")

    def test_url_handoff_file_is_not_written(self):
        self._publish("https://gh.test/acme/widget/pull/7", "acme/widget#7")
        self.assertFalse((self.beacon.CACHE_DIR / "url-GUID.txt").exists())
        # The `↗ code` button still needs its cwd handoff file.
        self.assertTrue((self.beacon.CACHE_DIR / "cwd-GUID.txt").exists())

    def test_beacon_url_uservar_is_not_published(self):
        self._publish("https://gh.test/acme/widget/pull/7", "acme/widget#7")
        batch = next(c for c in self.cli_calls if c[0] == "uservar-batch")
        self.assertFalse([p for p in batch[1:] if p.startswith("beacon_url=")])

    def test_url_only_change_still_republishes(self):
        # The URL rides the last-value gate's signature but not the uservar
        # payload. Two URLs can differ while every chip is identical, and the
        # persisted value must follow — otherwise the footer link goes stale.
        self._publish("https://gh.test/acme/widget/tree/a", "acme/widget")
        # Deliberately does NOT reset the gate — that is what's under test.
        with mock.patch.object(self.beacon, "_detect_branch_info",
                               return_value=("main", "clean", "", "default")), \
             mock.patch.object(self.beacon, "_project_full_at", return_value="gh:acme/widget"), \
             mock.patch.object(self.beacon, "_iterm_cache_key", return_value="GUID"), \
             mock.patch.object(self.beacon, "resolve_url",
                               return_value=("https://gh.test/acme/widget/tree/b", "acme/widget")):
            self.beacon._publish_chips(Path("/x"))
        self.assertEqual(self.beacon.read_state("resolved.url"),
                         "https://gh.test/acme/widget/tree/b")


class DeliverableAccumulation(BeaconTest):
    """STATUSLINE-03: _publish_chips records each deliverable the URL resolver
    lands on, so the status line can show what the session has crossed. Only
    forge issue/PR/MR URLs count — a branch or repo page is not a deliverable."""

    def _publish(self, url, project_full="gh:acme/widgets"):
        self.beacon._LAST_CHIP_SIGNATURE = None
        with mock.patch.object(self.beacon, "_detect_branch_info",
                               return_value=("main", "clean", "", "default")), \
             mock.patch.object(self.beacon, "_project_full_at", return_value=project_full), \
             mock.patch.object(self.beacon, "_iterm_cache_key", return_value=None), \
             mock.patch.object(self.beacon, "_tack_landed_urls", return_value=set()), \
             mock.patch.object(self.beacon, "resolve_url", return_value=(url, "label")):
            self.beacon._publish_chips(Path("/x"))

    def _refs(self):
        return [e["ref"] for e in self.beacon.read_state_json("deliverables", [])]

    def test_deliverable_url_is_recorded(self):
        self._publish("https://github.com/acme/widgets/pull/42")
        self.assertEqual(self._refs(), ["#42"])

    def test_gitlab_mr_records_bang_ref(self):
        self._publish("https://gitlab.com/acme/widgets/-/merge_requests/17")
        self.assertEqual(self._refs(), ["!17"])

    def test_branch_url_records_nothing(self):
        self._publish("https://github.com/acme/widgets/tree/main")
        self.assertEqual(self._refs(), [])

    def test_project_identity_is_stored_without_the_suffix(self):
        # The stored identity is what qualification compares against; carrying
        # the `#42` suffix would make every later ref read as foreign.
        self._publish("https://github.com/acme/widgets/pull/42")
        entry = self.beacon.read_state_json("deliverables", [])[0]
        self.assertEqual(entry["project"], "gh:acme/widgets")
        self.assertEqual(self.beacon.read_state("resolved.project"), "gh:acme/widgets")

    def test_crossing_projects_accumulates_both(self):
        self._publish("https://github.com/acme/widgets/pull/42")
        self._publish("https://github.com/other/otherproj/issues/75",
                      project_full="gh:other/otherproj")
        self.assertEqual(self._refs(), ["#42", "#75"])

    def _snapshot(self, task, provider):
        self.beacon.write_state("resolved", json.dumps(
            {"task": task, "task_provider": provider}))

    def test_title_is_the_same_string_the_badge_shows(self):
        # The badge paints the resolved task; the footer titles the CR. Sourcing
        # them separately is what made the two surfaces name one PR differently.
        self._snapshot("Move per-session values into the status line", "pr")
        self._publish("https://github.com/acme/widgets/pull/42")
        self.assertEqual(self.beacon.read_state_json("deliverables", [])[0]["title"],
                         "Move per-session values into the status line")

    def test_an_override_task_titles_the_cr_too(self):
        self._snapshot("ship the cart rework", "override")
        self._publish("https://github.com/acme/widgets/pull/42")
        self.assertEqual(self.beacon.read_state_json("deliverables", [])[0]["title"],
                         "ship the cart rework")

    def test_a_branch_derived_task_is_not_a_title(self):
        # `#42 2.0` is the branch name, not a name for the work.
        self._snapshot("2.0", "branch")
        self._publish("https://github.com/acme/widgets/pull/42")
        self.assertEqual(self.beacon.read_state_json("deliverables", [])[0]["title"], "")

    def test_fresh_start_drops_the_previous_tenant_list(self):
        # State keys on the pane, which outlives a Claude session. Without the
        # wipe, a fresh session's footer credits it with the prior session's
        # deliverables.
        self._publish("https://github.com/acme/widgets/pull/42")
        self.beacon._wipe_session_for_fresh_start()
        self.assertEqual(self._refs(), [])


class ConfigurableCodeButton(BeaconTest):
    """STATUS-BAR-07 (#25): the `↗ code` button's editor comes from the user
    config, read at click time so changing it needs no reinstall."""

    def _config(self, **keys):
        d = Path(self._tmp.name) / "cfg"
        (d / "beacon").mkdir(parents=True, exist_ok=True)
        (d / "beacon" / "config.json").write_text(json.dumps(keys))
        return mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(d)})

    def _button(self, name, **fields):
        return self._config(statusbar={"buttons": {name: fields}})

    def test_default_is_code_maximized(self):
        with self._config():
            self.assertEqual(self.beacon._code_launch_argv(), ["code", "--maximized"])

    def test_cmd_is_honored(self):
        with self._button("code", cmd="subl -n -w"):
            self.assertEqual(self.beacon._code_launch_argv(), ["subl", "-n", "-w"])

    def test_cmd_is_shell_quoted(self):
        with self._button("code", cmd='ed -a "two words"'):
            self.assertEqual(self.beacon._code_launch_argv(), ["ed", "-a", "two words"])

    def test_a_bare_program_passes_no_arguments(self):
        # The single-string cmd is how "no arguments" is said now — it replaces
        # the explicit empty argument list that used to mean the same thing.
        with self._button("code", cmd="mate"):
            self.assertEqual(self.beacon._code_launch_argv(), ["mate"])

    def test_editor_off_path_is_found_via_the_login_shell(self):
        # The regression: a status-bar action shell inherits iTerm2's PATH, so
        # `code` in /opt/homebrew/bin is invisible to shutil.which and the
        # button failed for everyone whose editor lives outside /usr/bin.
        calls = []

        def fake_run(argv, **kw):
            calls.append(argv)
            return types.SimpleNamespace(returncode=0, stdout="/opt/homebrew/bin/code\n",
                                         stderr=b"")

        with self._config(), \
             mock.patch.object(self.beacon.shutil, "which", return_value=None), \
             mock.patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             mock.patch.object(self.beacon.os, "access", return_value=True), \
             mock.patch.object(self.beacon.subprocess, "run", fake_run):
            self.assertEqual(self.beacon._resolve_editor("code"), "/opt/homebrew/bin/code")
        self.assertEqual(calls[0][:2], ["/bin/zsh", "-lc"])

    def test_an_absolute_editor_path_skips_lookup_entirely(self):
        with mock.patch.object(self.beacon.os, "access", return_value=True):
            self.assertEqual(self.beacon._resolve_editor("/Apps/ed"), "/Apps/ed")

    def test_unresolvable_editor_exits_with_an_actionable_message(self):
        # No `open -a` fallback (the repo's no-fallbacks convention): the button
        # surfaces this text in its alert so the user knows what to set.
        with self._button("code", cmd="beacon-no-such-editor"), \
             mock.patch.object(self.beacon.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir="/tmp"))
        msg = str(cm.exception)
        self.assertIn("beacon-no-such-editor", msg)
        self.assertIn("statusbar.buttons.code.cmd", msg)

    def test_launch_passes_args_then_directory(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append(argv)
            return types.SimpleNamespace(returncode=0, stderr=b"")

        with self._button("code", cmd="subl -n"), \
             mock.patch.object(self.beacon.shutil, "which", return_value="/bin/subl"), \
             mock.patch.object(self.beacon.subprocess, "run", fake_run):
            self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir="/work/repo"))
        self.assertEqual(calls, [["/bin/subl", "-n", "/work/repo"]])

    def test_nonzero_exit_is_surfaced(self):
        with self._config(), \
             mock.patch.object(self.beacon.shutil, "which", return_value="/bin/code"), \
             mock.patch.object(self.beacon.subprocess, "run", lambda a, **k: types.SimpleNamespace(
                 returncode=3, stderr=b"boom")):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_open_code(self.beacon.argparse.Namespace(dir="/tmp"))
        self.assertIn("boom", str(cm.exception))

    def test_config_get_space_joins_a_list(self):
        with self._config(focus_origins=["https://a.test", "https://b.test"]):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.beacon.cmd_config_get(self.beacon.argparse.Namespace(key="focus_origins"))
        self.assertEqual(buf.getvalue().strip(), "https://a.test https://b.test")


class CodeButtonInProfile(unittest.TestCase):
    """STATUS-BAR-07: the button delegates to `beacon open-code` rather than
    launching the editor from its own shell — an iTerm2 action shell has no
    interactive PATH (§6.10 caveat 3), so it invokes an absolute interpreter."""

    def _code_action(self):
        layout = _render_profile_template()["Status Bar Layout"]["components"]
        return next(c["configuration"]["knobs"]["action"] for c in layout
                    if c["class"] == "iTermStatusBarActionComponent"
                    and c["configuration"]["knobs"]["action"]["title"] == "↗ code")

    def test_button_calls_open_code_by_absolute_interpreter(self):
        param = self._code_action()["parameter"]
        self.assertIn('"/x/python3" "/x/scripts/beacon" open-code', param)
        self.assertNotIn("open -a", param)

    def test_button_strips_quotes_before_building_the_alert(self):
        # The alert interpolates the error text into AppleScript; an unescaped
        # quote there would break the script instead of showing the message.
        param = self._code_action()["parameter"]
        self.assertIn("tr -d", param)

    def test_python_placeholder_is_substituted_at_install(self):
        src = (REPO_ROOT / "scripts" / "beacon").read_text(encoding="utf-8")
        self.assertIn('"__BEACON_PYTHON__", _json_inner(sys.executable', src)


class PaletteDocMatchesCode(unittest.TestCase):
    """docs/palette.md documents the status line's SGR roles and names the
    constants that carry them. Renaming one in `scripts/beacon` without touching
    the doc leaves a reader chasing an identifier that no longer exists — the
    same drift the page's "keep the hexes in sync" note guards for the pane."""

    NAMES = ("STATUSLINE_CR_SGR", "STATUSLINE_ISSUE_SGR", "STATUSLINE_DELIVERED_SGR",
             "STATUSLINE_VERB_SGR", "STATUSLINE_TITLE_SGR")

    def test_every_constant_the_palette_cites_exists(self):
        palette = (REPO_ROOT / "docs" / "palette.md").read_text(encoding="utf-8")
        src = (REPO_ROOT / "scripts" / "beacon").read_text(encoding="utf-8")
        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertIn(name, palette, f"{name} missing from docs/palette.md")
                self.assertIn(f"{name} = ", src, f"{name} missing from scripts/beacon")

    def test_documented_sgr_values_match_the_code(self):
        palette = (REPO_ROOT / "docs" / "palette.md").read_text(encoding="utf-8")
        beacon = _load_beacon(REPO_ROOT / "tests")
        # The page prints the codes (`SGR 1;36`); a value edited in one place
        # only is exactly what a reader would trust and get wrong.
        for name in ("STATUSLINE_CR_SGR", "STATUSLINE_ISSUE_SGR"):
            with self.subTest(name=name):
                self.assertIn(f"SGR {getattr(beacon, name)}", palette)


class WebButton(unittest.TestCase):
    """STATUS-BAR-08: the `↖ web` chip resolves at click time through
    `beacon open-url`. What was retired in 2.0 is the *URL handoff file* — the
    second source that drifted from the chip (#5) — not the affordance, which a
    pane not running Claude has no other way to reach."""

    def test_chip_calls_open_url_and_reads_no_url_handoff(self):
        template = (REPO_ROOT / "iterm" / "profile.json.template").read_text(encoding="utf-8")
        self.assertIn("__BEACON_WEB_LABEL__", template)
        self.assertIn("open-url", template)
        # The cwd handoff survives; a URL handoff would reintroduce the drift.
        self.assertNotIn("url-${ITERM_SESSION_ID", template)

    def test_shell_publishes_no_url_var_or_handoff(self):
        shell = (REPO_ROOT / "shell" / "beacon.zsh").read_text(encoding="utf-8")
        self.assertNotIn("uservar beacon_url", shell)
        self.assertNotIn("_beacon_write_session_file url", shell)


class OpenUrlCommand(BeaconTest):
    """STATUS-BAR-08 / CMD-14: `open-url [dir]` resolves at click time against
    the directory it is given, so it is correct in a pane beacon isn't
    tracking."""

    def _config(self, **keys):
        d = Path(self._tmp.name) / "webcfg"
        (d / "beacon").mkdir(parents=True, exist_ok=True)
        (d / "beacon" / "config.json").write_text(json.dumps(keys))
        return mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(d)})

    def _web_button(self, cmd):
        return self._config(statusbar={"buttons": {"web": {"cmd": cmd}}})

    def test_resolves_against_the_directory_argument(self):
        seen = {}

        def fake_resolve(cwd=None):
            seen["cwd"] = str(cwd)
            return ("https://x.test/acme/widgets/pull/7", "acme/widgets#7")

        with self._config(), \
             mock.patch.object(self.beacon, "resolve_url", fake_resolve), \
             mock.patch.object(self.beacon.subprocess, "run",
                               lambda a, **k: types.SimpleNamespace(returncode=0, stderr=b"")):
            self.beacon.cmd_open_url(self.beacon.argparse.Namespace(dir="/work/repo"))
        # The arg round-trips through Path, which normalizes separators — so
        # compare against the platform's own rendering, not a POSIX literal.
        self.assertEqual(seen["cwd"], str(Path("/work/repo")))

    def test_a_configured_cmd_runs_in_that_directory(self):
        # `git web` and friends already exist on plenty of machines; beacon has
        # no business relitigating where the button should go.
        calls = []

        def fake_run(argv, **kw):
            calls.append((argv, kw.get("cwd")))
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with self._web_button("git web"), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/usr/bin/git"), \
             mock.patch.object(self.beacon.subprocess, "run", fake_run):
            self.beacon.cmd_open_url(self.beacon.argparse.Namespace(dir="/work/repo"))
        self.assertEqual(calls, [(["/usr/bin/git", "web"], str(Path("/work/repo")))])

    def test_a_configured_cmd_takes_precedence_over_beacons_own_resolution(self):
        with self._web_button("git web"), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value="/usr/bin/git"), \
             mock.patch.object(self.beacon, "resolve_url",
                               side_effect=AssertionError("must not resolve")), \
             mock.patch.object(self.beacon.subprocess, "run",
                               lambda a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr="")):
            self.beacon.cmd_open_url(self.beacon.argparse.Namespace(dir="/work/repo"))

    def test_an_unresolvable_cmd_names_the_config_key(self):
        with self._web_button("nope-not-here"), \
             mock.patch.object(self.beacon, "_resolve_editor", return_value=None):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_open_url(self.beacon.argparse.Namespace(dir="/work/repo"))
        self.assertIn("statusbar.buttons.web.cmd", str(cm.exception))


class HybridBranchProfileSlots(unittest.TestCase):
    """STATUS-BAR-03: the profile carries one fixed-color branch component per
    bucket — the default slot plus the three feature-state slots."""

    def test_four_branch_slots_present(self):
        template = (REPO_ROOT / "iterm" / "profile.json.template").read_text(encoding="utf-8")
        for var in ("beacon_branch_default", "beacon_branch_clean",
                    "beacon_branch_diverged", "beacon_branch_untracked"):
            self.assertIn(rf"\\(user.{var})", template)


class BranchIdentity(unittest.TestCase):
    """STATUS-BAR-03 (#20): _detect_branch_info classifies the checked-out
    branch as "default" (origin/HEAD, else main/master/trunk) or "feature" —
    the axis the hybrid branch coloring routes on."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.beacon = _load_beacon(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)
        self.repo = tempfile.TemporaryDirectory()
        self.addCleanup(self.repo.cleanup)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t.co")
        self._git("config", "user.name", "t")
        Path(self.repo.name, "f").write_text("a\n")
        self._git("add", "f")
        self._git("commit", "-qm", "init")
        self._git("update-ref", "refs/remotes/origin/main", "main")
        self._git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    def _git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo.name, check=True,
                       capture_output=True, text=True)

    def test_default_branch_is_default(self):
        *_rest, identity = self.beacon._detect_branch_info(Path(self.repo.name))
        self.assertEqual(identity, "default")

    def test_feature_branch_is_feature(self):
        self._git("checkout", "-q", "-b", "topic")
        *_rest, identity = self.beacon._detect_branch_info(Path(self.repo.name))
        self.assertEqual(identity, "feature")


class SessionAnchor(BeaconTest):
    """HOOK-08 / HOOK-08b: SessionStart persists the navigational anchor
    (`anchor.cwd` / `anchor.project`); Stop re-resolves chips from the
    persisted anchor cwd, not the turn's payload cwd. Without the persisted
    anchor the session's identity is only implicit in Claude's per-hook
    payload — the landmine this guards against."""

    def setUp(self):
        super().setUp()
        self.chip_cwds: list[str] = []
        p = mock.patch.object(
            self.beacon, "_publish_chips",
            # Normalize separators: str(Path("/x")) is "\\x" on Windows, and the
            # fixtures below use POSIX paths. The tests verify anchor logic, not
            # path formatting.
            side_effect=lambda cwd: self.chip_cwds.append(str(cwd).replace("\\", "/")),
        )
        p.start()
        self.addCleanup(p.stop)

    def _fire(self, event: str, payload: dict):
        args = mock.Mock(event=event)
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            self.beacon.cmd_hook(args)

    def test_session_start_persists_anchor(self):
        self._fire("SessionStart", {"cwd": "/work/acme/widget", "source": "startup"})
        self.assertEqual(self.beacon.read_state("anchor.cwd").replace("\\", "/"),
                         "/work/acme/widget")
        # _project_name_at is mocked to "acme/widget" in BeaconTest.
        self.assertEqual(self.beacon.read_state("anchor.project"), "acme/widget")

    def test_stop_resolves_chips_from_anchor_not_payload(self):
        self.beacon.write_state("anchor.cwd", "/anchored/dir")
        self.chip_cwds.clear()
        self._fire("Stop", {"cwd": "/some/other/dir"})
        self.assertEqual(
            self.chip_cwds, ["/anchored/dir"],
            "Stop must resolve chips from the persisted anchor cwd, not the payload cwd",
        )

    def test_stop_falls_back_to_payload_cwd_without_anchor(self):
        self.chip_cwds.clear()
        self._fire("Stop", {"cwd": "/payload/dir"})
        self.assertEqual(self.chip_cwds, ["/payload/dir"])

    def test_session_start_anchors_discovered_icon(self):
        # PROV-08: SessionStart records the discovered project icon path.
        with mock.patch.object(self.beacon, "_discover_icon_at",
                               return_value="/work/acme/widget/docs/favicon.svg"):
            self._fire("SessionStart", {"cwd": "/work/acme/widget", "source": "startup"})
        self.assertEqual(self.beacon.read_state("anchor.icon"),
                         "/work/acme/widget/docs/favicon.svg")

    def test_session_start_clears_stale_icon_anchor(self):
        # A reused pane whose new project ships no icon must not inherit the
        # prior tenant's anchored icon.
        self.beacon.write_state("anchor.icon", "/old/favicon.svg")
        with mock.patch.object(self.beacon, "_discover_icon_at", return_value=None):
            self._fire("SessionStart", {"cwd": "/work/acme/widget", "source": "startup"})
        self.assertIsNone(self.beacon.read_state("anchor.icon"))


class LatestTurn(BeaconTest):
    """WIP-11: latest_turn is auto-derived at hook time from observable events
    — the submitted prompt (human) and the last assistant text (agent) — with
    no agent cooperation, and cleared on a fresh start."""

    def _fire(self, event: str, payload: dict):
        args = mock.Mock(event=event, type=None)
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            self.beacon.cmd_hook(args)

    def _turn(self):
        raw = self.beacon.read_state("latest_turn")
        return json.loads(raw) if raw else None

    def test_user_prompt_records_human_turn(self):
        self._fire("UserPromptSubmit", {"prompt": "fix the flaky test"})
        t = self._turn()
        self.assertEqual(t["role"], "human")
        self.assertEqual(t["text"], "fix the flaky test")
        self.assertIn("at", t)

    def test_stop_records_agent_turn_from_transcript(self):
        with mock.patch.object(self.beacon, "_publish_chips"), \
                mock.patch.object(self.beacon, "_last_assistant_text",
                                  return_value="Done — all green."):
            self._fire("Stop", {})
        t = self._turn()
        self.assertEqual(t["role"], "agent")
        self.assertEqual(t["text"], "Done — all green.")

    def test_empty_turn_leaves_prior_value(self):
        # A pure tool-use turn yields no assistant text; the prior turn stands
        # rather than the signal blanking.
        self._fire("UserPromptSubmit", {"prompt": "go"})
        with mock.patch.object(self.beacon, "_publish_chips"), \
                mock.patch.object(self.beacon, "_last_assistant_text", return_value=None):
            self._fire("Stop", {})
        self.assertEqual(self._turn()["text"], "go")

    def test_synthetic_prompt_leaves_prior_turn(self):
        # Any leading angle-bracket tag is a harness wrapper (a finished
        # background task waking the agent, a system reminder, or a wrapper
        # added later) — not a human turn, so it must not clobber the latest
        # turn with its raw tag; the prior turn stands.
        for wrapper in (
            "<task-notification>\nBackground task done</task-notification>",
            "<system-reminder>some injected note</system-reminder>",
            "<future-harness-tag>whatever</future-harness-tag>",
        ):
            with self.subTest(wrapper=wrapper):
                self._fire("UserPromptSubmit", {"prompt": "deploy the service"})
                self._fire("UserPromptSubmit", {"prompt": wrapper})
                t = self._turn()
                self.assertEqual(t["role"], "human")
                self.assertEqual(t["text"], "deploy the service")

    def test_real_prompt_is_not_treated_as_synthetic(self):
        # The skip must not swallow genuine turns: prose and /slash-commands
        # (which reach the hook as plain "/cmd" text) are real human turns and
        # still register.
        for prompt in ("fix the flaky test", "/commit the changes"):
            with self.subTest(prompt=prompt):
                self._fire("UserPromptSubmit", {"prompt": prompt})
                self.assertEqual(self._turn()["text"], prompt)

    def test_synthetic_prompt_still_resumes_working(self):
        # Skipping the turn write doesn't skip the status flip: the session is
        # resuming work, so the signal goes back to working.
        self._fire("UserPromptSubmit", {"prompt": "<task-notification>done</task-notification>"})
        self.assertEqual(self.beacon.read_state("signal.status"), "working")

    def test_fresh_start_clears_latest_turn(self):
        self.beacon.write_state("latest_turn", json.dumps(
            {"role": "agent", "text": "stale", "at": "x"}))
        with mock.patch.object(self.beacon, "_publish_chips"):
            self._fire("SessionStart", {"cwd": "/work/acme/widget", "source": "startup"})
        self.assertIsNone(self.beacon.read_state("latest_turn"))

    def test_stop_stores_full_turn_alongside_excerpt(self):
        # WIP-14: the full multi-line text is persisted for on-demand fetch,
        # while latest_turn keeps only the single-line excerpt (WIP-11).
        long_turn = "First line of the reply.\nSecond line with detail.\nThird."
        with mock.patch.object(self.beacon, "_publish_chips"), \
                mock.patch.object(self.beacon, "_last_assistant_text",
                                  return_value=long_turn):
            self._fire("Stop", {})
        self.assertEqual(self._turn()["text"], "First line of the reply.")
        self.assertEqual(self.beacon.read_state("latest_turn_full"), long_turn)

    def test_fresh_start_clears_full_turn(self):
        self.beacon.write_state("latest_turn_full", "stale full text")
        with mock.patch.object(self.beacon, "_publish_chips"):
            self._fire("SessionStart", {"cwd": "/work/acme/widget", "source": "startup"})
        self.assertIsNone(self.beacon.read_state("latest_turn_full"))


class ExcerptHelper(BeaconTest):
    """_excerpt: the single-line, payload-bounded turn excerpt (WIP-11).
    Display truncation is the dashboard's job, so this only normalizes text."""

    def test_first_nonempty_line(self):
        self.assertEqual(self.beacon._excerpt("\n\nfirst line\nsecond"), "first line")

    def test_strips_leading_markdown_markers(self):
        self.assertEqual(self.beacon._excerpt("## Heading here"), "Heading here")
        self.assertEqual(self.beacon._excerpt("- a bullet"), "a bullet")
        self.assertEqual(self.beacon._excerpt("> quoted"), "quoted")
        self.assertEqual(self.beacon._excerpt("1. step one"), "step one")

    def test_collapses_whitespace_and_caps_length(self):
        out = self.beacon._excerpt("word  \t " * 100)
        self.assertLessEqual(len(out), self.beacon.TURN_EXCERPT_MAX)
        self.assertNotIn("  ", out)

    def test_empty_for_blank_input(self):
        self.assertEqual(self.beacon._excerpt(""), "")
        self.assertEqual(self.beacon._excerpt(None), "")
        self.assertEqual(self.beacon._excerpt("   \n  "), "")

    def test_last_assistant_text_found_in_large_transcript_tail(self):
        # A transcript larger than the tail window: the newest assistant reply
        # sits at EOF and is still found, proving the bounded tail read.
        tpath = self.data_dir / "transcript.jsonl"
        filler = json.dumps({"type": "user", "message": {"content": "x" * 1000}})
        lines = [filler] * 100  # ~100 KB, exceeds _TRANSCRIPT_TAIL_BYTES
        lines.append(json.dumps({"type": "assistant",
                                 "message": {"content": [{"type": "text", "text": "newest reply"}]}}))
        tpath.write_text("\n".join(lines) + "\n")
        self.beacon.write_state("transcript_path", str(tpath))
        self.assertEqual(self.beacon._last_assistant_text(), "newest reply")


class FullTurnHelper(BeaconTest):
    """_full_turn (WIP-14): the multi-line, generously-bounded companion to the
    single-line _excerpt — line breaks kept, blank runs collapsed, length capped."""

    def test_keeps_line_breaks(self):
        self.assertEqual(self.beacon._full_turn("a\nb\nc"), "a\nb\nc")

    def test_collapses_blank_runs_and_trims(self):
        self.assertEqual(self.beacon._full_turn("\n\nfirst\n\n\nsecond\n\n"),
                         "first\n\nsecond")

    def test_caps_length_with_ellipsis(self):
        out = self.beacon._full_turn("x" * (self.beacon.FULL_TURN_MAX + 500))
        self.assertEqual(len(out), self.beacon.FULL_TURN_MAX)
        self.assertTrue(out.endswith("…"))

    def test_empty_for_blank_input(self):
        self.assertEqual(self.beacon._full_turn(""), "")
        self.assertEqual(self.beacon._full_turn(None), "")
        self.assertEqual(self.beacon._full_turn("   \n  "), "")


class SessionEndDisengages(BeaconTest):
    """HOOK-09: when a session ends, the pane is no longer managed, so the
    plugin disengages (BADGE-14) — blanks the badge user vars, reverts color,
    and removes the engagement marker — instead of leaving a stale badge on the
    pane after the user exits. Reasons that aren't a real exit of this pane
    (`clear`, `resume`) are skipped so the badge survives the handoff."""

    def _fire(self, payload: dict):
        args = mock.Mock(event="SessionEnd")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            self.beacon.cmd_hook(args)

    def _engaged(self) -> bool:
        return self.beacon._engagement_marker_path().exists()

    def test_exit_disengages_the_pane(self):
        self.beacon.render()  # engage: places the marker, paints the badge
        self.assertTrue(self._engaged())
        self.cli_calls.clear()
        self._fire({"reason": "other"})
        self.assertFalse(self._engaged(), "Exit must remove the engagement marker")
        self.assertIn(
            ("uservar", "beacon_project", ""), self.cli_calls,
            "Exit must blank the badge text",
        )
        self.assertIn(("clear",), self.cli_calls, "Exit must revert badge/tab color")
        self.assertIsNone(self.beacon.read_state("resolved"))

    def test_exit_mid_mode_reverts_profile(self):
        # A session that ends while in a mode state (done/retro/release/paused)
        # sits on that mode's profile — the color-only `clear` can't undo its
        # background, so disengage must swap back to base or the pane keeps its
        # "powered off" look after exit.
        self.beacon.apply({**_base_state(), "status": "done"})
        self.assertTrue(self._engaged())
        self.cli_calls.clear()
        self._fire({"reason": "other"})
        self.assertIn(
            ("set-profile", "beacon-dev"), self.cli_calls,
            "Exit mid-mode must swap the pane back to the base beacon-dev profile",
        )

    def test_clear_reason_keeps_engagement(self):
        # `/clear` ends the session with reason=clear but a fresh SessionStart
        # re-engages the same pane immediately — disengaging would just flicker.
        self.beacon.render()
        self.cli_calls.clear()
        self._fire({"reason": "clear"})
        self.assertTrue(self._engaged(), "`clear` reason must not disengage the pane")

    def test_resume_reason_keeps_engagement(self):
        self.beacon.render()
        self.cli_calls.clear()
        self._fire({"reason": "resume"})
        self.assertTrue(self._engaged(), "`resume` reason must not disengage the pane")

    def test_absent_reason_disengages(self):
        # A SessionEnd with no `reason` key collapses to "" via the `or ""`
        # guard, which is not in the skip set — an ambiguous end is treated as
        # a real exit and the pane disengages (the safe direction).
        self.beacon.render()
        self.assertTrue(self._engaged())
        self._fire({})
        self.assertFalse(self._engaged(), "An end with no reason must disengage")


class BadgePinnedToAnchorOnWander(BeaconTest):
    """BADGE-02 / PROV-02a: the badge project follows the SessionStart anchor,
    not Claude's live subprocess cwd. When the agent cd's into a different
    project root mid-turn the project stays pinned, and an @<wandered-project>
    marker surfaces in the task slot as secondary spatial context. The landmine
    this guards
    against: render() re-resolving project from `Path.cwd()` so a mid-turn `cd`
    repaints the badge with the wandered directory."""

    def setUp(self):
        super().setUp()
        # A wander is only recognized when the live cwd resolves to a
        # marker-bearing project root under $HOME (PROV-02a). Mock $HOME to a
        # temp root and create both the anchor and the wandered-into project as
        # real .git repos beneath it, so _project_root finds their markers.
        self._home = tempfile.TemporaryDirectory()
        home = Path(self._home.name).resolve()
        self.addCleanup(self._home.cleanup)
        home_patcher = mock.patch.dict(os.environ, {"HOME": str(home)})
        home_patcher.start()
        self.addCleanup(home_patcher.stop)

        self.anchor_dir = home / "acme-widget"
        self.live_dir = home / "other-project"
        for d in (self.anchor_dir, self.live_dir):
            (d / ".git").mkdir(parents=True)
        self.beacon.write_state("anchor.cwd", str(self.anchor_dir))
        # The @marker is live "where the subprocess is" context, applied only
        # while the session is actively working (busy). These tests exercise the
        # wander overlay, so put the session in the working state.
        self.beacon.write_state("signal.status", "working")

    def _chdir(self, path: Path):
        prev = os.getcwd()
        os.chdir(path)
        self.addCleanup(os.chdir, prev)

    def test_wander_pins_project_and_surfaces_live_cwd_in_task(self):
        self._chdir(self.live_dir)
        self.beacon.render()

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "Project must stay pinned to the anchor when the agent wanders",
        )
        # No override and the live tmp dir is not a git repo, so the location
        # stands alone, joined by the " @ " separator: "<home> @ <where>".
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", f" @ {self.live_dir.name}")],
            "Wandered location must surface in the task slot after the ' @ ' separator",
        )

    def test_no_wander_keeps_normal_task(self):
        self._chdir(self.anchor_dir)
        self.beacon.render()
        # anchor root == live root: task resolves normally (nothing here — the
        # tmp dir is not a git repo), so the slot is never the wander path.
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"), [],
            "No wander: the task slot must not show a cwd path",
        )

    def test_task_override_survives_wander_behind_marker(self):
        self.beacon.write_state("override.task", "my-task")
        self._chdir(self.live_dir)
        self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", f" @ {self.live_dir.name} · my-task")],
            "An override must survive a wander as the task behind the ' · ' after the location",
        )

    def test_scratch_tmp_dir_is_not_a_wander(self):
        # PROV-02a: agents routinely cd into a uniquified scratch dir (a mktemp
        # path under /tmp or $TMPDIR) for ad-hoc work. It has no project marker
        # and lives outside $HOME, so _project_root returns None and no @marker
        # paints — the badge must not churn to @<random-tmp-name>.
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self._chdir(Path(scratch.name).resolve())
        self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"), [],
            "A scratch tmp dir must not trigger the wander @marker",
        )

    def test_subdirectory_of_anchor_is_not_a_wander(self):
        # PROV-02a gates on project *root*: navigating into a subdirectory of the
        # anchored project resolves to the same root, so no wander overlay fires.
        # _project_root's own marker walk only runs under $HOME, so mock it to a
        # fixed root for both operands (find_project_root delegates to it) — the
        # contract under test is the root comparison in the gate, not the marker
        # walk's home boundary.
        with mock.patch.object(self.beacon, "_project_root",
                               side_effect=lambda p: Path("/proj/root")):
            self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"), [],
            "Same project root (subdirectory nav) must not trigger the wander task",
        )

    def test_show_and_badge_share_wander_resolution(self):
        # CMD-01 / BADGE-12: `show` must report what the badge paints. Both go
        # through _resolve_for_display, so a wander reflects identically in both
        # — the badge project stays pinned, the task carries the bare location
        # (the " @ " separator is applied at render, apply()).
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertEqual(state["project"], "acme/widget")
        self.assertEqual(state["task_provider"], "wander")
        self.assertEqual(state["task"], self.live_dir.name)

    def test_wander_clears_at_rest(self):
        # PROV-02a: the marker is live working-state context. At rest (idle here,
        # but the same holds for blocked / paused) the task re-resolves from the
        # anchor and the marker is dropped — even though the live cwd is still
        # away. This is what removes the marker once a session comes home: the
        # returning turn's Stop renders at rest and clears it.
        self.beacon.write_state("signal.status", "idle")
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertNotEqual(
            state["task_provider"], "wander",
            "A session at rest must not carry the @marker, even while away",
        )

    def test_blocked_wander_does_not_freeze_marker(self):
        # The frozen-phantom case: a session that blocks on a prompt while away
        # must not persist an @marker into its snapshot (the fleet view reads it).
        self.beacon.write_state("pending-attention", "permission")
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertNotEqual(state["task_provider"], "wander")

    def test_paused_wander_does_not_freeze_marker(self):
        # `paused` is a distinct precedence branch in _logical_state_for (it
        # short-circuits above pending_attention), reachable only via
        # override.status — so it needs its own assertion that the busy-gate
        # drops the marker, not just the idle/blocked cases above.
        self.beacon.write_state("override.status", "paused")
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertNotEqual(
            state["task_provider"], "wander",
            "A paused session must not carry the @marker, even while away",
        )


class EmptyItermIdIsolatesSessions(BeaconTest):
    """When ITERM_SESSION_ID is unavailable (session launched outside an
    iTerm-integrated shell — auto-spawned tab, `claude --resume`, a non-iTerm
    terminal), session_hash() must still give each Claude session its own state
    bucket. Without isolation every such session collapses onto sha1("default")
    and they cross-wire: the last writer's project/url paints all of them."""

    def setUp(self):
        super().setUp()
        # _publish_anchor → _publish_chips would otherwise shell out to git.
        p = mock.patch.object(self.beacon, "_publish_chips", side_effect=lambda cwd: None)
        p.start()
        self.addCleanup(p.stop)

    def _fire_start_with_empty_id(self, session_id: str, cwd: str):
        # Each real hook is a fresh process whose env carries an empty
        # ITERM_SESSION_ID; reset before every fire to mirror that.
        os.environ["ITERM_SESSION_ID"] = ""
        args = mock.Mock(event="SessionStart")
        payload = {"session_id": session_id, "cwd": cwd, "source": "startup"}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            self.beacon.cmd_hook(args)

    def test_distinct_claude_sessions_do_not_share_bucket(self):
        self._fire_start_with_empty_id("sess-A", "/work/ai-sdlc")
        self._fire_start_with_empty_id("sess-B", "/work/beacon")
        anchors = sorted(
            p.read_text().replace("\\", "/") for p in self.beacon.STATE_DIR.glob("*.anchor.cwd")
        )
        self.assertEqual(
            anchors, ["/work/ai-sdlc", "/work/beacon"],
            "empty ITERM_SESSION_ID must not collapse distinct Claude sessions "
            "onto one shared state bucket",
        )


class SessionSeedFallback(BeaconTest):
    """Without ITERM_SESSION_ID (non-iTerm terminal, any OS — Windows, plain
    Linux), session_hash() seeds from CLAUDE_CODE_SESSION_ID, which Claude Code
    sets in every in-session tool subprocess. That way a bare `beacon set` and
    the hooks that ran alongside it resolve to one bucket instead of colliding
    on the shared "default"."""

    def setUp(self):
        super().setUp()
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("ITERM_SESSION_ID", "CLAUDE_CODE_SESSION_ID")
        }
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_claude_session_id_seeds_hash(self):
        os.environ.pop("ITERM_SESSION_ID", None)
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-X"
        expected = self.beacon.hashlib.sha1(b"claude-session:sess-X").hexdigest()[:16]
        self.assertEqual(self.beacon.session_hash(), expected)

    def test_cli_and_hook_share_bucket(self):
        # The hook fires with an empty ITERM id and synthesizes the session key
        # from the payload's session_id; a later bare CLI call has only
        # CLAUDE_CODE_SESSION_ID in its env. Both must hash to the same bucket.
        os.environ["ITERM_SESSION_ID"] = ""
        os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-Y"
        args = mock.Mock(event="SessionStart")
        payload = {"session_id": "sess-Y", "cwd": "/work/widget", "source": "startup"}
        with mock.patch.object(self.beacon, "_publish_chips", side_effect=lambda cwd: None):
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                self.beacon.cmd_hook(args)
        os.environ.pop("ITERM_SESSION_ID", None)
        cli_bucket = self.beacon.session_hash()
        anchor = self.beacon.STATE_DIR / f"{cli_bucket}.anchor.cwd"
        self.assertTrue(anchor.exists(), "CLI bucket must match the hook's bucket")
        self.assertEqual(anchor.read_text().replace("\\", "/"), "/work/widget")

    def test_tty_name_tolerates_missing_ttyname(self):
        # os.ttyname is absent on Windows; the lookup raises AttributeError.
        # create=True so the patch works on Windows too (where there's no attr
        # to replace) — that's the very platform this guard exists for.
        with mock.patch.object(self.beacon.os, "ttyname", create=True,
                               side_effect=AttributeError):
            self.assertIsNone(self.beacon._tty_name())

    def test_no_ids_falls_back_to_default(self):
        os.environ.pop("ITERM_SESSION_ID", None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        with mock.patch.object(self.beacon, "_tty_name", return_value=None):
            self.assertEqual(
                self.beacon.session_hash(),
                self.beacon.hashlib.sha1(b"default").hexdigest()[:16],
            )


class InstallGating(unittest.TestCase):
    """CMD-08: install always runs the terminal-agnostic steps (wrapper,
    completions) and runs the iTerm2 render-adapter steps only when iTerm2 is
    present. The serve service is opt-in (WIP-07), so install never starts it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.beacon = _load_beacon(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)
        returns = {
            "_install_cli_wrapper": Path("/tmp/beacon"),
            "_install_completions": None,
            "_install_shell_source": None,
            "_service_install": True,
            "install_dynamic_profile": (True, "profile written"),
        }
        self.mocks = {}
        for name, val in returns.items():
            p = mock.patch.object(self.beacon, name, return_value=val)
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)

    def _run_install(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.beacon.cmd_install(None)
        return buf.getvalue()

    _ITERM_STEPS = ("_install_shell_source", "install_dynamic_profile")
    _ALWAYS_STEPS = ("_install_cli_wrapper", "_install_completions")

    def test_dashboard_only_skips_iterm_steps(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            out = self._run_install()
        for name in self._ALWAYS_STEPS:
            self.assertTrue(self.mocks[name].called, f"{name} should run")
        for name in self._ITERM_STEPS:
            self.assertFalse(self.mocks[name].called, f"{name} should be skipped")
        self.assertFalse(self.mocks["_service_install"].called,
                         "the serve service is opt-in; install must not start it")
        self.assertIn("[1/3]", out)
        self.assertIn("[3/3]", out)  # includes the status-line advisory step
        self.assertIn("beacon wip", out)
        self.assertIn("beacon serve install", out)

    def test_full_runs_every_step(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True):
            out = self._run_install()
        for name in (*self._ALWAYS_STEPS, *self._ITERM_STEPS):
            self.assertTrue(self.mocks[name].called, f"{name} should run")
        self.assertFalse(self.mocks["_service_install"].called,
                         "the serve service is opt-in; install must not start it")
        self.assertIn("[6/6]", out)

    def test_install_completes_in_place(self):
        # 1.0 pivot: no pref needs iTerm2 quit, so install emits no
        # deferred-action notice.
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True):
            out = self._run_install()
        self.assertIn("no iTerm2 restart required", out)
        self.assertNotIn("DEFERRED", out)


@unittest.skipIf(sys.platform == "win32", "launchd/systemd service is POSIX-only")
class ServiceUnit(unittest.TestCase):
    """WIP-07: `serve install` writes a supervised unit that runs `serve` via
    the stable wrapper, restart-on-failure; `serve uninstall` removes it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.beacon = _load_beacon(self.tmp)
        self.addCleanup(self._tmp.cleanup)

    def _wrapper_file(self) -> Path:
        w = self.tmp / "beacon"
        w.write_text("#!/bin/sh\n")
        return w

    @staticmethod
    def _ok():
        return subprocess.CompletedProcess([], 0, "", "")

    @staticmethod
    def _fail(stderr="boom"):
        return subprocess.CompletedProcess([], 1, "", stderr)

    def test_wrapper_path_is_stable_local_bin(self):
        # The unit must point at the upgrade-stable wrapper, not a version-pinned
        # script path, so a plugin upgrade keeps the service working.
        self.assertTrue(str(self.beacon._wrapper_path()).endswith("/.local/bin/beacon"))

    def test_render_launchd_embeds_wrapper_keepalive_and_port(self):
        out = self.beacon._render_launchd_plist(Path("/x/beacon"), 1234, Path("/o"), Path("/e"))
        self.assertIn("<key>KeepAlive</key>", out)
        self.assertIn("<string>/x/beacon</string>", out)
        self.assertIn("<string>serve</string>", out)
        self.assertIn("<string>1234</string>", out)

    def test_render_systemd_embeds_wrapper_restart_and_port(self):
        out = self.beacon._render_systemd_unit(Path("/x/beacon"), 1234)
        self.assertIn("Restart=always", out)
        self.assertIn("ExecStart=/x/beacon serve --port 1234", out)
        self.assertIn("WantedBy=default.target", out)

    def test_install_launchd_writes_and_loads_idempotently(self):
        wrapper = self._wrapper_file()
        plist = self.tmp / "agent.plist"
        with mock.patch.object(self.beacon, "_wrapper_path", return_value=wrapper), \
             mock.patch.object(self.beacon, "_launchd_plist_path", return_value=plist), \
             mock.patch.object(self.beacon, "_launchctl", return_value=self._ok()), \
             mock.patch("sys.platform", "darwin"):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(self.beacon._service_install(8800))
                self.assertTrue(self.beacon._service_install(8800))  # idempotent
        content = plist.read_text()
        self.assertIn(str(wrapper), content)
        self.assertIn("8800", content)

    def test_install_systemd_writes_and_enables(self):
        wrapper = self._wrapper_file()
        unit = self.tmp / "beacon-serve.service"
        with mock.patch.object(self.beacon, "_wrapper_path", return_value=wrapper), \
             mock.patch.object(self.beacon, "_systemd_unit_path", return_value=unit), \
             mock.patch.object(self.beacon, "_systemctl", return_value=self._ok()), \
             mock.patch("sys.platform", "linux"):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(self.beacon._service_install(8800))
        self.assertIn("Restart=always", unit.read_text())
        self.assertIn("--port 8800", unit.read_text())

    def test_install_without_wrapper_fails(self):
        with mock.patch.object(self.beacon, "_wrapper_path",
                               return_value=self.tmp / "absent"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertFalse(self.beacon._service_install(8800))
        self.assertIn("install-cli", buf.getvalue())

    def test_uninstall_launchd_removes_unit(self):
        plist = self.tmp / "agent.plist"
        plist.write_text("x")
        with mock.patch.object(self.beacon, "_launchd_plist_path", return_value=plist), \
             mock.patch.object(self.beacon, "_launchctl", return_value=self._ok()), \
             mock.patch("sys.platform", "darwin"):
            with contextlib.redirect_stdout(io.StringIO()):
                self.beacon._service_uninstall()
        self.assertFalse(plist.exists())

    def test_run_supervisor_turns_missing_binary_into_nonzero(self):
        # A missing launchctl/systemctl must surface as r.stderr (a `! ...`
        # line), not an uncaught FileNotFoundError traceback.
        with mock.patch.object(self.beacon.subprocess, "run",
                               side_effect=FileNotFoundError("no launchctl")):
            r = self.beacon._launchctl("list")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no launchctl", r.stderr)

    def test_supervisor_is_none_when_systemctl_absent(self):
        with mock.patch("sys.platform", "linux"), \
             mock.patch.object(self.beacon, "_systemctl", return_value=self._fail()):
            self.assertEqual(self.beacon._service_supervisor(), "none")

    def test_supervisor_is_systemd_when_systemctl_present(self):
        with mock.patch("sys.platform", "linux"), \
             mock.patch.object(self.beacon, "_systemctl", return_value=self._ok()):
            self.assertEqual(self.beacon._service_supervisor(), "systemd")

    def test_install_launchd_failure_surfaces_bootstrap_error(self):
        wrapper = self._wrapper_file()
        plist = self.tmp / "agent.plist"
        # bootout, bootstrap, and the legacy load retry all fail; the bootstrap
        # diagnostic must be the one surfaced, not the (empty) load retry.
        calls = {"bootstrap": self._fail("Bootstrap failed: 5"), "load": self._fail("")}
        def launchctl(*a):
            return calls.get(a[0], self._fail(""))
        with mock.patch.object(self.beacon, "_wrapper_path", return_value=wrapper), \
             mock.patch.object(self.beacon, "_launchd_plist_path", return_value=plist), \
             mock.patch.object(self.beacon, "_launchctl", side_effect=launchctl), \
             mock.patch("sys.platform", "darwin"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = self.beacon._service_install(8800)
        self.assertFalse(ok)
        self.assertIn("Bootstrap failed: 5", buf.getvalue())

    def test_install_systemd_failure_returns_false(self):
        wrapper = self._wrapper_file()
        unit = self.tmp / "beacon-serve.service"
        with mock.patch.object(self.beacon, "_wrapper_path", return_value=wrapper), \
             mock.patch.object(self.beacon, "_systemd_unit_path", return_value=unit), \
             mock.patch.object(self.beacon, "_service_supervisor", return_value="systemd"), \
             mock.patch.object(self.beacon, "_systemctl", return_value=self._fail("enable failed")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = self.beacon._service_install(8800)
        self.assertFalse(ok)
        self.assertIn("enable failed", buf.getvalue())

    def test_uninstall_launchd_failure_returns_false(self):
        plist = self.tmp / "agent.plist"
        plist.write_text("x")
        with mock.patch.object(self.beacon, "_launchd_plist_path", return_value=plist), \
             mock.patch.object(self.beacon, "_launchctl", return_value=self._fail("wedged")), \
             mock.patch("sys.platform", "darwin"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = self.beacon._service_uninstall()
        self.assertFalse(ok)
        self.assertFalse(plist.exists())  # file still removed
        self.assertIn("wedged", buf.getvalue())

    def test_uninstall_systemd_removes_unit(self):
        unit = self.tmp / "beacon-serve.service"
        unit.write_text("x")
        with mock.patch.object(self.beacon, "_systemd_unit_path", return_value=unit), \
             mock.patch.object(self.beacon, "_systemctl", return_value=self._ok()), \
             mock.patch("sys.platform", "linux"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = self.beacon._service_uninstall()
        self.assertTrue(ok)
        self.assertFalse(unit.exists())

    def test_is_iterm_installed_false_off_darwin(self):
        with mock.patch("sys.platform", "linux"):
            self.assertFalse(self.beacon._is_iterm_installed())


class TaskChainCcSignals(BeaconTest):
    """PROV-02: the task chain is override → PR → branch → ai-title. A /rename
    is not its own tier — the harvest folds it into `override.task` (see
    ReadCcSignals), so it competes as an override. ai-title is the weakest
    fallback, below branch."""

    def test_override_beats_pr_and_branch(self):
        # The tier a harvested /rename lands in: an explicit task (whether from
        # `beacon set task` or a /rename) wins over the derived PR/branch tiers.
        self.beacon.write_state("override.task", "find me")
        with mock.patch.object(self.beacon, "p_pr_title", return_value="a PR"), \
             mock.patch.object(self.beacon, "p_branch", return_value="a-branch"):
            state = self.beacon.resolve(Path("/tmp"))
        self.assertEqual(state["task"], "find me")
        self.assertEqual(state["task_provider"], "override")

    def test_branch_beats_ai_title(self):
        self.beacon.write_state("cc.ai_title", "Auto summary")
        with mock.patch.object(self.beacon, "p_pr_title", return_value=None), \
             mock.patch.object(self.beacon, "p_branch", return_value="feature-x"):
            state = self.beacon.resolve(Path("/tmp"))
        self.assertEqual(state["task"], "feature-x")
        self.assertEqual(state["task_provider"], "branch")

    def test_ai_title_is_last_resort(self):
        self.beacon.write_state("cc.ai_title", "Auto summary")
        with mock.patch.object(self.beacon, "p_pr_title", return_value=None), \
             mock.patch.object(self.beacon, "p_branch", return_value=None):
            state = self.beacon.resolve(Path("/tmp"))
        self.assertEqual(state["task"], "Auto summary")
        self.assertEqual(state["task_provider"], "ai-title")


class ReadCcSignals(BeaconTest):
    """Harvesting /color, /rename, ai-title from the transcript tail."""

    def _write_transcript(self, records):
        p = self.data_dir / "transcript.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        self.beacon.write_state("transcript_path", str(p))
        return p

    def test_harvests_latest_of_each_type(self):
        self._write_transcript([
            {"type": "agent-color", "agentColor": "blue"},
            {"type": "custom-title", "customTitle": "old name"},
            {"type": "agent-color", "agentColor": "pink"},
            {"type": "custom-title", "customTitle": "find me"},
            {"type": "ai-title", "aiTitle": "Auto summary"},
        ])
        self.beacon._read_cc_signals()
        self.assertEqual(self.beacon.read_state("cc.agent_color"), "pink")
        self.assertEqual(self.beacon.read_state("cc.custom_title"), "find me")
        self.assertEqual(self.beacon.read_state("cc.ai_title"), "Auto summary")

    def test_absent_type_keeps_prior_value(self):
        self.beacon.write_state("cc.custom_title", "kept")
        self._write_transcript([{"type": "agent-color", "agentColor": "red"}])
        self.beacon._read_cc_signals()
        self.assertEqual(self.beacon.read_state("cc.custom_title"), "kept",
                         "A type missing from the tail must not blank its prior value")
        self.assertEqual(self.beacon.read_state("cc.agent_color"), "red")

    def test_new_custom_title_folds_into_task_override(self):
        # PROV-02: a /rename is shorthand for `beacon set task`, so a changed
        # custom-title lands in override.task and thus wins the chain.
        self._write_transcript([{"type": "custom-title", "customTitle": "renamed"}])
        self.beacon._read_cc_signals()
        self.assertEqual(self.beacon.read_state("override.task"), "renamed")

    def test_unchanged_custom_title_does_not_clobber_task(self):
        # Recency-wins: a later `beacon set task` must survive the next harvest.
        # The custom-title is unchanged from the last harvest, so the fold is a
        # no-op and the fresher agent label stands.
        self.beacon.write_state("cc.custom_title", "renamed")
        self.beacon.write_state("override.task", "agent label")
        self._write_transcript([{"type": "custom-title", "customTitle": "renamed"}])
        self.beacon._read_cc_signals()
        self.assertEqual(self.beacon.read_state("override.task"), "agent label")

    def test_absent_custom_title_leaves_task_untouched(self):
        self.beacon.write_state("override.task", "agent label")
        self._write_transcript([{"type": "agent-color", "agentColor": "red"}])
        self.beacon._read_cc_signals()
        self.assertEqual(self.beacon.read_state("override.task"), "agent label")

    def test_no_transcript_is_noop(self):
        self.beacon._read_cc_signals()
        self.assertIsNone(self.beacon.read_state("cc.custom_title"))

    def test_fresh_start_wipes_cc_signals(self):
        for f in ("cc.custom_title", "cc.agent_color", "cc.ai_title"):
            self.beacon.write_state(f, "x")
        self.beacon._wipe_session_for_fresh_start()
        for f in ("cc.custom_title", "cc.agent_color", "cc.ai_title"):
            self.assertIsNone(self.beacon.read_state(f))


class FleetPayloadColor(BeaconTest):
    """The /color signal is fleet-view metadata exposed in the wip payload."""

    def _seed_session(self):
        sh = self.beacon.session_hash()
        self.beacon.write_state("anchor.project", "acme/widget")
        self.beacon.write_state("anchor.cwd", "/tmp/x")
        return sh

    def test_agent_color_in_payload(self):
        sh = self._seed_session()
        self.beacon.write_state("cc.agent_color", "pink")
        row = self.beacon._resolve_session(sh, compute_branch=False)
        self.assertEqual(row["agent_color"], "pink")

    def test_no_color_is_none(self):
        sh = self._seed_session()
        row = self.beacon._resolve_session(sh, compute_branch=False)
        self.assertIsNone(row["agent_color"])


class PauseClearScreen(BeaconTest):
    """#8: `pause --clear-screen` sets status=paused AND drives the CLI's
    clear-screen; without the flag it must not clear."""

    def test_clear_screen_flag_invokes_cli(self):
        args = self.beacon.argparse.Namespace(note=[], clear_screen=True)
        self.beacon.cmd_pause(args)
        self.assertIn(("clear-screen",), self.cli_calls)
        self.assertEqual(self.beacon.read_state("override.status"), "paused")

    def test_without_flag_does_not_clear(self):
        args = self.beacon.argparse.Namespace(note=[], clear_screen=False)
        self.beacon.cmd_pause(args)
        self.assertNotIn(("clear-screen",), self.cli_calls)
        self.assertEqual(self.beacon.read_state("override.status"), "paused")


class StatusLineProvider(BeaconTest):
    """STATUSLINE-01: the Claude Code status-line provider (the footer row Claude
    owns, no terminal overlap) prints the pause reason and the resolved URL as an
    OSC-8 link — empty otherwise, since project/task/status are carried by the
    tab."""

    def _run(self):
        buf = io.StringIO()
        with mock.patch.object(self.beacon.sys, "stdin", io.StringIO('{"cwd":"/x"}')), \
             contextlib.redirect_stdout(buf):
            self.beacon.cmd_statusline(self.beacon.argparse.Namespace())
        return buf.getvalue()

    def test_paused_with_reason_prints_glyph_and_reason(self):
        self.beacon.write_state("override.status", "paused")
        self.beacon.write_state("description", "waiting on CI")
        out = self._run()
        self.assertIn("waiting on CI", out)
        self.assertIn(self.beacon.PAUSED_TITLE_GLYPH.strip(), out)  # ⏸
        self.assertIn("\033[", out)  # ANSI color

    def test_not_paused_prints_nothing(self):
        self.beacon.write_state("override.status", "working")
        self.beacon.write_state("description", "waiting on CI")
        self.assertEqual(self._run(), "")

    def test_paused_without_reason_prints_nothing(self):
        self.beacon.write_state("override.status", "paused")
        self.assertEqual(self._run(), "")

    def test_multiline_reason_collapsed_to_one_line(self):
        self.beacon.write_state("override.status", "paused")
        self.beacon.write_state("description", "line one\nline two")
        out = self._run()
        self.assertIn("line one line two", out)
        self.assertEqual(out.count("\n"), 1)  # only the trailing newline

    def test_resolved_url_renders_as_osc8_link(self):
        url = "https://github.com/acme/widgets/pull/42"
        self.beacon.write_state("resolved.url", url)
        self.beacon.write_state("resolved.url_label", "acme/widgets#42")
        out = self._run()
        # The full OSC-8 wrapper, not just the label: the label alone would pass
        # even if the sequence were dropped, which is the whole feature.
        self.assertIn(f"\033]8;;{url}\a", out)
        self.assertIn("acme/widgets#42", out)
        self.assertIn("\033]8;;\a", out)
        # The bare URL never appears as text — the label is the click target.
        self.assertNotIn(f" {url} ", out)

    def test_no_resolved_url_prints_nothing(self):
        self.assertEqual(self._run(), "")

    def test_url_falls_back_to_itself_when_unlabelled(self):
        url = "https://github.com/acme/widgets"
        self.beacon.write_state("resolved.url", url)
        self.assertIn(f"\033]8;;{url}\a{url}\033]8;;\a", self._run())

    def _visible(self, row):
        """Strip OSC-8 wrappers and SGR so assertions read like the rendered row."""
        return re.sub(r"\x1b\]8;;[^\a]*\a|\x1b\[[0-9;]*m", "", row).rstrip("\n")

    def _touch(self, ref, url, project, title="", landed=()):
        # tack IS on PATH on a dev machine, so an unmocked _record_deliverable
        # shells out and reads the author's real routes — slow and dependent on
        # state no test controls. `landed` stands in for the URLs whose tack has
        # gone done.
        with mock.patch.object(self.beacon, "_tack_landed_urls",
                               return_value=set(landed)):
            self.beacon._record_deliverable(ref, url, project, title)


    def _lines(self):
        return self._visible(self._run()).split("\n")

    def test_open_work_splits_by_kind_crs_above_issues(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("!3", "https://x.test/w/-/merge_requests/3", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        self._touch("#75", "https://x.test/o/issues/75", "gh:other/otherproj")
        # CRs lead; issues follow, newest first. Bare for this project,
        # qualified for another.
        self.assertEqual(self._lines(), ["!3", "otherproj:#75 · #4"])

    def test_each_deliverable_is_its_own_link(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        self._touch("#75", "https://x.test/o/issues/75", "gh:other/otherproj")
        out = self._run()
        self.assertIn("\033]8;;https://x.test/w/issues/4\a#4", out)
        self.assertIn("\033]8;;https://x.test/o/issues/75\aotherproj:#75", out)

    def test_crs_carry_more_weight_than_issues(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#9", "https://x.test/w/pull/9", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        out = self._run()
        # Same hue, two weights — a CR reads as the actionable thing, the issue
        # as its context. On GitHub both render `#<n>`, so weight is the cue.
        self.assertIn(f"\033[{self.beacon.STATUSLINE_CR_SGR}m"
                      "\033]8;;https://x.test/w/pull/9\a#9", out)
        self.assertIn(f"\033[{self.beacon.STATUSLINE_ISSUE_SGR}m"
                      "\033]8;;https://x.test/w/issues/4\a#4", out)

    def test_retouch_moves_to_the_front_without_duplicating(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        self._touch("#9", "https://x.test/w/issues/9", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        self.assertEqual(self._lines(), ["#4 · #9"])

    def test_items_on_a_line_share_one_separator(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        for n in (4, 5, 6):
            self._touch(f"#{n}", f"https://x.test/w/issues/{n}", "gh:acme/widgets")
        line = self._lines()[0]
        self.assertEqual(line, "#6 · #5 · #4")
        self.assertNotIn(",", line)

    def test_delivered_work_leads_on_its_own_line(self):
        url = "https://x.test/w/pull/9"
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        self._touch("#9", url, "gh:acme/widgets", landed=[url])
        self.assertEqual(self._lines(), ["#9 merged 🏁", "#4"])

    def test_delivered_ref_is_struck_but_the_verb_carries_it(self):
        url = "https://x.test/w/pull/9"
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#9", url, "gh:acme/widgets", landed=[url])
        out = self._run()
        # Strike wraps the ref text only — a four-character strike is too subtle
        # to be the signal, so the word and glyph outside it do the work.
        self.assertIn("\a\033[9m#9\033[29m\033]8;;\a", out)
        self.assertIn("merged 🏁", out)

    def test_a_release_is_delivered_without_asking_tack(self):
        # A /releases/tag/ URL only exists once published, so the kind settles
        # it — no tack route required.
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("v2.0.0", "https://x.test/w/releases/tag/v2.0.0", "gh:acme/widgets")
        self.assertEqual(self._lines(), ["v2.0.0 released 🚀"])

    def test_a_cr_carries_a_title(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#9", "https://x.test/w/pull/9", "gh:acme/widgets",
                    title="Rework the cart drawer")
        self.assertEqual(self._lines(), ["#9 Rework the cart drawer"])

    def test_issues_stay_bare(self):
        # Several issues share a line; titling each would wrap the row the cap
        # exists to prevent.
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets",
                    title="Some issue summary")
        self.assertEqual(self._lines(), ["#4"])

    def test_a_long_title_is_ellipsized(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#9", "https://x.test/w/pull/9", "gh:acme/widgets", title="x" * 200)
        title = self._lines()[0].split(" ", 1)[1]
        self.assertEqual(len(title), self.beacon.STATUSLINE_TITLE_MAX)
        self.assertTrue(title.endswith("…"))

    def test_a_title_survives_a_later_touch_that_has_none(self):
        # Only the current deliverable has a live task to read; an older CR must
        # keep the title it was captured with rather than being blanked.
        url = "https://x.test/w/pull/9"
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#9", url, "gh:acme/widgets", title="Rework the cart drawer")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        self.assertEqual(self._lines()[0], "#9 Rework the cart drawer")

    def test_a_delivered_cr_drops_its_title(self):
        # The delivered line is a ledger, not a worklist — the verb is the point.
        url = "https://x.test/w/pull/9"
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#9", url, "gh:acme/widgets",
                    title="Rework the cart drawer", landed=[url])
        self.assertEqual(self._lines(), ["#9 merged 🏁"])

    def test_oldest_drops_past_the_cap(self):
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        for n in range(self.beacon.DELIVERABLES_MAX + 3):
            self._touch(f"#{n}", f"https://x.test/w/issues/{n}", "gh:acme/widgets")
        entries = self.beacon.read_state_json("deliverables", [])
        self.assertEqual(len(entries), self.beacon.DELIVERABLES_MAX)
        self.assertEqual(entries[0]["ref"], "#3")   # #0..#2 aged out
        self.assertEqual(entries[-1]["ref"], f"#{self.beacon.DELIVERABLES_MAX + 2}")

    def test_deliverables_supersede_the_single_url(self):
        # A branch-tree URL resolves while the session has already touched a
        # deliverable — the accumulated work is the more useful answer.
        self.beacon.write_state("resolved.url", "https://x.test/w/tree/main")
        self.beacon.write_state("resolved.url_label", "acme/widgets")
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#4", "https://x.test/w/issues/4", "gh:acme/widgets")
        self.assertEqual(self._visible(self._run()), "#4")

    def test_pause_reason_and_link_share_one_row(self):
        self.beacon.write_state("override.status", "paused")
        self.beacon.write_state("description", "waiting on CI")
        self.beacon.write_state("resolved.url", "https://example.test/1")
        self.beacon.write_state("resolved.url_label", "ex#1")
        out = self._run()
        self.assertIn("waiting on CI", out)
        self.assertIn("ex#1", out)
        self.assertIn(self.beacon.STATUSLINE_SEPARATOR, out)
        self.assertEqual(out.count("\n"), 1)
        # Reason leads: it answers "why is this parked" before "where is it".
        self.assertLess(out.index("waiting on CI"), out.index("ex#1"))


class StatusBarLayout(unittest.TestCase):
    """STATUS-BAR-02: the strip is `↖ web · project ←spring→ branch ↗ code`.
    Each edge pairs an action with the data it acts on; the review chip was
    dropped for lack of use, and with nothing centred one spring suffices."""

    def _layout(self):
        return _render_profile_template()["Status Bar Layout"]["components"]

    def _action_titles(self):
        return [c["configuration"]["knobs"]["action"]["title"]
                for c in self._layout()
                if c["class"] == "iTermStatusBarActionComponent"]

    def test_the_two_action_chips_bookend_the_strip(self):
        self.assertEqual(self._action_titles(), ["↖ web", "↗ code"])

    def test_the_spring_sits_behind_web_leaving_one_right_hand_cluster(self):
        # `↖ web` alone at the left edge; the spring then pushes project, its
        # branch, and `↗ code` together on the right, so the identity sits
        # beside the branch it belongs to rather than across the strip from it.
        comps = self._layout()
        classes = [c["class"] for c in comps]
        self.assertEqual(classes.count("iTermStatusBarSpringComponent"), 1)
        self.assertEqual(comps[0]["configuration"]["knobs"]["action"]["title"], "↖ web")
        self.assertEqual(classes.index("iTermStatusBarSpringComponent"), 1)
        self.assertEqual(
            comps[2]["configuration"]["knobs"]["expression"],
            r"\(user.beacon_project_full)")
        self.assertEqual(comps[-1]["configuration"]["knobs"]["action"]["title"], "↗ code")

    def test_review_chip_is_gone(self):
        template = (REPO_ROOT / "iterm" / "profile.json.template").read_text(encoding="utf-8")
        self.assertNotIn("⇄ review", template)
        self.assertNotIn("beacon review", template)


class ReviewFeatureRemoved(BeaconTest):
    """CMD-16 retired: the branch-review subcommand goes with its chip. Reviewing
    a diff is a job other tools own; beacon's is reporting session state."""

    def test_review_is_not_a_subcommand(self):
        with self.assertRaises(SystemExit):
            self.beacon._build_parser().parse_args(["review"])

    def test_review_entry_points_are_gone(self):
        for name in ("cmd_review", "_anchor_review_script", "_working_tree_dirty"):
            self.assertFalse(hasattr(self.beacon, name), f"{name} should be removed")

    def test_completions_do_not_offer_review(self):
        self.assertNotIn("'review:", self.beacon.ZSH_COMPLETION)


class ExportImport(BeaconTest):
    """DUMP-01..DUMP-03: lossless backup/restore of the state-file directory."""

    def _seed(self):
        sd = self.beacon.STATE_DIR
        sd.mkdir(parents=True, exist_ok=True)
        h1, h2 = "aaaa11112222", "bbbb33334444"
        (sd / f"{h1}.anchor.project").write_text("widget")
        (sd / f"{h1}.claude_session_id").write_text("sid-one\n")
        # Non-ASCII on purpose: catches any read/write that skips encoding="utf-8"
        # (cp1252 on Windows would corrupt these glyphs and break the round-trip).
        (sd / f"{h1}.latest_turn").write_text(json.dumps(
            {"role": "agent", "text": "⇄ pushed 🚀", "at": "2026-07-07T00:00:00+00:00"}))
        (sd / f"{h1}.pending-attention").write_text("")  # empty marker must survive
        (sd / f"{h2}.anchor.project").write_text("gadget")
        old = 1_600_000_000.0
        for p in sd.glob(f"{h1}.*"):
            os.utime(p, (old, old))
        return h1, h2, old

    def _args(self, **kw):
        return self.beacon.argparse.Namespace(**kw)

    def test_export_envelope_surfaces_join_key_and_raw_fields(self):
        h1, h2, _ = self._seed()
        out = Path(self._tmp.name) / "dump.json"
        self.beacon.cmd_export(self._args(out_file=str(out), compress=False))
        d = json.loads(out.read_text())
        self.assertEqual(d["schemaVersion"], 1)
        self.assertTrue(d["generator"].startswith("beacon "))
        byhash = {s["hash"]: s for s in d["sessions"]}
        self.assertIn(h1, byhash)
        self.assertIn(h2, byhash)
        # claude_session_id is surfaced per record — the tack-export join key.
        self.assertEqual(byhash[h1]["claude_session_id"], "sid-one")
        # Raw field text is preserved verbatim, including the empty attention marker.
        self.assertEqual(byhash[h1]["fields"]["pending-attention"], "")
        self.assertEqual(byhash[h1]["fields"]["anchor.project"], "widget")

    def test_roundtrip_restores_bytes_and_mtime(self):
        h1, h2, old = self._seed()
        sd = self.beacon.STATE_DIR
        before = {p.name: p.read_text() for p in sd.glob(f"{h1}.*")}
        out = Path(self._tmp.name) / "dump.json.gz"  # .gz suffix triggers gzip
        self.beacon.cmd_export(self._args(out_file=str(out), compress=False))
        for p in list(sd.glob(f"{h1}.*")) + list(sd.glob(f"{h2}.*")):
            p.unlink()
        self.beacon.cmd_import(self._args(file=str(out), force=False))
        after = {p.name: p.read_text() for p in sd.glob(f"{h1}.*")}
        self.assertEqual(before, after)
        newest = max(os.stat(p).st_mtime for p in sd.glob(f"{h1}.*"))
        self.assertAlmostEqual(newest, old, delta=1)

    def test_import_is_nondestructive_until_force(self):
        h1, _, _ = self._seed()
        sd = self.beacon.STATE_DIR
        out = Path(self._tmp.name) / "dump.json"
        self.beacon.cmd_export(self._args(out_file=str(out), compress=False))
        (sd / f"{h1}.anchor.project").write_text("MUTATED")
        self.beacon.cmd_import(self._args(file=str(out), force=False))
        self.assertEqual((sd / f"{h1}.anchor.project").read_text(), "MUTATED")
        self.beacon.cmd_import(self._args(file=str(out), force=True))
        self.assertEqual((sd / f"{h1}.anchor.project").read_text(), "widget")

    def test_import_refuses_unknown_schema_version(self):
        out = Path(self._tmp.name) / "bad.json"
        out.write_text(json.dumps({"schemaVersion": 999, "sessions": []}))
        with self.assertRaises(SystemExit):
            self.beacon.cmd_import(self._args(file=str(out), force=False))

    def test_import_rejects_path_traversal_field(self):
        sd = self.beacon.STATE_DIR
        sd.mkdir(parents=True, exist_ok=True)
        out = Path(self._tmp.name) / "evil.json"
        out.write_text(json.dumps({"schemaVersion": 1, "sessions": [
            {"hash": "deadbeef1234", "mtime": None, "fields": {"../../pwned": "x"}},
        ]}))
        self.beacon.cmd_import(self._args(file=str(out), force=False))
        self.assertFalse((Path(self._tmp.name) / "pwned").exists())
        self.assertEqual(list(sd.glob("deadbeef1234.*")), [])


class CompletionsMatchSubcommands(BeaconTest):
    """CI guard: the zsh completion command list must cover every subcommand the
    argparse parser accepts, minus the intentionally-hidden internal ones. Fails
    on drift in either direction — a new command that skipped ZSH_COMPLETION, or
    a completion entry for a command that no longer exists."""

    def test_no_completion_drift(self):
        b = self.beacon
        sub = next(a for a in b._build_parser()._actions
                   if isinstance(a, b.argparse._SubParsersAction))
        parser_cmds = set(sub.choices)

        # Anchor on the array's closing `)` — alone on its own line — so a
        # literal `)` inside a description (e.g. "(project|task|status)") can't
        # truncate the block.
        block = b.re.search(r"commands=\((.*?)^\s*\)",
                            b.ZSH_COMPLETION, b.re.S | b.re.M).group(1)
        completion_cmds = set(b.re.findall(r"'([a-z][a-z-]*):", block))

        expected = parser_cmds - b._UNCOMPLETED_COMMANDS
        self.assertEqual(
            completion_cmds, expected,
            f"completion drift — missing from ZSH_COMPLETION: "
            f"{sorted(expected - completion_cmds)}; "
            f"stale (no such subcommand): {sorted(completion_cmds - expected)}",
        )

    def test_hidden_commands_are_real_subcommands(self):
        b = self.beacon
        sub = next(a for a in b._build_parser()._actions
                   if isinstance(a, b.argparse._SubParsersAction))
        self.assertLessEqual(b._UNCOMPLETED_COMMANDS, set(sub.choices))


def _load_beacon_iterm():
    path = REPO_ROOT / "bin" / "beacon-iterm"
    sys.modules.pop("beacon_iterm", None)
    loader = importlib.machinery.SourceFileLoader("beacon_iterm", str(path))
    spec = importlib.util.spec_from_loader("beacon_iterm", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ConfigureLayoutAudit(unittest.TestCase):
    """`beacon-iterm configure` audits app-wide iTerm2 layout prefs read-only:
    reports drift, exits non-zero on it, and issues no `defaults write`."""

    def setUp(self):
        self.iterm = _load_beacon_iterm()

    def _run(self, values, record=None):
        def fake_run(cmd, *a, **k):
            if record is not None:
                record.append(cmd)
            key = cmd[-1]
            if key in values:
                return subprocess.CompletedProcess(cmd, 0, stdout=values[key] + "\n", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="does not exist")
        buf = io.StringIO()
        with mock.patch.object(self.iterm.subprocess, "run", side_effect=fake_run), \
                contextlib.redirect_stdout(buf), \
                self.assertRaises(SystemExit) as cm:
            self.iterm.cmd_configure(types.SimpleNamespace(write=False, yes=False, keys=None))
        return cm.exception.code, buf.getvalue()

    def _aligned(self):
        return {s["key"]: s["want"] for s in self.iterm.RECOMMENDED_LAYOUT}

    def test_all_aligned_exits_zero(self):
        code, out = self._run(self._aligned())
        self.assertEqual(code, 0)
        self.assertIn("All aligned", out)

    def test_drift_exits_nonzero_and_names_setting(self):
        vals = self._aligned()
        del vals["StatusBarPosition"]
        code, out = self._run(vals)
        self.assertEqual(code, 1)
        self.assertIn("StatusBarPosition", out)
        self.assertIn("1 of", out)

    def test_never_writes_a_pref(self):
        record = []
        self._run(self._aligned(), record=record)
        self.assertTrue(record)
        for cmd in record:
            self.assertEqual(cmd[:2], ["defaults", "read"],
                             f"configure must only read, never write: {cmd}")


class ConfigureLayoutWrite(unittest.TestCase):
    """`configure --write` applies the layout without the Preferences GUI: it
    writes typed defaults only while iTerm2 is down, and when iTerm2 is up it
    hands off to a detached helper + quit rather than writing in-process (a
    running-iTerm2 write is clobbered on quit)."""

    def setUp(self):
        self.iterm = _load_beacon_iterm()

    def _args(self, **kw):
        return types.SimpleNamespace(**{"write": True, "yes": True, "keys": None, **kw})

    def test_apply_phase_writes_typed_defaults_then_relaunches(self):
        calls = []

        def fake_run(cmd, *a, **k):
            calls.append(cmd)
            code = 1 if cmd[:1] == ["pgrep"] else 0  # iTerm2 not running
            return subprocess.CompletedProcess(cmd, code, stdout="", stderr="")
        with mock.patch.object(self.iterm.subprocess, "run", side_effect=fake_run), \
                contextlib.redirect_stdout(io.StringIO()):
            self.iterm.cmd_configure(self._args(
                keys="TabViewType,UseCustomTabBarFontSize,CustomTabBarFontSize"))
        writes = {c[3]: c[4:] for c in calls if c[:2] == ["defaults", "write"]}
        self.assertEqual(writes["TabViewType"], ["-int", "2"])
        self.assertEqual(writes["UseCustomTabBarFontSize"], ["-bool", "true"])
        self.assertEqual(writes["CustomTabBarFontSize"], ["-float", "18"])
        self.assertTrue(any(c[:2] == ["open", "-a"] for c in calls))
        self.assertFalse(any(c[:1] == ["osascript"] for c in calls))

    def test_running_hands_off_to_helper_and_quits(self):
        calls, popen = [], []

        def fake_run(cmd, *a, **k):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")  # iTerm2 up
        with mock.patch.object(self.iterm.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(self.iterm.subprocess, "Popen",
                                  side_effect=lambda cmd, *a, **k: popen.append(cmd) or mock.Mock()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.iterm.cmd_configure(self._args(keys="StatusBarPosition"))
        self.assertEqual(len(popen), 1)
        helper = popen[0][-1]
        self.assertIn("configure --write --yes --keys", helper)
        self.assertIn("StatusBarPosition", helper)
        self.assertTrue(any(c[:1] == ["osascript"] for c in calls))
        self.assertFalse(any(c[:2] == ["defaults", "write"] for c in calls),
                         "must defer the write to the helper, not write while iTerm2 runs")

    def test_running_declined_makes_no_changes(self):
        calls, popen = [], []

        def fake_run(cmd, *a, **k):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        with mock.patch.object(self.iterm.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(self.iterm.subprocess, "Popen",
                                  side_effect=lambda *a, **k: popen.append(a)), \
                mock.patch.object(self.iterm, "_prompt_tty", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()):
            self.iterm.cmd_configure(self._args(yes=False, keys="StatusBarPosition"))
        self.assertEqual(popen, [])
        self.assertFalse(any(c[:1] == ["osascript"] for c in calls))
        self.assertFalse(any(c[:2] == ["defaults", "write"] for c in calls))


def _base_state() -> dict:
    """Default state dict acceptable to apply(). Tests override individual fields."""
    return {
        "project": "acme/widget", "project_provider": "git-remote",
        "task": "", "task_provider": "default",
        "status": "idle", "status_provider": "default",
        "description": "",
        "pending_attention": False,
        "note_image": None,
    }


if __name__ == "__main__":
    unittest.main()

"""Behavior tests for scripts/beacon.

The plugin script has no .py extension, so we load it via importlib. Each test
gets a fresh DATA_DIR (tempdir) and a mocked `_cli` so we can assert which OSC
calls would have fired.
"""

from __future__ import annotations

import contextlib
import gzip
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import stat
import shutil
import subprocess
import sys
import tempfile
import time
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
    # Keep the user config out of the run in both directions: the suite must not
    # read the developer's own `~/.config/beacon/config.json` (badge, focus
    # origins), and a hook under test records the data dir it was handed, which
    # would otherwise overwrite that developer's real pointer with a tempdir.
    os.environ["XDG_CONFIG_HOME"] = str(data_dir / "xdg-config")
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
    the one exception — see PausedSwapsProfile, RENDER-05). Every render repaints
    the color, so a wipe beacon did not cause recovers on the next hook."""

    def test_first_render_switches_base_profile_and_sets_ready_color(self):
        self.beacon.apply({**_base_state(), "activity": "idle"})

        self.assertIn(("set-profile", "beacon-dev"), self.cli_calls,
                      "First render must switch into the base beacon-dev profile")
        ready = self.beacon.COLOR_PALETTE["ready"]
        self.assertIn(("badge-color", ready), self.cli_calls)
        self.assertIn(("tab-color", ready), self.cli_calls)

    def test_status_transition_emits_color_not_profile(self):
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "activity": "working"})

        busy = self.beacon.COLOR_PALETTE["busy"]
        self.assertIn(("badge-color", busy), self.cli_calls)
        self.assertIn(("tab-color", busy), self.cli_calls)
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile"], [],
            "A state transition repaints via OSC color, never a profile switch",
        )

    def test_unchanged_state_still_repaints_color(self):
        self.beacon.apply({**_base_state(), "activity": "working"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "activity": "working"})

        busy = self.beacon.COLOR_PALETTE["busy"]
        self.assertIn(("tab-color", busy), self.cli_calls,
                      "The color is re-emitted every render: beacon cannot see a "
                      "wipe it did not cause, so gating on the snapshot would "
                      "strand the tab unpainted")
        self.assertIn(("badge-color", busy), self.cli_calls)
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile"], [],
            "Identical logical state must not switch profiles",
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
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.assertIn(
            ("set-name", "w0t0p0:ABC-123", self.beacon.TITLE_FORMAT),
            self.cli_calls,
            "first render (a swap) must set the session name to the badge template",
        )

    def test_mode_swap_resets_name(self):
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.cli_calls.clear()
        self.beacon.apply({**_base_state(), "mode": "pause"})
        self.assertIn(
            ("set-name", "w0t0p0:ABC-123", self.beacon.TITLE_FORMAT),
            self.cli_calls,
            "a mode swap resets the session name, so it must be re-set (TITLE-04)",
        )

    def test_non_swap_render_leaves_name_alone(self):
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.cli_calls.clear()
        self.beacon.apply({**_base_state(), "activity": "working"})  # ready→busy, no swap
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-name"], [],
            "a non-swap state change must not re-set the name — it persists",
        )

    def test_non_iterm_session_gets_no_title(self):
        self._set_iterm_id("claude-session:xyz")
        self.beacon.apply({**_base_state(), "activity": "idle"})
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

    def test_post_tool_use_reasserts_working(self):
        # HOOK-03a: a tool just returned and the agent is back to thinking, so
        # the activity write stands on its own — nothing else in the event
        # supplies it.
        args = mock.Mock(event="PostToolUse")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Bash"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_state("activity"), "working")

    def test_tool_hook_does_not_reassert_name(self):
        # PreToolUse/PostToolUse fire many times per turn; re-asserting there
        # would spawn an osascript each time (the NFR-perf reason TITLE-04 cites).
        self._set_iterm_id("w0t0p0:ABC-123")
        self.beacon.apply({**_base_state(), "activity": "working"})  # prime a snapshot
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
        self.beacon.apply({**_base_state(), "activity": "idle", "task": "wiring"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "mode": "pause", "task": "wiring"})

        self.assertIn(("set-profile", "beacon-pause"), self.cli_calls,
                      "entering paused must swap into the beacon-pause profile")
        self.assertIn(("badge-format", self.beacon.BADGE_FORMAT), self.cli_calls,
                      "a swap must re-emit the badge format (SetProfile wipes it)")
        # The tab color answers to activity, not the mode: this session is idle, so
        # it stays the calm gray. The mode reaches the tab as its glyph instead.
        ready = self.beacon.COLOR_PALETTE["ready"]
        self.assertIn(("tab-color", ready), self.cli_calls)
        self.assertIn(("uservar", "beacon_title_prefix", "⏸ "), self.cli_calls,
                      "pause must mark line 1 of the tab / OS window title")
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
        self.beacon.apply({**_base_state(), "mode": "pause"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "activity": "idle"})

        self.assertIn(("set-profile", "beacon-dev"), self.cli_calls,
                      "leaving paused must swap back to the base beacon-dev profile")
        ready = self.beacon.COLOR_PALETTE["ready"]
        self.assertIn(("badge-color", ready), self.cli_calls)

    def test_non_mode_transitions_never_swap(self):
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "activity": "working"})
        self.beacon.apply({**_base_state(), "activity": "waiting"})

        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile"], [],
            "ready/busy/blocked (dev) stay OSC overlays on the base profile — no swap",
        )

    def test_snapshot_records_active_profile(self):
        self.beacon.apply({**_base_state(), "mode": "pause"})
        snap = self.beacon.read_state_json("resolved", {})
        self.assertEqual(snap.get("profile"), "beacon-pause")
        self.assertEqual(snap.get("project"), "acme/widget",
                         "snapshot keeps the raw project")

        self.beacon.apply({**_base_state(), "activity": "idle"})
        snap = self.beacon.read_state_json("resolved", {})
        self.assertEqual(snap.get("profile"), "beacon-dev")


class RetroMode(BeaconTest):
    """RENDER-05 / STATE-08: retro is a mode with its own profile (beacon-retro,
    muted green + ticked clipboard), set via `retro`. It persists across a prompt
    and marks the tab with 📋; no mode decorates the badge text (BADGE-11)."""

    def test_retro_swaps_profile_and_marks_the_tab(self):
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "mode": "retro"})

        self.assertIn(("set-profile", "beacon-retro"), self.cli_calls,
                      "entering retro must swap into the beacon-retro profile")
        self.assertIn(("uservar", "beacon_title_prefix", "📋 "), self.cli_calls,
                      "the mode's only cross-tab surface is its glyph")
        self.assertIn(("tab-color", self.beacon.COLOR_PALETTE["ready"]), self.cli_calls,
                      "the tab color reports activity, so an idle retro stays calm")

    def test_retro_badge_text_has_no_glyph(self):
        self.beacon.apply({**_base_state(), "mode": "retro"})
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "the glyph rides the title prefix, never the badge text (BADGE-11)",
        )

    def test_retro_command_sets_mode_and_note_only(self):
        # A mode writes the mode. It used to also freeze project/task into
        # overrides, which auto-resume then kept forever.
        self.beacon.write_state("resolved", json.dumps({
            "project": "shown-proj", "project_provider": "git-remote",
            "task": "shown-task", "task_provider": "pr",
        }))
        self.beacon.cmd_retro(mock.Mock(note=["lessons", "learned"]))
        self.assertEqual(self.beacon.read_mode(), ("retro", "lessons learned"))
        self.assertIsNone(self.beacon.read_state("override.project"),
                          "entering a mode must not pin the identity")
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_retro_persists_across_prompt(self):
        # Auto-resume covers pause only; a returning prompt must not clear
        # retro.
        self.beacon.write_mode("retro")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "next step"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_mode()[0], "retro",
                         "retro is a deliberate mode — it persists until cleared")


class DoneMode(BeaconTest):
    """RENDER-05: done is the terminal "session complete, ready to hand off" mode
    with its own profile (beacon-done, near-black "powered off"), set via `done`.
    Like retro it freezes no identity, persists across a prompt, and carries no
    badge glyph — its cue is the powered-off background and dim-gray color. It
    additionally suppresses the task slot (STATE-12)."""

    def test_done_swaps_to_done_profile_and_color(self):
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "mode": "done"})

        self.assertIn(("set-profile", "beacon-done"), self.cli_calls,
                      "entering done must swap into the beacon-done profile")
        self.assertIn(("uservar", "beacon_title_prefix", "🏁 "), self.cli_calls,
                      "the mode's only cross-tab surface is its glyph")
        self.assertIn(("tab-color", self.beacon.COLOR_PALETTE["ready"]), self.cli_calls,
                      "the tab color reports activity, so an idle done stays calm")

    def test_done_badge_has_no_glyph(self):
        self.beacon.apply({**_base_state(), "mode": "done"})
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "done carries its cue in the profile/background, not a badge glyph",
        )

    def test_done_suppresses_task_keeps_project(self):
        # STATE-12: a done session shows its project alone — the task slot is
        # blanked at resolve time (even with a task override set), project kept.
        self.beacon.write_mode("done")
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
        self.assertEqual(self.beacon.read_mode()[0], "done")
        self.assertEqual(self.beacon.read_mode()[1], "handing off")
        self.assertIsNone(self.beacon.read_state("override.project"),
                          "entering a mode must not pin the identity")
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_done_persists_across_prompt(self):
        # STATE-04 auto-resume is paused-only; a returning prompt must not clear
        # done (a handed-off session stays complete until explicitly resumed).
        self.beacon.write_mode("done")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "one more thing"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_mode()[0], "done",
                         "done is a deliberate terminal mode — it persists until cleared")


class AxesAreIndependent(BeaconTest):
    """The point of the split: a declared mode and observed activity coexist.

    Under the merged field these states were unreachable — `resolve()` walked a
    provider chain with the override above the hook signal, so a mode always won
    and the activity was discarded. A session in `release`, `retro`, or `done`
    therefore could not report that it was blocked on the user, which is the one
    signal meant to interrupt."""

    def test_release_and_waiting_coexist(self):
        self.beacon.write_mode("release", "cutting v2.5")
        self.beacon.write_state("activity", "waiting")
        state = self.beacon.resolve()
        self.assertEqual(state["mode"], "release")
        self.assertEqual(state["activity"], "waiting")
        self.assertEqual(state["note"], "cutting v2.5")

    def test_interrupt_reaches_the_tab_through_a_mode(self):
        # The tab color is the interrupt channel, so it has to report `blocked`
        # even while the pane sits in a mode profile.
        self.beacon.apply({
            **_base_state(), "mode": "release", "activity": "waiting",
        })
        self.assertIn(("tab-color", self.beacon.COLOR_PALETTE["blocked"]), self.cli_calls,
                      "a moded session blocked on the user must still read as blocked")
        self.assertIn(("set-profile", "beacon-release"), self.cli_calls,
                      "and must keep the mode's pane background")
        self.assertIn(("uservar", "beacon_title_prefix", "🚀 "), self.cli_calls,
                      "and its glyph, so the tab says both things at once")

    def test_activity_never_displaces_the_mode_surfaces(self):
        # Whatever the activity, the pane stays in the mode's profile and the tab
        # keeps its glyph — only the color moves. Asserted on the snapshot rather
        # than the emitted calls, because a profile is only *swapped* when it
        # changes (RENDER-05), so the second pass through here emits nothing.
        for activity, hex_color in (("idle", "ready"), ("working", "busy"),
                                    ("waiting", "blocked")):
            with self.subTest(activity=activity):
                self.beacon.apply({
                    **_base_state(), "mode": "pause", "activity": activity,
                })
                snap = self.beacon.read_state_json("resolved", {})
                self.assertEqual(snap["profile"], "beacon-pause")
                self.assertEqual(snap["mode_glyph"], "⏸ ")
                self.assertEqual(snap["color_state"], hex_color)

    def test_activity_survives_entering_a_mode(self):
        # The merged field overwrote it; separate files cannot.
        self.beacon.write_state("activity", "waiting")
        self.beacon.write_mode("release", "")
        self.assertEqual(self.beacon.read_activity(), "waiting",
                         "entering a mode must not discard what the hooks observed")

    def test_hook_activity_writes_through_a_mode(self):
        # The Stop hook reports a calm turn regardless of mode; the mode stays.
        self.beacon.write_mode("retro", "writing it up")
        args = mock.Mock(event="Stop")
        with mock.patch.object(sys, "stdin", io.StringIO("{}")):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_activity(), "idle")
        self.assertEqual(self.beacon.read_mode(), ("retro", "writing it up"))


class ModeIsATuple(BeaconTest):
    """A mode and its note are one value with one writer, so they live in one
    file: only entering a mode sets either, and leaving one drops both."""

    def test_leaving_a_mode_drops_its_note(self):
        self.beacon.write_mode("pause", "waiting for VPN")
        self.beacon.write_mode(self.beacon.DEV_MODE)
        self.assertEqual(self.beacon.read_mode(), ("dev", ""))

    def test_dev_mode_stores_no_file(self):
        # "No mode" has exactly one representation on disk — an absent file —
        # rather than a sentinel a reader has to know about.
        self.beacon.write_mode("done", "finished")
        self.assertIsNotNone(self.beacon.read_state("mode"))
        self.beacon.write_mode(self.beacon.DEV_MODE)
        self.assertIsNone(self.beacon.read_state("mode"))

    def test_unknown_mode_name_reads_as_dev(self):
        # Live state still holds `wrapping`, retired in the pre-SDLC rename.
        self.beacon.write_state("mode", json.dumps({"name": "wrapping", "note": "x"}))
        self.assertEqual(self.beacon.read_mode(), ("dev", ""))

    def test_corrupt_mode_file_reads_as_dev(self):
        for raw in ("{not json", '"a string"', "[]", "null"):
            with self.subTest(raw=raw):
                self.beacon.write_state("mode", raw)
                self.assertEqual(self.beacon.read_mode(), ("dev", ""))


class ActivityHasNoOverrideTier(BeaconTest):
    """`beacon status` sets modes only. An activity pinned above the hooks goes
    stale the moment the session moves on, and every instance found in live state
    was contradicting the hooks it outranked — tabs painted `working` for months
    while the session was in fact blocked on the user."""

    def test_status_rejects_an_activity_value(self):
        parser = self.beacon._build_parser()
        with mock.patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["status", "working"])

    def test_status_accepts_every_mode_and_dev(self):
        parser = self.beacon._build_parser()
        for name in (self.beacon.DEV_MODE, *self.beacon.MODES):
            with self.subTest(name=name):
                self.assertEqual(parser.parse_args(["status", name]).mode, name)

    def test_status_dev_leaves_the_mode(self):
        self.beacon.write_mode("release", "v2.5")
        self.beacon.cmd_status(mock.Mock(mode=self.beacon.DEV_MODE, note=[]))
        self.assertEqual(self.beacon.read_mode(), ("dev", ""))

    def test_set_takes_no_state_field(self):
        self.assertEqual(self.beacon.VALID_FIELDS, ("project", "task"),
                         "overrides remain only where a provider chain sits below them")


class ReleaseMode(BeaconTest):
    """RENDER-05 / STATE-10: release is the active "ship-it flow in progress" mode
    with its own profile (beacon-release, launch-sky navy + rocket watermark), set via
    `release`. Like retro it freezes no identity, persists across a prompt, and
    carries no badge glyph — its cue is the profile background and green badge."""

    def test_release_swaps_to_release_profile_and_color(self):
        self.beacon.apply({**_base_state(), "activity": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "mode": "release"})

        self.assertIn(("set-profile", "beacon-release"), self.cli_calls,
                      "entering release must swap into the beacon-release profile")
        self.assertIn(("uservar", "beacon_title_prefix", "🚀 "), self.cli_calls,
                      "the mode's only cross-tab surface is its glyph")
        self.assertIn(("tab-color", self.beacon.COLOR_PALETTE["ready"]), self.cli_calls,
                      "the tab color reports activity, so an idle release stays calm")

    def test_release_badge_has_no_glyph(self):
        self.beacon.apply({**_base_state(), "mode": "release"})
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
        self.assertEqual(self.beacon.read_mode()[0], "release")
        self.assertEqual(self.beacon.read_mode()[1], "v2 ship")
        self.assertIsNone(self.beacon.read_state("override.project"),
                          "entering a mode must not pin the identity")
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_release_persists_across_prompt(self):
        # STATE-04 auto-resume is paused-only; a returning prompt must not clear
        # release (a shipping session stays in flight until explicitly resumed).
        self.beacon.write_mode("release")
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "one more thing"}))):
            self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon.read_mode()[0], "release",
                         "release is a deliberate mode — it persists until cleared")


class DataDirResolution(BeaconTest):
    """§6.2: every invocation context has to land on one data dir or hooks write
    where nothing reads. Only a hook is handed `CLAUDE_PLUGIN_DATA`, so it records
    that path and the env-less contexts (slash commands, the on-PATH wrapper, the
    serve service) read it back. Absent a record, the path is derived the way
    Claude Code names the directory: `<plugin>-<marketplace>` for a cache install,
    `<plugin>-inline` for a plugin loaded from a local directory."""

    def setUp(self):
        super().setUp()
        self._config = tempfile.TemporaryDirectory()
        self.addCleanup(self._config.cleanup)
        cfg = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._config.name})
        cfg.start()
        self.addCleanup(cfg.stop)
        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)
        home = mock.patch("pathlib.Path.home", return_value=Path(self._home.name))
        home.start()
        self.addCleanup(home.stop)

    def _with_plugin_root(self, root: Path):
        patcher = mock.patch.object(self.beacon, "PLUGIN_ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cache_install_derives_plugin_marketplace(self):
        home = Path(self._home.name)
        self._with_plugin_root(home / ".claude/plugins/cache/chris-peterson/beacon/2.3.0")
        self.assertEqual(self.beacon._default_data_dir(),
                         home / ".claude/plugins/data/beacon-chris-peterson")

    def test_local_plugin_root_derives_the_inline_bucket(self):
        # A plugin root outside the cache was loaded from a local directory,
        # which Claude Code buckets as `<plugin>-inline`. Deriving anything else
        # (e.g. from the checkout's git remote) points the wrapper and the sessions view
        # view at a directory the running session's hooks never write.
        home = Path(self._home.name)
        self._with_plugin_root(Path("/Users/dev/src/beacon"))
        self.assertEqual(self.beacon._default_data_dir(),
                         home / ".claude/plugins/data/beacon-inline")

    def test_recorded_pointer_wins_over_the_derivation(self):
        self._with_plugin_root(Path("/Users/dev/src/beacon"))
        recorded = Path(self._home.name) / "elsewhere/beacon-inline"
        self.beacon._record_data_dir(str(recorded))
        self.assertEqual(self.beacon._default_data_dir(), recorded)

    def test_blank_or_missing_pointer_falls_through_to_the_derivation(self):
        home = Path(self._home.name)
        self._with_plugin_root(Path("/Users/dev/src/beacon"))
        derived = home / ".claude/plugins/data/beacon-inline"
        self.assertEqual(self.beacon._default_data_dir(), derived)
        pointer = self.beacon._data_dir_pointer()
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text("   \n")
        self.assertEqual(self.beacon._default_data_dir(), derived)

    def test_pointer_naming_a_vanished_dir_falls_through(self):
        # A recorded dir that no longer exists (a temp dir from a test run, a
        # pruned install) would otherwise strand every env-less context on a path
        # nothing writes — the exact failure this resolution exists to prevent.
        home = Path(self._home.name)
        self._with_plugin_root(Path("/Users/dev/src/beacon"))
        gone = home / "gone/beacon-inline"
        self.beacon._record_data_dir(str(gone))
        self.assertEqual(self.beacon._default_data_dir(), gone)
        gone.rmdir()
        self.assertEqual(self.beacon._default_data_dir(),
                         home / ".claude/plugins/data/beacon-inline")

    def test_record_rewrites_only_on_change(self):
        home = Path(self._home.name)
        first_dir = home / "first/beacon-inline"
        self.beacon._record_data_dir(str(first_dir))
        pointer = self.beacon._data_dir_pointer()
        stamp = pointer.stat().st_mtime_ns
        self.beacon._record_data_dir(str(first_dir))
        self.assertEqual(pointer.stat().st_mtime_ns, stamp,
                         "an unchanged pointer must not be rewritten on every hook")
        second_dir = home / "second/beacon-chris-peterson"
        self.beacon._record_data_dir(str(second_dir))
        self.assertEqual(self.beacon._read_data_dir_pointer(), second_dir)

    def test_hook_records_the_dir_it_was_handed(self):
        handed_dir = Path(self._home.name) / "handed/beacon-inline"
        args = mock.Mock(event="UserPromptSubmit")
        handed = {"CLAUDE_PLUGIN_DATA": str(handed_dir)}
        with mock.patch.dict(os.environ, handed):
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "hi"}))):
                self.beacon.cmd_hook(args)
        self.assertEqual(self.beacon._read_data_dir_pointer(), handed_dir)

    def test_the_suite_never_writes_the_developers_own_pointer(self):
        # `_load_beacon` redirects XDG_CONFIG_HOME into the per-test tempdir, so a
        # hook under test can't overwrite the pointer the developer's own sessions
        # depend on. Asserted here because the leak is invisible in a green run.
        self.assertTrue(
            str(self.beacon._data_dir_pointer()).startswith(self._config.name),
            f"pointer escaped the test config dir: {self.beacon._data_dir_pointer()}")


class ModeProfileDerivation(unittest.TestCase):
    """RENDER-05 / §6.6: install derives one mode profile per MODE_SPECS entry
    from the rendered base — same layout, a de-emphasized Dracula background (and,
    for paused, a faint background image) — so they never drift. THEME-01: hexes
    are single-sourced in MODE_SPECS."""

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
        self.assertNotIn("Use Separate Colors for Light and Dark Mode", base,
                         "the light/dark switch is the parent profile's to set — "
                         "forcing it off points a stock profile at its white "
                         "light-mode background")
        # Whichever set that switch selects, the ready-gray default has to be there.
        ready = self.beacon.COLOR_PALETTE["ready"]
        for key in ("Badge Color", "Badge Color (Light)", "Badge Color (Dark)"):
            self.assertAlmostEqual(base[key]["Red Component"],
                                   int(ready[0:2], 16) / 255.0, msg=key)

        seen_guids = {base["Guid"]}
        for mode, spec in self.beacon.MODE_SPECS.items():
            prof = json.loads((profiles_dir / f"{spec['profile']}.json").read_text())["Profiles"][0]
            self.assertEqual(prof["Name"], spec["profile"])
            self.assertEqual(prof["Guid"], spec["guid"])
            self.assertNotIn(prof["Guid"], seen_guids, f"{mode} needs a distinct Guid")
            seen_guids.add(prof["Guid"])
            # Same layout (single-sourced) — a mode profile differs only by background.
            self.assertEqual(prof["Status Bar Layout"], base["Status Bar Layout"])
            for key in ("Background Color", "Background Color (Light)",
                        "Background Color (Dark)"):
                self.assertAlmostEqual(
                    prof[key]["Red Component"],
                    int(spec["background"][0:2], 16) / 255.0,
                    msg=f"{mode}: {key}",
                )
            if spec["image"]:
                self.assertTrue(prof["Background Image Location"].endswith(spec["image"]))
                self.assertEqual(prof["Background Image Mode"], 3)
                self.assertEqual(prof["Blend"], spec["blend"])
            else:
                self.assertNotIn("Background Image Location", prof)

    def test_a_split_pane_starts_where_the_pane_it_split_from_is(self):
        ok, msg = self.beacon.install_dynamic_profile()
        self.assertTrue(ok, msg)
        profiles_dir = (Path(self._home.name) / "Library" / "Application Support"
                        / "iTerm2" / "DynamicProfiles")
        base = json.loads((profiles_dir / "beacon-dev.json").read_text())["Profiles"][0]
        self.assertEqual(base["AWDS Pane Option"], "Recycle")
        # iTerm2 ignores the option unless its paired directory key is present,
        # even though Recycle never reads the value.
        self.assertIn("AWDS Pane Directory", base)
        # iTerm2 reads a per-scope rule only in Advanced mode.
        self.assertEqual(base["Custom Directory"], "Advanced")
        # The two scopes beacon does not claim stay the parent's to answer.
        for unclaimed in ("AWDS Tab Option", "AWDS Window Option", "Working Directory"):
            self.assertNotIn(unclaimed, base)
        for spec in self.beacon.MODE_SPECS.values():
            mode = json.loads((profiles_dir / f"{spec['profile']}.json").read_text())["Profiles"][0]
            self.assertEqual(mode["AWDS Pane Option"], "Recycle",
                             f"{spec['profile']} must not change where a split opens")

    def test_a_long_button_label_grows_its_width_cap(self):
        # iTerm2 draws an action title inside `maxwidth` and the layout removes
        # components that come out empty, so a label wider than the cap blanks
        # the button instead of truncating it.
        profile = {"Status Bar Layout": {"components": [
            {"configuration": {"knobs": {"maxwidth": 90,
                                         "action": {"title": "↗ code"}}}},
            {"configuration": {"knobs": {"maxwidth": 90,
                                         "action": {"title": "jetbrains-ultimate"}}}},
            {"configuration": {"knobs": {"maxwidth": 240}}},
        ]}}
        self.beacon._fit_action_button_widths(profile)
        caps = [c["configuration"]["knobs"]["maxwidth"]
                for c in profile["Status Bar Layout"]["components"]]
        self.assertEqual(caps[0], 90, "a default-length label keeps the template's cap")
        self.assertGreater(caps[1], 90, "a longer label needs a wider cap")
        self.assertEqual(caps[2], 240, "a non-action component is left alone")

    def test_default_button_labels_fit_the_template_caps(self):
        # The template's caps are the floor, so the shipped labels must already
        # fit them — otherwise the default install blanks its own buttons.
        for name in self.beacon.STATUSBAR_BUTTON_DEFAULTS:
            label = self.beacon.STATUSBAR_BUTTON_DEFAULTS[name]["label"]
            needed = (int(len(label) * self.beacon.STATUSBAR_TITLE_ADVANCE)
                      + self.beacon.STATUSBAR_TITLE_PADDING)
            self.assertLessEqual(needed, 90, f"{name}: {label!r}")

    def test_dev_is_never_a_mode(self):
        # `dev` is the absence of a mode — the empty mode file — so it must not
        # appear in the table that drives glyphs, profiles, and the CLI choices.
        self.assertNotIn(self.beacon.DEV_MODE, self.beacon.MODE_SPECS)
        self.assertEqual(set(self.beacon.MODES), set(self.beacon.MODE_SPECS))

    def test_activity_tables_agree(self):
        self.assertEqual(set(self.beacon.ACTIVITIES),
                         set(self.beacon.ACTIVITY_TO_COLOR_STATE))
        self.assertEqual(set(self.beacon.ACTIVITY_TO_COLOR_STATE.values()),
                         set(self.beacon.COLOR_PALETTE),
                         "every color state an activity maps to needs a hex")
        self.assertIn(self.beacon.DEFAULT_ACTIVITY, self.beacon.ACTIVITIES)

    def test_every_mode_carries_a_watermark(self):
        # Every mode carries a slate watermark and a blend — pause's ||-button,
        # release's rocket, retro's ticked clipboard, done's checkered flag — all
        # through iterm/make-bg.py. No mode is exempt: the background is one of
        # only two surfaces a mode has, so a mode without a mark is a mode that
        # reads as a bare tint.
        for mode in self.beacon.MODES:
            spec = self.beacon.MODE_SPECS[mode]
            self.assertTrue(spec["image"], f"{mode} should carry a watermark image")
            self.assertIsNotNone(spec["blend"], f"{mode} should carry a blend")

    def test_every_mode_carries_a_glyph(self):
        # The glyph is the mode's *only* cross-tab surface, so a mode without one
        # is invisible from any tab the user isn't looking at.
        for mode, spec in self.beacon.MODE_SPECS.items():
            self.assertTrue(spec["glyph"], f"{mode} should carry a tab glyph")

    def test_mode_image_files_exist(self):
        # The watermark assets each mode names must be present on disk: they back
        # both the profile background (install) and the /mode-bg/<state> serve
        # route the dashboard card renders (WIP-17). A rename that misses one
        # would 404 the card and blank the pane background.
        for mode, spec in self.beacon.MODE_SPECS.items():
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
                             {"label": "↗ code", "cmd": "code"})

    def test_label_and_cmd_are_read_from_the_block(self):
        with self._buttons(web={"label": "↖ repo", "cmd": "git web"}):
            self.assertEqual(self.beacon._statusbar_button("web"),
                             {"label": "↖ repo", "cmd": "git web"})

    def test_one_field_set_leaves_the_other_at_its_default(self):
        with self._buttons(code={"label": "↗ edit"}):
            self.assertEqual(self.beacon._statusbar_button("code"),
                             {"label": "↗ edit", "cmd": "code"})

    def test_a_blank_value_falls_back_rather_than_disabling(self):
        # A whitespace-only label would render an invisible button, and a blank
        # code cmd has nothing to launch — both mean "the default" instead.
        with self._buttons(code={"label": "   ", "cmd": ""}):
            self.assertEqual(self.beacon._statusbar_button("code"),
                             {"label": "↗ code", "cmd": "code"})

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
        for spec in self.beacon.MODE_SPECS.values():
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

    def test_refresh_requires_iterm(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_refresh_iterm_profiles(self.beacon.argparse.Namespace())
        self.assertIn("iTerm2", str(cm.exception))

    def test_refresh_rerenders_without_the_rest_of_the_bootstrap(self):
        calls = []
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True), \
             mock.patch.object(self.beacon, "install_dynamic_profile",
                               side_effect=lambda: (calls.append("profile") or (True, "wrote it"))), \
             mock.patch.object(self.beacon, "_install_cli_wrapper",
                               side_effect=AssertionError("must not run the wrapper step")), \
             mock.patch.object(self.beacon, "_install_shell_source",
                               side_effect=AssertionError("must not run the shell step")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.beacon.cmd_refresh_iterm_profiles(self.beacon.argparse.Namespace())
        self.assertEqual(calls, ["profile"])

    def test_refresh_exits_nonzero_when_the_write_fails(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True), \
             mock.patch.object(self.beacon, "install_dynamic_profile",
                               return_value=(False, "failed to write")):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_refresh_iterm_profiles(self.beacon.argparse.Namespace())
        self.assertIn("failed to write", str(cm.exception))

    def _layout(self, write=False, yes=False, keys=None, rc=0):
        """Run `beacon layout`, returning the argv and env handed to the CLI."""
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"], seen["env"] = cmd, kw.get("env") or {}
            return types.SimpleNamespace(returncode=rc)
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True), \
             mock.patch.object(self.beacon.subprocess, "run", side_effect=fake_run), \
             self.assertRaises(SystemExit) as cm:
            self.beacon.cmd_layout(self.beacon.argparse.Namespace(
                write=write, yes=yes, keys=keys))
        seen["code"] = cm.exception.code
        return seen

    def test_layout_requires_iterm(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            with self.assertRaises(SystemExit) as cm:
                self.beacon.cmd_layout(self.beacon.argparse.Namespace(
                    write=False, yes=False, keys=None))
        self.assertIn("iTerm2", str(cm.exception))

    def test_layout_audits_by_default(self):
        seen = self._layout()
        self.assertEqual(seen["cmd"][-1], "configure")
        self.assertNotIn("--write", seen["cmd"])

    def test_layout_passes_its_flags_through(self):
        seen = self._layout(write=True, yes=True, keys="HideTab,TabViewType")
        self.assertEqual(seen["cmd"][-5:],
                         ["configure", "--write", "--yes", "--keys", "HideTab,TabViewType"])

    def test_layout_tells_the_cli_which_command_to_advertise(self):
        # Otherwise the advice names beacon-iterm, which is the whole reason a
        # user never finds the layout settings from the command they type.
        seen = self._layout()
        self.assertEqual(seen["env"].get("BEACON_LAYOUT_COMMAND"), "beacon layout")

    def test_layout_exits_with_the_audits_status(self):
        # The audit signals drift by exiting non-zero; swallowing that would
        # make `beacon layout` useless as a check.
        self.assertEqual(self._layout(rc=1)["code"], 1)
        self.assertEqual(self._layout(rc=0)["code"], 0)


class ProjectChipIsTheProjectName(BeaconTest):
    """STATUS-BAR-02: the chip carries the project's name, not a forge identity
    and not a deliverable ref — so it reads the same in a plain shell as under
    Claude, in a git repo or out of one."""

    def test_the_chip_is_the_project_name(self):
        with mock.patch.object(self.beacon, "_project_name_at", return_value="widgets"):
            self.assertEqual(self.beacon._project_chip_at(Path("/work/widgets")), "widgets")

    def test_outside_a_project_the_chip_names_the_directory(self):
        # The old chip collapsed to empty here, which is the case the rewrite
        # exists to fix: a plain shell had no identity on the strip at all.
        with mock.patch.object(self.beacon, "_project_name_at", return_value=""):
            self.assertEqual(self.beacon._project_chip_at(Path("/tmp/scratch")), "scratch")

    def test_the_chip_carries_no_deliverable_ref(self):
        published = {}
        with mock.patch.object(self.beacon, "_project_name_at", return_value="widgets"), \
             mock.patch.object(self.beacon, "_project_full_at", return_value="gh:acme/widgets"), \
             mock.patch.object(self.beacon, "_detect_branch_info",
                               return_value=("topic", "clean", "", "feature")), \
             mock.patch.object(self.beacon, "resolve_url",
                               return_value=("https://github.com/acme/widgets/pull/42", "acme/widgets#42")), \
             mock.patch.object(self.beacon, "_cli",
                               side_effect=lambda *a: published.update({"args": a})):
            self.beacon._publish_chips(Path("/work/widgets"))
        pairs = published["args"][1:]
        self.assertIn("beacon_project_name=widgets", pairs)
        self.assertFalse([p for p in pairs if "#42" in p],
                         "the deliverable ref belongs to the status line, not the chip")

    def test_the_forge_identity_still_qualifies_deliverables(self):
        # `_project_full_at` outlives the chip that rendered it: STATUSLINE-03
        # needs it to tell this project's deliverables from another's.
        recorded = {}
        with mock.patch.object(self.beacon, "_project_name_at", return_value="widgets"), \
             mock.patch.object(self.beacon, "_project_full_at", return_value="gh:acme/widgets"), \
             mock.patch.object(self.beacon, "_detect_branch_info",
                               return_value=("topic", "clean", "", "feature")), \
             mock.patch.object(self.beacon, "resolve_url",
                               return_value=("https://github.com/acme/widgets/pull/42", "acme/widgets#42")), \
             mock.patch.object(self.beacon, "_tack_route_urls", return_value=[]), \
             mock.patch.object(self.beacon, "_record_deliverable",
                               side_effect=lambda *a: recorded.update({"args": a})), \
             mock.patch.object(self.beacon, "_cli"):
            self.beacon._publish_chips(Path("/work/widgets"))
        self.assertEqual(recorded["args"][0], "#42")
        self.assertEqual(recorded["args"][2], "gh:acme/widgets")
        self.assertEqual(self.beacon.read_state("resolved.project"), "gh:acme/widgets")


class ShellMirrorsTheChipContract(unittest.TestCase):
    """§6.5: the shell's precmd and the plugin publish the same slot, so a
    Claude pane and an interactive pane agree. These assert the shell source
    kept its half of the contract — it can't be imported and run here."""

    def setUp(self):
        self.shell = (REPO_ROOT / "shell" / "beacon.zsh").read_text(encoding="utf-8")

    def test_the_shell_publishes_the_project_name_slot(self):
        # Slots go out as raw OSC from zsh, so the publish call is what
        # carries the contract now.
        self.assertIn("_beacon_publish beacon_project_name", self.shell)
        self.assertNotIn("beacon_project_full", self.shell)

    def test_the_shell_never_publishes_the_plugin_owned_slot(self):
        # BADGE-02: beacon_project is the plugin's alone. The trailing space
        # keeps beacon_project_name from matching.
        self.assertNotIn("uservar beacon_project ", self.shell)
        self.assertNotIn("_beacon_publish beacon_project ", self.shell)

    def test_the_prompt_path_resolves_no_url(self):
        # The chip needs no URL, so the per-prompt python + tack subprocesses
        # are gone. A reintroduced resolve here would be a hot-path regression.
        for gone in ("_beacon_resolve_url", "_beacon_deliverable_suffix",
                     "_BEACON_RESOLVED_URL", '"$_BEACON_SCRIPT" resolve-url', "zstat"):
            with self.subTest(symbol=gone):
                self.assertNotIn(gone, self.shell)


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
            **_base_state(), "activity": "waiting", "pending_attention": True,
        })
        red = self.beacon.COLOR_PALETTE["blocked"]
        self.assertIn(("badge-color", red), self.cli_calls)
        self.assertIn(("tab-color", red), self.cli_calls)
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile" and c[1] != "beacon-dev"],
            [],
            "No per-state profile switch — blocked is an OSC color",
        )


class ModeNoteStaysOffLineOne(BeaconTest):
    """Line 1 of the tab carries the mode's glyph and nothing more: it is shared
    with the OS window title and cannot differ between them, so a note has no
    room there (TITLE-06). The note's surfaces are the status line (STATUSLINE-01)
    and, while the session is stood down, line 2 (TITLE-05a — see
    StoodDownModeNoteOnLineTwo). The pane paints the mode's profile and the
    activity's color, and no retired bg-image/note/clear-screen overlay."""

    def test_paused_leads_title_glyph_and_keeps_the_note_off_line_one(self):
        self.beacon.apply({**_base_state(), "activity": "working"})
        self.cli_calls.clear()
        self.beacon.apply({
            **_base_state(), "mode": "pause", "note": "leaving for lunch",
        })
        # TITLE-06: the mode's glyph leads line 1, and the note does not follow it.
        self.assertIn(("uservar", "beacon_title_prefix", "⏸ "), self.cli_calls)
        self.assertEqual(
            [c for c in self.cli_calls
             if c[:2] == ("uservar", "beacon_project") and "lunch" in c[2]],
            [],
            "the note must not reach line 1, which the window title shares",
        )
        self.assertEqual(
            [c for c in self.cli_calls
             if c[:2] == ("uservar", "beacon_task") and "lunch" in c[2]],
            [],
            "BADGE-11: the badge overlays output — never a home for free text",
        )
        for verb in ("bg-image", "note", "clear-screen"):
            self.assertEqual(
                [c for c in self.cli_calls if c[0] == verb], [],
                f"a note must not emit {verb} (overlay retired)",
            )

    def test_leaving_the_mode_clears_the_title_glyph(self):
        self.beacon.apply({**_base_state(), "mode": "pause", "note": "brb"})
        self.cli_calls.clear()
        self.beacon.apply({**_base_state(), "activity": "working"})
        self.assertIn(("uservar", "beacon_title_prefix", ""), self.cli_calls)

    def test_note_alone_moves_no_surface(self):
        # Adding a note without moving either axis is data-only.
        self.beacon.apply({**_base_state(), "mode": "pause", "note": ""})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "mode": "pause", "note": "bg refresh ~30 min",
        })

        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "set-profile"], [],
            "neither axis moved → no profile swap; the note is data",
        )
        # The color is re-emitted every render, but at the hex the axes already
        # resolved to — a note cannot move it.
        idle = self.beacon.COLOR_PALETTE["ready"]
        self.assertEqual(
            [c for c in self.cli_calls if c[0] == "tab-color"],
            [("tab-color", idle)],
        )


class StoodDownModeNoteOnLineTwo(BeaconTest):
    """TITLE-05a: while the session is stood down (`pause`, `done` — STATE-15),
    line 2 of the tab carries the mode's note in place of the task.

    The note's other home, the status line, exists only in the focused pane —
    the same weakness that makes the glyph rather than the pane background the
    mode's cross-tab surface. A halted session has no live task to displace, so
    the slot is empty in exactly the sessions that carry a note."""

    def _line_two(self):
        return [c[2] for c in self.cli_calls if c[:2] == ("uservar", "beacon_task_nl")]

    def test_pause_note_fills_line_two(self):
        self.beacon.write_mode("pause", "out for lunch")
        self.beacon.render()
        self.assertEqual(self._line_two(), ["\n  out for lunch"])

    def test_done_note_fills_line_two_that_state_12_blanked(self):
        self.beacon.write_state("override.task", "perms")
        self.beacon.write_mode("done", "handed off, CI green")
        self.beacon.render()
        # STATE-12 still suppresses the task on the badge's single line; the note
        # is what now occupies the second line it left empty.
        self.assertEqual(self._line_two(), ["\n  handed off, CI green"])
        self.assertEqual(
            [c[2] for c in self.cli_calls if c[:2] == ("uservar", "beacon_task")], [""],
        )

    def test_an_active_phase_keeps_its_task_on_line_two(self):
        self.beacon.write_state("override.task", "perms")
        for mode in ("release", "retro"):
            with self.subTest(mode=mode):
                self.cli_calls.clear()
                self.beacon.remove_state("resolved")
                self.beacon.write_mode(mode, "v2.5.0")
                self.beacon.render()
                self.assertEqual(
                    self._line_two(), ["\n  perms"],
                    "release / retro are working phases — the task is live "
                    "information and the note keeps its status-line home",
                )

    def test_a_stood_down_mode_without_a_note_leaves_the_slot_alone(self):
        self.beacon.write_state("override.task", "perms")
        self.beacon.write_mode("pause", "")
        self.beacon.render()
        self.assertEqual(self._line_two(), ["\n  perms"])

    def test_leaving_the_mode_restores_the_task(self):
        self.beacon.write_state("override.task", "perms")
        self.beacon.write_mode("pause", "out for lunch")
        self.beacon.render()
        self.cli_calls.clear()
        self.beacon.write_mode(self.beacon.DEV_MODE)
        self.beacon.render()
        self.assertEqual(
            self._line_two(), ["\n  perms"],
            "presentation-only, like STATE-12: nothing deleted the override",
        )
        self.assertEqual(self.beacon.read_state("override.task"), "perms")


class IdlePromptOnAStoodDownSession(BeaconTest):
    """HOOK-03d: an `idle_prompt` on a session stood down on purpose reports
    nothing its user doesn't know — it is idle *because* they parked or finished
    it, and since a halted session sits at an idle prompt by definition the timer
    is guaranteed to fire, making red the resting state of every parked tab.

    Not a precedence rule between the axes (RES-06): a `permission_prompt` still
    paints red in every mode, and what is dropped is one uninformative
    observation, not the activity axis losing an argument to the mode."""

    def _notify(self, kind):
        args = mock.Mock(event="Notification", kind=kind)
        with mock.patch.object(sys, "stdin", io.StringIO("{}")):
            self.beacon.cmd_hook(args)

    def test_idle_prompt_is_dropped_while_stood_down(self):
        for mode in ("pause", "done"):
            with self.subTest(mode=mode):
                self.beacon.remove_state("activity")
                self.beacon.remove_state("pending-attention")
                self.beacon.write_mode(mode, "")
                self._notify("idle_prompt")
                self.assertIsNone(self.beacon.read_state("activity"))
                self.assertIsNone(self.beacon.read_state("pending-attention"))

    def test_idle_prompt_still_lands_in_an_active_phase(self):
        for mode in ("dev", "release", "retro"):
            with self.subTest(mode=mode):
                self.beacon.remove_state("activity")
                self.beacon.write_mode(mode, "")
                self._notify("idle_prompt")
                self.assertEqual(self.beacon.read_activity(), "waiting")
                self.assertEqual(self.beacon.read_state("pending-attention"), "1")

    def test_permission_prompt_lands_in_every_mode(self):
        for mode in ("pause", "done", "release", "dev"):
            with self.subTest(mode=mode):
                self.beacon.remove_state("activity")
                self.beacon.write_mode(mode, "")
                self._notify("permission_prompt")
                self.assertEqual(
                    self.beacon.read_activity(), "waiting",
                    "Claude is blocked on a decision the user does not know about",
                )


class StoodDownIsDeclaredByTheMode(unittest.TestCase):
    """STATE-15: the halted/active split is an attribute on MODE_SPECS, not a
    tuple of names at a call site — a mode added later answers for itself. This
    also pins the partition itself, which two behaviors depend on."""

    def setUp(self):
        self.beacon = _load_beacon(REPO_ROOT / "tests")

    def test_the_partition(self):
        halted = {m for m, s in self.beacon.MODE_SPECS.items() if s.get("stood_down")}
        self.assertEqual(halted, {"pause", "done"})

    def test_every_mode_declares_a_boolean_or_omits_it(self):
        for mode, spec in self.beacon.MODE_SPECS.items():
            with self.subTest(mode=mode):
                self.assertIsInstance(spec.get("stood_down", False), bool)

    def test_the_notification_hooks_pass_their_matcher(self):
        # The payload carries no prompt kind, so hooks.json is the only place the
        # matcher survives to the CLI — the whole mechanism rests on this flag.
        wiring = json.loads(
            (REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        for entry in wiring["hooks"]["Notification"]:
            with self.subTest(matcher=entry["matcher"]):
                for h in entry["hooks"]:
                    self.assertIn(f"--kind {entry['matcher']}", h["command"])


class PauseWritesOnlyTheMode(BeaconTest):
    """Entering a mode writes the mode and nothing else.

    Pause used to also snapshot the resolved project and task into overrides so
    the identity held still while parked, and auto-resume then *preserved* them —
    so one pause pinned a session's identity permanently, above every provider.
    Live state showed the result: tasks pinned to branches the session had long
    left, and project labels a version and a half stale. The sessions view reads the
    last-rendered snapshot for the same stability, and a snapshot cannot outrank a
    live provider."""

    def test_pause_pins_no_identity(self):
        self.beacon.write_state("resolved", json.dumps({
            "project": "shown-proj", "project_provider": "git-remote",
            "task": "shown-task", "task_provider": "branch",
        }))
        self.beacon.cmd_pause(mock.Mock(note=["waiting", "for", "VPN"], clear_screen=False))
        self.assertEqual(self.beacon.read_mode(), ("pause", "waiting for VPN"))
        self.assertIsNone(self.beacon.read_state("override.project"))
        self.assertIsNone(self.beacon.read_state("override.task"))

    def test_pause_never_reresolves(self):
        # The freeze read the cached snapshot precisely to keep the task chain's
        # gh/glab PR-title provider out of this hot, user-facing path. Writing
        # nothing but the mode keeps that property for free.
        with mock.patch.object(self.beacon, "resolve",
                               side_effect=AssertionError("pause must not re-resolve")):
            self.beacon.write_mode("pause", "")
        self.assertEqual(self.beacon.read_mode()[0], "pause")

    def test_leaving_the_mode_restores_the_resolved_task(self):
        # The pin outranked every provider (OVR-02), so what it froze is what the
        # session showed forever. With nothing pinned, the chain answers again.
        self.beacon.write_state("override.task", "a real label")
        self.beacon.cmd_pause(mock.Mock(note=[], clear_screen=False))
        self.beacon.cmd_resume(mock.Mock())
        self.assertEqual(self.beacon.read_mode()[0], "dev")
        self.assertIsNone(self.beacon.read_state("override.task"),
                          "resume drops the overrides it always did")


class EngagementMarker(BeaconTest):
    """BADGE-14: any apply() call places the per-pane engagement marker.
    `beacon clear` (no field) removes it and disengages the pane."""

    def test_apply_places_marker(self):
        marker = self.beacon._engagement_marker_path()
        self.assertIsNotNone(marker)
        self.assertFalse(marker.exists(), "marker should be absent pre-engagement")

        self.beacon.apply({**_base_state(), "activity": "idle"})

        self.assertTrue(marker.exists(), "apply() must place the engagement marker")

    def test_clear_no_field_disengages(self):
        # Engage first
        self.beacon.apply({**_base_state(), "activity": "working"})
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
        self.beacon.apply({**_base_state(), "mode": "pause"})
        self.cli_calls.clear()
        self.beacon.cmd_clear(mock.Mock(field=None))
        self.assertIn(("set-profile", "beacon-dev"), self.cli_calls,
                      "clear (no field) mid-mode must swap back to the base beacon-dev profile")

    def test_clear_with_field_keeps_engagement(self):
        self.beacon.apply({**_base_state(), "activity": "working"})
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
    branch slug alone, so the status-line link and the sessions-view chip read the
    same route. A route pinned to the session whose slug differs from the
    branch (a pin, not a branch-slug match) must still surface its deliverable
    URL; location correlation (via _tack_route_for) is the fallback."""

    ISSUE = "https://gl.test/acme/widgets/-/issues/2"

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
            return self.beacon._tack_url_for(Path("/tmp/fake"), branch, "widgets")
        finally:
            for p in patches: p.stop()

    def test_pin_resolves_even_when_slug_differs_from_branch(self):
        routes = [{
            "slug": "widget-cache-maintenance",
            "sessions": [{"id": "sid-1", "started_at": "2026-07-08T22:24:34Z"}],
            "tacks": [{"status": "in_progress",
                       "deliverable": {"label": "widgets#2", "url": self.ISSUE}}],
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
            self.beacon.apply({**_base_state(), "activity": "working"})
        kinds = [c[0] for c in self.cli_calls]
        self.assertIn("tab-color", kinds)
        self.assertNotIn("badge-color", kinds)
        self.assertNotIn("badge-format", kinds)

    def test_enabled_paints_badge(self):
        self.beacon.apply({**_base_state(), "activity": "working"})
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

    def _publish(self, url, project_full="gh:acme/widgets", route=()):
        with mock.patch.object(self.beacon, "_detect_branch_info",
                               return_value=("main", "clean", "", "default")), \
             mock.patch.object(self.beacon, "_project_full_at", return_value=project_full), \
             mock.patch.object(self.beacon, "_iterm_cache_key", return_value=None), \
             mock.patch.object(self.beacon, "_tack_landed_urls", return_value=set()), \
             mock.patch.object(self.beacon, "_tack_route_urls", return_value=list(route)), \
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


class TackRouteAcquisition(BeaconTest):
    """STATUSLINE-03 (#31): the bound tack route — not the branch resolver — is
    what feeds the row. PROV-07 answers "what does this branch point at", so
    work with no branch to be found by (an issue filed from the default branch,
    another project's deliverable the session crossed) reached it not at all.

    Acquisition is scoped to the current session: a route spans the project's
    lifetime and the row spans one Claude session. Offering the whole route made
    HOOK-08a's wipe pointless — the next hook refilled the row with the
    project's shipping history, which a long-lived route holds in full. What the
    scope keeps is the route's *open* work — `pending` as well as `in_progress`
    — since a route commonly carries the tack it is working as pending until
    ship time, and gating on `in_progress` alone emptied the row for whole
    sessions."""

    SESSION_START = "2026-08-03T16:00:00.000+00:00"

    ROUTE = {
        "slug": "cart-rework",
        "tacks": [
            # Shipped in an earlier session: the row must not claim it.
            {"mode": "done", "done_at": "2026-07-01T09:00:00.000Z",
             "deliverable": {"url": "https://github.com/acme/widgets/pull/21"},
             "links": [{"url": "https://github.com/acme/widgets/issues/20"}]},
            # Shipped during this session.
            {"mode": "done", "done_at": "2026-08-03T17:30:00.000Z",
             "deliverable": {"url": "https://github.com/acme/widgets/pull/30"},
             "links": [{"url": "https://github.com/acme/widgets/issues/29"}]},
            {"status": "in_progress",
             "links": [{"url": "https://github.com/other/otherproj/issues/9"},
                       {"url": "https://github.com/acme/widgets/issues/29"}]},
            # Filed, not started: its issue is what the open work answers.
            {"status": "pending",
             "links": [{"url": "https://github.com/acme/widgets/issues/32"}]},
        ],
    }

    def _urls(self, route, started=None):
        if started is not False:
            self.beacon.write_state("session_started_at", started or self.SESSION_START)
        with mock.patch.object(self.beacon, "_bound_tack_route", return_value=route):
            return self.beacon._tack_route_urls(Path("/x"), "topic", "widgets")

    def test_this_session_s_deliverables_and_links_gather_in_route_order(self):
        self.assertEqual(self._urls(self.ROUTE), [
            "https://github.com/acme/widgets/pull/30",
            "https://github.com/acme/widgets/issues/29",
            "https://github.com/other/otherproj/issues/9",
            "https://github.com/acme/widgets/issues/32",
        ])

    def test_work_delivered_before_the_session_is_left_off(self):
        urls = self._urls(self.ROUTE)
        self.assertNotIn("https://github.com/acme/widgets/pull/21", urls)
        self.assertNotIn("https://github.com/acme/widgets/issues/20", urls,
                         "a history tack's links go with its deliverable")

    def test_without_a_session_stamp_only_open_tacks_qualify(self):
        # A pane engaged before the stamp existed has no window to test against.
        # Fail toward a thin row rather than a stale one.
        self.assertEqual(self._urls(self.ROUTE, started=False), [
            "https://github.com/other/otherproj/issues/9",
            "https://github.com/acme/widgets/issues/29",
            "https://github.com/acme/widgets/issues/32",
        ])

    def test_a_pending_tack_reaches_the_row(self):
        # A route that marks its tack done only at ship time has nothing
        # in_progress for most of a session; gating on that alone left the row
        # empty exactly while the work was underway.
        route = {"slug": "cart-rework", "tacks": [
            {"status": "pending",
             "deliverable": {"url": "https://github.com/acme/widgets/pull/40"},
             "links": [{"url": "https://github.com/acme/widgets/issues/39"}]},
        ]}
        self.assertEqual(self._urls(route), [
            "https://github.com/acme/widgets/pull/40",
            "https://github.com/acme/widgets/issues/39",
        ])

    def test_no_bound_route_gathers_nothing(self):
        self.assertEqual(self._urls(None), [])

    LOCATION = ("https://github.com/acme/widgets", "widgets")

    def _publish(self, url, route=(), project_full="gh:acme/widgets",
                 bound=None, location=LOCATION):
        # _bound_tack_route is patched even when a test doesn't care: the
        # resolved-URL guard consults it, and unpatched it would shell out to the
        # developer's real `tack list`. _location_url_at likewise shells to git.
        with mock.patch.object(self.beacon, "_detect_branch_info",
                               return_value=("main", "clean", "", "default")), \
             mock.patch.object(self.beacon, "_project_full_at", return_value=project_full), \
             mock.patch.object(self.beacon, "_iterm_cache_key", return_value=None), \
             mock.patch.object(self.beacon, "_tack_landed_urls", return_value=set()), \
             mock.patch.object(self.beacon, "_bound_tack_route", return_value=bound), \
             mock.patch.object(self.beacon, "_tack_route_urls", return_value=list(route)), \
             mock.patch.object(self.beacon, "_location_url_at", return_value=location), \
             mock.patch.object(self.beacon, "resolve_url", return_value=(url, "label")):
            self.beacon._publish_chips(Path("/x"))

    def _entries(self):
        return self.beacon.read_state_json("deliverables", [])

    def test_an_issue_with_no_branch_reaches_the_row(self):
        # The motivating session: on `main`, no open PR, so PROV-07 fell through
        # to the bare repo URL and nothing was recorded.
        self._publish("https://github.com/acme/widgets",
                      route=["https://github.com/acme/widgets/issues/9"])
        self.assertEqual([e["ref"] for e in self._entries()], ["#9"])

    def test_each_entry_carries_the_project_its_own_url_names(self):
        # Stamping cwd's identity on a foreign ref renders another project's #9
        # as if it were local.
        self._publish("https://github.com/acme/widgets",
                      route=["https://github.com/other/otherproj/issues/9"])
        self.assertEqual(self._entries()[0]["project"], "gh:other/otherproj")

    def test_the_resolved_url_is_recorded_last(self):
        # It is the only entry with a live task to title it, and last is
        # furthest from the DELIVERABLES_MAX eviction edge.
        self._publish("https://github.com/acme/widgets/pull/42",
                      route=["https://github.com/acme/widgets/issues/9"])
        self.assertEqual([e["ref"] for e in self._entries()], ["#9", "#42"])

    def test_a_url_in_both_the_route_and_the_resolver_is_recorded_once(self):
        url = "https://github.com/acme/widgets/pull/42"
        self._publish(url, route=[url])
        self.assertEqual([e["ref"] for e in self._entries()], ["#42"])

    def test_a_resolution_that_shipped_in_an_earlier_session_is_not_recorded(self):
        # With no tack in_progress, PROV-07 falls through to the most recently
        # completed deliverable (_tack_url_for step b), so on a route with
        # nothing open it keeps naming work that shipped before this session.
        # Fine as a ↖ web click target, but recording it credits this session
        # with someone else's delivery — the symptom that read as a stale row.
        url = "https://github.com/acme/widgets/pull/33"
        self.beacon.write_state("session_started_at", self.SESSION_START)
        self._publish(url, bound={
            "slug": "beacon",
            "tacks": [{"mode": "done", "done_at": "2026-07-20T09:00:00.000Z",
                       "deliverable": {"url": url}}],
        })
        self.assertEqual(self._entries(), [])

    def test_a_resolution_delivered_during_the_session_is_recorded(self):
        url = "https://github.com/acme/widgets/pull/33"
        self.beacon.write_state("session_started_at", self.SESSION_START)
        self._publish(url, bound={
            "slug": "beacon",
            "tacks": [{"mode": "done", "done_at": "2026-08-03T17:00:00.000Z",
                       "deliverable": {"url": url}}],
        })
        self.assertEqual([e["ref"] for e in self._entries()], ["#33"])

    def test_a_resolution_that_shipped_earlier_is_kept_off_the_link(self):
        # Keeping it out of `deliverables` isn't enough on its own: the link
        # segment falls back to the resolved URL exactly when the row is empty, so
        # a fresh session on an idle route led with a PR that shipped days ago.
        # The location tiers answer instead. `↖ web` resolves at click time and
        # still gets PROV-07's own answer.
        url = "https://github.com/acme/widgets/pull/33"
        self.beacon.write_state("session_started_at", self.SESSION_START)
        self._publish(url, bound={
            "slug": "beacon",
            "tacks": [{"mode": "done", "done_at": "2026-07-20T09:00:00.000Z",
                       "deliverable": {"url": url}}],
        })
        self.assertEqual(self.beacon.read_state("resolved.url"), self.LOCATION[0])
        self.assertEqual(self.beacon.read_state("resolved.url_label"), self.LOCATION[1])

    def test_a_resolution_delivered_during_the_session_stays_on_the_link(self):
        url = "https://github.com/acme/widgets/pull/33"
        self.beacon.write_state("session_started_at", self.SESSION_START)
        self._publish(url, bound={
            "slug": "beacon",
            "tacks": [{"mode": "done", "done_at": "2026-08-03T17:00:00.000Z",
                       "deliverable": {"url": url}}],
        })
        self.assertEqual(self.beacon.read_state("resolved.url"), url)

    def test_the_substituted_location_can_itself_be_a_deliverable(self):
        # The location tiers lead with the forge probe, so a session working a
        # branch whose PR the route hasn't caught up with gets its own ref on the
        # row rather than the route's last delivery.
        self.beacon.write_state("session_started_at", self.SESSION_START)
        self._publish("https://github.com/acme/widgets/pull/33",
                      bound={
                          "slug": "beacon",
                          "tacks": [{"mode": "done", "done_at": "2026-07-20T09:00:00.000Z",
                                     "deliverable": {
                                         "url": "https://github.com/acme/widgets/pull/33"}}],
                      },
                      location=("https://github.com/acme/widgets/pull/40", "widgets#40"))
        self.assertEqual([e["ref"] for e in self._entries()], ["#40"])

    def test_a_resolution_the_route_does_not_hold_is_recorded(self):
        # The guard only rejects known-stale route deliverables. A branch or PR
        # the resolver found on its own is this session's work by construction.
        url = "https://github.com/acme/widgets/pull/99"
        self.beacon.write_state("session_started_at", self.SESSION_START)
        self._publish(url, bound={
            "slug": "beacon",
            "tacks": [{"mode": "done", "done_at": "2026-07-20T09:00:00.000Z",
                       "deliverable": {"url": "https://github.com/acme/widgets/pull/33"}}],
        })
        self.assertEqual([e["ref"] for e in self._entries()], ["#99"])

    def test_a_link_added_to_the_route_is_recorded(self):
        # A link added to the route moves neither the branch nor the resolved
        # URL, so a publish that looked only at those two would have nothing to
        # tell it the deliverable set grew.
        url = "https://github.com/acme/widgets/pull/42"
        self._publish(url, route=[])
        self._publish(url, route=["https://github.com/acme/widgets/issues/9"])
        self.assertEqual([e["ref"] for e in self._entries()], ["#9", "#42"])


class ProjectIdentityFromUrl(BeaconTest):
    """STATUSLINE-03 (#31): an entry's project is derived from its own URL, so a
    ref from another project renders qualified."""

    def test_github(self):
        self.assertEqual(
            self.beacon._project_id_from_url("https://github.com/acme/widgets/pull/42"),
            "gh:acme/widgets")

    def test_a_nested_gitlab_project_keeps_every_segment(self):
        self.assertEqual(
            self.beacon._project_id_from_url(
                "https://gitlab.com/acme/team/widgets/-/issues/7"),
            "gl:acme/team/widgets")

    def test_a_group_scoped_epic_resolves_to_the_group(self):
        self.assertEqual(
            self.beacon._project_id_from_url("https://gitlab.com/groups/acme/-/epics/7"),
            "gl:acme")

    def test_a_non_forge_string_resolves_to_nothing(self):
        self.assertEqual(self.beacon._project_id_from_url("not a url"), "")


class WorkItemAndTrackerRefs(BeaconTest):
    """STATUSLINE-03 (#31): GitLab renamed `/-/issues/<n>` to `/-/work_items/<n>`
    and the API hands back the new form; epics and milestones are the same class
    of thing a session crosses. Sigils follow GitLab's own reference syntax."""

    CASES = (
        ("https://gl.test/a/b/-/work_items/12", "#12", "issue"),
        ("https://gl.test/a/b/-/issues/12", "#12", "issue"),
        ("https://gl.test/groups/a/-/epics/3", "&3", "epic"),
        ("https://gl.test/a/b/-/milestones/5", "%5", "milestone"),
        ("https://gl.test/a/b/-/merge_requests/8", "!8", "cr"),
    )

    def test_ref_and_kind(self):
        for url, ref, kind in self.CASES:
            with self.subTest(url=url):
                self.assertEqual(self.beacon._deliverable_suffix(url), ref)
                self.assertEqual(self.beacon._deliverable_kind(url), kind)


class QualifyAgainstGroupScope(BeaconTest):
    """STATUSLINE-03: an epic or group milestone resolves to the group where the
    session resolves to a repo inside it, so exact comparison alone would render
    the tracker the work is filed under as another project's."""

    CASES = (
        ("gl:acme", "gl:acme/widgets", "&7", "own group's epic reads bare"),
        ("gl:acme/platform", "gl:acme/platform/widgets", "%2", "nested subgroup"),
        ("gh:acme/widgets", "gh:acme/widgets", "#32", "own repo"),
        ("", "gh:acme/widgets", "#9", "entry with no identity"),
    )

    def test_prefix_of_session_identity_reads_bare(self):
        for owner, project_id, ref, name in self.CASES:
            with self.subTest(case=name):
                entry = {"ref": ref, "project": owner}
                self.assertEqual(
                    self.beacon._qualify_deliverable(entry, project_id), ref)

    def test_boundary_keeps_lookalike_group_qualified(self):
        # Without the trailing slash `gl:acme` would prefix-match `gl:acmecorp/x`
        # and a genuinely foreign epic would read as local.
        entry = {"ref": "&7", "project": "gl:acmecorp"}
        self.assertEqual(
            self.beacon._qualify_deliverable(entry, "gl:acme/widgets"), "acmecorp:&7")

    def test_foreign_repo_still_qualifies(self):
        entry = {"ref": "#9", "project": "gh:other/proj"}
        self.assertEqual(
            self.beacon._qualify_deliverable(entry, "gh:acme/widgets"), "proj:#9")


class OriginUrlMemo(BeaconTest):
    """A single `_publish_chips` resolves the origin four times over. The remote
    cannot change inside a hook process, so the lookup is memoized per root."""

    def test_repeated_lookups_shell_out_once(self):
        completed = subprocess.CompletedProcess(
            [], 0, stdout="git@github.com:acme/widgets.git\n", stderr="")
        self.beacon._ORIGIN_URL_CACHE.clear()
        with mock.patch.object(self.beacon.subprocess, "run",
                               return_value=completed) as run:
            first = self.beacon._origin_url_at("/work/widgets")
            second = self.beacon._origin_url_at("/work/widgets")
        self.assertEqual(first, "git@github.com:acme/widgets.git")
        self.assertEqual(second, first)
        self.assertEqual(run.call_count, 1)

    def test_distinct_roots_are_cached_separately(self):
        self.beacon._ORIGIN_URL_CACHE.clear()
        outs = [subprocess.CompletedProcess([], 0, stdout=f"{r}.git\n", stderr="")
                for r in ("a", "b")]
        with mock.patch.object(self.beacon.subprocess, "run", side_effect=outs):
            self.assertEqual(self.beacon._origin_url_at("/work/a"), "a.git")
            self.assertEqual(self.beacon._origin_url_at("/work/b"), "b.git")

    def test_missing_origin_caches_empty(self):
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        self.beacon._ORIGIN_URL_CACHE.clear()
        with mock.patch.object(self.beacon.subprocess, "run",
                               return_value=failed) as run:
            self.assertEqual(self.beacon._origin_url_at("/work/bare"), "")
            self.assertEqual(self.beacon._origin_url_at("/work/bare"), "")
        self.assertEqual(run.call_count, 1)


class DropDeliverable(BeaconTest):
    """CMD-24 (#31): a wider acquisition path records refs the session only
    mentioned, and the row is capped — so noise left in place evicts real work."""

    URL = "https://github.com/acme/widgets/issues/9"

    def _touch(self, ref, url, project="gh:acme/widgets"):
        with mock.patch.object(self.beacon, "_tack_landed_urls", return_value=set()):
            self.beacon._record_deliverable(ref, url, project)

    def _drop(self, ref):
        self.beacon.cmd_drop(types.SimpleNamespace(ref=ref))

    def _refs(self):
        return [e["ref"] for e in self.beacon.read_state_json("deliverables", [])]

    def test_the_named_entry_goes_and_the_rest_stay(self):
        self._touch("#9", self.URL)
        self._touch("#42", "https://github.com/acme/widgets/pull/42")
        self._drop("#9")
        self.assertEqual(self._refs(), ["#42"])

    def test_a_qualified_ref_names_the_same_entry(self):
        # The row renders another project's entry qualified, so that is the
        # string the user has in front of them to type.
        self.beacon.write_state("resolved.project", "gh:acme/widgets")
        self._touch("#9", self.URL, project="gh:other/otherproj")
        self._drop("otherproj:#9")
        self.assertEqual(self._refs(), [])

    def test_a_dropped_entry_does_not_come_back(self):
        # The route is re-read every publish; without remembering the removal
        # the entry returns on the next turn and drop reads as broken.
        self._touch("#9", self.URL)
        self._drop("#9")
        self._touch("#9", self.URL)
        self.assertEqual(self._refs(), [])

    def test_an_unknown_ref_exits_nonzero(self):
        self._touch("#9", self.URL)
        with self.assertRaises(SystemExit) as ctx, \
             mock.patch.object(self.beacon.sys, "stderr", io.StringIO()):
            self._drop("#404")
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(self._refs(), ["#9"])

    def test_a_fresh_session_forgets_what_was_dropped(self):
        self._touch("#9", self.URL)
        self._drop("#9")
        self.beacon._wipe_session_for_fresh_start()
        self._touch("#9", self.URL)
        self.assertEqual(self._refs(), ["#9"])


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

    def test_default_is_a_bare_code_invocation(self):
        with self._config():
            self.assertEqual(self.beacon._code_launch_argv(), ["code"])

    def test_default_carries_no_option_the_vscode_cli_does_not_know(self):
        # An option VS Code's CLI doesn't recognize is forwarded to
        # Electron/Chromium, and on a cold start (no instance running) that
        # makes VS Code drop the directory positional and open a Welcome
        # window instead — so the button lands nowhere. `--maximized` was such
        # an option, and it never maximized either: VS Code has no CLI flag for
        # window state (that is `window.newWindowDimensions` in settings).
        # Ship a bare program; startup options are the user's to add knowingly.
        self.assertEqual([a for a in self.beacon._code_launch_argv() if a.startswith("-")], [])

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


class ProjectOutsideAProject(BeaconTest):
    """PROV-01 / PROV-06: the `dir` tier names a *project root*. Where no
    marker is found the chain falls through to the abbreviated path, so a
    session parked in a scratch directory reads as `/tmp`, not `tmp`."""

    def _root(self, *parts) -> Path:
        d = Path(self._tmp.name).joinpath("home", *parts)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_the_dir_tier_names_the_project_root(self):
        root = self._root("widgets")
        (root / ".git").mkdir()
        nested = self._root("widgets", "src")
        with mock.patch("pathlib.Path.home", return_value=root.parent):
            self.assertEqual(self.beacon.p_project_dir(nested), "widgets")

    def test_the_dir_tier_is_empty_without_a_marker(self):
        scratch = self._root("scratch")
        with mock.patch("pathlib.Path.home", return_value=scratch.parent):
            self.assertIsNone(self.beacon.p_project_dir(scratch))

    def test_the_chain_falls_through_to_the_path(self):
        # PROV-06's own worked example: `/tmp` renders as `/tmp`, not `tmp`.
        # Separators are normalized because the fallback is `str(cwd)`, which
        # a Windows runner renders with backslashes.
        with mock.patch.object(self.beacon, "p_git_remote", return_value=None), \
             mock.patch.object(self.beacon, "p_package_name", return_value=None):
            state = self.beacon.resolve(Path("/tmp"))
        self.assertEqual(state["project"].replace("\\", "/"), "/tmp")
        self.assertEqual(state["project_provider"], "pwd")

    def test_the_system_temp_dir_is_not_a_project(self):
        # macOS resolves `$TMPDIR` to a path ending in `/T`, so naming the bare
        # directory painted a session that had wandered there as project "T".
        tmpdir = Path("/private/var/folders/xm/w8qj7c7521x2w0dkkpl8b9zm0000gp/T")
        with mock.patch.object(self.beacon, "p_git_remote", return_value=None), \
             mock.patch.object(self.beacon, "p_package_name", return_value=None):
            state = self.beacon.resolve(tmpdir)
        self.assertEqual(state["project"], str(tmpdir))


class CompactionIsNotAFreshStart(BeaconTest):
    """HOOK-08: the anchor is the cwd Claude was *invoked* with. Claude Code
    re-fires SessionStart with `source` of `compact` (context rebuilt in place)
    and `fork` (a new id for the conversation already in the pane) — neither
    begins a session, and by then the payload carries wherever the agent has
    navigated, so adopting it repins the session onto a directory the work
    merely passed through."""

    def setUp(self):
        super().setUp()
        self.chip_cwds: list[str] = []
        p = mock.patch.object(
            self.beacon, "_publish_chips",
            side_effect=lambda cwd: self.chip_cwds.append(str(cwd).replace("\\", "/")),
        )
        p.start()
        self.addCleanup(p.stop)

    def _fire(self, source: str, cwd: str):
        args = mock.Mock(event="SessionStart")
        payload = {"cwd": cwd, "source": source}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            self.beacon.cmd_hook(args)

    def _anchor(self) -> str:
        return (self.beacon.read_state("anchor.cwd") or "").replace("\\", "/")

    def test_compaction_keeps_the_startup_anchor(self):
        self._fire("startup", "/work/acme/widget")
        self._fire("compact", "/private/var/folders/xm/abc/T")
        self.assertEqual(self._anchor(), "/work/acme/widget")

    def test_a_fork_keeps_the_startup_anchor(self):
        self._fire("startup", "/work/acme/widget")
        self._fire("fork", "/private/var/folders/xm/abc/T")
        self.assertEqual(self._anchor(), "/work/acme/widget")

    def test_compaction_keeps_the_pinned_label(self):
        self._fire("startup", "/work/acme/widget")
        self.beacon.write_state("override.task", "shipping the release")
        self._fire("compact", "/work/acme/widget")
        self.assertEqual(self.beacon.read_state("override.task"), "shipping the release")

    def test_compaction_keeps_the_acquisition_window(self):
        self._fire("startup", "/work/acme/widget")
        started = self.beacon.read_state("session_started_at")
        self.beacon.write_state("deliverables", json.dumps([{"ref": "#4"}]))
        self._fire("compact", "/work/acme/widget")
        self.assertEqual(self.beacon.read_state("session_started_at"), started)
        self.assertIsNotNone(self.beacon.read_state("deliverables"))

    def test_compaction_still_refreshes_the_chips(self):
        self._fire("startup", "/work/acme/widget")
        self.chip_cwds.clear()
        self._fire("compact", "/private/var/folders/xm/abc/T")
        self.assertEqual(self.chip_cwds, ["/work/acme/widget"])

    def test_a_fresh_start_still_reanchors(self):
        self._fire("startup", "/work/acme/widget")
        self._fire("clear", "/work/acme/other")
        self.assertEqual(self._anchor(), "/work/acme/other")

    def test_compaction_before_any_anchor_still_anchors(self):
        # A pane whose first beacon-visible event is a compaction has no anchor
        # to keep, so the payload cwd is the only navigational signal there is.
        self._fire("compact", "/work/acme/widget")
        self.assertEqual(self._anchor(), "/work/acme/widget")


class ANestedSessionDoesNotTakeThePane(BeaconTest):
    """HOOK-12: state keys on the pane GUID (§6.2), which a `claude` spawned
    from inside a live session inherits through ITERM_SESSION_ID. Its
    SessionStart must not wipe the host's signals or repin the host's anchor."""

    PANE = "w0t0p0:PANE-GUID"
    HOST = "host-session-id"
    GUEST = "guest-session-id"

    def setUp(self):
        super().setUp()
        os.environ["ITERM_SESSION_ID"] = self.PANE
        self.addCleanup(os.environ.pop, "CLAUDE_CODE_SESSION_ID", None)
        chips = mock.patch.object(self.beacon, "_publish_chips")
        chips.start()
        self.addCleanup(chips.stop)
        # Real directories: the wander check (HOOK-08c) shells to git against
        # the anchor cwd, and a path that does not exist raises there.
        self.host_cwd = self.data_dir / "host"
        self.guest_cwd = self.data_dir / "guest"
        self.other_cwd = self.data_dir / "other"
        for d in (self.host_cwd, self.guest_cwd, self.other_cwd):
            d.mkdir()

    def _fire(self, event: str, payload: dict):
        # Each hook is its own process in production, so it starts from the
        # pane id the shell exported — undo any re-key the last one made.
        os.environ["ITERM_SESSION_ID"] = self.PANE
        args = mock.Mock(event=event, type=None)
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            self.beacon.cmd_hook(args)

    def _host(self, field: str):
        return self.beacon._read_state_for(self.beacon._hash_seed("PANE-GUID"), field)

    def _guest(self, field: str):
        seed = f"claude-session:{self.GUEST}"
        return self.beacon._read_state_for(self.beacon._hash_seed(seed), field)

    def _start(self, sid: str, cwd, source: str = "startup"):
        self._fire("SessionStart", {"cwd": str(cwd), "source": source, "session_id": sid})

    def _start_host(self):
        self._start(self.HOST, self.host_cwd)

    def _start_guest(self):
        self._start(self.GUEST, self.guest_cwd)

    def test_guest_leaves_the_host_anchor_alone(self):
        self._start_host()
        self._start_guest()
        self.assertEqual(self._host("anchor.cwd"), str(self.host_cwd))
        self.assertEqual(self._host("claude_session_id"), self.HOST)

    def test_guest_gets_its_own_bucket(self):
        self._start_host()
        self._start_guest()
        self.assertEqual(self._guest("claude_session_id"), self.GUEST)
        self.assertEqual(self._guest("guest_of"), "PANE-GUID")

    def test_guest_does_not_wipe_the_host_signals(self):
        self._start_host()
        self.beacon.write_state("override.task", "shipping the release")
        self._start_guest()
        self.assertEqual(self._host("override.task"), "shipping the release")

    def test_the_guests_later_hooks_follow_it(self):
        self._start_host()
        self._fire("UserPromptSubmit", {"prompt": "go", "session_id": self.HOST})
        self._start_guest()
        self._fire("Stop", {"session_id": self.GUEST})
        self.assertEqual(self._host("activity"), "working")
        self.assertEqual(self._guest("activity"), "idle")

    def test_guest_records_no_focus_handle(self):
        # FOCUS-02: it owns no pane, so there is nothing for the dashboard to
        # raise — and the host's handle must survive its visit.
        self._start_host()
        self._start_guest()
        self.assertEqual(self._host("iterm_session_id"), "PANE-GUID")
        self.assertIsNone(self._guest("iterm_session_id"))

    def test_guest_leaves_the_host_engagement_marker(self):
        self._start_host()
        self._start_guest()
        self._fire("SessionEnd", {"reason": "other", "session_id": self.GUEST})
        os.environ["ITERM_SESSION_ID"] = self.PANE
        marker = self.beacon._engagement_marker_path()
        self.assertTrue(marker.exists())

    def test_clear_is_the_incumbent_restarting(self):
        # `/clear` leaves the marker down (HOOK-09 skips disengagement) and
        # arrives with a new session id — a guest's shape exactly, so the
        # source is what separates them.
        self._start_host()
        self._start("cleared-id", self.other_cwd, "clear")
        self.assertEqual(self._host("anchor.cwd"), str(self.other_cwd))
        self.assertEqual(self._host("claude_session_id"), "cleared-id")

    def test_a_disengaged_pane_is_free(self):
        self._start_host()
        self._fire("SessionEnd", {"reason": "other", "session_id": self.HOST})
        self._start("next-tenant", self.other_cwd)
        self.assertEqual(self._host("anchor.cwd"), str(self.other_cwd))
        self.assertEqual(self._host("claude_session_id"), "next-tenant")

    def test_the_first_session_in_a_pane_owns_it(self):
        self._start_host()
        self.assertEqual(self._host("anchor.cwd"), str(self.host_cwd))
        self.assertIsNone(self._host("guest_of"))


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
        self.assertEqual(self.beacon.read_state("activity"), "working")

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
        self.beacon.apply({**_base_state(), "mode": "done"})
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

    def test_exit_hands_the_session_name_back_to_the_interactive_title(self):
        # The bug: disengage blanks every user var TITLE_FORMAT interpolates
        # (beacon_project, beacon_task_nl, beacon_title_prefix) but left the
        # name pointing at that template, so the tab label and window title
        # rendered empty after `exit`. The shell's own source-time set-name is
        # a one-shot that already ran (and skipped, the pane being engaged), so
        # nothing reclaimed the name. Disengage must set it to the interactive
        # template the shell would have used.
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w0t0p0:ABC-123"}):
            self.beacon.render()
            self.cli_calls.clear()
            self._fire({"reason": "other"})
        name_call = ("set-name", "w0t0p0:ABC-123", self.beacon.INTERACTIVE_TITLE_FORMAT)
        self.assertIn(
            name_call, self.cli_calls,
            "Exit must hand the name back to the interactive title, not leave "
            "it on a template whose vars disengage just blanked",
        )
        # And after the profile swap: `SetProfile=` resets the name to the target
        # profile's own (RENDER-05), so a handback emitted first is wiped by it.
        self.assertGreater(
            self.cli_calls.index(name_call),
            self.cli_calls.index(("set-profile", "beacon-dev")),
            "the name handback must follow the profile swap, which resets the name",
        )

    def test_name_handback_precedes_blanking_the_title_vars(self):
        # Ordering is the difference between a benign interrupted disengage and a
        # permanently blank tab. `_cli` swallows failures, so a handback emitted
        # after the blanking has no retry: the pane keeps the managed template
        # with nothing to interpolate for the rest of its life. Blanking last
        # degrades to a stale label instead. Observed in the wild as a live pane
        # reading `name = <b></b>` with beacon_project already empty.
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w0t0p0:ABC-123"}):
            self.beacon.render()
            self.cli_calls.clear()
            self._fire({"reason": "other"})
        handback = self.cli_calls.index(
            ("set-name", "w0t0p0:ABC-123", self.beacon.INTERACTIVE_TITLE_FORMAT))
        for var in ("beacon_project", "beacon_task_nl", "beacon_title_prefix"):
            self.assertGreater(
                self.cli_calls.index(("uservar", var, "")), handback,
                f"{var} must be blanked after the name handback, not before",
            )

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
        self.beacon.write_state("activity", "working")

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

    def test_the_location_joins_the_project_on_line_one(self):
        # The badge is opt-in (BADGE-15), so on a default install the two-line
        # tab label is the only surface a wander has. The location belongs on
        # line 1 with the project it qualifies: on line 2 a bare " @ other" has
        # no antecedent, since the project it attaches to is on the line above.
        self._chdir(self.live_dir)
        self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_location"),
            [("uservar", "beacon_location", f" @ {self.live_dir.name}")],
            "Line 1 must carry the wandered location",
        )

    def test_line_one_keeps_the_project_pinned_beside_it(self):
        # BADGE-02: the location is added to the identity, never substituted for
        # it — the tab reads "<home> @ <where>", so the session still says which
        # project it belongs to.
        self._chdir(self.live_dir)
        self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"),
            [("uservar", "beacon_project", "acme/widget")],
            "The project slot must stay the anchor's, unqualified",
        )

    def test_the_task_line_never_carries_the_location(self):
        self.beacon.write_state("override.task", "my-task")
        self._chdir(self.live_dir)
        self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task_nl"),
            [("uservar", "beacon_task_nl", "\n  my-task")],
            "Line 2 is the unit of work; the location is line 1's",
        )

    def test_the_title_format_interpolates_the_location(self):
        # A var the template never reads would paint nothing at all.
        self.assertIn("beacon_location", self.beacon.TITLE_FORMAT)
        self.assertNotIn("beacon_location", self.beacon.BADGE_FORMAT,
                         "The badge is one line and recombines via beacon_task")

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
        # — the badge project stays pinned, and the single-line form carries the
        # location (the " @ " separator is applied at render, apply()).
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertEqual(state["project"], "acme/widget")
        self.assertEqual(state["task_provider"], "wander")
        self.assertEqual(state["task_display"], self.live_dir.name)
        # The location rides apart from the task because the tab gives them
        # different lines; with nothing pinned there is no task at all.
        self.assertEqual(state["location"], self.live_dir.name)
        self.assertEqual(state["task"], "")

    def test_wander_clears_at_rest(self):
        # PROV-02a: the marker is live working-state context. At rest (idle here,
        # but the same holds for blocked / paused) the task re-resolves from the
        # anchor and the marker is dropped — even though the live cwd is still
        # away. This is what removes the marker once a session comes home: the
        # returning turn's Stop renders at rest and clears it.
        self.beacon.write_state("activity", "idle")
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertNotEqual(
            state["task_provider"], "wander",
            "A session at rest must not carry the @marker, even while away",
        )

    def test_blocked_wander_does_not_freeze_marker(self):
        # The frozen-phantom case: a session that blocks on a prompt while away
        # must not persist an @marker into its snapshot (the sessions view reads it).
        self.beacon.write_state("pending-attention", "permission")
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertNotEqual(state["task_provider"], "wander")

    def test_paused_wander_does_not_freeze_marker(self):
        # `paused` is a distinct precedence branch in _logical_state_for (it
        # short-circuits above pending_attention), reachable only via
        # override.status — so it needs its own assertion that the busy-gate
        # drops the marker, not just the idle/blocked cases above.
        self.beacon.write_mode("pause")
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertNotEqual(
            state["task_provider"], "wander",
            "A paused session must not carry the @marker, even while away",
        )


class LinkedWorktreeIsNotAWander(BeaconTest):
    """PROV-02a: a linked worktree is the same project on another branch. It
    has its own project root, so a root comparison alone reads a sibling
    checkout as somewhere else entirely and paints the tab with the worktree's
    directory name — which for a tool-generated tree is an opaque id sitting
    where the unit of work belongs."""

    def setUp(self):
        super().setUp()
        self._home = tempfile.TemporaryDirectory()
        home = Path(self._home.name).resolve()
        self.addCleanup(self._home.cleanup)
        patcher = mock.patch.dict(os.environ, {"HOME": str(home)})
        patcher.start()
        self.addCleanup(patcher.stop)

        self.repo = home / "widgets"
        self.worktree = home / "widgets-9f2c1ab"
        self.unrelated = home / "unrelated"
        self._make_repo(self.repo, "git@github.com:acme/widgets.git")
        self._git("worktree", "add", "-q", "-b", "feature-x",
                  str(self.worktree), cwd=self.repo)
        self._make_repo(self.unrelated, "git@github.com:acme/unrelated.git")

        self.beacon.write_state("anchor.cwd", str(self.repo))
        self.beacon.write_state("activity", "working")

    @staticmethod
    def _git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True, text=True)

    def _make_repo(self, path: Path, origin: str):
        path.mkdir(parents=True)
        self._git("init", "-q", "-b", "main", cwd=path)
        self._git("config", "user.email", "t@t.test", cwd=path)
        self._git("config", "user.name", "Test", cwd=path)
        self._git("config", "commit.gpgsign", "false", cwd=path)
        self._git("remote", "add", "origin", origin, cwd=path)
        (path / "f.txt").write_text("hi\n")
        self._git("add", "-A", cwd=path)
        self._git("commit", "-qm", "init", cwd=path)

    def _chdir(self, path: Path):
        prev = os.getcwd()
        os.chdir(path)
        self.addCleanup(os.chdir, prev)

    def test_a_worktree_of_the_anchor_repo_paints_no_marker(self):
        self._chdir(self.worktree)
        self.beacon.render()
        emitted = _uservar_emits(self.cli_calls, "beacon_task")
        self.assertFalse(
            any("@" in call[2] for call in emitted),
            f"A sibling worktree must not read as a wander: {emitted}",
        )

    def test_the_worktree_directory_name_never_reaches_the_tab(self):
        self._chdir(self.worktree)
        self.beacon.render()
        for call in _uservar_emits(self.cli_calls, "beacon_task_nl"):
            self.assertNotIn(self.worktree.name, call[2],
                             "The generated worktree name must not caption the tab")

    def test_a_genuinely_different_repo_still_wanders(self):
        self._chdir(self.unrelated)
        self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", f" @ {self.unrelated.name}")],
            "Leaving the repository entirely is still a wander",
        )

    def test_same_repository_sees_through_the_worktree(self):
        self.assertTrue(self.beacon._same_repository(self.repo, self.worktree))
        self.assertFalse(self.beacon._same_repository(self.repo, self.unrelated))

    def test_same_repository_is_false_outside_a_repo(self):
        # A non-git directory has no shared git dir to match on, so it can never
        # be mistaken for the anchor's repository.
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.assertFalse(
            self.beacon._same_repository(self.repo, Path(scratch.name).resolve()))


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
            "_install_statusline": None,
            "_install_shell_source": None,
            "_service_install": True,
            "install_dynamic_profile": (True, "profile written"),
        }
        self.mocks = {}
        for name, val in returns.items():
            p = mock.patch.object(self.beacon, name, return_value=val)
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)

    def _run_install(self, dir=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.beacon.cmd_install(self.beacon.argparse.Namespace(dir=dir))
        return buf.getvalue()

    _ITERM_STEPS = ("_install_shell_source", "install_dynamic_profile")
    _ALWAYS_STEPS = ("_install_cli_wrapper", "_install_completions", "_install_statusline")

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
        self.assertIn("[3/3]", out)  # includes the status-line wiring step
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

    def test_dir_reaches_the_wrapper_step(self):
        # CMD-13: `--dir` moved onto install when install-cli retired, so it is
        # the only remaining way to place the wrapper outside ~/.local/bin.
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            self._run_install(dir="~/elsewhere/bin")
        self.assertEqual(self.mocks["_install_cli_wrapper"].call_args,
                         mock.call(Path("~/elsewhere/bin").expanduser()))

    def test_no_dir_leaves_the_wrapper_default(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            self._run_install()
        self.assertEqual(self.mocks["_install_cli_wrapper"].call_args, mock.call(None))

    def _run_install_with_layout(self, audit_rc: int, write_rc: int = 0):
        """Install with the layout audit and write stubbed, returning the output
        and the CLI argv install used. The real audit shells out to `defaults
        read`, so without this the closing line — and these tests — turn on
        whatever iTerm2 prefs the machine running the suite happens to have."""
        real_run = self.beacon.subprocess.run
        layout_calls = []

        def fake_run(cmd, *a, **k):
            if "configure" in cmd:
                layout_calls.append(cmd[cmd.index("configure"):])
                rc = write_rc if "--write" in cmd else audit_rc
                return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")
            return real_run(cmd, *a, **k)
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True), \
                mock.patch.object(self.beacon.subprocess, "run", side_effect=fake_run):
            return self._run_install(), layout_calls

    def test_install_completes_in_place(self):
        out, calls = self._run_install_with_layout(audit_rc=0)
        self.assertIn("no iTerm2 restart required", out)
        self.assertNotIn("DEFERRED", out)
        self.assertEqual(calls, [["configure"]],
                         "An aligned layout must not be written again")

    def test_a_drifted_layout_is_applied_not_just_reported(self):
        # CMD-08: these are app-wide prefs no dynamic profile can carry, so left
        # as advice they stayed drifted — the closing line read as "nothing left
        # to do" beneath a report saying otherwise.
        out, calls = self._run_install_with_layout(audit_rc=1, write_rc=0)
        self.assertEqual(calls, [["configure"], ["configure", "--write"]],
                         "Drift must be offered for writing, after the audit table")
        self.assertIn("no iTerm2 restart required", out)

    def test_a_declined_write_does_not_fail_the_install(self):
        # No tty to confirm on, or the user said no. The beacon-owned steps have
        # already landed, so declining is a complete answer — install reports the
        # layout as outstanding and names the command, rather than erroring.
        out, calls = self._run_install_with_layout(audit_rc=1, write_rc=1)
        self.assertIn(["configure", "--write"], calls)
        self.assertNotIn("no iTerm2 restart required", out)
        self.assertIn("need an iTerm2 restart", out)
        self.assertIn("beacon layout --write", out)


class StatuslineWiring(unittest.TestCase):
    """STATUSLINE-01: install wires `statusLine` into Claude Code's user
    settings.json, since nothing else makes the footer row exist. Left as a
    printed block, the step was skipped or applied to one project's
    settings.local.json, so the row was absent everywhere else. The write is
    scoped to that one key and never replaces a statusLine the user chose."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.beacon = _load_beacon(self.tmp)
        self.addCleanup(self._tmp.cleanup)
        self.settings = self.tmp / "settings.json"

    def _install(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.beacon._install_statusline(self.settings)
        return buf.getvalue()

    def _written(self):
        return json.loads(self.settings.read_text())

    def test_writes_the_block_when_absent(self):
        self.settings.write_text(json.dumps({"model": "opus"}))
        self._install()
        data = self._written()
        self.assertEqual(data["statusLine"]["command"], "beacon statusline")
        self.assertEqual(data["model"], "opus", "unrelated settings must survive")

    def test_creates_the_file_when_missing(self):
        self._install()
        self.assertEqual(self._written()["statusLine"]["command"], "beacon statusline")

    def test_an_existing_statusline_is_left_alone(self):
        mine = {"type": "command", "command": "my-own-prompt"}
        self.settings.write_text(json.dumps({"statusLine": mine}))
        out = self._install()
        self.assertEqual(self._written()["statusLine"], mine)
        self.assertIn("already defines a statusLine", out)
        self.assertIn("beacon statusline", out, "the block to paste is still shown")

    def test_rerun_is_a_no_op(self):
        self._install()
        out = self._install()
        self.assertIn("already wired", out)

    def test_unparseable_settings_are_not_clobbered(self):
        self.settings.write_text("{ not json")
        out = self._install()
        self.assertEqual(self.settings.read_text(), "{ not json")
        self.assertIn("unreadable", out)


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
        self.assertIn("beacon install", buf.getvalue())

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


class SessionsPayloadProject(BeaconTest):
    """The row reads the project the way the render chain does — override
    (OVR-01) above the anchor — so `beacon set project` repairs the tab and
    the sessions view together rather than leaving them disagreeing."""

    def _seed(self):
        sh = self.beacon.session_hash()
        self.beacon.write_state("anchor.project", "acme/widget")
        self.beacon.write_state("anchor.cwd", "/tmp/x")
        return sh

    def test_override_outranks_the_anchor(self):
        sh = self._seed()
        self.beacon.write_state("override.project", "widget-api")
        row = self.beacon._resolve_session(sh, compute_branch=False)
        self.assertEqual(row["project"], "widget-api")

    def test_the_anchor_answers_when_nothing_is_pinned(self):
        sh = self._seed()
        row = self.beacon._resolve_session(sh, compute_branch=False)
        self.assertEqual(row["project"], "acme/widget")


class SessionsPayloadColor(BeaconTest):
    """The /color signal is sessions-view metadata exposed in the wip payload."""

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
        self.assertEqual(self.beacon.read_mode()[0], "pause")

    def test_without_flag_does_not_clear(self):
        args = self.beacon.argparse.Namespace(note=[], clear_screen=False)
        self.beacon.cmd_pause(args)
        self.assertNotIn(("clear-screen",), self.cli_calls)
        self.assertEqual(self.beacon.read_mode()[0], "pause")


class JsonPayload(BeaconTest):
    """CMD-15: `beacon json` is the handoff contract another tool reads.

    It had no coverage before 2.5.0, which is how it came to ship three of the
    seven keys `resolve()` returns while documenting "signals, providers,
    description" — `jq -r .task` printed `null` unconditionally, and nothing
    failed."""

    def _payload(self):
        buf = io.StringIO()
        with mock.patch.object(self.beacon, "resolve_url", return_value=("", "")), \
                contextlib.redirect_stdout(buf):
            self.beacon.cmd_json(self.beacon.argparse.Namespace())
        return json.loads(buf.getvalue())

    def test_carries_every_signal_with_its_provider(self):
        self.beacon.write_state("override.task", "ship it")
        p = self._payload()
        self.assertEqual(p["task"], "ship it")
        self.assertEqual(p["task_provider"], "override")
        self.assertTrue(p["project"])
        self.assertTrue(p["project_provider"])

    def test_absent_task_is_null_with_a_null_provider(self):
        # RES-04: absent, not "". A consumer distinguishing "no task" from "a
        # task that resolved empty" needs the difference.
        with mock.patch.object(self.beacon, "p_pr_title", return_value=""), \
                mock.patch.object(self.beacon, "p_branch", return_value=""):
            p = self._payload()
        self.assertIsNone(p["task"])
        self.assertIsNone(p["task_provider"])

    def test_task_provider_distinguishes_a_branch_fallback(self):
        # The branch name is the task chain's third tier (PROV-02), so `task` and
        # `branch` are routinely byte-identical. Only the provider tells a chosen
        # label from a fallback, which is what anchor#2 needs to drop the dupe.
        with mock.patch.object(self.beacon, "p_pr_title", return_value=""), \
                mock.patch.object(self.beacon, "p_branch", return_value="my-branch"):
            p = self._payload()
        self.assertEqual(p["task"], p["branch"])
        self.assertEqual(p["task_provider"], "branch")

    def test_mode_is_the_nested_tuple(self):
        self.beacon.write_mode("release", "cutting v2.5")
        p = self._payload()
        self.assertEqual(p["mode"], {"name": "release", "note": "cutting v2.5",
                                     "glyph": self.beacon.MODE_SPECS["release"]["glyph"]})
        self.assertNotIn("note", p, "the note rides the mode, never a sibling key")

    def test_dev_cycle_reports_the_default_mode(self):
        p = self._payload()
        self.assertEqual(p["mode"], {"name": "dev", "note": "", "glyph": ""})

    def test_axes_are_separate_keys(self):
        self.beacon.write_mode("release", "")
        self.beacon.write_state("activity", "waiting")
        p = self._payload()
        self.assertEqual(p["mode"]["name"], "release")
        self.assertEqual(p["activity"], "waiting")

    def test_no_provider_key_for_either_axis(self):
        # One writer each, so naming a tier would invent a distinction (RES-06).
        p = self._payload()
        self.assertNotIn("mode_provider", p)
        self.assertNotIn("activity_provider", p)

    def test_merged_status_keys_are_gone(self):
        p = self._payload()
        for retired in ("status", "status_provider", "description"):
            self.assertNotIn(retired, p,
                             f"{retired} was removed in 2.5.0 with no alias — an "
                             "alias would re-merge the axes")

    def test_shape_matches_the_sessions_payload(self):
        """The two published payloads must describe `mode` identically.

        They diverged once: this one nested the tuple while `wip.json` emitted a
        flat `mode` string beside a top-level `note`. Same tool, same concept,
        two shapes — and a consumer reading both needed two accessors.
        """
        self.beacon.write_mode("retro", "writing it up")
        self.beacon.write_state("anchor.project", "acme/widget")
        self.beacon.write_state("anchor.cwd", str(self.data_dir))
        single = self._payload()["mode"]
        record = self.beacon._resolve_session(self.beacon.session_hash())
        self.assertIsNotNone(record, "the session must resolve into the sessions payload")
        self.assertEqual(single, record["mode"])
        self.assertEqual(sorted(single), ["glyph", "name", "note"])


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
        self.beacon.write_mode("pause", "waiting on CI")
        out = self._run()
        self.assertIn("waiting on CI", out)
        self.assertIn(self.beacon.MODE_SPECS["pause"]["glyph"], out)  # ⏸
        self.assertIn("\033[", out)  # ANSI color

    def test_not_paused_prints_nothing(self):
        self.beacon.write_state("activity", "working")
        self.assertEqual(self._run(), "")

    def test_paused_without_reason_prints_nothing(self):
        self.beacon.write_mode("pause")
        self.assertEqual(self._run(), "")

    def test_multiline_reason_collapsed_to_one_line(self):
        self.beacon.write_mode("pause", "line one\nline two")
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

    def test_an_epic_and_a_milestone_share_the_issue_line(self):
        # They are what the work is *for*, like an issue — so they trail the CRs
        # rather than each claiming a line and wrapping the row.
        self.beacon.write_state("resolved.project", "gl:acme/widgets")
        self._touch("!3", "https://gl.test/acme/widgets/-/merge_requests/3", "gl:acme/widgets")
        self._touch("&7", "https://gl.test/groups/acme/-/epics/7", "gl:acme")
        self._touch("%2", "https://gl.test/acme/widgets/-/milestones/2", "gl:acme/widgets")
        # `&7` bare: the epic's own group is where this repo lives, so the
        # tracker the work is filed under is not another project's.
        self.assertEqual(self._lines(), ["!3", "%2 · &7"])

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
        self.beacon.write_mode("pause", "waiting on CI")
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
            r"\(user.beacon_project_name)")
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


class PruneCollectsCacheFiles(BeaconTest):
    """WIP-06: prune sweeps the per-pane cache files, not just state. They key on
    the pane GUID while state keys on the hash — a one-way SHA-1 of that GUID —
    so the sweep goes by mtime. Before this, the cache grew a file per pane ever
    opened and nothing ever collected them."""

    OLD = 1_600_000_000.0

    def _seed(self):
        cd = self.beacon.CACHE_DIR
        cd.mkdir(parents=True, exist_ok=True)
        for name in ("cwd-STALE-GUID.txt", "engaged-STALE-GUID", "url-STALE-GUID.txt",
                     "cwd-FRESH-GUID.txt", "engaged-FRESH-GUID"):
            (cd / name).write_text("/some/path\n")
        for name in ("cwd-STALE-GUID.txt", "engaged-STALE-GUID", "url-STALE-GUID.txt"):
            os.utime(cd / name, (self.OLD, self.OLD))
        return cd

    def _prune(self):
        self.beacon.cmd_prune(self.beacon.argparse.Namespace(keep="30d"))

    def test_idle_cache_files_are_removed_and_recent_ones_kept(self):
        cd = self._seed()
        self._prune()
        self.assertFalse((cd / "cwd-STALE-GUID.txt").exists())
        self.assertFalse((cd / "engaged-STALE-GUID").exists())
        self.assertTrue((cd / "cwd-FRESH-GUID.txt").exists())
        self.assertTrue((cd / "engaged-FRESH-GUID").exists())

    def test_retired_url_handoff_files_are_collected(self):
        # No writer creates these since 2.0 moved `↖ web` to click-time
        # resolution, so every one on disk is a leftover no code reads.
        cd = self._seed()
        self._prune()
        self.assertFalse((cd / "url-STALE-GUID.txt").exists())

    def test_current_pane_is_kept_however_stale_its_files_look(self):
        # Mirrors the state sweep's current-session protection: collecting the
        # live pane's engagement marker would tell the shell it is unengaged and
        # let it clobber the name the plugin owns (BADGE-14, TITLE-04).
        cd = self._seed()
        for name in ("cwd-MINE.txt", "engaged-MINE"):
            (cd / name).write_text("")
            os.utime(cd / name, (self.OLD, self.OLD))
        with mock.patch.object(self.beacon, "_iterm_cache_key", return_value="MINE"):
            self._prune()
        self.assertTrue((cd / "cwd-MINE.txt").exists())
        self.assertTrue((cd / "engaged-MINE").exists())
        self.assertFalse((cd / "engaged-STALE-GUID").exists())

    def test_unrelated_cache_entries_are_left_alone(self):
        cd = self._seed()
        other = cd / "something-else.json"
        other.write_text("{}")
        os.utime(other, (self.OLD, self.OLD))
        self._prune()
        self.assertTrue(other.exists(),
                        "the sweep is scoped to the two per-pane filename shapes")


@unittest.skipIf(sys.platform == "win32",
                 "POSIX mode bits: Windows chmod sets only the read-only flag")
class StateFilePermissions(BeaconTest):
    """Everything beacon writes under DATA_DIR is owner-only. The state files
    carry `latest_turn` / `latest_turn_full` — the user's prompts and the
    agent's replies — so the process umask is the wrong thing to decide who can
    read them.

    Windows has no umask and no POSIX mode to assert: chmod there sets only the
    read-only flag, so every path reads back 0o666 / 0o777 whatever beacon
    passed. Access is an ACL question on that platform, which is why this class
    is POSIX-only — the finding it guards against, a second local account
    reading turn text out of a 0755 home, is a POSIX one.
    `BinaryWritesSurviveTheOpener` covers what `_open_private` still owes
    Windows."""

    def _mode(self, path):
        return stat.S_IMODE(Path(path).stat().st_mode)

    def test_state_dir_and_files_are_owner_only_under_a_permissive_umask(self):
        # umask(0) rather than the ambient one: otherwise the assertion passes
        # on the runner's umask rather than on anything the code does.
        old = os.umask(0)
        self.addCleanup(os.umask, old)
        self.beacon.write_state("task", "ship it")
        self.assertEqual(self._mode(self.beacon.STATE_DIR), 0o700)
        self.assertEqual(self._mode(self.beacon._state_path("task")), 0o600)

    def test_a_file_written_before_this_is_corrected_on_the_next_write(self):
        # An install predating the tightening keeps 0o644 for the life of the
        # file otherwise: `open`'s mode argument applies only at creation.
        self.beacon.write_state("task", "first")
        path = self.beacon._state_path("task")
        os.chmod(path, 0o644)
        self.beacon.write_state("task", "second")
        self.assertEqual(self._mode(path), 0o600)
        self.assertEqual(self.beacon.read_state("task"), "second")

    def test_a_widened_state_dir_is_corrected(self):
        self.beacon.write_state("task", "first")
        os.chmod(self.beacon.STATE_DIR, 0o755)
        self.beacon.write_state("task", "second")
        self.assertEqual(self._mode(self.beacon.STATE_DIR), 0o700)

    def test_error_log_is_owner_only(self):
        self.beacon.log_error("cli.render", "something failed")
        self.assertEqual(self._mode(self.beacon.LOGS_DIR), 0o700)
        self.assertEqual(self._mode(self.beacon.ERRORS_LOG), 0o600)

    def test_error_log_created_by_initialization_is_owner_only(self):
        # ensure_initialized creates the log empty so `doctor` can name a path
        # that exists — and it, not log_error, is what usually creates the file,
        # so an `open` mode in log_error alone never fires.
        os.umask(0o022)
        self.beacon.ensure_initialized()
        self.assertEqual(self._mode(self.beacon.ERRORS_LOG), 0o600)
        self.beacon.log_error("cli.render", "something failed")
        self.assertEqual(self._mode(self.beacon.ERRORS_LOG), 0o600)

    def test_a_log_left_world_readable_by_an_earlier_version_converges(self):
        self.beacon.log_error("cli.render", "first")
        os.chmod(self.beacon.ERRORS_LOG, 0o644)
        self.beacon.log_error("cli.render", "second")
        self.assertEqual(self._mode(self.beacon.ERRORS_LOG), 0o600)

    def test_initialization_creates_every_dir_owner_only(self):
        self.beacon.ensure_initialized()
        for d in (self.beacon.DATA_DIR, self.beacon.STATE_DIR,
                  self.beacon.CACHE_DIR, self.beacon.LOGS_DIR):
            self.assertEqual(self._mode(d), 0o700, d)

    def test_pane_cache_is_owner_only(self):
        # The per-pane handoff carries the session's cwd, and the shell probes
        # the engagement marker by existence — both need only the owner.
        with mock.patch.object(self.beacon, "_iterm_cache_key", return_value="GUID-1"):
            self.beacon.place_engagement_marker()
        self.assertEqual(self._mode(self.beacon.CACHE_DIR), 0o700)
        self.assertEqual(self._mode(self.beacon.CACHE_DIR / "engaged-GUID-1"), 0o600)

    def test_export_dump_is_owner_only(self):
        # A dump is every session's turn text in one file.
        self.beacon.write_state("latest_turn_full", "a private turn")
        dest = self.data_dir / "dump.json"
        self.beacon.cmd_export(self.beacon.argparse.Namespace(
            out_file=str(dest), compress=False))
        self.assertEqual(self._mode(dest), 0o600)

    def test_compressed_dump_is_owner_only_and_complete(self):
        # The gzip path writes through a raw fd, and a GzipFile does not close a
        # fileobj it was handed — so the round-trip is what proves the buffer
        # reached disk.
        self.beacon.write_state("latest_turn_full", "a private turn")
        dest = self.data_dir / "dump.json.gz"
        self.beacon.cmd_export(self.beacon.argparse.Namespace(
            out_file=str(dest), compress=True))
        self.assertEqual(self._mode(dest), 0o600)
        payload = json.loads(gzip.decompress(dest.read_bytes()))
        self.assertEqual(
            [rec["fields"]["latest_turn_full"] for rec in payload["sessions"]],
            ["a private turn"])


class BinaryWritesSurviveTheOpener(BeaconTest):
    """`_open_private` hands `os.fdopen` a raw descriptor, and on Windows a raw
    descriptor defaults to the CRT's text mode — which would translate newlines
    below the text layer that already translates them. These run everywhere:
    the platform that can break them is the one that skips
    `StateFilePermissions`, so nothing else would catch it."""

    def test_binary_bytes_round_trip_unmodified(self):
        raw = b"\r\n\x00\x1f gzip-ish \n\r payload \x8b"
        path = self.data_dir / "blob.bin"
        with self.beacon._open_private(path, "wb") as fh:
            fh.write(raw)
        self.assertEqual(path.read_bytes(), raw)

    def test_a_compressed_dump_round_trips(self):
        # The one production caller that writes binary through the opener.
        self.beacon.write_state("latest_turn_full", "line one\nline two")
        dest = self.data_dir / "dump.json.gz"
        self.beacon.cmd_export(self.beacon.argparse.Namespace(
            out_file=str(dest), compress=True))
        payload = json.loads(gzip.decompress(dest.read_bytes()))
        self.assertEqual(
            [r["fields"]["latest_turn_full"] for r in payload["sessions"]],
            ["line one\nline two"])

    def test_text_writes_read_back_as_written(self):
        self.beacon.write_state("task", "ship it")
        self.assertEqual(self.beacon.read_state("task"), "ship it")

    def test_appends_accumulate_one_record_per_line(self):
        for i in range(3):
            self.beacon.log_error("cli.render", f"failure {i}")
        self.assertEqual([r["detail"] for r in self.beacon.read_error_log()],
                         ["failure 0", "failure 1", "failure 2"])


class AutomaticStateSweep(BeaconTest):
    """WIP-06: the age sweep runs on the session's behalf at SessionStart.
    Reachable only as a CLI verb it went unrun, and state accumulated for every
    pane ever opened — turn text included — with nothing collecting it."""

    OLD = 1_600_000_000.0

    def _stale_session(self, sh="deadbeefdead"):
        sd = self.beacon.STATE_DIR
        self.beacon._mkdir_private(sd)
        p = sd / f"{sh}.latest_turn_full"
        self.beacon._write_private(p, "an old turn")
        os.utime(p, (self.OLD, self.OLD))
        return p

    def test_sweep_removes_state_idle_past_the_retention_window(self):
        p = self._stale_session()
        self.beacon._sweep_stale_state()
        self.assertFalse(p.exists())

    def test_sweep_keeps_recent_state(self):
        self.beacon.write_state("latest_turn_full", "a live turn")
        self.beacon._sweep_stale_state()
        self.assertEqual(self.beacon.read_state("latest_turn_full"), "a live turn")

    def test_sweep_is_throttled_by_its_stamp(self):
        self.beacon._sweep_stale_state()
        stamp = self.beacon.CACHE_DIR / self.beacon.PRUNE_STAMP
        self.assertTrue(stamp.exists())
        p = self._stale_session()
        self.beacon._sweep_stale_state()
        self.assertTrue(p.exists(), "a second sweep the same day should not scan")

    def test_sweep_runs_again_once_the_stamp_ages_out(self):
        self.beacon._sweep_stale_state()
        stamp = self.beacon.CACHE_DIR / self.beacon.PRUNE_STAMP
        aged = time.time() - self.beacon.PRUNE_INTERVAL_SECONDS - 1
        os.utime(stamp, (aged, aged))
        p = self._stale_session()
        self.beacon._sweep_stale_state()
        self.assertFalse(p.exists())

    def test_the_stamp_survives_the_cache_sweep(self):
        # _prune_cache enumerates the per-pane filename shapes; the stamp is not
        # one of them, and collecting it would make the throttle a no-op.
        self.beacon._sweep_stale_state()
        stamp = self.beacon.CACHE_DIR / self.beacon.PRUNE_STAMP
        os.utime(stamp, (self.OLD, self.OLD))
        self.beacon._prune_cache(time.time())
        self.assertTrue(stamp.exists())

    def test_sweep_cost_does_not_grow_with_session_count(self):
        """The sweep runs on a hook (NFR-01), so its directory reads must be a
        fixed number of whole-dir passes — not one glob per session, which is
        what `cmd_prune` did when it was only ever a CLI verb."""
        def scans_for(n):
            self.beacon._mkdir_private(self.beacon.STATE_DIR)
            for i in range(n):
                sh = f"{i:016x}"
                for field in ("anchor.project", "latest_turn_full"):
                    q = self.beacon.STATE_DIR / f"{sh}.{field}"
                    self.beacon._write_private(q, "old")
                    os.utime(q, (self.OLD, self.OLD))
            calls = []
            real = os.scandir
            with mock.patch.object(os, "scandir",
                                   side_effect=lambda p=".": calls.append(p) or real(p)):
                self.beacon._prune_state(time.time())
            return len(calls)

        few = scans_for(4)
        many = scans_for(60)
        self.assertEqual(few, many, "scan count must not scale with sessions")

    def test_a_failing_sweep_is_logged_not_raised(self):
        with mock.patch.object(self.beacon, "_prune_state",
                               side_effect=RuntimeError("disk gone")):
            self.beacon._sweep_stale_state()
        self.assertEqual([r["op"] for r in self.beacon.read_error_log()], ["prune.auto"])


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

    def test_no_flag_drift(self):
        """The subcommand list was guarded and the flags were not, so `--timing`,
        `--clear-screen`, and `--print` all shipped uncompletable while the
        edit-time hook was already nudging about "any subcommand or flag"."""
        b = self.beacon
        sub = next(a for a in b._build_parser()._actions
                   if isinstance(a, b.argparse._SubParsersAction))
        # Walked line by line rather than matched: arms nest their own `case`
        # (so a non-greedy `esac` stops inside one), and a short arm closes with
        # `;;` on its own line rather than below it.
        completed: dict[str, set] = {}
        current: list[str] = []
        for line in b.ZSH_COMPLETION.splitlines():
            header = b.re.match(r"^ {4}([a-z][a-z|-]*)\)", line)
            if header:
                current = header.group(1).split("|")
                for name in current:
                    completed.setdefault(name, set())
            elif b.re.match(r"^ {0,2}\S", line):
                current = []          # left the outer case body
            for flag in b.re.findall(r"(--[a-z][a-z-]*)", line):
                for name in current:
                    completed[name].add(flag)

        for name, parser in sub.choices.items():
            if name in b._UNCOMPLETED_COMMANDS:
                continue
            real = {o for a in parser._actions for o in a.option_strings
                    if o.startswith("--") and o != "--help"}
            with self.subTest(cmd=name):
                self.assertEqual(
                    completed.get(name, set()), real,
                    f"`{name}` completion flags drifted — missing: "
                    f"{sorted(real - completed.get(name, set()))}; "
                    f"stale: {sorted(completed.get(name, set()) - real)}",
                )


class DocsCiteRealPaths(unittest.TestCase):
    """Every repo-relative path a doc names in backticks must exist.

    Three tables went on citing `skills/` for releases after the directory was
    deleted and SPEC.md had recorded the plugin ships no skill — the kind of
    claim a reader trusts and no test was watching."""

    DOCS = ("README.md", "AGENTS.md", "docs/README.md", "docs/iterm.md",
            "docs/statusbar.md", "docs/palette.md", "docs/why.md", "docs/demo.md")

    # A backticked repo-relative path: it must carry a slash, which is what
    # separates `hooks/` and `iterm/make-bg.py` from a bare `config.json` that
    # names a file in the user's home.
    PATH_RE = re.compile(r"`([A-Za-z0-9_.][A-Za-z0-9_.-]*/[A-Za-z0-9_./-]*)`")

    # Directories belonging to iTerm2, Claude Code, or other projects' layouts.
    EXTERNAL_ROOTS = {"DynamicProfiles", "public", "static", "Application Support"}

    # Rendered by `shipyard build-docs` from SPEC.md, the rules, and the CLI
    # manifest, and gitignored — so they exist after a docs build and never in a
    # fresh checkout.
    GENERATED = {"docs/spec.md", "docs/rules/", "docs/skills/", "docs/guides/",
                 "docs/cli.md"}

    def test_every_cited_path_exists(self):
        missing = []
        for rel in self.DOCS:
            doc = REPO_ROOT / rel
            if not doc.exists():
                missing.append(f"{rel} (the doc itself)")
                continue
            body = doc.read_text(encoding="utf-8")
            for m in self.PATH_RE.finditer(body):
                cited = m.group(1)
                root = cited.split("/")[0]
                # A slash alone doesn't make a path: `origin/HEAD` is a git ref,
                # `chris-peterson/gitconfig` a repo slug, `StandardOut/ErrorPath`
                # a pair of plist keys. What marks a citation of *this* repo is a
                # trailing slash (a directory, which is the form that went stale)
                # or a first segment that is really a top-level entry.
                claims_repo = cited.endswith("/") or (REPO_ROOT / root).exists()
                if (not claims_repo
                        or cited.startswith(("~", "/", "http", "."))
                        or root in self.EXTERNAL_ROOTS
                        or any(cited.startswith(g) for g in self.GENERATED)):
                    continue
                if not (REPO_ROOT / cited).exists():
                    line = body[:m.start()].count("\n") + 1
                    missing.append(f"{rel}:{line} cites `{cited}`")
        self.assertEqual(missing, [], "docs cite paths that don't exist: " + "; ".join(missing))


class CrossWriterConstants(unittest.TestCase):
    """The plugin and the shell both emit the badge format and both activate the
    base profile, and the shell hardcodes each as a literal because a python
    call on the source path is what the raw-printf fast path exists to avoid.
    `scripts/beacon` says the two "must stay in sync" — this is what checks it."""

    def setUp(self):
        self.beacon = _load_beacon(REPO_ROOT / "tests")
        self.shell = (REPO_ROOT / "shell" / "beacon.zsh").read_text(encoding="utf-8")

    def test_badge_format_matches(self):
        self.assertIn(self.beacon.BADGE_FORMAT, self.shell)

    def test_base_profile_name_matches(self):
        self.assertIn(f"SetProfile={self.beacon.BASE_PROFILE_NAME}", self.shell)


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
        with mock.patch("subprocess.run", side_effect=fake_run), \
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

    def test_tab_bar_stays_visible_at_one_tab(self):
        # A single-pane window is where most sessions live, and iTerm2 hides the
        # tab bar there by default — taking the tab color and two-line label with
        # it, which is the whole per-pane signal.
        spec = self._spec("HideTab")
        self.assertEqual(spec["want"], "0")
        self.assertEqual(spec["type"], "bool")
        self.assertEqual(self.iterm._defaults_write_args(spec), ["-bool", "false"])

    def test_status_bar_sits_at_the_top(self):
        # The bottom of the pane is Claude Code's, where beacon renders its own
        # status line.
        self.assertEqual(self._spec("StatusBarPosition")["want"], "0")

    def _spec(self, key):
        for s in self.iterm.RECOMMENDED_LAYOUT:
            if s["key"] == key:
                return s
        self.fail(f"{key} is not in RECOMMENDED_LAYOUT")

    def test_never_writes_a_pref(self):
        # The bare form reads: the prefs themselves, and iTerm2's running state
        # to say whether those reads are the effective values. Nothing else, and
        # nothing that mutates — that boundary is what keeps it clear of the
        # plist-cache trap (§6.6).
        record = []
        self._run(self._aligned(), record=record)
        self.assertTrue(record)
        allowed = (["defaults", "read"], ["osascript", "-e"])
        for cmd in record:
            self.assertIn(list(cmd[:2]), [list(a) for a in allowed],
                          f"configure must only read, never write: {cmd}")
            self.assertNotIn("quit", cmd[-1], f"the audit must not act on iTerm2: {cmd}")


class ConfigureLayoutWrite(unittest.TestCase):
    """`configure --write` applies the layout without the Preferences GUI: it
    writes typed defaults only while iTerm2 is down, and when iTerm2 is up it
    hands off to a detached helper + quit rather than writing in-process (a
    running-iTerm2 write is clobbered on quit)."""

    def setUp(self):
        self.iterm = _load_beacon_iterm()

    def _args(self, **kw):
        return types.SimpleNamespace(**{"write": True, "yes": True, "keys": None, **kw})

    @staticmethod
    def _fake_run(calls, running: bool):
        """Stand-in for `subprocess.run` answering the osascript running-check
        with `running`, and everything else successfully."""
        def run(cmd, *a, **k):
            calls.append(cmd)
            out = ""
            if cmd[:1] == ["osascript"] and "is running" in cmd[-1]:
                out = "true" if running else "false"
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        return run

    @staticmethod
    def _quit_requested(calls) -> bool:
        return any(c[:1] == ["osascript"] and "quit" in c[-1] for c in calls)

    def test_running_check_reads_iterm_not_the_process_table(self):
        """`pgrep -x iTerm2` never matches the running app — macOS matches `-x`
        against the full executable path — and the false negative sends the
        write into a live iTerm2, which restores the old value on quit."""
        calls = []
        with mock.patch("subprocess.run", side_effect=self._fake_run(calls, True)):
            self.assertTrue(self.iterm._is_iterm_running())
        self.assertFalse(any(c[:1] == ["pgrep"] for c in calls),
                         "pgrep reports iTerm2 down while it is up")
        calls.clear()
        with mock.patch("subprocess.run", side_effect=self._fake_run(calls, False)):
            self.assertFalse(self.iterm._is_iterm_running())

    def test_apply_phase_writes_typed_defaults_then_relaunches(self):
        calls = []
        with mock.patch("subprocess.run", side_effect=self._fake_run(calls, False)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.iterm.cmd_configure(self._args(
                keys="TabViewType,UseCustomTabBarFontSize,CustomTabBarFontSize"))
        writes = {c[3]: c[4:] for c in calls if c[:2] == ["defaults", "write"]}
        self.assertEqual(writes["TabViewType"], ["-int", "2"])
        self.assertEqual(writes["UseCustomTabBarFontSize"], ["-bool", "true"])
        self.assertEqual(writes["CustomTabBarFontSize"], ["-float", "22"])
        self.assertTrue(any(c[:2] == ["open", "-a"] for c in calls))
        self.assertFalse(self._quit_requested(calls))

    def test_running_hands_off_to_helper_and_quits(self):
        calls, popen = [], []
        with mock.patch("subprocess.run", side_effect=self._fake_run(calls, True)), \
                mock.patch("subprocess.Popen",
                                  side_effect=lambda cmd, *a, **k: popen.append(cmd) or mock.Mock()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.iterm.cmd_configure(self._args(keys="StatusBarPosition"))
        self.assertEqual(len(popen), 1)
        helper = popen[0][-1]
        self.assertIn("configure --write --yes --keys", helper)
        self.assertIn("StatusBarPosition", helper)
        self.assertNotIn("pgrep", helper,
                         "the helper would fall through before iTerm2 finished quitting")
        self.assertIn("is running", helper)
        self.assertTrue(self._quit_requested(calls))
        self.assertFalse(any(c[:2] == ["defaults", "write"] for c in calls),
                         "must defer the write to the helper, not write while iTerm2 runs")

    def test_helper_log_path_is_unpredictable_and_owner_only(self):
        """A fixed name under TMPDIR lets another local user pre-create the path
        as a symlink and have the truncating open follow it. mkstemp creates the
        file itself, O_EXCL and 0600, and the printed path is the one it got."""
        calls, popen, tmp = [], [], tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        buf = io.StringIO()
        with mock.patch("subprocess.run", side_effect=self._fake_run(calls, True)), \
                mock.patch("subprocess.Popen",
                           side_effect=lambda cmd, *a, **k: popen.append(k) or mock.Mock()), \
                mock.patch.object(tempfile, "tempdir", tmp), \
                contextlib.redirect_stdout(buf):
            self.iterm.cmd_configure(self._args(keys="StatusBarPosition"))
        logs = list(Path(tmp).iterdir())
        self.assertEqual(len(logs), 1)
        self.assertNotEqual(logs[0].name, "beacon-configure.log",
                            "the name must not be derivable in advance")
        self.assertTrue(logs[0].name.startswith("beacon-configure."))
        if sys.platform != "win32":   # POSIX modes only — see StateFilePermissions
            self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)
        self.assertIn(str(logs[0]), buf.getvalue())

    def test_running_declined_makes_no_changes(self):
        calls, popen = [], []
        with mock.patch("subprocess.run", side_effect=self._fake_run(calls, True)), \
                mock.patch("subprocess.Popen",
                                  side_effect=lambda *a, **k: popen.append(a)), \
                mock.patch.object(self.iterm, "_prompt_tty", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()):
            self.iterm.cmd_configure(self._args(yes=False, keys="StatusBarPosition"))
        self.assertEqual(popen, [])
        self.assertFalse(self._quit_requested(calls))
        self.assertFalse(any(c[:2] == ["defaults", "write"] for c in calls))

    def test_no_drift_while_running_names_the_way_past_the_refusal(self):
        """The drift check reads the plist, which a live iTerm2 overwrites from
        memory — so "nothing to write" is not proof the tab strip agrees, and
        refusing without a way forward is the dead end that strands a setting."""
        calls = []
        buf = io.StringIO()
        with mock.patch("subprocess.run", side_effect=self._fake_run(calls, True)), \
                mock.patch.object(self.iterm, "_layout_drift", return_value=[]), \
                contextlib.redirect_stdout(buf):
            self.iterm.cmd_configure(self._args())
        out = buf.getvalue()
        self.assertIn("nothing to write", out)
        self.assertIn("iTerm2 is running", out)
        self.assertIn("--keys", out)
        self.assertFalse(any(c[:2] == ["defaults", "write"] for c in calls))


class LayoutAdviceNamesTheFrontDoor(unittest.TestCase):
    """CLI-18/CMD-28: `beacon` is the only interface a user types, so the advice
    the CLI prints names `beacon layout` whenever the plugin fronts it."""

    def setUp(self):
        self.iterm = _load_beacon_iterm()

    def test_defaults_to_its_own_invocation(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.iterm._advertised_command(), "beacon-iterm configure")

    def test_plugin_supplied_name_wins(self):
        with mock.patch.dict(os.environ, {"BEACON_LAYOUT_COMMAND": "beacon layout"}):
            self.assertEqual(self.iterm._advertised_command(), "beacon layout")

    def test_drift_advice_carries_it(self):
        def fake_run(cmd, *a, **k):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        buf = io.StringIO()
        with mock.patch("subprocess.run", side_effect=fake_run), \
                mock.patch.dict(os.environ, {"BEACON_LAYOUT_COMMAND": "beacon layout"}), \
                contextlib.redirect_stdout(buf), \
                self.assertRaises(SystemExit):
            self.iterm.cmd_configure(types.SimpleNamespace(write=False, yes=False, keys=None))
        self.assertIn("beacon layout --write", buf.getvalue())
        self.assertNotIn("beacon-iterm", buf.getvalue())


class AncestorTtyResolution(unittest.TestCase):
    """`_ancestor_tty` finds the pty to write OSC to when the process has no
    controlling terminal of its own — Claude Code spawns hook and Bash-tool
    subprocesses detached from theirs, so `/dev/tty` is ENXIO and every painted
    surface depends on this walk landing on an ancestor's pty."""

    def setUp(self):
        self.iterm = _load_beacon_iterm()

    def _ps(self, tree, calls=None):
        """Stand-in for `ps`, answering either invocation shape so the same
        assertions hold whether the walk asks per-pid or reads the tree once:
          per-pid    `ps -o tt=,ppid= -p <pid>`  -> "<tt> <ppid>"
          whole-tree `ps -eo pid=,ppid=,tt=`     -> "<pid> <ppid> <tt>" per row
        `tree` maps pid -> (ppid, tt), where tt is "??" for no terminal.
        """
        def run(argv, *a, **k):
            if calls is not None:
                calls.append(list(argv))
            flags = list(argv[1:])
            if "-p" in flags:
                pid = int(flags[flags.index("-p") + 1])
                if pid not in tree:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
                ppid, tt = tree[pid]
                return subprocess.CompletedProcess(
                    argv, 0, stdout=f"{tt} {ppid}\n", stderr="")
            rows = "".join(f"{p} {pp} {tt}\n" for p, (pp, tt) in sorted(tree.items()))
            return subprocess.CompletedProcess(argv, 0, stdout=rows, stderr="")
        return run

    @contextlib.contextmanager
    def _tree(self, tree, pid=100, devices=(), calls=None):
        """Run with `tree` as the process table, `pid` as our own pid, and only
        the ttys in `devices` present under /dev."""
        real_exists = os.path.exists

        def exists(path):
            if str(path).startswith("/dev/tty"):
                return str(path) in devices
            return real_exists(path)

        with mock.patch("subprocess.run", side_effect=self._ps(tree, calls)), \
                mock.patch.object(self.iterm.os, "getpid", return_value=pid), \
                mock.patch.object(self.iterm.os.path, "exists", side_effect=exists):
            yield

    def test_uses_the_processes_own_terminal_when_it_has_one(self):
        tree = {100: (50, "s001"), 50: (1, "??")}
        with self._tree(tree, devices=("/dev/ttys001",)):
            self.assertEqual(self.iterm._ancestor_tty(), "/dev/ttys001")

    def test_walks_up_to_the_first_ancestor_with_a_terminal(self):
        tree = {100: (90, "??"), 90: (80, "??"), 80: (1, "s004")}
        with self._tree(tree, devices=("/dev/ttys004",)):
            self.assertEqual(self.iterm._ancestor_tty(), "/dev/ttys004")

    def test_keeps_walking_past_an_ancestor_whose_device_is_gone(self):
        # A tt column naming a device that no longer exists must not end the
        # walk — the pty above it is still a live target.
        tree = {100: (90, "??"), 90: (80, "s004"), 80: (1, "s007")}
        with self._tree(tree, devices=("/dev/ttys007",)):
            self.assertEqual(self.iterm._ancestor_tty(), "/dev/ttys007")

    def test_gives_up_at_the_top_of_the_tree(self):
        tree = {100: (90, "??"), 90: (1, "??")}
        with self._tree(tree, devices=("/dev/ttys001",)):
            self.assertIsNone(self.iterm._ancestor_tty())

    def test_gives_up_when_no_ancestor_device_exists(self):
        tree = {100: (90, "s001"), 90: (1, "s002")}
        with self._tree(tree, devices=()):
            self.assertIsNone(self.iterm._ancestor_tty())

    def test_a_cycle_in_the_tree_terminates(self):
        # Self-parenting and loops are possible in a racing process table; the
        # walk must not spin.
        tree = {100: (90, "??"), 90: (100, "??")}
        with self._tree(tree, devices=()):
            self.assertIsNone(self.iterm._ancestor_tty())

    def test_returns_none_when_ps_cannot_be_run(self):
        with mock.patch("subprocess.run", side_effect=OSError("no ps")):
            self.assertIsNone(self.iterm._ancestor_tty())

    def test_returns_none_when_ps_exits_nonzero(self):
        def failing(argv, *a, **k):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")
        with mock.patch("subprocess.run", side_effect=failing):
            self.assertIsNone(self.iterm._ancestor_tty())

    def test_asks_only_about_the_ancestors_it_walks(self):
        # Targeted queries, never the whole process table: `ps -e` formats every
        # process on the box and measures ~2.5x worse than the two extra spawns
        # it would save, since the walk is only a few levels deep.
        calls = []
        tree = {100: (90, "??"), 90: (80, "??"), 80: (70, "s004"), 70: (1, "s009")}
        with self._tree(tree, devices=("/dev/ttys004",), calls=calls):
            self.assertEqual(self.iterm._ancestor_tty(), "/dev/ttys004")
        self.assertTrue(all("-p" in c for c in calls),
                        f"expected per-ancestor queries, got {calls}")
        # Stops at the match: pid 70 is never asked about.
        self.assertEqual([c[c.index("-p") + 1] for c in calls], ["100", "90", "80"])

    def test_a_cycle_costs_one_query_per_distinct_process(self):
        # Without a seen-set a loop burns the full 32-iteration cap, and each
        # iteration is a spawn.
        calls = []
        tree = {100: (90, "??"), 90: (100, "??")}
        with self._tree(tree, devices=(), calls=calls):
            self.assertIsNone(self.iterm._ancestor_tty())
        self.assertEqual(len(calls), 2, f"expected 2 ps spawns, got {len(calls)}")


def _base_state() -> dict:
    """Default state dict acceptable to apply(). Tests override individual fields.

    `mode` and `activity` are separate keys because they are separate axes: a test
    wanting "releasing, and blocked on the user" sets both, which is the whole
    point of the split.
    """
    return {
        "project": "acme/widget", "project_provider": "git-remote",
        "task": "", "task_provider": None,
        "mode": "dev", "note": "",
        "activity": "idle",
        "pending_attention": False,
    }


class ErrorLog(unittest.TestCase):
    """The error log exists because every external call beacon makes is
    swallowed (NFR-06), so a persistent failure is otherwise invisible."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.beacon = _load_beacon(self.data_dir)

    def test_log_error_writes_one_parseable_line(self):
        self.beacon.log_error("cli.set-name", "boom", exit_code=3)
        rows = self.beacon.read_error_log()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["op"], "cli.set-name")
        self.assertEqual(rows[0]["detail"], "boom")
        self.assertEqual(rows[0]["exit"], 3)
        self.assertTrue(rows[0]["at"].endswith("Z"))

    def test_detail_is_flattened_to_one_line(self):
        """Concurrent sessions append to one file, so a record must never span
        lines — a multi-line stderr would corrupt every later parse."""
        self.beacon.log_error("cli.focus", "line one\nline two\n\tindented")
        raw = (self.data_dir / "logs" / "errors.log").read_text()
        self.assertEqual(len(raw.strip().splitlines()), 1)
        self.assertEqual(self.beacon.read_error_log()[0]["detail"],
                         "line one line two indented")

    def test_detail_is_capped(self):
        self.beacon.log_error("cli.render", "x" * 5000)
        self.assertLessEqual(len(self.beacon.read_error_log()[0]["detail"]),
                             self.beacon._ERRORS_LOG_MAX_DETAIL)

    def test_log_is_trimmed_to_the_tail_when_it_grows(self):
        for i in range(4000):
            self.beacon.log_error("cli.render", f"failure {i}")
        size = (self.data_dir / "logs" / "errors.log").stat().st_size
        self.assertLessEqual(size, self.beacon._ERRORS_LOG_MAX_BYTES)
        rows = self.beacon.read_error_log()
        self.assertIn("failure 3999", rows[-1]["detail"])

    def test_unparseable_lines_are_skipped(self):
        self.beacon.log_error("cli.render", "real")
        log = self.data_dir / "logs" / "errors.log"
        with open(log, "a") as fh:
            fh.write("{torn half-written line\n")
        rows = self.beacon.read_error_log()
        self.assertEqual([r["detail"] for r in rows], ["real"])

    def test_missing_log_reads_as_empty(self):
        self.assertEqual(self.beacon.read_error_log(), [])

    def test_cli_logs_a_nonzero_exit_with_its_stderr(self):
        """The failure that motivated the log was a nonzero exit, not a thrown
        exception — `_cli` passes check=False, so only returncode catches it."""
        def fake_run(cmd, *a, **k):
            return subprocess.CompletedProcess(cmd, 1, stdout=b"",
                                               stderr=b"set-name: no session (3)")
        with mock.patch("subprocess.run", side_effect=fake_run):
            self.beacon._cli("set-name", "guid", "name")
        rows = self.beacon.read_error_log()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["op"], "cli.set-name")
        self.assertEqual(rows[0]["exit"], 1)
        self.assertIn("no session (3)", rows[0]["detail"])

    def test_cli_logs_an_exception(self):
        with mock.patch("subprocess.run", side_effect=OSError("no python3")):
            self.beacon._cli("render")
        rows = self.beacon.read_error_log()
        self.assertEqual(rows[0]["op"], "cli.render")
        self.assertIn("no python3", rows[0]["detail"])

    def test_cli_logs_nothing_on_success(self):
        def fake_run(cmd, *a, **k):
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        with mock.patch("subprocess.run", side_effect=fake_run):
            self.beacon._cli("render")
        self.assertEqual(self.beacon.read_error_log(), [])

    def test_a_throwing_provider_is_recorded(self):
        """NFR-05 keeps a throwing provider from blocking the chain; without a
        record the chain silently resolves to a lower tier forever."""
        def boom():
            raise RuntimeError("gh exploded")
        val, name = self.beacon.chain([("gh-pr", boom), ("fallback", lambda: "x")])
        self.assertEqual((val, name), ("x", "fallback"))
        rows = self.beacon.read_error_log()
        self.assertEqual(rows[0]["op"], "provider.gh-pr")
        self.assertIn("gh exploded", rows[0]["detail"])


class Doctor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.beacon = _load_beacon(self.data_dir)
        # The iTerm2 section shells out to osascript; these tests are about the
        # report, not the adapter, so stand the adapter down.
        for name in ("_is_iterm_installed", "_is_iterm_running"):
            pt = mock.patch.object(self.beacon, name, return_value=False)
            pt.start()
            self.addCleanup(pt.stop)

    def _run(self, **kw):
        args = types.SimpleNamespace(**{"since": "7d", "json": False, **kw})
        buf = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(buf):
                self.beacon.cmd_doctor(args)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_clean_install_reports_no_errors_and_exits_zero(self):
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("none recorded", out)

    def test_recorded_errors_are_grouped_with_a_count(self):
        for _ in range(3):
            self.beacon.log_error("cli.set-name", "no session (3)", exit_code=1)
        self.beacon.log_error("provider.gh-pr", "timeout")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("cli.set-name", out)
        self.assertIn("×3", out)
        self.assertIn("provider.gh-pr", out)

    def test_a_known_signature_carries_advice(self):
        self.beacon.log_error("cli.set-name", "no session (3)", exit_code=1)
        _, out = self._run()
        self.assertIn("tab label", out)

    def test_advice_falls_back_to_the_op_prefix(self):
        self.beacon.log_error("osascript.app-path", "timed out")
        _, out = self._run()
        self.assertIn("Automation", out)

    def test_since_window_filters_old_entries(self):
        self.beacon.log_error("cli.render", "ancient")
        log = self.data_dir / "logs" / "errors.log"
        log.write_text(log.read_text().replace(
            json.loads(log.read_text())["at"], "2001-01-01T00:00:00Z"))
        code, out = self._run(since="1d")
        self.assertEqual(code, 0)
        self.assertIn("none recorded", out)

    def test_json_carries_checks_and_errors(self):
        self.beacon.log_error("cli.render", "boom")
        args = types.SimpleNamespace(since="7d", json=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.beacon.cmd_doctor(args)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["checks"])
        self.assertEqual(payload["errors"][0]["detail"], "boom")
        self.assertTrue(payload["log"].endswith("errors.log"))

    def test_a_disagreeing_data_dir_pointer_is_a_failure(self):
        """The trap the pointer exists to prevent: hooks writing state that the
        wrapper, dashboard, and status line never read."""
        with mock.patch.object(self.beacon, "_read_data_dir_pointer",
                               return_value=Path("/somewhere/else")):
            checks = self.beacon._doctor_checks()
        pointer = [c for c in checks if c["name"] == "pointer"][0]
        self.assertEqual(pointer["status"], self.beacon._DOCTOR_BAD)

    def test_adapterless_box_is_not_a_failure(self):
        """iTerm2 is optional by design (NFR-06) — the sessions view is the
        terminal-agnostic half."""
        checks = self.beacon._doctor_checks()
        adapter = [c for c in checks if c["name"] == "adapter"][0]
        self.assertEqual(adapter["status"], self.beacon._DOCTOR_OK)


class ErrorLogCreatedEagerly(unittest.TestCase):
    """`doctor` prints the log's path, so the path has to be one the reader can
    open. A log that appears only once something has already failed is absent at
    exactly the moment someone goes looking for it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.beacon = _load_beacon(self.data_dir)

    def test_initialization_creates_an_empty_log(self):
        self.beacon.ensure_initialized()
        self.assertTrue(self.beacon.ERRORS_LOG.exists())
        self.assertEqual(self.beacon.read_error_log(), [])

    def test_initialization_does_not_truncate_an_existing_log(self):
        self.beacon.log_error("cli.render", "earlier failure")
        self.beacon._initialized = False
        self.beacon.ensure_initialized()
        self.assertEqual([r["detail"] for r in self.beacon.read_error_log()],
                         ["earlier failure"])

    def test_doctor_names_an_absent_log_as_absent(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            try:
                self.beacon.cmd_doctor(types.SimpleNamespace(since="7d", json=False))
            except SystemExit:
                pass
        self.assertIn("not created yet", buf.getvalue())

    def test_doctor_does_not_create_the_state_dir_it_checks(self):
        """Its own state check would be tautological if it initialized first."""
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=False):
            checks = self.beacon._doctor_checks()
        state = [c for c in checks if c["name"] == "state"][0]
        self.assertEqual(state["status"], self.beacon._DOCTOR_WARN)
        self.assertFalse(self.beacon.STATE_DIR.exists())


class ItermHandleGuard(unittest.TestCase):
    """The `iterm_session_id` state file is bytes on disk, and two plugin-side
    readers put it somewhere a quote is dangerous: `_iterm_session_reachable`
    interpolates it into AppleScript, and `doctor` prints it to a terminal.
    Both check it against ITERM_GUID_RE first."""

    INJECTION = '''" & (do shell script "touch /tmp/pwned") & "'''

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.beacon = _load_beacon(Path(self._tmp.name))
        self.beacon.STATE_DIR.mkdir(parents=True, exist_ok=True)

    def test_injected_handle_never_reaches_osascript(self):
        with mock.patch.object(self.beacon.subprocess, "run") as run:
            found, why = self.beacon._iterm_session_reachable(self.INJECTION)
        run.assert_not_called()
        self.assertFalse(found)
        self.assertEqual(why, "not a session id")

    def test_empty_handle_never_reaches_osascript(self):
        with mock.patch.object(self.beacon.subprocess, "run") as run:
            found, _ = self.beacon._iterm_session_reachable("")
        run.assert_not_called()
        self.assertFalse(found)

    def test_well_formed_handle_is_probed(self):
        with mock.patch.object(
                self.beacon.subprocess, "run",
                return_value=mock.Mock(returncode=0, stdout="found", stderr="")) as run:
            found, _ = self.beacon._iterm_session_reachable("ABC-123")
        self.assertTrue(found)
        self.assertEqual(run.call_args.args[0][0], "osascript")
        self.assertIn('set theID to "ABC-123"', run.call_args.args[0][2])

    def test_focus_refuses_an_injected_handle_without_spawning_the_cli(self):
        (self.beacon.STATE_DIR / "abcdef01.iterm_session_id").write_text(self.INJECTION)
        with mock.patch.object(self.beacon.subprocess, "run") as run:
            ok, msg = self.beacon._focus_session("abcdef01")
        run.assert_not_called()
        self.assertFalse(ok)
        # A handle that fails the shape check is no handle, so the answer is the
        # same one an unrecorded handle gets.
        self.assertEqual(msg, "not focusable")

    def test_payload_and_focus_agree_about_a_bad_handle(self):
        # Both go through _read_iterm_handle, so the dashboard cannot be shown a
        # focus button for a session /focus would then refuse.
        (self.beacon.STATE_DIR / "abcdef01.anchor.project").write_text("p")
        (self.beacon.STATE_DIR / "abcdef01.iterm_session_id").write_text(self.INJECTION)
        rec = next(s for s in self.beacon.collect_sessions(None)["sessions"]
                   if s["hash"] == "abcdef01")
        self.assertFalse(rec["focusable"])
        self.assertFalse(self.beacon._focus_session("abcdef01")[0])

    def test_a_malformed_env_handle_is_not_recorded(self):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w1t0p0:" + self.INJECTION}):
            self.beacon._record_focus_handle()
        self.assertIsNone(self.beacon.read_state("iterm_session_id"))

    def test_doctor_reports_a_bad_handle_without_quoting_it(self):
        self.beacon.write_state("iterm_session_id", self.INJECTION)
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True), \
                mock.patch.object(self.beacon, "_is_iterm_running", return_value=True), \
                mock.patch.object(self.beacon.subprocess, "run",
                                  return_value=mock.Mock(returncode=0, stdout="", stderr="")) as run:
            checks = self.beacon._doctor_checks()
        # doctor shells out for other checks (a `git describe`); what must not
        # happen is an osascript carrying the handle.
        self.assertEqual(
            [c for c in run.call_args_list if c.args and c.args[0][:1] == ["osascript"]], [])
        pane = [c for c in checks if c["name"] == "this pane"][0]
        self.assertEqual(pane["status"], self.beacon._DOCTOR_BAD)
        self.assertIn("not a session id", pane["detail"])
        self.assertNotIn("do shell script", pane["detail"])


class DevInstallMarker(unittest.TestCase):
    """A working tree and a marketplace install report the same manifest
    version, so nothing distinguishes an unreleased beacon from a released one
    until the version string says so."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.beacon = _load_beacon(self.data_dir)

    def test_a_working_tree_is_a_dev_install(self):
        """The suite runs from the repo, which has a git dir."""
        self.assertTrue(self.beacon._is_dev_install())

    def test_an_extracted_install_is_not(self):
        installed = self.data_dir / "installed"
        (installed / ".claude-plugin").mkdir(parents=True)
        (installed / ".claude-plugin" / "plugin.json").write_text('{"version": "9.9.9"}')
        with mock.patch.object(self.beacon, "PLUGIN_ROOT", installed):
            self.assertFalse(self.beacon._is_dev_install())
            self.assertEqual(self.beacon._version_display(), "9.9.9")

    def test_a_dev_version_carries_the_marker_and_the_ref(self):
        def fake_run(cmd, *a, **k):
            return subprocess.CompletedProcess(cmd, 0, stdout="da64585-dirty\n", stderr="")
        with mock.patch.object(self.beacon, "_is_dev_install", return_value=True), \
                mock.patch.object(self.beacon, "_plugin_version", return_value="2.6.1"), \
                mock.patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(self.beacon._version_display(), "2.6.1-dev+da64585-dirty")

    def test_the_status_line_carries_no_marker(self):
        """The row is per-session work that varies; an install's version is
        static, so it would cost attention every prompt and say the same thing."""
        with mock.patch.object(self.beacon, "_is_dev_install", return_value=True):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), \
                    mock.patch.object(self.beacon.sys, "stdin", io.StringIO("{}")):
                self.beacon.cmd_statusline(types.SimpleNamespace())
        self.assertNotIn("dev", buf.getvalue())

    def test_an_unreadable_ref_still_says_dev(self):
        """The marker is the point; the ref is the detail. Losing git must not
        make a dev copy look released."""
        def fake_run(cmd, *a, **k):
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a git repo")
        with mock.patch.object(self.beacon, "_is_dev_install", return_value=True), \
                mock.patch.object(self.beacon, "_plugin_version", return_value="2.6.1"), \
                mock.patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(self.beacon._version_display(), "2.6.1-dev")
        self.assertEqual(self.beacon.read_error_log()[0]["op"], "git.describe")


class SubscribedSkillEntersItsMode(BeaconTest):
    """HOOK-13: a subscribed skill's invocation declares the phase, on both
    shapes the invocation arrives in. anchor has no idea beacon is listening."""

    def _skill_call(self, skill):
        args = mock.Mock(event="PostToolUse")
        payload = json.dumps({"tool_name": "Skill", "tool_input": {"skill": skill}})
        with mock.patch.object(sys, "stdin", io.StringIO(payload)):
            self.beacon.cmd_hook(args)

    def _typed(self, prompt):
        args = mock.Mock(event="UserPromptSubmit")
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": prompt}))):
            self.beacon.cmd_hook(args)

    def test_the_agent_invoking_it_enters_release(self):
        self._skill_call("anchor:release")
        self.assertEqual(self.beacon.read_mode()[0], "release")

    def test_the_user_typing_it_enters_release(self):
        # The shape the retired HOOK-11 subscriber never saw: a typed slash
        # command fires no Skill tool call at all.
        self._typed("/anchor:release")
        self.assertEqual(self.beacon.read_mode()[0], "release")

    def test_the_bare_name_enters_release(self):
        self._typed("/release minor")
        self.assertEqual(self.beacon.read_mode()[0], "release")

    def test_an_unsubscribed_skill_declares_nothing(self):
        self._skill_call("anchor:commit")
        self.assertEqual(self.beacon.read_mode()[0], self.beacon.DEV_MODE)

    def test_mentioning_the_command_declares_nothing(self):
        self._typed("run /anchor:release once the pipeline is green")
        self.assertEqual(self.beacon.read_mode()[0], self.beacon.DEV_MODE)

    def test_a_longer_name_sharing_the_prefix_declares_nothing(self):
        self._typed("/releases")
        self.assertEqual(self.beacon.read_mode()[0], self.beacon.DEV_MODE)

    def test_it_leaves_pause_the_way_the_prompt_does(self):
        # Auto-resume runs first on this prompt; the declaration outlives it.
        self.beacon.write_mode("pause", "waiting for VPN")
        self._typed("/anchor:release")
        self.assertEqual(self.beacon.read_mode(), ("release", ""))

    def test_re_entry_keeps_a_note_already_set(self):
        # Both hooks can fire for one invocation and the skill can be invoked
        # twice, so the reaction must be safe to repeat (RES-07).
        self.beacon.write_mode("release", "2.8.0")
        self._skill_call("anchor:release")
        self._typed("/anchor:release")
        self.assertEqual(self.beacon.read_mode(), ("release", "2.8.0"))

    def test_the_activity_axis_is_untouched(self):
        # RES-06: declaring a mode says nothing about what the hooks observed.
        self._typed("/anchor:release")
        self.assertEqual(self.beacon.read_activity(), "working")


if __name__ == "__main__":
    unittest.main()

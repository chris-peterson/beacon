"""Behavior tests for scripts/beacon.

The plugin script has no .py extension, so we load it via importlib. Each test
gets a fresh DATA_DIR (tempdir) and a mocked `_cli` so we can assert which OSC
calls would have fired.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
import tempfile
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
    project value changes, and clear any stale drift suffix on that pass."""

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

    def test_drift_cleared_on_project_change(self):
        # Establish drift state from a prior pass
        self.beacon.apply({**_base_state(), "project": "acme/widget"})
        self.beacon.write_state("drift.active", "1")
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "project": "custom-label"})

        self.assertIn(
            ("uservar", "beacon_project_drift", ""), self.cli_calls,
            "Project change must clear beacon_project_drift",
        )
        self.assertFalse(self.beacon._state_path("drift.active").exists())

    def test_task_only_change_does_not_touch_badge(self):
        self.beacon.apply({**_base_state(), "project": "acme/widget"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "project": "acme/widget", "task": "different",
        })

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"), [],
            "Task change must not republish beacon_project",
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

    def test_set_task_does_not_touch_badge(self):
        self.beacon.render()
        self.cli_calls.clear()

        args = mock.Mock(field="task", value=["my-task"])
        self.beacon.cmd_set(args)

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"), [],
            "set task must not touch beacon_project (task isn't on the badge)",
        )


class DriftSelfHealing(BeaconTest):
    """HOOK-09a: missing anchor must be adopted, not treated as drift."""

    def test_adopts_anchor_when_none_set(self):
        # No anchor.project on disk; _publish_drift should write it and
        # emit no suffix.
        self.beacon._publish_drift(self.data_dir)

        self.assertEqual(
            self.beacon.read_state("anchor.project"), "acme/widget",
            "Anchor should be auto-established on first observation",
        )
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project_drift"), [],
            "Anchor adoption must not emit a drift suffix",
        )

    def test_matching_anchor_clears_active_drift(self):
        self.beacon.write_state("anchor.project", "acme/widget")
        self.beacon.write_state("drift.active", "1")

        self.beacon._publish_drift(self.data_dir)

        self.assertIn(
            ("uservar", "beacon_project_drift", ""), self.cli_calls,
            "Matching project must clear an active drift suffix",
        )
        self.assertFalse(self.beacon._state_path("drift.active").exists())

    def test_mismatch_emits_suffix(self):
        self.beacon.write_state("anchor.project", "other/repo")

        # cwd basename determines the suffix label
        target = self.data_dir / "wandered-in"
        target.mkdir()
        self.beacon._publish_drift(target)

        emits = _uservar_emits(self.cli_calls, "beacon_project_drift")
        self.assertEqual(emits, [("uservar", "beacon_project_drift", ":wandered-in")])
        self.assertTrue(self.beacon._state_path("drift.active").exists())

    def test_no_project_no_action(self):
        # When the cwd has no project identity at all, _publish_drift should
        # be inert — neither adopt nor emit. (Mirrors a cwd outside any repo.)
        with mock.patch.object(self.beacon, "_project_name_at", return_value=""):
            self.beacon._publish_drift(self.data_dir)

        self.assertIsNone(self.beacon.read_state("anchor.project"))
        self.assertEqual(_uservar_emits(self.cli_calls, "beacon_project_drift"), [])

    def test_suffix_matching_anchor_tail_is_suppressed(self):
        # HOOK-09b: anchor=`my-proj`, current cwd resolves to a different
        # project name (so the names disagree → drift fires by the old rule)
        # but the cwd basename happens to also be `my-proj`. The suffix
        # would read `my-proj:my-proj` — meaningless. Suppress it.
        self.beacon.write_state("anchor.project", "my-proj")
        target = self.data_dir / "my-proj"
        target.mkdir()
        with mock.patch.object(self.beacon, "_project_name_at",
                                return_value="other/my-proj"):
            self.beacon._publish_drift(target)

        suffix_emits = _uservar_emits(self.cli_calls, "beacon_project_drift")
        # Either no emit at all, or an explicit clear — both are acceptable;
        # the contract is "no `:my-proj` annotation".
        for call in suffix_emits:
            self.assertEqual(
                call[2], "",
                "Suffix matching the anchor's last segment must be suppressed",
            )
        self.assertFalse(self.beacon._state_path("drift.active").exists())

    def test_anchor_with_slash_compares_by_tail(self):
        # Anchor `owner/my-proj`; cwd basename `my-proj`. Tail of anchor is
        # `my-proj` — same as the basename, so the suffix is suppressed.
        self.beacon.write_state("anchor.project", "owner/my-proj")
        target = self.data_dir / "my-proj"
        target.mkdir()
        with mock.patch.object(self.beacon, "_project_name_at",
                                return_value="other-resolver-output"):
            self.beacon._publish_drift(target)

        suffix_emits = [c for c in _uservar_emits(self.cli_calls, "beacon_project_drift")
                        if c[2]]
        self.assertEqual(
            suffix_emits, [],
            "Anchor tail match (owner/my-proj → my-proj) must suppress the suffix",
        )


class ApplyEmitsProfileSwitch(BeaconTest):
    """BADGE-09 + RENDER-04: status transitions among ready/busy/blocked/drifted
    are delivered via `set-profile beacon-<state>`, never via the per-session
    badge-color/tab-color OSC pair (those are reserved for paused — the only
    state that overlays rather than switches)."""

    def test_first_render_emits_ready_profile(self):
        self.beacon.apply({**_base_state(), "status": "idle"})

        self.assertIn(
            ("set-profile", "beacon-ready"), self.cli_calls,
            "First render with idle status must SetProfile=beacon-ready",
        )

    def test_status_transition_emits_profile(self):
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "working"})

        self.assertIn(
            ("set-profile", "beacon-busy"), self.cli_calls,
            "idle → working must SetProfile=beacon-busy",
        )
        for call in self.cli_calls:
            self.assertNotEqual(
                call[0], "badge-color",
                "Non-paused transitions must NOT emit badge-color (profile owns it)",
            )

    def test_unchanged_state_emits_nothing(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "working"})

        set_profile_calls = [c for c in self.cli_calls if c[0] == "set-profile"]
        self.assertEqual(
            set_profile_calls, [],
            "Identical state must not re-emit set-profile",
        )

    def test_drift_emits_drifted_profile(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "status": "working", "drift_active": True,
        })

        self.assertIn(("set-profile", "beacon-drifted"), self.cli_calls)


class PausedUsesOSCOverlay(BeaconTest):
    """BADGE-10 + RENDER-04 + §6.6: paused state is exempt from profile
    switching. The plugin overlays badge-color, tab-color, and note image
    via OSC on top of whatever profile is currently active."""

    def test_entering_pause_emits_osc_overlay(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "status": "idle", "paused": True,
            "note_image": "/tmp/note.png",
        })

        paused_hex = self.beacon.BADGE_COLOR_PALETTE["paused"]
        self.assertIn(("badge-color", paused_hex), self.cli_calls)
        self.assertIn(("tab-color", paused_hex), self.cli_calls)
        self.assertIn(("bg-image", "/tmp/note.png"), self.cli_calls)
        for call in self.cli_calls:
            self.assertNotEqual(
                call[0], "set-profile",
                "Entering pause must not switch profiles — overlay only",
            )

    def test_leaving_pause_emits_set_profile_only(self):
        # The set-profile call atomically wipes the OSC overlay; no
        # explicit `bg-image clear` should be needed.
        self.beacon.apply({
            **_base_state(), "status": "working", "paused": True,
            "note_image": "/tmp/note.png",
        })
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "working", "paused": False})

        self.assertIn(("set-profile", "beacon-busy"), self.cli_calls)
        bg_clears = [c for c in self.cli_calls
                     if c[0] == "bg-image" and (len(c) < 2 or c[1] == "clear")]
        self.assertEqual(
            bg_clears, [],
            "Resume must rely on set-profile's atomic wipe, not bg-image clear",
        )


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
        self.assertIn(("set-profile", "beacon"), self.cli_calls,
                      "clear (no field) must return to the base profile")
        self.assertIn(("uservar", "beacon_project", ""), self.cli_calls,
                      "clear (no field) must empty the badge text")

    def test_clear_with_field_keeps_engagement(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        marker = self.beacon._engagement_marker_path()
        self.assertTrue(marker.exists())

        self.beacon.cmd_clear(mock.Mock(field="project"))

        self.assertTrue(
            marker.exists(),
            "per-field clear must NOT disengage — engagement persists across overrides",
        )


def _base_state() -> dict:
    """Default state dict acceptable to apply(). Tests override individual fields."""
    return {
        "project": "acme/widget", "project_provider": "git-remote",
        "task": "", "task_provider": "default",
        "stage": "none", "stage_provider": "default",
        "status": "idle", "status_provider": "default",
        "paused": False,
        "pending_attention": False,
        "drift_active": False,
        "note_image": None,
    }


if __name__ == "__main__":
    unittest.main()

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
    """BADGE-13: apply() must republish beacon_project when the resolved
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

    def test_first_render_skips_emit(self):
        # _publish_anchor (HOOK-08) paints beacon_project at SessionStart;
        # the first apply() pass should not re-paint redundantly.
        self.beacon.apply({**_base_state(), "project": "acme/widget"})

        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_project"), [],
            "First render must not emit beacon_project — HOOK-08 already painted it",
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

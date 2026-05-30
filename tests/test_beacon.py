"""Behavior tests for scripts/beacon.

The plugin script has no .py extension, so we load it via importlib. Each test
gets a fresh DATA_DIR (tempdir) and a mocked `_cli` so we can assert which OSC
calls would have fired.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
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
            [("uservar", "beacon_task", ": different")],
            "Task change must publish beacon_task with leading ': ' separator",
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
            [("uservar", "beacon_task", ": my work")],
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
            [("uservar", "beacon_task", ": my-task")],
            "set task must publish beacon_task so the badge shows the new value",
        )


class ApplyEmitsProfileSwitch(BeaconTest):
    """BADGE-09 + RENDER-04: status transitions among ready/busy/blocked are
    delivered via `set-profile beacon-<state>`, never via the per-session
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

class PendingAttentionPicksWatermarkProfile(BeaconTest):
    """BADGE-09a + BADGE-15: the pending-attention marker forces the blocked
    color state, and the recorded subtype picks the watermark — `permission`
    routes to `beacon-blocked` (`!`), `idle` routes to `beacon-blocked-idle`
    (`?`). Both keep the red palette; only the watermark differs."""

    def test_permission_subtype_emits_blocked_profile(self):
        self.beacon.apply({
            **_base_state(),
            "status": "waiting",
            "pending_attention": True,
            "pending_attention_type": "permission",
        })
        self.assertIn(("set-profile", "beacon-blocked"), self.cli_calls)
        self.assertNotIn(("set-profile", "beacon-blocked-idle"), self.cli_calls)

    def test_idle_subtype_emits_blocked_idle_profile(self):
        self.beacon.apply({
            **_base_state(),
            "status": "waiting",
            "pending_attention": True,
            "pending_attention_type": "idle",
        })
        self.assertIn(("set-profile", "beacon-blocked-idle"), self.cli_calls)
        self.assertNotIn(("set-profile", "beacon-blocked"), self.cli_calls)

    def test_missing_subtype_defaults_to_blocked(self):
        # Defensive: a pending-attention marker without an explicit subtype
        # falls back to the permission watermark (the highest-urgency case).
        self.beacon.apply({
            **_base_state(),
            "status": "waiting",
            "pending_attention": True,
            "pending_attention_type": None,
        })
        self.assertIn(("set-profile", "beacon-blocked"), self.cli_calls)

    def test_subtype_transition_emits_new_profile(self):
        self.beacon.apply({
            **_base_state(),
            "status": "waiting",
            "pending_attention": True,
            "pending_attention_type": "idle",
        })
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(),
            "status": "waiting",
            "pending_attention": True,
            "pending_attention_type": "permission",
        })

        self.assertIn(
            ("set-profile", "beacon-blocked"), self.cli_calls,
            "Idle → permission must re-emit set-profile so the watermark swaps",
        )


class DescriptionOverlay(BeaconTest):
    """OVERLAY-01 + RENDER-04: a non-empty description triggers the OSC
    marginalia overlay (badge-color, tab-color, bg-image + clear-screen)
    on top of whatever profile is active. Clearing the description goes
    back to the profile-driven path."""

    def test_paused_with_description_emits_osc_overlay(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "status": "paused",
            "description": "leaving for lunch",
            "note_image": "/tmp/note.png",
        })

        paused_hex = self.beacon.BADGE_COLOR_PALETTE["paused"]
        self.assertIn(("badge-color", paused_hex), self.cli_calls)
        self.assertIn(("tab-color", paused_hex), self.cli_calls)
        self.assertIn(("bg-image", "/tmp/note.png"), self.cli_calls)
        # OVERLAY-01: the viewport is cleared after the bg-image paint so
        # the marginalia card has a clean canvas instead of fighting the
        # active TUI's overlaid text.
        self.assertIn(("clear-screen",), self.cli_calls)
        bg_idx = self.cli_calls.index(("bg-image", "/tmp/note.png"))
        clear_idx = self.cli_calls.index(("clear-screen",))
        self.assertLess(bg_idx, clear_idx,
                        "clear-screen must follow bg-image so the image is in place "
                        "before the viewport is wiped")
        for call in self.cli_calls:
            self.assertNotEqual(
                call[0], "set-profile",
                "Entering an overlay must not switch profiles — OSC only",
            )

    def test_paused_without_description_emits_osc_not_profile(self):
        # RENDER-04 / BADGE-10: bare `pause` (no note) has no static profile
        # to switch to — paused must paint via OSC badge-color/tab-color, not
        # SetProfile to a nonexistent `beacon-paused`.
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "paused"})

        paused_hex = self.beacon.BADGE_COLOR_PALETTE["paused"]
        self.assertIn(("badge-color", paused_hex), self.cli_calls)
        self.assertIn(("tab-color", paused_hex), self.cli_calls)
        for call in self.cli_calls:
            self.assertNotEqual(
                call[0], "set-profile",
                "Bare pause must not switch profiles (no beacon-paused exists)",
            )
        bg_calls = [c for c in self.cli_calls if c[0] == "bg-image"]
        self.assertEqual(bg_calls, [], "Bare pause paints no marginalia card")

    def test_dropping_note_while_staying_paused_clears_card(self):
        # described+paused → bare paused: no SetProfile fires to wipe the bg
        # image, so apply() must clear it explicitly or the stale card lingers.
        self.beacon.apply({
            **_base_state(), "status": "paused",
            "description": "stepping out", "note_image": "/tmp/note.png",
        })
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "paused"})

        self.assertIn(("bg-image", "clear"), self.cli_calls)
        for call in self.cli_calls:
            self.assertNotEqual(
                call[0], "set-profile",
                "Staying paused must not switch profiles",
            )

    def test_blocked_idle_with_description_uses_red_hex(self):
        # THEME-02: blocked-idle shares the red palette. With a description,
        # the OSC overlay must paint red, not fall back to paused gray.
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "status": "idle",
            "pending_attention": True, "pending_attention_type": "idle",
            "description": "waiting on you",
            "note_image": "/tmp/note.png",
        })

        red = self.beacon.BADGE_COLOR_PALETTE["blocked-idle"]
        self.assertIn(("badge-color", red), self.cli_calls)
        self.assertIn(("tab-color", red), self.cli_calls)

    def test_waiting_with_description_uses_blocked_hex(self):
        # `status waiting "bg refresh"` reuses the blocked palette so the
        # at-a-glance color signal still says "this session is parked on
        # something" — the description carries the why.
        self.beacon.apply({**_base_state(), "status": "idle"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "status": "waiting",
            "description": "bg refresh ~30 min",
            "note_image": "/tmp/note.png",
        })

        blocked_hex = self.beacon.BADGE_COLOR_PALETTE["blocked"]
        self.assertIn(("badge-color", blocked_hex), self.cli_calls)
        self.assertIn(("tab-color", blocked_hex), self.cli_calls)
        self.assertIn(("bg-image", "/tmp/note.png"), self.cli_calls)

    def test_clearing_description_emits_set_profile_only(self):
        # set-profile atomically wipes the OSC overlay; no explicit
        # `bg-image clear` should be needed.
        self.beacon.apply({
            **_base_state(), "status": "paused",
            "description": "leaving",
            "note_image": "/tmp/note.png",
        })
        self.cli_calls.clear()

        self.beacon.apply({**_base_state(), "status": "working"})

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
        self.assertIn(("uservar", "beacon_task", ""), self.cli_calls,
                      "clear (no field) must empty the task slot so a stale "
                      "task doesn't linger on the badge after disengagement")

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

    def test_profile_template_badge_text_matches_badge_format(self):
        # The dynamic profile's "Badge Text" is the canonical badge format
        # iTerm uses while the beacon profile is active. It must stay in sync
        # with BADGE_FORMAT — a drift here means OSC SetBadgeFormat writes get
        # overridden whenever the plugin switches profiles (BADGE-09).
        template = (REPO_ROOT / "iterm" / "profile.json.template").read_text()
        self.assertIn(
            r"\(user.beacon_task)", template,
            'profile.json.template "Badge Text" must reference user.beacon_task '
            "to match BADGE_FORMAT",
        )


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
            side_effect=lambda cwd: self.chip_cwds.append(str(cwd)),
        )
        p.start()
        self.addCleanup(p.stop)

    def _fire(self, event: str, payload: dict):
        args = mock.Mock(event=event)
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            self.beacon.cmd_hook(args)

    def test_session_start_persists_anchor(self):
        self._fire("SessionStart", {"cwd": "/work/acme/widget", "source": "startup"})
        self.assertEqual(self.beacon.read_state("anchor.cwd"), "/work/acme/widget")
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

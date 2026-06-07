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


class ApplyEmitsBaseProfileAndColor(BeaconTest):
    """RENDER-04 / §6.6: the first render switches into the single base
    `beacon` profile and sets the badge format; state color is delivered by
    OSC badge-color/tab-color, not a per-state profile. Subsequent renders
    repaint color only when the logical state changes."""

    def test_first_render_switches_base_profile_and_sets_ready_color(self):
        self.beacon.apply({**_base_state(), "status": "idle"})

        self.assertIn(("set-profile", "beacon"), self.cli_calls,
                      "First render must switch into the base beacon profile")
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
            [c for c in self.cli_calls if c[0] == "set-profile" and c[1] != "beacon"],
            [],
            "No per-state profile switch — blocked is an OSC color",
        )


class DescriptionIsFleetData(BeaconTest):
    """STATE-02: a description is persisted and surfaced in the fleet view; it
    paints no per-pane surface. apply() emits only the logical-state OSC color
    — never bg-image, note, or clear-screen (the overlay is retired)."""

    def test_paused_with_description_paints_only_color(self):
        self.beacon.apply({**_base_state(), "status": "working"})
        self.cli_calls.clear()

        self.beacon.apply({
            **_base_state(), "status": "paused",
            "description": "leaving for lunch",
        })

        paused_hex = self.beacon.BADGE_COLOR_PALETTE["paused"]
        self.assertIn(("badge-color", paused_hex), self.cli_calls)
        self.assertIn(("tab-color", paused_hex), self.cli_calls)
        for verb in ("bg-image", "note", "clear-screen"):
            self.assertEqual(
                [c for c in self.cli_calls if c[0] == verb], [],
                f"a description must not emit {verb} (overlay retired)",
            )

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
        self._anchor_dir = tempfile.TemporaryDirectory()
        self._live_dir = tempfile.TemporaryDirectory()
        self.anchor_dir = Path(self._anchor_dir.name).resolve()
        self.live_dir = Path(self._live_dir.name).resolve()
        self.addCleanup(self._anchor_dir.cleanup)
        self.addCleanup(self._live_dir.cleanup)
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
        # No override and the live tmp dir is not a git repo, so the marker
        # stands alone: @<wandered-project-basename>.
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"),
            [("uservar", "beacon_task", f": @{self.live_dir.name}")],
            "Wandered location must surface in the task slot as an @ marker",
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
            [("uservar", "beacon_task", f": @{self.live_dir.name}: my-task")],
            "An override must survive a wander as the text behind the @ marker",
        )

    def test_subdirectory_of_anchor_is_not_a_wander(self):
        # PROV-02a gates on project *root*: navigating into a subdirectory of the
        # anchored project resolves to the same root, so no wander overlay fires.
        # find_project_root's own marker walk only runs under $HOME, so mock it
        # to a fixed root for both operands — the contract under test is the
        # root comparison in the gate, not find_project_root's home boundary.
        with mock.patch.object(self.beacon, "find_project_root",
                               side_effect=lambda p: Path("/proj/root")):
            self.beacon.render()
        self.assertEqual(
            _uservar_emits(self.cli_calls, "beacon_task"), [],
            "Same project root (subdirectory nav) must not trigger the wander task",
        )

    def test_show_and_badge_share_wander_resolution(self):
        # CMD-01 / BADGE-12: `show` must report what the badge paints. Both go
        # through _resolve_for_display, so a wander reflects identically in both
        # — the badge project stays pinned, the task carries the @ marker.
        self._chdir(self.live_dir)
        state = self.beacon._resolve_for_display()
        self.assertEqual(state["project"], "acme/widget")
        self.assertEqual(state["task_provider"], "wander")
        self.assertEqual(state["task"], f"@{self.live_dir.name}")

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
            p.read_text() for p in self.beacon.STATE_DIR.glob("*.anchor.cwd")
        )
        self.assertEqual(
            anchors, ["/work/ai-sdlc", "/work/beacon"],
            "empty ITERM_SESSION_ID must not collapse distinct Claude sessions "
            "onto one shared state bucket",
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
        self.assertIn("[1/2]", out)
        self.assertIn("beacon wip", out)
        self.assertIn("beacon serve install", out)

    def test_full_runs_every_step(self):
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True):
            out = self._run_install()
        for name in (*self._ALWAYS_STEPS, *self._ITERM_STEPS):
            self.assertTrue(self.mocks[name].called, f"{name} should run")
        self.assertFalse(self.mocks["_service_install"].called,
                         "the serve service is opt-in; install must not start it")
        self.assertIn("[4/4]", out)

    def test_install_completes_in_place(self):
        # 1.0 pivot: no pref needs iTerm2 quit, so install emits no
        # deferred-action notice.
        with mock.patch.object(self.beacon, "_is_iterm_installed", return_value=True):
            out = self._run_install()
        self.assertIn("no iTerm2 restart required", out)
        self.assertNotIn("DEFERRED", out)


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

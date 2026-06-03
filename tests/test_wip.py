"""Behavior tests for the cross-session `wip` / `serve` export surfaces.

Like test_beacon.py, the script is loaded via importlib with a fresh tempdir
DATA_DIR. These tests write raw `<hash>.<field>` state files directly (the
shape hooks leave on disk) and assert collect_sessions / cmd_serve read,
correlate, and window-filter them correctly.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.request
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
    loader = importlib.machinery.SourceFileLoader("beacon", str(BEACON_PATH))
    spec = importlib.util.spec_from_loader("beacon", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class WipTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.beacon = _load_beacon(self.data_dir)
        self.state_dir = self.beacon.STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Isolate tack correlation from the developer's real ~/.tack.
        self._tack_tmp = tempfile.TemporaryDirectory()
        self.tack_home = Path(self._tack_tmp.name)
        (self.tack_home / "routes").mkdir(parents=True)
        tack_patcher = mock.patch.object(self.beacon, "TACK_HOME", self.tack_home)
        tack_patcher.start()
        self.addCleanup(tack_patcher.stop)
        self.addCleanup(self._tack_tmp.cleanup)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, sh: str, field: str, value: str, mtime: float | None = None):
        p = self.state_dir / f"{sh}.{field}"
        p.write_text(value)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def _route_file(self, slug: str, group: str | None = None, sessions=None):
        body = f"slug: {slug}\n" + (f"group: {group}\n" if group else "")
        if sessions:
            body += "sessions:\n"
            for sid, started in sessions:
                body += f"  - id: {sid}\n    started_at: {started}\n"
        (self.tack_home / "routes" / f"{slug}.yaml").write_text(body)

    def _sessions(self, since=None):
        return self.beacon.collect_sessions(since)["sessions"]

    # --- enumeration + resolve ---

    def test_enumerates_anchored_sessions(self):
        self._write("aaa", "anchor.project", "alpha")
        self._write("aaa", "signal.status", "working")
        self._write("bbb", "anchor.project", "beta")
        self._write("bbb", "claude_session_id", "sid-beta")

        sessions = self._sessions()
        projects = {s["project"] for s in sessions}
        self.assertEqual(projects, {"alpha", "beta"})
        alpha = next(s for s in sessions if s["project"] == "alpha")
        self.assertEqual(alpha["status"], "working")
        self.assertEqual(alpha["state"], "busy")

    def test_drops_sessions_without_a_location(self):
        # Only a claude_session_id, no project/cwd anchor → not a work stream.
        self._write("ghost", "claude_session_id", "sid-ghost")
        self._write("ghost", "signal.status", "working")
        self.assertEqual(self._sessions(), [])

    def test_one_record_per_claude_session_newest_wins(self):
        # A session resumed in a new pane leaves its prior pane's state
        # bucket behind; both buckets carry the same Claude session id.
        # WIP-01: one record per session — most recently active bucket wins.
        old = time.time() - 3600
        self._write("oldpane", "anchor.project", "proj", mtime=old)
        self._write("oldpane", "claude_session_id", "sid-moved", mtime=old)
        self._write("newpane", "anchor.project", "proj")
        self._write("newpane", "claude_session_id", "sid-moved")

        sessions = self._sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session"], "sid-moved")
        self.assertEqual(sessions[0]["hash"], "newpane")

    def test_panes_without_session_id_are_not_collapsed(self):
        # An empty session id is "unknown pane tenant", not a join key —
        # two id-less panes must both emit.
        self._write("aaa", "anchor.project", "p1")
        self._write("bbb", "anchor.project", "p2")
        self.assertEqual(len(self._sessions()), 2)

    # --- status → logical state ---

    def test_status_maps_to_logical_state(self):
        self._write("s1", "anchor.project", "p1")
        self._write("s1", "override.status", "paused")
        self._write("s2", "anchor.project", "p2")
        self._write("s2", "signal.status", "working")
        self._write("s3", "anchor.project", "p3")
        self._write("s3", "override.status", "waiting")
        self._write("s3", "pending-attention", "permission")

        by_proj = {s["project"]: s for s in self._sessions()}
        self.assertEqual(by_proj["p1"]["state"], "paused")
        self.assertEqual(by_proj["p2"]["state"], "busy")
        self.assertEqual(by_proj["p3"]["state"], "blocked")
        self.assertTrue(by_proj["p3"]["pending_attention"])

    # --- window filter ---

    def test_since_filters_by_last_activity(self):
        old = time.time() - 86400 * 3
        new = time.time() - 60
        self._write("old", "anchor.project", "stale", mtime=old)
        self._write("new", "anchor.project", "fresh", mtime=new)

        cutoff = time.time() - 3600
        projects = {s["project"] for s in self._sessions(since=cutoff)}
        self.assertEqual(projects, {"fresh"})

    def test_since_accepts_durations(self):
        now = time.time()
        self.assertAlmostEqual(self.beacon._parse_since("1d", True), now - 86400, delta=2)
        self.assertAlmostEqual(self.beacon._parse_since("2h", True), now - 7200, delta=2)
        self.assertAlmostEqual(self.beacon._parse_since("30m", True), now - 1800, delta=2)
        self.assertAlmostEqual(self.beacon._parse_since("90s", True), now - 90, delta=2)
        self.assertAlmostEqual(self.beacon._parse_since("1w", True), now - 604800, delta=2)
        # ISO-8601 still works
        self.assertEqual(
            self.beacon._parse_since("2026-05-30T00:00:00Z", True),
            self.beacon.datetime(2026, 5, 30, tzinfo=self.beacon.timezone.utc).timestamp())

    def test_no_since_returns_all(self):
        self._write("old", "anchor.project", "stale", mtime=time.time() - 86400 * 9)
        self._write("new", "anchor.project", "fresh")
        self.assertEqual(len({s["project"] for s in self._sessions()}), 2)

    # --- tack correlation ---

    def test_correlates_via_project_name(self):
        self._route_file("alpha", group="ai-tooling")
        self._write("s1", "anchor.project", "alpha")
        s = self._sessions()[0]
        self.assertEqual(s["route"], "alpha")
        self.assertEqual(s["route_group"], "ai-tooling")

    def test_project_name_match_is_case_insensitive(self):
        self._route_file("claudewatch")
        self._write("s1", "anchor.project", "ClaudeWatch")
        self.assertEqual(self._sessions()[0]["route"], "claudewatch")

    def test_correlates_via_tack_pin_file(self):
        pin_dir = Path(self._tmp.name) / "checkout"
        pin_dir.mkdir()
        (pin_dir / ".tack").write_text("slug: pinned-route\npinned_at: 2026-01-01\n")
        self._route_file("pinned-route", group="grp")
        self._write("s1", "anchor.project", "unrelated-name")
        self._write("s1", "anchor.cwd", str(pin_dir))
        s = self._sessions()[0]
        self.assertEqual(s["route"], "pinned-route")
        self.assertEqual(s["route_group"], "grp")

    def test_correlates_via_project_basename(self):
        # Git-remote-form project (owner/repo) should still match route <repo>.
        self._route_file("ai-sdlc", group="ai-tooling")
        self._write("s1", "anchor.project", "cpeterson/ai-sdlc")
        self.assertEqual(self._sessions()[0]["route"], "ai-sdlc")

    def test_session_id_is_authoritative_over_project(self):
        # The session id wins even when the project matches nothing — the
        # registered route is ground truth.
        self._route_file("real-route", group="grp",
                         sessions=[("sid-xyz", "2026-05-01T00:00:00Z")])
        self._write("s1", "claude_session_id", "sid-xyz")
        self._write("s1", "anchor.project", "totally-unrelated")
        s = self._sessions()[0]
        self.assertEqual(s["route"], "real-route")
        self.assertEqual(s["route_group"], "grp")

    def test_session_id_multi_route_picks_latest_started(self):
        self._route_file("older", sessions=[("dup", "2026-01-01T00:00:00Z")])
        self._route_file("newer", sessions=[("dup", "2026-05-01T00:00:00Z")])
        self._write("s1", "claude_session_id", "dup")
        self._write("s1", "anchor.project", "p1")
        self.assertEqual(self._sessions()[0]["route"], "newer")

    def test_unmatched_project_is_unrouted(self):
        self._write("s1", "anchor.project", "no-such-route")
        s = self._sessions()[0]
        self.assertIsNone(s["route"])
        self.assertIsNone(s["route_group"])

    # --- payload shape ---

    def test_payload_envelope(self):
        self._write("s1", "anchor.project", "p1")
        payload = self.beacon.collect_sessions(None)
        self.assertEqual(set(payload), {"generated_at", "window_since", "sessions"})
        self.assertIsNone(payload["window_since"])
        self.assertIn("age_seconds", payload["sessions"][0])
        self.assertIn("last_activity", payload["sessions"][0])

    # --- serve ---

    def test_serve_returns_payload_with_cors(self):
        self._write("s1", "anchor.project", "served")
        server = self.beacon.wip_http_server(0)  # ephemeral port
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/wip.json", timeout=3) as resp:
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "*")
            payload = json.loads(resp.read())
        self.assertEqual([s["project"] for s in payload["sessions"]], ["served"])


ANSI = re.compile(r"\x1b\[[0-9;]*m")


class WatchViewTest(unittest.TestCase):
    """The live `beacon watch` recency feed. _watch_frame_lines is a pure
    function over a payload dict, so these build sessions directly and assert
    on the rendered frame with SGR codes stripped."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.beacon = _load_beacon(Path(self._tmp.name))

    def _session(self, **kw):
        base = dict(state="ready", status="idle", project="proj",
                    branch=None, route=None, description="", age_seconds=10)
        base.update(kw)
        return base

    def _rows(self, sessions, cols=120):
        payload = {"sessions": sessions, "window_since": "2026-01-01T00:00:00+00:00"}
        return [ANSI.sub("", ln) for ln in self.beacon._watch_frame_lines(payload, cols)]

    def _body(self, lines):
        return [ln for ln in lines if ln.lstrip().startswith("●")]

    def test_recency_feed_most_recent_first(self):
        rows = self._body(self._rows([
            self._session(project="older", age_seconds=500),
            self._session(project="newer", age_seconds=2),
        ]))
        self.assertIn("newer", rows[0])
        self.assertIn("older", rows[1])

    def test_route_hidden_when_it_echoes_project(self):
        text = "\n".join(self._rows([
            self._session(project="beacon", route="beacon"),
            self._session(project="cpeterson/ai-sdlc", route="ai-sdlc"),
            self._session(project="sextant", route="spec-status"),
        ]))
        self.assertNotIn("[beacon]", text)       # exact echo suppressed
        self.assertNotIn("[ai-sdlc]", text)      # last-segment echo suppressed
        self.assertIn("[spec-status]", text)     # distinct route kept

    def test_empty_feed_message(self):
        self.assertTrue(any("No active beacon sessions." in ln for ln in self._rows([])))

    def test_columns_grid_aligned(self):
        rows = self._body(self._rows([
            self._session(project="x", status="idle", age_seconds=5),
            self._session(project="much-longer-project-name", status="waiting", age_seconds=50),
        ]))
        self.assertEqual(rows[0].index("idle"), rows[1].index("waiting"))

    def test_description_truncated_to_width(self):
        s = self._session(project="p", description="a very long description that keeps going")
        self.assertIn("very long description", "\n".join(self._rows([s], cols=200)))
        narrow = self._body(self._rows([s], cols=40))[0]
        self.assertIn("…", narrow)
        self.assertLessEqual(len(narrow), 40)

    def test_first_description_line_only(self):
        row = self._body(self._rows([self._session(description="line one\nline two")], cols=200))[0]
        self.assertIn("line one", row)
        self.assertNotIn("line two", row)


class ColorControlTest(unittest.TestCase):
    """_color_enabled precedence: --color flag (_COLOR_OVERRIDE) > env vars
    (NO_COLOR off, FORCE_COLOR / CLICOLOR_FORCE on) > stdout.isatty()."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.beacon = _load_beacon(Path(self._tmp.name))

    def _colored(self, *, env, isatty=False):
        full = {"NO_COLOR": "", "FORCE_COLOR": "", "CLICOLOR_FORCE": ""}
        full.update(env)
        with mock.patch.dict(os.environ, full), \
                mock.patch.object(self.beacon.sys.stdout, "isatty", return_value=isatty):
            return "\x1b[" in self.beacon._color("1", "x")

    def test_flag_override_beats_env(self):
        self.beacon._COLOR_OVERRIDE = True
        self.assertTrue(self._colored(env={"NO_COLOR": "1"}))
        self.beacon._COLOR_OVERRIDE = False
        self.assertFalse(self._colored(env={"FORCE_COLOR": "1"}))

    def test_no_color_beats_force_color(self):
        self.beacon._COLOR_OVERRIDE = None
        self.assertFalse(self._colored(env={"NO_COLOR": "1", "FORCE_COLOR": "1"}))

    def test_force_color_enables_without_tty(self):
        self.beacon._COLOR_OVERRIDE = None
        self.assertTrue(self._colored(env={"FORCE_COLOR": "1"}, isatty=False))

    def test_auto_follows_isatty(self):
        self.beacon._COLOR_OVERRIDE = None
        self.assertFalse(self._colored(env={}, isatty=False))
        self.beacon._COLOR_OVERRIDE = None
        self.assertTrue(self._colored(env={}, isatty=True))


if __name__ == "__main__":
    unittest.main()

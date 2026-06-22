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
import types
import urllib.request
import urllib.error
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


class _WipBase(unittest.TestCase):
    """Shared fixture for the wip/serve suites: a fresh tempdir DATA_DIR, tack
    correlation isolated from the developer's real ~/.tack, and helpers to
    write raw state files and collect the resolved sessions."""

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

    def _route_file(self, slug: str, group: str | None = None, sessions=None,
                    tacks=None):
        """Write a route YAML. `tacks` items are dicts: {id, summary?, status?,
        deliverable? (url), links? (list of urls)}. `sessions` items are
        (sid, started) or (sid, started, [bound_tack_ids]) — mirroring the
        RT-11 `tacks` array on a session entry."""
        body = f"slug: {slug}\n" + (f"group: {group}\n" if group else "")
        if tacks:
            body += "tacks:\n"
            for t in tacks:
                body += f"  - id: {t['id']}\n"
                body += f"    summary: {t.get('summary', 'work')}\n"
                body += f"    status: {t.get('status', 'pending')}\n"
                if t.get("deliverable"):
                    body += f"    deliverable:\n      label: d\n      url: {t['deliverable']}\n"
                if t.get("links"):
                    body += "    links:\n"
                    for u in t["links"]:
                        body += f"      - label: l\n        url: {u}\n"
        if sessions:
            body += "sessions:\n"
            for entry in sessions:
                sid, started = entry[0], entry[1]
                body += f"  - id: {sid}\n    started_at: {started}\n"
                bound = entry[2] if len(entry) > 2 else None
                if bound:
                    body += "    tacks:\n"
                    for tid in bound:
                        body += f"      - {tid}\n"
        (self.tack_home / "routes" / f"{slug}.yaml").write_text(body)

    def _sessions(self, since=None):
        return self.beacon.collect_sessions(since)["sessions"]


class WipTest(_WipBase):
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

    def test_task_in_payload(self):
        # task is a first-class field (WIP-01): an explicit override surfaces,
        # and the key is present (null) even when no task is set.
        self._write("withtask", "anchor.project", "alpha")
        self._write("withtask", "override.task", "ship it")
        self._write("notask", "anchor.project", "beta")
        by_hash = {s["hash"]: s for s in self._sessions()}
        self.assertEqual(by_hash["withtask"]["task"], "ship it")
        self.assertIn("task", by_hash["notask"])
        self.assertIsNone(by_hash["notask"]["task"])

    def test_task_falls_back_to_resolved_snapshot(self):
        # With no override, task comes from the last-rendered `resolved` snapshot.
        self._write("snap", "anchor.project", "gamma")
        self._write("snap", "resolved", json.dumps({"task": "from-branch"}))
        task = next(s for s in self._sessions() if s["hash"] == "snap")["task"]
        self.assertEqual(task, "from-branch")

    def test_latest_turn_in_payload(self):
        # WIP-11: latest_turn surfaces as a parsed object, and the key is
        # present (null) even when no turn is recorded.
        self._write("withturn", "anchor.project", "alpha")
        self._write("withturn", "latest_turn", json.dumps(
            {"role": "agent", "text": "wired the hook", "at": "2026-06-20T00:00:00+00:00"}))
        self._write("noturn", "anchor.project", "beta")
        by_hash = {s["hash"]: s for s in self._sessions()}
        self.assertEqual(by_hash["withturn"]["latest_turn"]["role"], "agent")
        self.assertEqual(by_hash["withturn"]["latest_turn"]["text"], "wired the hook")
        self.assertIn("latest_turn", by_hash["noturn"])
        self.assertIsNone(by_hash["noturn"]["latest_turn"])

    def test_latest_turn_null_on_corrupt_json(self):
        # A malformed state file must not crash the scan — it resolves to null.
        self._write("bad", "anchor.project", "alpha")
        self._write("bad", "latest_turn", "{not json")
        rec = next(s for s in self._sessions() if s["hash"] == "bad")
        self.assertIsNone(rec["latest_turn"])

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

    def test_since_exempts_paused_sessions(self):
        # WIP-03: a paused session is exempt from the window — parked, not
        # stale — so it survives past the cutoff where an old idle one is
        # dropped.
        old = time.time() - 86400 * 3
        self._write("parked", "anchor.project", "parked-proj", mtime=old)
        self._write("parked", "override.status", "paused", mtime=old)
        self._write("stale", "anchor.project", "stale-proj", mtime=old)

        cutoff = time.time() - 3600
        by_proj = {s["project"]: s for s in self._sessions(since=cutoff)}
        self.assertIn("parked-proj", by_proj)
        self.assertEqual(by_proj["parked-proj"]["state"], "paused")
        self.assertNotIn("stale-proj", by_proj)

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

    def test_branch_probe_memoized_per_cwd(self):
        # The git branch probe is a property of the directory, not the session.
        # A fleet with many sessions per repo must probe once per cwd, not once
        # per session (the dominant `wip` cost before memoization).
        for h, cwd in (("a", "/repo/x"), ("b", "/repo/x"), ("c", "/repo/y")):
            self._write(h, "anchor.project", "p")
            self._write(h, "anchor.cwd", cwd)
        with mock.patch.object(self.beacon, "_raw_branch", return_value="main") as m:
            self.beacon.collect_sessions(None)
        self.assertEqual(m.call_count, 2, "two distinct cwds → two probes, not three sessions")

    # --- session→tack binding (WIP-09) ---

    def test_bound_tack_is_route_qualified_and_existing(self):
        # A bound tack carrying a deliverable reads as existing, and its id is
        # qualified with the route slug (tack ids are route-scoped).
        self._route_file(
            "feat", group="grp",
            tacks=[{"id": "t1", "summary": "Wire it",
                    "deliverable": "https://github.com/o/r/pull/7"}],
            sessions=[("sid-1", "2026-05-01T00:00:00Z", ["t1"])],
        )
        self._write("s1", "claude_session_id", "sid-1")
        self._write("s1", "anchor.project", "feat")
        s = self._sessions()[0]
        self.assertEqual(len(s["tacks"]), 1)
        self.assertEqual(s["tacks"][0]["id"], "feat/t1")
        self.assertEqual(s["tacks"][0]["tack_id"], "t1")
        self.assertEqual(s["tacks"][0]["summary"], "Wire it")
        self.assertEqual(s["tacks"][0]["kind"], "existing")

    def test_bound_tack_without_tracker_is_emerging(self):
        self._route_file(
            "feat",
            tacks=[{"id": "t1", "summary": "New idea"}],
            sessions=[("sid-1", "2026-05-01T00:00:00Z", ["t1"])],
        )
        self._write("s1", "claude_session_id", "sid-1")
        self._write("s1", "anchor.project", "feat")
        self.assertEqual(self._sessions()[0]["tacks"][0]["kind"], "emerging")

    def test_tracker_link_marks_existing_but_docs_link_does_not(self):
        self._route_file(
            "feat",
            tacks=[
                {"id": "t1", "links": ["https://github.com/o/r/issues/3"]},
                {"id": "t2", "links": ["https://example.com/design-doc"]},
            ],
            sessions=[("sid-1", "2026-05-01T00:00:00Z", ["t1", "t2"])],
        )
        self._write("s1", "claude_session_id", "sid-1")
        self._write("s1", "anchor.project", "feat")
        by_id = {t["tack_id"]: t for t in self._sessions()[0]["tacks"]}
        self.assertEqual(by_id["t1"]["kind"], "existing")
        self.assertEqual(by_id["t2"]["kind"], "emerging")

    def test_bound_tacks_preserve_touch_order_last_is_current(self):
        self._route_file(
            "feat",
            tacks=[{"id": "t1"}, {"id": "t2"}],
            sessions=[("sid-1", "2026-05-01T00:00:00Z", ["t1", "t2"])],
        )
        self._write("s1", "claude_session_id", "sid-1")
        self._write("s1", "anchor.project", "feat")
        ids = [t["tack_id"] for t in self._sessions()[0]["tacks"]]
        self.assertEqual(ids, ["t1", "t2"])

    def test_location_correlated_session_has_empty_tacks(self):
        # Correlated by project name (WIP-02 tier 4), not a recorded binding —
        # so the bound-tack list is empty even though the route resolves.
        self._route_file("feat", tacks=[{"id": "t1"}])
        self._write("s1", "anchor.project", "feat")
        s = self._sessions()[0]
        self.assertEqual(s["route"], "feat")
        self.assertEqual(s["tacks"], [])

    def test_unknown_bound_tack_id_is_skipped(self):
        # A session referencing a tack that no longer exists (removed later)
        # is dropped from the resolved list rather than emitting a stub.
        self._route_file(
            "feat",
            tacks=[{"id": "t1"}],
            sessions=[("sid-1", "2026-05-01T00:00:00Z", ["t1", "t9"])],
        )
        self._write("s1", "claude_session_id", "sid-1")
        self._write("s1", "anchor.project", "feat")
        ids = [t["tack_id"] for t in self._sessions()[0]["tacks"]]
        self.assertEqual(ids, ["t1"])

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

    def test_serve_root_returns_dashboard_html(self):
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as resp:
            self.assertTrue(resp.headers["Content-Type"].startswith("text/html"))
            body = resp.read().decode()
        self.assertIn("beacon fleet", body)
        self.assertIn("/wip.json", body)


class IconTest(_WipBase):
    """PROV-08 / WIP-08: project-icon discovery, the `icon` field in the wip
    payload, and the /icon/<hash> serve route."""

    def _project(self, *rel_files: str) -> Path:
        """A throwaway project root (.git marker) with the given files, placed
        under a fake $HOME so `_project_root_at` accepts it."""
        home = Path(self._tmp.name) / "home"
        root = home / "proj"
        (root / ".git").mkdir(parents=True, exist_ok=True)
        for rel in rel_files:
            f = root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"<svg/>" if rel.endswith(".svg") else b"\x89PNG")
        self._home_patch = mock.patch.object(self.beacon.Path, "home", return_value=home)
        self._home_patch.start()
        self.addCleanup(self._home_patch.stop)
        # _project_root_at resolves paths (on macOS /var → /private/var), so
        # hand back the resolved root for symmetry with discovery's output.
        return root.resolve()

    def test_discover_prefers_docs_favicon(self):
        root = self._project("favicon.ico", "docs/favicon.svg")
        # docs/favicon.svg precedes the root favicon.ico in ICON_CANDIDATES.
        self.assertEqual(self.beacon._discover_icon_at(root),
                         str(root / "docs/favicon.svg"))

    def test_discover_none_when_no_icon(self):
        root = self._project("README.md")
        self.assertIsNone(self.beacon._discover_icon_at(root))

    def test_icon_field_local_file_points_at_route(self):
        root = self._project("favicon.svg")
        self._write("withicon", "anchor.project", "proj")
        self._write("withicon", "anchor.icon", str(root / "favicon.svg"))
        icon = next(s for s in self._sessions() if s["hash"] == "withicon")["icon"]
        self.assertEqual(icon, "/icon/withicon")

    def test_icon_field_http_override_passthrough(self):
        self._write("online", "anchor.project", "proj")
        self._write("online", "override.icon", "https://example.com/favicon.ico")
        icon = next(s for s in self._sessions() if s["hash"] == "online")["icon"]
        self.assertEqual(icon, "https://example.com/favicon.ico")

    def test_icon_field_http_override_scheme_is_case_insensitive(self):
        # An uppercase scheme is still a URL passthrough, not a local-file path.
        self._write("loud", "anchor.project", "proj")
        self._write("loud", "override.icon", "HTTPS://example.com/favicon.ico")
        icon = next(s for s in self._sessions() if s["hash"] == "loud")["icon"]
        self.assertEqual(icon, "HTTPS://example.com/favicon.ico")

    def test_icon_field_null_when_absent(self):
        self._write("plain", "anchor.project", "proj")
        rec = next(s for s in self._sessions() if s["hash"] == "plain")
        self.assertIn("icon", rec)
        self.assertIsNone(rec["icon"])

    def test_nonimage_override_is_refused(self):
        # The exfil guard (WIP-08): a local override that isn't an image type
        # resolves to no icon, so the route can't be steered into serving it.
        secret = Path(self._tmp.name) / "secret.txt"
        secret.write_text("nope")
        self._write("evil", "anchor.project", "proj")
        self._write("evil", "override.icon", str(secret))
        rec = next(s for s in self._sessions() if s["hash"] == "evil")
        self.assertIsNone(rec["icon"])
        self.assertIsNone(self.beacon._icon_local_path("evil"))

    def test_serve_icon_route_streams_bytes(self):
        root = self._project("docs/favicon.svg")
        self._write("served", "anchor.project", "proj")
        self._write("served", "anchor.icon", str(root / "docs/favicon.svg"))
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/icon/served", timeout=3) as resp:
            self.assertEqual(resp.headers["Content-Type"], "image/svg+xml")
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "*")
            self.assertEqual(resp.read(), b"<svg/>")

    def test_serve_icon_route_404_unknown(self):
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/icon/deadbeef", timeout=3)
        self.assertEqual(ctx.exception.code, 404)


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

    def test_paused_reason_carries_glyph(self):
        # WIP-12: a paused row's reason is anchored with the || pause glyph.
        row = self._body(self._rows([
            self._session(state="paused", status="paused", description="stepping away"),
        ], cols=200))[0]
        self.assertIn("|| stepping away", row)

    def test_paused_without_reason_still_anchored(self):
        # WIP-12: the glyph shows even with no reason, so a parked session
        # always reads as parked beyond its color dot.
        row = self._body(self._rows([
            self._session(state="paused", status="paused", description=""),
        ], cols=200))[0]
        self.assertIn("||", row)

    def test_non_paused_uses_dash_not_glyph(self):
        row = self._body(self._rows([
            self._session(state="ready", description="working on it"),
        ], cols=200))[0]
        self.assertIn("— working on it", row)
        self.assertNotIn("||", row)

    def test_supports_raw_false_without_termios(self):
        # A None entry in sys.modules makes `import termios` raise ImportError,
        # mirroring Windows where the module doesn't exist — watch then polls.
        with mock.patch.dict(sys.modules, {"termios": None}):
            self.assertFalse(self.beacon._watch_supports_raw())


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


class FocusTest(unittest.TestCase):
    """FOCUS-01..04 + CLI-17: focus-handle recording, the `focusable` flag in
    the payload, the hash→handle resolve, and the POST /focus access model."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.beacon = _load_beacon(Path(self._tmp.name))
        self.state_dir = self.beacon.STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, sh: str, field: str, value: str):
        (self.state_dir / f"{sh}.{field}").write_text(value)

    def _sessions(self):
        return self.beacon.collect_sessions(None)["sessions"]

    def test_focusable_flag_tracks_recorded_handle(self):
        self._write("withguid", "anchor.project", "p")
        self._write("withguid", "iterm_session_id", "GUID-1")
        self._write("noguid", "anchor.project", "q")
        by_hash = {s["hash"]: s for s in self._sessions()}
        self.assertTrue(by_hash["withguid"]["focusable"])
        self.assertFalse(by_hash["noguid"]["focusable"])

    def test_record_handle_keeps_guid_for_real_iterm_id(self):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w2t0p0:ABC-123"}):
            self.beacon._record_focus_handle()
            self.assertEqual(self.beacon.read_state("iterm_session_id"), "ABC-123")

    def test_record_handle_skips_synthesized_fallback(self):
        with mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "claude-session:xyz"}):
            self.beacon._record_focus_handle()
            self.assertIsNone(self.beacon.read_state("iterm_session_id"))

    def test_focus_session_not_focusable_without_handle(self):
        self._write("abcdef99", "anchor.project", "p")
        ok, msg = self.beacon._focus_session("abcdef99")
        self.assertFalse(ok)
        self.assertEqual(msg, "not focusable")

    def test_focus_session_rejects_non_hex_hash(self):
        ok, msg = self.beacon._focus_session("../secrets")
        self.assertFalse(ok)
        self.assertEqual(msg, "bad hash")

    def test_focus_session_invokes_cli_with_recorded_guid(self):
        self._write("abcdef01", "iterm_session_id", "GUID-9")
        with mock.patch.object(self.beacon.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stdout="", stderr="")) as run:
            ok, msg = self.beacon._focus_session("abcdef01")
        self.assertTrue(ok)
        cmd = run.call_args.args[0]
        self.assertIn("focus", cmd)
        self.assertIn("GUID-9", cmd)

    def _start_server(self):
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.handle_request, daemon=True).start()
        return server.server_address[1]

    def _post_focus(self, port, origin=None):
        body = json.dumps({"hash": "abcdef01"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/focus", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if origin is not None:
            req.add_header("Origin", origin)
        return urllib.request.urlopen(req, timeout=3)

    def test_focus_route_rejects_foreign_origin(self):
        port = self._start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post_focus(port, origin="https://evil.example")
        self.assertEqual(cm.exception.code, 403)

    def test_focus_route_invokes_focus_for_allowed_request(self):
        port = self._start_server()
        with mock.patch.object(self.beacon, "_focus_session",
                               return_value=(True, "focused")) as m:
            with self._post_focus(port) as resp:
                payload = json.loads(resp.read())
        self.assertTrue(payload["focused"])
        m.assert_called_once_with("abcdef01")

    def test_focus_route_allows_origin_from_config_allowlist(self):
        # FOCUS-04: a private deployment's origin reaches the allowlist via the
        # user config file rather than being baked into the source.
        cfg_origin = "https://dashboard.pages.example"
        with mock.patch.object(self.beacon, "_load_config",
                               return_value={"focus_origins": [cfg_origin]}):
            port = self._start_server()
            with mock.patch.object(self.beacon, "_focus_session",
                                   return_value=(True, "focused")):
                with self._post_focus(port, origin=cfg_origin) as resp:
                    payload = json.loads(resp.read())
        self.assertTrue(payload["focused"])

    def test_focus_origins_reads_config_list(self):
        with mock.patch.object(
                self.beacon, "_load_config",
                return_value={"focus_origins": ["https://a.example", "https://b.example"]}):
            origins = self.beacon._focus_origins()
        self.assertIn("https://a.example", origins)
        self.assertIn("https://b.example", origins)
        self.assertIn("https://chris-peterson.github.io", origins)

    def test_focus_origins_reads_config_from_xdg_path(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "beacon" / "config.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(json.dumps({"focus_origins": ["https://x.example"]}))
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
                origins = self.beacon._focus_origins()
        self.assertIn("https://x.example", origins)


class ForgetTest(unittest.TestCase):
    """FORGET-01..03: per-session state delete via the CLI verb and the
    POST /forget route, the hash guard, and the shared FOCUS-04 access model."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.beacon = _load_beacon(Path(self._tmp.name))
        self.state_dir = self.beacon.STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, sh: str, field: str, value: str):
        (self.state_dir / f"{sh}.{field}").write_text(value)

    def test_forget_removes_all_state_files(self):
        self._write("abcdef01", "anchor.project", "p")
        self._write("abcdef01", "override.status", "paused")
        self._write("beef0099", "anchor.project", "keep")  # a different session
        valid, files = self.beacon._forget_session("abcdef01")
        self.assertTrue(valid)
        self.assertEqual(files, 2)
        self.assertEqual(list(self.state_dir.glob("abcdef01.*")), [])
        self.assertTrue(list(self.state_dir.glob("beef0099.*")))  # untouched

    def test_forget_rejects_non_hex_hash(self):
        self._write("abcdef01", "anchor.project", "p")
        valid, files = self.beacon._forget_session("../secrets")
        self.assertFalse(valid)
        self.assertEqual(files, 0)
        self.assertTrue(list(self.state_dir.glob("abcdef01.*")))  # nothing deleted

    def test_forget_is_idempotent_for_unknown_session(self):
        valid, files = self.beacon._forget_session("abcdef02")
        self.assertTrue(valid)
        self.assertEqual(files, 0)

    def test_cmd_forget_exits_on_bad_hash(self):
        with self.assertRaises(SystemExit) as cm:
            self.beacon.cmd_forget(types.SimpleNamespace(hash="../x"))
        self.assertEqual(cm.exception.code, 2)

    def _start_server(self):
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.handle_request, daemon=True).start()
        return server.server_address[1]

    def _post_forget(self, port, sh="abcdef01", origin=None):
        body = json.dumps({"hash": sh}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/forget", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if origin is not None:
            req.add_header("Origin", origin)
        return urllib.request.urlopen(req, timeout=3)

    def test_forget_route_deletes_for_allowed_request(self):
        self._write("abcdef01", "anchor.project", "p")
        port = self._start_server()
        with self._post_forget(port) as resp:
            payload = json.loads(resp.read())
        self.assertTrue(payload["forgotten"])
        self.assertEqual(payload["files"], 1)
        self.assertEqual(list(self.state_dir.glob("abcdef01.*")), [])

    def test_forget_route_rejects_foreign_origin(self):
        self._write("abcdef01", "anchor.project", "p")
        port = self._start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post_forget(port, origin="https://evil.example")
        self.assertEqual(cm.exception.code, 403)
        self.assertTrue(list(self.state_dir.glob("abcdef01.*")))  # not deleted


if __name__ == "__main__":
    unittest.main()

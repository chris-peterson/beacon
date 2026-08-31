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


class _CountingReader:
    """Delegating `rfile` wrapper that records the size of each `read`.

    The request line and headers are parsed with `readline`, so a recorded
    `read` is a body read — which is what lets a test see whether a reply path
    consumed the request body before responding.
    """

    def __init__(self, inner, reads: list):
        self._inner = inner
        self._reads = reads

    def read(self, *args):
        data = self._inner.read(*args)
        self._reads.append(len(data))
        return data

    def __getattr__(self, name):
        return getattr(self._inner, name)


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
        self._write("aaa", "activity", "working")
        self._write("bbb", "anchor.project", "beta")
        self._write("bbb", "claude_session_id", "sid-beta")

        sessions = self._sessions()
        projects = {s["project"] for s in sessions}
        self.assertEqual(projects, {"alpha", "beta"})
        alpha = next(s for s in sessions if s["project"] == "alpha")
        self.assertEqual(alpha["activity"], "working")
        self.assertEqual(alpha["mode"], {"name": "dev", "note": "", "glyph": ""})
        self.assertEqual(alpha["color_state"], "busy")

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
        self._write("ghost", "activity", "working")
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

    def test_axes_resolve_independently(self):
        # The record carries both, and `color_state` follows activity alone — so a
        # moded session still reports whether it needs the user.
        self._write("s1", "anchor.project", "p1")
        self._write("s1", "mode", json.dumps({"name": "pause", "note": "brb"}))
        self._write("s2", "anchor.project", "p2")
        self._write("s2", "activity", "working")
        self._write("s3", "anchor.project", "p3")
        self._write("s3", "activity", "waiting")
        self._write("s3", "pending-attention", "permission")
        self._write("s4", "anchor.project", "p4")
        self._write("s4", "mode", json.dumps({"name": "release", "note": "v2.5"}))
        self._write("s4", "activity", "waiting")

        by_proj = {s["project"]: s for s in self._sessions()}
        self.assertEqual(by_proj["p1"]["mode"],
                         {"name": "pause", "note": "brb",
                          "glyph": self.beacon.MODE_SPECS["pause"]["glyph"]})
        self.assertEqual(by_proj["p1"]["activity"], "idle")
        self.assertEqual(by_proj["p1"]["color_state"], "ready")
        self.assertEqual(by_proj["p2"]["color_state"], "busy")
        self.assertEqual(by_proj["p3"]["color_state"], "blocked")
        self.assertTrue(by_proj["p3"]["pending_attention"])
        # The state the merged field could not represent: shipping *and* blocked.
        self.assertEqual(by_proj["p4"]["mode"]["name"], "release")
        self.assertEqual(by_proj["p4"]["activity"], "waiting")
        self.assertEqual(by_proj["p4"]["color_state"], "blocked",
                         "a mode must not hide that the session needs the user")

    def test_unknown_mode_name_reads_as_dev(self):
        # Live state still holds values retired in the pre-SDLC rename. A mode
        # name this version doesn't know is not a mode.
        self._write("legacy", "anchor.project", "p")
        self._write("legacy", "mode", json.dumps({"name": "wrapping", "note": "x"}))
        s = self._sessions()[0]
        self.assertEqual(s["mode"], {"name": "dev", "note": "", "glyph": ""},
                         "an unrecognized mode name is not a mode, and carries no note")

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
        self._write("parked", "mode", json.dumps({"name": "pause"}), mtime=old)
        self._write("stale", "anchor.project", "stale-proj", mtime=old)

        cutoff = time.time() - 3600
        by_proj = {s["project"]: s for s in self._sessions(since=cutoff)}
        self.assertIn("parked-proj", by_proj)
        self.assertEqual(by_proj["parked-proj"]["mode"]["name"], "pause")
        self.assertNotIn("stale-proj", by_proj)

    def test_since_exempts_done_sessions(self):
        # WIP-03: a done session is a mode state — deliberately set aside —
        # so it too survives past the window, like paused.
        old = time.time() - 86400 * 3
        self._write("finished", "anchor.project", "done-proj", mtime=old)
        self._write("finished", "mode", json.dumps({"name": "done"}), mtime=old)
        self._write("stale", "anchor.project", "stale-proj", mtime=old)

        cutoff = time.time() - 3600
        by_proj = {s["project"]: s for s in self._sessions(since=cutoff)}
        self.assertIn("done-proj", by_proj)
        self.assertEqual(by_proj["done-proj"]["mode"]["name"], "done")
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
        # Many sessions per repo must probe once per cwd, not once
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

    def test_bound_tack_refs_classified_cr_issue_other(self):
        # WIP-09: a tack's deliverable + links surface as classified refs so the
        # sessions view can emphasize change requests, then issues, then other.
        self._route_file(
            "feat",
            tacks=[{
                "id": "t1",
                "deliverable": "https://github.com/o/r/pull/7",
                "links": ["https://gitlab.com/o/r/-/issues/5",
                          "https://example.com/design-doc"],
            }],
            sessions=[("sid-1", "2026-05-01T00:00:00Z", ["t1"])],
        )
        self._write("s1", "claude_session_id", "sid-1")
        self._write("s1", "anchor.project", "feat")
        refs = self._sessions()[0]["tacks"][0]["refs"]
        self.assertEqual([r["type"] for r in refs], ["cr", "issue", "other"])
        self.assertEqual(refs[0]["url"], "https://github.com/o/r/pull/7")

    def test_gitlab_merge_request_ref_is_cr(self):
        self._route_file(
            "feat",
            tacks=[{"id": "t1", "deliverable": "https://gitlab.com/o/r/-/merge_requests/2"}],
            sessions=[("sid-1", "2026-05-01T00:00:00Z", ["t1"])],
        )
        self._write("s1", "claude_session_id", "sid-1")
        self._write("s1", "anchor.project", "feat")
        refs = self._sessions()[0]["tacks"][0]["refs"]
        self.assertEqual(refs[0]["type"], "cr")

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

    def test_serve_returns_payload_and_no_cors_header_for_originless_read(self):
        # An originless request (curl, a same-origin fetch) is served, and gets
        # no Access-Control-Allow-Origin: nothing asked to share it.
        self._write("s1", "anchor.project", "served")
        server = self.beacon.wip_http_server(0)  # ephemeral port
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/wip.json", timeout=3) as resp:
            self.assertIsNone(resp.headers["Access-Control-Allow-Origin"])
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
        self.assertIn("beacon · sessions", body)
        self.assertIn("/wip.json", body)

    def test_serve_turn_returns_full_text(self):
        # WIP-14: /turn/<hash> serves the full multi-line turn, not the excerpt,
        # with role/at mirroring the record's latest_turn.
        self._write("t1", "latest_turn", json.dumps(
            {"role": "agent", "text": "line one", "at": "2026-07-03T00:00:00Z"}))
        self._write("t1", "latest_turn_full", "line one\nline two\nline three")
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/turn/t1", timeout=3) as resp:
            self.assertIsNone(resp.headers["Access-Control-Allow-Origin"])
            body = json.loads(resp.read())
        self.assertEqual(body["role"], "agent")
        self.assertEqual(body["text"], "line one\nline two\nline three")
        self.assertEqual(body["at"], "2026-07-03T00:00:00Z")

    def test_serve_turn_falls_back_to_excerpt_without_full(self):
        # A turn stored before latest_turn_full existed still enriches to the
        # excerpt rather than 404ing.
        self._write("t2", "latest_turn", json.dumps(
            {"role": "human", "text": "just the excerpt", "at": "x"}))
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/turn/t2", timeout=3) as resp:
            body = json.loads(resp.read())
        self.assertEqual(body["text"], "just the excerpt")

    def test_serve_turn_404_for_unknown_session(self):
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/turn/nope", timeout=3)
        self.assertEqual(cm.exception.code, 404)


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

    def test_icon_ignores_a_stale_override_file(self):
        # The icon override retired in 2.5.0 (no live session carried one in three
        # months), so a leftover file is data nothing reads — not a URL the
        # dashboard should still load.
        self._write("stale", "anchor.project", "proj")
        self._write("stale", "override.icon", "https://example.com/favicon.ico")
        icon = next(s for s in self._sessions() if s["hash"] == "stale")["icon"]
        self.assertIsNone(icon)

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
            self.assertIsNone(resp.headers["Access-Control-Allow-Origin"])
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
        """A wip record. `mode` / `note` are given flat for readability and folded
        into the nested tuple the payload actually carries (WIP-01)."""
        base = dict(color_state="ready", mode="dev", activity="idle", project="proj",
                    branch=None, route=None, note="", age_seconds=10)
        base.update(kw)
        base["mode"] = {"name": base.pop("mode"), "note": base.pop("note")}
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
            self._session(project="x", activity="idle", age_seconds=5),
            self._session(project="much-longer-project-name", activity="waiting", age_seconds=50),
        ]))
        self.assertEqual(rows[0].index("idle"), rows[1].index("waiting"))

    def test_columns_align_across_double_width_glyphs(self):
        # 🚀 📋 🏁 are one character but *two* terminal columns (East Asian `W`),
        # so padding by len() leaves every glyph-bearing row a column short and
        # the grid visibly ragged. ⏸ and … are single-width, so the set is mixed
        # and no flat per-glyph fudge works either.
        cases = [("release", "release·idle"), ("pause", "pause·idle"), ("dev", "idle")]
        rows = self._body(self._rows(
            [self._session(project="proj", mode=m, activity="idle") for m, _ in cases],
            cols=200))
        # Anchor on the whole state cell: "idle" is a substring of "release·idle".
        starts = [self.beacon._display_width(row[: row.index(cell)])
                  for row, (_, cell) in zip(rows, cases)]
        self.assertEqual(len(set(starts)), 1,
                         f"state column starts at differing widths: {starts}")

    def test_display_width_counts_columns_not_characters(self):
        self.assertEqual(self.beacon._display_width("🚀"), 2)
        self.assertEqual(self.beacon._display_width("⏸"), 1)
        self.assertEqual(self.beacon._display_width("…"), 1)
        self.assertEqual(self.beacon._display_width("abc"), 3)

    def test_note_truncated_to_width(self):
        s = self._session(project="p", mode="pause",
                          note="a very long note that keeps going")
        self.assertIn("very long note", "\n".join(self._rows([s], cols=200)))
        narrow = self._body(self._rows([s], cols=40))[0]
        self.assertIn("…", narrow)
        self.assertLessEqual(len(narrow), 40)

    def test_first_note_line_only(self):
        row = self._body(self._rows([
            self._session(mode="pause", note="line one\nline two"),
        ], cols=200))[0]
        self.assertIn("line one", row)
        self.assertNotIn("line two", row)

    def test_moded_row_shows_both_axes(self):
        # The sessions view has to show a moded session's activity too: a session blocked
        # on the user is blocked whatever mode it declared, and the merged field
        # could only ever surface the mode.
        row = self._body(self._rows([
            self._session(mode="release", activity="waiting", color_state="blocked",
                          note="cutting v2.5"),
        ], cols=200))[0]
        self.assertIn("release·waiting", row)
        self.assertIn("— cutting v2.5", row)

    def test_moded_row_carries_the_mode_glyph(self):
        # The same glyph the tab shows, so a row and its tab read identically.
        row = self._body(self._rows([self._session(mode="pause")], cols=200))[0]
        self.assertIn(self.beacon.MODE_SPECS["pause"]["glyph"], row)

    def test_dev_row_shows_activity_alone_and_no_glyph(self):
        row = self._body(self._rows([
            self._session(mode="dev", activity="working", note=""),
        ], cols=200))[0]
        self.assertIn("working", row)
        self.assertNotIn("·", row.split("working")[0].split("●")[1],
                         "a dev-cycle row has no mode to join to its activity")
        for glyph in (m["glyph"] for m in self.beacon.MODE_SPECS.values()):
            self.assertNotIn(glyph, row)

    def test_note_uses_dash_lead_in(self):
        row = self._body(self._rows([
            self._session(mode="retro", note="writing it up"),
        ], cols=200))[0]
        self.assertIn("— writing it up", row)

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

    def test_focus_route_rejects_opaque_null_origin(self):
        # A sandboxed iframe or a data: URL page sends the literal `Origin: null`
        # — a browser context whose contents an attacker chose, not the absent
        # header a curl or same-origin fetch sends.
        port = self._start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post_focus(port, origin="null")
        self.assertEqual(cm.exception.code, 403)

    def _preflight(self, port, origin):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/focus", method="OPTIONS")
        req.add_header("Origin", origin)
        req.add_header("Access-Control-Request-Method", "POST")
        return urllib.request.urlopen(req, timeout=3)

    def test_focus_preflight_rejects_opaque_null_origin(self):
        # The preflight decides whether the browser sends the POST at all, so
        # it carries the same gate.
        port = self._start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._preflight(port, "null")
        self.assertEqual(cm.exception.code, 403)

    def test_focus_preflight_allows_loopback_origin(self):
        port = self._start_server()
        with self._preflight(port, "http://127.0.0.1:8787") as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"],
                             "http://127.0.0.1:8787")

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
            origins = self.beacon._allowed_origins()
        self.assertIn("https://a.example", origins)
        self.assertIn("https://b.example", origins)
        self.assertIn("https://chris-peterson.github.io", origins)

    def test_focus_origins_reads_config_from_xdg_path(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "beacon" / "config.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(json.dumps({"focus_origins": ["https://x.example"]}))
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
                origins = self.beacon._allowed_origins()
        self.assertIn("https://x.example", origins)


class ReadRouteAccessTest(_WipBase):
    """WIP-18 over the read half. The payload and /turn carry transcript-derived
    turn text, so the reads are gated on the same Host + Origin model the mutating
    routes use, and only a vetted origin is echoed back as CORS."""

    def setUp(self):
        super().setUp()
        self._write("abcdef01", "anchor.project", "secret-proj")
        self._write("abcdef01", "latest_turn", json.dumps(
            {"role": "human", "text": "an excerpt", "at": "2026-08-01T00:00:00Z"}))
        self._write("abcdef01", "latest_turn_full", "the whole turn")

    # Every read route, so a later route addition that skips the gate fails here
    # rather than shipping open.
    ROUTES = ("/", "/wip.json", "/turn/abcdef01", "/icon/abcdef01", "/mode-bg/pause")

    def _get(self, path, origin=None, host=None):
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        threading.Thread(target=server.handle_request, daemon=True).start()
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
        if origin is not None:
            req.add_header("Origin", origin)
        if host is not None:
            req.add_header("Host", host)
        return urllib.request.urlopen(req, timeout=3)

    def _assert_forbidden(self, path, **kw):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._get(path, **kw)
        self.assertEqual(cm.exception.code, 403, path)
        # The rejection carries no CORS header, so the browser cannot read the
        # body either.
        self.assertIsNone(cm.exception.headers["Access-Control-Allow-Origin"], path)

    def test_foreign_origin_refused_on_every_read_route(self):
        for path in self.ROUTES:
            self._assert_forbidden(path, origin="https://evil.example.com")

    def test_opaque_null_origin_refused_on_every_read_route(self):
        # `Origin: null` is what a browser sends for every opaque origin — a
        # sandboxed iframe, a data: URL, a cross-origin redirect. Any page can
        # create one on demand, so it is foreign, not the absent-header case.
        for path in self.ROUTES:
            self._assert_forbidden(path, origin="null")

    def test_non_loopback_host_refused_on_every_read_route(self):
        # DNS rebinding: the request reaches the loopback socket but carries the
        # attacker's own name in Host.
        for path in self.ROUTES:
            self._assert_forbidden(path, host="evil.example.com")

    def test_loopback_origin_is_served_and_echoed(self):
        with self._get("/wip.json", origin="http://127.0.0.1:8787") as resp:
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"],
                             "http://127.0.0.1:8787")
            self.assertEqual(resp.headers["Vary"], "Origin")
            payload = json.loads(resp.read())
        self.assertEqual([s["project"] for s in payload["sessions"]], ["secret-proj"])

    def test_allowlisted_origin_is_served_and_echoed(self):
        # A remotely-hosted dashboard keeps working by being on the allowlist —
        # the built-in public dashboard origin, or one added via focus_origins.
        origin = "https://chris-peterson.github.io"
        with self._get("/turn/abcdef01", origin=origin) as resp:
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"], origin)
            body = json.loads(resp.read())
        self.assertEqual(body["text"], "the whole turn")

    def test_config_origin_reaches_the_read_routes(self):
        cfg_origin = "https://dashboard.pages.example"
        with mock.patch.object(self.beacon, "_load_config",
                               return_value={"focus_origins": [cfg_origin]}):
            with self._get("/wip.json", origin=cfg_origin) as resp:
                self.assertEqual(resp.headers["Access-Control-Allow-Origin"], cfg_origin)


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
        self._write("abcdef01", "activity", "working")
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

    def _start_server(self, body_reads: list = None):
        server = self.beacon.wip_http_server(0)
        self.addCleanup(server.server_close)
        if body_reads is not None:
            class _Spy(server.RequestHandlerClass):
                def setup(self):
                    super().setup()
                    self.rfile = _CountingReader(self.rfile, body_reads)

            server.RequestHandlerClass = _Spy
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

    def test_forget_route_rejects_opaque_null_origin(self):
        self._write("abcdef01", "anchor.project", "p")
        port = self._start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post_forget(port, origin="null")
        self.assertEqual(cm.exception.code, 403)
        self.assertTrue(list(self.state_dir.glob("abcdef01.*")))  # not deleted

    def test_forget_route_rejects_a_non_object_payload(self):
        # A JSON body that isn't an object has no `hash` to look up. It earns a
        # 400, not a torn-down connection — the handler answers every request it
        # accepts, including the ill-formed ones.
        port = self._start_server()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/forget", data=b'"not-an-object"', method="POST")
        req.add_header("Content-Type", "application/json")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(cm.exception.code, 400)

    def test_rejected_post_reads_the_body_it_refuses(self):
        # FORGET-03 / FOCUS-04 require the rejection to reach the caller. The
        # response is written and the connection then closes, so the body has to
        # be consumed first: closing a socket that still holds unread bytes
        # makes Windows abort it, and the caller sees a connection error where
        # the 403 should be.
        self._write("abcdef01", "anchor.project", "p")
        body_reads: list = []
        port = self._start_server(body_reads)
        sent = json.dumps({"hash": "abcdef01"}).encode()  # what _post_forget sends
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post_forget(port, origin="https://evil.example")
        self.assertEqual(cm.exception.code, 403)
        self.assertEqual(body_reads, [len(sent)])


if __name__ == "__main__":
    unittest.main()

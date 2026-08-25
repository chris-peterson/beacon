#!/usr/bin/env python3
"""Seed an isolated beacon state dir with a hypothetical concurrent-work fleet,
serve the real dashboard against it, and run a calm simulation — a zero-setup,
interactive demo that needs no real Claude Code sessions.

Everything lives under a throwaway data dir (default /tmp/beacon-demo) and an
isolated TACK_HOME, so your real beacon state and tack routes are untouched.

The simulation mirrors how a real fleet behaves: sessions churn quietly between
working and idle, but every so often one *stalls* — it blocks on you and turns
red (`waiting`). Stalled sessions stay stalled and pile up; only you clear them.
On the dashboard, a waiting card is the only kind that's clickable — clicking it
**returns that session to its agent** (the demo's stand-in for raising the
window and answering the prompt), so it flips back to working and the red ring
clears. The `×` on hover forgets a session outright.

    python3 dev/demo.py                 # seed + serve + simulate on :8788
    python3 dev/demo.py --port 9000     # pick a port
    python3 dev/demo.py --interval 8    # seconds between simulation ticks (default 5)
    python3 dev/demo.py --seed-only     # write a static fleet and exit (no serve)
    python3 dev/demo.py --data-dir DIR  # use a specific isolated data dir

Re-running reseeds from scratch (the data dir and routes are wiped first).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import random
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BEACON_PATH = REPO / "scripts" / "beacon"
DASHBOARD = REPO / "dashboard" / "index.html"
HOME = Path.home()

# A fictional commerce org's concurrent work. Each entry is one dashboard card.
# Most start working/idle; the fleet drifts toward `waiting` as it runs.
#   activity: idle|working|waiting — what the hooks would observe
#   mode + note: a declared phase and its annotation (omit for the dev cycle)
#   route: (slug, group) → a [slug] chip; None means unrouted.
SESSIONS = [
    dict(project="checkout-api", task="idempotency keys for refunds", activity="working",
         age=3, route=("checkout", "payments"),
         turn=("agent", "Added the idempotency-key column and a unique index; wiring the refund handler to look it up before charging")),
    dict(project="checkout-api", task="rebase on main", activity="waiting",
         age=95, route=("checkout", "payments"),
         turn=("agent", "Hit a conflict in refund_handler.py between your idempotency change and main's retry backoff — which side wins?")),
    dict(project="ledger-svc", task="double-entry migration", activity="working",
         age=240, route=("ledger", "payments"),
         turn=("human", "make sure the backfill is idempotent — it'll get re-run")),
    dict(project="storefront-web", task="PDP gallery redesign", activity="idle",
         age=720, route=("storefront", "web"),
         mode="pause", note="waiting on the Figma handoff"),
    dict(project="storefront-web", task="a/b test cleanup", activity="working",
         age=480, route=("storefront", "web"),
         turn=("agent", "Removed the three expired experiment flags and their dead branches")),
    dict(project="search-indexer", task="embedding reindex", activity="working",
         age=1500, route=("search", "discovery"),
         turn=("agent", "Reindexing batch 14 of 60 — throughput is holding at ~8k docs/s")),
    dict(project="mobile-ios", task="deep-link QA", activity="idle", age=2400),
    dict(project="data-pipeline", task="backfill stuck on warehouse quota",
         activity="waiting", age=3600,
         turn=("human", "can you bump the slot reservation or do we need to wait?")),
    # Shipping *and* blocked on you — the state a single merged field could not
    # represent. The card keeps its release treatment and turns its dot red.
    dict(project="auth-svc", task="passkey rollout", activity="waiting",
         mode="release", note="v4.2.0 — canary at 5%",
         age=300, route=("auth", "platform"),
         turn=("agent", "Canary is green at 5%; ramping to 25% needs your sign-off")),
    dict(project="infra-terraform", task="vpc peering to the new region",
         activity="idle", mode="pause", age=18000,
         note="parked on a netops change ticket"),
    dict(project="notifications", task="digest email templates", activity="idle", age=900),
    dict(project="release-tooling", task="cut 3.1.0", activity="working",
         mode="release", note="Shipping\n_Phase 3: CI pipeline_", age=45),
    dict(project="beacon", task="session retro", activity="idle",
         mode="retro", note="writing it up", age=600),
    dict(project="analytics-dbt", task="revenue model v2", activity="working",
         age=160, route=("analytics", "discovery"),
         turn=("agent", "Rebuilt the revenue mart; reconciling the v1/v2 totals — off by $1.2k in deferred revenue")),
]

# Next activity for a session the sim picks (waiting sessions are sticky — only a
# user click returns them, so they're never auto-mutated). Repeats are no-ops,
# which keeps the board calm; `working` carries a real chance of stalling. A
# session's mode is never simulated: a mode is declared, not observed.
ACTIVE_NEXT = {
    "working": ["working", "working", "idle", "waiting"],
    "idle":    ["idle", "idle", "working"],
}


def _hash(seed: str) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:16]


def _write(path: Path, value: str, mtime: float | None = None) -> None:
    path.write_text(value)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _set_activity(state: Path, sh: str, activity: str) -> None:
    """Write the hook-owned activity file (leaving mtime at now, so the session
    surfaces as freshly active) and sync the two waiting-only markers: the
    attention ring, and the focus handle that makes the card clickable. A
    waiting card is the only kind a user can click to return.

    The session's mode is untouched — the simulator moves one axis, which is what
    lets a releasing card go red without losing its release treatment."""
    pend, handle = state / f"{sh}.pending-attention", state / f"{sh}.iterm_session_id"
    _write(state / f"{sh}.activity", activity)
    if activity == "waiting":
        _write(pend, "permission")
        _write(handle, f"demo:{sh}")
    else:
        pend.unlink(missing_ok=True)
        handle.unlink(missing_ok=True)


def seed(data_dir: Path, tack_home: Path) -> list[dict]:
    """Wipe and write the initial fleet at staggered ages. Returns the live model
    (hash + current activity per session) the simulator mutates."""
    state, routes = data_dir / "state", tack_home / "routes"
    for d in (state, routes):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    now = time.time()
    fleet = []
    for i, s in enumerate(SESSIONS):
        sh = _hash(f"demo-{i}-{s['project']}")
        mt = now - s["age"]
        cwd = str(HOME / "work" / "meridian" / s["project"])
        _write(state / f"{sh}.anchor.project", s["project"], mt)
        _write(state / f"{sh}.anchor.cwd", cwd, mt)
        _write(state / f"{sh}.claude_session_id", f"demo-sess-{i}", mt)
        _write(state / f"{sh}.activity", s["activity"], mt)
        if s.get("mode"):
            _write(state / f"{sh}.mode",
                   json.dumps({"name": s["mode"], "note": s.get("note", "")}), mt)
        if s.get("task"):
            _write(state / f"{sh}.override.task", s["task"], mt)
        if s.get("turn"):
            role, text = s["turn"]
            _write(state / f"{sh}.latest_turn",
                   json.dumps({"role": role, "text": text,
                               "at": datetime.fromtimestamp(mt, timezone.utc).isoformat()}),
                   mt)
        if s["activity"] == "waiting":  # waiting-only markers: ring + clickable handle
            _write(state / f"{sh}.pending-attention", "permission", mt)
            _write(state / f"{sh}.iterm_session_id", f"demo:{sh}", mt)
        fleet.append({"sh": sh, "project": s["project"], "activity": s["activity"]})

    for s in SESSIONS:  # routes are matched by project name; in-file slug is the chip
        if s.get("route"):
            slug, group = s["route"]
            (routes / f"{s['project']}.yaml").write_text(f"slug: {slug}\ngroup: {group}\n")
    return fleet


def simulate(state: Path, fleet: list[dict], interval: float) -> None:
    """Every `interval` seconds, nudge one non-waiting session toward its next
    state. Waiting sessions are left alone so they accumulate until cleared."""
    while True:
        time.sleep(interval)
        active = [s for s in fleet if s["activity"] != "waiting"]
        if not active:
            continue
        s = random.choice(active)
        nxt = random.choice(ACTIVE_NEXT[s["activity"]])
        if nxt == s["activity"]:
            continue
        _set_activity(state, s["sh"], nxt)
        print(f"  {s['project']}: {s['activity']} → {nxt}", flush=True)
        s["activity"] = nxt


def _load_beacon(data_dir: Path, tack_home: Path):
    # collect_sessions reads STATE_DIR / TACK_HOME, both resolved at import from
    # the environment — so point them at the isolated dirs before loading.
    os.environ["CLAUDE_PLUGIN_DATA"] = str(data_dir)
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(REPO)
    os.environ["TACK_HOME"] = str(tack_home)
    loader = importlib.machinery.SourceFileLoader("beacon", str(BEACON_PATH))
    spec = importlib.util.spec_from_loader("beacon", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def make_server(port: int, state: Path, beacon, fleet: list[dict]):
    """A thin demo server: serves the real dashboard + payload, but treats the
    card-click (POST /focus) as 'return this session to its agent'."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse

    dash = DASHBOARD.read_bytes()
    by_hash = {s["sh"]: s for s in fleet}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _hash_arg(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                sh = (json.loads(raw or b"{}").get("hash") or "").strip()
            except ValueError:
                sh = ""
            return sh if re.fullmatch(r"[0-9a-f]{6,}", sh) else ""

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, dash, "text/html; charset=utf-8")
            elif path == "/wip.json":
                self._send(200, json.dumps(beacon.collect_sessions(None)))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            path = urlparse(self.path).path
            sh = self._hash_arg()
            if path == "/focus":
                # Demo's "return to agent": send the stalled session back to work.
                if sh:
                    _set_status(state, sh, "working")
                    if sh in by_hash:
                        by_hash[sh]["status"] = "working"
                self._send(200, json.dumps({"focused": bool(sh), "detail": "returned to agent"}))
            elif path == "/forget":
                files = 0
                if sh:
                    for f in state.glob(f"{sh}.*"):
                        f.unlink()
                        files += 1
                    by_hash.pop(sh, None)
                self._send(200, json.dumps({"forgotten": bool(sh), "files": files}))
            else:
                self._send(404, json.dumps({"error": "not found"}))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed, serve, and simulate a beacon demo fleet.")
    ap.add_argument("--port", type=int, default=8788, help="serve port (default 8788)")
    ap.add_argument("--interval", type=float, default=5.0,
                    help="seconds between simulation ticks (default 5)")
    ap.add_argument("--data-dir", type=Path, default=Path("/tmp/beacon-demo"),
                    help="isolated data dir (default /tmp/beacon-demo)")
    ap.add_argument("--seed-only", action="store_true",
                    help="write a static fleet and exit without serving or simulating")
    args = ap.parse_args()

    data_dir = args.data_dir.expanduser().resolve()
    tack_home = data_dir / "tack"
    fleet = seed(data_dir, tack_home)
    print(f"seeded {len(fleet)} demo sessions → {data_dir}")

    if args.seed_only:
        print("inspect: CLAUDE_PLUGIN_DATA={d} TACK_HOME={t} python3 {b} wip".format(
            d=data_dir, t=tack_home, b=BEACON_PATH))
        return

    beacon = _load_beacon(data_dir, tack_home)
    server = make_server(args.port, data_dir / "state", beacon, fleet)
    threading.Thread(target=simulate, args=(data_dir / "state", fleet, args.interval),
                     daemon=True).start()
    print(f"dashboard → http://127.0.0.1:{args.port}/   "
          f"(click a red card to return it · Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

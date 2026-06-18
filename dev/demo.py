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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BEACON_PATH = REPO / "scripts" / "beacon"
DASHBOARD = REPO / "dashboard" / "index.html"
HOME = Path.home()

# A fictional commerce org's concurrent work. Each entry is one dashboard card.
# Most start working/idle; the fleet drifts toward `waiting` as it runs.
#   route: (slug, group) → a [slug] chip; None means unrouted.
SESSIONS = [
    dict(project="checkout-api", task="idempotency keys for refunds", status="working",
         age=3, route=("checkout", "payments"),
         desc="stripe webhook retries were double-charging"),
    dict(project="checkout-api", task="rebase on main", status="waiting",
         age=95, route=("checkout", "payments"),
         desc="merge conflict in the refund handler — needs you"),
    dict(project="ledger-svc", task="double-entry migration", status="working",
         age=240, route=("ledger", "payments")),
    dict(project="storefront-web", task="PDP gallery redesign", status="idle",
         age=720, route=("storefront", "web"),
         desc="waiting on the Figma handoff"),
    dict(project="storefront-web", task="a/b test cleanup", status="working",
         age=480, route=("storefront", "web")),
    dict(project="search-indexer", task="embedding reindex", status="working",
         age=1500, route=("search", "discovery")),
    dict(project="mobile-ios", task="deep-link QA", status="idle", age=2400),
    dict(project="data-pipeline", task="backfill stuck on warehouse quota",
         status="waiting", age=3600,
         desc="bigquery slot exhaustion — escalated to data-platform"),
    dict(project="auth-svc", task="passkey rollout", status="working",
         age=300, route=("auth", "platform")),
    dict(project="infra-terraform", task="vpc peering to the new region",
         status="paused", age=18000,
         desc="parked on a netops change ticket"),
    dict(project="notifications", task="digest email templates", status="idle", age=900),
    dict(project="analytics-dbt", task="revenue model v2", status="working",
         age=160, route=("analytics", "discovery")),
]

# Next state for a session the sim picks (waiting sessions are sticky — only a
# user click returns them, so they're never auto-mutated). Repeats are no-ops,
# which keeps the board calm; `working` carries a real chance of stalling.
ACTIVE_NEXT = {
    "working": ["working", "working", "idle", "waiting"],
    "idle":    ["idle", "idle", "working"],
    "paused":  ["paused", "paused", "paused", "working"],
}


def _hash(seed: str) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:16]


def _write(path: Path, value: str, mtime: float | None = None) -> None:
    path.write_text(value)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _set_status(state: Path, sh: str, status: str) -> None:
    """Write the authoritative status file (leaving mtime at now, so the session
    surfaces as freshly active) and sync the two waiting-only markers: the
    attention ring, and the focus handle that makes the card clickable. A
    waiting card is the only kind a user can click to return."""
    sig, ovr = state / f"{sh}.signal.status", state / f"{sh}.override.status"
    pend, handle = state / f"{sh}.pending-attention", state / f"{sh}.iterm_session_id"
    if status == "paused":
        _write(ovr, "paused")
        sig.unlink(missing_ok=True)
    else:
        _write(sig, status)
        ovr.unlink(missing_ok=True)
    if status == "waiting":
        _write(pend, "permission")
        _write(handle, f"demo:{sh}")
    else:
        pend.unlink(missing_ok=True)
        handle.unlink(missing_ok=True)


def seed(data_dir: Path, tack_home: Path) -> list[dict]:
    """Wipe and write the initial fleet at staggered ages. Returns the live model
    (hash + current status per session) the simulator mutates."""
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
        status_field = "override.status" if s["status"] == "paused" else "signal.status"
        _write(state / f"{sh}.{status_field}", s["status"], mt)
        if s.get("task"):
            _write(state / f"{sh}.override.task", s["task"], mt)
        if s.get("desc"):
            _write(state / f"{sh}.description", s["desc"], mt)
        if s["status"] == "waiting":  # waiting-only markers: ring + clickable handle
            _write(state / f"{sh}.pending-attention", "permission", mt)
            _write(state / f"{sh}.iterm_session_id", f"demo:{sh}", mt)
        fleet.append({"sh": sh, "project": s["project"], "status": s["status"]})

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
        active = [s for s in fleet if s["status"] != "waiting"]
        if not active:
            continue
        s = random.choice(active)
        nxt = random.choice(ACTIVE_NEXT[s["status"]])
        if nxt == s["status"]:
            continue
        _set_status(state, s["sh"], nxt)
        print(f"  {s['project']}: {s['status']} → {nxt}", flush=True)
        s["status"] = nxt


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

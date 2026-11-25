#!/usr/bin/env python3
"""Render the status panel's lines (STATUS-01, STATUS-03) for a set of
invented sessions, through beacon's own `_status_lines`, under the mode's
ribbon (STATUS-09) when the scenario declares a mode that has one.

    python3 dev/statusline-demo.py          print every scenario in this terminal
    python3 dev/statusline-demo.py --shots  regenerate docs/images/statusline-*.png

Each scenario seeds a throwaway data dir and runs the renderer against it, so
nothing reads or writes your real beacon state, and nothing on the page comes
from a real session: the projects, titles, and the gitlab.example.com host are
invented. The screenshots are the same ANSI output drawn by headless Google
Chrome (`npx playwright screenshot --channel chrome`, so Playwright downloads
no browser of its own), with the SGR attributes the status line uses mapped
to CSS.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import importlib.machinery
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
DOCS_IMAGES = REPO / "docs" / "images"
PLAYWRIGHT = "playwright@1.64.0"
FORGE = "https://gitlab.example.com/meridian"
SESSION_START = "2026-01-05T09:00:00+00:00"
LANDED = "2026-01-05T11:30:00+00:00"
COLUMNS = 96


def mr(project: str, n: int) -> str:
    return f"{FORGE}/{project}/-/merge_requests/{n}"


def issue(project: str, n: int) -> str:
    return f"{FORGE}/{project}/-/issues/{n}"


def release(project: str, tag: str) -> str:
    return f"{FORGE}/{project}/-/tags/{tag}"


# Each scenario is touched oldest first, as a session would touch it; the row
# renders newest first within a line.
SCENARIOS = {
    "single": dict(
        caption="one project, bare refs",
        touches=[
            (issue("storefront-web", 18), {}),
            (issue("storefront-web", 22), {}),
            (mr("storefront-web", 41), dict(title="PDP gallery redesign",
                                            closes=[issue("storefront-web", 18)])),
        ],
    ),
    "multi": dict(
        caption="two projects, named refs, blocked work gray",
        touches=[
            (mr("ledger-svc", 12), dict(title="double-entry migration")),
            (mr("checkout-api", 88), dict(title="idempotency keys for refunds",
                                          waits_on=[mr("ledger-svc", 12)])),
            (mr("storefront-web", 41), dict(title="PDP gallery redesign")),
        ],
    ),
    "stack": dict(
        caption="each CR built on the one above",
        touches=[
            (mr("design-system", 30), dict(title="extract color tokens")),
            (mr("design-system", 31), dict(title="theme provider",
                                           stacked_on=[mr("design-system", 30)])),
            (mr("design-system", 32), dict(title="dark mode toggle",
                                           stacked_on=[mr("design-system", 31)])),
        ],
    ),
    "merged": dict(
        caption="the stack's base merged",
        touches=[
            (mr("design-system", 30), dict(title="extract color tokens",
                                           state="merged", landed_at=LANDED)),
            (mr("design-system", 31), dict(title="theme provider",
                                           stacked_on=[mr("design-system", 30)])),
            (mr("design-system", 32), dict(title="dark mode toggle",
                                           stacked_on=[mr("design-system", 31)])),
        ],
    ),
    "release": dict(
        caption="release ribbon, shipped, open",
        mode=("release", "cutting **v3.1.0**: waiting on the canary"),
        touches=[
            (mr("design-system", 32), dict(title="dark mode toggle",
                                           state="merged", landed_at=LANDED)),
            (mr("design-system", 34), dict(title="changelog for v3.1.0")),
        ],
    ),
    "done": dict(
        caption="done ribbon, shipped",
        mode=("done", "handed off to on-call"),
        touches=[
            (release("design-system", "v3.1.0"), {}),
            (mr("design-system", 32), dict(title="dark mode toggle",
                                           state="merged", landed_at=LANDED)),
        ],
    ),
    "retro": dict(
        caption="no ribbon: the note leads with the glyph",
        mode=("retro", "writing up the *dark mode* rollout"),
        touches=[
            (release("design-system", "v3.1.0"), {}),
        ],
    ),
    "paused": dict(
        caption="ribbon, shipped, open",
        mode=("pause", "waiting on **design review** before the toggle lands"),
        touches=[
            (release("design-system", "v3.1.0"), {}),
            (mr("design-system", 30), dict(title="extract color tokens",
                                           state="merged", landed_at=LANDED)),
            (mr("design-system", 32), dict(title="dark mode toggle")),
        ],
    ),
}


def load_beacon(data_dir: Path):
    os.environ["BEACON_DATA_DIR"] = str(data_dir)
    os.environ["ITERM_SESSION_ID"] = "w0t0p0:STATUS-DEMO"
    loader = importlib.machinery.SourceFileLoader("beacon_demo", str(REPO / "scripts" / "beacon"))
    spec = importlib.util.spec_from_loader("beacon_demo", loader)
    beacon = importlib.util.module_from_spec(spec)
    loader.exec_module(beacon)
    return beacon


def render(scenario: dict) -> tuple[dict | None, str]:
    """The mode's ribbon (None without one) and the status lines for one
    scenario, from a data dir that exists only for this call."""
    with tempfile.TemporaryDirectory(prefix="beacon-statusline-demo-") as tmp:
        beacon = load_beacon(Path(tmp))
        beacon.write_state("session_started_at", SESSION_START)
        if scenario.get("mode"):
            beacon.write_mode(*scenario["mode"])
        # The tack tier would shell out to `tack tree` for whatever route this
        # machine has bound; the demo has no route.
        with mock.patch.object(beacon, "_tack_landed_urls", return_value=set()):
            for url, record in scenario["touches"]:
                beacon._record_deliverable(beacon._deliverable_suffix(url), url,
                                           beacon._project_id_from_url(url))
                if record:
                    beacon._update_links(url, **record)
        mode = beacon._status_panel_mode()
        ribbon = mode if mode and mode["band"] else None
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"COLUMNS": str(COLUMNS)}), \
             mock.patch.object(beacon.sys, "stdin", io.StringIO("{}")), \
             contextlib.redirect_stdout(out):
            lines = beacon._status_lines(mode_note=ribbon is None)
            sys.stdout.write("".join(line + "\n" for line in lines))
        return ribbon, out.getvalue()


# hooks/status-panel.tsx's RIBBON_TEXT and RIBBON_HINT.
RIBBON_TEXT = "#f8f8f2"
RIBBON_HINT = "#bfbfd0"


def _rgb(hexstr: str) -> str:
    h = hexstr.lstrip("#")
    return ";".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def ribbon_ansi(ribbon: dict) -> str:
    """The ribbon as the panel draws it, in truecolor: a row of its hue above
    and below the text."""
    bg = f"\033[48;2;{_rgb(ribbon['band'])}m"
    fg = f"\033[38;2;{_rgb(RIBBON_TEXT)}m"
    hint = f"\033[38;2;{_rgb(RIBBON_HINT)}m"
    text = f" {ribbon['glyph']} {ribbon['label']}"
    body = f"{bg}{fg}\033[1m{text}\033[22m"
    if ribbon["note_line"]:
        body += f"{hint} · {fg}{ribbon['note_line']}"
    blank = f"{bg}\033[K\033[0m"
    tail = f"{hint}\033[3m  type to resume \033[23m" if ribbon["resumes_on_prompt"] else ""
    return f"{blank}\n{body}{tail}\033[K\033[0m\n{blank}\n"


def ribbon_html(ribbon: dict) -> str:
    note = ""
    if ribbon["note_line"]:
        note = (f'<span style="color:{RIBBON_HINT}"> · </span>'
                f'<span style="color:{RIBBON_TEXT}">{ansi_to_html(ribbon["note_line"])}</span>')
    hint = (f'<span style="color:{RIBBON_HINT};font-style:italic">type to resume</span>'
            if ribbon["resumes_on_prompt"] else "")
    return (f'<div class="ribbon" style="background:{ribbon["band"]}">'
            f'<span><b style="color:{RIBBON_TEXT}">{html.escape(ribbon["glyph"])} '
            f'{html.escape(ribbon["label"])}</b>{note}</span>{hint}</div>')


# The attributes the status line emits, as CSS. Colors approximate a dark
# terminal theme; 38;5;141 is the mode note's 256-color purple.
_SGR_ON = {"1": ("font-weight", "bold"), "2": ("opacity", "0.6"), "3": ("font-style", "italic"),
           "9": ("text-decoration", "line-through")}
_SGR_OFF = {"22": ("font-weight", "opacity"), "23": ("font-style",), "29": ("text-decoration",)}
_COLORS = {"32": "#5fd75f", "36": "#4fd1d9", "37": "#d0d0d0", "90": "#808080",
           "38;5;61": "#8787d7", "38;5;141": "#af87ff"}
_TOKEN_RE = re.compile(r"\x1b\]8;;[^\x07]*\x07|\x1b\[([0-9;]*)m|[^\x1b]+")


def ansi_to_html(text: str) -> str:
    style: dict[str, str] = {}
    out = []
    for m in _TOKEN_RE.finditer(text):
        token = m.group(0)
        if token.startswith("\x1b]"):
            continue
        if m.group(1) is not None:
            code = m.group(1)
            if code in ("", "0"):
                style.clear()
            elif code in _COLORS:
                style["color"] = _COLORS[code]
            else:
                for part in code.split(";"):
                    if part in _SGR_ON:
                        key, value = _SGR_ON[part]
                        style[key] = value
                    elif part in _SGR_OFF:
                        for key in _SGR_OFF[part]:
                            style.pop(key, None)
                    elif part in _COLORS:
                        style["color"] = _COLORS[part]
            continue
        css = ";".join(f"{k}:{v}" for k, v in style.items())
        out.append(f'<span style="{css}">{html.escape(token)}</span>' if css else html.escape(token))
    return "".join(out)


PAGE = """<!doctype html>
<meta charset="utf-8">
<style>
  body {{ margin: 0; background: #1b1d23; }}
  .shot {{ padding: 14px 18px; background: #1b1d23; display: inline-block; min-width: 724px;
           font: 14px/1.5 Menlo, "SF Mono", Consolas, monospace; }}
  .ribbon {{ display: flex; justify-content: space-between; padding: 21px 9px;
             margin-bottom: 4px; white-space: pre; }}
  pre {{ margin: 0; color: #d0d0d0; font: inherit; }}
</style>
<div class="shot">{ribbon}<pre>{body}</pre></div>
"""


def shoot(name: str, rendered: tuple[dict | None, str], workdir: Path) -> Path:
    ribbon, lines = rendered
    page = workdir / f"{name}.html"
    page.write_text(PAGE.format(ribbon=ribbon_html(ribbon) if ribbon else "",
                                body=ansi_to_html(lines.rstrip("\n"))), encoding="utf-8")
    rows = lines.count("\n") + (3 if ribbon else 0)
    out = DOCS_IMAGES / f"statusline-{name}.png"
    subprocess.run(["npx", "-y", PLAYWRIGHT, "screenshot", "--channel", "chrome", "--viewport-size",
                    f"760,{28 + 21 * rows}", page.as_uri(), str(out)], check=True,
                   stdout=subprocess.DEVNULL)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--shots", action="store_true",
                    help="write docs/images/statusline-<scenario>.png instead of printing")
    ap.add_argument("scenarios", nargs="*", metavar="scenario",
                    help=f"which to render (default: all of {', '.join(SCENARIOS)})")
    args = ap.parse_args()
    unknown = [n for n in args.scenarios if n not in SCENARIOS]
    if unknown:
        ap.error(f"unknown scenario {', '.join(unknown)}; choose from {', '.join(SCENARIOS)}")
    names = args.scenarios or list(SCENARIOS)
    if args.shots:
        with tempfile.TemporaryDirectory(prefix="beacon-statusline-shots-") as tmp:
            for name in names:
                print(shoot(name, render(SCENARIOS[name]), Path(tmp)).relative_to(REPO))
        return 0
    for name in names:
        print(f"\033[2m{name}: {SCENARIOS[name]['caption']}\033[0m")
        ribbon, lines = render(SCENARIOS[name])
        sys.stdout.write((ribbon_ansi(ribbon) if ribbon else "") + lines)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

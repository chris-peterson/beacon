#!/usr/bin/env python3
"""Render beacon's tab labels under each iTerm2 tab style and font size, and
capture the tab strip of each for review.

Every combination needs its own iTerm2 launch, because the style, the font size
and the tab height are app-wide preferences iTerm2 reads at launch and rewrites
from memory on quit. So each one quits iTerm2, writes the preferences through
`beacon-iterm configure` (which relaunches it), opens a window of sample tabs,
and captures it. Run it from a terminal other than iTerm2: it quits iTerm2
repeatedly, closing every window. At the end it applies your configured layout
(`beacon layout --write`).

The sample labels are composed the way beacon composes them (TITLE-05,
TITLE-06, TITLE-06a) and painted with beacon's weighted tab colors (TAB-04), so
the strip reads as a real one.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BEACON_ITERM = REPO / "bin" / "beacon-iterm"
ITERM = 'application id "com.googlecode.iterm2"'
TAB_COMMAND = "/bin/sleep 900"

SAMPLE_PROJECT = "acme-widget"
# (task, mode, color state): two-line, one-line, a moded label, a blocked one,
# and a task long enough to truncate.
SAMPLE_TABS = (
    ("ship the uploader retry", None, "ready"),
    ("", None, "busy"),
    ("cut 1.2.3", "release", "ready"),
    ("waiting on a permission prompt", None, "blocked"),
    ("a task long enough to run past the edge of the strip", None, "busy"),
)

# Where the first tab starts in a capture: Regular keeps a title bar above the
# strip, the others draw the strip from under the window's traffic lights.
STRIP_TOP = {"minimal": 24, "compact": 24, "regular": 30}
DOCS_IMAGES = REPO / "docs" / "images"
DOCS_STYLE_SIZE = 16
DOCS_SIZE_STYLE = "minimal"
PANEL_GAP = 24
CAPTION_HEIGHT = 34
CANVAS = (33, 34, 44)
CAPTION_COLOR = (205, 210, 230)
CAPTION_FONT = "/System/Library/Fonts/Helvetica.ttc"

LAYOUT_KEYS = ("UseCustomTabBarFontSize", "CustomTabBarFontSize", "TabStyleWithAutomaticOption",
               "DefaultTabBarHeight", "CompactMinimalTabBarHeight")


def load_source(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_beacon():
    return load_source("beacon", REPO / "scripts" / "beacon")


def osascript(script: str, *args: str) -> str:
    r = subprocess.run(["osascript", "-", *args], input=script, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"osascript failed: {r.stderr.strip()}")
    return r.stdout.strip()


def iterm_running() -> bool:
    return osascript(f"return {ITERM} is running") == "true"


def wait_for(predicate, what: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            sys.exit(f"timed out waiting for {what}")
        time.sleep(0.5)


def iterm_answering() -> bool:
    r = subprocess.run(["osascript", "-e", f"tell {ITERM} to count windows"],
                       capture_output=True, text=True)
    return r.returncode == 0


def quit_iterm() -> None:
    if iterm_running():
        osascript(f"tell {ITERM} to quit")
        wait_for(lambda: not iterm_running(), "iTerm2 to quit")


def apply_layout(style: str, size: int) -> None:
    """Write the style, size and height with iTerm2 down; configure relaunches it."""
    quit_iterm()
    subprocess.run(["python3", str(BEACON_ITERM), "configure", "--write", "--yes",
                    "--tab-style", style, "--tab-font-size", str(size),
                    "--keys", ",".join(LAYOUT_KEYS)],
                   check=True, stdout=subprocess.DEVNULL)
    wait_for(iterm_running, "iTerm2 to relaunch")
    wait_for(iterm_answering, "iTerm2 to answer Apple Events")


def tab_label(beacon, style: str, task: str, mode: str | None) -> str:
    indent1, indent2 = beacon.TAB_LABEL_INDENT[style]
    lead = " " * indent1 + (beacon.MODE_SPECS[mode]["glyph"] if mode else beacon.DEV_TITLE_LEAD)
    line2 = f"\n{' ' * indent2}{task}" if task else ""
    return f"<b>{lead}{SAMPLE_PROJECT}</b>{line2}"


def tab_hex(beacon, style: str, color_state: str) -> str:
    return beacon._mute_hex(beacon.COLOR_PALETTE[color_state],
                            beacon.TAB_MUTE[style].get(color_state, 1.0))


OPEN_WINDOW = f'''
on run argv
    tell {ITERM}
        set w to (create window with profile "beacon-dev" command "{TAB_COMMAND}")
        set bounds of w to {{80, 60, 1000, 760}}
        repeat ((count of argv) - 1) times
            tell w to create tab with profile "beacon-dev" command "{TAB_COMMAND}"
        end repeat
        set ttys to {{}}
        repeat with i from 1 to count of argv
            set s to current session of tab i of w
            set name of s to item i of argv
            set end of ttys to tty of s
        end repeat
        tell tab 1 of w to select
        set AppleScript's text item delimiters to ","
        set b to bounds of w
        return ((item 1 of b) as text) & "," & ((item 2 of b) as text) & "," & ((item 3 of b) as text) & "," & ((item 4 of b) as text) & ";" & (ttys as text)
    end tell
end run
'''


def capture(beacon, style: str, size: int, out: Path) -> Path:
    labels = [tab_label(beacon, style, task, mode) for task, mode, _ in SAMPLE_TABS]
    bounds, ttys = osascript(OPEN_WINDOW, *labels).split(";")
    ttys = ttys.split(",")
    for tty, (_, _, state) in zip(ttys, SAMPLE_TABS):
        subprocess.run(["python3", str(BEACON_ITERM), "tab-color", tab_hex(beacon, style, state),
                        "--tty", tty], check=True)
    time.sleep(2)
    x1, y1, x2, y2 = (int(v) for v in bounds.split(","))
    path = out / f"{style}-{size}pt.png"
    subprocess.run(["screencapture", "-x", "-R", f"{x1},{y1},{x2 - x1},{y2 - y1}", str(path)],
                   check=True)
    for tty in ttys:
        subprocess.run(["pkill", "-t", tty.removeprefix("/dev/"), "sleep"])
    return path


def strip_crop(path: Path, style: str, size: int, strip_width: int, tab_height):
    """The tab strip of one capture: every sample tab, and nothing of the pane."""
    from PIL import Image

    top = STRIP_TOP[style]
    bottom = top + len(SAMPLE_TABS) * tab_height(size) + 6
    return Image.open(path).convert("RGB").crop((0, top, strip_width, bottom))


def montage(panels: list[tuple[str, object]], dest: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(CAPTION_FONT, 20)
    width = sum(img.width for _, img in panels) + PANEL_GAP * (len(panels) + 1)
    height = CAPTION_HEIGHT + max(img.height for _, img in panels) + PANEL_GAP * 2
    canvas = Image.new("RGB", (width, height), CANVAS)
    draw = ImageDraw.Draw(canvas)
    x = PANEL_GAP
    for caption, img in panels:
        draw.text((x, PANEL_GAP), caption, font=font, fill=CAPTION_COLOR)
        canvas.paste(img, (x, PANEL_GAP + CAPTION_HEIGHT))
        x += img.width + PANEL_GAP
    canvas.save(dest, optimize=True)


def compose_docs(out: Path, styles: list[str], sizes: list[int]) -> list[Path]:
    """docs/images/tab-styles.png (every style at one size) and tab-sizes.png
    (one style at every size), from the captures in `out`."""
    tab_height = load_source("beacon_iterm", BEACON_ITERM)._tab_height
    strip_width = int(float(subprocess.run(
        ["defaults", "read", "com.googlecode.iterm2", "LeftTabBarWidth"],
        capture_output=True, text=True, check=True).stdout))

    def panel(style, size):
        return strip_crop(out / f"{style}-{size}pt.png", style, size, strip_width, tab_height)

    written = [DOCS_IMAGES / "tab-styles.png", DOCS_IMAGES / "tab-sizes.png"]
    montage([(style, panel(style, DOCS_STYLE_SIZE)) for style in styles], written[0])
    montage([(f"{size}pt", panel(DOCS_SIZE_STYLE, size)) for size in sizes], written[1])
    return written


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--styles", default="minimal,compact,regular")
    p.add_argument("--sizes", default="12,16,20,24")
    p.add_argument("--out", type=Path, required=True, help="directory for the captures")
    p.add_argument("--no-restore", action="store_true",
                   help="leave the last combination applied instead of your configured layout")
    p.add_argument("--docs", action="store_true",
                   help=f"compose docs/images/tab-styles.png and tab-sizes.png from the "
                        f"captures (needs Pillow; wants every style at {DOCS_STYLE_SIZE}pt "
                        f"and {DOCS_SIZE_STYLE} at every size)")
    p.add_argument("--skip-capture", action="store_true",
                   help="reuse the captures already in --out")
    args = p.parse_args()
    styles = args.styles.split(",")
    sizes = [int(n) for n in args.sizes.split(",")]

    if not args.skip_capture:
        if os.environ.get("TERM_PROGRAM") == "iTerm.app":
            sys.exit("run this from a terminal other than iTerm2: it quits iTerm2")
        beacon = load_beacon()
        args.out.mkdir(parents=True, exist_ok=True)
        for style in styles:
            for size in sizes:
                apply_layout(style, size)
                print(f"{style} {size}pt: {capture(beacon, style, size, args.out)}", flush=True)
    if args.docs:
        for path in compose_docs(args.out, styles, sizes):
            print(f"wrote {path.relative_to(REPO)}")
    if not args.no_restore and not args.skip_capture:
        quit_iterm()
        subprocess.run(["python3", str(REPO / "scripts" / "beacon"), "layout", "--write", "--yes"],
                       check=True, stdout=subprocess.DEVNULL)
        print("restored your configured layout")


if __name__ == "__main__":
    main()

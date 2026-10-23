#!/usr/bin/env python3
"""Rebuild the OSC 7501 adoption chart and tables in docs/program-status.md
from dev/program-status.json.

    python3 dev/program-status.py          rewrite the generated parts of the page
    python3 dev/program-status.py --check  exit 1 if the page is out of date

The JSON is the record: one entry per program, with its state, the dates the
chart draws, and the events the sources table lists. The page's prose stays
hand-written; only the chart SVG, the sources table, the "Checked against"
date, and the per-group status tables are replaced.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dev" / "program-status.json"
PAGE = ROOT / "docs" / "program-status.md"

PLOT_LEFT, PLOT_RIGHT = 160.0, 860.0
STATUS_X, NAME_X, WIDTH = 880, 150, 1040
ROW = 30
SPEC_ROW = 38
GROUP_GAP = 22
HEADER_RULE = 72
KIND_RANK = {"shipped": 0, "merged": 1, "open": 2, "declined": 3, "none": 4}


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def short(d: date) -> str:
    return f"{d:%b} {d.day}"


class Axis:
    def __init__(self, start: date, as_of: date):
        self.start = start
        self.as_of = as_of
        self.days = (as_of - start).days + 2
        self.step = (PLOT_RIGHT - PLOT_LEFT) / self.days

    def x(self, d: date) -> float:
        return PLOT_LEFT + ((d - self.start).days + 0.5) * self.step

    def edge(self, i: int) -> float:
        return PLOT_LEFT + i * self.step

    @property
    def today(self) -> float:
        return self.edge((self.as_of - self.start).days + 1)


def diamond(cls: str, x: float, y: float) -> str:
    return f'<path class="{cls}" d="M{x:.1f},{y - 7:.1f} L{x + 7:.1f},{y:.1f} L{x:.1f},{y + 7:.1f} L{x - 7:.1f},{y:.1f} Z"/>'


def tooltip(name: str, program: dict) -> str:
    parts = [f"{e['event']} {short(date.fromisoformat(e['date']))}" for e in program.get("events", [])]
    if program.get("tip"):
        parts.append(program["tip"])
    return f"{name}: " + "; ".join(parts)


def day_cells(axis: Axis, cls: str, y: float, height: float) -> list[str]:
    """One hover target per day, classed c<i> so the generated :has() rules can
    light that day's column; docsify runs no script from the page, so CSS is
    the only way to track the pointer."""
    return [
        f'<rect class="{cls} c{i}" x="{axis.edge(i):.1f}" y="{y:.1f}" width="{axis.step:.1f}" height="{height}"/>'
        for i in range(axis.days)
    ]


def program_row(axis: Axis, p: dict, y0: float) -> list[str]:
    kind = p["kind"]
    out = [
        f'<a href="{esc(p["link"])}" target="_blank" rel="noopener"><title>{esc(tooltip(p["name"], p))}</title>',
        f'<rect class="rowhit" x="0" y="{y0:.1f}" width="{PLOT_LEFT:.0f}" height="{ROW}"/>',
        *day_cells(axis, "rowhit", y0, ROW),
        f'<rect class="rowhit" x="{PLOT_RIGHT:.0f}" y="{y0:.1f}" width="{WIDTH - PLOT_RIGHT:.0f}" height="{ROW}"/>',
        f'<text class="name" x="{NAME_X}" y="{y0 + 19:.1f}" text-anchor="end">{esc(p["name"])}</text>',
    ]
    mid = y0 + 15
    if kind != "none":
        xs = axis.x(date.fromisoformat(p["start"]))
    if kind == "shipped":
        xr = axis.x(date.fromisoformat(p["released"]))
        if xr > xs:
            out.append(f'<rect class="bar-work" x="{xs:.1f}" y="{y0 + 9:.1f}" width="{xr - xs:.1f}" height="12" rx="3"/>')
        out.append(f'<line class="live" x1="{xr:.1f}" x2="{axis.today:.1f}" y1="{mid:.1f}" y2="{mid:.1f}"/>')
        out.append(diamond("ms-ship", xr, mid))
    elif kind in ("merged", "open"):
        out.append(f'<rect class="bar-{kind}" x="{xs:.1f}" y="{y0 + 9:.1f}" width="{axis.today - xs:.1f}" height="12" rx="3"/>')
    elif kind == "declined":
        out.append(f'<path class="decl" d="M{xs - 5:.1f},{mid - 5:.1f} L{xs + 5:.1f},{mid + 5:.1f} M{xs - 5:.1f},{mid + 5:.1f} L{xs + 5:.1f},{mid - 5:.1f}"/>')
    out.append(f'<text class="status st-link st-{kind}" x="{STATUS_X}" y="{y0 + 19:.1f}">{esc(p["status"])}</text>')
    out.append("</a>")
    return out


def spec_row(axis: Axis, spec: dict, y0: float) -> list[str]:
    revs = spec["revisions"]
    first, last = (axis.x(date.fromisoformat(r["date"])) for r in (revs[0], revs[-1]))
    mid = y0 + 15
    out = [
        f'<text class="name" x="{NAME_X}" y="{y0 + 19:.1f}" text-anchor="end">{esc(spec["name"])}</text>',
        f'<rect class="bar-spec" x="{first:.1f}" y="{y0 + 11:.1f}" width="{last - first:.1f}" height="8" rx="4"/>',
    ]
    for r in revs:
        x = axis.x(date.fromisoformat(r["date"]))
        tip = f"{short(date.fromisoformat(r['date']))}: {r['tip']}"
        out.append(
            f'<a href="{esc(r["url"])}" target="_blank" rel="noopener"><title>{esc(tip)}</title>'
            f'{diamond("ms-spec", x, mid)}<rect class="hit" x="{x - 12:.1f}" y="{mid - 12:.1f}" width="24" height="24"/></a>'
        )
        label_y = y0 + 35 if r.get("below") else y0 + 3
        out.append(f'<text class="mslbl" x="{x + 2:.1f}" y="{label_y:.1f}">{esc(r["label"])}</text>')
    out.append(f'<a href="{esc(spec["link"])}" target="_blank" rel="noopener"><text class="status st-link" x="{STATUS_X}" y="{y0 + 19:.1f}">{esc(spec["status"])}</text></a>')
    return out


def charted(group: dict) -> list[dict]:
    return [p for p in group["programs"] if p.get("chart", True)]


def svg(data: dict) -> str:
    axis = Axis(date.fromisoformat(data["start"]), date.fromisoformat(data["as_of"]))
    body: list[str] = []
    grp_y = HEADER_RULE + 32
    body.append(f'<text class="grp" x="12" y="{grp_y}">Spec</text>')
    body.append(f'<line class="grpline" x1="12" x2="{WIDTH - 12}" y1="{grp_y + 8}" y2="{grp_y + 8}"/>')
    y = grp_y + 18
    body += day_cells(axis, "hcell", y - 10, SPEC_ROW + 10)
    body += spec_row(axis, data["spec"], y)
    y += SPEC_ROW
    for group in data["groups"]:
        grp_y = y + GROUP_GAP
        body.append(f'<text class="grp" x="12" y="{grp_y}">{esc(group["name"])}</text>')
        body.append(f'<line class="grpline" x1="12" x2="{WIDTH - 12}" y1="{grp_y + 8}" y2="{grp_y + 8}"/>')
        y = grp_y + 18
        for p in charted(group):
            body += program_row(axis, p, y)
            y += ROW
    bottom = y - 4
    height = y + 2

    head: list[str] = []
    for i in range(axis.days):
        d = axis.start + timedelta(days=i)
        if d.weekday() >= 5:
            head.append(f'<rect class="wkend" x="{axis.edge(i):.1f}" y="52" width="{axis.step:.1f}" height="{bottom - 52:.0f}"/>')
        head.append(f'<rect class="colhl h{i}" x="{axis.edge(i):.1f}" y="52" width="{axis.step:.1f}" height="{bottom - 52:.0f}"/>')
        if d.weekday() != 0:
            head.append(f'<line class="dayline" x1="{axis.edge(i):.1f}" x2="{axis.edge(i):.1f}" y1="52" y2="{bottom:.0f}"/>')
        head.append(f'<text class="day dl{i}" x="{axis.x(d):.1f}" y="64" text-anchor="middle">{d.day}</text>')
    today = axis.today
    tag = f"As of {short(axis.as_of)}"
    head.append(f'<line class="today" x1="{today:.1f}" x2="{today:.1f}" y1="20" y2="{bottom:.0f}"/>')
    head.append(f'<rect class="todaytag" x="{today - 44:.1f}" y="2" width="88" height="18" rx="9"/>')
    head.append(f'<text class="todaytxt" x="{today:.1f}" y="15" text-anchor="middle">{tag}</text>')
    for i in range(axis.days):
        d = axis.start + timedelta(days=i)
        if d.weekday() == 0:
            x = axis.edge(i)
            head.append(f'<line class="week" x1="{x:.1f}" x2="{x:.1f}" y1="30" y2="{bottom:.0f}"/>')
            head.append(f'<text class="weekhd" x="{x + 6:.1f}" y="42">Week of {short(d)}</text>')
    head.append(f'<line class="rule" x1="{PLOT_LEFT:.0f}" x2="{PLOT_RIGHT:.0f}" y1="{HEADER_RULE}" y2="{HEADER_RULE}"/>')
    head.append(f'<text class="colhd" x="{STATUS_X}" y="42">Where it stands</text>')
    head += day_cells(axis, "hcell", 52, HEADER_RULE - 52)
    hovered = lambda target: ",".join(f".osc-gantt:has(.c{i}:hover) .{target}{i}" for i in range(axis.days))
    head.append(f"<style>{hovered('h')}{{opacity:1}}{hovered('dl')}{{fill:var(--fg);font-weight:600}}</style>")

    shipped = sum(p["kind"] == "shipped" for g in data["groups"] for p in charted(g))
    title = f"OSC 7501 adoption, {short(axis.start)} to {short(axis.as_of)} {axis.as_of.year}"
    desc = (
        f"A Gantt chart: the spec from its {short(axis.start)} draft through revision "
        f"{data['spec']['revisions'][-1]['label']} on {short(date.fromisoformat(data['spec']['revisions'][-1]['date']))}, "
        f"then each terminal and program from its first merged change or request to its release. "
        f"{shipped} programs had shipped by {short(axis.as_of)}. The sources table below lists every date."
    )
    return "\n".join(
        [
            f'<svg class="osc-gantt" viewBox="0 0 {WIDTH} {height:.0f}" role="img" aria-labelledby="osc-g-t osc-g-d">',
            f'<title id="osc-g-t">{esc(title)}</title>',
            f'<desc id="osc-g-d">{esc(desc)}</desc>',
            *head,
            *body,
            "</svg>",
        ]
    )


def sources(data: dict) -> str:
    rows = [(date.fromisoformat(r["date"]), 0, "Spec", r) for r in data["spec"]["revisions"]]
    order = 1
    for group in data["groups"]:
        for p in group["programs"]:
            for e in p.get("events", []):
                rows.append((date.fromisoformat(e["date"]), order, p["name"], e))
            order += 1
    rows.sort(key=lambda r: (r[0], r[1]))
    lines = ["| Date | Program | Event | Source |", "|:---|:---|:---|:---|"]
    lines += [f"| {short(d)} | {name} | {e['event']} | [{e['source']}]({e['url']}) |" for d, _, name, e in rows]
    return "\n".join(lines)


def status_tables(data: dict) -> str:
    blocks = []
    for group in data["groups"]:
        ranked = sorted(enumerate(group["programs"]), key=lambda ip: (KIND_RANK[ip[1]["kind"]], ip[0]))
        lines = [
            f"### {group['heading']}",
            "",
            f"| Program | Status | Source | {group['note_column']} |",
            "|:---|:---|:---|:---|",
        ]
        for _, p in ranked:
            source = f"[{p['source']}]({p['link']})" if p.get("link") else ""
            lines.append(f"| {p['name']} | {p['status']} | {source} | {p.get('note', '')} |")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render(page: str, data: dict) -> str:
    page = re.sub(r'<svg class="osc-gantt".*?</svg>', lambda _: svg(data), page, count=1, flags=re.S)
    page = re.sub(
        r"(<summary>Sources for each date</summary>\n\n).*?(\n\n</details>)",
        lambda m: m.group(1) + sources(data) + m.group(2),
        page,
        count=1,
        flags=re.S,
    )
    page = re.sub(
        r"(changelogs on \*\*)\d{4}-\d{2}-\d{2}(\*\*)",
        lambda m: m.group(1) + data["as_of"] + m.group(2),
        page,
        count=1,
    )
    page = re.sub(
        r"### Terminals.*?(?=\n## )",
        lambda _: status_tables(data) + "\n",
        page,
        count=1,
        flags=re.S,
    )
    return page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the page is out of date")
    args = parser.parse_args()
    data = json.loads(DATA.read_text())
    current = PAGE.read_text()
    rendered = render(current, data)
    if args.check:
        if rendered != current:
            print(f"{PAGE.relative_to(ROOT)} is out of date; run `just program-status`", file=sys.stderr)
            return 1
        return 0
    PAGE.write_text(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())

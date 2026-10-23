# Program status (OSC 7501)

Coding agents and long builds spend most of their time either working or waiting on you, and until October 2026 a terminal had no standard way to hear which. Each tool that wanted the answer guessed from the screen or the window title, or wired its own socket. The **Program Status Protocol** is an escape sequence a program writes to say what it is doing, so any terminal can show it the same way.

Mitchell Hashimoto announced it on [2026-10-06](https://mitchellh.com/writing/program-status-osc7501), and the [spec](https://www.superlogical.com/rex/docs/build/program-status) reached revision 0.4 four days later. Within two weeks Claude Code was sending it and iTerm2 was drawing it on the tab, which is where it meets beacon.

## The protocol in brief

A program writes one report per change:

```text
ESC ] 7501 ; state=blocked:kind=permission:app=claude-code:msg=<base64> ESC \
```

| Key | Meaning |
|:---|:---|
| `state` | `idle`, `working`, `done`, `blocked`, `error`, or `clear` to remove records. Required. |
| `kind` | Why it's blocked: `permission`, `question`, or `auth`. |
| `progress` | 0 to 100, for `working` or `blocked`. Absent means indeterminate. |
| `app` | A stable program name, such as `claude-code` or `codex`. |
| `id` | A `/`-separated path, so one program can report several tasks: the session `idle` while a sub-agent is `blocked`. |
| `title`, `msg` | Base64 UTF-8 text: a short label, and one human-readable line. |

A program asks whether the terminal supports it with `ESC ] 7501 ; ? ESC \`, and a terminal that does replies with `?`. `working` and `blocked` records end when the program exits or the shell prompt returns. `done` and `error` stay until the terminal decides you've seen them, which in iTerm2 is when you type in the pane.

## Who supports it

<style>
.osc {
  --panel: #282a36; --raised: #2f3241; --line: rgba(139,233,253,0.14);
  --fg: #f8f8f2; --muted: #b8bed6; --faint: #7e8290; --grid: #343746;
  --accent: #3987e5; --spec: #bd93f9; --today: #ff5555; --link: #8be9fd;
  --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
  width: max(100%, min(1080px, calc(100vw - 340px))); box-sizing: border-box;
  position: relative; left: 50%; transform: translateX(-50%);
  margin: 1.25rem 0 1.5rem; padding: 1.1rem 1.1rem 0.4rem; border: 1px solid var(--line);
  border-radius: 12px; background: var(--panel); color: var(--fg); font-family: var(--sans);
}
.osc-scroll { overflow-x: auto; }
.osc-gantt { display: block; width: 100%; min-width: 900px; height: auto; font-family: var(--sans); }
.osc-gantt .wkend { fill: #ffffff; opacity: 0.025; }
.osc-gantt .week { stroke: var(--grid); stroke-width: 1; }
.osc-gantt .rule, .osc-gantt .grpline { stroke: var(--grid); stroke-width: 1; }
.osc-gantt .day { fill: var(--faint); font-size: 10px; font-variant-numeric: tabular-nums; }
.osc-gantt .weekhd, .osc-gantt .colhd { fill: var(--muted); font-size: 11px; }
.osc-gantt .weekhd, .osc-gantt .day { paint-order: stroke; stroke: var(--panel); stroke-width: 4px; stroke-linejoin: round; }
.osc-gantt .grp { fill: var(--fg); font-size: 12px; font-weight: 600; }
.osc-gantt .name { fill: var(--fg); font-size: 12.5px; }
.osc-gantt .status { fill: var(--muted); font-size: 12px; }
.osc-gantt .st-shipped { fill: var(--fg); }
.osc-gantt .st-declined, .osc-gantt .st-open { fill: var(--faint); }
.osc-gantt .mslbl { fill: var(--muted); font-size: 11px; }
.osc-gantt .bar-spec { fill: var(--spec); opacity: 0.22; }
.osc-gantt .ms-spec { fill: var(--spec); stroke: var(--panel); stroke-width: 2; }
.osc-gantt .bar-work { fill: var(--accent); opacity: 0.35; }
.osc-gantt .ms-ship { fill: var(--accent); stroke: var(--panel); stroke-width: 2; }
.osc-gantt .live { stroke: var(--accent); stroke-width: 2; opacity: 0.55; stroke-linecap: round; }
.osc-gantt .bar-merged { fill: rgba(57,135,229,0.12); stroke: var(--accent); stroke-width: 1.5; }
.osc-gantt .bar-open { fill: rgba(126,130,144,0.12); stroke: var(--faint); stroke-width: 1.5; }
.osc-gantt .decl { stroke: var(--faint); stroke-width: 2; stroke-linecap: round; }
.osc-gantt .today { stroke: var(--today); stroke-width: 2; }
.osc-gantt .todaytag { fill: var(--today); }
.osc-gantt .todaytxt { fill: #21222c; font-size: 11px; font-weight: 600; }
.osc-gantt .hit, .osc-gantt .rowhit, .osc-gantt .hcell { fill: transparent; }
.osc-gantt .rowhit, .osc-gantt .hcell { shape-rendering: crispEdges; }
.osc-gantt .dayline { stroke: var(--grid); stroke-width: 1; opacity: 0.45; }
.osc-gantt .colhl { fill: var(--link); opacity: 0; fill-opacity: 0.1; pointer-events: none; }
.osc-gantt :is(.bar-work, .bar-merged, .bar-open, .live, .ms-ship, .decl, .bar-spec) { pointer-events: none; }
.osc-gantt a, .osc-gantt a text { cursor: pointer; text-decoration: none !important; border: 0 !important; }
.osc-gantt a:hover .rowhit, .osc-gantt a:focus-visible .rowhit { fill: rgba(139,233,253,0.06); }
.osc-gantt a:focus-visible { outline: none; }
.osc-gantt a:focus-visible .rowhit { stroke: var(--link); stroke-width: 1; }
.osc-gantt .st-link { fill: var(--link); }
.osc-gantt .st-link.st-open, .osc-gantt .st-link.st-declined, .osc-gantt .st-link.st-none { fill: var(--link); opacity: 0.7; }
.osc-gantt a:hover .st-link, .osc-gantt a:focus-visible .st-link { text-decoration: underline !important; opacity: 1; }
.osc-key { display: flex; flex-wrap: wrap; gap: 0.4rem 1.4rem; margin: 0.6rem 0 0.2rem; font-size: 0.8rem; color: var(--muted); }
.osc-key svg { width: 22px; height: 12px; vertical-align: -1px; margin-right: 0.4rem; }
.osc-refs { margin: 0.5rem 0 0.7rem; border-top: 1px solid var(--grid); padding-top: 0.6rem; }
.osc-refs summary { cursor: pointer; font-size: 0.85rem; color: var(--muted); list-style-position: inside; }
.osc-refs summary:hover { color: var(--fg); }
.osc-refs table { display: table; width: 100%; margin: 0.7rem 0 0.2rem; border-collapse: collapse; font-size: 0.83rem; }
.osc-refs th, .osc-refs td { background: transparent !important; color: var(--fg) !important; border: 0 !important;
  border-bottom: 1px solid var(--grid) !important; padding: 0.35rem 0.75rem 0.35rem 0 !important; text-align: left; }
.osc-refs th { color: var(--muted) !important; font-weight: 600; }
.osc-refs td:first-child { color: var(--muted) !important; font-variant-numeric: tabular-nums; white-space: nowrap; }
.osc-refs tr, .osc-refs tr:nth-child(2n), .osc-refs thead tr { background: transparent !important; }
.osc-refs tbody tr:nth-child(2n) td { background: rgba(255,255,255,0.03) !important; }
.osc-refs tbody tr:hover td { background: rgba(139,233,253,0.06) !important; }
.osc-refs a { color: var(--link) !important; }
.osc-refs code { font-size: 0.85em; background: rgba(128,128,128,0.18) !important; color: inherit !important; }
</style>

<div class="osc">
<div class="osc-scroll">
<svg class="osc-gantt" viewBox="0 0 1040 1422" role="img" aria-labelledby="osc-g-t osc-g-d">
<title id="osc-g-t">OSC 7501 adoption, Sep 28 to Oct 22 2026</title>
<desc id="osc-g-d">A Gantt chart: the spec from its Sep 28 draft through revision 0.4 on Oct 10, then each terminal and program from its first merged change or request to its release. 11 programs had shipped by Oct 22. The sources table below lists every date.</desc>
<rect class="colhl h0" x="160.0" y="52" width="26.9" height="1364"/>
<text class="day dl0" x="173.5" y="64" text-anchor="middle">28</text>
<rect class="colhl h1" x="186.9" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="186.9" x2="186.9" y1="52" y2="1416"/>
<text class="day dl1" x="200.4" y="64" text-anchor="middle">29</text>
<rect class="colhl h2" x="213.8" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="213.8" x2="213.8" y1="52" y2="1416"/>
<text class="day dl2" x="227.3" y="64" text-anchor="middle">30</text>
<rect class="colhl h3" x="240.8" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="240.8" x2="240.8" y1="52" y2="1416"/>
<text class="day dl3" x="254.2" y="64" text-anchor="middle">1</text>
<rect class="colhl h4" x="267.7" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="267.7" x2="267.7" y1="52" y2="1416"/>
<text class="day dl4" x="281.2" y="64" text-anchor="middle">2</text>
<rect class="wkend" x="294.6" y="52" width="26.9" height="1364"/>
<rect class="colhl h5" x="294.6" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="294.6" x2="294.6" y1="52" y2="1416"/>
<text class="day dl5" x="308.1" y="64" text-anchor="middle">3</text>
<rect class="wkend" x="321.5" y="52" width="26.9" height="1364"/>
<rect class="colhl h6" x="321.5" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="321.5" x2="321.5" y1="52" y2="1416"/>
<text class="day dl6" x="335.0" y="64" text-anchor="middle">4</text>
<rect class="colhl h7" x="348.5" y="52" width="26.9" height="1364"/>
<text class="day dl7" x="361.9" y="64" text-anchor="middle">5</text>
<rect class="colhl h8" x="375.4" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="375.4" x2="375.4" y1="52" y2="1416"/>
<text class="day dl8" x="388.8" y="64" text-anchor="middle">6</text>
<rect class="colhl h9" x="402.3" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="402.3" x2="402.3" y1="52" y2="1416"/>
<text class="day dl9" x="415.8" y="64" text-anchor="middle">7</text>
<rect class="colhl h10" x="429.2" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="429.2" x2="429.2" y1="52" y2="1416"/>
<text class="day dl10" x="442.7" y="64" text-anchor="middle">8</text>
<rect class="colhl h11" x="456.2" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="456.2" x2="456.2" y1="52" y2="1416"/>
<text class="day dl11" x="469.6" y="64" text-anchor="middle">9</text>
<rect class="wkend" x="483.1" y="52" width="26.9" height="1364"/>
<rect class="colhl h12" x="483.1" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="483.1" x2="483.1" y1="52" y2="1416"/>
<text class="day dl12" x="496.5" y="64" text-anchor="middle">10</text>
<rect class="wkend" x="510.0" y="52" width="26.9" height="1364"/>
<rect class="colhl h13" x="510.0" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="510.0" x2="510.0" y1="52" y2="1416"/>
<text class="day dl13" x="523.5" y="64" text-anchor="middle">11</text>
<rect class="colhl h14" x="536.9" y="52" width="26.9" height="1364"/>
<text class="day dl14" x="550.4" y="64" text-anchor="middle">12</text>
<rect class="colhl h15" x="563.8" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="563.8" x2="563.8" y1="52" y2="1416"/>
<text class="day dl15" x="577.3" y="64" text-anchor="middle">13</text>
<rect class="colhl h16" x="590.8" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="590.8" x2="590.8" y1="52" y2="1416"/>
<text class="day dl16" x="604.2" y="64" text-anchor="middle">14</text>
<rect class="colhl h17" x="617.7" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="617.7" x2="617.7" y1="52" y2="1416"/>
<text class="day dl17" x="631.2" y="64" text-anchor="middle">15</text>
<rect class="colhl h18" x="644.6" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="644.6" x2="644.6" y1="52" y2="1416"/>
<text class="day dl18" x="658.1" y="64" text-anchor="middle">16</text>
<rect class="wkend" x="671.5" y="52" width="26.9" height="1364"/>
<rect class="colhl h19" x="671.5" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="671.5" x2="671.5" y1="52" y2="1416"/>
<text class="day dl19" x="685.0" y="64" text-anchor="middle">17</text>
<rect class="wkend" x="698.5" y="52" width="26.9" height="1364"/>
<rect class="colhl h20" x="698.5" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="698.5" x2="698.5" y1="52" y2="1416"/>
<text class="day dl20" x="711.9" y="64" text-anchor="middle">18</text>
<rect class="colhl h21" x="725.4" y="52" width="26.9" height="1364"/>
<text class="day dl21" x="738.8" y="64" text-anchor="middle">19</text>
<rect class="colhl h22" x="752.3" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="752.3" x2="752.3" y1="52" y2="1416"/>
<text class="day dl22" x="765.8" y="64" text-anchor="middle">20</text>
<rect class="colhl h23" x="779.2" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="779.2" x2="779.2" y1="52" y2="1416"/>
<text class="day dl23" x="792.7" y="64" text-anchor="middle">21</text>
<rect class="colhl h24" x="806.2" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="806.2" x2="806.2" y1="52" y2="1416"/>
<text class="day dl24" x="819.6" y="64" text-anchor="middle">22</text>
<rect class="colhl h25" x="833.1" y="52" width="26.9" height="1364"/>
<line class="dayline" x1="833.1" x2="833.1" y1="52" y2="1416"/>
<text class="day dl25" x="846.5" y="64" text-anchor="middle">23</text>
<line class="today" x1="833.1" x2="833.1" y1="20" y2="1416"/>
<rect class="todaytag" x="789.1" y="2" width="88" height="18" rx="9"/>
<text class="todaytxt" x="833.1" y="15" text-anchor="middle">As of Oct 22</text>
<line class="week" x1="160.0" x2="160.0" y1="30" y2="1416"/>
<text class="weekhd" x="166.0" y="42">Week of Sep 28</text>
<line class="week" x1="348.5" x2="348.5" y1="30" y2="1416"/>
<text class="weekhd" x="354.5" y="42">Week of Oct 5</text>
<line class="week" x1="536.9" x2="536.9" y1="30" y2="1416"/>
<text class="weekhd" x="542.9" y="42">Week of Oct 12</text>
<line class="week" x1="725.4" x2="725.4" y1="30" y2="1416"/>
<text class="weekhd" x="731.4" y="42">Week of Oct 19</text>
<line class="rule" x1="160" x2="860" y1="72" y2="72"/>
<text class="colhd" x="880" y="42">Where it stands</text>
<rect class="hcell c0" x="160.0" y="52.0" width="26.9" height="20"/>
<rect class="hcell c1" x="186.9" y="52.0" width="26.9" height="20"/>
<rect class="hcell c2" x="213.8" y="52.0" width="26.9" height="20"/>
<rect class="hcell c3" x="240.8" y="52.0" width="26.9" height="20"/>
<rect class="hcell c4" x="267.7" y="52.0" width="26.9" height="20"/>
<rect class="hcell c5" x="294.6" y="52.0" width="26.9" height="20"/>
<rect class="hcell c6" x="321.5" y="52.0" width="26.9" height="20"/>
<rect class="hcell c7" x="348.5" y="52.0" width="26.9" height="20"/>
<rect class="hcell c8" x="375.4" y="52.0" width="26.9" height="20"/>
<rect class="hcell c9" x="402.3" y="52.0" width="26.9" height="20"/>
<rect class="hcell c10" x="429.2" y="52.0" width="26.9" height="20"/>
<rect class="hcell c11" x="456.2" y="52.0" width="26.9" height="20"/>
<rect class="hcell c12" x="483.1" y="52.0" width="26.9" height="20"/>
<rect class="hcell c13" x="510.0" y="52.0" width="26.9" height="20"/>
<rect class="hcell c14" x="536.9" y="52.0" width="26.9" height="20"/>
<rect class="hcell c15" x="563.8" y="52.0" width="26.9" height="20"/>
<rect class="hcell c16" x="590.8" y="52.0" width="26.9" height="20"/>
<rect class="hcell c17" x="617.7" y="52.0" width="26.9" height="20"/>
<rect class="hcell c18" x="644.6" y="52.0" width="26.9" height="20"/>
<rect class="hcell c19" x="671.5" y="52.0" width="26.9" height="20"/>
<rect class="hcell c20" x="698.5" y="52.0" width="26.9" height="20"/>
<rect class="hcell c21" x="725.4" y="52.0" width="26.9" height="20"/>
<rect class="hcell c22" x="752.3" y="52.0" width="26.9" height="20"/>
<rect class="hcell c23" x="779.2" y="52.0" width="26.9" height="20"/>
<rect class="hcell c24" x="806.2" y="52.0" width="26.9" height="20"/>
<rect class="hcell c25" x="833.1" y="52.0" width="26.9" height="20"/>
<style>.osc-gantt:has(.c0:hover) .h0,.osc-gantt:has(.c1:hover) .h1,.osc-gantt:has(.c2:hover) .h2,.osc-gantt:has(.c3:hover) .h3,.osc-gantt:has(.c4:hover) .h4,.osc-gantt:has(.c5:hover) .h5,.osc-gantt:has(.c6:hover) .h6,.osc-gantt:has(.c7:hover) .h7,.osc-gantt:has(.c8:hover) .h8,.osc-gantt:has(.c9:hover) .h9,.osc-gantt:has(.c10:hover) .h10,.osc-gantt:has(.c11:hover) .h11,.osc-gantt:has(.c12:hover) .h12,.osc-gantt:has(.c13:hover) .h13,.osc-gantt:has(.c14:hover) .h14,.osc-gantt:has(.c15:hover) .h15,.osc-gantt:has(.c16:hover) .h16,.osc-gantt:has(.c17:hover) .h17,.osc-gantt:has(.c18:hover) .h18,.osc-gantt:has(.c19:hover) .h19,.osc-gantt:has(.c20:hover) .h20,.osc-gantt:has(.c21:hover) .h21,.osc-gantt:has(.c22:hover) .h22,.osc-gantt:has(.c23:hover) .h23,.osc-gantt:has(.c24:hover) .h24,.osc-gantt:has(.c25:hover) .h25{opacity:1}.osc-gantt:has(.c0:hover) .dl0,.osc-gantt:has(.c1:hover) .dl1,.osc-gantt:has(.c2:hover) .dl2,.osc-gantt:has(.c3:hover) .dl3,.osc-gantt:has(.c4:hover) .dl4,.osc-gantt:has(.c5:hover) .dl5,.osc-gantt:has(.c6:hover) .dl6,.osc-gantt:has(.c7:hover) .dl7,.osc-gantt:has(.c8:hover) .dl8,.osc-gantt:has(.c9:hover) .dl9,.osc-gantt:has(.c10:hover) .dl10,.osc-gantt:has(.c11:hover) .dl11,.osc-gantt:has(.c12:hover) .dl12,.osc-gantt:has(.c13:hover) .dl13,.osc-gantt:has(.c14:hover) .dl14,.osc-gantt:has(.c15:hover) .dl15,.osc-gantt:has(.c16:hover) .dl16,.osc-gantt:has(.c17:hover) .dl17,.osc-gantt:has(.c18:hover) .dl18,.osc-gantt:has(.c19:hover) .dl19,.osc-gantt:has(.c20:hover) .dl20,.osc-gantt:has(.c21:hover) .dl21,.osc-gantt:has(.c22:hover) .dl22,.osc-gantt:has(.c23:hover) .dl23,.osc-gantt:has(.c24:hover) .dl24,.osc-gantt:has(.c25:hover) .dl25{fill:var(--fg);font-weight:600}</style>
<text class="grp" x="12" y="104">Spec</text>
<line class="grpline" x1="12" x2="1028" y1="112" y2="112"/>
<rect class="hcell c0" x="160.0" y="112.0" width="26.9" height="48"/>
<rect class="hcell c1" x="186.9" y="112.0" width="26.9" height="48"/>
<rect class="hcell c2" x="213.8" y="112.0" width="26.9" height="48"/>
<rect class="hcell c3" x="240.8" y="112.0" width="26.9" height="48"/>
<rect class="hcell c4" x="267.7" y="112.0" width="26.9" height="48"/>
<rect class="hcell c5" x="294.6" y="112.0" width="26.9" height="48"/>
<rect class="hcell c6" x="321.5" y="112.0" width="26.9" height="48"/>
<rect class="hcell c7" x="348.5" y="112.0" width="26.9" height="48"/>
<rect class="hcell c8" x="375.4" y="112.0" width="26.9" height="48"/>
<rect class="hcell c9" x="402.3" y="112.0" width="26.9" height="48"/>
<rect class="hcell c10" x="429.2" y="112.0" width="26.9" height="48"/>
<rect class="hcell c11" x="456.2" y="112.0" width="26.9" height="48"/>
<rect class="hcell c12" x="483.1" y="112.0" width="26.9" height="48"/>
<rect class="hcell c13" x="510.0" y="112.0" width="26.9" height="48"/>
<rect class="hcell c14" x="536.9" y="112.0" width="26.9" height="48"/>
<rect class="hcell c15" x="563.8" y="112.0" width="26.9" height="48"/>
<rect class="hcell c16" x="590.8" y="112.0" width="26.9" height="48"/>
<rect class="hcell c17" x="617.7" y="112.0" width="26.9" height="48"/>
<rect class="hcell c18" x="644.6" y="112.0" width="26.9" height="48"/>
<rect class="hcell c19" x="671.5" y="112.0" width="26.9" height="48"/>
<rect class="hcell c20" x="698.5" y="112.0" width="26.9" height="48"/>
<rect class="hcell c21" x="725.4" y="112.0" width="26.9" height="48"/>
<rect class="hcell c22" x="752.3" y="112.0" width="26.9" height="48"/>
<rect class="hcell c23" x="779.2" y="112.0" width="26.9" height="48"/>
<rect class="hcell c24" x="806.2" y="112.0" width="26.9" height="48"/>
<rect class="hcell c25" x="833.1" y="112.0" width="26.9" height="48"/>
<text class="name" x="150" y="141.0" text-anchor="end">Program Status Protocol</text>
<rect class="bar-spec" x="173.5" y="133.0" width="323.1" height="8" rx="4"/>
<a href="https://www.superlogical.com/rex/docs/build/program-status" target="_blank" rel="noopener"><title>Sep 28: Revision 0.1, initial draft</title><path class="ms-spec" d="M173.5,130.0 L180.5,137.0 L173.5,144.0 L166.5,137.0 Z"/><rect class="hit" x="161.5" y="125.0" width="24" height="24"/></a>
<text class="mslbl" x="175.5" y="125.0">0.1 draft</text>
<a href="https://mitchellh.com/writing/program-status-osc7501" target="_blank" rel="noopener"><title>Oct 6: Revision 0.2; Mitchell Hashimoto&#x27;s announcement post</title><path class="ms-spec" d="M388.8,130.0 L395.8,137.0 L388.8,144.0 L381.8,137.0 Z"/><rect class="hit" x="376.8" y="125.0" width="24" height="24"/></a>
<text class="mslbl" x="390.8" y="125.0">0.2 announced</text>
<a href="https://www.superlogical.com/rex/docs/build/program-status" target="_blank" rel="noopener"><title>Oct 7: Revision 0.3: absent progress means indeterminate; programs may send without querying</title><path class="ms-spec" d="M415.8,130.0 L422.8,137.0 L415.8,144.0 L408.8,137.0 Z"/><rect class="hit" x="403.8" y="125.0" width="24" height="24"/></a>
<text class="mslbl" x="417.8" y="157.0">0.3</text>
<a href="https://www.superlogical.com/rex/docs/build/program-status" target="_blank" rel="noopener"><title>Oct 10: Revision 0.4: the query reply may list states and kinds</title><path class="ms-spec" d="M496.5,130.0 L503.5,137.0 L496.5,144.0 L489.5,137.0 Z"/><rect class="hit" x="484.5" y="125.0" width="24" height="24"/></a>
<text class="mslbl" x="498.5" y="125.0">0.4</text>
<a href="https://www.superlogical.com/rex/docs/build/program-status" target="_blank" rel="noopener"><text class="status st-link" x="880" y="141.0">Revision 0.4</text></a>
<text class="grp" x="12" y="182">Terminals</text>
<line class="grpline" x1="12" x2="1028" y1="190" y2="190"/>
<a href="https://www.superlogical.com/rex/docs/build/program-status" target="_blank" rel="noopener"><title>Rex: Shipped with the spec Oct 6</title>
<rect class="rowhit" x="0" y="200.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="200.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="200.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="200.0" width="180" height="30"/>
<text class="name" x="150" y="219.0" text-anchor="end">Rex</text>
<line class="live" x1="388.8" x2="833.1" y1="215.0" y2="215.0"/>
<path class="ms-ship" d="M388.8,208.0 L395.8,215.0 L388.8,222.0 L381.8,215.0 Z"/>
<text class="status st-link st-shipped" x="880" y="219.0">Shipped with the spec</text>
</a>
<a href="https://github.com/ghostty-org/ghostty/pull/14560" target="_blank" rel="noopener"><title>libghostty: Merged Oct 6; Updated to revision 0.4 Oct 10</title>
<rect class="rowhit" x="0" y="230.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="230.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="230.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="230.0" width="180" height="30"/>
<text class="name" x="150" y="249.0" text-anchor="end">libghostty</text>
<rect class="bar-merged" x="388.8" y="239.0" width="444.2" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="249.0">Merged, for Ghostty 1.4.0</text>
</a>
<a href="https://github.com/microsoft/intelligent-terminal/issues/1096" target="_blank" rel="noopener"><title>Windows Terminal: Requested Oct 7; Moved to Intelligent Terminal Oct 8</title>
<rect class="rowhit" x="0" y="260.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="260.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="260.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="260.0" width="180" height="30"/>
<text class="name" x="150" y="279.0" text-anchor="end">Windows Terminal</text>
<rect class="bar-open" x="415.8" y="269.0" width="417.3" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="279.0">Sent to Intelligent Terminal</text>
</a>
<a href="https://github.com/superset-sh/superset/issues/8278" target="_blank" rel="noopener"><title>Superset: Requested Oct 7</title>
<rect class="rowhit" x="0" y="290.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="290.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="290.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="290.0" width="180" height="30"/>
<text class="name" x="150" y="309.0" text-anchor="end">Superset</text>
<rect class="bar-open" x="415.8" y="299.0" width="417.3" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="309.0">Requested</text>
</a>
<a href="https://github.com/manaflow-ai/cmux/releases/tag/v0.65.1" target="_blank" rel="noopener"><title>cmux: Merged Oct 9; Shipped in v0.65.1 Oct 12</title>
<rect class="rowhit" x="0" y="320.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="320.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="320.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="320.0" width="180" height="30"/>
<text class="name" x="150" y="339.0" text-anchor="end">cmux</text>
<rect class="bar-work" x="469.6" y="329.0" width="80.8" height="12" rx="3"/>
<line class="live" x1="550.4" x2="833.1" y1="335.0" y2="335.0"/>
<path class="ms-ship" d="M550.4,328.0 L557.4,335.0 L550.4,342.0 L543.4,335.0 Z"/>
<text class="status st-link st-shipped" x="880" y="339.0">Shipped v0.65.1</text>
</a>
<a href="https://iterm2.com/downloads.html" target="_blank" rel="noopener"><title>iTerm2: Merged Oct 9; Shipped in 3.7.5 Oct 12; 3.7.6 coalesces floods</title>
<rect class="rowhit" x="0" y="350.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="350.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="350.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="350.0" width="180" height="30"/>
<text class="name" x="150" y="369.0" text-anchor="end">iTerm2</text>
<rect class="bar-work" x="469.6" y="359.0" width="80.8" height="12" rx="3"/>
<line class="live" x1="550.4" x2="833.1" y1="365.0" y2="365.0"/>
<path class="ms-ship" d="M550.4,358.0 L557.4,365.0 L550.4,372.0 L543.4,365.0 Z"/>
<text class="status st-link st-shipped" x="880" y="369.0">Shipped 3.7.5</text>
</a>
<a href="https://github.com/herdrdev/herdr/pull/5172" target="_blank" rel="noopener"><title>Herdr: Draft pull request opened Oct 11</title>
<rect class="rowhit" x="0" y="380.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="380.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="380.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="380.0" width="180" height="30"/>
<text class="name" x="150" y="399.0" text-anchor="end">Herdr</text>
<rect class="bar-open" x="523.5" y="389.0" width="309.6" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="399.0">Draft pull request</text>
</a>
<a href="https://github.com/kovidgoyal/kitty/pull/10657" target="_blank" rel="noopener"><title>kitty: Merged, for 0.50.0 Oct 13</title>
<rect class="rowhit" x="0" y="410.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="410.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="410.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="410.0" width="180" height="30"/>
<text class="name" x="150" y="429.0" text-anchor="end">kitty</text>
<rect class="bar-merged" x="577.3" y="419.0" width="255.8" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="429.0">Merged, for 0.50.0</text>
</a>
<a href="https://github.com/tmux/tmux/issues/5713" target="_blank" rel="noopener"><title>tmux: Declined for now Oct 13; premature, waiting to see wider adoption</title>
<rect class="rowhit" x="0" y="440.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="440.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="440.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="440.0" width="180" height="30"/>
<text class="name" x="150" y="459.0" text-anchor="end">tmux</text>
<path class="decl" d="M572.3,450.0 L582.3,460.0 M572.3,460.0 L582.3,450.0"/>
<text class="status st-link st-declined" x="880" y="459.0">Declined for now</text>
</a>
<a href="https://github.com/warpdotdev/warp/pull/16460" target="_blank" rel="noopener"><title>Warp: Pull request opened Oct 14</title>
<rect class="rowhit" x="0" y="470.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="470.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="470.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="470.0" width="180" height="30"/>
<text class="name" x="150" y="489.0" text-anchor="end">Warp</text>
<rect class="bar-open" x="604.2" y="479.0" width="228.8" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="489.0">Pull request open</text>
</a>
<a href="https://github.com/getpaseo/paseo/pull/6962" target="_blank" rel="noopener"><title>Paseo: Pull request opened Oct 15</title>
<rect class="rowhit" x="0" y="500.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="500.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="500.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="500.0" width="180" height="30"/>
<text class="name" x="150" y="519.0" text-anchor="end">Paseo</text>
<rect class="bar-open" x="631.2" y="509.0" width="201.9" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="519.0">Pull request open</text>
</a>
<a href="https://github.com/stablyai/orca/releases/tag/v1.4.232" target="_blank" rel="noopener"><title>Orca: Merged Oct 19; Shipped in v1.4.232 Oct 20</title>
<rect class="rowhit" x="0" y="530.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="530.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="530.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="530.0" width="180" height="30"/>
<text class="name" x="150" y="549.0" text-anchor="end">Orca</text>
<rect class="bar-work" x="738.8" y="539.0" width="26.9" height="12" rx="3"/>
<line class="live" x1="765.8" x2="833.1" y1="545.0" y2="545.0"/>
<path class="ms-ship" d="M765.8,538.0 L772.8,545.0 L765.8,552.0 L758.8,545.0 Z"/>
<text class="status st-link st-shipped" x="880" y="549.0">Shipped v1.4.232</text>
</a>
<a href="https://github.com/zellij-org/zellij/pull/5734" target="_blank" rel="noopener"><title>Zellij: Merged Oct 20</title>
<rect class="rowhit" x="0" y="560.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="560.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="560.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="560.0" width="180" height="30"/>
<text class="name" x="150" y="579.0" text-anchor="end">Zellij</text>
<rect class="bar-merged" x="765.8" y="569.0" width="67.3" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="579.0">Merged, unreleased</text>
</a>
<a href="https://github.com/umputun/agterm/blob/master/docs/backlog/program-status-waits-on-an-upstream-app-action.md" target="_blank" rel="noopener"><title>agterm: Backlogged, waits on libghostty Oct 21</title>
<rect class="rowhit" x="0" y="590.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="590.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="590.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="590.0" width="180" height="30"/>
<text class="name" x="150" y="609.0" text-anchor="end">agterm</text>
<rect class="bar-open" x="792.7" y="599.0" width="40.4" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="609.0">Waits on libghostty</text>
</a>
<text class="grp" x="12" y="642">Coding agents</text>
<line class="grpline" x1="12" x2="1028" y1="650" y2="650"/>
<a href="https://github.com/earendil-works/pi/releases/tag/v1.1.0" target="_blank" rel="noopener"><title>pi: Shipped in v1.1.0 Oct 7</title>
<rect class="rowhit" x="0" y="660.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="660.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="660.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="660.0" width="180" height="30"/>
<text class="name" x="150" y="679.0" text-anchor="end">pi</text>
<line class="live" x1="415.8" x2="833.1" y1="675.0" y2="675.0"/>
<path class="ms-ship" d="M415.8,668.0 L422.8,675.0 L415.8,682.0 L408.8,675.0 Z"/>
<text class="status st-link st-shipped" x="880" y="679.0">Shipped v1.1.0</text>
</a>
<a href="https://github.com/anthropics/claude-code/releases/tag/v2.1.295" target="_blank" rel="noopener"><title>Claude Code: Shipped in 2.1.295 Oct 8</title>
<rect class="rowhit" x="0" y="690.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="690.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="690.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="690.0" width="180" height="30"/>
<text class="name" x="150" y="709.0" text-anchor="end">Claude Code</text>
<line class="live" x1="442.7" x2="833.1" y1="705.0" y2="705.0"/>
<path class="ms-ship" d="M442.7,698.0 L449.7,705.0 L442.7,712.0 L435.7,705.0 Z"/>
<text class="status st-link st-shipped" x="880" y="709.0">Shipped 2.1.295</text>
</a>
<a href="https://github.com/charmbracelet/crush/releases/tag/v0.98.0" target="_blank" rel="noopener"><title>Crush: Shipped in v0.98.0 Oct 8</title>
<rect class="rowhit" x="0" y="720.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="720.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="720.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="720.0" width="180" height="30"/>
<text class="name" x="150" y="739.0" text-anchor="end">Crush</text>
<line class="live" x1="442.7" x2="833.1" y1="735.0" y2="735.0"/>
<path class="ms-ship" d="M442.7,728.0 L449.7,735.0 L442.7,742.0 L435.7,735.0 Z"/>
<text class="status st-link st-shipped" x="880" y="739.0">Shipped v0.98.0</text>
</a>
<a href="https://github.com/openai/codex/pull/52725" target="_blank" rel="noopener"><title>Codex CLI: Merged Oct 9; Shipped in rust-v0.163.0 Oct 15</title>
<rect class="rowhit" x="0" y="750.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="750.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="750.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="750.0" width="180" height="30"/>
<text class="name" x="150" y="769.0" text-anchor="end">Codex CLI</text>
<rect class="bar-work" x="469.6" y="759.0" width="161.5" height="12" rx="3"/>
<line class="live" x1="631.2" x2="833.1" y1="765.0" y2="765.0"/>
<path class="ms-ship" d="M631.2,758.0 L638.2,765.0 L631.2,772.0 L624.2,765.0 Z"/>
<text class="status st-link st-shipped" x="880" y="769.0">Shipped rust-v0.163.0</text>
</a>
<a href="https://github.com/can1357/oh-my-pi/releases/tag/v18.8.7" target="_blank" rel="noopener"><title>oh-my-pi: Shipped in v18.8.7 Oct 9</title>
<rect class="rowhit" x="0" y="780.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="780.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="780.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="780.0" width="180" height="30"/>
<text class="name" x="150" y="799.0" text-anchor="end">oh-my-pi</text>
<line class="live" x1="469.6" x2="833.1" y1="795.0" y2="795.0"/>
<path class="ms-ship" d="M469.6,788.0 L476.6,795.0 L469.6,802.0 L462.6,795.0 Z"/>
<text class="status st-link st-shipped" x="880" y="799.0">Shipped v18.8.7</text>
</a>
<a href="https://github.com/google-gemini/gemini-cli/issues/29710" target="_blank" rel="noopener"><title>Gemini CLI: Requested Oct 10</title>
<rect class="rowhit" x="0" y="810.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="810.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="810.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="810.0" width="180" height="30"/>
<text class="name" x="150" y="829.0" text-anchor="end">Gemini CLI</text>
<rect class="bar-open" x="496.5" y="819.0" width="336.5" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="829.0">Requested</text>
</a>
<a href="https://github.com/QwenLM/qwen-code/pull/13994" target="_blank" rel="noopener"><title>Qwen Code: Requested Oct 10; Pull request opened Oct 12</title>
<rect class="rowhit" x="0" y="840.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="840.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="840.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="840.0" width="180" height="30"/>
<text class="name" x="150" y="859.0" text-anchor="end">Qwen Code</text>
<rect class="bar-open" x="496.5" y="849.0" width="336.5" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="859.0">Pull request open</text>
</a>
<a href="https://github.com/XiaomiMiMo/MiMo-Code/issues/2631" target="_blank" rel="noopener"><title>MiMo Code: Requested Oct 10</title>
<rect class="rowhit" x="0" y="870.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="870.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="870.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="870.0" width="180" height="30"/>
<text class="name" x="150" y="889.0" text-anchor="end">MiMo Code</text>
<rect class="bar-open" x="496.5" y="879.0" width="336.5" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="889.0">Requested</text>
</a>
<a href="https://github.com/github/copilot-cli/issues/5112" target="_blank" rel="noopener"><title>GitHub Copilot CLI: Requested Oct 10</title>
<rect class="rowhit" x="0" y="900.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="900.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="900.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="900.0" width="180" height="30"/>
<text class="name" x="150" y="919.0" text-anchor="end">GitHub Copilot CLI</text>
<rect class="bar-open" x="496.5" y="909.0" width="336.5" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="919.0">Requested</text>
</a>
<a href="https://github.com/Kilo-Org/kilocode/issues/14973" target="_blank" rel="noopener"><title>Kilo Code: Requested Oct 11</title>
<rect class="rowhit" x="0" y="930.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="930.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="930.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="930.0" width="180" height="30"/>
<text class="name" x="150" y="949.0" text-anchor="end">Kilo Code</text>
<rect class="bar-open" x="523.5" y="939.0" width="309.6" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="949.0">Requested</text>
</a>
<a href="https://github.com/anomalyco/opencode/pull/54560" target="_blank" rel="noopener"><title>opencode: Pull request opened Oct 11</title>
<rect class="rowhit" x="0" y="960.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="960.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="960.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="960.0" width="180" height="30"/>
<text class="name" x="150" y="979.0" text-anchor="end">opencode</text>
<rect class="bar-open" x="523.5" y="969.0" width="309.6" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="979.0">Pull request open</text>
</a>
<a href="https://github.com/mastra-ai/mastra/issues/26910" target="_blank" rel="noopener"><title>Mastra Code: Requested Oct 13</title>
<rect class="rowhit" x="0" y="990.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="990.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="990.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="990.0" width="180" height="30"/>
<text class="name" x="150" y="1009.0" text-anchor="end">Mastra Code</text>
<rect class="bar-open" x="577.3" y="999.0" width="255.8" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1009.0">Requested</text>
</a>
<a href="https://github.com/NousResearch/hermes-agent/pull/140837" target="_blank" rel="noopener"><title>Hermes Agent: Requested, pull request opened Oct 14; Second pull request opened Oct 18</title>
<rect class="rowhit" x="0" y="1020.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1020.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1020.0" width="180" height="30"/>
<text class="name" x="150" y="1039.0" text-anchor="end">Hermes Agent</text>
<rect class="bar-open" x="604.2" y="1029.0" width="228.8" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1039.0">Pull request open</text>
</a>
<a href="https://github.com/aaif-goose/goose/pull/12928" target="_blank" rel="noopener"><title>goose: Merged Oct 16</title>
<rect class="rowhit" x="0" y="1050.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1050.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1050.0" width="180" height="30"/>
<text class="name" x="150" y="1069.0" text-anchor="end">goose</text>
<rect class="bar-merged" x="658.1" y="1059.0" width="175.0" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="1069.0">Merged, unreleased</text>
</a>
<a href="https://github.com/openclaw/openclaw/pull/175692" target="_blank" rel="noopener"><title>OpenClaw: Merged Oct 18</title>
<rect class="rowhit" x="0" y="1080.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1080.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1080.0" width="180" height="30"/>
<text class="name" x="150" y="1099.0" text-anchor="end">OpenClaw</text>
<rect class="bar-merged" x="711.9" y="1089.0" width="121.2" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="1099.0">Merged, unreleased</text>
</a>
<text class="grp" x="12" y="1132">Libraries and developer tools</text>
<line class="grpline" x1="12" x2="1028" y1="1140" y2="1140"/>
<a href="https://github.com/rust-lang/cargo/issues/17559" target="_blank" rel="noopener"><title>Cargo: Requested Oct 7</title>
<rect class="rowhit" x="0" y="1150.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1150.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1150.0" width="180" height="30"/>
<text class="name" x="150" y="1169.0" text-anchor="end">Cargo</text>
<rect class="bar-open" x="415.8" y="1159.0" width="417.3" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1169.0">Requested</text>
</a>
<a href="https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.0" target="_blank" rel="noopener"><title>Bubble Tea: Shipped in v2.1.0 Oct 8</title>
<rect class="rowhit" x="0" y="1180.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1180.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1180.0" width="180" height="30"/>
<text class="name" x="150" y="1199.0" text-anchor="end">Bubble Tea</text>
<line class="live" x1="442.7" x2="833.1" y1="1195.0" y2="1195.0"/>
<path class="ms-ship" d="M442.7,1188.0 L449.7,1195.0 L442.7,1202.0 L435.7,1195.0 Z"/>
<text class="status st-link st-shipped" x="880" y="1199.0">Shipped v2.1.0</text>
</a>
<a href="https://github.com/neovim/neovim/issues/42276" target="_blank" rel="noopener"><title>Neovim: Requested Oct 8</title>
<rect class="rowhit" x="0" y="1210.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1210.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1210.0" width="180" height="30"/>
<text class="name" x="150" y="1229.0" text-anchor="end">Neovim</text>
<rect class="bar-open" x="442.7" y="1219.0" width="390.4" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1229.0">Requested</text>
</a>
<a href="https://github.com/ratatui/ratatui/issues/2811" target="_blank" rel="noopener"><title>ratatui: Requested Oct 8</title>
<rect class="rowhit" x="0" y="1240.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1240.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1240.0" width="180" height="30"/>
<text class="name" x="150" y="1259.0" text-anchor="end">ratatui</text>
<rect class="bar-open" x="442.7" y="1249.0" width="390.4" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1259.0">Requested</text>
</a>
<a href="https://github.com/tqdm/tqdm/pull/1884" target="_blank" rel="noopener"><title>tqdm: Requested Oct 8; Pull request opened Oct 16</title>
<rect class="rowhit" x="0" y="1270.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1270.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1270.0" width="180" height="30"/>
<text class="name" x="150" y="1289.0" text-anchor="end">tqdm</text>
<rect class="bar-open" x="442.7" y="1279.0" width="390.4" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1289.0">Pull request open</text>
</a>
<a href="https://github.com/expo/expo/pull/51289" target="_blank" rel="noopener"><title>Expo CLI: Experimental pull request opened Oct 9</title>
<rect class="rowhit" x="0" y="1300.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1300.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1300.0" width="180" height="30"/>
<text class="name" x="150" y="1319.0" text-anchor="end">Expo CLI</text>
<rect class="bar-open" x="469.6" y="1309.0" width="363.5" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1319.0">Experimental pull request</text>
</a>
<a href="https://github.com/anomalyco/opentui/releases/tag/v0.6.3" target="_blank" rel="noopener"><title>OpenTUI: Shipped in v0.6.3 Oct 13</title>
<rect class="rowhit" x="0" y="1330.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1330.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1330.0" width="180" height="30"/>
<text class="name" x="150" y="1349.0" text-anchor="end">OpenTUI</text>
<line class="live" x1="577.3" x2="833.1" y1="1345.0" y2="1345.0"/>
<path class="ms-ship" d="M577.3,1338.0 L584.3,1345.0 L577.3,1352.0 L570.3,1345.0 Z"/>
<text class="status st-link st-shipped" x="880" y="1349.0">Shipped v0.6.3</text>
</a>
<a href="https://github.com/gradle/gradle/pull/39468" target="_blank" rel="noopener"><title>Gradle: Pull request opened Oct 14</title>
<rect class="rowhit" x="0" y="1360.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1360.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1360.0" width="180" height="30"/>
<text class="name" x="150" y="1379.0" text-anchor="end">Gradle</text>
<rect class="bar-open" x="604.2" y="1369.0" width="228.8" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1379.0">Pull request open</text>
</a>
<a href="https://github.com/docker/compose/issues/14365" target="_blank" rel="noopener"><title>Docker Compose: Requested Oct 20</title>
<rect class="rowhit" x="0" y="1390.0" width="160" height="30"/>
<rect class="rowhit c0" x="160.0" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c1" x="186.9" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c2" x="213.8" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c3" x="240.8" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c4" x="267.7" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c5" x="294.6" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c6" x="321.5" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c7" x="348.5" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c8" x="375.4" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c9" x="402.3" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c10" x="429.2" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c11" x="456.2" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c12" x="483.1" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c13" x="510.0" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c14" x="536.9" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c15" x="563.8" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c16" x="590.8" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c17" x="617.7" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c18" x="644.6" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c19" x="671.5" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c20" x="698.5" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c21" x="725.4" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c22" x="752.3" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c23" x="779.2" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c24" x="806.2" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit c25" x="833.1" y="1390.0" width="26.9" height="30"/>
<rect class="rowhit" x="860" y="1390.0" width="180" height="30"/>
<text class="name" x="150" y="1409.0" text-anchor="end">Docker Compose</text>
<rect class="bar-open" x="765.8" y="1399.0" width="67.3" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="1409.0">Requested</text>
</a>
</svg>
</div>
<div class="osc-key">
<span><svg viewBox="0 0 22 12"><rect x="1" y="2" width="12" height="8" rx="2" fill="#3987e5" opacity="0.35"/><path d="M15,1 L20,6 L15,11 L10,6 Z" fill="#3987e5"/></svg>Work merged, then released</span>
<span><svg viewBox="0 0 22 12"><line x1="2" y1="6" x2="20" y2="6" stroke="#3987e5" stroke-width="2" opacity="0.55"/></svg>Available since release</span>
<span><svg viewBox="0 0 22 12"><rect x="1" y="2" width="20" height="8" rx="2" fill="rgba(57,135,229,0.12)" stroke="#3987e5" stroke-width="1.5"/></svg>Merged, waiting on a release</span>
<span><svg viewBox="0 0 22 12"><rect x="1" y="2" width="20" height="8" rx="2" fill="rgba(126,130,144,0.12)" stroke="#7e8290" stroke-width="1.5"/></svg>Under review or requested</span>
<span><svg viewBox="0 0 22 12"><path d="M7,2 L15,10 M7,10 L15,2" stroke="#7e8290" stroke-width="2" stroke-linecap="round"/></svg>Declined</span>
</div>
<details class="osc-refs">
<summary>Sources for each date</summary>

| Date | Program | Event | Source |
|:---|:---|:---|:---|
| Sep 28 | Spec | Revision 0.1, initial draft | [spec](https://www.superlogical.com/rex/docs/build/program-status) |
| Oct 6 | Spec | Revision 0.2, announced | [post](https://mitchellh.com/writing/program-status-osc7501) |
| Oct 6 | Rex | Shipped with the spec | [spec](https://www.superlogical.com/rex/docs/build/program-status) |
| Oct 6 | libghostty | Merged | [#14560](https://github.com/ghostty-org/ghostty/pull/14560) |
| Oct 7 | Spec | Revision 0.3 | [spec](https://www.superlogical.com/rex/docs/build/program-status) |
| Oct 7 | Windows Terminal | Requested | [#1096](https://github.com/microsoft/intelligent-terminal/issues/1096) |
| Oct 7 | Superset | Requested | [#8278](https://github.com/superset-sh/superset/issues/8278) |
| Oct 7 | pi | Shipped in v1.1.0 | [release](https://github.com/earendil-works/pi/releases/tag/v1.1.0) |
| Oct 7 | Cargo | Requested | [#17559](https://github.com/rust-lang/cargo/issues/17559) |
| Oct 8 | Windows Terminal | Moved to Intelligent Terminal | [#1096](https://github.com/microsoft/intelligent-terminal/issues/1096) |
| Oct 8 | Claude Code | Shipped in 2.1.295 | [release](https://github.com/anthropics/claude-code/releases/tag/v2.1.295) |
| Oct 8 | Crush | Shipped in v0.98.0 | [release](https://github.com/charmbracelet/crush/releases/tag/v0.98.0) |
| Oct 8 | Bubble Tea | Shipped in v2.1.0 | [release](https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.0) |
| Oct 8 | Neovim | Requested | [#42276](https://github.com/neovim/neovim/issues/42276) |
| Oct 8 | ratatui | Requested | [#2811](https://github.com/ratatui/ratatui/issues/2811) |
| Oct 8 | tqdm | Requested | [#1873](https://github.com/tqdm/tqdm/issues/1873) |
| Oct 9 | cmux | Merged | [#18742](https://github.com/manaflow-ai/cmux/pull/18742) |
| Oct 9 | iTerm2 | Merged | [`49936d3a5`](https://github.com/gnachman/iTerm2/commit/49936d3a5) |
| Oct 9 | Codex CLI | Merged | [#52725](https://github.com/openai/codex/pull/52725) |
| Oct 9 | oh-my-pi | Shipped in v18.8.7 | [release](https://github.com/can1357/oh-my-pi/releases/tag/v18.8.7) |
| Oct 9 | Expo CLI | Experimental pull request opened | [#51289](https://github.com/expo/expo/pull/51289) |
| Oct 10 | Spec | Revision 0.4 | [spec](https://www.superlogical.com/rex/docs/build/program-status) |
| Oct 10 | libghostty | Updated to revision 0.4 | [#14630](https://github.com/ghostty-org/ghostty/pull/14630) |
| Oct 10 | Gemini CLI | Requested | [#29710](https://github.com/google-gemini/gemini-cli/issues/29710) |
| Oct 10 | Qwen Code | Requested | [#13870](https://github.com/QwenLM/qwen-code/issues/13870) |
| Oct 10 | MiMo Code | Requested | [#2631](https://github.com/XiaomiMiMo/MiMo-Code/issues/2631) |
| Oct 10 | GitHub Copilot CLI | Requested | [#5112](https://github.com/github/copilot-cli/issues/5112) |
| Oct 11 | Herdr | Draft pull request opened | [#5172](https://github.com/herdrdev/herdr/pull/5172) |
| Oct 11 | Kilo Code | Requested | [#14973](https://github.com/Kilo-Org/kilocode/issues/14973) |
| Oct 11 | opencode | Pull request opened | [#54560](https://github.com/anomalyco/opencode/pull/54560) |
| Oct 12 | cmux | Shipped in v0.65.1 | [release](https://github.com/manaflow-ai/cmux/releases/tag/v0.65.1) |
| Oct 12 | iTerm2 | Shipped in 3.7.5 | [downloads](https://iterm2.com/downloads.html) |
| Oct 12 | Qwen Code | Pull request opened | [#13994](https://github.com/QwenLM/qwen-code/pull/13994) |
| Oct 13 | kitty | Merged, for 0.50.0 | [#10657](https://github.com/kovidgoyal/kitty/pull/10657) |
| Oct 13 | tmux | Declined for now | [#5713](https://github.com/tmux/tmux/issues/5713) |
| Oct 13 | Mastra Code | Requested | [#26910](https://github.com/mastra-ai/mastra/issues/26910) |
| Oct 13 | OpenTUI | Shipped in v0.6.3 | [release](https://github.com/anomalyco/opentui/releases/tag/v0.6.3) |
| Oct 14 | Warp | Pull request opened | [#16460](https://github.com/warpdotdev/warp/pull/16460) |
| Oct 14 | Hermes Agent | Requested, pull request opened | [#138152](https://github.com/NousResearch/hermes-agent/pull/138152) |
| Oct 14 | Gradle | Pull request opened | [#39468](https://github.com/gradle/gradle/pull/39468) |
| Oct 15 | Paseo | Pull request opened | [#6962](https://github.com/getpaseo/paseo/pull/6962) |
| Oct 15 | Codex CLI | Shipped in rust-v0.163.0 | [#52725](https://github.com/openai/codex/pull/52725) |
| Oct 16 | goose | Merged | [#12928](https://github.com/aaif-goose/goose/pull/12928) |
| Oct 16 | tqdm | Pull request opened | [#1884](https://github.com/tqdm/tqdm/pull/1884) |
| Oct 18 | Hermes Agent | Second pull request opened | [#140837](https://github.com/NousResearch/hermes-agent/pull/140837) |
| Oct 18 | OpenClaw | Merged | [#175692](https://github.com/openclaw/openclaw/pull/175692) |
| Oct 19 | Orca | Merged | [#30262](https://github.com/stablyai/orca/pull/30262) |
| Oct 20 | Orca | Shipped in v1.4.232 | [release](https://github.com/stablyai/orca/releases/tag/v1.4.232) |
| Oct 20 | Zellij | Merged | [#5734](https://github.com/zellij-org/zellij/pull/5734) |
| Oct 20 | Docker Compose | Requested | [#14365](https://github.com/docker/compose/issues/14365) |
| Oct 21 | agterm | Backlogged, waits on libghostty | [backlog](https://github.com/umputun/agterm/blob/master/docs/backlog/program-status-waits-on-an-upstream-app-action.md) |

</details>
</div>

Checked against each project's own releases, pull requests, and changelogs on **2026-10-22**. Support is moving week to week; the community [support matrix](https://github.com/hyeebeen/awesome-osc7501/blob/main/docs/support-matrix.md) tracks more programs, less strictly.

### Terminals, multiplexers, and agent workspaces

| Program | Status | Source | How it shows status |
|:---|:---|:---|:---|
| Rex | Shipped with the spec | [spec](https://www.superlogical.com/rex/docs/build/program-status) | The session picker and unfocused tab headers; a Lua event for scripts |
| cmux | Shipped v0.65.1 | [release](https://github.com/manaflow-ai/cmux/releases/tag/v0.65.1) | A sidebar row per pane with the app, title, message, and progress |
| iTerm2 | Shipped 3.7.5 | [downloads](https://iterm2.com/downloads.html) | A dot on the tab and the status color on the tab's subtitle line; also the Session Status tool, the Cockpit window, and the dock badge |
| Orca | Shipped v1.4.232 | [release](https://github.com/stablyai/orca/releases/tag/v1.4.232) | An agent IDE; reads the reports beside its agent hooks and shows them on session rows and tabs |
| libghostty | Merged, for Ghostty 1.4.0 | [#14560](https://github.com/ghostty-org/ghostty/pull/14560) | The library keeps the records; the Ghostty app doesn't show them yet |
| kitty | Merged, for 0.50.0 | [#10657](https://github.com/kovidgoyal/kitty/pull/10657) | `tab.program_status` in the tab title template; `kitten @ ls` |
| Zellij | Merged, unreleased | [#5734](https://github.com/zellij-org/zellij/pull/5734) | Marks on pane frames and tabs, an inbox in the session manager; forwards to the outer terminal by default |
| Windows Terminal | Sent to Intelligent Terminal | [#1096](https://github.com/microsoft/intelligent-terminal/issues/1096) | The team moved the request to Intelligent Terminal, Microsoft's agent-focused fork, to evaluate first; it awaits triage there. ConPTY passes the sequence through, so it reaches Windows Terminal, which doesn't draw it or answer the query. |
| Superset | Requested | [#8278](https://github.com/superset-sh/superset/issues/8278) | An agent workspace; the request is to store the records and expose them |
| Herdr | Draft pull request | [#5172](https://github.com/herdrdev/herdr/pull/5172) |  |
| Warp | Pull request open | [#16460](https://github.com/warpdotdev/warp/pull/16460) |  |
| Paseo | Pull request open | [#6962](https://github.com/getpaseo/paseo/pull/6962) | An agent workspace; would take each terminal's activity from the reports |
| agterm | Waits on libghostty | [backlog](https://github.com/umputun/agterm/blob/master/docs/backlog/program-status-waits-on-an-upstream-app-action.md) | A macOS terminal on libghostty, whose embedding layer drops the reports and leaves the query unanswered, so Claude Code sends none. Its own hook adapters set a status glyph per session. |
| tmux | Declined for now | [#5713](https://github.com/tmux/tmux/issues/5713) | Drops the sequence, so reports from inside tmux never reach the outer terminal |
| WezTerm, Alacritty, VS Code | No support found |  |  |

### Coding agents

| Program | Status | Source | Notes |
|:---|:---|:---|:---|
| pi | Shipped v1.1.0 | [release](https://github.com/earendil-works/pi/releases/tag/v1.1.0) | `PI_PROGRAM_STATUS=0` turns it off |
| Claude Code | Shipped 2.1.295 | [release](https://github.com/anthropics/claude-code/releases/tag/v2.1.295) | Sends only after the terminal answers the query. `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` turns it off, along with Claude's window title. |
| Crush | Shipped v0.98.0 | [release](https://github.com/charmbracelet/crush/releases/tag/v0.98.0) | Through Bubble Tea |
| Codex CLI | Shipped rust-v0.163.0 | [#52725](https://github.com/openai/codex/pull/52725) | `idle`, `working`, and `blocked`, whenever its output is a terminal |
| oh-my-pi | Shipped v18.8.7 | [release](https://github.com/can1357/oh-my-pi/releases/tag/v18.8.7) | Carries the pending question or the error in `msg`; `terminal.programStatus` turns it off |
| goose | Merged, unreleased | [#12928](https://github.com/aaif-goose/goose/pull/12928) |  |
| OpenClaw | Merged, unreleased | [#175692](https://github.com/openclaw/openclaw/pull/175692) |  |
| Gemini CLI | Requested | [#29710](https://github.com/google-gemini/gemini-cli/issues/29710) |  |
| Qwen Code | Pull request open | [#13994](https://github.com/QwenLM/qwen-code/pull/13994) |  |
| MiMo Code | Requested | [#2631](https://github.com/XiaomiMiMo/MiMo-Code/issues/2631) |  |
| GitHub Copilot CLI | Requested | [#5112](https://github.com/github/copilot-cli/issues/5112) |  |
| Kilo Code | Requested | [#14973](https://github.com/Kilo-Org/kilocode/issues/14973) |  |
| opencode | Pull request open | [#54560](https://github.com/anomalyco/opencode/pull/54560) |  |
| Mastra Code | Requested | [#26910](https://github.com/mastra-ai/mastra/issues/26910) |  |
| Hermes Agent | Pull request open | [#140837](https://github.com/NousResearch/hermes-agent/pull/140837) |  |

### Libraries and developer tools

| Program | Status | Source | Notes |
|:---|:---|:---|:---|
| Bubble Tea | Shipped v2.1.0 | [release](https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.0) | Any Bubble Tea program can report |
| OpenTUI | Shipped v0.6.3 | [release](https://github.com/anomalyco/opentui/releases/tag/v0.6.3) | Any OpenTUI program can report; the renderer sends the query at startup |
| Cargo | Requested | [#17559](https://github.com/rust-lang/cargo/issues/17559) | Labeled as needing more information |
| Neovim | Requested | [#42276](https://github.com/neovim/neovim/issues/42276) |  |
| ratatui | Requested | [#2811](https://github.com/ratatui/ratatui/issues/2811) | A helper for emitting reports |
| tqdm | Pull request open | [#1884](https://github.com/tqdm/tqdm/pull/1884) | Optional, from its progress bars |
| Expo CLI | Experimental pull request | [#51289](https://github.com/expo/expo/pull/51289) |  |
| Gradle | Pull request open | [#39468](https://github.com/gradle/gradle/pull/39468) |  |
| Docker Compose | Requested | [#14365](https://github.com/docker/compose/issues/14365) | For its progress output |
| Terraform, Homebrew | Proof of concept | [announcement](https://mitchellh.com/writing/program-status-osc7501) | No upstream change |

## Where it overlaps beacon

Read as a list of keys, the protocol looks like it covers much of what beacon paints: a state, a reason, a message, a title. In practice the two share one axis, for three reasons.

1. **The spec describes what a program can send.** Claude Code sends less of it. As of 2.1.306, `msg` carries the question or the command awaiting approval while `blocked`, a task headline while `working` only in fullscreen mode, and nothing on `done`. `title` is set only on sub-agent records.
2. **iTerm2 puts only `state` on the tab.** `msg` and `title` appear in the Session Status tool and the Cockpit window, not in the tab label.
3. **The spec doesn't model what most of beacon's surfaces carry.** It has no project, branch, task, phase, or deliverable; `app` names the program, not the work.

| Key | iTerm2 3.7.6 shows it |
|:---|:---|
| `state` | The tab dot, the color of the tab's subtitle line, and the status word on that line, which beacon's two-line label pushes out of view |
| `kind` | The detail line in the Session Status tool, when there's no `msg` |
| `msg` | The detail line in the Session Status tool and the Cockpit |
| `title` | Sub-agent rows in the Session Status tool |
| `progress` | The progress bar, which beacon turns off |

Against beacon's surfaces:

| beacon surface | What beacon puts there | OSC 7501 counterpart |
|:---|:---|:---|
| Tab color | Activity: ready, busy, blocked | **`state`**, as the dot and subtitle color. It adds `done` vs `idle` and `error`, which beacon doesn't distinguish. |
| Tab glyph | The declared phase (⏸ 🚀 📋 🏁) | None |
| Tab label | Project over task | None |
| Window title | The same label | None |
| Pane background | The declared phase | None |
| Badge (off by default) | Project and task, in the activity color | Color only |
| Status bar | Project, branch, `↖ web`, `↗ code` | None |
| [Status line](/statusline) | Deliverables, change requests, merge order | None |
| [Sessions view](/demo) | Every session's activity, phase, latest turn, plan mode, and work route | iTerm2's Cockpit groups sessions by `state` with `msg` as detail, in iTerm2 only |

The protocol also brings surfaces beacon has no counterpart for: the dock badge counting sessions waiting on you, the ring when a session first needs you, optional per-status notifications, and a row per running sub-agent.

## How beacon uses it

beacon leaves the reports to iTerm2 and decides how its tab shares the strip with them, through the [tab look](/iterm/layout?id=tab-look):

- **modern** (the default) leaves Claude Code's reports on and paints a dark fill for iTerm2's status colors to read on. A finished turn's task line stays green until you've looked at it, then turns gray.
- **legacy** turns Claude Code's reports off with `CLAUDE_CODE_DISABLE_TERMINAL_TITLE`, and the tab is beacon's color alone.

iTerm2's status colors are fixed, and no iTerm2 setting hides the dot. The ring around a blocked dot marks whichever status sits first in iTerm2's Status Priority list, which is `waiting` unless you reorder it.

## Security

Anything that prints in the pane can send a report: `cat` of a file, `curl`, `git log`, a log you're tailing, a host you're connected to over SSH. The spec treats every report as untrusted input. The table covers what that means on iTerm2 3.7.6.

| Concern | What can happen | Mitigation today |
|:---|:---|:---|
| A false status | Printed output can mark a session `done` or `idle` while it's still working, or `blocked` when it isn't. A report of `state=clear` with no `id` removes every record in the pane, including Claude's real `blocked`. | None in the protocol; it identifies the terminal, not the program. Check the pane before acting on the dot. |
| Status that triggers actions | iTerm2 workgroups can send clippings to another session, or request a review, when a session goes from working to idle. A false report fires them. | Both are opt-in toggles in the workgroup toolbar. Leave them off where untrusted output can reach the pane. |
| Text read by an agent | Orchestrators and agent inboxes read `msg`, which makes it a prompt-injection channel. iTerm2 strips bidi overrides and most invisible formatting from it but keeps Unicode tag characters, which people can't see and models can read. | Don't feed another program's `msg` to a model unfiltered. |
| A fake prompt | `blocked` with `kind=auth` and a message asking for a password shows in the Session Status tool, the Cockpit, and notifications. | iTerm2's per-status notifications are off by default and name the session. No real prompt asks for a password through the status line. |
| Flooding | The record cap is 256 per terminal, oldest dropped first, so a burst of reports can push out real ones. | iTerm2 3.7.6 coalesces floods. |
| Remote hosts | The spec doesn't cover SSH or multiplexers. A remote host's output reports into your local terminal like any other. | tmux drops the sequence; Zellij forwards it unless `host_status false`. |

Reports travel one way. The only reply a terminal sends is the answer to the feature query, which carries nothing from any report, and the protocol has no request that returns the records.

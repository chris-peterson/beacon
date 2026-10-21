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
.osc-gantt .hit, .osc-gantt .rowhit { fill: transparent; }
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
<svg class="osc-gantt" viewBox="0 0 1040 812" role="img" aria-labelledby="osc-g-t osc-g-d">
<title id="osc-g-t">OSC 7501 adoption, Sep 28 to Oct 21 2026</title>
<desc id="osc-g-d">A Gantt chart: the spec from its Sep 28 draft through revision 0.4 on Oct 10, then each terminal and application from its first merged change to its release. Nine had shipped by Oct 21. The sources table below lists every date.</desc>
<text class="day" x="173.5" y="64" text-anchor="middle">28</text>
<text class="day" x="200.4" y="64" text-anchor="middle">29</text>
<text class="day" x="227.3" y="64" text-anchor="middle">30</text>
<text class="day" x="254.2" y="64" text-anchor="middle">1</text>
<text class="day" x="281.2" y="64" text-anchor="middle">2</text>
<rect class="wkend" x="294.6" y="52" width="26.9" height="754"/>
<text class="day" x="308.1" y="64" text-anchor="middle">3</text>
<rect class="wkend" x="321.5" y="52" width="26.9" height="754"/>
<text class="day" x="335.0" y="64" text-anchor="middle">4</text>
<text class="day" x="361.9" y="64" text-anchor="middle">5</text>
<text class="day" x="388.8" y="64" text-anchor="middle">6</text>
<text class="day" x="415.8" y="64" text-anchor="middle">7</text>
<text class="day" x="442.7" y="64" text-anchor="middle">8</text>
<text class="day" x="469.6" y="64" text-anchor="middle">9</text>
<rect class="wkend" x="483.1" y="52" width="26.9" height="754"/>
<text class="day" x="496.5" y="64" text-anchor="middle">10</text>
<rect class="wkend" x="510.0" y="52" width="26.9" height="754"/>
<text class="day" x="523.5" y="64" text-anchor="middle">11</text>
<text class="day" x="550.4" y="64" text-anchor="middle">12</text>
<text class="day" x="577.3" y="64" text-anchor="middle">13</text>
<text class="day" x="604.2" y="64" text-anchor="middle">14</text>
<text class="day" x="631.2" y="64" text-anchor="middle">15</text>
<text class="day" x="658.1" y="64" text-anchor="middle">16</text>
<rect class="wkend" x="671.5" y="52" width="26.9" height="754"/>
<text class="day" x="685.0" y="64" text-anchor="middle">17</text>
<rect class="wkend" x="698.5" y="52" width="26.9" height="754"/>
<text class="day" x="711.9" y="64" text-anchor="middle">18</text>
<text class="day" x="738.8" y="64" text-anchor="middle">19</text>
<text class="day" x="765.8" y="64" text-anchor="middle">20</text>
<text class="day" x="792.7" y="64" text-anchor="middle">21</text>
<text class="day" x="819.6" y="64" text-anchor="middle">22</text>
<text class="day" x="846.5" y="64" text-anchor="middle">23</text>
<line class="today" x1="806.2" x2="806.2" y1="20" y2="806"/>
<rect class="todaytag" x="762.2" y="2" width="88" height="18" rx="9"/>
<text class="todaytxt" x="806.2" y="15" text-anchor="middle">Today, Oct 21</text>
<line class="week" x1="160.0" x2="160.0" y1="30" y2="806"/>
<text class="weekhd" x="166.0" y="42">Week of Sep 28</text>
<line class="week" x1="348.5" x2="348.5" y1="30" y2="806"/>
<text class="weekhd" x="354.5" y="42">Week of Oct 5</text>
<line class="week" x1="536.9" x2="536.9" y1="30" y2="806"/>
<text class="weekhd" x="542.9" y="42">Week of Oct 12</text>
<line class="week" x1="725.4" x2="725.4" y1="30" y2="806"/>
<text class="weekhd" x="731.4" y="42">Week of Oct 19</text>
<line class="rule" x1="160" x2="860" y1="72" y2="72"/>
<text class="colhd" x="880" y="42">Where it stands</text>
<text class="grp" x="12" y="104">Spec</text>
<line class="grpline" x1="12" x2="1028" y1="112" y2="112"/>
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
<a href="https://www.superlogical.com/rex/docs/build/program-status" target="_blank" rel="noopener"><title>Rex: Rex ships alongside the spec</title>
<rect class="rowhit" x="0" y="200.0" width="1040" height="30"/>
<text class="name" x="150" y="219.0" text-anchor="end">Rex</text>
<line class="live" x1="388.8" x2="806.2" y1="215.0" y2="215.0"/>
<path class="ms-ship" d="M388.8,208.0 L395.8,215.0 L388.8,222.0 L381.8,215.0 Z"/>
<text class="status st-link st-shipped" x="880" y="219.0">Shipped with the spec</text>
</a>
<a href="https://github.com/ghostty-org/ghostty/pull/14560" target="_blank" rel="noopener"><title>libghostty: #14560 merged Oct 6; #14630 moved it to rev 0.4 on Oct 10; for Ghostty 1.4.0</title>
<rect class="rowhit" x="0" y="230.0" width="1040" height="30"/>
<text class="name" x="150" y="249.0" text-anchor="end">libghostty</text>
<rect class="bar-merged" x="388.8" y="239.0" width="417.3" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="249.0">Merged, unreleased</text>
</a>
<a href="https://github.com/manaflow-ai/cmux/releases/tag/v0.65.1" target="_blank" rel="noopener"><title>cmux: #18742 merged Oct 9; v0.65.1 released Oct 12</title>
<rect class="rowhit" x="0" y="260.0" width="1040" height="30"/>
<text class="name" x="150" y="279.0" text-anchor="end">cmux</text>
<rect class="bar-work" x="469.6" y="269.0" width="80.8" height="12" rx="3"/>
<line class="live" x1="550.4" x2="806.2" y1="275.0" y2="275.0"/>
<path class="ms-ship" d="M550.4,268.0 L557.4,275.0 L550.4,282.0 L543.4,275.0 Z"/>
<text class="status st-link st-shipped" x="880" y="279.0">Shipped v0.65.1</text>
</a>
<a href="https://iterm2.com/downloads.html" target="_blank" rel="noopener"><title>iTerm2: 49936d3a5 on Oct 9; 3.7.5 tagged Oct 12; 3.7.6 coalesces floods</title>
<rect class="rowhit" x="0" y="290.0" width="1040" height="30"/>
<text class="name" x="150" y="309.0" text-anchor="end">iTerm2</text>
<rect class="bar-work" x="469.6" y="299.0" width="80.8" height="12" rx="3"/>
<line class="live" x1="550.4" x2="806.2" y1="305.0" y2="305.0"/>
<path class="ms-ship" d="M550.4,298.0 L557.4,305.0 L550.4,312.0 L543.4,305.0 Z"/>
<text class="status st-link st-shipped" x="880" y="309.0">Shipped 3.7.5</text>
</a>
<a href="https://github.com/amanthanvi/noctty/releases/tag/v1.3.132" target="_blank" rel="noopener"><title>noctty (Windows): #301 merged Oct 10: tab badges, taskbar, toasts; v1.3.132 released Oct 16</title>
<rect class="rowhit" x="0" y="320.0" width="1040" height="30"/>
<text class="name" x="150" y="339.0" text-anchor="end">noctty (Windows)</text>
<rect class="bar-work" x="496.5" y="329.0" width="161.5" height="12" rx="3"/>
<line class="live" x1="658.1" x2="806.2" y1="335.0" y2="335.0"/>
<path class="ms-ship" d="M658.1,328.0 L665.1,335.0 L658.1,342.0 L651.1,335.0 Z"/>
<text class="status st-link st-shipped" x="880" y="339.0">Shipped v1.3.132</text>
</a>
<a href="https://github.com/herdrdev/herdr/pull/5172" target="_blank" rel="noopener"><title>Herdr: #5172 opened Oct 11</title>
<rect class="rowhit" x="0" y="350.0" width="1040" height="30"/>
<text class="name" x="150" y="369.0" text-anchor="end">Herdr</text>
<rect class="bar-open" x="523.5" y="359.0" width="282.7" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="369.0">Draft pull request</text>
</a>
<a href="https://github.com/deblasis/wintty/pull/1316" target="_blank" rel="noopener"><title>Wintty (Windows): #1316 merged Oct 12; Wintty is a Windows fork of Ghostty</title>
<rect class="rowhit" x="0" y="380.0" width="1040" height="30"/>
<text class="name" x="150" y="399.0" text-anchor="end">Wintty (Windows)</text>
<rect class="bar-merged" x="550.4" y="389.0" width="255.8" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="399.0">Merged, unreleased</text>
</a>
<a href="https://github.com/psmux/psmux/commit/daa6be09c" target="_blank" rel="noopener"><title>psmux (Windows): daa6be09c on Oct 12; a program-status option gates it, off by default; after v3.4.0</title>
<rect class="rowhit" x="0" y="410.0" width="1040" height="30"/>
<text class="name" x="150" y="429.0" text-anchor="end">psmux (Windows)</text>
<rect class="bar-merged" x="550.4" y="419.0" width="255.8" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="429.0">Merged, off by default</text>
</a>
<a href="https://github.com/kovidgoyal/kitty/pull/10657" target="_blank" rel="noopener"><title>kitty: #10657 merged Oct 13</title>
<rect class="rowhit" x="0" y="440.0" width="1040" height="30"/>
<text class="name" x="150" y="459.0" text-anchor="end">kitty</text>
<rect class="bar-merged" x="577.3" y="449.0" width="228.8" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="459.0">Merged, for 0.50.0</text>
</a>
<a href="https://github.com/tmux/tmux/issues/5713" target="_blank" rel="noopener"><title>tmux: #5713 closed Oct 13: premature, waiting to see wider adoption</title>
<rect class="rowhit" x="0" y="470.0" width="1040" height="30"/>
<text class="name" x="150" y="489.0" text-anchor="end">tmux</text>
<path class="decl" d="M572.3,480.0 L582.3,490.0 M572.3,490.0 L582.3,480.0"/>
<text class="status st-link st-declined" x="880" y="489.0">Declined for now</text>
</a>
<a href="https://github.com/warpdotdev/warp/pull/16460" target="_blank" rel="noopener"><title>Warp: #16460 opened Oct 14</title>
<rect class="rowhit" x="0" y="500.0" width="1040" height="30"/>
<text class="name" x="150" y="519.0" text-anchor="end">Warp</text>
<rect class="bar-open" x="604.2" y="509.0" width="201.9" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="519.0">Pull request open</text>
</a>
<a href="https://github.com/zellij-org/zellij/pull/5734" target="_blank" rel="noopener"><title>Zellij: #5734 merged Oct 20</title>
<rect class="rowhit" x="0" y="530.0" width="1040" height="30"/>
<text class="name" x="150" y="549.0" text-anchor="end">Zellij</text>
<rect class="bar-merged" x="765.8" y="539.0" width="40.4" height="12" rx="3"/>
<text class="status st-link st-merged" x="880" y="549.0">Merged, unreleased</text>
</a>
<a href="https://github.com/microsoft/terminal/issues?q=7501" target="_blank" rel="noopener"><title>Windows Terminal: No issue or pull request upstream; ConPTY passes the sequence through</title>
<rect class="rowhit" x="0" y="560.0" width="1040" height="30"/>
<text class="name" x="150" y="579.0" text-anchor="end">Windows Terminal</text>
<text class="status st-link st-none" x="880" y="579.0">No support yet</text>
</a>
<text class="grp" x="12" y="612">Applications</text>
<line class="grpline" x1="12" x2="1028" y1="620" y2="620"/>
<a href="https://github.com/earendil-works/pi/releases/tag/v1.1.0" target="_blank" rel="noopener"><title>pi: v1.1.0 released Oct 7</title>
<rect class="rowhit" x="0" y="630.0" width="1040" height="30"/>
<text class="name" x="150" y="649.0" text-anchor="end">pi</text>
<line class="live" x1="415.8" x2="806.2" y1="645.0" y2="645.0"/>
<path class="ms-ship" d="M415.8,638.0 L422.8,645.0 L415.8,652.0 L408.8,645.0 Z"/>
<text class="status st-link st-shipped" x="880" y="649.0">Shipped v1.1.0</text>
</a>
<a href="https://github.com/anthropics/claude-code/releases/tag/v2.1.295" target="_blank" rel="noopener"><title>Claude Code: 2.1.295 released Oct 8</title>
<rect class="rowhit" x="0" y="660.0" width="1040" height="30"/>
<text class="name" x="150" y="679.0" text-anchor="end">Claude Code</text>
<line class="live" x1="442.7" x2="806.2" y1="675.0" y2="675.0"/>
<path class="ms-ship" d="M442.7,668.0 L449.7,675.0 L442.7,682.0 L435.7,675.0 Z"/>
<text class="status st-link st-shipped" x="880" y="679.0">Shipped 2.1.295</text>
</a>
<a href="https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.0" target="_blank" rel="noopener"><title>Bubble Tea: v2.1.0 released Oct 8</title>
<rect class="rowhit" x="0" y="690.0" width="1040" height="30"/>
<text class="name" x="150" y="709.0" text-anchor="end">Bubble Tea</text>
<line class="live" x1="442.7" x2="806.2" y1="705.0" y2="705.0"/>
<path class="ms-ship" d="M442.7,698.0 L449.7,705.0 L442.7,712.0 L435.7,705.0 Z"/>
<text class="status st-link st-shipped" x="880" y="709.0">Shipped v2.1.0</text>
</a>
<a href="https://github.com/charmbracelet/crush/releases/tag/v0.98.0" target="_blank" rel="noopener"><title>Crush: v0.98.0 released Oct 8, through Bubble Tea</title>
<rect class="rowhit" x="0" y="720.0" width="1040" height="30"/>
<text class="name" x="150" y="739.0" text-anchor="end">Crush</text>
<line class="live" x1="442.7" x2="806.2" y1="735.0" y2="735.0"/>
<path class="ms-ship" d="M442.7,728.0 L449.7,735.0 L442.7,742.0 L435.7,735.0 Z"/>
<text class="status st-link st-shipped" x="880" y="739.0">Shipped v0.98.0</text>
</a>
<a href="https://github.com/openai/codex/pull/52725" target="_blank" rel="noopener"><title>Codex CLI: #52725 merged Oct 9; rust-v0.163.0 released Oct 15</title>
<rect class="rowhit" x="0" y="750.0" width="1040" height="30"/>
<text class="name" x="150" y="769.0" text-anchor="end">Codex CLI</text>
<rect class="bar-work" x="469.6" y="759.0" width="161.5" height="12" rx="3"/>
<line class="live" x1="631.2" x2="806.2" y1="765.0" y2="765.0"/>
<path class="ms-ship" d="M631.2,758.0 L638.2,765.0 L631.2,772.0 L624.2,765.0 Z"/>
<text class="status st-link st-shipped" x="880" y="769.0">Shipped rust-v0.163.0</text>
</a>
<a href="https://github.com/google-gemini/gemini-cli/issues/29710" target="_blank" rel="noopener"><title>Gemini CLI: #29710 opened Oct 10</title>
<rect class="rowhit" x="0" y="780.0" width="1040" height="30"/>
<text class="name" x="150" y="799.0" text-anchor="end">Gemini CLI</text>
<rect class="bar-open" x="496.5" y="789.0" width="309.6" height="12" rx="3"/>
<text class="status st-link st-open" x="880" y="799.0">Requested</text>
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
| Oct 7 | pi | Shipped in v1.1.0 | [release](https://github.com/earendil-works/pi/releases/tag/v1.1.0) |
| Oct 8 | Claude Code | Shipped in 2.1.295 | [release](https://github.com/anthropics/claude-code/releases/tag/v2.1.295) |
| Oct 8 | Bubble Tea | Shipped in v2.1.0 | [release](https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.0) |
| Oct 8 | Crush | Shipped in v0.98.0 | [release](https://github.com/charmbracelet/crush/releases/tag/v0.98.0) |
| Oct 9 | cmux | Merged | [#18742](https://github.com/manaflow-ai/cmux/pull/18742) |
| Oct 9 | iTerm2 | Merged | [`49936d3a5`](https://github.com/gnachman/iTerm2/commit/49936d3a5) |
| Oct 9 | Codex CLI | Merged | [#52725](https://github.com/openai/codex/pull/52725) |
| Oct 10 | Spec | Revision 0.4 | [spec](https://www.superlogical.com/rex/docs/build/program-status) |
| Oct 10 | libghostty | Updated to revision 0.4 | [#14630](https://github.com/ghostty-org/ghostty/pull/14630) |
| Oct 10 | Gemini CLI | Requested | [#29710](https://github.com/google-gemini/gemini-cli/issues/29710) |
| Oct 10 | noctty | Merged | [#301](https://github.com/amanthanvi/noctty/pull/301) |
| Oct 11 | Herdr | Draft pull request opened | [#5172](https://github.com/herdrdev/herdr/pull/5172) |
| Oct 12 | cmux | Shipped in v0.65.1 | [release](https://github.com/manaflow-ai/cmux/releases/tag/v0.65.1) |
| Oct 12 | iTerm2 | Shipped in 3.7.5 | [downloads](https://iterm2.com/downloads.html) |
| Oct 12 | Wintty | Merged | [#1316](https://github.com/deblasis/wintty/pull/1316) |
| Oct 12 | psmux | Merged, off by default | [`daa6be09c`](https://github.com/psmux/psmux/commit/daa6be09c) |
| Oct 13 | kitty | Merged, for 0.50.0 | [#10657](https://github.com/kovidgoyal/kitty/pull/10657) |
| Oct 13 | tmux | Declined for now | [#5713](https://github.com/tmux/tmux/issues/5713) |
| Oct 14 | Warp | Pull request opened | [#16460](https://github.com/warpdotdev/warp/pull/16460) |
| Oct 15 | Codex CLI | Shipped in rust-v0.163.0 | [#52725](https://github.com/openai/codex/pull/52725) |
| Oct 16 | noctty | Shipped in v1.3.132 | [release](https://github.com/amanthanvi/noctty/releases/tag/v1.3.132) |
| Oct 20 | Zellij | Merged | [#5734](https://github.com/zellij-org/zellij/pull/5734) |

</details>
</div>

Checked against each project's own releases, pull requests, and changelogs on **2026-10-21**. Support is moving week to week; the community [support matrix](https://github.com/hyeebeen/awesome-osc7501/blob/main/docs/support-matrix.md) tracks more programs, less strictly.

### Terminals and multiplexers

| Program | Status | Source | How it shows status |
|:---|:---|:---|:---|
| iTerm2 | Shipped in 3.7.5 | [downloads](https://iterm2.com/downloads.html) | A dot on the tab and the status color on the tab's subtitle line; also the Session Status tool, the Cockpit window, and the dock badge |
| cmux | Shipped in v0.65.1 | [release](https://github.com/manaflow-ai/cmux/releases/tag/v0.65.1) | A sidebar row per pane with the app, title, message, and progress |
| Rex | Shipped | [spec](https://www.superlogical.com/rex/docs/build/program-status) | The session picker and unfocused tab headers; a Lua event for scripts |
| kitty | Merged, unreleased (0.50.0) | [#10657](https://github.com/kovidgoyal/kitty/pull/10657) | `tab.program_status` in the tab title template; `kitten @ ls` |
| Zellij | Merged, unreleased | [#5734](https://github.com/zellij-org/zellij/pull/5734) | Marks on pane frames and tabs, an inbox in the session manager; forwards to the outer terminal by default |
| Ghostty | Library only, unreleased (1.4.0) | [#14560](https://github.com/ghostty-org/ghostty/pull/14560) | libghostty keeps the records; the Ghostty app doesn't show them yet |
| Warp | Open pull request | [#16460](https://github.com/warpdotdev/warp/pull/16460) | |
| Herdr | Open draft pull request | [#5172](https://github.com/herdrdev/herdr/pull/5172) | |
| tmux | Declined for now | [#5713](https://github.com/tmux/tmux/issues/5713) | Drops the sequence, so reports from inside tmux never reach the outer terminal |
| noctty (Windows) | Shipped in v1.3.132 | [release](https://github.com/amanthanvi/noctty/releases/tag/v1.3.132) | Tab badges, the taskbar, and toast notifications |
| Wintty (Windows) | Merged, unreleased | [#1316](https://github.com/deblasis/wintty/pull/1316) | A Windows fork of Ghostty; a state glyph on each tab |
| psmux (Windows) | Merged, unreleased | [`daa6be09c`](https://github.com/psmux/psmux/commit/daa6be09c) | A Windows multiplexer; its `program-status` option is off by default |
| Windows Terminal | No support found | | ConPTY passes the sequence through, so it reaches Windows Terminal, which doesn't draw it or answer the query |
| WezTerm, Alacritty, VS Code | No support found | | |

### Applications

| Program | Status | Source | Notes |
|:---|:---|:---|:---|
| Claude Code | Shipped in 2.1.295 | [release](https://github.com/anthropics/claude-code/releases/tag/v2.1.295) | Sends only after the terminal answers the query. `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` turns it off, along with Claude's window title. |
| OpenAI Codex CLI | Shipped in rust-v0.163.0 | [#52725](https://github.com/openai/codex/pull/52725) | `idle`, `working`, and `blocked`, whenever its output is a terminal |
| Crush | Shipped in v0.98.0 | [release](https://github.com/charmbracelet/crush/releases/tag/v0.98.0) | Through Bubble Tea |
| Bubble Tea | Shipped in v2.1.0 | [release](https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.0) | Any Bubble Tea program can report |
| pi | Shipped in v1.1.0 | [release](https://github.com/earendil-works/pi/releases/tag/v1.1.0) | `PI_PROGRAM_STATUS=0` turns it off |
| Gemini CLI | Requested | [#29710](https://github.com/google-gemini/gemini-cli/issues/29710) | || Terraform, Homebrew | Proof of concept | [announcement](https://mitchellh.com/writing/program-status-osc7501) | No upstream change |

## Where it overlaps beacon

Read as a list of keys, the protocol looks like it covers much of what beacon paints: a state, a reason, a message, a title. In practice the overlap is one axis, because of three narrowings between the spec and your tab.

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

beacon doesn't read the reports. It decides how its tab shares the strip with them, through the [tab look](/iterm/layout?id=tab-look):

- **modern** (the default) leaves Claude Code's reports on and paints a dark fill for iTerm2's status colors to read on. A finished turn stays green until you've looked at it, rather than turning red when the prompt sits unanswered.
- **legacy** turns Claude Code's reports off with `CLAUDE_CODE_DISABLE_TERMINAL_TITLE`, and the tab is beacon's color alone.

iTerm2's status colors are fixed, and no iTerm2 setting hides the dot. The ring around a blocked dot marks whichever status sits first in iTerm2's Status Priority list, which is `waiting` unless you reorder it.

## Security

A report is only as trustworthy as the bytes in the pane. Anything that prints there can send one: `cat` of a file, `curl`, `git log`, a log you're tailing, a host you're connected to over SSH. The spec treats every report as untrusted input, and the points below are what that means in practice on iTerm2 3.7.6.

| Concern | What can happen | Mitigation today |
|:---|:---|:---|
| A false status | Printed output can mark a session `done` or `idle` while it's still working, or `blocked` when it isn't. A report of `state=clear` with no `id` removes every record in the pane, including Claude's real `blocked`. | None in the protocol; it identifies the terminal, not the program. Treat the dot as a hint and the pane as the truth. |
| Status that triggers actions | iTerm2 workgroups can send clippings to another session, or request a review, when a session goes from working to idle. A false report fires them. | Both are opt-in toggles in the workgroup toolbar. Leave them off where untrusted output can reach the pane. |
| Text read by an agent | Orchestrators and agent inboxes read `msg`, which makes it a prompt-injection channel. iTerm2 strips bidi overrides and most invisible formatting from it but keeps Unicode tag characters, which people can't see and models can read. | Don't feed another program's `msg` to a model unfiltered. |
| A fake prompt | `blocked` with `kind=auth` and a message asking for a password shows in the Session Status tool, the Cockpit, and notifications. | iTerm2's per-status notifications are off by default and name the session. No real prompt asks for a password through the status line. |
| Flooding | The record cap is 256 per terminal, oldest dropped first, so a burst of reports can push out real ones. | iTerm2 3.7.6 coalesces floods. |
| Remote hosts | The spec doesn't cover SSH or multiplexers. A remote host's output reports into your local terminal like any other. | tmux currently drops the sequence; Zellij forwards it unless `host_status false`. |

What the protocol rules out: it can't be used to read anything back. The only reply a terminal sends is the answer to the feature query, which carries nothing from any report, and there is no way to ask for the records.

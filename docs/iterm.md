# In iTerm2: per-pane painting

On macOS with iTerm2, beacon paints each session's state onto its own pane — the tab's label and color, a status bar, and a background for the mode cycles. Where the [fleet dashboard](/demo) gathers every session into one browser view, per-pane painting works the other way: it puts the state *on the pane itself*, so a glance across a wall of split panes or a row of tabs tells you which session needs you without focusing any of them or opening the dashboard.

These surfaces are an iTerm2 render adapter, so they're macOS + iTerm2 only. On any other terminal beacon skips them and you use the [fleet dashboard](/demo) instead — same state, different view.

<!--
  These figures are drawn in HTML from the spec palette (THEME-02 / THEME-03)
  rather than screenshotted, because the iTerm2 surfaces don't exist off macOS.
  The source of record is dev/iterm-mock.html — edit both together.

  The pf- prefix stays clear of the bcn- namespace that the marketplace hub's
  session.css owns: shipyard links that stylesheet into every plugin whose
  plugin.yml declares a suite, its rules land after this block in the cascade,
  and its .bcn-tab background resolves through a --bcn-state var these figures
  never set — so an equal-specificity name here silently loses its background.
-->
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
.panefig {
  --abyss: #21222c; --body: #282a36; --bar: #30323e; --fg: #f8f8f2;
  --identity: #9aa3c0; --sep: #a0a4b3; --pink: #ff79c6;
  --ready: #8b8fa0; --busy: #ffb86c; --blocked: #ff5555; --paused: #6272a4;
  --green: #50fa7b;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  max-width: 720px; margin: 1rem 0;
}
.pf-win { border: 1px solid rgba(139,233,253,0.14); border-radius: 13px; overflow: hidden; background: var(--body); box-shadow: 0 18px 40px rgba(0,0,0,0.45); }
.pf-title { display: flex; align-items: center; gap: 0.6rem; background: var(--abyss); border-bottom: 1px solid rgba(248,248,242,0.07); padding: 0.6rem 0.85rem; }
.pf-dots { display: inline-flex; gap: 0.45rem; }
.pf-dots i { width: 11px; height: 11px; border-radius: 50%; display: block; }
.pf-dots i:nth-child(1) { background: #ff5f57; }
.pf-dots i:nth-child(2) { background: #febc2e; }
.pf-dots i:nth-child(3) { background: #28c840; }
.pf-wintab { display: inline-flex; flex-direction: column; font: 12px var(--mono); line-height: 1.4; border-radius: 6px; padding: 0.2rem 0.7rem; background: color-mix(in srgb, var(--ready) 18%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ready) 32%, transparent); }
.pf-wintab b { font-weight: 700; color: var(--ready); letter-spacing: 0.04em; }
.pf-wintab .t { color: var(--identity); padding-left: 0.85em; }
/* the strip is one fixed-layout row, so it scrolls rather than wraps once the
   viewport is narrower than it — wrapping would misrepresent what iTerm2 draws */
.pf-bar { display: flex; align-items: center; gap: 0.55rem; background: var(--bar); font: 13px var(--mono); padding: 0.4rem 0.7rem; white-space: nowrap; overflow-x: auto; scrollbar-width: thin; }
.pf-act { color: var(--pink); font-weight: 700; }
.pf-sep { color: var(--sep); }
.pf-proj { color: var(--identity); }
.pf-proj b { color: var(--green); font-weight: 700; }
.pf-spring { flex: 1 1 auto; }
.pf-branch { color: var(--green); }
.pf-branch.diverged { color: var(--busy); }
.pf-body { position: relative; font: 13px var(--mono); color: var(--fg); padding: 0.85rem 0.9rem 1.1rem; min-height: 96px; }
.pf-body .prompt { color: var(--green); }
.pf-mk { display: inline-flex; align-items: center; justify-content: center; width: 1.05em; height: 1.05em; margin-left: 0.3em; border-radius: 50%; background: #8be9fd; color: #21222c; font: 700 0.62em/1 ui-sans-serif, system-ui, sans-serif; vertical-align: super; position: relative; top: -0.15em; }
.pf-legend { list-style: none; counter-reset: panefig; margin: 0.9rem 0 0; padding: 0; display: grid; gap: 0.5rem; }
.pf-legend li { counter-increment: panefig; display: grid; grid-template-columns: 1.4rem 1fr; align-items: start; font-size: 0.9rem; color: inherit; }
.pf-legend li::before { content: counter(panefig); display: inline-flex; align-items: center; justify-content: center; width: 1.15rem; height: 1.15rem; border-radius: 50%; background: #8be9fd; color: #21222c; font-weight: 700; font-size: 0.72rem; }
.pf-legend b { color: inherit; font-weight: 600; }
.panefig code { font: 0.85em var(--mono); background: rgba(128,128,128,0.18) !important; padding: 0.05em 0.35em; border-radius: 4px; color: inherit !important; }
.pf-striprow { display: grid; gap: 0.75rem; }
.pf-strip { border: 1px solid rgba(139,233,253,0.14); border-radius: 9px; overflow: hidden; }
.pf-strip .cap { font-size: 0.85rem; color: #cdd2e6; padding: 0.45rem 0.7rem; background: var(--body); }
.pf-states { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: 0.75rem; }
.pf-chip { border: 1px solid rgba(139,233,253,0.14); border-radius: 10px; background: var(--body); padding: 1rem 0.9rem 0.8rem; text-align: center; }
.pf-chip .b { font: 700 19px/1.15 var(--mono); line-height: 1.3; }
.pf-chip .b .task { display: block; font-weight: 400; font-size: 0.8em; opacity: 0.9; }
.pf-chip .b.ready { color: var(--ready); }
.pf-chip .b.busy { color: var(--busy); }
.pf-chip .b.blocked { color: var(--blocked); }
.pf-chip .b.paused { color: var(--paused); }
.pf-chip .cap { margin-top: 0.6rem; font-size: 0.82rem; color: #cdd2e6; }
.pf-tabcol { display: flex; gap: 1.1rem; align-items: flex-start; flex-wrap: wrap; }
.pf-tabstrip { display: grid; gap: 5px; width: 15rem; flex: 0 0 auto; }
.pf-tab { display: flex; align-items: center; gap: 0.55rem; font: 600 13px var(--mono); color: var(--fg); background: var(--body); border-left: 4px solid var(--sep); border-radius: 5px; padding: 0.6rem 0.65rem; }
.pf-tab i { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; }
.pf-tab .pf-lbl { display: flex; flex-direction: column; line-height: 1.35; min-width: 0; }
.pf-tab .t { font-weight: 400; color: var(--identity); padding-left: 0.85em; }
.pf-tab.ready { border-left-color: var(--ready); } .pf-tab.ready i { background: var(--ready); }
.pf-tab.busy { border-left-color: var(--busy); background: linear-gradient(rgba(255,184,108,0.13), rgba(255,184,108,0.13)), var(--body); } .pf-tab.busy i { background: var(--busy); }
.pf-tab.blocked { border-left-color: var(--blocked); background: linear-gradient(rgba(255,85,85,0.16), rgba(255,85,85,0.16)), var(--body); } .pf-tab.blocked i { background: var(--blocked); }
.pf-tab.paused { border-left-color: var(--paused); } .pf-tab.paused i { background: var(--paused); }
/* this caption sits beside the strip on the page, not inside a dark panel like
   the other .cap variants — so it takes the page's own text color, not theirs */
.pf-tabcol .cap { flex: 1 1 12rem; font-size: 0.9rem; color: inherit; line-height: 1.5; align-self: center; }
</style>

## Anatomy of a painted pane

The tab carries the session's identity and its state, the status bar runs along the top, and the pane itself is left to Claude Code and your profile. (The bar's placement is a [recommended layout](#recommended-layout) setting, not one beacon paints.)

<div class="panefig">
  <div class="pf-win">
    <div class="pf-title">
      <span class="pf-dots"><i></i><i></i><i></i></span>
      <span class="pf-wintab"><b>claude-marketplace<span class="pf-mk">1</span></b><span class="t">Redesign the install flow</span></span>
    </div>
    <div class="pf-body">
      <div><span class="prompt">›</span> run just build</div>
    </div>
    <div class="pf-bar">
      <span class="pf-act">↖ web<span class="pf-mk">2</span></span>
      <span class="pf-spring"></span>
      <span class="pf-proj">claude-marketplace<span class="pf-mk">3</span></span>
      <span class="pf-sep">│</span>
      <span class="pf-branch">main<span class="pf-mk">4</span></span>
      <span class="pf-sep">│</span>
      <span class="pf-act">↗ code<span class="pf-mk">5</span></span>
    </div>
  </div>
  <ol class="pf-legend">
    <li><span><b>Tab</b> — the project, with the task indented under it, tinted by the <em>activity</em> traffic-light and led by the <em>mode</em>'s glyph when one is declared. Two slots, two axes, so a releasing session that needs you shows both at once. Line 1 is also the single-line OS window title, so a window you <code>/rename</code> keeps its project context in Mission Control and the window switcher.</span></li>
    <li><span><b><code>↖ web</code> button</b> — opens this session's web view: the PR/MR/issue it resolves to, else the repo. Both buttons take their text and their command from <code>statusbar.buttons</code> in your config.</span></li>
    <li><span><b>Project chip</b> — the project's name. Needs no git repo, no remote, and no Claude session, so it reads the same in every pane.</span></li>
    <li><span><b>Branch</b> — colored by git sync state: green synced, amber ahead/behind, gray no upstream.</span></li>
    <li><span><b><code>↗ code</code> button</b> — opens this session's working directory in your editor (<code>code</code> by default).</span></li>
  </ol>
</div>

## The tab: a traffic light

The tab's color is the highest-leverage signal beacon paints, and its label is the session's identity — so a strip of tabs tells you what every session is and which one needs you, with nothing focused. The color is the same as a [dashboard card](/demo): the **dev** stoplight — a neutral gray at rest, amber working, red waiting for you — plus a distinct color for each mode cycle (`pause`, `release`, `retro`, `done`). See [The beacon palette](/palette) for the whole set.

<div class="panefig pf-states">
  <div class="pf-chip"><div class="b ready">checkout-api</div><div class="cap">idle — ready for a prompt</div></div>
  <div class="pf-chip"><div class="b busy">checkout-api<span class="task">refunds</span></div><div class="cap">Claude is working</div></div>
  <div class="pf-chip"><div class="b blocked">checkout-api<span class="task">refunds</span></div><div class="cap">waiting for you</div></div>
  <div class="pf-chip"><div class="b ready">⏸ checkout-api</div><div class="cap">paused — the glyph is the mode, the color is still the activity</div></div>
  <div class="pf-chip"><div class="b busy">🚀 checkout-api<span class="task">v2.5.0</span></div><div class="cap">releasing, and working</div></div>
  <div class="pf-chip"><div class="b blocked">🚀 checkout-api<span class="task">v2.5.0</span></div><div class="cap">releasing, and blocked on you</div></div>
</div>

That signal comes into its own with **tabs down the left side**. A left strip turns a fleet of sessions into a scannable column — one row per session, each carrying its state color — so you read the whole fleet at a glance without a single window focused. This is the layout beacon is tuned for, and why the [recommended layout](#recommended-layout) below sets the tabs wider and taller: the default strip is too cramped for the color to register.

<div class="panefig pf-tabcol">
  <div class="pf-tabstrip">
    <div class="pf-tab blocked"><i></i><span class="pf-lbl">checkout-api<span class="t">refunds</span></span></div>
    <div class="pf-tab busy"><i></i><span class="pf-lbl">widgets-web<span class="t">#42</span></span></div>
    <div class="pf-tab ready"><i></i><span class="pf-lbl">auth-svc</span></div>
    <div class="pf-tab busy"><i></i><span class="pf-lbl">beacon<span class="t">#14</span></span></div>
    <div class="pf-tab paused"><i></i><span class="pf-lbl">infra-tf</span></div>
  </div>
  <div class="cap">Five sessions, one column: <b>checkout-api</b> is red — it needs you — while two are working, one idle, one paused. No window focused, no dashboard open.</div>
</div>

Line 1 is the project name; line 2 is the task, and it collapses when no task is set. The hooks own the gray / amber / red dev transitions; you (or a skill) drive the mode cycles — `/beacon:pause "leaving for lunch"`, and from the CLI `beacon release`, `beacon retro`, `beacon done` (or any `beacon status …`). A pause note isn't painted on the tab — it surfaces in the [fleet dashboard](/demo) and in the [status line](#the-status-line), and the next prompt clears it.

### Turning the badge on

beacon can also paint an iTerm2 **badge** — the large project/task overlay in the pane's top-right corner. It's off by default, because the tab already carries the same two values and its color says the same thing. If you work in one window at a time rather than a strip of tabs, the badge is the bigger target — it's the one surface large enough to read in Mission Control / Exposé. Turn it on in `~/.config/beacon/config.json`:

```json
{ "badge": "on" }
```

Re-run `beacon refresh-iterm-profiles` to pick it up; the color follows the same states as the tab.

## The status bar

The status bar carries a fixed-layout strip the tab has no room for: `↖ web ⟷ project branch ↗ code`. It's part of a beacon-managed dynamic profile, so it appears once you're switched into the beacon profile (which `install` handles).

It carries only the two things a link can't do — type a command into the pane, and launch a local app. Navigating to the session's URL is the [status line](#the-status-line)'s job, where it's a real hyperlink that works in any terminal.

The project chip names the project, and the branch beside it is colored by its git sync state:

<div class="panefig pf-striprow">
  <div class="pf-strip">
    <div class="pf-bar">
      <span class="pf-act">↖ web</span><span class="pf-spring"></span><span class="pf-proj">widgets</span><span class="pf-sep">│</span><span class="pf-branch">main</span><span class="pf-sep">│</span><span class="pf-act">↗ code</span>
    </div>
    <div class="cap">On the default branch, synced — branch is green.</div>
  </div>
  <div class="pf-strip">
    <div class="pf-bar">
      <span class="pf-act">↖ web</span><span class="pf-spring"></span><span class="pf-proj">widgets</span><span class="pf-sep">│</span><span class="pf-branch diverged">fix/login</span><span class="pf-sep">│</span><span class="pf-act">↗ code</span>
    </div>
    <div class="cap">Ahead of upstream — branch is amber.</div>
  </div>
  <div class="pf-strip">
    <div class="pf-bar">
      <span class="pf-act">↖ web</span><span class="pf-spring"></span><span class="pf-proj">notes</span><span class="pf-sep">│</span><span class="pf-act">↗ code</span>
    </div>
    <div class="cap">Not a git repo — the chip still names the directory; no branch renders.</div>
  </div>
</div>

The chip needs no git repo, no remote, and no Claude session to have an answer, so it reads the same in every pane. Which **deliverable** you are on is the status line's job (a clickable `#42`), and the `↖ web` button opens it.

## The status line

Claude Code renders footer rows from a command you nominate, above its own badges and never overlapping terminal output. beacon supplies one — `beacon statusline` — and it works in **any** terminal, not just iTerm2.

It gives you a line per class of thing, so a glance separates what you shipped from what's in flight:

```text
⏸ waiting on CI
v1.26.0 released 🚀 · #19 closed ✓ · #27 merged 🏁
#28 Move per-session values into the Claude Code status line
#25 · #18 · #26 · #23
```

Every ref is a clickable link. Empty lines are omitted, so an ordinary session is one line of open work.

- **Delivered** work is kept on screen — shipping is rare and it's what the session has to show for itself. It reads by its verb and glyph, in the same green beacon reserves for releases.
- **Change requests** lead the open work and carry a title: the same string the tab shows, so the two surfaces never describe one PR differently.
- **Issues** trail, dimmed and bare — several share a line, and titling each would wrap the row. GitLab epics (`&7`) and milestones (`%2`) ride the same line.
- Refs in the current project render bare (`#4`); refs elsewhere are qualified (`otherproj:#75`), so a session crossing repos still reads unambiguously.

The row comes from the [tack](https://github.com/chris-peterson/tack) route bound to the session — every deliverable and tracker link it holds — plus whatever the current branch resolves to. So an issue you filed from `main`, with no branch and no open PR, still lands on the row: the route knows about it. With no route bound, the row is just the branch resolution, and keeping a route is what makes it complete.

"Delivered" comes from the same place: a tack that's `done` promotes its deliverable. That means it follows *your* record of the work rather than the forge's — it can drift if a tack goes stale, and the trade is that the row costs no network call. Releases are the exception: a release tag only exists once published, so it needs no tack.

A URL you pasted as a reference is indistinguishable from one you're working, and the row holds eight before the oldest ages out. Take one off with `beacon drop`, naming it the way the row does:

```console
$ beacon drop otherproj:#75
dropped otherproj:#75 (3 deliverable(s) remaining)
```

It stays off for the rest of the session.

`beacon install` prints the `settings.json` block to add; it doesn't edit the file for you. Whether the links are actually clickable is your terminal's call — iTerm2, WezTerm, kitty, Windows Terminal, and recent VTE all render them.

## What beacon doesn't paint

beacon paints the tab's color and label, the status bar, and — in a mode cycle only — the pane background. Everything else belongs to Claude Code, your own profile, or other tools, and beacon leaves it alone: the terminal foreground, the cursor color and shape, the tab title, and the pane background outside a mode. Those are your colors, not beacon's: its profiles inherit from the iTerm2 profile named `Default`. It also disables iTerm2's notification-center and terminal-bell alerts on permission and idle prompts, since the tab color already signals both — a duplicate notification adds no information.

Splitting a beacon pane opens the new pane where the old one is, rather than at your home directory — the profile carries that as a pane-scoped rule. New tabs and windows are left to your own profile's setting.

The window title is the one surface it *did* take over: beacon sets the session name, so a `/rename`d Claude session keeps its project in Mission Control, ⌘\`, and the Dock. The base profile turns off iTerm2's honoring of terminal-set titles to make that stick, which is why Claude Code's own title no longer shows.

## Recommended layout

beacon paints per-*profile* surfaces it fully controls (status bar, colors, mode backgrounds). The *shape* of the tab strip those colors ride on — where the tabs sit, how big they are — lives in iTerm2's **app-wide Appearance preferences**, not in any profile. None of these are per-profile keys, so a beacon dynamic profile can't carry them, and beacon writes no iTerm2 preference at all (that's what keeps `install` restart-free and clear of iTerm2's plist cache). So these are yours to set — beacon only recommends them and, at the end of `install`, tells you which differ.

The tab signal + two-line `project` / `task` label are tuned for a **tall left tab strip**. These settings make that strip readable, and they all live in **iTerm2 → Preferences → Appearance**. [CLI-18](/spec) lists each one: its `defaults` key, the value to set, and why it matters.

Audit your current setup at any time — it reports only what differs and writes nothing:

```
beacon layout
```

Rather than hunt through the Preferences window, let beacon apply them for you:

```
beacon layout --write
```

It confirms each setting, then quits and relaunches iTerm2 with the new values. The quit is unavoidable: iTerm2 holds its preferences in memory and rewrites the plist when it quits, so a write made while it's running is silently clobbered — the only way to make one stick is to write it while iTerm2 is down. **`--write` closes every window and pane, including running sessions, so run it when idle — not with a fleet of work open.** (Prefer the GUI? Every setting is under Appearance → Tabs, except the status bar under Appearance → General.)

That same in-memory copy is why the audit adds a caveat while iTerm2 is running: it reads the plist on disk, which is the effective value only once iTerm2 is down. When the audit reports every setting aligned but the tab strip disagrees, a write landed behind the running app and will be discarded on quit. Name the setting to write it regardless of what the plist says:

```
beacon layout --write --keys CustomTabBarFontSize
```

`beacon layout` is app-wide iTerm2 preferences. Its neighbour `beacon refresh-iterm-profiles` re-renders beacon's *own* dynamic profiles — the status bar, badge sizing, and mode backgrounds — which iTerm2 reloads live, so that one needs no restart. Reach for it after changing a status-bar button `label` in your config.

One related knob is left entirely to taste — beacon renders identically whichever way you set it and never touches it: **pane/window dimming** (Appearance → Dimming). Dimming unfocused panes helps you spot the active one, but also dims beacon's colors on the very panes you're scanning.

## Setup

Per-pane painting is wired up by `/beacon install` on macOS + iTerm2: it writes the dynamic profiles (the base profile and one per mode cycle), adds the shell `source` line, and switches new sessions into the beacon profile. iTerm2 reloads the profile live, so there's no restart. It closes by auditing the [recommended layout](#recommended-layout) and naming any app-wide setting that differs — advisory only, since beacon never writes those. Off iTerm2 these steps are skipped automatically. See [Install](/?id=install).

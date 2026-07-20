# In iTerm2: per-pane painting

On macOS with iTerm2, beacon paints each session's state onto its own pane — a badge, a status bar, and the tab color. Where the [fleet dashboard](/demo) gathers every session into one browser view, per-pane painting works the other way: it puts the state *on the pane itself*, so a glance across a wall of split panes or a row of tabs tells you which session needs you without focusing any of them or opening the dashboard.

These surfaces are an iTerm2 render adapter, so they're macOS + iTerm2 only. On any other terminal beacon skips them and you use the [fleet dashboard](/demo) instead — same state, different view.

<!--
  These figures are drawn in HTML from the spec palette (THEME-02 / THEME-03)
  rather than screenshotted, because the iTerm2 surfaces don't exist off macOS.
  The source of record is dev/iterm-mock.html — edit both together.
-->
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
.bcn {
  --abyss: #21222c; --body: #282a36; --bar: #30323e; --fg: #f8f8f2;
  --identity: #9aa3c0; --sep: #7e8290; --pink: #ff79c6;
  --ready: #8b8fa0; --busy: #ffb86c; --blocked: #ff5555; --paused: #6272a4;
  --green: #50fa7b;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  max-width: 720px; margin: 1rem 0;
}
.bcn-win { border: 1px solid rgba(139,233,253,0.14); border-radius: 13px; overflow: hidden; background: var(--body); box-shadow: 0 18px 40px rgba(0,0,0,0.45); }
.bcn-title { display: flex; align-items: center; gap: 0.6rem; background: var(--abyss); border-bottom: 1px solid rgba(248,248,242,0.07); padding: 0.6rem 0.85rem; }
.bcn-dots { display: inline-flex; gap: 0.45rem; }
.bcn-dots i { width: 11px; height: 11px; border-radius: 50%; display: block; }
.bcn-dots i:nth-child(1) { background: #ff5f57; }
.bcn-dots i:nth-child(2) { background: #febc2e; }
.bcn-dots i:nth-child(3) { background: #28c840; }
.bcn-ttl { font: 12px var(--mono); color: var(--identity); letter-spacing: 0.04em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bcn-bar { display: flex; align-items: center; gap: 0.55rem; background: var(--bar); font: 13px var(--mono); padding: 0.4rem 0.7rem; white-space: nowrap; }
.bcn-act { color: var(--pink); font-weight: 700; }
.bcn-sep { color: var(--sep); }
.bcn-proj { color: var(--identity); }
.bcn-proj b { color: var(--green); font-weight: 700; }
.bcn-spring { flex: 1 1 auto; }
.bcn-branch { color: var(--green); }
.bcn-branch.diverged { color: var(--busy); }
.bcn-body { position: relative; font: 13px var(--mono); color: var(--fg); padding: 0.85rem 0.9rem 1.1rem; min-height: 96px; }
.bcn-body .prompt { color: var(--green); }
.bcn-badge { position: absolute; right: 0.95rem; top: 0.85rem; font: 700 28px/1 var(--mono); letter-spacing: 0.01em; }
.bcn-badge.ready { color: var(--ready); }
.bcn-badge .task { font-weight: 400; opacity: 0.92; }
.bcn-mk { display: inline-flex; align-items: center; justify-content: center; width: 1.05em; height: 1.05em; margin-left: 0.3em; border-radius: 50%; background: #8be9fd; color: #21222c; font: 700 0.62em/1 ui-sans-serif, system-ui, sans-serif; vertical-align: super; position: relative; top: -0.15em; }
.bcn-badge .bcn-mk { background: #f8f8f2; }
.bcn-legend { list-style: none; counter-reset: bcn; margin: 0.9rem 0 0; padding: 0; display: grid; gap: 0.5rem; }
.bcn-legend li { counter-increment: bcn; display: grid; grid-template-columns: 1.4rem 1fr; align-items: start; font-size: 0.9rem; color: inherit; }
.bcn-legend li::before { content: counter(bcn); display: inline-flex; align-items: center; justify-content: center; width: 1.15rem; height: 1.15rem; border-radius: 50%; background: #8be9fd; color: #21222c; font-weight: 700; font-size: 0.72rem; }
.bcn-legend b { color: inherit; font-weight: 600; }
.bcn code { font: 0.85em var(--mono); background: rgba(128,128,128,0.18) !important; padding: 0.05em 0.35em; border-radius: 4px; color: inherit !important; }
.bcn-striprow { display: grid; gap: 0.75rem; }
.bcn-strip { border: 1px solid rgba(139,233,253,0.14); border-radius: 9px; overflow: hidden; }
.bcn-strip .cap { font-size: 0.85rem; color: #cdd2e6; padding: 0.45rem 0.7rem; background: var(--body); }
.bcn-badges { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: 0.75rem; }
.bcn-chip { border: 1px solid rgba(139,233,253,0.14); border-radius: 10px; background: var(--body); padding: 1rem 0.9rem 0.8rem; text-align: center; }
.bcn-chip .b { font: 700 19px/1.15 var(--mono); }
.bcn-chip .b .task { font-weight: 400; opacity: 0.9; }
.bcn-chip .b.ready { color: var(--ready); }
.bcn-chip .b.busy { color: var(--busy); }
.bcn-chip .b.blocked { color: var(--blocked); }
.bcn-chip .b.paused { color: var(--paused); }
.bcn-chip .cap { margin-top: 0.6rem; font-size: 0.82rem; color: #cdd2e6; }
.bcn-tabcol { display: flex; gap: 1.1rem; align-items: flex-start; flex-wrap: wrap; }
.bcn-tabstrip { display: grid; gap: 5px; width: 15rem; flex: 0 0 auto; }
.bcn-tab { display: flex; align-items: center; gap: 0.55rem; font: 600 13px var(--mono); color: var(--fg); background: var(--body); border-left: 4px solid var(--sep); border-radius: 5px; padding: 0.6rem 0.65rem; }
.bcn-tab i { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; }
.bcn-tab .t { font-weight: 400; color: var(--identity); }
.bcn-tab.ready { border-left-color: var(--ready); } .bcn-tab.ready i { background: var(--ready); }
.bcn-tab.busy { border-left-color: var(--busy); background: rgba(255,184,108,0.10); } .bcn-tab.busy i { background: var(--busy); }
.bcn-tab.blocked { border-left-color: var(--blocked); background: rgba(255,85,85,0.12); } .bcn-tab.blocked i { background: var(--blocked); }
.bcn-tab.paused { border-left-color: var(--paused); } .bcn-tab.paused i { background: var(--paused); }
.bcn-tabcol .cap { flex: 1 1 12rem; font-size: 0.9rem; color: #cdd2e6; line-height: 1.5; align-self: center; }
</style>

## Anatomy of a painted pane

The badge sits top-right, the status bar runs along the bottom, and everything else is left to Claude Code and your profile. (The bar's placement is a [recommended layout](#recommended-layout) setting, not one beacon paints.)

<div class="bcn">
  <div class="bcn-win">
    <div class="bcn-title">
      <span class="bcn-dots"><i></i><i></i><i></i></span>
      <span class="bcn-ttl">✳ Redesign frontend plugin installation interface<span class="bcn-mk">1</span></span>
    </div>
    <div class="bcn-body">
      <div><span class="prompt">›</span> run just build</div>
      <span class="bcn-badge ready">claude-marketplace<span class="bcn-mk">6</span></span>
    </div>
    <div class="bcn-bar">
      <span class="bcn-act">↖ web<span class="bcn-mk">2</span></span>
      <span class="bcn-sep">│</span>
      <span class="bcn-proj">gh:chris-peterson/claude-marketplace<span class="bcn-mk">3</span></span>
      <span class="bcn-spring"></span>
      <span class="bcn-sep">│</span>
      <span class="bcn-branch">main<span class="bcn-mk">4</span></span>
      <span class="bcn-sep">│</span>
      <span class="bcn-act">↗ code<span class="bcn-mk">5</span></span>
    </div>
  </div>
  <ol class="bcn-legend">
    <li><span><b>Window title</b> — Claude Code's, not beacon's. beacon never paints the title, terminal colors, or cursor.</span></li>
    <li><span><b><code>↖ web</code> button</b> — opens the URL resolved for this session: an open PR/MR/issue when one matches the branch, else the branch or repo page.</span></li>
    <li><span><b>Project chip</b> — the forge identity, abbreviated (<code>gh:</code>, <code>gl:</code>). Appends <code>#42</code> / <code>!17</code> when the session is on a deliverable.</span></li>
    <li><span><b>Branch</b> — colored by git sync state: green synced, amber ahead/behind, gray no upstream.</span></li>
    <li><span><b><code>↗ code</code> button</b> — opens this session's working directory in VS Code.</span></li>
    <li><span><b>Badge</b> — project name (and task), in the status traffic-light color. The one surface big enough to read in Mission Control.</span></li>
  </ol>
</div>

## The badge: a traffic light

The badge is always on, and its color is the highest-leverage signal beacon paints — it's the only surface large enough to read in Mission Control / Exposé, so a glance across many windows tells you which session needs you. The color is the same as a [dashboard card](/demo): the **dev** stoplight — a neutral gray at rest, amber working, red waiting for you — plus a distinct color for each mode cycle (`pause`, `release`, `retro`, `done`). See [The beacon palette](/palette) for the whole set. The **tab color** mirrors it, so a strip of tabs carries the same state without opening any of them.

<div class="bcn bcn-badges">
  <div class="bcn-chip"><div class="b ready">checkout-api</div><div class="cap">idle — ready for a prompt</div></div>
  <div class="bcn-chip"><div class="b busy">checkout-api<span class="task"> : refunds</span></div><div class="cap">Claude is working</div></div>
  <div class="bcn-chip"><div class="b blocked">checkout-api<span class="task"> : refunds</span></div><div class="cap">waiting for you</div></div>
  <div class="bcn-chip"><div class="b paused">checkout-api</div><div class="cap">paused</div></div>
</div>

That signal comes into its own with **tabs down the left side**. A left strip turns a fleet of sessions into a scannable column — one row per session, each carrying its state color — so you read the whole fleet at a glance without a single window focused. This is the layout beacon is tuned for, and why the [recommended layout](#recommended-layout) below sets the tabs wider and taller: the default strip is too cramped for the color to register.

<div class="bcn bcn-tabcol">
  <div class="bcn-tabstrip">
    <div class="bcn-tab blocked"><i></i>checkout-api<span class="t"> : refunds</span></div>
    <div class="bcn-tab busy"><i></i>widgets-web<span class="t"> : #42</span></div>
    <div class="bcn-tab ready"><i></i>auth-svc</div>
    <div class="bcn-tab busy"><i></i>beacon<span class="t"> : #14</span></div>
    <div class="bcn-tab paused"><i></i>infra-tf</div>
  </div>
  <div class="cap">Five sessions, one column: <b>checkout-api</b> is red — it needs you — while two are working, one idle, one paused. No window focused, no dashboard open.</div>
</div>

The text is the project name, optionally followed by `: <task>` when a task is set. The hooks own the gray / amber / red dev transitions; you (or a skill) drive the mode cycles — `/beacon pause "leaving for lunch"`, `/beacon release`, `/beacon retro`, `/beacon done` (or any `/beacon status …`). A pause note isn't painted on the pane — it surfaces in the [fleet dashboard](/demo) as recall context, and the next prompt clears it.

## The status bar

The status bar carries a fixed-layout strip the badge has no room for: `↖ web · project │ branch · ↗ code`. It's part of a beacon-managed dynamic profile, so it appears once you're switched into the beacon profile (which `install` handles). The two ends pair an action button with the data it acts on — `↖ web` with the project identity it opens, `↗ code` with the working directory.

The project chip answers "what am I working on," not just "what repo am I in" — it appends the deliverable and colors the branch by its git sync state. Clicking `↖ web` opens whatever the chip points at:

<div class="bcn bcn-striprow">
  <div class="bcn-strip">
    <div class="bcn-bar">
      <span class="bcn-act">↖ web</span><span class="bcn-sep">│</span><span class="bcn-proj">gh:acme/widgets</span><span class="bcn-spring"></span><span class="bcn-sep">│</span><span class="bcn-branch">main</span><span class="bcn-sep">│</span><span class="bcn-act">↗ code</span>
    </div>
    <div class="cap">In a repo, no tracked deliverable — <code>↖ web</code> opens the repo.</div>
  </div>
  <div class="bcn-strip">
    <div class="bcn-bar">
      <span class="bcn-act">↖ web</span><span class="bcn-sep">│</span><span class="bcn-proj">gh:acme/widgets<b>#42</b></span><span class="bcn-spring"></span><span class="bcn-sep">│</span><span class="bcn-branch diverged">fix/login</span><span class="bcn-sep">│</span><span class="bcn-act">↗ code</span>
    </div>
    <div class="cap">On a GitHub PR — chip shows <code>#42</code>, branch is amber (ahead of upstream), <code>↖ web</code> opens the PR.</div>
  </div>
  <div class="bcn-strip">
    <div class="bcn-bar">
      <span class="bcn-act">↖ web</span><span class="bcn-sep">│</span><span class="bcn-proj">gl:platform/auth-svc<b>!17</b></span><span class="bcn-spring"></span><span class="bcn-sep">│</span><span class="bcn-branch">passkeys</span><span class="bcn-sep">│</span><span class="bcn-act">↗ code</span>
    </div>
    <div class="cap">On a GitLab MR — chip shows <code>!17</code>, <code>↖ web</code> opens the MR.</div>
  </div>
</div>

The deliverable URL comes from [tack](https://github.com/chris-peterson/tack) when it's tracking the branch, or from `gh`/`glab` when an open PR/MR matches it. Without either, the chip shows the bare repo identity and `↖ web` opens the repo or branch page. See [Tack integration](/?id=tack-integration-optional) for the resolution order.

## What beacon doesn't paint

beacon paints the badge, the status bar, and the tab color — and nothing else. The terminal background and foreground, any background image, the window title, the tab title, and the cursor color and shape all belong to Claude Code, your own profile, or other tools, and beacon leaves them alone. It also disables iTerm2's notification-center and terminal-bell alerts on permission and idle prompts, since the badge color already signals both — a duplicate notification adds no information and can briefly overlay the badge.

## Recommended layout

beacon paints per-*profile* surfaces it fully controls (badge, status bar, colors). The *shape* of the tab strip those colors ride on — where the tabs sit, how big they are — lives in iTerm2's **app-wide Appearance preferences**, not in any profile. None of these are per-profile keys, so a beacon dynamic profile can't carry them, and beacon writes no iTerm2 preference at all (that's what keeps `install` restart-free and clear of iTerm2's plist cache). So these are yours to set — beacon only recommends them and, at the end of `install`, tells you which differ.

The tab signal + two-line `project` / `task` label are tuned for a **tall left tab strip**. These settings make that strip readable; set them in **iTerm2 → Preferences → Appearance**:

| Setting | `defaults` key | Set to | Why it matters |
|:---|:---|:---:|:---|
| Tabs on the left | `TabViewType` | `2` | a left column is the natural home for a fleet; the tab color becomes a scannable strip (Appearance → Tabs) |
| Larger tab labels | `UseCustomTabBarFontSize` + `CustomTabBarFontSize` | `on` + `18` | default labels are unreadably small in a left strip (Appearance → Tabs) |
| Taller tabs | `DefaultTabBarHeight` | `90` | gives the two-line project/task label room to show both lines (Appearance → Tabs) |
| Status bar at the bottom | `StatusBarPosition` | `1` | keeps the status strip clear of the top-right badge (Appearance → General) |
| HTML tab titles | `HTMLTabTitles` | `on` | renders the bold project accent in the two-line tab label (Appearance → Tabs) |

Audit your current setup at any time — it reports only what differs and writes nothing:

```
beacon-iterm configure
```

Rather than hunt through the Preferences window, let beacon apply them for you:

```
beacon-iterm configure --write
```

It confirms each setting, then quits and relaunches iTerm2 with the new values. The quit is unavoidable: iTerm2 holds its preferences in memory and rewrites the plist when it quits, so a write made while it's running is silently clobbered — the only way to make one stick is to write it while iTerm2 is down. **`--write` closes every window and pane, including running sessions, so run it when idle — not with a fleet of work open.** (Prefer the GUI? The `defaults` key and Appearance location for each setting are in the table above.)

Two related knobs are left entirely to taste — beacon renders identically whichever you choose and never touches them: **pane/window dimming** (Appearance → Dimming; dimming unfocused panes helps you spot the active one, but also dims beacon's colors on the very panes you're scanning) and, if you don't use left tabs, **status-bar position** top vs. bottom.

## Setup

Per-pane painting is wired up by `/beacon install` on macOS + iTerm2: it writes the dynamic profile (status bar + badge sizing), adds the shell `source` line, and switches new sessions into the beacon profile. iTerm2 reloads the profile live, so there's no restart. It closes by auditing the [recommended layout](#recommended-layout) and naming any app-wide setting that differs — advisory only, since beacon never writes those. Off iTerm2 these steps are skipped automatically. See [Install](/?id=install).

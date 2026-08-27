# The beacon palette

beacon paints two independent things about a session, so a glance tells you both — no reading required.

**What's happening right now** (`activity`) is the tab **color**: gray at rest, orange working, red when Claude needs you. Three values, one meaning, on every tab.

**What phase you've declared** (`mode`) is the tab **glyph** and, once you focus the pane, its **background**. `⏸` `🚀` `📋` `🏁` `…`.

They never compete, because they never share a surface. A releasing session that needs you is a red tab beside a `🚀`. The same split rides the [dashboard](/demo) cards, so the pane and the browser view always agree. (The color also paints the [badge](/iterm?id=turning-the-badge-on) if you turn one on — it's off by default.)

Colors are drawn from the [Dracula palette](https://draculatheme.com/contribute), each hue serving one meaning across every surface.

<!--
  Figures are drawn in HTML from the spec palette (COLOR_PALETTE / MODE_SPECS /
  MODE_SPECS, THEME-02 / THEME-02a) rather than screenshotted, since the pane surfaces
  don't exist off macOS. The mode watermarks are the real generated assets
  (iterm/resources/<mode>-bg.png), thumbnailed to images/wm-<mode>.png by
  iterm/make-bg.py. Keep the hexes in sync with scripts/beacon.
-->
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
.pal {
  --ground: #21222c; --panel: #282a36; --line: rgba(139,233,253,0.14);
  --fg: #f8f8f2; --muted: #b8bed6; --faint: #7e8290;
  --ready: #8b8fa0; --busy: #ffb86c; --blocked: #ff5555;
  --paused: #6272a4; --release: #50fa7b; --retro: #f8f8f2; --done: #5f6072;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  margin: 1.25rem 0;
}
.pal-stoplight { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 0.75rem; }
.pal-chip { border: 1px solid var(--line); border-radius: 11px; background: var(--panel); padding: 1rem 0.95rem 0.85rem; }
.pal-chip .row { font: 700 20px/1.1 var(--mono); }
/* tab chips take their tint from the state color each figure sets inline */
.pal-chip .tab, .pal-pane .tab { display: inline-flex; flex-direction: column; font: 700 18px/1.3 var(--mono); border-radius: 6px; padding: 0.15rem 0.6rem;
  background: color-mix(in srgb, currentColor 18%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, currentColor 32%, transparent); }
.pal-chip .tab .t, .pal-pane .tab .t { font-weight: 400; font-size: 0.78em; color: var(--muted); padding-left: 0.85em; }
.pal-chip .cap { margin-top: 0.55rem; font-size: 0.84rem; color: var(--muted); line-height: 1.4; }
.pal-chip .hex { font: 0.72rem var(--mono); color: var(--faint); }

.pal-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: 1rem; }
.pal-card { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: var(--panel); }
.pal-pane { position: relative; height: 118px; display: block; }
.pal-pane .wm { position: absolute; inset: 0; margin: auto; width: 60px; height: 60px; object-fit: contain; opacity: 0.6; }
.pal-pane .tab { position: absolute; top: 0.55rem; left: 0.7rem; font-size: 15px; letter-spacing: 0.01em; }
.pal-meta { padding: 0.8rem 0.9rem 0.95rem; }
.pal-meta h4 { margin: 0 0 0.15rem; font: 600 1.05rem/1.2 var(--mono); color: var(--fg); }
.pal-meta .cmd { font: 0.72rem var(--mono); color: var(--faint); }
.pal-meta p { margin: 0.5rem 0 0; font-size: 0.86rem; color: var(--muted); line-height: 1.5; }
.pal-meta .hexrow { margin-top: 0.6rem; display: flex; flex-wrap: wrap; gap: 0.35rem 0.9rem; font: 0.72rem var(--mono); color: var(--faint); }
.pal-meta .hexrow .sw { display: inline-block; width: 0.72rem; height: 0.72rem; border-radius: 3px; vertical-align: middle; margin-right: 0.3rem; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.14); }
.pal code { font: 0.85em var(--mono); background: rgba(128,128,128,0.18) !important; padding: 0.05em 0.35em; border-radius: 4px; color: inherit !important; }
</style>

## activity — the tab color

Everyday development. There's no mode background — the pane stays your own profile — and the tab color is a **dynamic stoplight** the hooks drive as Claude works. Green is deliberately **not** in it: at rest the tab is a calm neutral gray, so a fresh session has a known default before its first turn, and green is freed to mean one thing only — [`release`](#mode-cycles).

<div class="pal pal-stoplight">
  <div class="pal-chip">
    <div class="tab" style="color: var(--ready)">checkout-api<span class="t">refunds</span></div>
    <div class="cap">idle — at rest, ready for a prompt <span class="hex">#8b8fa0</span></div>
  </div>
  <div class="pal-chip">
    <div class="tab" style="color: var(--busy)">checkout-api<span class="t">refunds</span></div>
    <div class="cap">working — Claude is processing <span class="hex">#ffb86c</span></div>
  </div>
  <div class="pal-chip">
    <div class="tab" style="color: var(--blocked)">checkout-api<span class="t">refunds</span></div>
    <div class="cap">waiting for you — a prompt or a permission <span class="hex">#ff5555</span></div>
  </div>
</div>

The tab's label is the project name over the task, indented; line 2 collapses when no task is set. The hooks own these three transitions; you never set them by hand.

## branch — the status-bar chip

The branch chip in the status bar reads by a **hybrid of identity and sync state**. The repo's default branch (`origin/HEAD`, else `main` / `master` / `trunk`) is de-emphasized whatever its state, so a feature branch is the one that stands out — and reads by how it sits against its upstream:

| Branch | Color | Hex |
|:---|:---|:---|
| default (main/master/trunk) | slate, de-emphasized | `#6272a4` |
| feature — synced | cyan | `#8be9fd` |
| feature — diverged (ahead/behind) | yellow | `#f1fa8c` |
| feature — untracked (no upstream) | orange | `#ffb86c` |

Green is absent here too — it stays reserved for [`release`](#mode-cycles). The color is a Dracula hue in every case; the four are published as separate user-var slots so the profile resolves the one that applies without any conditional logic.

## modes — the tab glyph and the pane

A mode is something you (or a skill) declare. Each carries a **glyph on the tab** — its only cross-tab surface, since with many tabs open only one pane is on screen — and swaps that pane into its own dynamic profile for a background the glyph alone can't express: a distinct color plus a faint slate watermark matching the glyph. A mode never touches the tab color, so declaring one never hides whether the session needs you. They persist until you `resume` (`pause` also lifts automatically, on your next prompt).

<div class="pal pal-grid">

  <div class="pal-card">
    <div class="pal-pane" style="background: #3c3357">
      <img class="wm" src="images/wm-pause.png" alt="pause bars watermark">
      <span class="tab" style="color: #8b8fa0">⏸ checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>pause <span class="cmd">/beacon:pause</span></h4>
      <p>You've parked the session. The one mode that can happen anytime — and the one that lifts on its own, the next prompt you send.</p>
      <div class="hexrow"><span>glyph ⏸</span><span><span class="sw" style="background:#3c3357"></span>pane #3c3357</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: #212c45">
      <img class="wm" src="images/wm-release.png" alt="rocket watermark">
      <span class="tab" style="color: #8b8fa0">🚀 checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>release <span class="cmd">beacon release</span></h4>
      <p>A ship-it flow is in progress. The one active mode — a rocket climbing a deep launch-sky.</p>
      <div class="hexrow"><span>glyph 🚀</span><span><span class="sw" style="background:#212c45"></span>pane #212c45</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: #2c4636">
      <img class="wm" src="images/wm-retro.png" alt="checklist clipboard watermark">
      <span class="tab" style="color: #8b8fa0">📋 checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>retro <span class="cmd">beacon retro</span></h4>
      <p>A post-work follow-up or retro phase. A calm green pane under a ticked clipboard — work looked back over.</p>
      <div class="hexrow"><span>glyph 📋</span><span><span class="sw" style="background:#2c4636"></span>pane #2c4636</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: #1a1622">
      <img class="wm" src="images/wm-done.png" alt="checkered finish-flag watermark">
      <span class="tab" style="color: #8b8fa0">🏁 checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>done <span class="cmd">beacon done</span></h4>
      <p>Session complete, ready to hand off. The dimmest, "powered-off" pane under a checkered finish-flag. The tab shows the project alone — the task line is dropped.</p>
      <div class="hexrow"><span>glyph 🏁</span><span><span class="sw" style="background:#1a1622"></span>pane #1a1622</span></div>
    </div>
  </div>

</div>

## status line — the footer rows

The [status line](/iterm?id=the-status-line) is the one surface that isn't iTerm2's, so its palette is ANSI rather than hex: beacon emits SGR codes and *your* terminal theme decides the exact shade. The meanings are fixed even though the shades aren't.

<div class="pal pal-stoplight">
  <div class="pal-chip">
    <div class="row" style="color: #50fa7b"><s>#27</s> <span style="opacity:0.6">merged 🏁</span></div>
    <div class="cap">delivered — green, verb muted against its ref <span class="hex">SGR 32 / 2;32</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #8be9fd; font-weight: 700">#28</div>
    <div class="cap">open change request — full weight <span class="hex">SGR 1;36</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #8be9fd; opacity: 0.55">#25</div>
    <div class="cap">open issue — same hue, dimmed <span class="hex">SGR 2;36</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #6272a4">⏸ waiting on CI</div>
    <div class="cap">the mode's note, led by its glyph <span class="hex">SGR 38;5;61</span></div>
  </div>
</div>

Three rules carry it:

- **One hue, two weights.** A change request and the issues it answers share cyan; the CR is bold and the issues are dim. On GitHub both are `#<n>`, so weight and line position are the only cues that separate them — GitLab's `!` already differs by sigil.
- **Green still means shipped.** The delivered row reuses the same green `release` owns, so it reads as shipping on the footer exactly as it does on the pane.
- **The verb carries the state, not the strike.** `merged 🏁` / `released 🚀` / `closed ✓` are the signal; the strikethrough on the ref is decoration. A four-character struck ref is too subtle at that size, and strikethrough is among the first attributes a terminal drops.

### What a terminal will actually render

The footer's design is bounded by what survives Claude Code's status-line renderer *and* your terminal. This was measured rather than assumed — a probe wired in as a real `statusLine` command, read off the footer in iTerm2:

| Capability | Result | Where beacon relies on it |
|:---|:---|:---|
| Multi-line output | renders | one line per class — delivered, CRs, issues |
| 16-color | yes | every segment |
| 256-color, 24-bit truecolor | yes, full fidelity | available, not yet needed |
| bold / dim | yes | CR vs issue weight |
| underline / reverse | yes | unused — terminals underline links already |
| italic / strikethrough | yes *here* | strike is decorative only, for exactly this reason |
| OSC-8 link, custom label | yes — label shown, URL hidden | every ref is a link |
| **Several OSC-8 links on one line** | yes — each resolves to its own target | the whole accumulated-deliverables design |
| Styling composed with a link | yes | bold/dim/green refs stay clickable |
| Box-drawing glyphs + emoji | yes | `⏸ · 🏁 🚀 ✓` |

Two of these were load-bearing enough that the feature would have been designed differently without them. **Multiple independent links on one line** is what allows a row of refs rather than a single URL. **Multi-line output** is what allows delivered work its own row instead of being crowded in beside open work.

Italic and strikethrough are the two attributes terminals most often drop, so nothing depends on them alone. If yours renders no strike, a delivered ref still reads `#27 merged 🏁`.

## Why these colors

- **Color means one thing.** The tab color answers "does this need me" and nothing else, on every tab, whatever the session has declared about itself. Modes are told apart by shape instead, which is also what lets you read both at once.
- **Gray is the calm default.** A session at rest — and a session that's `done` — sit in neutral grays that recede, so the loud colors (orange, red, green) are the ones that pull your eye.
- **Each mode owns a background.** `pause` a muted purple, `release` a deep launch-sky navy (a darkened Dracula *comment*), `retro` a muted green, `done` a near-black powered-off purple — recognizable whole-pane, not just by the tab.
- **One glyph, never spliced into the name.** A mode's glyph sits in its own slot on the tab, the [dashboard card](/demo), and the sessions list, matching the pane's watermark — so nothing has to add, and later strip, a marker inside the project name. The status line's `🏁 🚀 ✓` are the deliberate exception: that row is prose, not a label, and a delivered ref needs a word and a mark to read at four characters wide.
- **Painted surfaces use hex; the status line uses ANSI.** The pane is beacon's to color exactly. The footer belongs to your terminal, so beacon names a role (bold, dim, green) and lets your theme choose the shade.

The full color contract lives in the [specification](/spec) (THEME, BADGE, RENDER, STATUSLINE); pane hexes are tunable in one place in `scripts/beacon` (`COLOR_PALETTE`, `MODE_SPECS`), and the footer's SGR codes beside them (`STATUSLINE_CR_SGR`, `STATUSLINE_ISSUE_SGR`, `STATUSLINE_DELIVERED_SGR`, `STATUSLINE_VERB_SGR`, `STATUSLINE_TITLE_SGR`).

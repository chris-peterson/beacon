# The beacon palette

beacon paints two independent things about a session, so a glance tells you both.

**What's happening right now** (`activity`) is the tab **color**: gray at rest, orange working, red when Claude needs you. Three values, one meaning, on every tab. That's the legacy [tab look](/iterm/layout?id=tab-look) this page draws. The modern look, the default on iTerm2 3.7.5+, lets Claude Code's own status color the task line and puts a dark fill tinted toward the same hue behind it.

**What phase you've declared** (`mode`) is the tab **glyph** and, once you focus the pane, a **ribbon** atop Claude Code's [status panel](/statusline) with the mode's name in its footer. `⏸` `🚀` `📋` `🏁` `…`.

**What a session is waiting on**, when the color can't say it, is a tab glyph alone: `❓` `🔒` `👀` for what a block wants from you, `⏳` for background work still running. See [tab-only marks](#tab-only-marks-the-glyph-and-nothing-else).

Color and glyph never compete, because they never share a surface. A releasing session keeps its `🚀` whatever its color; when it stops to ask you something, the `🚀` gives way to `❓` or `🔒` until you answer, and the release ribbon stays put. The same split rides the [dashboard](/demo) cards, so the band and the browser view always agree.

**The badge**, the text in the pane's top-right corner, is for other tools to set. By default beacon puts nothing of its own there: a tool that wants to name something about a session writes one line with `beacon badge "<text>"`, in a color of its own with `--color <hex>` or a neutral gray without one, and takes it down with `beacon badge --clear`. (beacon's project and task can sit there too if you [turn that on](/iterm/layout?id=turning-the-badge-on); it's off by default.)

<div class="pal pal-grid">

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: #8b8fa0">checkout-api</span>
      <span class="badge" style="color: #ff79c6">rig: web</span>
    </div>
    <div class="pal-meta">
      <h4>its own color <span class="cmd">beacon badge "rig: web" --color ff79c6</span></h4>
      <p>The badge holds the color it was given, whatever the session is doing.</p>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: #ffb86c">checkout-api</span>
      <span class="badge" style="color: #8b8fa0">rig: web</span>
    </div>
    <div class="pal-meta">
      <h4>neutral gray <span class="cmd">beacon badge "rig: web"</span></h4>
      <p>With no color named, the badge stays gray. The tab reports what the session is doing.</p>
    </div>
  </div>

</div>

**Plan mode is watched but not painted.** beacon reads Claude Code's permission mode off every hook, and surfaces it in the [sessions view](/demo): a card has room for the word `plan` where a tab does not. The tab says nothing about it: color is the only signal you read across every tab at once, so it answers *does this need me* and nothing else.

Colors are drawn from the [Dracula palette](https://draculatheme.com/contribute), each hue serving one meaning across every surface.

<!--
  Figures are drawn in HTML from the spec palette (COLOR_PALETTE / MODE_SPECS /
  BLOCKED_TITLE_LEADS, THEME-02 / THEME-02a) rather than screenshotted, since
  the tab surfaces don't exist off macOS. The ribbon foregrounds are RIBBON_TEXT /
  RIBBON_HINT in hooks/status-panel.tsx. Keep the hexes in sync with scripts/beacon.
-->
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
.pal {
  --ground: #21222c; --panel: #282a36; --line: rgba(139,233,253,0.14);
  --fg: #f8f8f2; --muted: #b8bed6; --faint: #7e8290;
  --idle: #8b8fa0; --working: #ffb86c; --blocked: #ff5555;
  --paused: #6272a4; --release: #50fa7b; --retro: #f8f8f2; --done: #5f6072;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  margin: 1.25rem 0;
}
.pal-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 0.75rem; }
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
.pal-pane .ribbon { position: absolute; left: 0.7rem; right: 0.7rem; bottom: 0.7rem; padding: 0.55rem 0.6rem; border-radius: 4px;
  display: flex; justify-content: space-between; gap: 0.6rem; font: 13px/1.3 var(--mono); color: #f8f8f2; white-space: nowrap; overflow: hidden; }
.pal-pane .ribbon b { font-weight: 700; }
.pal-pane .ribbon .hint { color: #bfbfd0; font-style: italic; }
.pal-pane .footer { position: absolute; right: 0.8rem; bottom: 0.7rem; font: 12px/1.3 var(--mono); color: var(--faint); }
.pal-pane .tab { position: absolute; top: 0.55rem; left: 0.7rem; font-size: 15px; letter-spacing: 0.01em; }
.pal-pane .badge { position: absolute; top: 0.55rem; right: 0.7rem; font: 700 15px/1.3 var(--mono); }
.pal-meta { padding: 0.8rem 0.9rem 0.95rem; }
.pal-meta h4 { margin: 0 0 0.15rem; font: 600 1.05rem/1.2 var(--mono); color: var(--fg); }
.pal-meta .cmd { font: 0.72rem var(--mono); color: var(--faint); }
.pal-meta p { margin: 0.5rem 0 0; font-size: 0.86rem; color: var(--muted); line-height: 1.5; }
.pal-meta .hexrow { margin-top: 0.6rem; display: flex; flex-wrap: wrap; gap: 0.35rem 0.9rem; font: 0.72rem var(--mono); color: var(--faint); }
.pal-meta .hexrow .sw { display: inline-block; width: 0.72rem; height: 0.72rem; border-radius: 3px; vertical-align: middle; margin-right: 0.3rem; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.14); }
.pal code { font: 0.85em var(--mono); background: rgba(128,128,128,0.18) !important; padding: 0.05em 0.35em; border-radius: 4px; color: inherit !important; }
</style>

## activity: the tab color

Everyday development. There's no mode ribbon (the pane stays your own profile, as it does in every mode), and the tab color is the session's **activity**, which the hooks change as Claude works. Green is deliberately **not** one of its colors: at rest the tab is a calm neutral gray, so a fresh session has a known default before its first turn, and green is left to mean one thing: [`release`](#modes-the-tab-glyph-and-the-ribbon).

<div class="pal pal-grid">
  <div class="pal-chip">
    <div class="tab" style="color: var(--idle)">checkout-api<span class="t">refunds</span></div>
    <div class="cap">idle: at rest, ready for a prompt <span class="hex">#8b8fa0</span></div>
  </div>
  <div class="pal-chip">
    <div class="tab" style="color: var(--idle)">⏳ checkout-api<span class="t">refunds</span></div>
    <div class="cap">background: the turn ended, but a background shell or subagent is still running <span class="hex">#8b8fa0</span></div>
  </div>
  <div class="pal-chip">
    <div class="tab" style="color: var(--working)">checkout-api<span class="t">refunds</span></div>
    <div class="cap">working: Claude is processing <span class="hex">#ffb86c</span></div>
  </div>
  <div class="pal-chip">
    <div class="tab" style="color: var(--blocked)">checkout-api<span class="t">refunds</span></div>
    <div class="cap">waiting for you: a question, a permission, or a turn stopped on an API error <span class="hex">#ff5555</span></div>
  </div>
</div>

The tab's label is the project name over the task, indented; line 2 collapses when no task is set. The hooks own these transitions; you never set them by hand. A turn that stops on an API error paints red too, since it won't resume until you act. A turn that ends with background work still running stays gray, because it needs nothing from you, and leads its tab with `⏳` until the last task finishes and wakes the session.

## what the tab actually paints

The hexes above are the hues, and every surface but one paints them as they are. iTerm2's Minimal style (the one beacon pins) paints the state color as the tab's *whole background* rather than a tint, and a left strip makes each tab tall. A hue that reads right in a small dashboard dot is glaring across that much area, so the tab paints each hue under a weight. [Layout](/iterm/layout?id=the-tab-color-is-the-activity) shows the result rendered.

The weight is per state rather than one global dimming. Uniform dimming calms the strip but flattens it: with every tab equally muted, the one session that wants you doesn't stand out from the several that don't. So the weight tracks how often you see a state.

| State | Weight | Tab hex | Why |
|:---|--:|:---|:---|
| `blocked` | 0.90 | `#e64c4c` | rare, and the reason the channel exists, so it stays loud |
| `working` | 0.52 | `#856038` | most of every strip, so it recedes |
| `idle` | 0.46 | `#40424a` | most of every strip, so it recedes furthest |

Multiplying the channels leaves hue and saturation alone and scales only value, so a weighted state is the same color with less light behind it. It's also the transform iTerm2's own inactive-window dimming applies, which is where the numbers started.

## branch: the status panel's head row

The branch on the [status panel](/statusline)'s head row reads by a **hybrid of identity and sync state**. The repo's default branch (`origin/HEAD`, else `main` / `master` / `trunk`) is de-emphasized whatever its state, so a feature branch is the one that stands out, and it reads by how it sits against its upstream:

| Branch | Color | Hex |
|:---|:---|:---|
| default (main/master/trunk) | slate, de-emphasized | `#8d98c4` |
| feature, synced | cyan | `#8be9fd` |
| feature, diverged (ahead/behind) | yellow | `#f1fa8c` |
| feature, untracked (no upstream) | orange | `#ffb86c` |

Green stays reserved here too, for [`release`](#modes-the-tab-glyph-and-the-ribbon). The color is a Dracula hue in every case, and the ahead/behind counts (`↑2↓1`) lead the name in the same color.

## modes: the tab glyph and the ribbon

A mode is something you (or a skill) declare. Each carries a **glyph on the tab** (its only cross-tab surface, since with many tabs open only one pane is on screen) and, in the focused pane, a **ribbon** at the top of the [status panel](/statusline): a bar in the mode's own hue with its glyph, name, and note. The mode's name also joins the labels at the right of Claude Code's footer, so it still shows with the panel collapsed. `retro` is the exception: it runs long and is spent writing, so it gets no ribbon and its glyph is its mark. Both are Claude Code's to draw, so they read the same in any terminal, and your pane keeps its own background in every mode. A mode never touches the tab color, so declaring one never hides whether the session needs you. They persist until you `resume` (`pause` also lifts automatically, on your next prompt).

<div class="pal pal-grid">

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: #8b8fa0">⏸ checkout-api</span>
      <div class="ribbon" style="background: #44385f"><span><b>⏸ paused</b> · back after standup</span></div>
    </div>
    <div class="pal-meta">
      <h4>pause <span class="cmd">/beacon:pause</span></h4>
      <p>You've parked the session. The one mode that can happen anytime, and the one that lifts on its own when you send the next prompt, which its ribbon says.</p>
      <div class="hexrow"><span>glyph ⏸</span><span><span class="sw" style="background:#44385f"></span>ribbon #44385f</span><span>footer <code>paused</code></span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: #8b8fa0">🚀 checkout-api</span>
      <div class="ribbon" style="background: #2a3a63"><span><b>🚀 releasing</b> · v3.0.0</span></div>
    </div>
    <div class="pal-meta">
      <h4>release <span class="cmd">beacon release</span></h4>
      <p>A ship-it flow is in progress. The one active mode, on a launch-sky navy ribbon.</p>
      <div class="hexrow"><span>glyph 🚀</span><span><span class="sw" style="background:#2a3a63"></span>ribbon #2a3a63</span><span>footer <code>releasing</code></span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: #8b8fa0">📋 checkout-api</span>
      <span class="footer">retro</span>
    </div>
    <div class="pal-meta">
      <h4>retro <span class="cmd">beacon retro</span></h4>
      <p>A post-work follow-up or retro phase. No ribbon: its glyph leads the panel's head row and its note sits on the first status line.</p>
      <div class="hexrow"><span>glyph 📋</span><span>footer <code>retro</code></span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: #8b8fa0">🏁 checkout-api</span>
      <div class="ribbon" style="background: #2b2633"><span><b>🏁 done</b> · handed to review</span></div>
    </div>
    <div class="pal-meta">
      <h4>done <span class="cmd">beacon done</span></h4>
      <p>Session complete, ready to hand off. The dimmest ribbon, "powered off". The tab shows the project alone, with no task line.</p>
      <div class="hexrow"><span>glyph 🏁</span><span><span class="sw" style="background:#2b2633"></span>ribbon #2b2633</span><span>footer <code>done</code></span></div>
    </div>
  </div>

</div>

## tab-only marks: the glyph and nothing else

Some states get a glyph on the tab and no ribbon. They're observed rather than declared, and short-lived: a block opens and closes several times a turn, and background work flips at every turn's end. A ribbon for each would flicker in and out to say again what the tab already says, so the panel is left alone.

**Blocked on you.** The color already says the session needs you; the glyph says what for, so you know before switching whether you can reply from memory, have to read what a tool is about to do, or have a review waiting in a split. It stands in for a declared mode's glyph until you answer.

**Waiting on its own work.** `⏳` marks a turn that ended with a background shell, subagent, or monitor still running. The color stays idle, since it needs nothing from you, but it isn't ready for your next prompt either. A declared mode keeps its own glyph.

<div class="pal pal-grid">

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: var(--blocked)">❓ checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>question</h4>
      <p>Claude is asking you something, or wants a plan approved.</p>
      <div class="hexrow"><span>glyph ❓</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: var(--blocked)">🔒 checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>permission</h4>
      <p>Claude wants permission to run a tool.</p>
      <div class="hexrow"><span>glyph 🔒</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: var(--blocked)">👀 checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>review</h4>
      <p>A tool opened something for you to review, like anchor's diff viewer, and is waiting on your verdict. The status panel names what's under review.</p>
      <div class="hexrow"><span>glyph 👀</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: var(--ground)">
      <span class="tab" style="color: var(--idle)">⏳ checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>background</h4>
      <p>The turn ended with background work still running; it wakes the session when it finishes.</p>
      <div class="hexrow"><span>glyph ⏳</span></div>
    </div>
  </div>

</div>

## status lines: under the head row

The [status panel](/statusline) is the one surface that isn't iTerm2's: it draws in Claude Code's band above the prompt, in any terminal. beacon names each line's roles as SGR codes, and the panel draws each code in the Dracula hex beside it below, so the shades are fixed and match the rest of the band. The waiting gray and the mode note use 256-color codes, since no 16-color code reaches 4.5:1 on a dark ground for those two roles ([contrast](#contrast)).

<div class="pal pal-grid">
  <div class="pal-chip">
    <div class="row" style="color: #50fa7b"><s style="font-weight: 700">#27</s> merged 🏁</div>
    <div class="cap">delivered: green, verb a weight below its ref <span class="hex">SGR 1;32 / 32</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #f8f8f2; font-weight: 700">#28</div>
    <div class="cap">open change request: full weight <span class="hex">SGR 1;37</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #f8f8f2">#25</div>
    <div class="cap">open issue: same hue, regular weight <span class="hex">SGR 37</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #9e9e9e; font-weight: 700">!21</div>
    <div class="cap">change request waiting on open work: gray in place of white <span class="hex">SGR 1;38;5;247</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #9e9e9e">#25</div>
    <div class="cap">issue waiting on open work <span class="hex">SGR 38;5;247</span></div>
  </div>
  <div class="pal-chip">
    <div class="row"><span style="color: #9e9e9e">└</span> <span style="color: #9e9e9e; font-weight: 700">!22</span></div>
    <div class="cap">stacked change request, led by its mark <span class="hex">SGR 38;5;247</span></div>
  </div>
  <div class="pal-chip">
    <div class="row" style="color: #af87ff">⏸ waiting on CI</div>
    <div class="cap">the mode's note, led by its glyph <span class="hex">SGR 38;5;141</span></div>
  </div>
</div>

The rules that carry it:

- **One hue, two weights.** A change request and the issues it answers share the foreground white; the CR is bold and the issues are regular weight. On GitHub both are `#<n>`, so weight and line position are the only cues that separate them. On GitLab the `!` sigil already does. A ref is the row's content, so it takes the foreground, and hue is left to say what state it is in.
- **Gray means waiting.** A ref that waits on open work on the row takes gray in place of white and keeps its weight, so the white refs are exactly what can merge now.
- **Green still means shipped.** The delivered row takes the green no state or branch color claims, so it reads as shipping and nothing else.
- **The verb carries the state, not the strike.** `merged 🏁` / `released 🚀` / `closed ✓` are the signal; the strikethrough on the ref is decoration. A four-character struck ref is too subtle at that size, and strikethrough is among the first attributes a terminal drops.

Strikethrough is among the first attributes a terminal drops, so nothing depends on it alone. If yours renders no strike, a delivered ref still reads `#27 merged 🏁`.

## Why these colors

- **Color means one thing.** The tab color answers "does this need me" and nothing else, on every tab, whatever the session has declared about itself. Modes are told apart by shape instead, which is also what lets you read both at once.
- **Gray is the calm default.** A session at rest and a session that's `done` both sit in neutral grays that recede, so the loud colors (orange, red, green) are the ones that pull your eye.
- **Most modes own a ribbon hue.** `pause` a muted purple, `release` a launch-sky navy, `done` a near-black purple. Each is dark enough to sit under one light foreground at WCAG AA or better (see [contrast](#contrast)). `retro` runs long and is spent writing, so it gets no ribbon and is marked by its glyph alone.
- **Only a declared phase gets a ribbon.** A mode is set once and held until you leave it, so it's worth a bar of its own. A block or background work comes and goes within a turn, so it gets the tab glyph alone.
- **Your pane stays yours.** Through 2.x a mode repainted the whole pane through an iTerm2 profile. The ribbon says the same thing, plus the note and how to leave a pause, in any terminal, and the pane background never changes.
- **One glyph, never spliced into the name.** A mode's glyph sits in its own slot on the tab, the ribbon, the [dashboard card](/demo), and the sessions list, so nothing has to add, and later strip, a marker inside the project name. The status lines' `🏁 🚀 ✓` are the deliberate exception: that row is prose, not a label, and a delivered ref needs a word and a mark to read at four characters wide.
- **The panel names roles; the hexes live in one place.** beacon says what a ref is (bold, gray, green) as an SGR code, and the panel turns each code into a Dracula hex, so a retune touches the panel's table and nothing else.

## contrast

Every role clears WCAG AA, 4.5:1, against Dracula's background (`#282a36`), with a dim role measured as iTerm2 draws it: blended halfway into the background. The 2.23 audit found six that didn't, and moved each up to the shade that does, keeping its hue:

| Role | Was | Ratio | Now | Ratio |
|:---|:---|--:|:---|--:|
| open issue | `2;36` | 3.75 | `37` | 13.4 |
| waiting CR / issue | `1;90` / `2;90` | 3.03 / 1.74 | `1;38;5;247` / `38;5;247` | 5.3 |
| stack lead `└` | `90` | 3.03 | `38;5;247` | 5.3 |
| delivered verb | `2;32` | 3.69 | `32` | 10.4 |
| mode note | `38;5;61` | 2.54 | `38;5;141` | 5.2 |
| default branch | `#6272a4` | 3.03 | `#8d98c4` | 5.0 |

The change request moved from cyan to white (`1;37`, 13.4) for a different reason: cyan already says "synced feature branch" on the head row, and a ref is content, not a state.

A mode's ribbon sits on its own hue rather than Dracula's background, so it's measured there. Both of its foregrounds clear AA on every hue, and a test holds them to it:

| Ribbon | Text `#f8f8f2` | Hint `#bfbfd0` |
|:---|--:|--:|
| `pause` `#44385f` | 9.97 | 5.86 |
| `release` `#2a3a63` | 10.46 | 6.15 |
| `done` `#2b2633` | 13.80 | 8.11 |

The full color contract lives in the [specification](/spec) (THEME, BADGE, RENDER, STATUSLINE); tab and ribbon hexes are tunable in one place in `scripts/beacon` (`COLOR_PALETTE`, `MODE_SPECS`), the status lines' SGR codes beside them (`STATUSLINE_CR_SGR`, `STATUSLINE_ISSUE_SGR`, `STATUSLINE_CR_BLOCKED_SGR`, `STATUSLINE_ISSUE_BLOCKED_SGR`, `STATUSLINE_STACK_LEAD_SGR`, `STATUSLINE_DELIVERED_SGR`, `STATUSLINE_VERB_SGR`, `STATUSLINE_TITLE_SGR`), and the hexes the panel draws them and the ribbon's text in at the top of `hooks/status-panel.tsx`.

# The beacon palette

beacon organizes a session's life into **SDLC cycles**, and paints each one so a glance tells you where a session is — no reading required. Every cycle carries a **badge color**; the mode cycles additionally swap the whole pane into a background of their own. The same colors ride the [fleet dashboard](/demo) cards, so the pane and the browser view always agree.

Colors are drawn from the [Dracula palette](https://draculatheme.com/contribute), each hue serving one meaning across every surface.

<!--
  Figures are drawn in HTML from the spec palette (BADGE_COLOR_PALETTE /
  MODE_PROFILES, THEME-02) rather than screenshotted, since the pane surfaces
  don't exist off macOS. Keep the hexes in sync with scripts/beacon.
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
.pal-chip .badge { font: 700 20px/1.1 var(--mono); }
.pal-chip .cap { margin-top: 0.55rem; font-size: 0.84rem; color: var(--muted); line-height: 1.4; }
.pal-chip .hex { font: 0.72rem var(--mono); color: var(--faint); }

.pal-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: 1rem; }
.pal-card { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: var(--panel); }
.pal-pane { position: relative; height: 118px; display: block; }
.pal-pane .wm { position: absolute; inset: 0; margin: auto; width: 46px; height: 46px; }
.pal-pane .badge { position: absolute; top: 0.6rem; right: 0.75rem; font: 700 17px/1 var(--mono); letter-spacing: 0.01em; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
.pal-meta { padding: 0.8rem 0.9rem 0.95rem; }
.pal-meta h4 { margin: 0 0 0.15rem; font: 600 1.05rem/1.2 var(--mono); color: var(--fg); }
.pal-meta .cmd { font: 0.72rem var(--mono); color: var(--faint); }
.pal-meta p { margin: 0.5rem 0 0; font-size: 0.86rem; color: var(--muted); line-height: 1.5; }
.pal-meta .hexrow { margin-top: 0.6rem; display: flex; flex-wrap: wrap; gap: 0.35rem 0.9rem; font: 0.72rem var(--mono); color: var(--faint); }
.pal-meta .hexrow .sw { display: inline-block; width: 0.72rem; height: 0.72rem; border-radius: 3px; vertical-align: middle; margin-right: 0.3rem; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.14); }
.pal code { font: 0.85em var(--mono); background: rgba(128,128,128,0.18) !important; padding: 0.05em 0.35em; border-radius: 4px; color: inherit !important; }
</style>

## dev — the default cycle

Everyday development. There's no mode background — the pane stays your own profile — and the badge color is a **dynamic stoplight** the hooks drive as Claude works. Green is deliberately **not** in it: at rest the badge is a calm neutral gray, so a fresh session has a known default before its first turn, and green is freed to mean one thing only — [`release`](#mode-cycles).

<div class="pal pal-stoplight">
  <div class="pal-chip">
    <div class="badge" style="color: var(--ready)">checkout-api</div>
    <div class="cap">idle — at rest, ready for a prompt <span class="hex">#8b8fa0</span></div>
  </div>
  <div class="pal-chip">
    <div class="badge" style="color: var(--busy)">checkout-api</div>
    <div class="cap">working — Claude is processing <span class="hex">#ffb86c</span></div>
  </div>
  <div class="pal-chip">
    <div class="badge" style="color: var(--blocked)">checkout-api</div>
    <div class="cap">waiting for you — a prompt or a permission <span class="hex">#ff5555</span></div>
  </div>
</div>

The badge text is the project name (plus `: <task>` when a task is set). The hooks own these three transitions; you never set them by hand.

## Mode cycles

The four mode cycles are ones you (or a skill) declare. Each swaps the pane into its own dynamic profile for a whole-pane background the badge color alone can't express, and each carries **no glyph** — the background and badge color are the entire cue. They persist until you `resume` (only `pause` also lifts automatically, on your next prompt).

<div class="pal pal-grid">

  <div class="pal-card">
    <div class="pal-pane" style="background: #3c3357">
      <svg class="wm" viewBox="0 0 24 24" opacity="0.4"><rect x="7.5" y="4" width="3" height="16" rx="1.4" fill="#6272a4"/><rect x="13.5" y="4" width="3" height="16" rx="1.4" fill="#6272a4"/></svg>
      <span class="badge" style="color: #6272a4">checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>pause <span class="cmd">/beacon:pause</span></h4>
      <p>You've parked the session. The one mode that can happen anytime — and the one that lifts on its own, the next prompt you send.</p>
      <div class="hexrow"><span><span class="sw" style="background:#6272a4"></span>badge #6272a4</span><span><span class="sw" style="background:#3c3357"></span>pane #3c3357</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: #212c45">
      <svg class="wm" viewBox="0 0 24 24" opacity="0.5" fill="#50fa7b" fill-rule="evenodd"><path d="M12 3.4 14 8.4 14 12.6 15.8 16 14 15.4 12.9 15.4 12 19 11.1 15.4 10 15.4 8.2 16 10 12.6 10 8.4Z M12 9.3A1.35 1.35 0 1 0 12 12A1.35 1.35 0 1 0 12 9.3Z"/></svg>
      <span class="badge" style="color: #50fa7b">checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>release <span class="cmd">/beacon:release</span></h4>
      <p>A ship-it flow is in progress. The one active mode — a rocket climbing a deep launch-sky, under the green you never see during dev, so it reads unmistakably as "shipping."</p>
      <div class="hexrow"><span><span class="sw" style="background:#50fa7b"></span>badge #50fa7b</span><span><span class="sw" style="background:#212c45"></span>pane #212c45</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: #2c4636">
      <span class="badge" style="color: #f8f8f2">checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>retro <span class="cmd">/beacon:retro</span></h4>
      <p>A post-work follow-up or retro phase. A calm green pane under a white badge — tint only, no watermark.</p>
      <div class="hexrow"><span><span class="sw" style="background:#f8f8f2"></span>badge #f8f8f2</span><span><span class="sw" style="background:#2c4636"></span>pane #2c4636</span></div>
    </div>
  </div>

  <div class="pal-card">
    <div class="pal-pane" style="background: #1a1622">
      <svg class="wm" viewBox="0 0 24 24" opacity="0.55" fill="none" stroke="#5f6072" stroke-width="2" stroke-linecap="round"><path d="M12 3v8"/><path d="M7.4 6.6a6.6 6.6 0 1 0 9.2 0"/></svg>
      <span class="badge" style="color: #5f6072">checkout-api</span>
    </div>
    <div class="pal-meta">
      <h4>done <span class="cmd">/beacon:done</span></h4>
      <p>Session complete, ready to hand off. The dimmest, "powered-off" pane under a power-symbol watermark. The badge shows the project alone — the task is dropped.</p>
      <div class="hexrow"><span><span class="sw" style="background:#5f6072"></span>badge #5f6072</span><span><span class="sw" style="background:#1a1622"></span>pane #1a1622</span></div>
    </div>
  </div>

</div>

## Why these colors

- **Green means one thing.** It's absent from the dev stoplight and reserved for `release`, so a green pane is always "shipping," never "idle."
- **Gray is the calm default.** A session at rest — and a session that's `done` — sit in neutral grays that recede, so the loud colors (orange, red, green) are the ones that pull your eye.
- **Each mode owns a background.** `pause` a muted purple, `release` a deep launch-sky navy (a darkened Dracula *comment*), `retro` a muted green, `done` a near-black powered-off purple — recognizable whole-pane, not just by the badge.
- **No glyphs.** A mode is read by its color and background, the same on the pane, the [dashboard card](/demo), and the fleet list — nothing has to decode a symbol.

The full color contract lives in the [specification](/spec) (THEME, BADGE, RENDER); the hexes are tunable in one place in `scripts/beacon` (`BADGE_COLOR_PALETTE`, `MODE_PROFILES`).

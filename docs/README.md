# <img src="favicon.svg" alt="beacon" width="64" height="64" style="vertical-align: middle"> beacon

At-a-glance awareness across concurrent Claude Code sessions.

beacon surfaces what every session is doing — which project, what task, and what's happening right now — so you can scan a whole fleet without focusing each one. It does this two ways:

- a **fleet dashboard** that reads across all your sessions and works in any terminal (`wip` / `watch` / `serve`) — click a live session to focus its iTerm2 window
- **per-pane painting in iTerm2** — a badge, status bar, and tab color on each pane

A glance across the windows tells you which session needs you:

<!--
  Bespoke fleet figure drawn in HTML from the spec palette (BADGE_COLOR_PALETTE,
  THEME-02) rather than screenshotted, so it stays crisp and on-brand and needs
  no macOS/iTerm2. Same hues and idioms as the .bcn figures on /iterm and /palette
  — keep the hexes in sync with scripts/beacon. The play-by-play narrative it
  replaces still lives in plugin.yml's suite.session (read by the marketplace hub).
-->
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');
.fleet {
  --ground: #21222c; --panel: #282a36; --line: rgba(139,233,253,0.14);
  --fg: #f8f8f2; --muted: #b8bed6; --faint: #7e8290; --sep: #7e8290;
  --ready: #8b8fa0; --busy: #ffb86c; --blocked: #ff5555; --cyan: #8be9fd; --green: #50fa7b;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  margin: 1.4rem 0 1.75rem;
  padding: 1.35rem 1.3rem 1.4rem;
  border: 1px solid var(--line);
  border-radius: 16px;
  background:
    radial-gradient(130% 130% at 88% -20%, rgba(255,85,85,0.13), transparent 52%),
    radial-gradient(120% 130% at 4% 118%, rgba(139,233,253,0.06), transparent 48%),
    linear-gradient(180deg, #262735, var(--ground));
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.035), 0 26px 64px -22px rgba(0,0,0,0.65);
}
.fleet-head { display: flex; align-items: baseline; gap: 0.65rem; flex-wrap: wrap; margin: 0 0.15rem 1.05rem; }
.fleet-head .k { font: 600 0.68rem/1 var(--mono); letter-spacing: 0.22em; text-transform: uppercase; color: var(--faint); }
.fleet-head .h { font: 400 0.9rem/1.4 var(--mono); color: var(--muted); }
.fleet-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.8rem; }
@media (max-width: 620px) { .fleet-grid { grid-template-columns: 1fr; } }
.fl-card {
  position: relative;
  border: 1px solid var(--line);
  border-left: 4px solid var(--sep);
  border-radius: 12px;
  background: var(--panel);
  padding: 0.85rem 0.9rem 0.95rem;
  animation: fl-rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.fl-card:nth-child(1) { animation-delay: 0.05s; }
.fl-card:nth-child(2) { animation-delay: 0.15s; }
.fl-card:nth-child(3) { animation-delay: 0.25s; }
@keyframes fl-rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
.fl-top { display: flex; align-items: center; gap: 0.5rem; }
.fl-dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; box-shadow: 0 0 0 3px rgba(255,255,255,0.03); }
.fl-proj { font: 700 0.98rem/1.2 var(--mono); color: var(--fg); white-space: nowrap; }
.fl-win { margin-left: auto; font: 500 0.66rem/1 var(--mono); letter-spacing: 0.06em; color: var(--faint); text-transform: uppercase; }
.fl-task { margin-top: 0.5rem; font: 400 0.82rem/1.35 var(--mono); color: var(--muted); }
.fl-task b { font-weight: 400; color: var(--faint); }
.fl-foot { margin-top: 0.7rem; display: flex; align-items: center; gap: 0.5rem; }
.fl-branch { font: 400 0.72rem/1 var(--mono); color: var(--cyan); }
.fl-state { margin-left: auto; font: 600 0.68rem/1 var(--mono); letter-spacing: 0.05em; text-transform: uppercase; }
.fl-card.busy    { border-left-color: var(--busy); }
.fl-card.busy .fl-dot   { background: var(--busy); }
.fl-card.busy .fl-state { color: var(--busy); }
.fl-card.ready   { opacity: 0.9; }
.fl-card.ready .fl-dot   { background: var(--ready); }
.fl-card.ready .fl-state { color: var(--ready); }
.fl-card.blocked {
  border-left-color: var(--blocked);
  background:
    linear-gradient(180deg, rgba(255,85,85,0.10), rgba(255,85,85,0.03)),
    var(--panel);
  box-shadow: 0 0 0 1px rgba(255,85,85,0.35), 0 14px 34px -12px rgba(255,85,85,0.4);
}
.fl-card.blocked .fl-dot   { background: var(--blocked); animation: fl-pulse 1.8s ease-in-out infinite; }
.fl-card.blocked .fl-state { color: var(--blocked); }
.fl-card.blocked .fl-branch { color: var(--busy); }
@keyframes fl-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255,85,85,0.55); }
  50%      { box-shadow: 0 0 0 6px rgba(255,85,85,0); }
}
.fl-here { margin-left: auto; padding: 0.12em 0.46em; border-radius: 5px; font: 700 0.6rem/1.4 var(--mono); letter-spacing: 0.07em; text-transform: uppercase; color: var(--ground); background: var(--busy); white-space: nowrap; }
.fl-cap { margin: 1.05rem 0.2rem 0; font-size: 0.86rem; line-height: 1.55; color: var(--muted); }
.fl-cap b { color: var(--fg); font-weight: 600; }
.fl-cap .red { color: var(--blocked); font-weight: 600; }
@media (prefers-reduced-motion: reduce) {
  .fl-card { animation: none; }
  .fl-card.blocked .fl-dot { animation: none; }
}
</style>

<div class="fleet">
  <div class="fleet-head">
    <span class="k">Your fleet</span>
    <span class="h">three windows · one wants you</span>
  </div>
  <div class="fleet-grid">
    <div class="fl-card busy">
      <div class="fl-top"><span class="fl-dot"></span><span class="fl-proj">widgets-web</span><span class="fl-here">you're here</span></div>
      <div class="fl-task">refactor the cart drawer</div>
      <div class="fl-foot"><span class="fl-branch">feat/cart-drawer</span><span class="fl-state">working</span></div>
    </div>
    <div class="fl-card ready">
      <div class="fl-top"><span class="fl-dot"></span><span class="fl-proj">auth-svc</span><span class="fl-win">win 2</span></div>
      <div class="fl-task"><b>idle — waiting for a prompt</b></div>
      <div class="fl-foot"><span class="fl-branch">main</span><span class="fl-state">at rest</span></div>
    </div>
    <div class="fl-card blocked">
      <div class="fl-top"><span class="fl-dot"></span><span class="fl-proj">checkout-api</span><span class="fl-win">win 3</span></div>
      <div class="fl-task">rebase on main — <b>merge conflict in the refund handler</b></div>
      <div class="fl-foot"><span class="fl-branch">fix/refunds</span><span class="fl-state">needs you</span></div>
    </div>
  </div>
  <p class="fl-cap">You're heads-down in <b>widgets-web</b>. Meanwhile <b>checkout-api</b> went <span class="red">red</span> and has been waiting the whole time — the color pulls your eye before you think to check.</p>
</div>

> [!TIP]
> Want to see it first? [Try the demo](/demo) — one command seeds a fictional fleet and serves the real dashboard, no setup and no real sessions. Read the full behavioral spec on the [Specification](/spec) page.

## Platform support

The fleet view reads session state and paints no pane, so it runs anywhere Python 3 does. The per-pane painting is an iTerm2 render adapter, so it's macOS + iTerm2 only. A coworker on Windows or a non-iTerm terminal gets the whole fleet view and skips only the decorations.

| Capability | Where it works |
|:---|:---|
| Fleet dashboard — `wip`, `watch`, `serve`, and the browser dashboard | Any OS, any terminal (needs Python 3) |
| Per-pane painting — badge, status bar, tab color | macOS + iTerm2 |
| Click a dashboard card to raise its window | macOS + iTerm2 |
| Always-on `serve` service | launchd (macOS), systemd (Linux); run `serve` yourself on Windows |

### On Windows or a non-iTerm terminal

1. Install the plugin (see [Install](#install)) — the hooks populate session state on any platform.
2. Run `beacon serve` and open `http://127.0.0.1:8787/` in a browser.

That's the full fleet view: the bundled dashboard, plus `beacon wip` and `beacon watch` at the shell. The badge / status bar / tab color need iTerm2 and are skipped automatically.

## Fleet dashboard (any terminal)

`wip` / `watch` / `serve` read every beacon session's state and paint no pane, so they need no iTerm2 — anywhere Python 3 runs.

- **`beacon wip`** — a snapshot of active work streams, grouped by correlated [tack](https://github.com/chris-peterson/tack) route. `--json` emits the machine-readable payload; `--since` / `--all` set the window.
- **`beacon watch`** — a live, in-place view with the most-recently-active session on top, so a pane that starts working rises to the head. `q` to quit. Use it to scan your own fleet.
- **`beacon serve`** — serves a bundled reference dashboard at `http://127.0.0.1:8787/`, with its data at `/wip.json` (loopback only). Open the URL in any browser to see your fleet — the page polls `/wip.json` and renders one card per session. It also accepts two mutating actions the dashboard drives: `POST /focus` raises a session's iTerm2 window when its card is clicked, and `POST /forget` deletes a session's state when you dismiss a timed-out card (the `beacon forget <hash>` verb does the same from the CLI). To keep it always running, see [the always-on service](#always-on-serve-service-optional) below.

  The bundled dashboard (`dashboard/index.html`) is a self-contained starting point — no build, no dependencies. Clone and restyle it, or point your own dashboard at the same `/wip.json` + `/focus` + `/forget` contract; both work from any browser regardless of the session's terminal.

Each session record carries an `icon` field so a dashboard can show the project's favicon and tell work streams apart at a glance. beacon finds the icon from the project's own files (`docs/favicon.svg`, a root `favicon.*`, the web-framework `public/` / `static/` roots, …); to point it elsewhere, set one with `beacon icon <path-or-url>`. A local icon is served alongside the payload at `/icon/<hash>` (so it needs the live `serve` endpoint); an `http(s)` icon URL is passed through and loads from any origin. The field is `null` when a project ships no icon.

## Always-on serve service (optional)

If an external dashboard polls `serve`, run it under your init system so it survives reboots and restarts on crash — this is opt-in and not part of `/beacon:beacon install`:

```bash
beacon serve install      # launchd agent (macOS) / systemd user unit (Linux)
beacon serve status       # is it installed and running?
beacon serve uninstall    # tear it down
```

The unit runs `beacon serve` via the `~/.local/bin/beacon` wrapper, so a plugin upgrade that refreshes the wrapper keeps the service working. The state files stay the source of record; `serve` re-reads them per request, so the service can restart between two polls without the dashboard noticing.

### Clicking focus or dismiss from a deployed dashboard

The mutating routes `POST /focus` and `POST /forget` accept requests from loopback origins and from the built-in public dashboard. A dashboard served from another origin (e.g. your own GitLab Pages or Cloudflare Pages host) is rejected by the browser's CORS preflight until you add its origin to `~/.config/beacon/config.json`:

```json
{
  "focus_origins": ["https://your-dashboard.example"]
}
```

`serve` reads the config at startup, so restart it after editing (`beacon serve status` to check, then re-run, or restart the always-on unit). The config persists across reinstalls. Reading the dashboard's `wip.json` works from any origin without this; only the focus-on-click action is gated.

## In iTerm2: per-pane painting

On macOS with iTerm2, beacon also paints each session's state onto its own pane — a **badge** (project + task in a status-driven traffic-light color), a **status bar** (`↖ web · project branch ↗ code`, whose buttons open the repo's web view and the cwd in an editor), and the **tab color** (mirrors the badge). It's the other half of beacon: the [fleet dashboard](#fleet-dashboard-any-terminal) gathers every session into one browser view; per-pane painting puts the state *on the pane*, so a glance across split panes or a row of tabs tells you which session needs you.

See **[In iTerm2: per-pane painting](/iterm)** for the anatomy, the badge states, and what the status-bar chips mean.

### Choosing the editor the `↗ code` button opens

By default the button runs `code --maximized`. Point it at a different editor, or pass your own startup arguments, in `~/.config/beacon/config.json`:

```json
{
  "code_app": "subl",
  "code_args": ["-n"]
}
```

The keys are read when you click, so a change takes effect immediately — no `beacon install` re-run. If the command isn't on your `PATH`, beacon asks your login shell before giving up (an action button doesn't inherit your interactive `PATH`, so `/opt/homebrew/bin` and friends are invisible to it). Failing both, the button says so and names the key to fix rather than quietly opening something else.

### Choosing what the `↖ web` button opens

By default it opens whatever beacon resolves for the session — the PR/MR/issue when there is one, else the branch or repo page. If you already have a command for this, point the button at it:

```json
{ "web_cmd": "git web" }
```

It runs in the session's directory, and is resolved the same way (`PATH`, then your login shell), so a git alias or a script both work.

Resolution happens when you click, against that directory — so the button is right even in a pane beacon isn't tracking, like a shell you're just poking around in. That's also why there's no cached URL for it to get wrong.

## Install

```bash
claude plugin marketplace add chris-peterson/claude-marketplace
claude plugin install beacon@chris-peterson
```

Then, inside a Claude Code session, bootstrap everything around the plugin:

```text
/beacon:beacon install
```

The first two commands install the Claude plugin (hooks, slash command, skill, scripts) — these populate session state on any platform, so the fleet dashboard works as soon as the plugin is installed. `/beacon:beacon install` then bootstraps the `beacon` CLI wrapper on `$PATH` and zsh tab completion.

On macOS with iTerm2, `install` additionally sets up the per-pane painting: the shell `source` line and the iTerm2 dynamic profile (status bar + badge sizing). iTerm2 reloads the profile live, so every step completes in place — no restart, and no prefs that need iTerm2 quit. Off iTerm2 (Linux, or a macOS terminal without iTerm.app), those steps are skipped automatically and `install` points you at the fleet dashboard.

To keep `serve` running for an external dashboard, install the always-on service separately — see [Always-on serve service](#always-on-serve-service-optional).

## Verify

In a fresh tab:

```bash
beacon show         # resolved project / task / status (with description if set)
beacon <TAB>        # subcommands with descriptions
```

Then run `claude` in that tab and type any prompt:

- the badge color flips to amber while Claude is processing, back to a neutral gray when the turn ends; it goes red when Claude is waiting for you (a permission or idle prompt)
- `/beacon:session-mode pause "checking lunch options"` parks the session and records your note in the dashboard; sending the next prompt clears both
- `/beacon:beacon status waiting "bg refresh ~30 min"` flips the badge to red and records your note in the dashboard — useful when *you* are waiting on something async, not Claude

## Usage

The label and status commands paint the pane's badge — the same traffic-light colors the [fleet view](/demo) uses. Here's what each one produces:

<!--
  Bespoke command→badge figure in the spec palette (BADGE_COLOR_PALETTE), same
  idioms as the .fleet figure above and the .bcn figures on /iterm and /palette.
  Replaces the generic animated session player; the play-by-play it showed still
  lives in plugin.yml's suite.examples (read by the marketplace hub).
-->
<style>
.cmdfig {
  --ground: #21222c; --panel: #282a36; --line: rgba(139,233,253,0.14);
  --fg: #f8f8f2; --muted: #b8bed6; --faint: #7e8290;
  --ready: #8b8fa0; --busy: #ffb86c; --blocked: #ff5555; --paused: #6272a4; --cyan: #8be9fd;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  margin: 1.3rem 0 1.6rem;
  padding: 0.4rem 1.15rem;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, #262735, var(--ground));
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.035), 0 22px 54px -24px rgba(0,0,0,0.6);
}
.cf-row { display: grid; grid-template-columns: minmax(0, 1fr) 1.4rem minmax(0, 1.15fr); align-items: center; gap: 0.65rem 0.9rem; padding: 0.9rem 0; }
.cf-row + .cf-row { border-top: 1px solid rgba(139,233,253,0.09); }
@media (max-width: 560px) {
  .cf-row { grid-template-columns: 1fr; justify-items: start; gap: 0.4rem; }
  .cf-arrow { display: none; }
}
.cf-cmd {
  font: 500 0.8rem/1.5 var(--mono) !important;
  color: var(--cyan) !important;
  background: linear-gradient(rgba(139,233,253,0.08), rgba(139,233,253,0.08)), var(--ground) !important;
  border: 1px solid var(--line);
  padding: 0.4em 0.6em !important;
  border-radius: 7px;
  white-space: normal !important;
  overflow-wrap: break-word;
}
.cf-arrow { color: var(--faint); font: 400 1.05rem/1 var(--mono); text-align: center; }
.cf-out { display: flex; flex-direction: column; gap: 0.22rem; min-width: 0; }
.cf-badge { font: 700 1.05rem/1.15 var(--mono); white-space: nowrap; }
.cf-badge .t { font-weight: 400; opacity: 0.9; }
.cf-badge.ready { color: var(--ready); }
.cf-badge.blocked { color: var(--blocked); }
.cf-badge.paused { color: var(--paused); }
.cf-cap { font: 400 0.78rem/1.4 var(--mono); color: var(--muted); }
</style>

<div class="cmdfig">
  <div class="cf-row">
    <code class="cf-cmd">/beacon:beacon set task perms</code>
    <span class="cf-arrow">→</span>
    <span class="cf-out">
      <span class="cf-badge ready">ai-sdlc<span class="t"> : perms</span></span>
      <span class="cf-cap">labeled — neutral gray while idle</span>
    </span>
  </div>
  <div class="cf-row">
    <code class="cf-cmd">/beacon:beacon status waiting "bg refresh"</code>
    <span class="cf-arrow">→</span>
    <span class="cf-out">
      <span class="cf-badge blocked">ai-sdlc<span class="t"> : perms</span></span>
      <span class="cf-cap">you flag yourself waiting — the badge goes red</span>
    </span>
  </div>
  <div class="cf-row">
    <code class="cf-cmd">/beacon:session-mode pause "lunch"</code>
    <span class="cf-arrow">→</span>
    <span class="cf-out">
      <span class="cf-badge paused">ai-sdlc<span class="t"> : perms</span></span>
      <span class="cf-cap">parked — the pane dims to purple</span>
    </span>
  </div>
</div>

Inside Claude Code:

```text
/beacon:beacon                               # show resolved state (default)
/beacon:beacon status waiting "bg refresh"   # set status with a description
/beacon:session-mode pause "out for lunch"   # any mode: pause/release/retro/done
/beacon:session-mode resume                  # clear all overrides + description
/beacon:beacon clear status                  # clear just the status override
```

At the shell:

```bash
beacon show
beacon status paused "afk"
beacon pause "afk"
```

### Claude Code's own `/rename` and `/color`

If reaching for beacon's own commands feels heavier than the built-ins, beacon also picks up Claude Code's native slash commands:

- **`/rename <label>`** becomes the session's `task` — it's shorthand for `beacon task`, folded into the same label slot, so the two are peers: whichever you set most recently wins (above the PR-title/branch fallbacks). It shows on the badge (`project: <label>`) and in the fleet view.
- **`/color <name>`** is surfaced in the fleet view (a swatch on the dashboard card) as your own tag. It does **not** repaint the badge — that color stays the ready/busy/blocked status light.
- Claude Code's auto-generated title is the weakest `task` fallback, so a session you never labeled still shows a readable headline.

`pause` / `wrap` sit above the task label; between `beacon task` and `/rename`, the most recent one wins.

## Tack integration (optional)

beacon has a soft dependency on [tack](https://github.com/chris-peterson/tack), a CLI for tracking AI-assisted development work. When `tack` is on `$PATH`, beacon asks it for the URL most relevant to the current branch and surfaces that URL in two places:

- The status-line link points at it instead of the bare project URL.
- The project chip appends `#42` (issue/PR) or `!17` (GitLab MR) when the URL is a forge deliverable — `gh:owner/repo#42` instead of just `gh:owner/repo`.

The dependency is **soft**: if tack isn't installed or has nothing for the current branch, beacon probes the forge directly — `gh pr list --head <branch>` on github hosts, `glab mr list --source-branch <branch>` on gitlab hosts — and uses the first open PR/MR it finds. This catches the common case where you've pushed an MR but never ran `tack link add`. If the forge has nothing either (or neither CLI is installed), beacon falls through to a branch URL or the bare project URL. No configuration on any path.

Prefer Linear, Jira, GitHub Issues, or a custom provider? Override `_beacon_resolve_url()` in your `.zshrc` after sourcing `beacon.zsh`. The function returns a `<url>\t<label>` line and slots into PROV-07; see [PROV-07](/spec) and [BADGE-08](/spec) for the full contract.

## Standalone (no tack, no recipes)

beacon works on its own. The hooks set the fields they can observe — project, branch, and the ready / busy / blocked status color — without any other tooling. The one thing they can't observe is *what each session is working on*, the recall context that makes the fleet view worth a glance.

To fill that gap standalone, beacon ships an ambient rule (`rules/keep-session-labeled.md`, emitted into context at session start) that has Claude keep the session's `task` label current as the work focus shifts. So the fleet view stays meaningful even with no tack route bound and no recipe nudging Claude to label the pane. When tack *is* tracking the work, the rule defers to it — tack supplies the route and the rule leaves the beacon task alone, so the two don't fight.

## Upgrade

Third-party Claude Code marketplaces have auto-update **off by default**. Either:

- **Enable auto-update once** via `/plugin` → Marketplaces → `chris-peterson` → Enable auto-update. Future releases install on the next session start.
- **Or update manually** with `claude plugin update beacon@chris-peterson`.

After every upgrade, re-run `/beacon:beacon install` (or just `/beacon:beacon install-cli` if all you need is a fresh wrapper). Plugin upgrades change the version-pinned cache path; both the `source` line in `.zshrc` and the wrapper at `~/.local/bin/beacon` hardcode that path at install time and need to be rewritten to point at the new version. The plugin's `SessionStart` hook compares `beacon --version` against the installed plugin version on every Claude Code session start and nudges you to refresh when they differ.

Confirm what's installed: `beacon --version`. See [`CHANGELOG.md`](https://github.com/chris-peterson/beacon/blob/main/CHANGELOG.md) for release notes.

## Uninstall

```text
/plugin uninstall beacon
```

If you set up the [always-on serve service](#always-on-serve-service-optional), tear it down first: `beacon serve uninstall`.

To fully clean up the shell side, also delete these from `~/.zshrc`:

```zsh
fpath=(~/.zsh/completions $fpath)         # only if no other tool relies on it
source ".../beacon/shell/beacon.zsh"      # beacon: project · branch · status badging
```

And `rm ~/.zsh/completions/_beacon ~/.local/bin/beacon`.

## Architecture

beacon ships as three deliverables with a hard boundary between them:

| ID | What | Form |
|:---|:---|:---|
| D1 | This specification | [SPEC.md](/spec) |
| D2 | `beacon-iterm` CLI | A stateless executable that emits iTerm2 escape sequences |
| D3 | `beacon` Claude Code plugin | Hooks, slash command, skill, COR resolver, shell integration |

D3 invokes D2 for every iTerm2 surface change. D2 has no Claude awareness — it can be used from any caller, which keeps the seam clean for future render-target CLIs (`beacon-tmux`, etc.) or driver plugins.

## License

MIT.

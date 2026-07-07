# <img src="favicon.svg" alt="beacon" width="64" height="64" style="vertical-align: middle"> beacon

At-a-glance awareness across concurrent Claude Code sessions.

beacon surfaces what every session is doing — which project, what task, and what's happening right now — so you can scan a whole fleet without focusing each one. It does this two ways:

- a **fleet dashboard** that reads across all your sessions and works in any terminal (`wip` / `watch` / `serve`) — click a live session to focus its iTerm2 window
- **per-pane painting in iTerm2** — a badge, status bar, and tab color on each pane

A glance across the windows tells you which session needs you:

<div class="cw-session" data-cw-session="session"></div>

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

On macOS with iTerm2, beacon also paints each session's state onto its own pane — a **badge** (project + task in a status-driven traffic-light color), a **status bar** (`↖ web · project │ branch · ↗ code`, whose buttons open the resolved PR/MR/issue and the cwd in VS Code), and the **tab color** (mirrors the badge). It's the other half of beacon: the [fleet dashboard](#fleet-dashboard-any-terminal) gathers every session into one browser view; per-pane painting puts the state *on the pane*, so a glance across split panes or a row of tabs tells you which session needs you.

See **[In iTerm2: per-pane painting](/iterm)** for the anatomy, the badge states, and what the status-bar chips mean.

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
- `/beacon:pause "checking lunch options"` moves the badge to the muted-purple pause color (and dims the pane); the note shows in the fleet dashboard, and sending the next prompt clears both
- `/beacon:beacon status waiting "bg refresh ~30 min"` flips the badge to red and records your note in the dashboard — useful when *you* are waiting on something async, not Claude

## Usage

Labeling a pane and scanning the fleet, in motion:

<div class="cw-session" data-cw-session="examples"></div>

Inside Claude Code:

```text
/beacon:beacon                             # show resolved state (default)
/beacon:beacon status waiting "bg refresh" # set status with a description
/beacon:pause "leaving for lunch"          # shorthand for `status paused …`
/beacon:beacon resume                      # clear all overrides + description
/beacon:beacon clear status                # clear just the status override
```

At the shell:

```bash
beacon show
beacon status paused "afk"
beacon pause "afk"
```

### Claude Code's own `/rename` and `/color`

If reaching for beacon's own commands feels heavier than the built-ins, beacon also picks up Claude Code's native slash commands:

- **`/rename <label>`** becomes the session's `task` — sitting just below an explicit `beacon task` override, above the PR-title/branch fallbacks. It shows on the badge (`project: <label>`) and in the fleet view.
- **`/color <name>`** is surfaced in the fleet view (a swatch on the dashboard card) as your own tag. It does **not** repaint the badge — that color stays the ready/busy/blocked status light.
- Claude Code's auto-generated title is the weakest `task` fallback, so a session you never labeled still shows a readable headline.

An explicit `beacon task` / `pause` / `wrap` always wins over these.

## Tack integration (optional)

beacon has a soft dependency on [tack](https://github.com/chris-peterson/tack), a CLI for tracking AI-assisted development work. When `tack` is on `$PATH`, beacon asks it for the URL most relevant to the current branch and surfaces that URL in two places:

- The `↖ web` button opens it instead of the bare project URL.
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
| D1 | This specification | [docs/spec.md](/spec) |
| D2 | `beacon-iterm` CLI | A stateless executable that emits iTerm2 escape sequences |
| D3 | `beacon` Claude Code plugin | Hooks, slash command, skill, COR resolver, shell integration |

D3 invokes D2 for every iTerm2 surface change. D2 has no Claude awareness — it can be used from any caller, which keeps the seam clean for future render-target CLIs (`beacon-tmux`, etc.) or driver plugins.

## License

MIT.

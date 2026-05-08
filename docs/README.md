# <img src="favicon.svg" alt="beacon" width="64" height="64" style="vertical-align: middle"> beacon

At-a-glance session awareness for Claude Code in iTerm2.

beacon shows what each Claude Code session is doing without you having to focus on it. Two surfaces in every iTerm2 pane:

- **Badge** (always on) — project name plus a status-driven color: green when idle, amber when Claude is working, red when waiting on you or paused. The badge stays readable in Mission Control / Exposé, so a glance across many windows tells you which sessions need attention.
- **Status bar** (in the beacon profile) — a fixed-layout strip: `↖ web · project · branch · cwd · ↗ code`. The `↖ web` button opens the resolved URL (a CR/PR/issue if [tack](https://github.com/chris-peterson/tack) is on `$PATH` and matches the branch, otherwise a branch URL or the project URL); the `↗ code` button opens the cwd in VS Code.

Plus a third surface only during pause:

- **Post-it overlay** — a yellow sticky-note bg image carrying your free-text note (`/beacon pause "leaving for lunch"`). Distinguishes paused from waiting — both share the red badge color, but only pause paints the overlay.

> [!TIP]
> Read the full behavioral spec on the [Specification](/spec) page.

## Install

```text
/plugin marketplace add chris-peterson/claude-marketplace
/plugin install beacon@chris-peterson/claude-marketplace
/beacon install
```

The first two commands install the Claude plugin (hooks, slash command, skill, scripts). `/beacon install` then bootstraps everything around it: shell `source` line, zsh tab completion, the iTerm2 dynamic profile, `PerPaneBackgroundImage`, and post-it bg-image trust pre-approval.

Some prefs (default profile, bg-image trust pre-approval) only stick when iTerm2 is fully quit. If `install` reports those steps as DEFERRED, run `beacon exclusive-configuration` — it confirms before quitting iTerm2, applies the writes, and relaunches.

## Stage vs status

| | Stage | Status |
|:---|:---|:---|
| Question | What kind of work? | What's happening right now? |
| Pace | Minutes-to-hours | Sub-second-to-seconds |
| Driven by | Skill (`plan`, `review`) + hooks (`dev`, `shipping`) + override | Hooks (`working`, `waiting`) + override |

Status drives the badge color; stage shows up in `beacon show` for cross-session handoff.

## Usage

Inside Claude Code:

```text
/beacon                                    # show resolved state (default)
/beacon pause "leaving for lunch"
/beacon resume
/beacon set stage review                   # explicit override
/beacon clear stage                        # remove a single override
```

At the shell:

```bash
beacon show
beacon stage plan
beacon pause "afk"
```

> [!NOTE]
> The skill bundled with the plugin tells Claude to set `stage plan` on plan-mode entry and `stage review` when you ask for code review — both are events hooks can't see. Hooks own `dev`, `shipping`, and all status transitions.

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

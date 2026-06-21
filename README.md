# beacon

At-a-glance awareness across concurrent Claude Code sessions — a terminal-agnostic fleet dashboard plus iTerm2 per-pane painting.

**[Read the docs](https://chris-peterson.github.io/beacon/)** for install, usage, and the full behavioral spec.

This README covers working *on* beacon. To install or use the released plugin, follow the docs site.

## Develop / install from a clone

Working on beacon directly (no marketplace):

```bash
git clone https://github.com/chris-peterson/beacon ~/src/beacon
python3 ~/src/beacon/scripts/beacon install
```

This wires up the shell side just like `/beacon:beacon install`, but pointed at your clone. To get the plugin side (slash command, hooks, skill) loaded into Claude Code, use the marketplace install path — `claude --plugin-dir` may not register hooks reliably across versions.

## Dependencies

The fleet dashboard (`wip` / `watch` / `serve`) needs only:

- Python 3 — the plugin script and CLI run via the system `python3`.

The per-pane painting layer (badge, status bar, tab color; spec §4) additionally needs:

- macOS with iTerm2 — the render adapter is iTerm2-specific. `install` detects iTerm.app and skips these steps when it's absent.
- zsh — the shell snippet relies on zsh-only features.

The always-on serve service (`beacon serve install`) uses launchd on macOS, systemd user units on Linux.

## Repository layout

| Path | What |
|:---|:---|
| `bin/beacon-iterm` | Stateless CLI that translates subcommands to iTerm2 OSC sequences (D2) |
| `scripts/beacon` | Plugin script — hook handlers, COR resolver, slash command, install (D3) |
| `shell/beacon.zsh` | Sourceable zsh snippet — refreshes project / branch / cwd / URL on every prompt |
| `hooks/`, `commands/`, `skills/` | Claude Code plugin glue |
| `rules/` | Ambient rules emitted into context at SessionStart by `hooks/emit-rules.sh` |
| `dashboard/index.html` | Self-contained reference fleet dashboard `serve` hosts at `/` |
| `iterm/profile.json.template` | Beacon dynamic profile, including the status-bar layout |
| `docs/` | Docsify site sources; `spec.md` is the EARS-style behavioral spec (D1) |

## Tests

```bash
just test                              # or:
python3 -m unittest discover -s tests -v
```

The suite is pure stdlib `unittest` — it loads `scripts/beacon` via importlib and mocks `_cli` and `sys.platform`, so the iTerm2 paint paths and the launchd/systemd/Windows branches are all exercised without a Mac. `.github/workflows/test.yml` runs it on an `ubuntu` / `macos` / `windows` × Python `3.9`–`3.13` matrix on every push and PR, which is what guards the cross-platform fallbacks (session-id seeding, `watch` polling) from regressing.

## Architecture

beacon ships as three deliverables with a hard boundary between them:

| ID | What | Form |
|:---|:---|:---|
| D1 | Behavioral spec | [docs/spec.md](docs/spec.md) |
| D2 | `beacon-iterm` CLI | Stateless OSC-emitter executable |
| D3 | `beacon` Claude Code plugin | Hooks, slash command, skill, COR resolver, shell integration |

D3 invokes D2 for every iTerm2 surface change. D2 has no Claude awareness — it can be used from any caller, which keeps the seam clean for future render-target CLIs (`beacon-tmux`, `beacon-kitty`) or driver plugins.

The behavioral contract for hooks vs shell is documented in [`CLAUDE.md`](CLAUDE.md): the plugin owns `status` (and its optional description) and writes to its user-var slots; the shell owns `project`/`branch`/`cwd`/`url` and writes to disjoint slots; the CLI is unaware of either.

`beacon wip` / `watch` / `serve` (spec §3.8) are the terminal-agnostic fleet surface on D3 — they enumerate every session's state and render a snapshot (TTY, JSON, or localhost HTTP) for external dashboards rather than painting iTerm2, so they don't route through D2 and work in any terminal. `beacon serve install` keeps `serve` running under launchd/systemd. The per-session state-file directory is the single source of record: the iTerm2 paint and the fleet view both read it, and `serve` re-reads it per request, so they can't disagree.

## License

MIT. See [LICENSE](LICENSE).

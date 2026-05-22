# beacon

At-a-glance session awareness for Claude Code in iTerm2.

**[Read the docs](https://chris-peterson.github.io/beacon/)** for install, usage, and the full behavioral spec.

This README covers working *on* beacon. To install or use the released plugin, follow the docs site.

## Develop / install from a clone

Working on beacon directly (no marketplace):

```bash
git clone https://github.com/chris-peterson/beacon ~/src/beacon
python3 ~/src/beacon/scripts/beacon install
```

This wires up the shell side just like `/beacon install`, but pointed at your clone. To get the plugin side (slash command, hooks, skill) loaded into Claude Code, use the marketplace install path — `claude --plugin-dir` may not register hooks reliably across versions.

## Dependencies

- macOS with iTerm2 — the only adapter today; spec §4 is iTerm2-specific.
- zsh — the shell snippet relies on zsh-only features.
- Python 3 — the plugin script runs via the system `python3`.

## Repository layout

| Path | What |
|:---|:---|
| `bin/beacon-iterm` | Stateless CLI that translates subcommands to iTerm2 OSC sequences (D2) |
| `scripts/beacon` | Plugin script — hook handlers, COR resolver, slash command, install (D3) |
| `shell/beacon.zsh` | Sourceable zsh snippet — refreshes project / branch / cwd / URL on every prompt |
| `hooks/`, `commands/`, `skills/` | Claude Code plugin glue |
| `iterm/profile.json.template` | Beacon dynamic profile, including the status-bar layout |
| `docs/` | Docsify site sources; `spec.md` is the EARS-style behavioral spec (D1) |

## Architecture

beacon ships as three deliverables with a hard boundary between them:

| ID | What | Form |
|:---|:---|:---|
| D1 | Behavioral spec | [docs/spec.md](docs/spec.md) |
| D2 | `beacon-iterm` CLI | Stateless OSC-emitter executable |
| D3 | `beacon` Claude Code plugin | Hooks, slash command, skill, COR resolver, shell integration |

D3 invokes D2 for every iTerm2 surface change. D2 has no Claude awareness — it can be used from any caller, which keeps the seam clean for future render-target CLIs (`beacon-tmux`, a web dashboard) or driver plugins.

The behavioral contract for hooks vs shell is documented in [`CLAUDE.md`](CLAUDE.md): the plugin owns `status` (and its optional description) and writes to its user-var slots; the shell owns `project`/`branch`/`cwd`/`url` and writes to disjoint slots; the CLI is unaware of either.

## License

MIT. See [LICENSE](LICENSE).

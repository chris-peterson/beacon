# beacon

At-a-glance session awareness for Claude Code in iTerm2.

beacon shows what each Claude Code session is doing without you having to focus on it. Two surfaces in every iTerm2 pane:

- **Badge** (always on) — project name (e.g. `acme/widgets`, or `ac/auth-svc` after applying an alias) plus a status-driven color: green when idle, amber when Claude is working, red when waiting on you or paused. The badge is large enough to read in Mission Control / Exposé, so a glance across many windows tells you which sessions need attention.
- **Status bar** (in the beacon profile) — a fixed-layout strip grouped as remote-context on the left and local-context on the right: `project_url · ↗ · branch │ cwd · code · {}`. The branch chip is colored by remote-relative state (green when synced, orange when ahead/behind, with `↑N↓M` indicators inline). The `↗` button opens the resolved URL (a CR/PR/issue if [tack](https://github.com/chris-peterson/tack) is on `$PATH` and matches the branch, otherwise a branch URL or the project URL); the `code` button opens the cwd in VS Code; the `{}` button copies a JSON block of the session state to the clipboard for sharing.

Plus a third surface only during pause:

- **Post-it overlay** — a yellow sticky-note bg image carrying your free-text note (`/beacon pause "leaving for lunch"`). Clears automatically when you send the next prompt. Distinguishes "paused" from "waiting" — both share the red badge color, but only pause paints the overlay.

beacon explicitly does **not** touch tab color, terminal background, foreground, window title, or cursor — those are Claude Code's domain or the user's profile. The badge color is the only signal-coloring surface beacon paints.

beacon ships as a Claude Code plugin plus a sourceable zsh snippet. The plugin owns `stage` (workflow phase: `plan`/`dev`/`review`/`shipping`) and `status` (activity: `idle`/`working`/`waiting`); the shell owns `project`, `branch`, and the local cwd. They write to disjoint iTerm2 user-variable slots and never fight.

### Stage vs status

| | Stage | Status |
|:---|:---|:---|
| Question | What kind of work? | What's happening right now? |
| Pace | Minutes-to-hours | Sub-second-to-seconds |
| Driven by | Skill (`plan`, `review`) + hooks (`dev`, `shipping`) + override | Hooks (`working`, `waiting`) + override |

---

## Install

```text
/plugin marketplace add chris-peterson/claude-marketplace
/plugin install beacon@chris-peterson/claude-marketplace
/beacon install
```

The first two commands install the Claude plugin (hooks, slash command, skill, scripts). `/beacon install` then bootstraps everything around it:

- appends a `source` line to `~/.zshrc` (idempotent, marked with a sentinel so upgrades replace it in place)
- installs zsh tab completion to `~/.zsh/completions/_beacon` and inserts `fpath` before your existing `compinit`
- enables iTerm2's *Separate background images per pane* default so the post-it scopes to the active pane
- pre-approves the post-it bg-image paths in iTerm2's `AlwaysAllowBackgroundImage` (no trust prompts at runtime)
- writes a beacon dynamic profile with the fixed-layout status bar

The badge works in any iTerm2 profile. The **status bar** shows up only when you switch to the *Claude Code - Beacon* profile (Profiles menu → "Claude Code - Beacon"); set it as default if you want it everywhere.

After install, open a fresh iTerm2 tab (`⌘T`). The badge should immediately show your current project name; switch to the beacon profile to see the full chip row.

## Verify

In a fresh tab:

```bash
beacon show         # resolved project / task / stage / status with providers
beacon <TAB>        # twelve+ subcommands with descriptions
```

Then run `claude` in that tab and type any prompt:

- the badge color flips to amber while Claude is processing, red when it stops waiting on you
- stage transitions (`dev` on any Write/Edit, `plan` on plan-mode entry, `review`, `shipping` on deploy commands) are tracked internally and surfaced in `beacon show` and the `export` JSON
- `/beacon pause "checking lunch options"` paints a yellow post-it (and the badge goes red); sending the next prompt clears both

## Usage

### Slash command (inside Claude Code)

```text
/beacon                                    # show resolved state (default)
/beacon pause "leaving for lunch"
/beacon resume
/beacon set stage review                   # explicit override
/beacon clear stage                        # remove a single override
/beacon clear                              # remove all overrides
/beacon reset                              # clear all per-session state
/beacon alias acmecorp ac                  # shorten a project segment
/beacon alias                              # list aliases
/beacon alias clear acmecorp               # remove one
/beacon copy-status                        # print shareable session block
```

### Shell command (outside Claude Code)

The same subcommands work at the shell with tab completion:

```bash
beacon show
beacon stage plan
beacon pause "afk"
beacon alias dotnet dn
```

The skill bundled with the plugin tells Claude to set `stage plan` on plan-mode entry and `stage review` when you ask for a code review or QA pass — both are events hooks can't see. Hooks own `dev` (any Write/Edit), `shipping` (deploy commands), and all status transitions.

### Project aliases

Project names default to `<top-group>/<repo>` from the git remote (intermediate subgroups are dropped). For very long org names you can register a short form once:

```bash
beacon alias acmecorp ac
# Project at git.example/acmecorp/platform/auth-svc.git
#   PROV-01 drops 'platform' (intermediate subgroup):  acmecorp/auth-svc
#   ALIAS-02 substitutes 'acmecorp' → 'ac':            ac/auth-svc
```

Aliases are global (shared across all sessions) and persist across upgrades.

## Upgrade

```text
/plugin update beacon
/beacon install
```

The second step is required because plugin upgrades change the version-pinned cache path. The installer detects the prior `source` line by sentinel and rewrites it to the new path; everything else is already idempotent.

## Uninstall

```text
/plugin uninstall beacon
```

To fully clean up the shell side, also delete these from `~/.zshrc`:

```zsh
fpath=(~/.zsh/completions $fpath)         # only if no other tool relies on it
source ".../beacon/shell/beacon.zsh"  # beacon: project · branch · stage badging
```

And `rm ~/.zsh/completions/_beacon`.

## Develop / install from a clone

Working on beacon directly (no marketplace):

```bash
git clone https://github.com/chris-peterson/beacon ~/src/beacon
python3 ~/src/beacon/scripts/beacon install
```

This wires up the shell side just like `/beacon install`, but pointed at your clone. To get the plugin side (slash command, hooks, skill) loaded into Claude Code, use the marketplace install path — `claude --plugin-dir` may not register hooks reliably across versions.

## Design

Requirements (EARS) and architecture in [docs/spec.md](docs/spec.md). beacon ships as three deliverables:

| ID | What | Form |
|:---|:---|:---|
| D1 | This specification | `docs/spec.md` |
| D2 | `beacon-iterm` CLI | A stateless executable that emits iTerm2 escape sequences |
| D3 | `beacon` Claude Code plugin | Hooks, slash command, skill, COR resolver, shell integration |

D3 invokes D2 for every iTerm2 surface change. D2 has no Claude awareness — it can be used from any caller, which keeps the seam clean for future render-target CLIs (`beacon-tmux`, etc.) or driver plugins.

## License

MIT. See [LICENSE](LICENSE).

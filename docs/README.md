# <img src="favicon.svg" alt="beacon" width="64" height="64" style="vertical-align: middle"> beacon

At-a-glance session awareness for Claude Code in iTerm2.

beacon shows what each Claude Code session is doing without you having to focus on it. Two surfaces in every iTerm2 pane:

- **Badge** (always on) — project name plus a status-driven color: green when idle, amber when Claude is working, red when waiting on you or paused. The badge stays readable in Mission Control / Exposé, so a glance across many windows tells you which sessions need attention.
- **Status bar** (in the beacon profile) — a fixed-layout strip with `↖ web` + project identity flush left, branch + `↗ code` flush right: `↖ web · project │ branch · ↗ code`. The project chip abbreviates known forge hosts (`gh:acme/widgets`, `gl:acmecorp/platform/auth-svc`) and appends `#42` / `!17` when the resolved URL points at a deliverable. The `↖ web` button opens the resolved URL (a CR/PR/issue if [tack](https://github.com/chris-peterson/tack) is on `$PATH` and matches the branch — see [Tack integration](#tack-integration-optional) — otherwise a branch URL or the project URL); the `↗ code` button opens the cwd in VS Code.

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

## Verify

In a fresh tab:

```bash
beacon show         # resolved project / task / stage / status with providers
beacon <TAB>        # subcommands with descriptions
```

Then run `claude` in that tab and type any prompt:

- the badge color flips to amber while Claude is processing, back to green when the turn ends; it goes red only while Claude is actively blocked on you (permission/idle prompt)
- stage transitions (`dev` on any Write/Edit, `plan` on plan-mode entry, `review`, `shipping` on deploy commands) are tracked internally and surfaced in `beacon show`
- `/beacon pause "checking lunch options"` paints a yellow post-it and flips the badge to gray; sending the next prompt clears both

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

## Tack integration (optional)

beacon has a soft dependency on [tack](https://github.com/chris-peterson/tack), a CLI for tracking AI-assisted development work. When `tack` is on `$PATH`, beacon asks it for the URL most relevant to the current branch and surfaces that URL in two places:

- The `↖ web` button opens it instead of the bare project URL.
- The project chip appends `#42` (issue/PR) or `!17` (GitLab MR) when the URL is a forge deliverable — `gh:owner/repo#42` instead of just `gh:owner/repo`.

The dependency is **soft**: if tack isn't installed (or has nothing for the current branch), beacon falls through to a branch URL or the bare project URL. No configuration either way.

Prefer Linear, Jira, GitHub Issues, or a custom provider? Override `_beacon_resolve_url()` in your `.zshrc` after sourcing `beacon.zsh`. The function returns a `<url>\t<label>` line and slots into PROV-07 step 2; see [PROV-07](/spec) and [BADGE-08](/spec) for the full contract.

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

To fully clean up the shell side, also delete these from `~/.zshrc`:

```zsh
fpath=(~/.zsh/completions $fpath)         # only if no other tool relies on it
source ".../beacon/shell/beacon.zsh"      # beacon: project · branch · stage badging
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

# <img src="favicon.svg" alt="beacon" width="64" height="64" style="vertical-align: middle"> beacon

At-a-glance session awareness for Claude Code in iTerm2.

beacon shows what each Claude Code session is doing without you having to focus on it. Two surfaces in every iTerm2 pane:

- **Badge** (always on) — project name, optionally followed by `: <task>` when a task is set, plus a status-driven color: green when idle, amber when Claude is working, red when waiting on you or paused. The badge stays readable in Mission Control / Exposé, so a glance across many windows tells you which sessions need attention.
- **Status bar** (in the beacon profile) — a fixed-layout strip with `↖ web` + project identity flush left, branch + `↗ code` flush right: `↖ web · project │ branch · ↗ code`. The project chip abbreviates known forge hosts (`gh:acme/widgets`, `gl:acmecorp/platform/auth-svc`) and appends `#42` / `!17` when the resolved URL points at a deliverable. The `↖ web` button opens the resolved URL — a CR/PR/issue when [tack](https://github.com/chris-peterson/tack) is on `$PATH` and matches the branch, or when `gh`/`glab` finds an open PR/MR for the current branch (see [Tack integration](#tack-integration-optional)) — otherwise a branch URL or the project URL; the `↗ code` button opens the cwd in VS Code.

Plus a third surface only during pause:

- **Pause overlay** — a Dracula-themed marginalia card anchored to the right edge of the pane, carrying your free-text note (`/beacon pause "leaving for lunch"`). Multi-line notes treat the first line as a heading; `*` toggles bold and `_` toggles italic (any quantity of marker works). The badge color flips to a de-emphasized gray; together they distinguish paused from waiting (red).

> [!TIP]
> Read the full behavioral spec on the [Specification](/spec) page.

## Install

```bash
claude plugin marketplace add chris-peterson/claude-marketplace
claude plugin install beacon@chris-peterson
```

Then, inside a Claude Code session, bootstrap everything around the plugin:

```text
/beacon install
```

The first two commands install the Claude plugin (hooks, slash command, skill, scripts). `/beacon install` then bootstraps everything around it: shell `source` line, zsh tab completion, the iTerm2 dynamic profile, `PerPaneBackgroundImage`, and pause-overlay bg-image trust pre-approval.

Some prefs (default profile, bg-image trust pre-approval) only stick when iTerm2 is fully quit. If `install` reports those steps as DEFERRED, run `beacon exclusive-configuration` — it confirms before quitting iTerm2, applies the writes, and relaunches.

## Verify

In a fresh tab:

```bash
beacon show         # resolved project / task / status (with description if set)
beacon <TAB>        # subcommands with descriptions
```

Then run `claude` in that tab and type any prompt:

- the badge color flips to amber while Claude is processing, back to green when the turn ends; it goes red with a `!` watermark when Claude is hard-blocked on a permission prompt, or red with a `?` for the softer idle prompt
- `/beacon pause "checking lunch options"` flips the badge to gray and pins a marginalia card to the right edge of the pane carrying the note; sending the next prompt clears both
- `/beacon status waiting "bg refresh ~30 min"` flips the badge to red and pins the same marginalia card with your description — useful when *you* are waiting on something async, not Claude

## Usage

Inside Claude Code:

```text
/beacon                                    # show resolved state (default)
/beacon status waiting "bg refresh"        # set status with a description
/beacon pause "leaving for lunch"          # shorthand for `status paused …`
/beacon resume                             # clear all overrides + description
/beacon clear status                       # clear just the status override
```

At the shell:

```bash
beacon show
beacon status paused "afk"
beacon pause "afk"
```

## Tack integration (optional)

beacon has a soft dependency on [tack](https://github.com/chris-peterson/tack), a CLI for tracking AI-assisted development work. When `tack` is on `$PATH`, beacon asks it for the URL most relevant to the current branch and surfaces that URL in two places:

- The `↖ web` button opens it instead of the bare project URL.
- The project chip appends `#42` (issue/PR) or `!17` (GitLab MR) when the URL is a forge deliverable — `gh:owner/repo#42` instead of just `gh:owner/repo`.

The dependency is **soft**: if tack isn't installed or has nothing for the current branch, beacon probes the forge directly — `gh pr list --head <branch>` on github hosts, `glab mr list --source-branch <branch>` on gitlab hosts — and uses the first open PR/MR it finds. This catches the common case where you've pushed an MR but never ran `tack link add`. If the forge has nothing either (or neither CLI is installed), beacon falls through to a branch URL or the bare project URL. No configuration on any path.

Prefer Linear, Jira, GitHub Issues, or a custom provider? Override `_beacon_resolve_url()` in your `.zshrc` after sourcing `beacon.zsh`. The function returns a `<url>\t<label>` line and slots into PROV-07; see [PROV-07](/spec) and [BADGE-08](/spec) for the full contract.

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

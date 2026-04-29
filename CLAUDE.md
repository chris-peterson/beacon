# CLAUDE.md

Notes for AI coding agents working on beacon. Behavioral spec is [docs/spec.md](./docs/spec.md); user-facing docs are [README.md](./README.md). When the spec and the code disagree, ask — don't silently choose one.

## What beacon is

A Claude Code plugin + sourceable zsh snippet + standalone CLI that surfaces session state on iTerm2 surfaces (badge, status bar, post-it overlay during pause) so the user can scan many concurrent panes without focusing each one.

## Three deliverables, hard boundaries

| Deliverable | Path | Owns |
|:---|:---|:---|
| **CLI** | `bin/beacon-iterm` | Translating subcommands to iTerm2 OSC sequences. **Stateless.** No Claude awareness. |
| **Plugin** | `scripts/beacon`, `hooks/`, `commands/`, `skills/` | Hook handlers, COR resolver for signals, slash command. Invokes the CLI for every iTerm2 write. |
| **Shell** | `shell/beacon.zsh` | Project / branch / cwd / URL — refreshed every prompt. Calls the CLI directly; never goes through the plugin. |

The plugin and shell write to **disjoint user-var slots** so they never overwrite each other. Don't blur this boundary.

The CLI must remain unaware of Claude — it's usable from CI, ad-hoc terminal scripts, or future drivers (e.g., a tmux variant). Don't import plugin state into it.

## Hot paths — keep fast

- `apply()` in `scripts/beacon` — runs on every Claude Code hook. Diff against the resolved-state snapshot before invoking the CLI.
- `_beacon_precmd` in `shell/beacon.zsh` — runs on every prompt redraw. Last-value sentinels gate every CLI call.
- Critical OSC sequences in `shell/beacon.zsh` (badge format, bg-image clear) are emitted via raw `printf` to `/dev/tty`, bypassing python startup.

## Surfaces beacon paints

Per docs/spec.md §4.1 — these and only these:

- **Badge** — text (project) + color (status-driven traffic light: ready / busy / blocked)
- **Status bar** — the beacon dynamic profile only (never the user's profile)
- **Background image** — only during pause, for the post-it overlay
- **Tab color** — mirrors the badge color (same logical state) on the tab strip; intended for tabs-not-panes workflows

beacon does **not** paint: terminal bg/fg, window title, tab title, cursor color/shape. These belong to Claude Code, the user's profile, or other tools. Adding to this list is a spec change, not an implementation choice.

## Logical states are the contract

Status maps to a logical color state (`ready` / `busy` / `blocked`) which then maps to hex. Two-step indirection is intentional — call sites speak in logical names so the palette can be tuned in one place. See `BADGE_COLOR_PALETTE` and `STATUS_TO_BADGE_STATE` in `scripts/beacon`.

## State and cache locations

`DATA_DIR` resolves to `$CLAUDE_PLUGIN_DATA` when set (Claude Code provides it for hook invocations). For slash commands and the shell alias the env var is unset, so the script derives the same path from `CLAUDE_PLUGIN_ROOT` matching Claude Code's `<plugin>-<owner>` convention (e.g. `~/.claude/plugins/data/beacon-chris-peterson/`). All three invocation contexts must land on the same dir or hooks see no state to act on.

- Per-session state: `<DATA_DIR>/state/<session-hash>.<field>` — fields include `paused`, `pending-attention` (sticky permission marker), `note-image`, `override.*`, `signal.*`, `resolved`, `claude_session_id`.
- Note image pool (LRU, fixed N=8): `<DATA_DIR>/cache/note-NN.png`
- Per-session shell handoff files (read by status-bar action buttons): `<DATA_DIR>/cache/{url,cwd}-$ITERM_SESSION_ID.txt`

Session hash is SHA-1 of `$ITERM_SESSION_ID` truncated; collisions are not a security concern.

## iTerm2 preference-cache trap

iTerm2 caches its plist in memory while running and writes it back on quit. Any `defaults write com.googlecode.iterm2 ...` while iTerm2 is running gets clobbered when iTerm2 next quits. Three places this matters:

- `PerPaneBackgroundImage` and `AlwaysAllowBackgroundImage` writes — `_pre_approve_iterm_paths()` defers when iTerm2 is running, telling the user to quit + re-run.
- `Default Bookmark Guid` and `AlwaysAllowBackgroundImage` — `cmd_exclusive_configuration` orchestrates a quit + relaunch via a detached `nohup` helper that re-invokes the script after iTerm2 exits, so all writes that need an iTerm2-dead window happen in one pass. **`install` does NOT trigger this orchestration** — it'd quietly close the user's only terminal. Install instead emits a deferred-action notice pointing the user at `beacon exclusive-configuration`.
- The dynamic profile JSON in `DynamicProfiles/` works fine while running; iTerm2 watches the directory.

## Conventions

- **No fallbacks.** Don't add a "simple alternative" path inside a try/except around the real logic. Let primary failures surface. (`_cli()` is an exception — it deliberately swallows errors so a bad CLI invocation can't crash a hook.)
- **No comments explaining WHAT.** Good identifiers do that. Comments capture WHY: hidden constraints, subtle invariants, workarounds. Re-read existing code comments before adding new ones — most explain non-obvious WHYs and should be kept.
- **No backwards-compat hacks.** beacon is pre-1.0; rename, delete, restructure freely.
- **No symlinks.** If you think you need one, stop and ask.
- **Imperative commit subjects, ≤50 chars** ([cbea.ms style](https://cbea.ms/git-commit/)).

## Running things

| Task | Command |
|:---|:---|
| Run plugin once | `python3 scripts/beacon <subcommand>` |
| Bootstrap install | `python3 scripts/beacon install` |
| Apply prefs needing iTerm2 quit (default profile, bg-image trust) | `python3 scripts/beacon exclusive-configuration` |
| Reload shell integration | `exec zsh` |
| Smoke test the CLI | `python3 bin/beacon-iterm <subcommand>` (writes OSC to `/dev/tty`) |

There is no test suite yet. Verify behavior by sourcing the shell snippet, running the CLI, and visually confirming in iTerm2.

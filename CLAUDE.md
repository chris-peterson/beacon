# CLAUDE.md

Notes for AI coding agents working on beacon. Behavioral spec is [docs/spec.md](./docs/spec.md); user-facing docs are [README.md](./README.md). When the spec and the code disagree, ask — don't silently choose one.

## What beacon is

A Claude Code plugin + sourceable zsh snippet + standalone CLI that surfaces session state two ways: a **terminal-agnostic fleet view** (`wip` / `watch` / `serve`, optionally kept always-on via `beacon service`) that reads across all sessions and paints no pane, and an **iTerm2 per-pane render adapter** (badge, status bar, pause overlay) for scanning concurrent panes without focusing each. Both read the same per-session state files — the single source of record; neither inverts that into a daemon. The fleet view works in any terminal; the iTerm2 adapter needs macOS + iTerm2.

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
- **Background image** — the marginalia card overlay, painted whenever the session has a non-empty `description` (any user-set status, not just paused)
- **Tab color** — mirrors the badge color (same logical state) on the tab strip; intended for tabs-not-panes workflows

beacon does **not** paint: terminal bg/fg, window title, tab title, cursor color/shape. These belong to Claude Code, the user's profile, or other tools. Adding to this list is a spec change, not an implementation choice.

beacon profiles also explicitly **disable** iTerm2's notification-center delivery (`BM Growl: false`) and terminal-generated alerts (`Send Terminal Generated Alerts: false`). Claude Code triggers these on permission prompts and idle prompts, but beacon already surfaces both via badge color + watermark — duplicate notifications add no signal and can transiently overlay the badge.

## Logical states are the contract

Status maps to a logical color state (`ready` / `busy` / `blocked`) which then maps to hex. Two-step indirection is intentional — call sites speak in logical names so the palette can be tuned in one place. See `BADGE_COLOR_PALETTE` and `STATUS_TO_BADGE_STATE` in `scripts/beacon`.

## State and cache locations

`DATA_DIR` resolves to `$CLAUDE_PLUGIN_DATA` when set (Claude Code provides it for hook invocations). For slash commands and the `~/.local/bin/beacon` wrapper the env var is unset, so the script derives the same path from `CLAUDE_PLUGIN_ROOT` matching Claude Code's `<plugin>-<owner>` convention (e.g. `~/.claude/plugins/data/beacon-chris-peterson/`). All three invocation contexts must land on the same dir or hooks see no state to act on.

- Per-session state: `<DATA_DIR>/state/<session-hash>.<field>` — fields include `description` (user-supplied marginalia text), `note-image` (rendered PNG path), `pending-attention` (sticky permission marker), `override.*`, `signal.status`, `resolved`, `claude_session_id`, `anchor.cwd` / `anchor.project` (SessionStart navigational anchor; Stop re-resolves chips from `anchor.cwd` per HOOK-08/08b).
- Note image pool (LRU, fixed N=8): `<DATA_DIR>/cache/note-NN.png`
- Per-session shell handoff files (read by status-bar action buttons): `<DATA_DIR>/cache/{url,cwd}-$ITERM_SESSION_ID.txt`
- Always-on serve service logs (launchd `StandardOut/ErrorPath`): `<DATA_DIR>/logs/serve.{out,err}.log`

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
| List active work streams across all sessions (last 24h) | `python3 scripts/beacon wip [--json] [--since 1d] [--all]` |
| Serve the wip snapshot for the goals dashboard | `python3 scripts/beacon serve [--port 8787]` |
| Manage the always-on serve service (launchd/systemd) | `python3 scripts/beacon service <install\|uninstall\|status>` |
| GC per-session state for long-idle panes | `python3 scripts/beacon prune [--since 30d]` |
| Reload shell integration | `exec zsh` |
| Smoke test the CLI | `python3 bin/beacon-iterm <subcommand>` (writes OSC to `/dev/tty`) |
| Run unit tests | `just test` (loads `scripts/beacon` via importlib, mocks `_cli`) |

The test suite under `tests/` covers plugin-side behavior (apply/render emit decisions, override propagation). Surface verification (the actual badge / status bar / overlay rendering in iTerm2) still requires sourcing the shell snippet and looking.

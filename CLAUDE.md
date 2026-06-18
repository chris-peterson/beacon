# CLAUDE.md

Notes for AI coding agents working on beacon. Behavioral spec is [docs/spec.md](./docs/spec.md); user-facing docs are [README.md](./README.md). When the spec and the code disagree, ask — don't silently choose one.

## What beacon is

A Claude Code plugin + sourceable zsh snippet + standalone CLI that surfaces session state two ways: a **terminal-agnostic fleet view** (`wip` / `watch` / `serve`, optionally kept always-on via `beacon serve install`) that reads across all sessions and paints no pane, and an **iTerm2 per-pane render adapter** (badge, status bar, tab color) for scanning concurrent panes without focusing each. Clicking a session in the dashboard raises its iTerm2 window (serve's `POST /focus` → `beacon-iterm focus`). Both read the same per-session state files — the single source of record; neither inverts that into a daemon. The fleet view works in any terminal; the iTerm2 adapter needs macOS + iTerm2.

## Three deliverables, hard boundaries

| Deliverable | Path | Owns |
|:---|:---|:---|
| **CLI** | `bin/beacon-iterm` | Translating subcommands to iTerm2 control operations — OSC sequences for painted surfaces, Apple Events (`focus`) to raise a window. **Stateless.** No Claude awareness. |
| **Plugin** | `scripts/beacon`, `hooks/`, `commands/`, `skills/`, `rules/` | Hook handlers, COR resolver for signals, slash command. `rules/` holds ambient rules emitted at SessionStart by `hooks/emit-rules.sh` (e.g. `keep-session-labeled` — proactive task upkeep so the fleet view has signal standalone). Invokes the CLI for every iTerm2 write. |
| **Shell** | `shell/beacon.zsh` | Project / branch / cwd / URL — refreshed every prompt. Calls the CLI directly; never goes through the plugin. |

The plugin and shell write to **disjoint user-var slots** so they never overwrite each other. Don't blur this boundary.

The CLI must remain unaware of Claude — it's usable from CI, ad-hoc terminal scripts, or future drivers (e.g., a tmux variant). Don't import plugin state into it.

## Hot paths — keep fast

- `apply()` in `scripts/beacon` — runs on every Claude Code hook. Diff against the resolved-state snapshot before invoking the CLI.
- `_beacon_precmd` in `shell/beacon.zsh` — runs on every prompt redraw. Last-value sentinels gate every CLI call.
- Critical OSC sequences in `shell/beacon.zsh` (profile activation, badge format) are emitted via raw `printf` to `/dev/tty`, bypassing python startup.

## Surfaces beacon paints

Per docs/spec.md §4.1 — these and only these:

- **Badge** — text (project) + color (status-driven traffic light: ready / busy / blocked), set via OSC on top of the single base profile
- **Status bar** — the beacon dynamic profile only (never the user's profile)
- **Tab color** — mirrors the badge color (same logical state) on the tab strip; intended for tabs-not-panes workflows

The session `description` is no longer painted on the pane — it surfaces in the fleet view (`wip` / `watch` / dashboard) as recall context.

beacon does **not** paint: terminal bg/fg, background image, window title, tab title, cursor color/shape. These belong to Claude Code, the user's profile, or other tools. Adding to this list is a spec change, not an implementation choice.

beacon profiles also explicitly **disable** iTerm2's notification-center delivery (`BM Growl: false`) and terminal-generated alerts (`Send Terminal Generated Alerts: false`). Claude Code triggers these on permission prompts and idle prompts, but beacon already surfaces both via badge color — duplicate notifications add no signal and can transiently overlay the badge.

## Logical states are the contract

Status maps to a logical color state (`ready` / `busy` / `blocked`) which then maps to hex. Two-step indirection is intentional — call sites speak in logical names so the palette can be tuned in one place. See `BADGE_COLOR_PALETTE` and `STATUS_TO_BADGE_STATE` in `scripts/beacon`.

## State and cache locations

`DATA_DIR` resolves to `$CLAUDE_PLUGIN_DATA` when set (Claude Code provides it for hook invocations). For slash commands and the `~/.local/bin/beacon` wrapper the env var is unset, so the script derives the same path from `CLAUDE_PLUGIN_ROOT` matching Claude Code's `<plugin>-<owner>` convention (e.g. `~/.claude/plugins/data/beacon-chris-peterson/`). All three invocation contexts must land on the same dir or hooks see no state to act on.

- Per-session state: `<DATA_DIR>/state/<session-hash>.<field>` — fields include `description` (user-supplied recall note, surfaced in the fleet view), `iterm_session_id` (the iTerm2 GUID focus handle, FOCUS-02), `pending-attention` (sticky attention marker), `override.*`, `signal.status`, `resolved`, `claude_session_id`, `anchor.cwd` / `anchor.project` (SessionStart navigational anchor; Stop re-resolves chips from `anchor.cwd` per HOOK-08/08b).
- Per-session shell handoff files (read by status-bar action buttons): `<DATA_DIR>/cache/{url,cwd}-$ITERM_SESSION_ID.txt`
- Always-on serve service logs (launchd `StandardOut/ErrorPath`): `<DATA_DIR>/logs/serve.{out,err}.log`

Session hash is SHA-1 (truncated) of the session seed: `$ITERM_SESSION_ID` on iTerm2, else `claude-session:$CLAUDE_CODE_SESSION_ID` (the id Claude Code sets in every in-session subprocess on any OS, so a bare `beacon set` on Windows/non-iTerm lands in the same bucket as its hooks), else the tty name, else `default`. See `_session_seed()`. Collisions are not a security concern.

## No iTerm2 prefs written — profile activated at runtime

beacon makes **no** `defaults write com.googlecode.iterm2 ...` and is not iTerm2's default profile, so it sidesteps the plist-cache trap entirely (iTerm2 caches prefs in memory and clobbers any `defaults write` on quit). Instead:

- The base `beacon` dynamic profile lives in `DynamicProfiles/`; iTerm2 watches the directory and reloads it live, so `install` needs no iTerm2 restart.
- Each session is switched *into* that profile at runtime via `set-profile` (OSC `SetProfile=`): the plugin at SessionStart, the shell snippet on source. Badge/tab color then layer on via OSC `SetColors=` — there are no per-state profiles.
- Because nothing requires an iTerm2-dead window, there is no `exclusive-configuration` command and no deferred-action install step.

## Session focus (FOCUS)

Clicking a session in the dashboard raises its iTerm2 window. The chain: dashboard `POST /focus {hash}` → `serve` resolves `hash` → the recorded `iterm_session_id` GUID **server-side** (the GUID never reaches the browser) → `beacon-iterm focus <guid>`. The CLI's osascript **captures the target with no side effects, then** selects session→tab→window→activate — selecting mid-enumeration reorders iTerm2's window list and throws `Invalid index -1719` on nested splits. The `/focus` route is loopback-only with a Host-header rebind check and an Origin allowlist (FOCUS-04); `GET /wip.json` keeps its permissive CORS. Non-iTerm sessions record no handle and are not focusable (`focusable: false` in the payload).

## Conventions

- **No fallbacks.** Don't add a "simple alternative" path inside a try/except around the real logic. Let primary failures surface. (`_cli()` is an exception — it deliberately swallows errors so a bad CLI invocation can't crash a hook.)
- **No comments explaining WHAT.** Good identifiers do that. Comments capture WHY: hidden constraints, subtle invariants, workarounds. Re-read existing code comments before adding new ones — most explain non-obvious WHYs and should be kept.
- **No backwards-compat hacks.** Rename, delete, restructure freely.
- **No symlinks.** If you think you need one, stop and ask.
- **Imperative commit subjects, ≤50 chars** ([cbea.ms style](https://cbea.ms/git-commit/)).

## Running things

| Task | Command |
|:---|:---|
| Run plugin once | `python3 scripts/beacon <subcommand>` |
| Bootstrap install | `python3 scripts/beacon install` |
| Focus an iTerm2 session window by its id | `python3 bin/beacon-iterm focus <session-id>` |
| List active work streams across all sessions (last 24h) | `python3 scripts/beacon wip [--json] [--since 1d] [--all]` |
| Serve the bundled dashboard (`/`) + wip snapshot (`/wip.json`) | `python3 scripts/beacon serve [--port 8787]` |
| Manage the always-on serve service (launchd/systemd) | `python3 scripts/beacon serve <install\|uninstall\|status>` |
| GC per-session state for long-idle panes | `python3 scripts/beacon prune [--since 30d]` |
| Delete per-session state for one session | `python3 scripts/beacon forget <hash>` |
| Reload shell integration | `exec zsh` |
| Smoke test the CLI | `python3 bin/beacon-iterm <subcommand>` (writes OSC to `/dev/tty`) |
| Run unit tests | `just test` (loads `scripts/beacon` via importlib, mocks `_cli`) |

The test suite under `tests/` covers plugin-side behavior (apply/render emit decisions, override propagation, focus handle + `/focus` route). Surface verification (the actual badge / status bar / tab color rendering, and the focus action, in iTerm2) still requires sourcing the shell snippet and looking.

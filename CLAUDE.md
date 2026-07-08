# CLAUDE.md

Notes for AI coding agents working on beacon. Behavioral spec is [docs/spec.md](./docs/spec.md); user-facing docs are [README.md](./README.md). When the spec and the code disagree, ask — don't silently choose one.

## What beacon is

A Claude Code plugin + sourceable zsh snippet + standalone CLI that surfaces session state two ways: a **terminal-agnostic fleet view** (`wip` / `watch` / `serve`, optionally kept always-on via `beacon serve install`) that reads across all sessions and paints no pane, and an **iTerm2 per-pane render adapter** (badge, status bar, tab color, window title) for scanning concurrent panes without focusing each. Clicking a session in the dashboard raises its iTerm2 window (serve's `POST /focus` → `beacon-iterm focus`). Both read the same per-session state files — the single source of record; neither inverts that into a daemon. The fleet view works in any terminal; the iTerm2 adapter needs macOS + iTerm2.

## Three deliverables, hard boundaries

| Deliverable | Path | Owns |
|:---|:---|:---|
| **CLI** | `bin/beacon-iterm` | Translating subcommands to iTerm2 control operations — OSC sequences for painted surfaces, Apple Events (`focus` to raise a window, `set-name` to set the window title). **Stateless.** No Claude awareness. |
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

- **Badge** — text (raw project; no mode decorates it — no glyphs, BADGE-11) + color (status-driven: the dev cycle's gray / orange / red stoplight — green is retired from it — plus the mode colors paused / release / retro / done), set via OSC on top of the active profile
- **Status bar** — the beacon dynamic profile only (never the user's profile)
- **Tab color** — mirrors the badge color (same logical state) on the tab strip; intended for tabs-not-panes workflows
- **Pane background** — **mode states only** (`paused`, `release`, `retro`, `done`), and only by swapping into that mode's profile (RENDER-05), never an ad-hoc background OSC. Outside a mode, the background is the user's profile's.
- **Window title** — the OS window title carries `project · task` (same template as the badge) so a `/rename`d window keeps its project context in a sea of windows (§4.8, TITLE). Set via the session *name* (not the profile name), through Apple Events (`set-name`); the profile disables OSC title-setting (`Allow Title Setting: false`) so Claude's title OSC can't overwrite it, and shows the name via `Title Components: 1`. The plugin sets it on the first render and re-sets it after each profile swap (which resets the name); iTerm2 re-evaluates the interpolated name as the badge vars change. Interactive (non-Claude) panes get the project alone (`beacon_project_full`), set once by the shell on source (`shell/beacon.zsh`) — the one place the shell calls the CLI via python rather than raw printf, since the session name has no OSC verb.

The session `description` is no longer painted on the pane — it surfaces in the fleet view (`wip` / `watch` / dashboard) as recall context (WIP-12). No state carries a text glyph; a mode reads by its color dot / card treatment.

beacon does **not** paint: terminal fg, tab title, cursor color/shape. Terminal background (color, and a faint image) is the one painted exception, scoped to the mode profile swaps above. The rest belong to Claude Code, the user's profile, or other tools. Adding to this list is a spec change, not an implementation choice. (The **window** title *is* painted, via the session name — see the Window title bullet above and docs/spec.md §4.8; the **tab** title remains a non-goal — see §8.)

beacon profiles also explicitly **disable** iTerm2's notification-center delivery (`BM Growl: false`) and terminal-generated alerts (`Send Terminal Generated Alerts: false`). Claude Code triggers these on permission prompts and idle prompts, but beacon already surfaces both via badge color — duplicate notifications add no signal and can transiently overlay the badge.

## Logical states are the contract

Status maps to a logical color state (`ready` / `busy` / `blocked` — the dev cycle, plus the mode states `paused` / `release` / `retro` / `done`) which then maps to hex. Two-step indirection is intentional — call sites speak in logical names so the palette can be tuned in one place. See `BADGE_COLOR_PALETTE` and `STATUS_TO_BADGE_STATE` in `scripts/beacon`. Mode states additionally map to a dedicated dynamic profile (background) via `MODE_PROFILES` — the same indirection, so call sites never name iTerm profiles.

## State and cache locations

`DATA_DIR` resolves to `$CLAUDE_PLUGIN_DATA` when set (Claude Code provides it for hook invocations). For slash commands and the `~/.local/bin/beacon` wrapper the env var is unset, so the script derives the same path from `CLAUDE_PLUGIN_ROOT` matching Claude Code's `<plugin>-<owner>` convention (e.g. `~/.claude/plugins/data/beacon-chris-peterson/`). All three invocation contexts must land on the same dir or hooks see no state to act on.

- Per-session state: `<DATA_DIR>/state/<session-hash>.<field>` — fields include `description` (user-supplied recall note, surfaced in the fleet view), `latest_turn` (most recent conversation turn `{role,text,at}`, auto-derived at hook time and surfaced in the fleet view per WIP-11), `latest_turn_full` (the same turn's full multi-line text, served on demand at `/turn/<hash>` for card expansion per WIP-14), `cc.custom_title` / `cc.agent_color` / `cc.ai_title` (Claude Code's `/rename`, `/color`, and auto-title, harvested from the transcript tail per PROV-09 — the first and third feed the task chain, the color is fleet-view-only), `iterm_session_id` (the iTerm2 GUID focus handle, FOCUS-02), `pending-attention` (sticky attention marker), `override.*`, `signal.status`, `resolved`, `claude_session_id`, `anchor.cwd` / `anchor.project` (SessionStart navigational anchor; Stop re-resolves chips from `anchor.cwd` per HOOK-08/08b).
- Per-session shell handoff files (read by status-bar action buttons): `<DATA_DIR>/cache/{url,cwd}-$ITERM_SESSION_ID.txt`
- Always-on serve service logs (launchd `StandardOut/ErrorPath`): `<DATA_DIR>/logs/serve.{out,err}.log`

Session hash is SHA-1 (truncated) of the session seed: `$ITERM_SESSION_ID` on iTerm2, else `claude-session:$CLAUDE_CODE_SESSION_ID` (the id Claude Code sets in every in-session subprocess on any OS, so a bare `beacon set` on Windows/non-iTerm lands in the same bucket as its hooks), else the tty name, else `default`. See `_session_seed()`. Collisions are not a security concern.

## No iTerm2 prefs written — profile activated at runtime

beacon makes **no** `defaults write com.googlecode.iterm2 ...` and is not iTerm2's default profile, so it sidesteps the plist-cache trap entirely (iTerm2 caches prefs in memory and clobbers any `defaults write` on quit). Instead:

- The base `beacon-dev` dynamic profile (the dev cycle) and one mode profile per `MODE_PROFILES` entry (`beacon-pause`, `beacon-release`, `beacon-retro`, `beacon-done`) live in `DynamicProfiles/`; iTerm2 watches the directory and reloads them live, so `install` needs no iTerm2 restart. Each mode profile is derived from the base at install time (same layout, distinct background — pause gets a faint `||` background image, release a faint rocket one, done a faint `⏻` power-off one; retro is tint-only) so they never drift.
- Each session is switched *into* the base `beacon-dev` profile at runtime via `set-profile` (OSC `SetProfile=`): the plugin at SessionStart, the shell snippet on source. Badge/tab color then layer on via OSC `SetColors=`. The per-state profiles are the **mode profiles** — a mode state (`paused`, `release`, `retro`, `done`) swaps into its profile for the background change a color OSC can't express (RENDER-05); ready/busy/blocked (dev) stay OSC overlays on the base. The logical-mode → profile mapping lives in `MODE_PROFILES`, so call sites never name iTerm profiles.
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
| Review the whole branch vs the default branch (moor-aware; backs the `⇄ review` status-bar button) | `python3 scripts/beacon review` |
| Manage the always-on serve service (launchd/systemd) | `python3 scripts/beacon serve <install\|uninstall\|status>` |
| GC per-session state for long-idle panes | `python3 scripts/beacon prune [--since 30d]` |
| Delete per-session state for one session | `python3 scripts/beacon forget <hash>` |
| Reload shell integration | `exec zsh` |
| Smoke test the CLI | `python3 bin/beacon-iterm <subcommand>` (writes OSC to `/dev/tty`) |
| Run unit tests | `just test` (loads `scripts/beacon` via importlib, mocks `_cli`) |

The test suite under `tests/` covers plugin-side behavior (apply/render emit decisions, override propagation, focus handle + `/focus` route). Surface verification (the actual badge / status bar / tab color rendering, and the focus action, in iTerm2) still requires sourcing the shell snippet and looking.

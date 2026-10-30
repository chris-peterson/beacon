# beacon

Notes for AI coding agents working on beacon. What beacon does, requirement by requirement, is [SPEC.md](./SPEC.md) (published to the docs site as `/spec`); user-facing docs are [README.md](./README.md). This file holds what the spec doesn't: the boundaries, hot paths, and traps that shape the code. Cite a requirement id (`STATUSLINE-03`) rather than restating it here. When the spec and the code disagree, ask; don't silently choose one.

## What beacon is

A Claude Code plugin, a sourceable zsh snippet, and a standalone CLI that surface session state two ways: a terminal-agnostic **sessions view** (`wip` / `watch` / `serve`) that reads across all sessions, and an **iTerm2 render adapter** that paints each pane. Both read the same per-session state files, the single source of record; neither inverts that into a daemon. See SPEC §1–2.

## Three deliverables, hard boundaries

| Deliverable | Path | Owns |
|:---|:---|:---|
| **CLI** | `bin/beacon-iterm` | Translating subcommands to iTerm2 control operations: OSC sequences for painted surfaces, Apple Events (`focus` to raise a window, `set-name` to set the window title). **Stateless.** No Claude awareness. |
| **Plugin** | `scripts/beacon`, `hooks/`, `commands/`, `rules/` | Hook handlers, COR resolver for signals, slash command. `rules/` holds ambient rules emitted at SessionStart by `hooks/emit-rules.sh`. Invokes the CLI for every iTerm2 write. |
| **Shell** | `shell/beacon.zsh` | Project name / branch / cwd, refreshed every prompt. Emits its own `SetUserVar` OSC by raw `printf`; calls the CLI for `set-name`. Never goes through the plugin. |

The plugin and shell write to **disjoint user-var slots** so they never overwrite each other. Don't blur this boundary.

The CLI must remain unaware of Claude. It's usable from CI, ad-hoc terminal scripts, or future drivers (a tmux variant). Don't import plugin state into it.

## Hot paths: keep fast

- `apply()` in `scripts/beacon` runs on every Claude Code hook. Diff against the resolved-state snapshot before invoking the CLI.
- `_refresh_branch_chips_if_git` runs on every PostToolUse and is a gate before it is a publisher. The branch slots alone (three local git reads) are what a mid-turn push can afford; `_publish_chips` wholesale cannot, because it calls `resolve_url` (git, possibly `gh`/`glab`) and `_tack_route_urls` (a `tack tree` subprocess). Keep the gate on the git *subcommand*: the bare word `git` would fire on the `status` / `log` / `diff` calls that are most of a session (HOOK-08c).
- `_beacon_precmd` in `shell/beacon.zsh` runs on every prompt redraw and spawns no process of its own. Last-value sentinels gate every emit, one `git for-each-ref` yields every branch value, the origin URL is memoized per project root, and the helpers answer through `_beacon_reply` / `_beacon_binfo` because each `$(...)` is a fork.
- The shell emits every OSC by raw `printf` **to `/dev/tty`**, with `_beacon_b64` as a zsh-native base64, so it costs no fork. Stdout would splice escape bytes into `x=$(cd somedir; …)`, because zsh fires `chpwd` and `precmd` inside command-substitution subshells. `_beacon_b64` encodes to UTF-8 first (the branch display carries `↑`/`↓`) and pins `multibyte` / `noksharrays` for its own scope, as `_beacon_branch_info` and `_beacon_precmd` pin the options their array indexing assumes. The `shell-init` block (CMD-27) is cached so a new terminal usually spawns no python.
- `beacon statusline` renders per prompt, so it reads state and nothing else: never `resolve_url`, never a forge (STATUSLINE-01/02). Forge data reaches it through `refresh-links`, which runs detached and writes `deliverables.links` only, so it can't race a hook over the entries.

## Surfaces

SPEC §4.1 lists the surfaces beacon paints, and only those. Adding one is a spec change, not an implementation choice. The rules call sites have to keep:

- The status bar lives in the beacon dynamic profile, never the user's profile.
- The pane background changes only by swapping profiles, never by an ad-hoc background OSC: into a mode profile (RENDER-05), or, in the dev cycle only, into a block profile (RENDER-07). A declared mode keeps the pane while blocked.
- The window title and tab label go through the session name (`set-name`), not an OSC title or the profile's `Subtitle` (TITLE-05). Disengagement hands the name back *before* blanking the user vars; the other order leaves a blank tab and window title (§4.8, §6.10 caveat 7).
- A status-bar button's `cmd` is read on the click, but its `label` is baked into the profile, so a label change needs `beacon refresh-iterm-profiles` (STATUS-BAR-09, CMD-23). Buttons run through an absolute interpreter path because an action shell has no interactive `PATH` (STATUS-BAR-07).
- The badge is opt-in and gated at three paint sites: the profile's `Badge Text`, the plugin render, and the shell's `shell-init` block (BADGE-15). Change all three together.
- The tab paints the activity hue through `_tab_hex`'s per-state weights (TAB-04). The badge and the sessions view take `COLOR_PALETTE` directly, since a weight tuned for a full-bleed tab erases a 10px dot.

## The axes are the contract

The axes resolve independently, each owning its own surfaces (SPEC §1.3). No call site arbitrates between mode and activity, and none names a hex, a glyph, or an iTerm profile directly:

| Axis | Written by | Maps through | To |
|:---|:---|:---|:---|
| `activity` | hooks only, several times a turn | `ACTIVITY_TO_COLOR_STATE` → `COLOR_PALETTE` | tab (and badge) color |
| `mode` | declared by a user or skill | `MODE_SPECS` | tab / window-title glyph |
| | | `MODE_SPECS` | dynamic profile + pane background + watermark |
| `permission` | hooks only, from the payload's `permission_mode` | `_is_planning` | the sessions view only, **no terminal surface** (PERM-02) |

The indirection through a logical name (`idle` / `working` / `blocked`) is the contract, so the palette retunes in one place. Don't reintroduce a precedence rule between mode and activity; the design is that they don't need one.

## How beacon reaches tack

Two questions, two mechanisms, and neither reads tack's storage:

| Question | Answered by |
|:---|:---|
| which route is this session working, and which tacks | `codes.bridgeai.tack/session.started` and `session.ended`, recorded as `announced.route` |
| what is currently true of that route | `tack tree <slug> --json`, memoized per route per process (`_route_doc_for`) |

An announcement holds identity only (the slug, the tack ids), since it states a fact at a moment and everything else about a tack is mutable. It is tack's payload to design, not beacon's.

The dependency is optional: no announcement means no slug, so the `_which("tack")` probe is never reached.

**Don't reintroduce correlation.** Scanning `$TACK_HOME/routes/*.yaml`, or guessing a route from a `.tack` pin file, the branch, or the project name, parses a schema tack is free to change and guesses wrong on any slug that matches none of them. `tack tree` is grammar tack publishes in its own `spec/cli.yml`.

## State

The layout is SPEC §6.2, and each field is defined by the requirement that writes it. The traps:

- **One `DATA_DIR` for every caller.** Hooks get `$CLAUDE_PLUGIN_DATA`. Slash commands, the `~/.local/bin/beacon` wrapper, and the serve service don't, so they read the dir the last hook recorded at `~/.config/beacon/data-dir`. Claude Code buckets an inline plugin as `<plugin>-inline` and a marketplace install as `<plugin>-<marketplace>`, and a caller that lands on the other one writes state nothing reads.
- **The session seed is the pane GUID**, the segment of `$ITERM_SESSION_ID` after the last colon. The full id's `wNtNpN` prefix drifts when a pane moves. A nested `claude` inherits its parent's pane id, so a SessionStart that finds the pane held takes a `claude-session:` seed instead (HOOK-12, `_session_seed()`). Per-pane cache files key on the same GUID (`_iterm_cache_key()`).
- **Permissions are explicit.** Directories are `0700` and files `0600`, re-applied on each write through `_mkdir_private` / `_write_private`; the state files carry turn text verbatim, so the umask doesn't decide who reads them.
- **A swallowed failure is logged.** Every site that shells out and swallows the result (NFR-06) calls `log_error()` into `<DATA_DIR>/logs/errors.log`; `beacon doctor` reads it back (DIAG). The serve service logs to `serve.{out,err}.log` beside it.
- **The age sweep runs itself.** `_sweep_stale_state` (WIP-06) runs at SessionStart, throttled to once a day by `cache/last-prune`'s mtime.

## iTerm2 preferences

No hook or render runs `defaults write com.googlecode.iterm2`. iTerm2 caches prefs in memory and restores them on quit, so the writers that exist (`configure --write` / `--defer`, CLI-18 and CLI-22; `refresh-iterm-profiles --remigrate`, CLI-19) write only while iTerm2 is down. Never call them from a hook or render: the restart closes every window.

- Decide whether iTerm2 is running through Apple Events, never `pgrep -x iTerm2`, which never matches the running app (macOS matches `-x` against the full executable path).
- Profiles load from `DynamicProfiles/`, which iTerm2 reloads live. Sessions switch into them at runtime with `set-profile`; `MODE_SPECS` maps mode to profile so call sites never name one.
- A stale saved copy shadowing a dynamic profile is repaired by re-enabling iTerm2's own migration (CLI-19). **Don't** write `New Bookmarks` to fix it.

A new iTerm2 release can rename a key or move a default and break a surface silently. `just iterm-release` reports the releases not yet read; the `iterm-release` project skill does the read.

## Session focus

`POST /focus` resolves the session hash to its `iterm_session_id` server-side, so the GUID never reaches the browser (FOCUS). The CLI's osascript captures the target first and selects after: selecting mid-enumeration reorders iTerm2's window list and throws `Invalid index -1719` on nested splits. Every serve route is loopback-only with a Host and Origin check (WIP-18), the reads included, because the payload carries turn text.

## The CLI reference is a recording

`plugin.yml`'s `cli:` block declares how to run the CLI (`python3 scripts/beacon`,
`engine: argparse`) and how the reference page reads: a lede, one group per family
of commands, and the notes and worked examples help output has no way to express.
shipyard's `gen-cli-manifest` then runs the CLI, records the grammar its help
documents into `spec/cli.yml`, and `build-docs` renders that as `/cli` on the docs
site. Neither file is hand-edited; a diff in `spec/cli.yml` is a change to the
public grammar.

The generator refuses any disagreement between the two halves: a group naming a
command the help doesn't document fails, and so does a documented command no group
lists. So **a new subcommand needs a `cli: groups:` entry in the same change**.
Read the projection before pushing with `just check-generated`.

## Releasing

Releases are dispatched, not tagged by hand: run the **Release** workflow with a
bump level, and shipyard derives the version from `plugin.yml`, retitles
`CHANGELOG.md`'s `## Unreleased` section, commits, tags that commit, and
publishes. Write the notes into `## Unreleased` first; reading what landed is
what picks the level.

## Conventions

- **No fallbacks.** Don't add a "simple alternative" path inside a try/except around the real logic. Let primary failures surface. (`_cli()` is an exception: it swallows errors so a bad CLI invocation can't crash a hook.)
- **No comments explaining WHAT.** Good identifiers do that. Comments capture WHY: hidden constraints, subtle invariants, workarounds. Re-read existing code comments before adding new ones; most explain non-obvious WHYs and should be kept.
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
| Check the install and report recorded errors | `python3 scripts/beacon doctor [--since 7d] [--json]` |
| GC per-session state + per-pane cache files for long-idle panes | `python3 scripts/beacon prune [--since 30d]` |
| Delete per-session state for one session | `python3 scripts/beacon forget <hash>` |
| Render the Claude Code status-line row (mode note + deliverable links) | `echo '{}' \| python3 scripts/beacon statusline` |
| Reload shell integration | `exec zsh` |
| Smoke test the CLI | `python3 bin/beacon-iterm <subcommand>` (writes OSC to `/dev/tty`) |
| Regenerate the mode watermarks after changing their source art | `python3 iterm/make-bg.py [<mode>...]` |
| Run unit tests | `just test` (loads `scripts/beacon` via importlib, mocks `_cli`) |
| Re-record the CLI grammar + reference page | `just generate` (writes `spec/cli.yml`, renders `docs/cli.md`) |
| Read a new iTerm2 release against the surfaces beacon renders through | `just iterm-release` (`--ack` records it) |

### Running your changes

`just trial-on` points every installed entry point at this working copy, and
`just trial-off` points them back at the installed build. beacon pins three of
them to a plugin root at install time (the `beacon` on PATH, the `.zshrc`
source line, and the script path baked into each iTerm2 profile's buttons), and
`install` is what rewrites all three from its own root, so both recipes run it
rather than moving surfaces by hand (CMD-08a). Run `exec zsh` after either.

`beacon --version` tells you which is in force: a trial answers
`<version>-dev.g<short-sha>`, an installed copy answers the bare version (CMD-30).

The test suite under `tests/` covers plugin-side behavior. Surface verification (the actual badge, status bar, and tab color rendering, and the focus action, in iTerm2) still requires sourcing the shell snippet and looking.

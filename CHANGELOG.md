# Changelog

## 1.20.0

## Window title

A `/rename`d window kept losing its project context, leaving concurrent sessions hard to tell apart in Mission Control, the window switcher, and the Dock. The OS window title now carries `project · task` — the same as the badge — and it sticks.

- **`project · task` in the title bar** — set via the iTerm2 session *name*, so it survives Claude Code's `/rename` and auto-titles. The profile disables terminal-set titles (`Allow Title Setting`), so nothing overwrites it; beacon owns the name out-of-band through Apple Events.
- **Reuses the badge template** — the title and badge are one source, so they never drift, and the title re-evaluates live as the project / task change.
- **Interactive shells get it too** — a plain `beacon-dev` pane shows its project in the title (project only; there's no task outside a Claude session).
- **Profiles unchanged** — no profile renames, same switch keys, so nothing else moves.

## Badge default

- **At-rest badge is now gray by default** — a fresh pane reads the dev-cycle gray before its first status render, instead of inheriting the parent profile's badge color.

Full detail in the [CHANGELOG](https://github.com/chris-peterson/beacon/blob/main/CHANGELOG.md).

## 1.19.0

### SDLC cycle profiles

- **Statuses are now SDLC cycles.** The everyday **dev** cycle (`idle` /
  `working` / `waiting`) rides the base `beacon-dev` profile with a dynamic
  badge stoplight; the mode cycles — `pause`, `release`, `retro`, `done` — each
  own a dedicated profile. `wrapping` is renamed **`retro`** and `releasing` is
  renamed **`release`**; the base profile is renamed `beacon` → `beacon-dev` and
  the mode profiles to `beacon-pause` / `beacon-release` / `beacon-retro` /
  `beacon-done` (an upgrade sweeps the old profile files).
- **`release` mode** — a new cycle for a ship-it / release flow (`beacon release`
  or `/beacon:release`): a deep launch-sky navy pane with a faint rocket
  watermark under a pinned **green** badge.
- **Green leaves the dev stoplight.** At rest the badge is now a neutral **gray**
  (a session's known default before its first turn), so green is reserved for
  `release` and reads unambiguously as "shipping."
- **`done` drops the task.** A completed session shows its project alone —
  the task slot is suppressed while `done` (reversibly, STATE-12) — plus a
  dim-gray badge and the powered-off pane.
- **`retro` recolored** to a white badge on its muted-green pane.
- **No more `||` badge glyph.** Every cycle now reads by background + color
  alone, consistently across the pane, the dashboard card, and the fleet list;
  the pause text glyph is gone.
- **New docs page — [The beacon palette](https://chris-peterson.github.io/beacon/#/palette)** — the cycle
  taxonomy and every color, plus refreshed fleet screenshots.

### Spec & internals

- New requirements STATE-11 (the `release` synonym), STATE-12 (`done` suppresses
  the task, keeps the project), and STATE-13 (the SDLC cycle vocabulary); the
  pre-existing STATE-10 (`pause --clear-screen`) is unchanged. BADGE-09 stoplight recolored (gray at
  rest), BADGE-11 rewritten (no glyph), and the `wrapping`/`releasing` →
  `retro`/`release` and `beacon` → `beacon-dev` renames threaded through STATE,
  CMD, RENDER, THEME, WIP, and §6.6. Colors stay Dracula-sourced (THEME-01), the
  `release` navy being a darkened `comment`.

## 1.18.0

### Fleet dashboard: grouping, project stacks, and a needs-you band

- **Automatic grouping** — the fleet view now groups sessions by their
  correlated route group; the flat/group toggle is gone. Sessions with no route
  group fall into an unlabeled section at the bottom.
- **Same-project stacks** — multiple sessions for one project collapse into an
  overlapping stack, newest in front, with the rest brought forward on click or
  Tab (an animated raise). Only the front card exposes its controls; a behind
  card is click-anywhere-to-raise and previews its task + latest turn on hover.
  An expanded card holds the front slot so a sibling's newer turn can't collapse
  what you're reading.
- **Needs-you band** — genuinely blocked sessions are hoisted into a pinned band
  above the calmer fleet. A parked/wrapping/done session stays in the fleet (its
  mode outranks a lingering attention marker), so it reads as set-aside rather
  than as needing you. Clicking a card's `waiting` pill focuses the session.
- **Mode-card treatment** — a paused/done card echoes its iTerm2 pane: a muted
  tint plus a large, faint, centered watermark (`||` for paused, a power-off ring
  for done); wrapping is tint-only.
- **Inline forget** — the card close (×) opens a small confirmation fly-out
  instead of the browser `confirm()` dialog (Keep / Esc / click-away to dismiss).

### Spec & internals

- New requirements WIP-15 (project stacks), WIP-16 (route grouping), WIP-17
  (mode-card treatment), RENDER-06 (suppress iTerm2's native notifications),
  HOOK-10 (SessionStart emits the bundled ambient rules); WIP-12 narrowed to the
  text-only views. Coverage ledger refreshed to 149 IDs; the duplicate CMD-16
  (`data-dir`) is renumbered to CMD-21.
- Removed the never-read pending-attention prompt-type plumbing (the `--type`
  hook flag and its state field).

## 1.17.0

### Branch review

- New `beacon review` subcommand diffs the whole branch against the default
  branch (`origin/HEAD` → `main` → `master`) through git's configured difftool
  with `MOOR_CONTEXT` set, relaying [moor](https://github.com/chris-peterson/moor)'s
  sidecar verdict (comments + exit code) on stdout. On the default branch, or
  outside a git repo, it reports there's nothing to review instead of opening an
  empty diff.
- The status bar gains a centered **`⇄ review`** action chip — an iTerm2 Send
  Text action that types `beacon review` into the pane. In a shell it opens moor
  for a manual review; in a live Claude session Claude runs it and acts on the
  `fix-now` comments, closing the review loop from one click. `bin/beacon-iterm`
  stays unaware of moor and Claude. (#11)

## 1.16.0

### Fleet dashboard

- Turn cards now render markdown **links** — `[text](url)` becomes a clickable
  link (new tab), including code chips inside links (`[`sha`](url)`) and links
  in table cells. Hrefs are scheme-sanitized (http(s)/relative/anchor only) and
  quote-escaped, so a `javascript:`/`data:` URL falls through as plain text.
- **Bold-wrapped inline code** (`` **`x`** ``) now renders as bold code, in the
  collapsed one-liner, the expanded panel, and table cells.

### Session control

- `beacon pause --clear-screen` clears the iTerm2 session's screen **and**
  scrollback (the Cmd+K / "Clear Buffer" equivalent) alongside pausing — for a
  clean stand-down, e.g. the retro launcher parking a spent session. It degrades
  gracefully outside iTerm2 or with no reachable tty: the pause still applies,
  the clear is skipped. (#8)

## 1.15.0

### Fleet dashboard: rich turn rendering

- Expanded session cards render Claude's replies as markdown — bold, inline &
  fenced code, bulleted/numbered lists, headings, and GFM tables — in a quoted
  transcript panel; the collapsed one-liner renders inline bold/code too. All
  rendering escapes before it formats, so turn text can't inject markup.
- The session description renders its own _italic_ and line breaks (beacon's
  status-overlay convention) instead of raw underscores; underscore-italic is
  word-boundaried so `snake_case` and paths in a recall note stay intact.

### Card layout & de-duplication

- `/color` reads as a compact identity pill on the project name rather than a
  full saturated header band that shouted over the status colors.
- The expanded quote block's left accent encodes role (you/claude); status
  stays on the dot + bottom bar, so the two no longer double-encode.
- The waiting badge moved to its own row above the title (short tasks no longer
  wrap) and absorbed the elapsed time; the standalone wait line is gone.
- Elapsed time in the footer gets a clock glyph; branch moved from a duplicated
  footer label to a copyable detail row; dropped the redundant footer status
  word and the turn-at detail.
- The grid caps at 4 columns on wide screens.

## 1.14.0

### Features
- **Fleet dashboard overhaul.** Visual weight now tracks how much a session needs you: a blocked or attention-flagged session keeps its red glow + `WAITING` flag wherever it sits, sorts first within its group, and floats its group to the top — no separate band. A grouping toggle (flat / group / project) in the masthead governs the whole view.
- **`/color` as the card's identity.** `agent_color` fills the whole title row behind the project icon (which stands in for the status dot); the status color moves to a bottom bar so identity and status don't compete.
- **Click-to-expand.** Reveals the full task, the full turn, and a detail block (cwd, turn time, session id) with copy buttons; a dedicated `go →` button focuses the window; the route chip is dropped when it just echoes the project.
- **Full turn on demand (WIP-14).** The plugin persists each turn's full text (`latest_turn_full`) and serves it at `GET /turn/<hash>`; the dashboard fetches it on expand. The bulk `/wip.json` stays single-line (WIP-11), so the cross-session feed stays small.
- **Bound-tack references (WIP-09).** Each bound tack carries its deliverable/link URLs classified `cr` / `issue` / `other`, rendered on the card as links emphasized change request → issue → other.

### Other
- The iTerm2 badge's project/task separator is now ` · ` (middle dot), matching the dashboard's `project · task` separator.

## 1.13.0

### Features
- **`/rename` and `/color` are now beacon signals.** Renaming a session with Claude Code's `/rename` sets its fleet-view **task** — ranked just below an explicit `beacon task`, above the PR-title and branch fallbacks — so the label you reach for naturally shows up across the fleet without a separate `beacon` command. Claude's auto-generated session title becomes the *weakest* task fallback, so a session you never labeled still carries a readable headline. Setting a session's **`/color`** surfaces that color in the fleet view (a swatch on each dashboard card, and an `agent_color` field in `/wip.json`); it does **not** repaint the badge, which stays the ready / busy / blocked status light.

### Fixes
- A Claude session that ends (or is cleared with `beacon clear`) while in a mode state (`paused` / `wrapping` / `done`) now restores its pane background instead of keeping the mode's darkened background.

## 1.12.0

### Features
- Sessions can now be marked **done** — a "session complete, ready to hand off" mode for a session that has finished and delegated (e.g. a retro that stands down). The pane drops to a near-black "powered off" look with a faint power-symbol watermark and a dim purple badge. Set it with `beacon done [note]` or `/beacon:done`. Like `wrap`, it persists until you `resume`/`clear` rather than auto-resuming on the next prompt, and it stays pinned in the fleet view as deliberately set aside.

## 1.11.1

### Other
- The `beacon` skill (and the `wrap` / `pause` commands) are now marked `disable-model-invocation`, dropping their descriptions from every session's always-resident context. Still available via `/`; Claude no longer auto-loads them.

## 1.11.0

### Fixes
- Fleet view no longer shows a raw `<task-notification>` as a session's latest turn. Harness wake-ups (prompts that arrive with a leading angle-bracket tag) are skipped at UserPromptSubmit, so the play-by-play keeps showing the prior real turn; the status still flips to working.
- Clicking a fleet-view card now focuses a session whose window was minimized to the Dock — the window is de-miniaturized before select/activate (a no-op when it wasn't minimized).

### Other
- Trimmed the `beacon` skill's `description` frontmatter to cut the always-resident context cost; the trigger enumeration is dropped in favor of one what/when sentence.

## 1.10.1

### Fixes
- The `↖ web` button's per-session URL handoff file is now rewritten every prompt, so if it is emptied out-of-band (a cache prune, a deleted file, a stale-id clobber) the button heals within one prompt cycle instead of falling back to a search-engine landing while the status chip still shows the deliverable.
- Paths substituted into the iTerm2 profile are now escaped, so a path with special characters no longer breaks the profile.
- The shell-completions freshness reminder is now keyed on `CLAUDE_CODE_SESSION_ID`.

## 1.10.0

### Features
- Paused sessions now dim the whole pane: the background switches to a muted
  purple with a faint `||` watermark, so a parked pane is recognizable at a
  glance — not just by its badge color. The `||` glyph also anchors the session
  on the badge and in the fleet view (`wip` / `watch` / dashboard).
- New `wrapping` mode for a post-work follow-up / retro phase. `beacon wrap
  [note]` (or `/beacon:wrap`) gives the session a muted-green pane background
  and a teal badge. Unlike pause, it persists until you `resume` or the session
  ends.

### Other
- Both modes are delivered by dedicated iTerm2 dynamic profiles
  (`beacon-paused`, `beacon-wrapping`) derived from the base profile at install,
  so a mode can paint a pane background the badge-color signal can't express.

## 1.9.0

Each fleet card now shows what a session is actually doing — not just its project and status — without relying on the agent to label itself.

### Features

- **The fleet view surfaces each session's most recent turn.** Every card now carries a `latest_turn` line — the latest human prompt (`›`) or agent reply (`↳`) — derived automatically from the session's transcript at hook time, so a session that never sets a task label still shows live context. The dashboard ellipsizes the line to the card's width. The task label becomes the durable headline layered over this play-by-play (WIP-11).

### Other

- The test suite is now portable to Windows CI.
- Added end-user docs for the `just demo` fleet and the iTerm2 per-pane views.

## 1.8.0

Makes the fleet view a first-class cross-platform surface, so beacon is useful beyond macOS + iTerm2. The per-pane painting stays iTerm2-only by design; everything below works in any terminal on any OS.

### Cross-platform fleet view

- `beacon watch` now runs on Windows and other terminals that lack POSIX terminal control, via a polling fallback (Ctrl-C to quit).
- Session identity seeds from `CLAUDE_CODE_SESSION_ID` when there's no iTerm pane id or tty, so concurrent windows on Windows / non-iTerm terminals no longer collide on a shared state bucket.

### Reference dashboard

- `beacon serve` now hosts a self-contained reference dashboard at `http://127.0.0.1:8787/` (data still at `/wip.json`). Open it in any browser to see your fleet — no dashboard of your own required. Clone and restyle it, or point your own consumer at the same `/wip.json` + `/focus` + `/forget` contract.

### Standalone labeling

- A `keep-session-labeled` ambient rule (emitted at SessionStart) keeps each session's task label current as the work shifts, so the fleet view has signal without tack or recipes — and defers to tack when a route is bound.

### Tooling

- Cross-platform CI matrix: ubuntu / macOS / Windows × Python 3.9–3.13.
- `just demo` (`dev/demo.py`) seeds an isolated fleet and serves a live simulation, so you can demo beacon without real Claude Code sessions.

Docs and the spec (WIP-10) updated to match.

## 1.7.0

### Features

- **The fleet view shows which tack each session is driving, not just which route.** `wip` records now carry a `tacks` field — the route-qualified tacks the session is bound to (in touch order, last = current focus), each tagged `existing` (work resumed on a tracked tack) or `emerging` (spun up fresh this session). Pairs with tack 0.18.0, which records the binding (WIP-09).
- **`/beacon:pause [note]`** — a dedicated slash command to park a session in one keystroke, instead of `/beacon:beacon pause`. The badge flips to the paused color immediately (CMD-18).

### Performance

- **The `wip` / `serve` fleet scan is dramatically faster on large fleets.** Profiling a 375-session fleet found the dashboard's default-window poll spending most of its time spawning a `git` subprocess per session and re-scanning the whole state directory per session. The scan now reads last-activity in a single pass, memoizes the branch probe per directory, and probes git only for the sessions it actually emits. Default-window scan: ~3.6s → ~0.3s; full history: ~3.6s → ~0.9s. Adds `beacon wip --timing` for profiling (PERF-01..04).

### Fixes

- **Pausing no longer makes a network call or drops your label.** Setting `paused` froze the badge's identity by re-resolving from scratch — which ran a `gh`/`glab` PR-title lookup in that hot path and discarded any active project/task override. It now freezes what the badge already shows (STATE-03).

## 1.6.0

### Features
- **Forget a single stale session from the fleet view.** A long-idle pane lingers in the dashboard — a paused or aged-out session you've moved on from. `prune` sweeps these in bulk by age; the new `forget <hash>` removes one named session now, and the always-on `serve` process exposes it as `POST /forget` so the dashboard's close button on a timed-out card deletes that session's state directly (FORGET-01..03). The route shares the `/focus` access model — loopback bind, DNS-rebind defense, the same origin allowlist — since it's a mutating endpoint. A forgotten session repaints on its next hook event, exactly as after a prune; forgetting a session with no state on disk is a no-op.

## 1.5.0

### Changes
- **Paused sessions stay in the fleet view however long they're parked.** `wip` / `serve` window by last-activity, so a session you set aside for days used to drop out of the snapshot once it aged past the window. A `paused` session is now exempt from the window — parking is deliberate, not idle decay — so it survives past the cutoff where an idle/working session of the same age is dropped (WIP-03). A dashboard can surface these alongside active work (the wip dashboard pins them to the right).

## 1.4.0

### Features
- **The fleet view now carries each project's icon.** beacon finds the project's favicon from its own files (`docs/favicon.svg`, a root `favicon.*`, the web-framework `public/` / `static/` / `app/` roots, `icon.*` / `logo.*`) and exposes it in the `wip` / `serve` payload's new `icon` field, so a dashboard can show the favicon and tell work streams apart at a glance. A local icon is served alongside the payload at `/icon/<hash>`; an `http(s)` icon URL loads from any origin. Point beacon at a custom icon with `beacon icon <path-or-url>`; the field is `null` when a project ships no icon.

## 1.3.0

### Features
- **Exiting a session now clears its badge.** A new `SessionEnd` hook disengages the pane when you leave Claude — the badge text and color clear and the pane looks like an unmanaged terminal again, instead of holding the last-painted color and project. `/clear` and resume are exempt, since those re-engage the same pane immediately. (Exit is best-effort: a hard crash or `kill -9` can't run the hook, so a stale badge there clears on the pane's next beacon-aware action.)

### Changes
- **The `@<project>` wander marker now clears when a session comes home.** The marker is live "where the session is working" context, so it shows only while the session is actively working. At rest — idle, blocked on a prompt, or paused — the task re-resolves from the session's anchor and the marker drops. A session that returns home and finishes its turn clears the marker at Stop, and a session that blocks or ends while away no longer freezes a stale marker into the fleet view.

## 1.2.0

### Changes
- **A wandering session now shows a compact `@<project>` marker plus what it's doing there.** When a session works in another project mid-task, the task slot read the full live path (`beacon: ~/src/getty/cpeterson/ai-sdlc`). It now reads `beacon: @ai-sdlc: <task>`, where the task is your explicit override if set, otherwise the PR title or branch resolved at the wandered location. With nothing to show there, the marker stands alone (`beacon: @ai-sdlc`). The marker now also coexists with an override instead of being suppressed by it.

## 1.1.0

### Features
- **A session that works in another project now shows where it went.** When a Claude session changes directory into a different project mid-task, the badge's task slot surfaces that location (e.g. `beacon: ~/src/ai-sdlc`) as secondary context. Navigating within the session's own project keeps the branch/PR task; an explicit task you've set always wins.

### Fixes
- **The badge project stays anchored to where the session started.** A session that changed directory mid-task used to repaint its badge with the new directory's project, so glancing across panes no longer identified each session by its home project. The badge now pins the project to the directory the session began in, and `beacon show` reports the same project and task the badge paints.
- **A dashboard deployed to a private host can now focus sessions on click.** `POST /focus` extends its origin allowlist (FOCUS-04) with the `focus_origins` list in `~/.config/beacon/config.json` — so a dashboard served off-machine (e.g. GitLab/Cloudflare Pages) clears the browser's CORS preflight without committing the origin to the source. The config is read at serve startup and persists across reinstalls. Reading `wip.json` was already open to any origin; only focus-on-click was gated.

## 1.0.0

### Breaking Changes
- **The iTerm2 marginalia overlay is retired in favor of the externalized fleet view.** Its raster-to-file rendering, permission grants, behind-text layering, and color-banding made it a poor surface. Removed with it: the `note` / background-image / clear-screen subcommands, the `_compose.py` helper and the Pillow dependency, the four per-state dynamic profiles and the `!` / `?` watermark assets, and the exclusive-configuration / default-profile / background-image-trust machinery. beacon no longer issues any `defaults write` — badge and tab color paint via OSC on a single base profile, activated by a runtime `set-profile`.

### Features
- **Click a session in the fleet dashboard to raise its iTerm2 window** (FOCUS-01..04). `beacon-iterm focus <id>` brings the window forward; the iTerm2 session GUID is recorded at SessionStart and exposed as a per-session `focusable` flag in `wip.json` without leaking the GUID. `serve` adds `POST /focus`, which resolves the hash to the handle server-side behind a loopback `Host` check and an `Origin` allowlist; `GET /wip.json` keeps its permissive CORS.
- **The session description is now recall context in the fleet view** rather than paint on the pane — it survives the overlay's removal.
- **`task` is part of the `wip.json` session payload** (WIP-01). One of beacon's three core signals (project / task / status), it was previously dropped from the payload, so the fleet view and the goals/WIP dashboard couldn't show what each session was working on. Sourced from the last-rendered snapshot, preferring a fresher explicit override.

## 0.23.0

### Features
- **The fleet dashboard (`wip` / `watch` / `serve`) now works in any terminal.** It reads across all sessions and paints no pane, so it no longer depends on iTerm2 — only the per-pane painting (badge, status bar, overlay) needs macOS + iTerm2.
- **`beacon install` is terminal-aware.** It detects iTerm2 (macOS + `iTerm.app`); when absent it installs only the CLI wrapper and completions and points you at the fleet dashboard, skipping the iTerm2-only setup instead of attempting it.
- **New `beacon serve install|uninstall|status`.** Keeps `serve` always running under a launchd agent (macOS) or systemd user unit (Linux) so an external dashboard has a stable endpoint that restarts on crash. Opt-in — `install` doesn't start it.

### Fixes
- **`beacon install` no longer reports success for an iTerm2 preference it couldn't set.** On a non-macOS box the `PerPaneBackgroundImage` write silently no-ops; install now reports the failure instead of printing a checkmark.

### Other
- Repositioned the spec and docs around beacon's two surfaces — the terminal-agnostic fleet view and the iTerm2 per-pane adapter. `docs/README.md` gains a Fleet dashboard section and an opt-in always-on service section.

## 0.22.0

### Breaking Changes
- **Bare `beacon` (no arguments) now prints the usage text** (to stderr, exit 1) instead of running `show` (CMD-17). Run `beacon show` for the resolved signal state. The `/beacon:beacon` slash command is unaffected — its shim passes `show` when given no arguments.

### Features
- **`beacon-iterm` with no arguments now prints the full help text** (to stderr, exit 1) instead of argparse's one-line "cmd required" error (CLI-16). `--help` / `-h` behavior is unchanged (full help to stdout, exit 0).
- **`beacon help` and `beacon-iterm help`** now work as aliases for `--help` (CMD-17, CLI-16).

## 0.21.0

### Features
- New `beacon watch`: a live, person-facing work-stream view. Sessions form a recency feed (most-recently-active on top), refreshing in place without the flicker of `watch beacon wip`. Press `q` to quit. The tack route is shown only when it carries signal the project name doesn't.
- `beacon` now respects standard color controls so output keeps its color through a pipe: a global `--color=auto|always|never` flag and the `NO_COLOR` / `FORCE_COLOR` / `CLICOLOR_FORCE` environment variables. This makes `watch --color 'beacon --color=always wip'` render in color, where `watch beacon wip` previously came through uncolored.

### Fixes
- Sessions started without an iTerm pane id (auto-spawned tabs, `claude --resume`, non-iTerm terminals) no longer share a single state bucket and cross-wire each other's project and URL.

### Other
- Refreshed STATUS.md to the current spec audit and trimmed an obsolete `tack find <pwd>` clause from the spec.

## 0.20.0

### Features
- `beacon wip` surfaces active work streams across every session, not just the current pane. It enumerates each session's stored state (status, anchored project/cwd, marginalia description, last activity, Claude session id) and prints a table grouped by tack route. Route correlation is authoritative-first: the Claude session id matched against tack's `sessions[]` block, then `.tack` pin, branch, or project name (whole or last path segment, so `owner/repo` maps to route `repo`). `--json` emits a structured snapshot; `--since <ISO-8601>` windows to a given time (e.g. the prior dashboard refresh); with no flag it defaults to the last 24h, and `--all` returns the full history.
- `beacon serve` exposes the same snapshot over `http://127.0.0.1:8787/wip.json` (loopback only, CORS-open, optional `?since=`) so a locally-opened dashboard can poll for near-realtime work-stream signal. The goals dashboard's "wip" tab consumes this to highlight which planned routes have a live session attached right now, falling back to a baked snapshot when the service isn't reachable.
- `--since` accepts a duration (`1d`, `2h`, `30m`) as well as an ISO-8601 timestamp.
- `beacon prune [--since 30d]` (alias `--keep`) garbage-collects per-session state for long-idle panes (including project-less sessions that never reached SessionStart), keeping the current session and everything active within the window.

### Other
- `wip` / `serve` / `prune` are read-only/maintenance surfaces — they paint no iTerm2 surface. New spec section §3.8 (WIP-01..06); CLAUDE.md and README updated; `tests/test_wip.py` added.

## 0.19.0

### Features
- The session note card is now a compact tile in the top-right corner instead of a tall panel down the side of the pane. It covers far less of the terminal and gets overwritten by output much less often. A longer note grows the card (up to ~2x its resting height) and shrinks its text to fit before truncating, so short notes stay small and long ones stay readable.

### Fixes
- `beacon pause` with no note now shows the paused gray badge and tab color — previously a note-less pause painted nothing (it tried to switch to a profile that doesn't exist).
- Clearing the note while a pane stays paused (e.g. `pause "x"` then `pause`) no longer leaves the old card on screen.
- A pane showing an idle-prompt notification alongside a note now reads red, matching its state, instead of the paused gray.
- Project / branch / URL chips stay pinned to where the session started instead of drifting with the working directory mid-session.

### Other
- The note card no longer shows a timestamp (low signal, and it went stale while a pane sat paused).
- Spec (OVERLAY-01, §4.1, CLI-05), CLAUDE.md, and tests updated; the card's type sizes and padding now scale from the card height.

## 0.18.1

### Fixes
- Marginalia card no longer renders faintly when a description is set while the session is also showing a permission/idle prompt. The `beacon-blocked` and `beacon-blocked-idle` profiles were forcing `Blend: 0.20` for the red `!` / `?` watermark; that dilution bled into the card painted on top via OSC. Blend is now `1.0` across every state profile, and the watermark PNGs carry their pre-faded alpha so they still read as a quiet backdrop.

### Migration
- Re-run `python3 scripts/beacon install` after upgrading so iTerm2 picks up the updated `beacon-blocked` / `beacon-blocked-idle` profile templates (without re-install, the cached profiles keep `Blend: 0.20`).

## 0.18.0

### Features
- Overlay descriptions now support bulleted lists (`* item` per line) and strikethrough (`~text~`), in addition to the existing `*bold*` and `_italic_` markers.

### Fixes
- Strikethrough renders as a single continuous line across struck words instead of one segment per word — no more visible gaps or wobble.
- Long overlay text no longer overflows past the card's bottom or right edge. Content past the card truncates with an ellipsis. Body text also stays at a consistent size across notes (previously the font shrank to fit, making the same overlay look different sizes for different inputs).

### Other
- Added `just preview` — renders an HTML gallery of representative overlays at `.preview/index.html` for visual iteration without launching iTerm2.
- Added 67 tests covering the overlay compositor (parser, block splitting, layout, strike-run merging, oversized-word truncation, smoke render).
- Spec updates: OVERLAY-01 and CLI-05 enumerate the expanded markdown subset; §6.11 names a daemon-backed headless renderer as the eventual escape hatch.

## 0.17.0

### Breaking Changes
- The `stage` signal is gone. `beacon stage …`, `beacon set stage …`, `beacon signal stage …`, and `beacon clear stage` no longer exist and fail with an argparse error. Stage never had a render surface (it only appeared in `beacon show`); folding the visible behaviors into `status` simplified the model.
- The `signal` subcommand is removed — it existed solely to feed `stage` from the skill. The skill no longer signals stage transitions on plan-mode entry or code-review requests.
- `beacon-iterm note` now requires a label: `note <label> <text>` (the uppercase status — `PAUSED`, `WAITING`, etc.). Direct callers must update; the plugin's internal callers are updated in this release.

### Features
- `status` accepts a free-text description that drives a marginalia card on the right edge of the pane: `beacon status waiting "bg data refresh ~30 min"` parks the card with that note while the badge flips to red. Useful for "I'm waiting on something async, not Claude."
- `paused` is now a fourth `status` value. The marginalia card renders for any user-set status with a description, not just paused; the card label tracks the live status (`PAUSED`, `WAITING`, …).
- `pause [<note>]` stays as shorthand for `status paused [<note>]` — muscle memory unaffected. Auto-resume on prompt submission fires only for `paused`; other user-set statuses survive the next turn.

### Other
- iTerm2 notification-center delivery and terminal-generated alerts are disabled on the beacon profile (`BM Growl: false`, `Send Terminal Generated Alerts: false`). They duplicated the badge color signal and could transiently overlay the badge.
- Spec rewrite: §1.3 (stage values) and §1.5 (stage vs status) deleted; §3.5 PAUSE renamed to STATE covering user-set status + description. `CMD-10` (`signal`) gone; `STATE-*` IDs replace `PAUSE-*`.
- Hook handlers no longer promote stage on `Write` / `Edit` / `Bash` / `ExitPlanMode`. The deploy regex is gone.

### Migration
- Re-run `python3 scripts/beacon install` after upgrading. The profile template gained `BM Growl: false` and `Send Terminal Generated Alerts: false` — without re-install the existing profile still fires Claude Code's permission/idle alerts as duplicate notifications.
- If any external scripts call `beacon stage …`, `beacon signal stage …`, or `beacon-iterm note <text>` (the single-arg form), update them. The arg surface changed.

## 0.16.0

### Features
- The pause overlay is now a left-anchored Dracula marginalia card — uppercase `PAUSED` label in pink, timestamp, short editorial rule, and your note body in foreground type — replacing the centered yellow post-it. The right side of the pane stays transparent so terminal content reads when you return.
- `/beacon pause "<note>"` no longer co-opts the badge's task slot. The note carries recall context for the overlay only; the badge's task slot keeps whatever PAUSE-01 snapshotted (PR title, branch, override). Long notes that previously overflowed the badge now stay where they belong.
- The pane's visible viewport is cleared before the overlay paints, so TUI content (Claude Code's chips, input, transcript) stops fighting the card for legibility. Scrollback is preserved — scroll up to see pre-pause history.

### Other
- New CLI subcommand `beacon-iterm clear-screen` (CLI-15) emits the CSI `2J` + `H` escapes used by the pause render path.
- Spec/doc sweep: "post-it overlay" → "pause overlay" / "marginalia card" across CLAUDE.md, STATUS.md, docs, shell snippet.

### Migration
- Run `python3 scripts/beacon install` after upgrading to land the `Blend: 1.0` setting on the base profile. Without it, the new card renders diluted against the terminal bg.

## 0.15.2

### Fixes
- Clicking the `↗ code` status-bar chip no longer leaks VS Code's "To read from stdin, append '-'" hint into the active pane (which previously landed in Claude's prompt input). The chip now opens the cwd via macOS `open -a "Visual Studio Code"` instead of the `code` CLI.

## 0.15.1

### Fixes
- Branch and URL status-bar chips now refresh during a Claude session. Previously, the chips were painted once at SessionStart and stayed frozen for the rest of the session — so a branch the agent created mid-turn, or a tack deliverable pinned mid-session, was invisible until you returned to a shell prompt. The plugin now re-resolves the chip slots from the session's anchor cwd at the end of each turn.

## 0.15.0

### Features
- The red blocked-state badge now distinguishes two prompt kinds via watermark: `!` for a permission prompt (Claude is hard-blocked on a human answer) and `?` for an idle prompt (softer — often spurious during background tools). Both still paint the badge red; the watermark lets a scan across panes separate "must answer now" from "might want to look."

### Fixes
- Idle prompts again paint the badge red. 0.14.0 narrowed the Notification matcher to `permission_prompt` only to suppress false positives during `run_in_background` work — but `permission_prompt` alone fires rarely enough that the red state was effectively gone. The matcher is back to catching both, with the `?` vs `!` watermark carrying the urgency distinction instead.

### Migration
- Run `python3 scripts/beacon install` after upgrading to land the new `beacon-blocked-idle` dynamic profile and its `?` watermark image.

## 0.14.0

### Features
- Badge labels are now shorter and consistent. Previously, projects with a `name` field in `package.json` / `Cargo.toml` / `pyproject.toml` showed the short name (`beacon`, `tack`) while everything else showed the full owner/repo path (`chris-peterson/beacon`). The badge now always renders the repo basename. The owner-bearing identity is still available as the `gh:owner/repo` status-bar chip for disambiguation; with `beacon set project <label>` available for custom overrides, the short form is the better default for the badge.

### Fixes
- The red `!` blocked-state badge no longer fires during background work. Previously, beacon caught both `idle_prompt` and `permission_prompt` Notifications. But Claude Code emits `idle_prompt` whenever the agent is idle — including while a `run_in_background` Bash is still in flight (e.g. `/wip`'s background refresh phase), even though no permission dialog is open. The matcher is now narrowed to `permission_prompt`, so red `!` reliably means "a permission dialog needs your answer."

### Other
- Spec entries PROV-01 and §6.2's badge-render example synced to match the new basename behavior.

## 0.13.0

### Breaking Changes
- The drift detection feature is removed. The badge no longer appends a `:<basename>` suffix when Claude's Bash subprocess wanders out of the SessionStart anchor, and there is no longer a separate cyan "drifted" badge color or `beacon-drifted` dynamic profile. In practice, the feature was firing on cases the suppression logic was supposed to catch (e.g. badges reading `chris-peterson/beacon:beacon` or `cpeterson/ai-sdlc:ai-sdlc`), and the cost of fixing it didn't justify the at-a-glance signal it was meant to provide.

### Migration
- Run `python3 scripts/beacon install` after upgrading. The install step rewrites the dynamic profile JSONs (three states now: ready / busy / blocked) and deletes the leftover `beacon-drifted.json` from `~/Library/Application Support/iTerm2/DynamicProfiles/` so it stops showing up in the iTerm2 profile picker.
- The `beacon_project_drift` iTerm user variable is no longer published. If you reference it in a custom iTerm profile or status-bar configuration, remove the reference.

## 0.12.0

### Features
- The badge now shows the resolved task as a `: <task>` suffix after the project (e.g. `beacon: render-on-badge`). When no task is set, the badge shows project alone — the slot self-collapses. Previously, `beacon set task` only updated `beacon show`; the visible badge stayed on project alone, leaving users without an at-a-glance signal of *what* they're working on within a given project.

### Migration
- Run `python3 scripts/beacon install` after upgrading to land the new dynamic profile JSON with the updated badge format. Existing iTerm panes pick up the format hot from the dynamic-profile reload; new panes pick it up via the refreshed shell snippet.

## 0.11.0

### Features
- The URL chain now probes `gh` (github hosts) or `glab` (gitlab hosts) for an open PR/MR on the current branch when tack has no link for it. The `↖ web` button lands on your MR/PR even when you haven't run `tack link add` — the common workflow gap. Soft integration: missing CLI or unrecognized forge host skips silently to the existing branch / project fallbacks.

## 0.10.0

### Features
- Freshly opened terminals stay unmanaged until a beacon-aware action engages them — no more giant badge spanning the pane the moment you open a tab. The badge only appears once you run `claude`, `beacon ...`, or invoke a beacon slash command in that pane. `beacon clear` fully disengages a pane, returning it to the same calm state as a fresh tab.
- Badge color is now translucent, so terminal content shows through. Mission Control / Exposé legibility is preserved while normal-zoom readability is no longer compromised. Badge sizing also shrinks (Max Height halved) so long repo names occupy less of the pane.
- The blocked state ships an `!` watermark behind the terminal — "Claude needs me" is now parseable in Mission Control where badge text isn't.
- `beacon set project <label>` overrides now stick in interactive shells. The shell snippet no longer republishes a cwd-derived value on every prompt and clobbers your explicit label.

### Fixes
- The `my-proj:my-proj` drift false positive — drift detection no longer adds a `:<basename>` suffix when the suffix would just repeat the anchor's last segment.
- `_publish_drift` self-heals when no SessionStart anchor exists: adopts the first observation as the anchor instead of running away with `:<basename>` suffixes on every PostToolUse Bash.
- `set project` overrides now propagate to the badge text (previously they updated `beacon show` but the badge stayed on the SessionStart anchor value).
- `skills/beacon/SKILL.md` previously told agents to use `beacon set task` for "badge labeling at session start", but task isn't on the badge. Replaced with a surface map and explicit "use set project" guidance.

### Other
- Spec restructured around an engagement precondition. New requirements: BADGE-13 (sizing + opacity), BADGE-14 (engagement-gated badging), BADGE-15 (state-driven background image), CLI-14 (`set-profile`), HOOK-09a (anchor self-healing), HOOK-09b (no-op drift suppression). The badge color mechanism pivoted from per-session OSC `SetColors=badge=` to one dynamic profile per state (`beacon-ready` / `-busy` / `-blocked` / `-drifted`), switched via `OSC SetProfile=`. Pause stays as an OSC overlay since its image is per-note.
- `iterm/images/blocked.png` bundled with the plugin.
- 22 unit tests (11 new this release) covering profile switching, OSC overlay for pause, engagement marker, first-render publish, and drift no-op condition.

### Migration
- Run `python3 scripts/beacon install` after upgrading — the new state profiles need to land in `~/Library/Application Support/iTerm2/DynamicProfiles/`.
- If you previously had `beacon-flicker-test.json` from manual testing in your DynamicProfiles dir, remove it.

## 0.9.0

### Features
- The status bar's project chip now collapses known forge hosts: `github.com/owner/repo` shows as `gh:owner/repo`, GitLab as `gl:`, Bitbucket as `bb:`. Unknown hosts pass through as `host/owner/repo`.
- When tack is tracking a deliverable for the current branch (or you've set a URL override pointing at a forge issue/PR/MR), the project chip appends `#42` for issues/PRs or `!17` for GitLab merge requests, e.g. `gh:chris-peterson/beacon#42`. The chip answers "what am I working on", not just "what repo am I in."
- Status bar reshaped: `↖ web · project │ branch · ↗ code`. The branch chip now sits next to the `↗ code` action so each end pairs an action with the data it acts on. The cwd chip is gone — the project chip now carries the spatial-context job alone.
- Badge renders the full nested-group path. `acmecorp/platform/auth-svc` shows in full instead of being collapsed to `acmecorp/.../auth-svc`. With the cwd chip gone, the badge owns spatial context and doesn't need to truncate.
- Branch chip drops the leading `@` sigil on the synced state — color (green / orange / dim gray) already carries the synced / diverged / untracked signal, and the bare name reads cleaner. Diverged (`↑3 main`) and untracked are unchanged.
- Drift hint format simplified from ` (@ <basename>)` to `:<basename>`, e.g. `chris-peterson/beacon:ai-sdlc`. The colon separator reads as a path tail and keeps the anchor in the same spatial column when scanning panes vertically.

### Fixes
- Badge sizing now uses iTerm2's Badge Max Width / Max Height knobs rather than a font-size suffix — more consistent across panes of different sizes.

### Other
- The docsify homepage (`docs/README.md`) gained a "Tack integration (optional)" section describing the soft dependency on tack and the `_beacon_resolve_url()` override hook for users wanting Linear / Jira / GitHub Issues / a custom provider.
- Root `README.md` trimmed to maintainer-focused content (clone-from-source, dependencies, repo layout, architecture). End-user install / verify / usage / upgrade / uninstall now live only on the docs site.
- Spec dropped PROV-01a (the nested-group abbreviation rule); PROV-01 now specifies the full `owner/.../repo` path.

## 0.8.0

### Features
- Project names with multi-level subgroups now display as `<top>/.../<repo>` instead of silently dropping intermediate segments. A remote at `acmecorp/platform/auth-svc` renders as `acmecorp/.../auth-svc`, so the displayed path is unambiguous. Two-segment paths render as before.
- Drift hint changed from ` (<basename>)` to ` (@ <basename>)` and now uses Dracula cyan. The `@` prefix reads as "currently at" — a transient location Claude has stepped into — so drift is visually distinct from the badge anchor identity.
- Freshly-sourced shell integration paints the badge calm green (`ready`) immediately, so a fresh pane doesn't inherit a stale red/orange color from whatever Claude session was last active there. Claude's hooks repaint to `busy` / `blocked` on the next turn as before.
- All iTerm2 surfaces beacon paints (badge, tab color, status-bar chips) now share a single Dracula palette with a strict one-role-per-hue rule: green/orange/red is the calm/working/blocked traffic light, cyan is reserved exclusively for drift, comment-gray is de-emphasis, and pink is the single "interactive" accent on action chips.

### Fixes
- Directories outside any recognized project (no `.git`, `package.json`, etc. before `$HOME`) now render consistently across every beacon surface. Previously `beacon show`, `beacon json`, and the in-Claude badge color path returned a literal `?` while the SessionStart anchor and shell integration showed the abbreviated cwd; now every surface uses the abbreviated cwd.

### Other
- Removed the `alias` feature from the spec and README. It was documented but never implemented, and no user had needed it; README examples referencing project-name shortening have been deleted.
- Internal: `docs/spec.md` was reconciled with the shipping code so every CLI subcommand and SKILL behavior has a requirement ID. New `STATUS.md` tracks per-requirement coverage.
- `.claude/` is now gitignored.

## 0.7.0

### Changes
- `beacon` is now exposed via a real wrapper at `~/.local/bin/beacon` (installed by `beacon install-cli`) rather than a zsh alias. The freshness check in `hooks/cli-freshness.sh` runs from non-interactive shells where aliases don't apply, so the prior alias-based setup silently bypassed drift detection. The wrapper matches the pattern used by tack and logbook. Run `/beacon:beacon install` after upgrading; `install` now drops the wrapper as part of its bootstrap, and `/beacon:beacon install-cli` refreshes just the wrapper for subsequent upgrades.

## 0.6.0

### Changes
- Badge now stays calm (green) between turns. Red is reserved for moments when Claude is actually blocked on you (permission or idle prompt), so across a wall of panes a red badge always means "this one needs me right now" — not "this one is between turns." Dock bounces follow the same rule and no longer fire on turn-end.
- Badge font reduced to `Menlo-Bold 10` so the badge text competes less with terminal content while staying readable in Mission Control.

### Fixes
- When Claude starts in a directory that isn't part of any recognized project (no `.git`, `package.json`, etc. before `$HOME`), the badge now shows the abbreviated cwd (e.g. `~/scratch`) instead of going empty. Drift hints render as `~/scratch (foo)` instead of a stranded `(foo)`.

## 0.5.0

### Features
- `SessionStart` hook now checks CLI wrapper freshness on every Claude Code session start, regardless of which surface invokes the CLI. Previously the freshness check lived in the `beacon` skill, which only fired on skill invocation — consumers calling `beacon` directly (other skills, shell, tooling) bypassed it. The hook compares `beacon --version` against `plugin.json#version` and emits an `additionalContext` nudge when they differ; silent on match, silent when the CLI isn't on PATH, never blocks the session.

## 0.4.0

### Features
- `beacon --version` (and `-v`) now reports the installed plugin version, sourced from `.claude-plugin/plugin.json`.
- The beacon skill now checks CLI freshness before its first invocation in a session. If the shell `beacon` wrapper (from `/beacon:beacon install`) is older than the running plugin, it surfaces a one-line note and offers to refresh.

### Other
- Documented the auto-update path for end users in the Upgrade section of the README.

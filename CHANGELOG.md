# Changelog

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

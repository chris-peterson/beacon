# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`SPEC.md`](SPEC.md).
Maintained by `/sextant:spec-status`.

**Last audit:** 2026-08-28
**Spec version:** v2 (root-level, `SPEC.md`)
**Coverage:** 179 spec requirement IDs, all implemented (0 Missing, 0 Contradicts).
2.0 moves per-session values into the Claude Code status line: STATUSLINE-02
(the resolved URL as an OSC-8 link) and STATUSLINE-03 (accumulated
deliverables) join STATUSLINE-01, and STATUS-BAR-07 makes the `↗ code` editor
configurable, and STATUS-BAR-08 gives `↖ web` a click-time resolver plus a
user-command knob (its URL *handoff file* is what 2.0 retires, not the chip).
STATUS-BAR-02 drops `⇄ review`, whose whole feature went with it (CMD-16
retired, along with the `moor` / `anchor` soft deps that served it).
CMD-19/20/22 retire into a single CMD-18, which then retires itself: with no
mode command at all there is nothing left for `/release` and `/retro` to
collide with, and the skills that drive mode transitions were written against
the CLI from the start.
SKILL-01..03 retire with the skill itself: the plugin ships no
`skills/` tree, its two conventions moved into the `keep-session-labeled`
ambient rule (HOOK-10), and the freshness check they duplicated was always
`hooks/cli-freshness.sh`'s. CMD-25 (`/beacon:pause`) and CMD-26
(`/beacon:install-beacon`) are the two slash commands the retired `/beacon:beacon`
wrapper leaves behind, and CMD-13's `install-cli` subcommand folds into
CMD-08.

The plugin version is **not** recorded here: the release workflow bumps
`plugin.yml` / `.claude-plugin/plugin.json` when a GitHub Release is published,
so a hand-written version in this file goes stale the moment CI runs.

The spec declares IDs in two forms — `**XX-NN.**` throughout, and `**[PERF-NN]**`
for the PERF block. Both are normative; a count that reads only the first misses
PERF entirely, which is what made the `PERF-01..04` row look sourceless.

A session resolves on **two independent axes** (RES-06), which were one `status`
field until 2.5.0. `activity` — `idle` / `working` / `waiting` — is what the hooks
observe, written several times a turn, and maps to the `ready` / `busy` /
`blocked` stoplight that colors the tab (BADGE-09). `mode` — `pause`, `release`,
`retro`, `done`, or the default `dev` — is what a user or skill
declares, and owns two surfaces of its own: a tab glyph (`MODE_SPECS`, TITLE-06)
and a dynamic profile whose background carries a watermark (`MODE_SPECS`,
RENDER-05).

The old single field merged them by priority, so the declared value won and the
observed one was discarded: a session in `release` or `retro` could not report
that it was blocked on the user. Splitting them makes `release · waiting`
representable, and the surface assignment is what keeps both readable at once —
with many tabs open only one *pane* is visible, so the tab's two slots take one
axis each. Nothing arbitrates between them, which is why no requirement states a
precedence.

**1.0 pivot (landed).** The 1.0 spec retired the iTerm2 marginalia overlay, the
`!` / `?` watermarks, the per-state dynamic profiles, `exclusive-configuration`,
and all background-image machinery, and added dashboard-driven session focus
(FOCUS, CLI-17). The code has converged: `focus` ships (`bin/beacon-iterm
focus`, the `POST /focus` route, the recorded `iterm_session_id` handle), color
is OSC `tab-color` on whichever profile the pane sits in, and the retired
surfaces are gone — `install_dynamic_profile` sweeps any beacon profile it did
not just write, keyed on what was written rather than on the list of past names
that had accumulated one entry per rename since 0.x. A bounded set of profiles
returns by design — the **mode profiles** (`beacon-pause` / `beacon-release` /
`beacon-retro` / `beacon-done`): a mode swaps into its profile
for a background no OSC can express (RENDER-05), while the activity states stay
overlays on whatever profile is active.

## Status by category

| Prefix | Covered | Status | Notes |
|--------|--------:|--------|-------|
| RES-01, 02, 04..07 (RES-03 retired) | 6 | All Covered | Signal resolution model; RES-02 exposes each chained signal's provider wherever the value is exposed, since a resolved `task` can be byte-identical to `branch`; RES-06 resolves `mode` / `activity` independently with no chain between them (`read_mode`, `read_activity`), and RES-07 stores a mode's note *with* the mode as one tuple so it can't outlive what it annotates (`write_mode`) |
| PROV-01, 02 (incl. 02a), 05, 06 (no PROV-04; PROV-03 retired) | 5 | All Covered | Provider chains; PROV-02 folds a `/rename` into the task override (recency-wins); PROV-02a joins the wandered project to home with a ` @ ` separator while working, clearing it at rest — its dev-cycle gate is now explicit, since a mode no longer wins the merged field for free; PROV-03 (the `status` chain) retired with the split — that chain *was* the defect; a linked worktree is not a wander — it has its own project root, so the root comparison alone painted a sibling checkout as another project (an opaque id where a tool generates the tree name); the shared git dir (`--git-common-dir`) is what tells a second checkout from actually leaving, checked only once the roots differ; the location is resolved apart from the task (`location` / `task_display`) and joins the **project on line 1** of the tab — `beacon @ ai-sdlc` — via its own `beacon_location` var, left out of `beacon_project` so the status-bar chip keeps the bare name; the marker was shaped for the badge's single line, and BADGE-15 made the badge opt-in, so the surface it actually reaches is the two-line tab, where a leading ` @ where` on line 2 has no antecedent |
| PROV-07 | 1 | Covered | `url` chain; branch-slug match (`scripts/beacon` `_tack_url_for`) |
| PROV-08 | 1 | Covered | `icon`: the discovered project favicon (`_discover_icon_at`), anchored at SessionStart; the override retired with OVR-05 |
| PROV-09 | 1 | Covered | Harvest Claude Code `/color` / `/rename` / `ai-title` from the transcript tail (`_read_cc_signals`); custom/ai-title feed the task chain, agent-color is sessions-view-only (WIP-13); wiped by HOOK-08a |
| HOOK-01, 01a, 02, 03, 03a..03d, 08, 08a, 08b, 09, 10 (HOOK-11 retired) | 13 | All Covered | Hook handlers; HOOK-03/03b paint permission and idle identically — the sticky marker carries a constant, not the prompt type — while HOOK-03d reads the kind for the one decision that is not a paint: an `idle_prompt` on a stood-down session (STATE-15) records nothing, since a parked pane sits at an idle prompt by definition and red would become its resting state (`cmd_hook`, `IdlePromptOnAStoodDownSession`); the matcher reaches the CLI as `--kind` from `hooks/hooks.yml`, the payload carrying no prompt kind; HOOK-08a's fresh-start wipe also stamps `session_started_at`, the window STATUSLINE-03 scopes acquisition to (`_wipe_session_for_fresh_start`); HOOK-09 disengages the pane on SessionEnd, handing the session name back to the interactive template *before* blanking the vars that template interpolates (`_disengage`); HOOK-10 emits the bundled ambient rules (`hooks/emit-rules.sh`, `keep-session-labeled`) at SessionStart; HOOK-11 retired with the `handoff` mode it was the only automatic writer of (STATE-14) — tack's session-close skill no longer moves the pane, and `_skill_invocation` / `SLASH_COMMAND_RE`, which existed for it alone, go with it |
| OVR-01..04 (OVR-05 retired) | 4 | All Covered | User overrides, now only where a provider chain sits beneath them (`VALID_FIELDS` = `project`, `task`) — which is what the `override.` prefix means; the `url` and `icon` overrides retired, neither carried by any live session across three months of state |
| STATE-01, 02, 04, 06..13, 15 (STATE-03, 04a, 05, 14 retired) | 12 | All Covered | Declared modes; STATE-01 takes modes only and rejects an activity value (`cmd_status`, `ActivityHasNoOverrideTier`); STATE-02's note rides the mode as one tuple and no longer claims recall context — that is `latest_turn`'s job (WIP-11); STATE-03 + STATE-05 retired: the pause-time identity freeze, which auto-resume then *preserved*, pinned a session's project/task above every provider forever (live state held tasks pinned to branches long since left); STATE-04a retired: its natural-language pause matcher authored zero of the notes on disk across three months, and its `brb` / `stepping away` triggers had come to mean the opposite thing; STATE-08 is the `retro` synonym for `status retro`; STATE-09 is the `done` mode (`cmd_done`, no snapshot, no auto-resume); STATE-10 is `pause --clear-screen` (`_cli("clear-screen")`, `cmd_clear_screen` in `bin/beacon-iterm`); STATE-11 is the `release` synonym (`cmd_release`); STATE-12 suppresses the task while `done`, now keyed on `mode` directly rather than on a value of the merged field (blanked in `resolve`, `test_done_suppresses_task_keeps_project`); STATE-13 makes the **mode name** the shared vocabulary across CLI, sessions view, glyphs, and profiles (`MODE_SPECS`, keyed by it); STATE-14 retired: `handoff` sat one turn of auto-resume away from `done`, and the phase it named is what `done` already says, leaving `AUTO_RESUME_MODES` a single member; STATE-15 puts the halted/active split on `MODE_SPECS` as `stood_down` (true for `pause` and `done`) so no call site names those two by hand and a later mode answers for itself — TITLE-05a and HOOK-03d read it, and reached the same pair independently (`_mode_stood_down`, `StoodDownIsDeclaredByTheMode`) |
| CMD-01..09, 13..15, 17, 21, 23..30 (gap 10, 11; CMD-12, 16, 18, 19, 20, 22 retired) | 22 | All Covered | CMD-01 `show` reports each chained signal with its provider plus the two axes (no provider — one writer each); CMD-15 `json` now satisfies its own contract, emitting every signal with a provider, `mode` as a nested `{name, note}` tuple, and `activity` — the `task` + `task_provider` pair chris-peterson/anchor#2 was parked on; it drops `status`/`description` with no aliases, since a `status` alias would have had to re-merge the axes and hand every consumer the defect back; CMD-24 is `drop <ref>`, which takes one deliverable off the status-line row and remembers the removal in `deliverables.dropped` so route re-reads don't restore it (`cmd_drop`); CMD-08 install writes the base + mode dynamic profiles and takes the `--dir` that came off the retired `install-cli` (`cmd_install`); CMD-13 now specifies the wrapper `install` writes rather than a subcommand of its own — `install-cli` ran install's first two steps and was what the drift nudge named, which left the version-pinned `.zshrc` source line unrefreshed; CMD-25 is `/beacon:pause` (`commands/pause.md`, user-invocable only) and CMD-26 is `/beacon:install-beacon` (`commands/install-beacon.md`), the only door to the newly-installed plugin root, named by `hooks/cli-freshness.sh`; CMD-16 retired in 2.0 with the branch-review feature (chip + `beacon review` subcommand + the moor/anchor soft deps); CMD-18 (the `/beacon:session-mode` shim CMD-19/20/22 folded into in 2.0, issue #23) is itself retired — its one live clause was staying model-invocable for a skill caller that never materialized, since a skill reaches `beacon release` in one shell call; CMD-21 is `data-dir` (renumbered 2026-07-06 from a duplicate CMD-16), now a contract for env-less callers rather than the shell's path to it; CMD-27 is `shell-init` (`cmd_shell_init`), the one zsh-sourceable block carrying every source-time value `shell/beacon.zsh` needs — the shell caches it and regenerates only when the script, the data-dir pointer, or the user config is newer, so a new terminal spawns no interpreter in the steady state; CMD-23 is `refresh-iterm-profiles`, the profile-only re-render that applies a changed button label, a moved interpreter, or a GUI-edited profile (`cmd_refresh_iterm_profiles`) — renamed off the `install-*` prefix, which now means the bootstrap only; it is never a first-install step, since `install` calls the same `install_dynamic_profile` renderer; CMD-28 is `layout` (`cmd_layout`), the plugin front door for CLI-18's app-wide layout audit: `beacon` is the only interface a user is expected to type, and the CLI is told which name to advertise (`BEACON_LAYOUT_COMMAND`) so its own advice, `install`'s drift line, and the docs all name `beacon layout` — it stays separate from CMD-23 because the two write disjoint things and only the app-wide half needs an iTerm2 restart, leaving CMD-23's no-advisory clause intact; CMD-29 is `doctor` (`cmd_doctor`), the front door to DIAG — install and environment checks plus the recorded error log, exiting non-zero so it can gate a health check; CMD-30 marks `--version` `-dev+<ref>` from a working tree (`_version_display`, `_is_dev_install`) — a git dir is present in exactly one of the two copies, and without the marker a released and an unreleased beacon of the same number read alike |
| WIP-01..17 | 17 | All Covered | Cross-session introspection / export; WIP-06 `prune` sweeps the per-pane cache (`cwd-*`, `engaged-*`, and the `url-*` files 2.0 retired) on the same `--since` cutoff as state, by each file's own mtime since the pane GUID isn't recoverable from a session hash (`_prune_cache`); WIP-01 emits `focusable` (FOCUS-03) + `icon` (PROV-08) + `latest_turn` (WIP-11); WIP-08 is the `/icon/<hash>` serve route; WIP-09 emits the session→tack bound `tacks` (route-qualified, existing/emerging); WIP-10 is the bundled reference dashboard `serve` hosts at `/` (`dashboard/index.html`); WIP-11 is the auto-derived `latest_turn` (human prompt / agent reply), written at hook time, ellipsized to card width by the dashboard; WIP-01 carries `mode` as the same nested `{name, note}` tuple CMD-15 emits, so beacon's two published payloads describe the value identically (`_record_mode` is the one accessor the sessions-view renderers read it through); WIP-12: every sessions-view consumer shows *both* axes — the dot carries `color_state`, the mode carries its own glyph, and the text views render `release·waiting` (`_wip_state_cell`), since a session blocked on the user is blocked whatever mode it declared; WIP-13 emits `agent_color` (sessions-view identity pill only, never painted); WIP-14 persists `latest_turn_full` + serves it at `GET /turn/<hash>` for card expansion; WIP-15 collapses same-project sessions into a z-stack (newest front, raise on demand); hovering or tab-focusing a tucked card brings the whole card forward in place, replacing the floating task+turn tooltip — a partial re-rendering of a card the reader can simply be shown (it comes forward in place because the ~11-13px peek means translating it would move it out from under the pointer and oscillate); WIP-16 auto-groups the sessions by route group (groupless in an unlabeled bottom section, no toggle); WIP-17 gives moded cards the pane-analog treatment (muted tint + centered watermark) on `mode` while the dot and accent bar answer to `color_state`, so a moded session that goes `waiting` keeps its treatment *and* turns red; it stays out of the attention band because the band's glow would paint over the only place the mode is legible, not because the mode outranks the signal |
| WATCH-01..02 | 2 | All Covered | Live person-facing recency feed |
| DUMP-01..04 | 4 | All Covered | `export` / `import` full-fidelity per-session state backup (`_export_payload`, `cmd_export`, `cmd_import`); versioned JSON envelope, gzip optional, mtimes preserved (DUMP-03), hex-hash + path-traversal guard on import; DUMP-04 treats the dump as sensitive (raw payload is the product, not shape-only) |
| DIAG-01..08 | 8 | All Covered | Error log + `doctor` (`log_error`, `read_error_log`, `_doctor_checks`, `cmd_doctor`). DIAG-01 records swallowed external-command failures as JSONL at `<DATA_DIR>/logs/errors.log`, keyed on non-zero exit as well as raised exception — the render CLI reports a failed iTerm2 operation the first way, which is how a broken `set-name` went a whole session unnoticed; DIAG-02/03 keep each record single-line and under `PIPE_BUF` for atomic concurrent appends and trim the file to its tail; DIAG-04 scopes recording to shelled-out failures so ordinary absences don't bury real ones; DIAG-05 probes the data-dir pointer, state dir, wrapper, status line, and — where the adapter applies — iTerm2 install/run state, the dynamic profiles, and whether this session's recorded pane handle still resolves through Apple Events; DIAG-08 keeps an adapterless box healthy rather than failing |
| COLOR-01 | 1 | Covered | `--color` + `NO_COLOR` / `FORCE_COLOR` precedence |
| FOCUS-01..04 | 4 | All Covered | Dashboard focus: `POST /focus` route + `_focus_session`, `iterm_session_id` handle (FOCUS-02), `focusable` in payload (FOCUS-03), loopback + Host/Origin guard (FOCUS-04) |
| FORGET-01..03 | 3 | All Covered | Dashboard forget: `forget <hash>` CLI + `POST /forget` route → `_forget_session` (FORGET-01), hex-hash guard (FORGET-02), shared FOCUS-04 access model (FORGET-03); tests in `ForgetTest` |
| PERF-01..04 | 4 | All Covered | Session-scan cost scales with emitted, not total sessions: `_session_mtimes` single dir scan, `_branch_for` per-cwd memoization, two-phase `collect_sessions` (cheap resolve → dedup → window → branch-fill), `wip --timing` (PERF-03); `test_branch_probe_memoized_per_cwd` |
| CLI-01..03, 06..12, 14..18 (gap 13; CLI-04/05 retired) | 15 | All Covered | CLI-15 is `set-name`, the Apple Events title path (`cmd_set_name` in `bin/beacon-iterm`) — the id was reused for it when the spec moved to the root, the third of the three live reuses below; CLI-16 is the `--help` usage table; CLI-17 `focus` via osascript (`cmd_focus` in `bin/beacon-iterm`); CLI-18 is `configure`, the one path that writes an iTerm2 preference — explicit, user-invoked, quit-write-relaunch (`cmd_configure`), never reachable from a hook or render; its seven audited settings are a spec table (`RECOMMENDED_LAYOUT` in `bin/beacon-iterm`), adding `HideTab=0` (iTerm2 hides the tab bar at one tab per window, taking the whole per-pane signal with it) and moving `StatusBarPosition` to `0` (the bottom of the pane is where Claude Code renders STATUSLINE-01); CLI-18's running check asks iTerm2 through Apple Events rather than `pgrep -x iTerm2`, which never matches it (macOS matches `-x` against the full executable path) — the false negative inverted the one branch the orchestration turns on, writing into a live iTerm2 that then restored the old values on quit, and the detached helper polled the same way; the audit now also qualifies an aligned reading while iTerm2 is running, since `defaults read` answers from a plist the running app will overwrite from memory |
| BADGE-01..07, 09, 09a, 11..15 (BADGE-08, BADGE-10 retired) | 14 | All Covered | Badge text + color + engagement; BADGE-09 maps `activity` to the three-value stoplight and no mode reaches it (`ACTIVITY_TO_COLOR_STATE`, `COLOR_PALETTE`); BADGE-09a keeps only the `pending-attention` clause — the mode clause above it is exactly what suppressed the interrupt signal; BADGE-10 retired with the per-mode color (a paused session now reads by its `⏸` glyph and pane background instead); BADGE-11 leaves the badge *text* undecorated — the mode's marks live on their own surfaces; BADGE-15 is **not** the retired watermark — the id was reused for the opt-in badge gate (off by default, `"badge": "on"` in the user config, read via `config-get` at all three paint sites) |
| TITLE-01..06 (incl. 05a) | 7 | All Covered | OS window title via the iTerm2 session *name* (Apple Events `set-name`; profile `Allow Title Setting: false`); TITLE-01 interactive panes fall back to the cwd (`beacon_title` = project else cwd); TITLE-02 records that iTerm2 implements the session name as a session-scoped override of the session's copy of the profile `Name` key (§6.10 caveat 7), so an engaged pane reads its profile name back as the raw template while `set-profile` still matches; TITLE-04 one-shot re-assert on the first turn boundary reclaims the title from the shell's backgrounded launch write, and disengagement returns the name to `beacon_title` ahead of blanking the badge user vars, since the shell's own write never re-runs (`test_name_handback_precedes_blanking_the_title_vars`); TITLE-05 is the two-line tab label (`TITLE_FORMAT`, `<b>project</b>` over the indented `beacon_task_nl`), whose line 1 doubles as the single-line OS window title; TITLE-06 leads line 1 with the declared mode's glyph via `beacon_title_prefix` (`MODE_SPECS` — `⏸` `🚀` `📋` `🏁`), which is the mode's *only* cross-tab surface now the tab color reports activity; until 2.5.0 only `paused` marked the title, leaving four of five modes legible from another tab by color alone; TITLE-05a gives a stood-down mode's note line 2 in place of the task, the note's only cross-tab surface — the status line it otherwise relies on exists solely in the focused pane, and a halted session has no live task to displace (`resolve`, `StoodDownModeNoteOnLineTwo`) |
| STATUS-BAR-01..03, 05..09 (gap 04) | 8 | All Covered | STATUS-BAR-01: runtime `set-profile` activation (plugin first render + install writes the base + mode profiles); STATUS-BAR-02 dropped the `⇄ review` chip in 2.0, leaving `↖ web` and `↗ code` to bookend the strip; STATUS-BAR-07 is the configurable `↗ code` editor, defaulting to a bare `code` (VS Code's CLI has no `--maximized`, and passing it through to Electron drops the directory on a cold start), and STATUS-BAR-08 the `↖ web` chip resolving at click time via `cmd_open_url <cwd>`, both reached through an absolute interpreter path and the login-shell binary lookup, since an action shell has no interactive `PATH` (issue #25, §6.10 caveat 3); STATUS-BAR-09 is the `statusbar.buttons.<name>` block behind both — `cmd` read on the click (with `{dir}` / `{project}` / `{branch}` expanded per argument by `_substitute_cmd_tokens`, `{dir}` suppressing the editor append), `label` baked into the profile by `install_dynamic_profile` and applied by CMD-23 (issue #29), its `maxwidth` knob grown to fit the baked title by `_fit_action_button_widths` since iTerm2 blanks an action component whose title overflows the cap; STATUS-BAR-01 additionally pins the base profile's colour behaviour to the parent (no `Use Separate Colors for Light and Dark Mode` override, no colour keys of its own) and carries the pane-scoped `AWDS Pane Option: Recycle` + its paired `AWDS Pane Directory`, which iTerm2 ignores unless both are present |
| STATUSLINE-01..03 | 3 | All Covered | Claude Code status-line provider (`cmd_statusline`): STATUSLINE-01 the ` · `-joined row (the declared mode's note, led by its glyph — the one place a mode's prose fits, since line 1 of the tab is shared with the OS window title; silent when every segment is empty), wired into `~/.claude/settings.json` by `install` (`_install_statusline`, one key, never replacing an existing `statusLine`); STATUSLINE-02 the resolved URL as an OSC-8 link read from persisted `resolved.url` state, never re-resolving (issue #26), with PROV-07's location tiers substituted when its answer is a route deliverable that shipped before `session_started_at` (`_location_url_at`), leaving click-time `↖ web` on the unsubstituted answer; STATUSLINE-03 the accumulated `deliverables` list, bare vs project-qualified, capped and deduped, dropped by the fresh-start wipe (issue #18), acquired from the bound tack route plus PROV-07's own resolution with each entry's project taken from its own URL (issue #31), and scoped to one Claude session by `session_started_at` — a tack reaches the row while open (`in_progress` or `pending`, `_OPEN_TACK_STATUSES`) or completed since the stamp, and PROV-07's resolution is skipped when it names only a route deliverable that shipped earlier (`_tack_in_session_scope`, `_url_delivered_before_session`)|
| RENDER-01..06 | 6 | All Covered | RENDER-04: OSC `tab-color` (+ `badge-color` when enabled) for the activity state, always an overlay — a color change never swaps a profile, which is what keeps a permission prompt mid-mode from flickering the background; RENDER-05: every mode swaps into a dedicated profile (distinct background *and* watermark) and re-emits the wiped OSC, keyed on the mode alone; RENDER-06: the beacon profile disables iTerm2's native notification-center + terminal-generated alerts; `MODE_SPECS` owns the mapping; each mode background is written to the plain and the `(Light)` / `(Dark)` keys alike, so it lands whichever set the parent's light/dark switch selects (`install_dynamic_profile`) |
| TAB-01..03 | 3 | All Covered | TAB-01: OSC `tab-color` carries `activity` and nothing else (`_color_state_for`) — no mode reaches it, which is what lets a moded session still report that it needs the user |
| THEME-01, 02, 02a, 03 | 4 | All Covered | Dracula palette; THEME-02 is now the three activity hexes alone (`COLOR_PALETTE`) and THEME-02a the per-mode background + watermark + blend (`MODE_SPECS`) — the axes never share a table because they never share a surface; `retro`'s blend rises to 0.25, since flat geometry carries less ink than the illustration it replaced |
| NFR-01, 03..12 (NFR-02 retired) | 11 | All Covered | Timing reqs advisory; NFR-04 bounds `focus`; NFR-06 soft deps are `tack` / `gh` / `glab` / `osascript`, all `_which`-probed — the `moor` and `anchor` deps went with the branch-review feature in 2.0; NFR-12 closes the loop on NFR-06 — the swallow that keeps a display failure from crashing a hook records to the DIAG-01 log rather than vanishing |

Numbering gaps (no PROV-04, no CMD-10/CMD-11, no CLI-13, no
STATUS-BAR-04) are intentional. IDs retired in the 1.0 pivot — CMD-12
(`exclusive-configuration`), CLI-04/05 (`bg-image` / `note`), CLI-15
(`clear-screen`), BADGE-08 and BADGE-15 (watermark), NFR-02 (overlay caching),
and the entire OVERLAY namespace — are removed, not missing coverage. The whole
SKILL namespace joins them: beacon ships no skill, so §3.6 holds only the
retirement note. The 2.5.0 mode/activity split retires seven more, each with its
reason recorded in the spec: RES-03 and PROV-03 (the `status` default and its
provider chain — that chain *was* the defect), STATE-03 + STATE-05 (the
pause-time identity freeze and its preservation through auto-resume), STATE-04a
(the natural-language pause matcher), BADGE-10 (the per-mode badge/tab color),
and OVR-05 (the `icon` override).

Two of those ids were later reused rather than left fallow, and both reuses are
live contract: **CLI-15** now numbers `set-name`, the Apple Events title path,
and **BADGE-15** the opt-in badge gate. Two retired *capabilities* also
returned, each under a different id than it left on: `clear-screen` as
STATE-10's `pause --clear-screen`, and `exclusive-configuration` as CLI-18's
quit-write-relaunch orchestration.

## Open items

**⚠ Resolved 2026-08-24** (both found by that day's spec-sync, both fixed rather
than carried):

- ~~**`resolve-url` orphan**~~ — the subcommand had no requirement and no
  caller: the shell dropped it from the per-prompt path (a test asserts it stays
  gone), no hook, status-bar action, or dashboard reached it, and it was hidden
  from completions. `cmd_resolve_url` and its three registrations are deleted;
  the `resolve_url()` function they wrapped keeps its live callers. `copy-url`
  is untouched — CMD-14 covers it and it is user-facing.
- ~~**PERF-01..04 in the retired bullet form**~~ — normalized to the `XX-NN.`
  heading form every other category uses, so a single-pattern inventory pass
  reads all 169 instead of silently undercounting by four.

### From the 2026-07-06 spec-sync

All divergences from the 2026-07-06 spec-sync are now **closed** — captured to
spec, resolved by hand, or explicitly declined. Kept here as the decision record.

**⚠ Resolved 2026-07-06:**

- ~~**CMD-16 duplicated**~~ — `data-dir` renumbered to `CMD-21`; `review` keeps
  CMD-16.
- ~~**`pending-attention` type orphan**~~ — deleted the unused
  `pending_attention_type` capture (Notification handler now writes a constant
  marker; the `resolve()` and wip-record pass-throughs removed) and the stale
  `BADGE-15` comment. The marker's presence still drives `blocked` (unchanged);
  only the never-read prompt-type value is gone. Tests green (195).

**→ to-spec — captured 2026-07-06** (four of the five drift items canonized):
WIP-15 (same-project z-stack), WIP-16 (automatic route-group grouping), RENDER-06
(suppress native iTerm2 notifications), HOOK-10 (emit ambient rules at
SessionStart) are now in the spec and Covered.

**Declined (left as intentional non-contract):**

- **Waiting-pill focus** — clicking the WAITING pill focuses the session (a 2nd
  affordance beside the `go` control). Reviewed in the `--to-spec` pass and *not*
  canonized: it over-specifies the reference dashboard, which WIP-10 explicitly
  frames as restyleable. The behavior stays in the code; if a future consumer
  contract needs it, revisit.

Note: the dashboard **needs-you band** (waiting sessions hoisted into a pinned
top band, removed from the sessions below) is *already* WIP-10 ("a prominent band
above the calmer sessions") — recent code realigned to it, not drift.

**Requirement quality:**

- ~~Text-drift: `BADGE-04` / `BADGE-05`~~ — **fixed 2026-07-06**: both now
  attribute the badge project + PROV-05 root walk to the plugin (`_publish_anchor`),
  with a note that the shell mirrors the walk for its own chips but never writes
  `beacon_project` (BADGE-02).
- Advisory, intentionally left as-is (they fight the spec's deliberate
  prose-plus-mechanism style): `HOOK-03c` (literal `^\s*ready\b`, already hedged
  "currently"), `CMD-16 review` (moor sidecar documented as the contract),
  `BADGE-09a` (clear as prose), `PROV-02a` (split into a/b/c/d — churn, little
  contract gain). Revisit if the spec ever moves to strict EARS.

## Audit history

### 2026-08-27 — Coverage refresh (spec-status)

168 IDs, all Covered, 0 needs-decision — coverage unchanged. CLI-15 corrected
from retired to live: the id was reused for `set-name` when the spec moved to
the root SPEC.md, and the CLI row's count had counted it all along while its
label and the numbering-gaps note still retired it as `clear-screen`.

### 2026-08-26 — Coverage refresh (spec-status)

168 IDs, all Covered, 0 needs-decision. Net +5, of which only +3 are new:
STATE-15, TITLE-05a, and HOOK-03d land the stood-down split — a mode declares
whether it means the session is at a halt, and two behaviors read it. The other
+2 corrects this header, which read 163 against a category table summing to 165;
the table was right.

### 2026-08-24 — Coverage refresh (spec-status)

163 IDs, all Covered, 0 needs-decision. Net −2: STATE-14 and HOOK-11 retired
with the `handoff` mode — the mode set is now `dev`, `pause`, `release`,
`retro`, `done`. `AUTO_RESUME_MODES` drops to one member (STATE-04) and
`_skill_invocation` / `SLASH_COMMAND_RE` go with HOOK-11, their only caller.

### 2026-08-24 — Full spec-sync + coverage refresh (spec-sync, spec-status)

Coverage unchanged at 169/169 Covered. CLI-18 (audit table, `HideTab`,
`StatusBarPosition` → top), STATUS-BAR-01 (colour inheritance, pane-scoped
`AWDS Pane Option`), STATUS-BAR-09 (button width cap) and RENDER-05 (three
colour keys per mode background) gained evidence. Both divergences the sync
found were fixed in the same pass: the `resolve-url` orphan deleted, and
PERF-01..04 normalized onto the current ID-heading form.

### 2026-08-21 — Coverage refresh (spec-status)

165 IDs, all Covered, 0 needs-decision. Net −4 for the mode/activity split
(#38): RES-06/-07 and THEME-02a added; RES-03, PROV-03, OVR-05, STATE-03,
STATE-04a, STATE-05 and BADGE-10 retired. RES-04/-05 keep their original
numbers — an earlier draft renumbered them down into RES-03's slot, which would
have silently changed what two published IDs mean; the pre-existing RES-05
cross-references at BADGE-03 and §6.6 (which meant the task rule, RES-04) are
corrected in the same pass.

### 2026-08-20 — Coverage refresh (spec-status)

167 IDs, all Covered, 0 needs-decision. Net −2: SKILL-01/02/03 and CMD-18
retired, CMD-25 (`/beacon:pause`) and CMD-26 (`/beacon:install-beacon`) added. CMD-13
rewritten in place — `install-cli` folds into CMD-08, which gains `--dir` — and
CMD-17 loses the `/beacon:beacon` bare-invocation clause with the command. Two
slash commands remain, both user-invocable only, so no model-facing beacon
surface is a command.
### 2026-08-18 — Coverage refresh (spec-status)

STATUS.md updated: coverage unchanged at 171 Covered; HOOK-11 amended in place
to cover the typed `/tack:end` slash command alongside the `Skill` tool call,
and STATE-04 to name the two prompts that set a mode rather than leaving one.

### 2026-08-17 — Add the `handoff` mode state (spec-status)

+2 IDs (STATE-14, HOOK-11), both Covered. Adds `handoff` alongside `paused` /
`release` / `retro` / `done`: a mode state for a session mid-transition to
another tool/skill/session, entered by hand (`beacon handoff`, STATE-14) or
automatically when `PostToolUse` observes a `Skill` call naming tack's
`tack:end` session-close skill (HOOK-11). It borrows only `paused`'s
auto-resume trait (STATE-04, generalized to `AUTO_RESUME_STATUSES`) — no
identity-freeze snapshot, no watermark image, no other trace of `paused`'s
semantics. Every mode-name enumeration this touches (STATE-01/04/08/09/11/13,
HOOK-03a/09, CMD-04/18, WIP-03/17, BADGE-09a/11, RENDER-04/05, THEME-02,
STATUS-BAR-01, and the §4/§6 surface lists) was amended in place rather than
minted as new IDs, matching how `done` was added.

### 2026-08-05 — Coverage refresh (spec-status)

169 IDs unchanged, all Covered, 0 needs-decision. No new IDs. Records the
STATUSLINE row note the status-line wiring commit amended in place: `install`
writes the `statusLine` key into `~/.claude/settings.json` (`_install_statusline`),
and STATUSLINE-03's session scope now takes a route's open work — `pending` as
well as `in_progress` (`_OPEN_TACK_STATUSES`, `_tack_in_session_scope`).

### 2026-08-03 — Status-line link held to the session window (spec-status)

No new IDs. **STATUSLINE-02** amended in place: the fallback link renders the
resolved URL whenever the deliverables list is empty, which is every fresh
session, so the pre-session delivery STATUSLINE-03 had just stopped recording
came back through that path. The persisted link now substitutes PROV-07's
location tiers in that case (`_location_url_at`); click-time `↖ web` keeps the
unsubstituted answer. STATUSLINE-03's own note is unchanged, and its
"serviceable click target" rationale now names only `↖ web`.

### 2026-08-03 — Coverage refresh (spec-status)

STATUS.md updated: 169 IDs unchanged, all Covered, 0 needs-decision. No new IDs;
seven requirements were amended in place and their row notes re-sourced —
HOOK-08a (stamps `session_started_at`), HOOK-09 / TITLE-04 (the disengage name
handback and its ordering ahead of the var blanking), TITLE-02 (§6.10 caveat 7,
the session name as a profile-`Name` override), WIP-06 (`prune` sweeps the
per-pane cache), STATUSLINE-03 (row acquisition scoped to one Claude session),
and STATUS-BAR-07 (default `cmd` now a bare `code`).

### 2026-08-02 — Coverage refresh (spec-status)

STATUS.md updated: 164 → 169 IDs, all Covered, 0 needs-decision. +1 new
(CMD-24, `drop`); +4 that existed in the spec but had never been balanced into
the table (BADGE-15, CLI-18, TITLE-05, TITLE-06). Retired the 2026-07-30
hand-reconciliation caveat: the three untallied rows it flagged are now
reconciled, and the `PERF-01..04` row was never sourceless — PERF declares its
ids as `**[PERF-NN]**` where every other domain uses `**XX-NN.**`, so a count
reading only the second form missed the block. Corrected the numbering-gaps note,
which listed BADGE-15 as retired while the id was live. STATUSLINE-03's note now
records the tack-route acquisition path (issue #31).

### 2026-07-08 — `review` delegates to anchor on the default branch (issue #13)

No new IDs. Amended **CMD-16** and **NFR-06** in place: on the default branch
with a dirty working tree, `beacon review` now delegates to anchor's
`review-diff.sh --local` (working-tree vs `HEAD`) instead of reporting "nothing
to review", relaying its `REVIEW_VERDICT` / `REVIEW_OUTPUT` verbatim. anchor is a
soft dependency (NFR-06) probed via Claude Code's plugin registry
(`~/.claude/plugins/installed_plugins.json`, `_anchor_review_script`) rather than
`_which`, since it ships as a plugin, not a `$PATH` binary; absent anchor or a
clean tree stays inert, with no beacon-native copy of the diff. Feature-branch
behavior (`<default>...HEAD`) is untouched. Count unchanged (158).

### 2026-07-08 — TITLE + DUMP domains, /rename fold (hand reconciliation, 1.21.0)

Ledger had drifted two releases behind (still read 1.19.0). Reconciled by hand
because `/sextant:spec-status` is model-invocation-disabled. Added the **TITLE**
row (TITLE-01..04, §4.8 window title — landed 1.20.0, never balanced into the
table) and the **DUMP** row (DUMP-01..04, export/import — 1.21.0). PROV-02 now
folds a `/rename` into the task override (recency-wins) and PROV-02a's wander
marker became a ` @ ` separator; the PROV row notes were updated in 1.21.0.
Fixed a dangling `DUMP-05` reference in `scripts/beacon` (the spec defines only
DUMP-01..04). Still owed: a full `spec-status` pass to reconcile the per-domain
row counts to 158 (the `PERF-01..04` row has no matching spec IDs; the `CLI` row
undercounts by one) — flagged in the header.

### 2026-07-07 — SDLC cycle profiles (new-feature, hand audit for 1.19.0)

Statuses reorganized into named SDLC cycles (STATE-13). The dev cycle
(`idle`/`working`/`waiting`) keeps the dynamic stoplight but green is retired
from it — at rest is now a neutral gray — so green can pin the new `release`
mode (STATE-11, `beacon-release`, a launch-sky navy pane + rocket watermark).
`wrapping` → `retro` and `releasing` → `release`; the base profile `beacon` →
`beacon-dev` and the mode profiles → `beacon-pause` / `beacon-release` /
`beacon-retro` / `beacon-done` (install sweeps the old names). `done` now
suppresses the task, keeping the project (STATE-12). The `||` badge/fleet glyph
is gone — BADGE-11 rewritten so every cycle reads by background + color alone.
New IDs: STATE-11, STATE-12, STATE-13, CMD-22 (`/beacon:release`); the two
append collisions caught in review (STATE-10 vs `pause --clear-screen`, CMD-21
vs `data-dir`) were renumbered so the shipped IDs kept their meaning. Colors
stay Dracula-sourced (THEME-01). Docs: new **The beacon palette** page +
refreshed fleet screenshots. Coverage 149 → 153, all Covered.

### 2026-07-06 — Delete pending-attention orphan + fix BADGE-04/05 drift (hand fix)

Removed the never-read `pending_attention_type` capture: the Notification handler
now writes a constant `pending-attention` marker (presence still forces `blocked`
via `_logical_state_for`, unchanged), and the `resolve()` + wip-record
pass-throughs and the stale `BADGE-15` comment are gone. Reworded BADGE-04/05 to
attribute the badge project + PROV-05 root walk to the plugin (`_publish_anchor`),
since the shell no longer writes `beacon_project` (BADGE-02). No ID count change
(148). All 195 unit tests green.

### 2026-07-06 — Resolve CMD-16 duplicate (hand fix)

Renumbered the duplicated `data-dir` requirement from CMD-16 to **CMD-21**
(relocated to the end of the CMD block); `review` keeps CMD-16. All other CMD-16
references (§4.1 review button, `scripts/beacon`, `tests/`) point to `review` and
are unaffected. 147 → 148 distinct IDs (the doubled ID is now two).

### 2026-07-06 — Capture dashboard/hook drift (spec-sync --to-spec)

+4 IDs. Canonized four spec-silent drift items surfaced by the same-day refresh:
WIP-15 (same-project z-stack collapse), WIP-16 (automatic route-group grouping,
groupless headerless at bottom, no toggle), RENDER-06 (beacon profile disables
iTerm2's native notifications), HOOK-10 (SessionStart emits the bundled ambient
rules). A fifth item — the waiting-pill focus affordance — was reviewed and
declined as over-specifying the restyleable reference dashboard. 143 → 147
Covered. CMD-16 duplicate and the `pending_attention_type` orphan remain open
(defect / needs-decision, not drift to canonize).

### 2026-07-06 — Full spec-sync refresh to v1.17.0 (spec-sync)

Ledger was stale at v1.9.0 (137). Full-domain sweep of all 143 requirement IDs
against the code: still 0 Missing, 0 Contradicts. +6 IDs Covered since the last
audit — PROV-09, STATE-09 (`done`), STATE-10 (`pause --clear-screen`), CMD-20
(`/beacon:done`), WIP-13 (`agent_color`), WIP-14 (`latest_turn_full` +
`/turn/<hash>`). 137 → 143 Covered. Surfaced one spec defect (CMD-16 duplicated),
one orphan (`pending_attention_type`), five spec-silent dashboard/hook drift
items, and requirement-quality flags — all recorded under **Open items**; none
written to the spec (default mode proposes, doesn't canonize).

### 2026-06-22 — Mode profiles: paused background + `||` glyph + wrapping (new-feature)

+5 IDs. Background-on-pause family: RENDER-05 (a **mode state** owns a dedicated
dynamic profile — `MODE_SPECS` — for a background a color OSC can't set; the
swap re-emits the badge format, user vars, and badge/tab color it wipes), BADGE-11
(the `||` pause glyph prefixes the badge text while paused), WIP-12 (the same glyph
prefixes the paused reason across the human table, `watch`, and the dashboard).
New `wrapping` mode (post-work follow-up / retro): STATE-08 (`wrap` synonym, persists,
no freeze, no auto-resume) and CMD-19 (`/beacon:wrap` shim). `paused` gains a muted
purple background `#3c3357` + a faint `||` background image (`iterm/paused-bg.png`);
`wrapping` is a muted green `#2c4636` with a teal-green badge `#34c79d`. §4.1's
do-not-paint list now scopes the background (color + image) as a mode-only exception.
132 → 137 Covered.

### 2026-06-20 — Coverage refresh (spec-status)

+1 ID for the 1.9.0 release: WIP-11 (auto-derived `latest_turn` in the wip
payload — the session's most recent human/agent turn, written at hook time and
ellipsized to card width by the dashboard). 131 → 132 Covered.

### 2026-06-17 — Coverage refresh (spec-status)

+1 ID for the 1.8.0 release: WIP-10 (bundled reference dashboard served at `/`,
`dashboard/index.html`, with the cross-platform fleet-view work). 130 → 131
Covered.

### 2026-06-17 — Coverage refresh (spec-status)

+6 IDs for the 1.7.0 release: WIP-09 (session→tack bound `tacks` in the wip
payload), CMD-18 (`/beacon:pause` shim), PERF-01..04 (fleet-scan performance
objectives + `wip --timing`). STATE-03 reworded — the paused snapshot now reads
the cached `resolved` state instead of re-resolving (network-free, preserves
overrides); still Covered, no count change. 124 → 130 Covered.

### 2026-06-09 — Coverage refresh (spec-status)

WIP-03 extended: paused sessions are exempt from the activity window (`collect_sessions` in `scripts/beacon`, `test_since_exempts_paused_sessions`). Still Covered, no count change.

### 2026-06-08 — Project icons (new-feature)

Added the `icon` provider chain (PROV-08), the `icon` field + `/icon/<hash>`
serve route (WIP-01 extended, WIP-08 new), and the dedicated `icon` override
(OVR-05). The fleet view now carries each project's favicon so a dashboard can
tell work streams apart. 118 → 121 Covered.

### 2026-06-07 — Coverage refresh (spec-status)

1.0 pivot landed in the code: FOCUS-01..04 + CLI-17 (dashboard focus) now
Covered; CMD-08 / RENDER-04 (was Contradicts) and STATUS-BAR-01 / TAB-01 (was
Partial) now Covered — color is OSC `badge-color`/`tab-color` over the single
base profile and the `focus` chain ships. NFR row count corrected 11 → 10
(NFR-02 retired, not coverage). 110 → 118 Covered; 0 Partial, 0
Missing/Contradicts. Open / Needs Decision section removed (no open items).

### 2026-06-07 — Coverage refresh (spec-status)

PROV-02a behavior revised (the @<project> marker now applies only while working and clears at rest); still Covered, no count change. Added HOOK-09 (SessionEnd disengages the pane), Covered; 109 → 110 Covered.

### 2026-06-06 — Coverage refresh (spec-status)

PROV-02a behavior revised (wander now prefixes an @<project> marker plus task); still Covered, no count change.

### 2026-06-05 — Coverage refresh (spec-status)

STATUS.md updated: +1 ID (PROV-02a, Covered), 108 → 109 Covered.

## How to use this file

When you implement a new requirement, change the row's status and add an
evidence pointer. When an audit reveals drift, update the row to **Partial**
or **Contradicts** with a one-line note.

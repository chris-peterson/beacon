# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`SPEC.md`](SPEC.md).
Maintained by `/sextant:spec-status`.

**Last audit:** 2026-08-02
**Spec version:** v2 (root-level, `SPEC.md`)
**Coverage:** 169 spec requirement IDs, all implemented (0 Missing, 0 Contradicts).
2.0 moves per-session values into the Claude Code status line: STATUSLINE-02
(the resolved URL as an OSC-8 link) and STATUSLINE-03 (accumulated
deliverables) join STATUSLINE-01, and STATUS-BAR-07 makes the `↗ code` editor
configurable, and STATUS-BAR-08 gives `↖ web` a click-time resolver plus a
user-command knob (its URL *handoff file* is what 2.0 retires, not the chip).
STATUS-BAR-02 drops `⇄ review`, whose whole feature went with it (CMD-16
retired, along with the `moor` / `anchor` soft deps that served it).
CMD-19/20/22 retire into a single CMD-18 (`/beacon:session-mode`).

The plugin version is **not** recorded here: the release workflow bumps
`plugin.yml` / `.claude-plugin/plugin.json` when a GitHub Release is published,
so a hand-written version in this file goes stale the moment CI runs.

The spec declares IDs in two forms — `**XX-NN.**` throughout, and `**[PERF-NN]**`
for the PERF block. Both are normative; a count that reads only the first misses
PERF entirely, which is what made the `PERF-01..04` row look sourceless.

Status (`signal.status`) has seven values, organized into **SDLC cycles**
(STATE-13): the **dev** cycle — `idle` / `working` / `waiting` — maps to the
dynamic `ready` / `busy` / `blocked` stoplight (a neutral gray at rest, green
retired from it, BADGE-09), and rides the base `beacon-dev` profile. `paused`,
`release`, `retro`, and `done` are **mode states** — each a distinct badge color
plus a dedicated dynamic profile (background) it swaps into (RENDER-05). No mode
decorates the badge text; the cue is background + color (BADGE-11). `done` also
suppresses the task slot, keeping the project (STATE-12).

**1.0 pivot (landed).** The 1.0 spec retired the iTerm2 marginalia overlay, the
`!` / `?` watermarks, the per-state dynamic profiles, `exclusive-configuration`,
and all background-image machinery, and added dashboard-driven session focus
(FOCUS, CLI-17). The code has converged: `focus` ships (`bin/beacon-iterm
focus`, the `POST /focus` route, the recorded `iterm_session_id` handle), color
is OSC `badge-color` / `tab-color` on the base `beacon-dev` profile switched
in via `set-profile`, and the retired surfaces are gone — `install_dynamic_profile`
sweeps the per-state profiles a pre-1.0 install (and the pre-SDLC-rename names)
left behind. A bounded set of per-state profiles returns by design — the **mode
profiles** (`beacon-pause` / `beacon-release` / `beacon-retro` / `beacon-done`):
a mode state swaps into its profile for a background a color OSC can't express
(RENDER-05); the dev cycle (ready/busy/blocked) stays OSC overlays on the base.

## Status by category

| Prefix | Covered | Status | Notes |
|--------|--------:|--------|-------|
| RES-01..05 | 5 | All Covered | Signal resolution model |
| PROV-01..03 (incl. 02a), 05, 06 | 6 | All Covered | Provider chains (no PROV-04); PROV-02 folds a `/rename` into the task override (recency-wins); PROV-02a joins the wandered project to home with a ` @ ` separator while working, clearing it at rest |
| PROV-07 | 1 | Covered | `url` chain; branch-slug match (`scripts/beacon` `_tack_url_for`) |
| PROV-08 | 1 | Covered | `icon` chain: override → discovered project favicon (`_discover_icon_at`), anchored at SessionStart |
| PROV-09 | 1 | Covered | Harvest Claude Code `/color` / `/rename` / `ai-title` from the transcript tail (`_read_cc_signals`); custom/ai-title feed the task chain, agent-color is fleet-view-only (WIP-13); wiped by HOOK-08a |
| HOOK-01, 01a, 02, 03, 03a..03c, 08, 08a, 08b, 09, 10 | 12 | All Covered | Hook handlers; HOOK-03/03b simplified — permission/idle no longer distinguished on the pane; HOOK-09 disengages the pane on SessionEnd; HOOK-10 emits the bundled ambient rules (`hooks/emit-rules.sh`, `keep-session-labeled`) at SessionStart |
| OVR-01..05 | 5 | All Covered | User overrides; OVR-05 is the dedicated `icon` override (set/clear, outside the `set <field>` set) |
| STATE-01..13 (incl. 04a) | 14 | All Covered | User-set status; description persisted + exported to the fleet view (no pane overlay); STATE-03 paused snapshot reads the cached `resolved` state (network-free, preserves overrides), `PauseSnapshotIsNetworkFree`; STATE-08 is the `retro` synonym for `status retro`; STATE-09 is the `done` mode (`cmd_done`, no snapshot, no auto-resume); STATE-10 is `pause --clear-screen` (`_cli("clear-screen")`, `cmd_clear_screen` in `bin/beacon-iterm`); STATE-11 is the `release` synonym (`cmd_release`); STATE-12 suppresses the task while `done` (blanked in `resolve`, `test_done_suppresses_task_keeps_project`); STATE-13 is the SDLC-cycle grouping (`MODE_PROFILES` keyed by cycle) |
| SKILL-01..03 | 3 | All Covered | CLI-freshness + conventions |
| CMD-01..09, 13..15, 17, 18, 21, 23, 24 (gap 10, 11; CMD-12, 16, 19, 20, 22 retired) | 17 | All Covered | CMD-24 is `drop <ref>`, which takes one deliverable off the status-line row and remembers the removal in `deliverables.dropped` so route re-reads don't restore it (`cmd_drop`); CMD-08 install writes the base + mode dynamic profiles; CMD-16 retired in 2.0 with the branch-review feature (chip + `beacon review` subcommand + the moor/anchor soft deps); CMD-18 is the single `/beacon:session-mode <mode>` shim (no model pin) that CMD-19/20/22 folded into in 2.0 (issue #23); CMD-21 is `data-dir` (renumbered 2026-07-06 from a duplicate CMD-16); CMD-23 is `install-profile`, the profile-only re-render that applies a changed button label (`cmd_install_profile`) |
| WIP-01..17 | 17 | All Covered | Cross-session introspection / export; WIP-01 emits `focusable` (FOCUS-03) + `icon` (PROV-08) + `latest_turn` (WIP-11); WIP-08 is the `/icon/<hash>` serve route; WIP-09 emits the session→tack bound `tacks` (route-qualified, existing/emerging); WIP-10 is the bundled reference dashboard `serve` hosts at `/` (`dashboard/index.html`); WIP-11 is the auto-derived `latest_turn` (human prompt / agent reply), written at hook time, ellipsized to card width by the dashboard; WIP-12: no state carries a text glyph — every fleet row reads by its color dot and `status` (the dashboard conveys a mode via the WIP-17 card treatment); WIP-13 emits `agent_color` (fleet-view identity pill only, never painted); WIP-14 persists `latest_turn_full` + serves it at `GET /turn/<hash>` for card expansion; WIP-15 collapses same-project sessions into a z-stack (newest front, raise on demand); WIP-16 auto-groups the fleet by route group (groupless in an unlabeled bottom section, no toggle); WIP-17 gives mode-state cards the pane-analog treatment (muted tint + centered `||` / rocket / clipboard / finish-flag watermark) and keeps a mode session out of the attention band |
| WATCH-01..02 | 2 | All Covered | Live person-facing recency feed |
| DUMP-01..04 | 4 | All Covered | `export` / `import` full-fidelity per-session state backup (`_export_payload`, `cmd_export`, `cmd_import`); versioned JSON envelope, gzip optional, mtimes preserved (DUMP-03), hex-hash + path-traversal guard on import; DUMP-04 treats the dump as sensitive (raw payload is the product, not shape-only) |
| COLOR-01 | 1 | Covered | `--color` + `NO_COLOR` / `FORCE_COLOR` precedence |
| FOCUS-01..04 | 4 | All Covered | Dashboard focus: `POST /focus` route + `_focus_session`, `iterm_session_id` handle (FOCUS-02), `focusable` in payload (FOCUS-03), loopback + Host/Origin guard (FOCUS-04) |
| FORGET-01..03 | 3 | All Covered | Dashboard forget: `forget <hash>` CLI + `POST /forget` route → `_forget_session` (FORGET-01), hex-hash guard (FORGET-02), shared FOCUS-04 access model (FORGET-03); tests in `ForgetTest` |
| PERF-01..04 | 4 | All Covered | Fleet-scan cost scales with emitted, not total sessions: `_session_mtimes` single dir scan, `_branch_for` per-cwd memoization, two-phase `collect_sessions` (cheap resolve → dedup → window → branch-fill), `wip --timing` (PERF-03); `test_branch_probe_memoized_per_cwd` |
| CLI-01..12, 14, 16..18 (gap 13; CLI-04/05/15 retired) | 15 | All Covered | CLI-16 is the `--help` usage table; CLI-17 `focus` via osascript (`cmd_focus` in `bin/beacon-iterm`); CLI-18 is `configure`, the one path that writes an iTerm2 preference — explicit, user-invoked, quit-write-relaunch (`cmd_configure`), never reachable from a hook or render |
| BADGE-01..15 (incl. 09a; BADGE-08 retired) | 15 | All Covered | Badge text + color + engagement; watermark removed; BADGE-09 stoplight is gray/orange/red (green retired to `release`); BADGE-11 leaves the badge text undecorated — no mode glyph, the cue is background + color; BADGE-15 is **not** the retired watermark — the id was reused for the opt-in badge gate (off by default, `"badge": "on"` in the user config, read via `config-get` at all three paint sites) |
| TITLE-01..06 | 6 | All Covered | OS window title via the iTerm2 session *name* (Apple Events `set-name`; profile `Allow Title Setting: false`); TITLE-01 interactive panes fall back to the cwd (`beacon_title` = project else cwd); TITLE-04 one-shot re-assert on the first turn boundary reclaims the title from the shell's backgrounded launch write; TITLE-05 is the two-line tab label (`TITLE_FORMAT`, `<b>project</b>` over the indented `beacon_task_nl`), whose line 1 doubles as the single-line OS window title; TITLE-06 leads line 1 with `PAUSED_TITLE_GLYPH` (`⏸`) via `beacon_title_prefix` while paused, marking the parked state where the tab color isn't legible |
| STATUS-BAR-01..03, 05..09 (gap 04) | 8 | All Covered | STATUS-BAR-01: runtime `set-profile` activation (plugin first render + install writes the base + mode profiles); STATUS-BAR-02 dropped the `⇄ review` chip in 2.0, leaving `↖ web` and `↗ code` to bookend the strip; STATUS-BAR-07 is the configurable `↗ code` editor and STATUS-BAR-08 the `↖ web` chip resolving at click time via `cmd_open_url <cwd>`, both reached through an absolute interpreter path and the login-shell binary lookup, since an action shell has no interactive `PATH` (issue #25, §6.10 caveat 3); STATUS-BAR-09 is the `statusbar.buttons.<name>` block behind both — `cmd` read on the click (with `{dir}` / `{project}` / `{branch}` expanded per argument by `_substitute_cmd_tokens`, `{dir}` suppressing the editor append), `label` baked into the profile by `install_dynamic_profile` and applied by CMD-23 (issue #29) |
| STATUSLINE-01..03 | 3 | All Covered | Claude Code status-line provider (`cmd_statusline`): STATUSLINE-01 the ` · `-joined row (pause reason, silent when every segment is empty); STATUSLINE-02 the resolved URL as an OSC-8 link read from persisted `resolved.url` state, never re-resolving (issue #26); STATUSLINE-03 the accumulated `deliverables` list, bare vs project-qualified, capped and deduped, dropped by the fresh-start wipe (issue #18), acquired from the bound tack route plus PROV-07's own resolution with each entry's project taken from its own URL (issue #31) |
| RENDER-01..06 | 6 | All Covered | RENDER-04: OSC `badge-color` / `tab-color` on the base `beacon-dev` profile for the dev cycle (ready/busy/blocked); RENDER-05: mode states (`paused`, `release`, `retro`, `done`) swap into a dedicated profile (distinct background; `paused`/`release`/`done` also a faint watermark image) and re-emit the wiped OSC; RENDER-06: the beacon profile disables iTerm2's native notification-center + terminal-generated alerts (deduped against BADGE-09 color); the `MODE_PROFILES` table owns the mode mapping |
| TAB-01..03 | 3 | All Covered | TAB-01: OSC `tab-color` on every status change, mirroring the badge state |
| THEME-01..03 | 3 | All Covered | Dracula palette across badge, tab, status-bar chips (blocked-idle row removed) |
| NFR-01, 03..11 (NFR-02 retired) | 10 | All Covered | Timing reqs advisory; NFR-04 bounds `focus`; NFR-06 soft deps are `tack` / `gh` / `glab` / `osascript`, all `_which`-probed — the `moor` and `anchor` deps went with the branch-review feature in 2.0 |

Numbering gaps (no PROV-04, no CMD-10/CMD-11, no CLI-13, no
STATUS-BAR-04) are intentional. IDs retired in the 1.0 pivot — CMD-12
(`exclusive-configuration`), CLI-04/05/15 (`bg-image` / `note` /
`clear-screen`), BADGE-08 and BADGE-15 (watermark), NFR-02 (overlay caching),
and the entire OVERLAY namespace — are removed, not missing coverage.

Two of those ids were later reused rather than left fallow, and both reuses are
live contract: the `clear-screen` CLI *capability* returned under STATE-10
(`pause --clear-screen`) — not as a re-issued CLI-15, which stays retired — and
**BADGE-15** now numbers the opt-in badge gate. `exclusive-configuration` also
returned, as CLI-18's quit-write-relaunch orchestration, under a new id.

## Open items (from the 2026-07-06 spec-sync)

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
top band, removed from the fleet below) is *already* WIP-10 ("a prominent band
above the calmer fleet") — recent code realigned to it, not drift.

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
dynamic profile — `MODE_PROFILES` — for a background a color OSC can't set; the
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

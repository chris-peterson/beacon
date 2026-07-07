# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`docs/spec.md`](docs/spec.md).
Maintained by `/sextant:spec-status`.

**Last audit:** 2026-07-07
**Spec version:** v1 (root-level, `docs/spec.md`)
**Plugin version:** 1.19.0
**Coverage:** 153 requirement IDs — all implemented (0 Missing, 0 Contradicts),
0 open divergences. 1.19.0 adds STATE-11 / STATE-12 / STATE-13 and CMD-22 (see the audit history).

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
| PROV-01..03 (incl. 02a), 05, 06 | 6 | All Covered | Provider chains (no PROV-04); PROV-02a prefixes the task slot with an @<wandered-project> marker while working, clearing it at rest |
| PROV-07 | 1 | Covered | `url` chain; branch-slug match (`scripts/beacon` `_tack_url_for`) |
| PROV-08 | 1 | Covered | `icon` chain: override → discovered project favicon (`_discover_icon_at`), anchored at SessionStart |
| PROV-09 | 1 | Covered | Harvest Claude Code `/color` / `/rename` / `ai-title` from the transcript tail (`_read_cc_signals`); custom/ai-title feed the task chain, agent-color is fleet-view-only (WIP-13); wiped by HOOK-08a |
| HOOK-01, 01a, 02, 03, 03a..03c, 08, 08a, 08b, 09, 10 | 12 | All Covered | Hook handlers; HOOK-03/03b simplified — permission/idle no longer distinguished on the pane; HOOK-09 disengages the pane on SessionEnd; HOOK-10 emits the bundled ambient rules (`hooks/emit-rules.sh`, `keep-session-labeled`) at SessionStart |
| OVR-01..05 | 5 | All Covered | User overrides; OVR-05 is the dedicated `icon` override (set/clear, outside the `set <field>` set) |
| STATE-01..13 (incl. 04a) | 14 | All Covered | User-set status; description persisted + exported to the fleet view (no pane overlay); STATE-03 paused snapshot reads the cached `resolved` state (network-free, preserves overrides), `PauseSnapshotIsNetworkFree`; STATE-08 is the `retro` synonym for `status retro`; STATE-09 is the `done` mode (`cmd_done`, no snapshot, no auto-resume); STATE-10 is `pause --clear-screen` (`_cli("clear-screen")`, `cmd_clear_screen` in `bin/beacon-iterm`); STATE-11 is the `release` synonym (`cmd_release`); STATE-12 suppresses the task while `done` (blanked in `resolve`, `test_done_suppresses_task_keeps_project`); STATE-13 is the SDLC-cycle grouping (`MODE_PROFILES` keyed by cycle) |
| SKILL-01..03 | 3 | All Covered | CLI-freshness + conventions |
| CMD-01..09, 13..22 (gap 10, 11; CMD-12 retired) | 19 | All Covered | CMD-08 install writes the base + mode dynamic profiles; CMD-16 is `review` (backs the `⇄ review` status-bar button); CMD-18/19/20/22 are the `/beacon:pause` / `retro` / `done` / `release` shims (no model pin); CMD-21 is `data-dir` (renumbered 2026-07-06 from a duplicate CMD-16) |
| WIP-01..17 | 17 | All Covered | Cross-session introspection / export; WIP-01 emits `focusable` (FOCUS-03) + `icon` (PROV-08) + `latest_turn` (WIP-11); WIP-08 is the `/icon/<hash>` serve route; WIP-09 emits the session→tack bound `tacks` (route-qualified, existing/emerging); WIP-10 is the bundled reference dashboard `serve` hosts at `/` (`dashboard/index.html`); WIP-11 is the auto-derived `latest_turn` (human prompt / agent reply), written at hook time, ellipsized to card width by the dashboard; WIP-12: no state carries a text glyph — every fleet row reads by its color dot and `status` (the dashboard conveys a mode via the WIP-17 card treatment); WIP-13 emits `agent_color` (fleet-view identity pill only, never painted); WIP-14 persists `latest_turn_full` + serves it at `GET /turn/<hash>` for card expansion; WIP-15 collapses same-project sessions into a z-stack (newest front, raise on demand); WIP-16 auto-groups the fleet by route group (groupless in an unlabeled bottom section, no toggle); WIP-17 gives mode-state cards the pane-analog treatment (muted tint + centered `||` / rocket / ⏻ watermark) and keeps a mode session out of the attention band |
| WATCH-01..02 | 2 | All Covered | Live person-facing recency feed |
| COLOR-01 | 1 | Covered | `--color` + `NO_COLOR` / `FORCE_COLOR` precedence |
| FOCUS-01..04 | 4 | All Covered | Dashboard focus: `POST /focus` route + `_focus_session`, `iterm_session_id` handle (FOCUS-02), `focusable` in payload (FOCUS-03), loopback + Host/Origin guard (FOCUS-04) |
| FORGET-01..03 | 3 | All Covered | Dashboard forget: `forget <hash>` CLI + `POST /forget` route → `_forget_session` (FORGET-01), hex-hash guard (FORGET-02), shared FOCUS-04 access model (FORGET-03); tests in `ForgetTest` |
| PERF-01..04 | 4 | All Covered | Fleet-scan cost scales with emitted, not total sessions: `_session_mtimes` single dir scan, `_branch_for` per-cwd memoization, two-phase `collect_sessions` (cheap resolve → dedup → window → branch-fill), `wip --timing` (PERF-03); `test_branch_probe_memoized_per_cwd` |
| CLI-01..12, 14, 16, 17 (gap 13; CLI-04/05/15 retired) | 13 | All Covered | CLI-17 `focus` via osascript (`cmd_focus` in `bin/beacon-iterm`) |
| BADGE-01..14 (incl. 09a; BADGE-15 retired) | 15 | All Covered | Badge text + color + engagement; watermark removed; BADGE-09 stoplight is gray/orange/red (green retired to `release`); BADGE-11 leaves the badge text undecorated — no mode glyph, the cue is background + color |
| STATUS-BAR-01..03, 05, 06 (gap 04) | 5 | All Covered | STATUS-BAR-01: runtime `set-profile` activation (plugin first render + install writes the base + mode profiles) |
| RENDER-01..06 | 6 | All Covered | RENDER-04: OSC `badge-color` / `tab-color` on the base `beacon-dev` profile for the dev cycle (ready/busy/blocked); RENDER-05: mode states (`paused`, `release`, `retro`, `done`) swap into a dedicated profile (distinct background; `paused`/`release`/`done` also a faint watermark image) and re-emit the wiped OSC; RENDER-06: the beacon profile disables iTerm2's native notification-center + terminal-generated alerts (deduped against BADGE-09 color); the `MODE_PROFILES` table owns the mode mapping |
| TAB-01..03 | 3 | All Covered | TAB-01: OSC `tab-color` on every status change, mirroring the badge state |
| THEME-01..03 | 3 | All Covered | Dracula palette across badge, tab, status-bar chips (blocked-idle row removed) |
| NFR-01, 03..11 (NFR-02 retired) | 10 | All Covered | Timing reqs advisory; NFR-04 bounds `focus` |

Numbering gaps (no PROV-04, no CMD-10/CMD-11, no CLI-13, no
STATUS-BAR-04) are intentional. IDs retired in the 1.0 pivot — CMD-12
(`exclusive-configuration`), CLI-04/05/15 (`bg-image` / `note` /
`clear-screen`), BADGE-15 (watermark), NFR-02 (overlay caching), and the entire
OVERLAY namespace — are removed, not missing coverage. (The `clear-screen` CLI
*capability* later returned under STATE-10 — `pause --clear-screen` — but not as
a re-issued CLI-15 id; CLI-15 stays retired.)

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

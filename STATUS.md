# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`docs/spec.md`](docs/spec.md).
Maintained by `/sextant:spec-status`.

**Last audit:** 2026-06-09
**Spec version:** v1 (root-level, `docs/spec.md`)
**Plugin version:** 1.5.0
**Coverage:** 121 Covered, 0 Partial, 0 Missing/Contradicts.

Status (`signal.status`) has four values — `idle`, `working`, `waiting`,
`paused` — mapping to three logical badge color states (`ready` / `busy` /
`blocked`), with `paused` adding a de-emphasized gray. Pause is a status value,
not a separate concept (STATE).

**1.0 pivot (landed).** The 1.0 spec retired the iTerm2 marginalia overlay, the
`!` / `?` watermarks, the per-state dynamic profiles, `exclusive-configuration`,
and all background-image machinery, and added dashboard-driven session focus
(FOCUS, CLI-17). The code has converged: `focus` ships (`bin/beacon-iterm
focus`, the `POST /focus` route, the recorded `iterm_session_id` handle), color
is OSC `badge-color` / `tab-color` on the single base `beacon` profile switched
in via `set-profile`, and the retired surfaces are gone — `install_dynamic_profile`
sweeps the per-state profiles a pre-1.0 install left behind.

## Status by category

| Prefix | Covered | Status | Notes |
|--------|--------:|--------|-------|
| RES-01..05 | 5 | All Covered | Signal resolution model |
| PROV-01..03 (incl. 02a), 05, 06 | 6 | All Covered | Provider chains (no PROV-04); PROV-02a prefixes the task slot with an @<wandered-project> marker while working, clearing it at rest |
| PROV-07 | 1 | Covered | `url` chain; branch-slug match (`scripts/beacon` `_tack_url_for`) |
| PROV-08 | 1 | Covered | `icon` chain: override → discovered project favicon (`_discover_icon_at`), anchored at SessionStart |
| HOOK-01, 01a, 02, 03, 03a..03c, 08, 08a, 08b, 09 | 11 | All Covered | Hook handlers; HOOK-03/03b simplified — permission/idle no longer distinguished on the pane; HOOK-09 disengages the pane on SessionEnd |
| OVR-01..05 | 5 | All Covered | User overrides; OVR-05 is the dedicated `icon` override (set/clear, outside the `set <field>` set) |
| STATE-01..07 (incl. 04a) | 8 | All Covered | User-set status; description persisted + exported to the fleet view (no pane overlay) |
| SKILL-01..03 | 3 | All Covered | CLI-freshness + conventions |
| CMD-01..09, 13..17 (gap 10, 11; CMD-12 retired) | 14 | All Covered | CMD-08 install runs only the terminal-agnostic steps + the base dynamic profile; exclusive-config / bg-image gone |
| WIP-01..08 | 8 | All Covered | Cross-session introspection / export; WIP-01 emits `focusable` (FOCUS-03) + `icon` (PROV-08); WIP-08 is the `/icon/<hash>` serve route |
| WATCH-01..02 | 2 | All Covered | Live person-facing recency feed |
| COLOR-01 | 1 | Covered | `--color` + `NO_COLOR` / `FORCE_COLOR` precedence |
| FOCUS-01..04 | 4 | All Covered | Dashboard focus: `POST /focus` route + `_focus_session`, `iterm_session_id` handle (FOCUS-02), `focusable` in payload (FOCUS-03), loopback + Host/Origin guard (FOCUS-04) |
| CLI-01..12, 14, 16, 17 (gap 13; CLI-04/05/15 retired) | 13 | All Covered | CLI-17 `focus` via osascript (`cmd_focus` in `bin/beacon-iterm`) |
| BADGE-01..10, 12..14 (incl. 09a; gap 11; BADGE-15 retired) | 14 | All Covered | Badge text + color + engagement; watermark removed |
| STATUS-BAR-01..03, 05, 06 (gap 04) | 5 | All Covered | STATUS-BAR-01: runtime `set-profile` activation (plugin first render + install writes the base profile) |
| RENDER-01..04 | 4 | All Covered | RENDER-04: OSC `badge-color` / `tab-color` on the single base profile, no per-state swap |
| TAB-01..03 | 3 | All Covered | TAB-01: OSC `tab-color` on every status change, mirroring the badge state |
| THEME-01..03 | 3 | All Covered | Dracula palette across badge, tab, status-bar chips (blocked-idle row removed) |
| NFR-01, 03..11 (NFR-02 retired) | 10 | All Covered | Timing reqs advisory; NFR-04 bounds `focus` |

Numbering gaps (no PROV-04, no CMD-10/CMD-11, no CLI-13, no BADGE-11, no
STATUS-BAR-04) are intentional. IDs retired in the 1.0 pivot — CMD-12
(`exclusive-configuration`), CLI-04/05/15 (`bg-image` / `note` /
`clear-screen`), BADGE-15 (watermark), NFR-02 (overlay caching), and the entire
OVERLAY namespace — are removed, not missing coverage.

## Audit history

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

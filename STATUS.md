# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`docs/spec.md`](docs/spec.md).
Maintained by `/sextant:spec-status`.

**Last audit:** 2026-06-05
**Spec version:** v1 (root-level, `docs/spec.md`)
**Plugin version:** 1.1.0
**Coverage:** 109 Covered, 2 Partial, 7 Missing/Contradicts.

Status (`signal.status`) has four values — `idle`, `working`, `waiting`,
`paused` — mapping to three logical badge color states (`ready` / `busy` /
`blocked`), with `paused` adding a de-emphasized gray. Pause is a status value,
not a separate concept (STATE).

**1.0 pivot (in progress).** The 1.0 spec retires the iTerm2 marginalia
overlay, the `!` / `?` watermarks, the per-state dynamic profiles,
`exclusive-configuration`, and all background-image machinery — and adds
dashboard-driven session focus (FOCUS, CLI-17). The code is still pre-pivot, so
the rows below mark the gap: FOCUS + CLI-17 are Missing, and CMD-08 / RENDER-04
/ STATUS-BAR-01 / TAB-01 still implement the retired model. Convergence is
tracked in the implementation issue.

## Status by category

| Prefix | Covered | Status | Notes |
|--------|--------:|--------|-------|
| RES-01..05 | 5 | All Covered | Signal resolution model |
| PROV-01..03 (incl. 02a), 05, 06 | 6 | All Covered | Provider chains (no PROV-04); PROV-02a surfaces a wandered cwd in the task slot |
| PROV-07 | 1 | Covered | `url` chain; branch-slug match (`scripts/beacon` `_tack_url_for`) |
| HOOK-01, 01a, 02, 03, 03a..03c, 08, 08a, 08b | 10 | All Covered | Hook handlers; HOOK-03/03b simplified — permission/idle no longer distinguished on the pane |
| OVR-01..04 | 4 | All Covered | User overrides |
| STATE-01..07 (incl. 04a) | 8 | All Covered | User-set status; description persisted + exported to the fleet view (no pane overlay) |
| SKILL-01..03 | 3 | All Covered | CLI-freshness + conventions |
| CMD-01..09, 13..17 (gap 10, 11; CMD-12 retired) | 14 | 13 Covered, 1 Contradicts | CMD-08 install still runs the retired exclusive-config / bg-image steps — to be gutted |
| WIP-01..07 | 7 | All Covered | Cross-session introspection / export; WIP-01 must add the `focusable` field (FOCUS-03) |
| WATCH-01..02 | 2 | All Covered | Live person-facing recency feed |
| COLOR-01 | 1 | Covered | `--color` + `NO_COLOR` / `FORCE_COLOR` precedence |
| FOCUS-01..04 | 4 | Missing | Dashboard-driven session focus — not yet implemented |
| CLI-01..12, 14, 16, 17 (gap 13; CLI-04/05/15 retired) | 13 | 12 Covered, 1 Missing | CLI-17 `focus` (osascript) not yet implemented |
| BADGE-01..10, 12..14 (incl. 09a; gap 11; BADGE-15 retired) | 14 | All Covered | Badge text + color + engagement; watermark removed |
| STATUS-BAR-01..03, 05, 06 (gap 04) | 5 | 4 Covered, 1 Partial | STATUS-BAR-01: runtime `set-profile` activation (plugin SessionStart + shell on source) not yet wired — code still relies on the default-profile model |
| RENDER-01..04 | 4 | 3 Covered, 1 Contradicts | RENDER-04: code switches per-state profiles; spec now mandates OSC `badge-color`/`tab-color` on a single base profile |
| TAB-01..03 | 3 | 2 Covered, 1 Partial | TAB-01: code delivers tab color via per-state profile; spec now mandates OSC `tab-color` on every change |
| THEME-01..03 | 3 | All Covered | Dracula palette across badge, tab, status-bar chips (blocked-idle row removed) |
| NFR-01..11 | 11 | All Covered | Timing reqs advisory; NFR-02 (overlay caching) retired, NFR-04 now bounds `focus` |

Numbering gaps (no PROV-04, no CMD-10/CMD-11, no CLI-13, no BADGE-11, no
STATUS-BAR-04) are intentional. IDs retired in the 1.0 pivot — CMD-12
(`exclusive-configuration`), CLI-04/05/15 (`bg-image` / `note` /
`clear-screen`), BADGE-15 (watermark), and the entire OVERLAY namespace — are
removed, not missing coverage.

## Open / Needs Decision

The 1.0 pivot is captured in the spec but not yet in the code. Implementing it
means **adding** FOCUS-01..04 + CLI-17 (dashboard focus) and **removing** the
retired surfaces from `scripts/beacon`, `bin/beacon-iterm`, `shell/beacon.zsh`,
`hooks/`, and `iterm/` — the marginalia overlay, `note` / `bg-image` /
`clear-screen` subcommands, `_compose.py`, the per-state profiles, the `!`/`?`
watermark assets, `exclusive-configuration`, and the bg-image trust /
`PerPaneBackgroundImage` install steps. RENDER-04 / TAB-01 must move to
OSC-only color on a single base profile, and STATUS-BAR-01 must activate that
profile via runtime `set-profile` instead of the default-profile pref.

## Audit history

### 2026-06-05 — Coverage refresh (spec-status)

STATUS.md updated: +1 ID (PROV-02a, Covered), 108 → 109 Covered.

## How to use this file

When you implement a new requirement, change the row's status and add an
evidence pointer. When an audit reveals drift, update the row to **Partial**
or **Contradicts** with a one-line note.

# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`docs/spec.md`](docs/spec.md).
Updated after each `/spec-audit`.

**Last audit:** 2026-05-31
**Spec version:** v1 (root-level, `docs/spec.md`)
**Plugin version:** 0.20.0
**Coverage:** 115 Covered, 0 Partial, 0 Missing/Contradicts.

Status (`signal.status`) has exactly four values — `idle`, `working`,
`waiting`, `paused` — mapping to three logical badge color states (`ready` /
`busy` / `blocked`), with `blocked-idle` sharing `blocked`'s hex but a distinct
`?` watermark (BADGE-09 / -15). Pause is a status value, not a separate concept
(STATE).

## Status by category

| Prefix | Covered | Status | Notes |
|--------|--------:|--------|-------|
| RES-01..05 | 5 | All Covered | Signal resolution model |
| PROV-01..03, 05, 06 | 5 | All Covered | Provider chains (no PROV-04) |
| PROV-07 | 1 | Covered | `url` chain uses branch-slug match (`scripts/beacon` `_tack_url_for`); spec step 2 updated to match (the `tack find <pwd>` fallback clause was struck). |
| HOOK-01, 01a, 02, 03, 03a..03c, 08, 08a, 08b | 10 | All Covered | Hook handlers |
| OVR-01..04 | 4 | All Covered | User overrides |
| STATE-01..07 (incl. 04a) | 8 | All Covered | User-set status; pause is `status = paused`; descriptions on any user-set status |
| SKILL-01..03 | 3 | All Covered | CLI-freshness + conventions; stage-signaling responsibility removed with stage |
| CMD-01..09, 12..16 (gap at 10, 11) | 14 | All Covered | Slash command surface |
| WIP-01..06 | 6 | All Covered | Cross-session introspection / export (`wip`, `serve`, `prune`) |
| CLI-01..12, 14, 15 (gap at 13) | 14 | All Covered | `beacon-iterm` subcommands |
| BADGE-01..10, 12..15 (incl. 09a; gap at 11) | 15 | All Covered | Badge text + color + watermark; profile-per-state mechanism |
| STATUS-BAR-01..03, 05, 06 (gap at 04) | 5 | All Covered | Fixed-layout status-bar chips + action buttons |
| OVERLAY-01..04 | 4 | All Covered | Marginalia card overlay; LRU image pool; trust pre-approval |
| RENDER-01..04 | 4 | All Covered | Render orchestration (profile-switch vs. OSC-overlay split) |
| TAB-01..03 | 3 | All Covered | Tab-color mirror of badge state |
| THEME-01..03 | 3 | All Covered | Dracula palette across badge, tab, status-bar chips |
| NFR-01..11 | 11 | All Covered | NFR-01 / NFR-04 timing requirements lack a measurement harness; advisory |

Numbering gaps (no PROV-04, no CMD-10/CMD-11, no CLI-13, no BADGE-11, no
STATUS-BAR-04) are intentional — IDs retired with deleted requirements, not
missing coverage.

## How to use this file

When you implement a new requirement, change the row's status and add an
evidence pointer. When an audit reveals drift, update the row to **Partial**
or **Contradicts** with a one-line note.

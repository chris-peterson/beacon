# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`docs/spec.md`](docs/spec.md).
Updated after each `/spec-audit`.

**Last audit:** 2026-05-08
**Last spec change:** 2026-05-14
**Last implementation:** 2026-05-14
**Spec version:** v1 (root-level, `docs/spec.md`)
**Plugin version:** 0.9.0
**Coverage:** all normative requirements covered.

The 2026-05-14 spec change restructured §4.3 BADGE around an **engagement** precondition (BADGE-14) and pivoted the badge color mechanism from per-session OSC `SetColors=badge=` to **profile-per-state switching** via `OSC SetProfile=` (new CLI-14), enabling translucent badges (BADGE-13) and state-driven background images (BADGE-15, blocked = `!` watermark). Pause stays as an OSC overlay; resume's `set-profile` atomically wipes any session overrides (RENDER-04). The prior BADGE-12 ("paint `ready` on shell source") was deleted; the prior BADGE-13 (republish on project change) was renumbered to BADGE-12. Implementation lands in the same change: 5 dynamic profiles (`beacon`, `beacon-ready`, `beacon-busy`, `beacon-blocked`, `beacon-drifted`), a bundled `iterm/images/blocked.png`, new CLI `set-profile` subcommand, plugin render-flow split, engagement marker keyed on `$ITERM_SESSION_ID`, and shell-snippet gating of badge user-vars on the marker.

## Status by category

| Prefix | Covered | Status | Notes |
|--------|--------:|--------|-------|
| RES-01..06 | 6 | All Covered | Resolution model |
| PROV-01..05 (incl. -01a) | 6 | All Covered | PROV-01a added 2026-05-08 — subgroup elision as `<top>/.../<repo>` |
| PROV-06 | 1 | Covered (fixed 2026-05-08) | `resolve()` now returns abbreviated cwd, not literal `"?"` |
| PROV-07 | 1 | Partial | `tack find <pwd>` fallback still missing — slug-match only |
| HOOK-01..09 (incl. -03a, -03b, -09b) | 12 | All Covered | HOOK-09b added 2026-05-14 — suppress drift suffix when it would repeat the anchor's tail |
| OVR-01..04 | 4 | All Covered | |
| STATE-01..07 (incl. -04a) | 8 | All Covered | Renamed from PAUSE namespace 2026-05-22; pause is now `status = paused`; descriptions on any user-set status |
| SKILL-01..03 | 3 | All Covered | Stage-signaling SKILL-01/-02 deleted 2026-05-22 with stage; remaining numbers are convention + CLI-freshness |
| CMD-01..16 (gap at 10, 11) | 14 | All Covered | CMD-04 now also accepts `status <value> [description]`; CMD-10 (`signal`) removed 2026-05-22 with stage |
| CLI-01..15 | 15 | All Covered | CLI-14 (`set-profile`) added 2026-05-14; CLI-15 (`clear-screen`) added 2026-05-21 |
| BADGE-01..15 (incl. -09a) | 16 | All Covered | 2026-05-14 restructured §4.3 (old BADGE-12 deleted, BADGE-13 → BADGE-12), pivoted to profile-per-state mechanism, added BADGE-15 (state-driven bg image, blocked = `!`) |
| OVERLAY-01..04 | 4 | All Covered | OVERLAY-01 / OVERLAY-04 amended 2026-05-14 (overlay layers over static state image; install pre-approves state image paths); OVERLAY-01 amended 2026-05-21..22 (post-it → right-anchored marginalia card; multi-line first-line-as-heading; `*` bold / `_` italic inline markers); OVERLAY-01 generalized 2026-05-22 from paused-only to any status with a description |
| RENDER-01..04 | 4 | All Covered | RENDER-04 amended 2026-05-14 (pause vs status mechanism split) |
| TAB-01..03 | 3 | All Covered | TAB-01 amended 2026-05-14 (profile-driven for non-paused, OSC overlay during pause) |
| THEME-01..03 | 3 | All Covered | New 2026-05-08 — Dracula palette adopted across badge, tab, status-bar chips |
| STATUS-BAR-01..06 (gap at 04) | 5 | All Covered | STATUS-BAR-04 is a numbering gap (not used) |
| NFR-01..11 (gap at NFR-04 evidence) | 11 | All Covered | NFR-01 / NFR-04 timing requirements lack measurement harness; advisory |
| FUT (none) | 0 | — | |

## How to use this file

When you implement a new requirement, change the row's status and add an
evidence pointer. When an audit reveals drift, update the row to **Partial**
or **Contradicts** with a one-line note.

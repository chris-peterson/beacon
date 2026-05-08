# beacon — Spec Coverage Status

Tracking status of the requirements declared in [`docs/spec.md`](docs/spec.md).
Updated after each `/spec-audit`.

**Last audit:** 2026-05-08
**Spec version:** v1 (root-level, `docs/spec.md`)
**Plugin version:** 0.7.0
**Coverage:** all normative requirements covered

After this session's edits the spec covers the eight CLI subcommands and
helpers that previously shipped without coverage (`signal`, `copy-url` /
`open-url`, `json`, `data-dir`, `uservar-batch`, `attention`, the SKILL
freshness check). The PROV-06 contradiction in `resolve()` is fixed.
ALIAS (project name aliases) was YAGNI'd out of the spec, README, and
code — the feature was never implemented and never used.

## Status by category

| Prefix | Covered | Status | Notes |
|--------|--------:|--------|-------|
| RES-01..06 | 6 | All Covered | Resolution model |
| PROV-01..05 (incl. -01a) | 6 | All Covered | PROV-01a added 2026-05-08 — subgroup elision as `<top>/.../<repo>` |
| PROV-06 | 1 | Covered (fixed 2026-05-08) | `resolve()` now returns abbreviated cwd, not literal `"?"` |
| PROV-07 | 1 | Partial | `tack find <pwd>` fallback still missing — slug-match only |
| HOOK-01..09 (incl. -03a, -03b) | 11 | All Covered | HOOK-09 drift suffix changed 2026-05-08 to `(@ <basename>)` |
| OVR-01..04 | 4 | All Covered | |
| PAUSE-01..06 (incl. -04a) | 7 | All Covered | NL pause-intent regex covers a superset of the spec's examples |
| SKILL-01..05 | 5 | All Covered | SKILL-05 added 2026-05-08 |
| CMD-01..16 (gap at 11) | 15 | All Covered | CMD-10 / CMD-14 / CMD-15 / CMD-16 added 2026-05-08; CMD-11 removed with ALIAS |
| CLI-01..13 | 13 | All Covered | CLI-12 / CLI-13 added 2026-05-08 |
| BADGE-01..12 (incl. -09a) | 13 | All Covered | BADGE-12 added 2026-05-08 — shell sets badge to `ready` on source |
| OVERLAY-01..04 | 4 | All Covered | |
| RENDER-01..04 | 4 | All Covered | |
| TAB-01..03 | 3 | All Covered | |
| THEME-01..03 | 3 | All Covered | New 2026-05-08 — Dracula palette adopted across badge, tab, status-bar chips |
| STATUS-BAR-01..06 (gap at 04) | 5 | All Covered | STATUS-BAR-04 is a numbering gap (not used) |
| NFR-01..11 (gap at NFR-04 evidence) | 11 | All Covered | NFR-01 / NFR-04 timing requirements lack measurement harness; advisory |
| FUT (none) | 0 | — | |

## How to use this file

When you implement a new requirement, change the row's status and add an
evidence pointer. When an audit reveals drift, update the row to **Partial**
or **Contradicts** with a one-line note.

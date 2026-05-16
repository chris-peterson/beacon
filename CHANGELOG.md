# Changelog

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

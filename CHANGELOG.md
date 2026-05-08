# Changelog

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

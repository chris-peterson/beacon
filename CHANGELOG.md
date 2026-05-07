# Changelog

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

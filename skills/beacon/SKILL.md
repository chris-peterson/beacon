---
name: beacon
description: Label sessions (project / task) and ensure the beacon CLI wrapper is fresh. Triggers when the user asks to label a pane or set a project/task, and on first invocation per session for the freshness check.
---

# beacon — labeling and CLI freshness backstop

beacon is a session-awareness tool that displays the current project, task, and status on the iTerm2 terminal. Hooks own status transitions; the shell owns project / branch resolution. Your job is to fill the gaps hooks cannot observe — nothing more.

## Before first invocation in a session

Compare `beacon --version` against the plugin version in `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. If they differ, surface a one-line note and offer `/beacon:beacon install` to refresh the shell wrapper. If `beacon` isn't on PATH, skip silently.

## Surface map — what each field paints

When the user asks you to label a session, pick the field by the surface they're pointing at:

| Field    | Surfaces                                                                 |
|:---------|:-------------------------------------------------------------------------|
| `project`| **Badge text** — leading chip (the per-pane label in iTerm2) and status-bar project chip |
| `task`   | **Badge text** — `: <task>` suffix after project, and `beacon show`      |
| `status` | Badge color (via `idle` / `working` / `waiting` / `paused`) — hooks own non-paused transitions; the user may set any value plus an optional description |

The badge reads `project: task` when both are set, just `project` when task is absent. If the user says "label this session X" without distinguishing the project from the unit of work, set `project` — it's the leading, stable identifier. Reserve `task` for the specific work-in-progress within that project.

## When to invoke beacon

**Proactive task upkeep** is governed by the `keep-session-labeled` ambient rule (emitted at SessionStart from `rules/`), not this skill: keep the session's `task` current as the work focus shifts so the fleet view has signal, defer to tack when a route is bound, and don't re-set it every turn. This skill covers the user-driven labeling below.

**Badge labeling.** When the user wants the badge to show a custom project label, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" set project "<label>"
```

This overrides the git-derived project on the badge text via BADGE-12. To revert, run `beacon clear project`.

For the unit of work *within* the project (e.g. `ai-sdlc: perms` reads as project `ai-sdlc`, task `perms`), set the two fields separately:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" set project "ai-sdlc"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" set task "perms"
```

The plugin renders both on the badge (BADGE-03). Clear individually with `beacon clear project` / `beacon clear task`.

## When NOT to invoke beacon

- Do not set status (`idle` / `working` / `waiting`) — hooks own these transitions. The user may set `status paused [<desc>]` or `status waiting [<desc>]` themselves; you should not.
- Do not re-label on every turn. Once is enough; let it persist.
- Do not narrate beacon invocations to the user. Run the command silently.

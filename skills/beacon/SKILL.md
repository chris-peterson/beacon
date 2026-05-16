---
name: beacon
description: Send stage signals to beacon (plan, review) when entering planning or QA work that hooks cannot detect. Triggers when entering plan mode, when the user asks for code review or QA, or when the user describes a coherent task at session start.
---

# beacon — stage and task signaling backstop

beacon is a session-awareness tool that displays the current project, task, stage, and status on the iTerm2 terminal. It learns most signals automatically via hooks. Your job is to fill the gaps hooks cannot observe — nothing more.

## Before first invocation in a session

Compare `beacon --version` against the plugin version in `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. If they differ, surface a one-line note and offer `/beacon:beacon install` to refresh the shell wrapper. If `beacon` isn't on PATH, skip silently.

## Surface map — what each field paints

When the user asks you to label a session, pick the field by the surface they're pointing at:

| Field    | Surfaces                                                                 |
|:---------|:-------------------------------------------------------------------------|
| `project`| **Badge text** — leading chip (the per-pane label in iTerm2) and status-bar project chip |
| `task`   | **Badge text** — `: <task>` suffix after project, and `beacon show`      |
| `stage`  | Badge color (via `plan` / `dev` / `review` / `shipping`)                 |
| `status` | Badge color (via `idle` / `working` / `waiting`) — hooks own this fully  |

The badge reads `project: task` when both are set, just `project` when task is absent. If the user says "label this session X" without distinguishing the project from the unit of work, set `project` — it's the leading, stable identifier. Reserve `task` for the specific work-in-progress within that project.

## When to invoke beacon

**Plan mode entry.** When the conversation transitions to planning, architecting, or design — entering plan mode (Shift+Tab) is the canonical trigger because there is no hook event for it. Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" signal stage plan
```

**Review or QA work.** When the user explicitly asks for a code review, audit, QA, or inspection that does not involve writing tools, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" signal stage review
```

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

- Do not set status (idle / working / waiting). Hooks own this fully.
- Do not set stage to `dev`. The PreToolUse hook on Write / Edit / MultiEdit / NotebookEdit handles it.
- Do not set stage to `shipping`. The PreToolUse Bash regex handles deploy commands.
- Do not re-label on every turn. Once is enough; let it persist.
- Do not narrate beacon invocations to the user. Run the command silently.

---
name: beacon
description: Send stage signals to beacon (plan, review) when entering planning or QA work that hooks cannot detect. Triggers when entering plan mode, when the user asks for code review or QA, or when the user describes a coherent task at session start.
---

# beacon — stage and task signaling backstop

beacon is a session-awareness tool that displays the current project, task, stage, and status on the iTerm2 terminal. It learns most signals automatically via hooks. Your job is to fill the gaps hooks cannot observe — nothing more.

## Before first invocation in a session

Compare `beacon --version` against the plugin version in `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. If they differ, surface a one-line note and offer `/beacon:beacon install` to refresh the shell wrapper. If `beacon` isn't on PATH, skip silently.

## When to invoke beacon

**Plan mode entry.** When the conversation transitions to planning, architecting, or design — entering plan mode (Shift+Tab) is the canonical trigger because there is no hook event for it. Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" signal stage plan
```

**Review or QA work.** When the user explicitly asks for a code review, audit, QA, or inspection that does not involve writing tools, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" signal stage review
```

**Task labeling at session start.** Once at the start of a session — when the user describes a coherent unit of work in a sentence or two and there is no PR title or non-default branch to derive task from — run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" set task "<short-label>"
```

## When NOT to invoke beacon

- Do not set status (idle / working / waiting). Hooks own this fully.
- Do not set stage to `dev`. The PreToolUse hook on Write / Edit / MultiEdit / NotebookEdit handles it.
- Do not set stage to `shipping`. The PreToolUse Bash regex handles deploy commands.
- Do not re-label task on every turn. Once is enough; let it persist.
- Do not narrate beacon invocations to the user. Run the command silently.

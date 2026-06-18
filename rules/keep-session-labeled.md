# Keep this session's beacon work label current

beacon shows every concurrent Claude Code session in one fleet view — `beacon wip`, or the dashboard `beacon serve` opens at `http://127.0.0.1:8787/`. A session is only as useful there as its label. The hooks already set the fields they can observe on any platform: the project, the git branch, and the ready / busy / blocked status color. What they can't observe is *what this session is actually working on*. Keep that current so a glance at the fleet tells the user which window is doing what — without them having to ask you to label it.

- When the focus of your work becomes clear or **meaningfully shifts** — a new feature, bug, file, or phase — set the work label:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" set task "<short phrase>"
  ```

  Keep it to a few words: it's the unit of work, not a sentence, and it shares the iTerm2 badge with the project name. Update it when the focus changes; don't re-set it every turn for the same work, and clear it with `clear task` when the work is done.

- **Defer to tack.** If this work is tracked by a tack route (tack is installed and a route is bound to the session), tack already supplies the fleet-view label — leave the beacon task alone and let tack own it. Set a beacon task only when no tack route is driving the session.

- **Don't set status.** The hooks own the ready / busy / blocked transitions. The user sets `paused` / `waiting` themselves; you don't.

- Run the command silently — don't narrate it to the user.

# Keep this session's beacon work label current

beacon shows every concurrent Claude Code session in one fleet view — `beacon wip`, or the dashboard `beacon serve` opens at `http://127.0.0.1:8787/`. A session is only as useful there as its label. The hooks already set the fields they can observe on any platform: the project, the git branch, the ready / busy / blocked status color, and the most recent turn (the `latest_turn` play-by-play, derived from the transcript with no help from you). What they can't observe is *the durable headline* — the unit of work this session is on, which outlives any single turn. Keep that current so a glance at the fleet tells the user which window is doing what — without them having to ask you to label it.

- `task` is the headline, not a turn-by-turn log — `latest_turn` already carries the play-by-play. When the focus of your work becomes clear or **meaningfully shifts** — a new feature, bug, file, or phase — set the work label:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" set task "<short phrase>"
  ```

  Keep it to a few words: it's the unit of work, not a sentence, and it sits under the project name on the iTerm2 tab. Update it when the focus changes; don't re-set it every turn for the same work, and clear it with `clear task` when the work is done.

- **Defer to tack.** If this work is tracked by a tack route (tack is installed and a route is bound to the session), tack already supplies the fleet-view label — leave the beacon task alone and let tack own it. Set a beacon task only when no tack route is driving the session.

- **Defer to the user's `/rename`.** A Claude Code `/rename` is shorthand for setting the task — beacon folds it into the same label slot. If the user has renamed the session, treat that as their chosen headline: don't overwrite it with `set task` unless the work has *genuinely* shifted to something the rename no longer describes (a new feature, bug, or phase). Recency wins, so a needless relabel silently discards what the user typed.

- **Don't set status.** The hooks own the ready / busy / blocked transitions. The user sets `paused` / `waiting` themselves; you don't.

- Run the command silently — don't narrate it to the user.

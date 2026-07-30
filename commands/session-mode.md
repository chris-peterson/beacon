---
description: Set this session's beacon mode — release, retro, pause, done, or resume — with an optional note
argument-hint: "<release|retro|pause|done|resume> [note]"
---

Move this session's beacon into the mode named by the first argument. This is a fast, single-action wrapper — run the command below, then reply with one short line confirming the mode (echo the note if one was given). Do no other work: no preamble, no status checks, no follow-up suggestions.

<!-- No `model:` override on purpose: pinning a cheaper model forces a
cross-model turn whose prompt cache can't reuse the session's, so the whole
initial context cold-prefills — far slower than the one-line reply this runs on
the session model. The latency here is prefill, not generation. -->

This command runs on the session's model so the prompt cache stays warm; keep it that way.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" ${ARGUMENTS}
```

The CLI repaints the pane as it runs, so the user sees the change immediately; your one-line reply just confirms it.

| Mode | What the pane becomes |
|:---|:---|
| `pause` | Muted-purple badge over the pause profile (faint `\|\|`-button watermark). The only mode that auto-clears — the next prompt resumes the session. |
| `release` | Green badge over the release profile: deep "launch-sky" navy with a faint rocket watermark. |
| `retro` | White badge over the retro profile: muted green with a faint checklist-clipboard watermark. |
| `done` | Dim-gray badge over the done profile: near-black "powered off" with a faint checkered finish-flag watermark. Drops the task from the badge so it shows the project alone. |
| `resume` | Clears the mode and returns the pane to the dev cycle. |

Apart from `pause`, a mode persists until the session runs `resume` / `clear` or ends — it does not auto-clear on the next prompt.

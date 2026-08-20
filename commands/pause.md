---
description: Park this session's beacon — set status to paused, with an optional note
argument-hint: "[note]"
disable-model-invocation: true
---

Park this session's beacon. This is a fast, single-action wrapper — run the command below, then reply with one short line confirming the pause (echo the note if one was given). Do no other work: no preamble, no status checks, no follow-up suggestions.

<!-- No `model:` override on purpose: pinning a cheaper model forces a
cross-model turn whose prompt cache can't reuse the session's, so the whole
initial context cold-prefills — far slower than the one-line reply this runs on
the session model. The latency here is prefill, not generation. -->

This command runs on the session's model so the prompt cache stays warm; keep it that way.

<!-- User-invocable only (CMD-25). A skill entering a mode runs the CLI —
`beacon release`, `beacon retro`, `beacon done` — in one shell call; a
model-facing command here would reach the same subcommand for the price of a
model turn. -->

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" pause ${ARGUMENTS}
```

The CLI repaints the pane as it runs — muted-purple tab over the pause profile, a `⏸` on the tab and window title, the note in the Claude Code status line — so the user sees the change immediately; your one-line reply just confirms it.

Pause is the one mode that auto-clears: the next prompt resumes the session. The other modes, and `resume`, are CLI subcommands — `beacon release`, `beacon retro`, `beacon done`, `beacon resume`.

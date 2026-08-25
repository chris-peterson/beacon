---
description: Park this session's beacon — enter pause mode, with an optional note
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

The CLI repaints the pane as it runs — a `⏸` on the tab and window title, the pause profile's muted-purple background, the note in the Claude Code status line — so the user sees the change immediately; your one-line reply just confirms it. The tab *color* is unchanged: it reports what the hooks observe, not what the session declares, so parking a session doesn't hide whether it needs the user.

Pause is the one mode that auto-clears on the next prompt. The rest, and `resume`, are CLI subcommands — `beacon release`, `beacon retro`, `beacon done`, `beacon resume`.

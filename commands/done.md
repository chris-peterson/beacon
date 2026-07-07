---
description: Mark this session complete — set status to done (ready to hand off to another session), with an optional note
argument-hint: "[note]"
disable-model-invocation: true
---

Mark this session's beacon complete (the session is finished and ready to hand off to another). This is a fast, single-action wrapper — run the command below, then reply with one short line confirming it (echo the note if one was given). Do no other work: no preamble, no status checks, no follow-up suggestions.

<!-- No `model:` override on purpose: pinning a cheaper model forces a
cross-model turn whose prompt cache can't reuse the session's, so the whole
initial context cold-prefills — far slower than the one-line reply this runs on
the session model. The latency here is prefill, not generation. -->

This command runs on the session's model so the prompt cache stays warm; keep it that way.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" done ${ARGUMENTS}
```

The CLI swaps the pane into the done profile (near-black "powered off" background with a faint `⏻` power-symbol watermark, under a dim-gray badge) as it runs, and drops the task from the badge so it shows the project alone; the user sees the change immediately, and your one-line reply just confirms it. Done persists until the session runs `resume` / `clear` or ends — it does not auto-clear on the next prompt.

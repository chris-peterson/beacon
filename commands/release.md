---
description: Enter release mode for this session — set status to release (ship-it flow in progress), with an optional note
argument-hint: "[note]"
disable-model-invocation: true
---

Move this session's beacon into release mode (a ship-it / release flow is in progress). This is a fast, single-action wrapper — run the command below, then reply with one short line confirming it (echo the note if one was given). Do no other work: no preamble, no status checks, no follow-up suggestions.

<!-- No `model:` override on purpose: pinning a cheaper model forces a
cross-model turn whose prompt cache can't reuse the session's, so the whole
initial context cold-prefills — far slower than the one-line reply this runs on
the session model. The latency here is prefill, not generation. -->

This command runs on the session's model so the prompt cache stays warm; keep it that way.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" release ${ARGUMENTS}
```

The CLI swaps the pane into the release profile (deep "launch-sky" navy background with a faint rocket watermark, under a green badge color) as it runs, so the user sees the change immediately; your one-line reply just confirms it. Release persists until the session runs `resume` / `clear` or ends — it does not auto-clear on the next prompt.

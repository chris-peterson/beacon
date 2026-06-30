---
description: Pause this session's beacon — set status to paused, with an optional note
argument-hint: "[note]"
disable-model-invocation: true
---

Park this session's beacon. This is a fast, single-action wrapper — run the command below, then reply with one short line confirming the pause (echo the note if one was given). Do no other work: no preamble, no status checks, no follow-up suggestions.

<!-- No `model:` override on purpose: pinning a cheaper model forces a
cross-model turn whose prompt cache can't reuse the session's, so the whole
initial context cold-prefills — far slower than the one-line reply this runs on
the session model. The latency here is prefill, not generation. -->

This command runs on the session's model so the prompt cache stays warm; keep it that way.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" pause ${ARGUMENTS}
```

The CLI flips the badge to the paused color in the pane as it runs, so the user sees the change immediately; your one-line reply just confirms it.

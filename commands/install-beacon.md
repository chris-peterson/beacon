---
description: Bootstrap or refresh beacon's wrapper, completions, status line, and iTerm2 profiles
argument-hint: "[--dir <path>]"
disable-model-invocation: true
---

Run beacon's install bootstrap, then report its output as-is — one line if every step was already current. Do no other work.

<!-- This command exists because it is the only door to the *newly installed*
plugin root. The wrapper at ~/.local/bin/beacon and the `source` line in .zshrc
both hardcode a version-pinned path at install time, so after a plugin upgrade
`beacon install` from the shell re-points them at the version they already
name. `${CLAUDE_PLUGIN_ROOT}` is the new one. -->

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" install ${ARGUMENTS}
```

Every step is idempotent, so re-running it is the normal way to recover from drift — the SessionStart freshness hook nudges you here when `beacon --version` falls behind the plugin.

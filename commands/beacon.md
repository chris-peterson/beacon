---
description: Show or set session beacon signals (project, task, status)
argument-hint: "[show | status <value> [description] | resume | task <label> | project <name> | icon <path|url> | clear | install-cli [--dir <path>]]"
---

Run the beacon command with the user's arguments. If no arguments were provided, run `show`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/beacon" ${ARGUMENTS:-show}
```

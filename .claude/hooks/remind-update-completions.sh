#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): keep tab completion in sync with the CLI.
#
# The zsh completion is an embedded string constant (ZSH_COMPLETION in
# scripts/beacon), installed as a frozen copy at ~/.zsh/completions/_beacon by
# `beacon completions zsh`. Change a subcommand or flag without updating that
# constant — and reinstalling — and both the embedded block and every
# developer's installed copy drift stale. This fires once per session when the
# CLI source is edited, nudging the developer to reconcile both.
#
# Sibling of hooks/cli-freshness.sh: that catches wrapper-vs-plugin version
# drift at SessionStart for every consumer; this catches embedded-completion
# drift at edit time for developers of the plugin.

set -euo pipefail

fp=$(jq -r '.tool_input.file_path // empty')
[ -z "$fp" ] && exit 0

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
fp="${fp#"$root/"}"

# Only the CLI source carries the embedded completion.
[ "$fp" = "scripts/beacon" ] || exit 0

# Fire once per session to avoid reminder fatigue during batch edits.
marker="/tmp/beacon-remind-completions-${CLAUDE_SESSION_ID:-$$}"
[ -f "$marker" ] && exit 0
touch "$marker"

cat <<'MSG'
You edited the beacon CLI. If you changed any subcommand or flag, keep tab
completion in sync:
1. Update the embedded ZSH_COMPLETION block in scripts/beacon to match.
2. Run `beacon completions zsh` to refresh the installed copy at
   ~/.zsh/completions/_beacon (it is a frozen snapshot, not regenerated on its own).
MSG

#!/usr/bin/env bash
# SessionStart hook: emit this plugin's ambient rules into context. Stdout is
# added to context on every SessionStart (startup, resume, compaction — no
# matcher in hooks.json), so the labeling guidance survives a compaction. This
# is what makes beacon useful standalone: without tack or a recipe nudging it,
# the rule keeps each session's work label current so the sessions view has signal.

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
RULES_DIR="$PLUGIN_ROOT/rules"
[ -d "$RULES_DIR" ] || exit 0

# Rules reference bundled files as ${CLAUDE_PLUGIN_ROOT}/<path> placeholders;
# expand them here so the injected text carries real, runnable paths.
printf '# Ambient rules from the beacon plugin\n\n'
for f in "$RULES_DIR"/*.md; do
  [ -e "$f" ] || exit 0
  sed "s|\${CLAUDE_PLUGIN_ROOT}|$PLUGIN_ROOT|g" "$f"
  printf '\n'
done

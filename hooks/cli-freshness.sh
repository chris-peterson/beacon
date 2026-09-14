#!/usr/bin/env bash
# SessionStart hook: report entry points a plugin update left behind.
#
# Claude Code updates the plugin in the background, so new code arrives with no
# action from the user — while the wrapper on $PATH, the `.zshrc` source line,
# and the iTerm2 status-bar buttons all keep the path they baked at install
# time. Once the old version's directory is reaped those paths reach nothing.
#
# The check itself is the CLI's (`freshness`, HOOK-14), run from
# ${CLAUDE_PLUGIN_ROOT} because that is the one copy guaranteed to be the
# version now loaded. Stdout is added to context on every SessionStart; the
# subcommand prints nothing when every surface already reaches this install.
#
# See ai-sdlc/src/claude/skills/ai-cli-tool (Architecture Rule 11).

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
[ -n "$PLUGIN_ROOT" ] || exit 0
[ -f "$PLUGIN_ROOT/scripts/beacon" ] || exit 0

exec python3 "$PLUGIN_ROOT/scripts/beacon" freshness

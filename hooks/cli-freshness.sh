#!/usr/bin/env bash
# SessionStart hook: detect CLI wrapper drift after a plugin update.
#
# The `install-cli` subcommand drops a wrapper at ~/.local/bin/<name>
# whose path is hardcoded at install time. When the plugin updates, the
# wrapper does NOT auto-update — it still points at wherever install-cli
# was last run from. This hook fires on each Claude Code session start,
# compares `<name> --version` against `plugin.json#version`, and emits an
# additionalContext nudge when they differ. Silent when versions match,
# silent when the CLI isn't on PATH, never blocks the session.
#
# See ai-sdlc/src/recipes/ai-cli-tool.md (Architecture Rule 11).

set -euo pipefail

NAME="beacon"
PLUGIN_JSON="${CLAUDE_PLUGIN_ROOT:-}/.claude-plugin/plugin.json"

[ -f "$PLUGIN_JSON" ] || exit 0
command -v "$NAME" >/dev/null 2>&1 || exit 0

PLUGIN_VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$PLUGIN_JSON" 2>/dev/null) || exit 0
CLI_VERSION=$("$NAME" --version 2>/dev/null | awk '{print $NF}') || exit 0

[ -z "$CLI_VERSION" ] && exit 0
[ "$PLUGIN_VERSION" = "$CLI_VERSION" ] && exit 0

NAME="$NAME" CLI_VERSION="$CLI_VERSION" PLUGIN_VERSION="$PLUGIN_VERSION" python3 <<'PY'
import json, os
n  = os.environ["NAME"]
cv = os.environ["CLI_VERSION"]
pv = os.environ["PLUGIN_VERSION"]
msg = (
    f"PLEASE TELL THE USER (do not skip): the {n} CLI on PATH reports "
    f"version {cv}, but the {n} plugin is at {pv}. Refresh the shell "
    f"wrapper before relying on the CLI — typically `/{n}:{n} install-cli`, "
    f"or `git pull` in the local source checkout if the wrapper points "
    f"there. Until refreshed, CLI invocations may run stale code."
)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": msg,
    }
}, separators=(",", ":")))
PY

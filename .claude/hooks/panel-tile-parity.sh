#!/usr/bin/env bash
# Stop hook: keep the tab stack's tiles drawn as the status panel draws itself.
#
# Each tile in the dashboard's tab stack (dashboard/index.html, WIP-19) is a
# session's status panel, redrawn by a second renderer in another language: the
# band's hooks module (hooks/status-panel.tsx) lays out Ink boxes, the tile lays
# out HTML. Nothing ties the two, so a change to the band's rows, columns, or
# colors leaves every tile on the old ones until someone opens the stack and
# notices.
#
# So a turn whose branch changes the panel but not the dashboard is refused
# once, with the reason. The second stop goes through (stop_hook_active): a
# panel change with nothing for a tile to restate (the session picker, the
# footer's mode label) costs one sentence saying so, not a loop.

set -euo pipefail

input=$(cat)
[ "$(jq -r '.stop_hook_active // false' <<<"$input")" = true ] && exit 0

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root"

# The branch's whole change, committed or not, against where it left main.
base=$(git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD main 2>/dev/null) || exit 0
changed=$({ git diff --name-only "$base"; git ls-files --others --exclude-standard; } | sort -u)

grep -qx 'hooks/status-panel.tsx' <<<"$changed" || exit 0
grep -qx 'dashboard/index.html' <<<"$changed" && exit 0

jq -n '{
  decision: "block",
  reason: "This branch changes the status panel (hooks/status-panel.tsx) but not the tab stack tiles that redraw it (dashboard/index.html: PIP_CSS and updatePipRow, WIP-19). Bring the tiles in line with the band, and SPEC.md WIP-10 with them, or, if this change has nothing a tile draws (the session picker, the footer label), say so and stop again."
}'

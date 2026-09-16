#!/usr/bin/env bash
# End a trial (`just trial-on`): point every installed entry point back at the
# highest installed plugin build. Runs that build's own `install`, the same path
# `/beacon:install-beacon` takes, so ending a trial lands exactly what a user
# has rather than surfaces this script hand-wrote.
#
# Three surfaces are pinned to a plugin root at install time — the `beacon` on
# PATH, the `.zshrc` source line, and the script path baked into each iTerm2
# profile's buttons — and `install` is what rewrites all three from its own
# root. `--skip-layout` holds back the one step that can quit iTerm2, which has
# nothing to say about which copy the surfaces reach.
set -euo pipefail

cache="${HOME}/.claude/plugins/cache"

# The marketplace beacon is installed from is not fixed, so the version
# directories are found by where beacon lands rather than by a name baked in
# here. Versions sort as numbers, so 2.13.2 beats 2.9.0.
root=$(find "$cache" -mindepth 3 -maxdepth 3 -type d -path "*/beacon/*" 2>/dev/null \
	| awk -F/ '{ split($NF, v, "."); printf "%010d%010d%010d\t%s\n", v[1], v[2], v[3], $0 }' \
	| sort \
	| tail -1 \
	| cut -f2)

if [ -z "$root" ]; then
	echo "No installed beacon plugin found under $cache." >&2
	echo "Install it with \`claude plugin install beacon\`, then re-run." >&2
	exit 1
fi

script="$root/scripts/beacon"
if [ ! -f "$script" ]; then
	echo "Plugin at $root has no scripts/beacon." >&2
	exit 1
fi

export CLAUDE_PLUGIN_ROOT="$root"

# The installed build is whatever shipped last, so it need not know a flag this
# working copy just added — `install` would abort on it. Ask that build what it
# accepts rather than assuming, which also retires this check on its own once
# every installed version carries the flag.
layout_flag=""
if python3 "$script" install --help 2>/dev/null | grep -q -- --skip-layout; then
	layout_flag="--skip-layout"
else
	echo "note: installed beacon $(basename "$root") predates --skip-layout, so it"
	echo "      will close by auditing the app-wide iTerm2 layout prefs."
fi

python3 "$script" install ${layout_flag:+"$layout_flag"}

echo
echo "Restored $(python3 "$script" --version) from the plugin cache."

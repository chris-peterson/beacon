# shipyard runs from its git ref, with no checkout and no install. CI is the
# writer for what lands; these recipes are for seeing the projection first.
shipyard := "uvx --from 'git+https://github.com/chris-peterson/shipyard@v2' shipyard"

# What this is, and every recipe there is
[private]
default:
    @echo ""
    @echo "  beacon — at-a-glance awareness across concurrent Claude Code sessions:"
    @echo "  a terminal-agnostic sessions view, plus iTerm2 per-pane painting."
    @echo ""
    @echo "  New here?   just demo      a live dashboard, seeded, with no real sessions"
    @echo "  Broken?     just doctor    check the install and read the recorded errors"
    @echo ""
    @just --list --unsorted --list-prefix '    ' --list-heading ''
    @echo ""
    @echo "  Recipes run against this clone; trial-off is the one that reaches the install."
    @echo "  generate / check / docs fetch shipyard through uvx; the rest need only python3."
    @echo ""

# seed an isolated demo fleet, serve the dashboard, and live-simulate state changes
[group('start here')]
demo *args:
    python3 dev/demo.py {{args}}

# launch an interactive Claude Code session with the local plugin loaded
[group('start here')]
try:
    claude --plugin-dir .

# point the `beacon` on your PATH at this working copy, until `just trial-off`
[group('start here')]
trial-on:
    @python3 scripts/beacon install --skip-layout
    @echo
    @echo "Trialling $(python3 scripts/beacon --version) from $(pwd)."
    @echo "Run \`exec zsh\` to pick it up; \`just trial-off\` to revert."

# put the installed plugin build back on your PATH
[group('start here')]
trial-off:
    @bash scripts/trial-off.sh

# preview the docsify docs site locally
[group('start here')]
docs:
    {{shipyard}} build-docs
    docsify serve docs --open

# run the python test suite (stdlib unittest, no external deps)
[group('check your work')]
test:
    python3 -m unittest discover -s tests -v

# read what the projection job would commit, without keeping it; `git restore .` discards
[group('check your work')]
check:
    {{shipyard}} generate
    git --no-pager diff --stat

# Non-zero while any check fails or an error is recorded, so `-` as below.
# check the install and report the errors hooks swallowed, with advice per kind
[group('check your work')]
doctor *args:
    -@python3 scripts/beacon doctor {{args}}

# regenerate all generated artifacts from source (describe, plugin.json, hooks.json, docs)
[group('regenerate from source')]
generate:
    {{shipyard}} generate

# resync plugin.yml suite.describe from the skills/rules/hooks sources
[group('regenerate from source')]
describe:
    {{shipyard}} gen-describe

# regenerate .claude-plugin/plugin.json from plugin.yml (the canonical descriptor)
[group('regenerate from source')]
plugin-json:
    {{shipyard}} gen-plugin-json

# The audit exits non-zero while anything is set, which `just` would report as a
# failed recipe; `-` keeps the listing clean for what is a read.
# read which iTerm2 prefs beacon's surfaces render through are set here; --write clears them
[group('iterm2 upkeep')]
reset-iterm-layout *args:
    -@python3 bin/beacon-iterm reset-layout {{args}}

# Non-zero while a release is unread, same as the audit above, so `-` again.
# update the iTerm2 clone to its latest release and report what beacon must read; --ack records it
[group('iterm2 upkeep')]
iterm-release *args:
    -@python3 dev/iterm-release.py {{args}}

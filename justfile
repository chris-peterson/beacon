# shipyard runs from its git ref, with no checkout and no install. CI is the
# writer for what lands; these recipes are for seeing the projection first.
shipyard := "uvx --from 'git+https://github.com/chris-peterson/shipyard@v2' shipyard"

default:
    @just --list

# regenerate all generated artifacts from source (describe, plugin.json, hooks.json, docs)
generate:
    {{shipyard}} generate

# read what the projection job would commit, without keeping it; `git restore .` discards
check:
    {{shipyard}} generate
    git --no-pager diff --stat

# preview the docsify docs site locally
docs:
    {{shipyard}} build-docs
    docsify serve docs --open

# regenerate .claude-plugin/plugin.json from plugin.yml (the canonical descriptor)
plugin-json:
    {{shipyard}} gen-plugin-json

# resync plugin.yml suite.describe from the skills/rules/hooks sources
describe:
    {{shipyard}} gen-describe

# launch an interactive Claude Code session with the local plugin loaded
try:
    claude --plugin-dir .

# seed an isolated demo fleet, serve the dashboard, and live-simulate state changes
demo *args:
    python3 dev/demo.py {{args}}

# run the python test suite (stdlib unittest, no external deps)
test:
    python3 -m unittest discover -s tests -v

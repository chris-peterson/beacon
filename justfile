default:
    @just --list

# regenerate all generated artifacts from source (describe, plugin.json, docs)
generate:
    scripts/shipyard generate

# validate source projects cleanly and preview the pending projection (no write)
check:
    scripts/shipyard generate --dry-run

# preview the docsify docs site locally
docs:
    scripts/shipyard build-docs
    docsify serve docs --open

# regenerate .claude-plugin/plugin.json from plugin.yml (the canonical descriptor)
plugin-json:
    scripts/shipyard gen-plugin-json

# resync plugin.yml suite.describe from the skills/rules/hooks sources
describe:
    scripts/shipyard gen-describe

# launch an interactive Claude Code session with the local plugin loaded
try:
    claude --plugin-dir .

# seed an isolated demo fleet, serve the dashboard, and live-simulate state changes
demo *args:
    python3 dev/demo.py {{args}}

# run the python test suite (stdlib unittest, no external deps)
test:
    python3 -m unittest discover -s tests -v

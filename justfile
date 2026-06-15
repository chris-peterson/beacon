default:
    @just --list

# preview the docsify docs site locally
docs:
    python3 scripts/gen-suite-json.py
    docsify serve docs --open

# regenerate .claude-plugin/plugin.json from plugin.yml (the canonical descriptor)
plugin-json:
    python3 scripts/gen-plugin-json.py

# verify plugin.json is in sync with plugin.yml (used by CI and the pre-commit hook)
plugin-json-check:
    python3 scripts/gen-plugin-json.py --check

# install the git pre-commit hook that keeps plugin.json in sync with plugin.yml
install-hooks:
    cp scripts/hooks/pre-commit .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
    @echo "installed .git/hooks/pre-commit"

# launch an interactive Claude Code session with the local plugin loaded
try:
    claude --plugin-dir .

# run the python test suite (stdlib unittest, no external deps)
test:
    python3 -m unittest discover -s tests -v

# render marginalia overlay gallery → .preview/index.html (auto-opens)
preview:
    @python3 dev/preview.py
    @open .preview/index.html

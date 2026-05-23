default:
    @just --list

# preview the docsify docs site locally
docs:
    docsify serve docs --open

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

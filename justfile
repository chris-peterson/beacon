default:
    @just --list

# preview the docsify docs site locally
docs:
    docsify serve docs --open

# launch an interactive Claude Code session with the local plugin loaded
try:
    claude --plugin-dir .

# Changelog

## 0.4.0

### Features
- `beacon --version` (and `-v`) now reports the installed plugin version, sourced from `.claude-plugin/plugin.json`.
- The beacon skill now checks CLI freshness before its first invocation in a session. If the shell `beacon` wrapper (from `/beacon:beacon install`) is older than the running plugin, it surfaces a one-line note and offers to refresh.

### Other
- Documented the auto-update path for end users in the Upgrade section of the README.

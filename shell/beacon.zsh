# beacon zsh integration — publishes project + branch user vars to iTerm2
# on every prompt. Source from .zshrc:
#
#   source /path/to/beacon/shell/beacon.zsh
#
# When in a recognized project, sets user.beacon_project to the project name
# and user.beacon_branch to the current git branch (with a leading separator
# so empty values collapse cleanly in the badge format string).

if [[ -n "${_BEACON_INSTALLED:-}" ]]; then
  return 0
fi

# Path to the beacon-iterm CLI, derived from this file's location.
typeset -g _BEACON_ITERM="${0:A:h:h}/bin/beacon-iterm"

if [[ ! -x "$_BEACON_ITERM" ]]; then
  echo "beacon.zsh: beacon-iterm not found at $_BEACON_ITERM" >&2
  return 1
fi

# Path to the plugin script — used by helpers below (resolve-url, data-dir).
# The user-facing `beacon` command on PATH comes from a wrapper installed by
# `beacon install-cli` to ~/.local/bin/beacon, NOT from a shell alias. The
# wrapper is what the SessionStart freshness hook (hooks/cli-freshness.sh)
# can see via `command -v beacon` from non-interactive shells; an alias
# wouldn't be visible there.
typeset -g _BEACON_SCRIPT="${0:A:h:h}/scripts/beacon"

# tack's route directory, mirroring the plugin's `TACK_HOME or ~/.tack`
# resolution (scripts/beacon) so a relocated tack home keeps the url-cache
# signal correct. Each route lives at `<dir>/<slug>.yaml`; the precmd folds
# the matching route file's mtime into the url cache key so a mid-session
# tack write (which bumps that mtime) forces one re-resolve without a `cd`
# or branch switch.
typeset -g _BEACON_TACK_ROUTES="${TACK_HOME:-$HOME/.tack}/routes"

# `zstat` for the per-prompt route-file mtime probe — a pure-zsh stat that
# keeps the hot path free of an extra subprocess.
zmodload -F zsh/stat b:zstat

# Critical escape sequences emitted FAST via raw printf — no python3 startup
# in the hot path.
#
# Switch this pane into the beacon-dev profile (STATUS-BAR-01): it carries the
# status bar layout and badge sizing, and is the dev cycle's base profile.
# beacon-dev is not iTerm2's default profile, so interactive panes activate it
# here; Claude panes do it at SessionStart. A non-iTerm terminal silently
# ignores the sequence.
printf '\e]1337;SetProfile=beacon-dev\a'
# Badge (BADGE-15): opt-in, off by default — the tab (color + two-line
# identity) and the status-bar titlebar carry the identity now, so the badge is
# redundant in a tabs workflow. Emit its format only when the user config turns
# it on (`"badge": "on"` in ~/.config/beacon/config.json). Read once here at
# source, never in the per-prompt hot path. Set after SetProfile, which wipes
# session OSC overrides including SetBadgeFormat (§6.10).
if [[ "${(L)$(python3 "$_BEACON_SCRIPT" config-get badge 2>/dev/null)}" == (1|true|on|yes) ]]; then
  printf '\e]1337;SetBadgeFormat=%s\a' \
    "$(printf '%s' '\(user.beacon_project)\(user.beacon_task)' | base64)"
fi

# Project markers (mirrors PROV-05 in docs/spec.md).
typeset -gra _BEACON_MARKERS=(
  .git package.json Cargo.toml pyproject.toml go.mod .hg pom.xml Gemfile
)

_beacon_project_root() {
  local dir="$PWD"
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    # Stop at $HOME — markers there (stray package.json, dotfiles .git) don't
    # represent the user's "current project".
    [[ "$dir" == "$HOME" ]] && return 1
    for m in $_BEACON_MARKERS; do
      [[ -e "$dir/$m" ]] && { print -r -- "$dir"; return 0 }
    done
    dir="${dir:h}"
  done
  return 1
}

# Outputs three lines: display, state, indicator.
#   display   — branch name, prefixed with an ahead/behind indicator only
#               when diverged so the eye can scan a column of branches and
#               spot divergent ones without re-parsing each name. Examples:
#                 "main"           (clean — synced with upstream)
#                 "↑3 feature"     (3 ahead)
#                 "↑3↓1 feature"   (3 ahead, 1 behind)
#                 "topic"          (untracked — color carries the signal)
#   state     — "clean" (synced with upstream), "diverged" (ahead/behind), or
#               "untracked" (no upstream set — local-only branch)
#   indicator — "" | "↑N" | "↓N" | "↑N↓M"
#   identity  — "default" (the repo's default branch) or "feature" (any other)
# All four empty when not in a git repo.
_beacon_branch_info() {
  local name
  name="$(git symbolic-ref --short HEAD 2>/dev/null)" || { printf '\n\n\n\n'; return }
  local state="untracked" ind="" counts ahead behind
  if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1 \
     && counts="$(git rev-list --left-right --count "@{u}...HEAD" 2>/dev/null)"; then
    behind="${counts%%	*}"
    ahead="${counts##*	}"
    if (( ahead == 0 && behind == 0 )); then
      state="clean"
    else
      state="diverged"
      (( ahead > 0 ))  && ind+="↑${ahead}"
      (( behind > 0 )) && ind+="↓${behind}"
    fi
  fi
  # Identity axis (#20): the default branch is de-emphasized whatever its state;
  # a feature branch reads by state. origin/HEAD names the default when it's set
  # (git clone / `git remote set-head`); when it isn't, fall back to the
  # conventional names so a fresh local repo still classifies main/master/trunk.
  local default_branch identity="feature"
  default_branch="$(git symbolic-ref --short --quiet refs/remotes/origin/HEAD 2>/dev/null)"
  default_branch="${default_branch#origin/}"
  if [[ -z "$default_branch" ]]; then
    case "$name" in main|master|trunk) default_branch="$name" ;; esac
  fi
  [[ -n "$default_branch" && "$name" == "$default_branch" ]] && identity="default"
  local display="$name"
  [[ "$state" == "diverged" ]] && display="${ind} ${name}"
  print -r -- "$display"
  print -r -- "$state"
  print -r -- "$ind"
  print -r -- "$identity"
}

# Local cwd with $HOME substituted as ~ (STATUS-BAR-05).
_beacon_local_path() {
  print -r -- "${PWD/#$HOME/~}"
}

# Abbreviated remote identity (e.g. `gh:owner/repo`), or empty when not in a
# recognized git project. Used by the status bar's project_full chip. Known
# forge hosts collapse to a 2-letter prefix; unknown hosts pass through as
# `host/owner/repo`. Mirrors python's `_project_full_at` / `_abbrev_remote_host`.
_beacon_project_full() {
  local root
  root="$(_beacon_project_root)" || { print -r -- ""; return }
  local url=""
  if [[ -d "$root/.git" || -f "$root/.git" ]]; then
    url="$(git -C "$root" config --get remote.origin.url 2>/dev/null)"
  fi
  if [[ -z "$url" ]]; then
    print -r -- ""
    return
  fi
  local path="$url"
  if [[ "$path" == *"://"* ]]; then
    path="${path#*://}"
    path="${path#*@}"            # strip optional user@ prefix
  elif [[ "$path" == *":"* ]]; then
    # ssh form: git@host:owner/repo.git → host/owner/repo
    local host_path="${path#*@}"
    local host="${host_path%%:*}"
    local p="${host_path#*:}"
    path="$host/$p"
  fi
  path="${path%/}"
  path="${path%.git}"
  case "$path" in
    github.com/*)    path="gh:${path#github.com/}"    ;;
    gitlab.com/*)    path="gl:${path#gitlab.com/}"    ;;
    bitbucket.org/*) path="bb:${path#bitbucket.org/}" ;;
  esac
  print -r -- "$path"
}

# PROV-07 implementation. Override-point: redefine in your .zshrc
# AFTER sourcing beacon.zsh to swap in a non-tack URL provider (Linear, Jira,
# GitHub Issues, etc.). Default impl delegates to the plugin, which knows the
# full chain (override → tack → branch URL → project URL).
# Output format: "<url>\t<label>\n" (TAB-separated).
_beacon_resolve_url() {
  python3 "$_BEACON_SCRIPT" resolve-url 2>/dev/null
}

# Suffix derived from a forge issue/PR/MR URL: `#42` for issues/PRs, `!17`
# for GitLab MRs. Empty when the URL isn't a recognized deliverable. Used
# to contextualize the project_full chip when PROV-07 returns a deliverable
# URL. Mirrors python's `_deliverable_suffix`. GitLab patterns come first
# because their `/-/issues/` and `/-/merge_requests/` paths contain the
# literal substring `/issues/` that the generic GitHub patterns would also
# match — we want the GitLab sigil (`!` for MRs) to win on GitLab URLs.
_beacon_deliverable_suffix() {
  emulate -L zsh
  local url="$1"
  local sigil="" id=""
  case "$url" in
    *"/-/merge_requests/"*) sigil="!"; id="${${url##*"/-/merge_requests/"}%%[!0-9]*}" ;;
    *"/-/issues/"*)         sigil="#"; id="${${url##*"/-/issues/"}%%[!0-9]*}" ;;
    *"/pull/"*)             sigil="#"; id="${${url##*"/pull/"}%%[!0-9]*}" ;;
    *"/issues/"*)           sigil="#"; id="${${url##*"/issues/"}%%[!0-9]*}" ;;
  esac
  [[ -n "$id" ]] && print -r -- "${sigil}${id}"
}

# Track last-published values so we only emit on change. The sentinel ensures
# the first publish always fires — including when the resolved value is empty
# (e.g. shell starts in a non-project directory). Without this, an empty
# resolved value would match the initial empty state and we'd skip the publish.
typeset -g _BEACON_LAST_PROJECT_FULL='__unset__'
typeset -g _BEACON_LAST_TITLE='__unset__'
typeset -g _BEACON_LAST_BRANCH='__unset__'
typeset -g _BEACON_LAST_BRANCH_STATE='__unset__'
typeset -g _BEACON_LAST_BRANCH_DEFAULT='__unset__'
typeset -g _BEACON_LAST_BRANCH_CLEAN='__unset__'
typeset -g _BEACON_LAST_BRANCH_DIVERGED='__unset__'
typeset -g _BEACON_LAST_BRANCH_UNTRACKED='__unset__'
typeset -g _BEACON_LAST_LOCAL_PATH='__unset__'
typeset -g _BEACON_LAST_URL_SIGNAL='__unset__'
typeset -g _BEACON_LAST_URL='__unset__'
typeset -g _BEACON_RESOLVED_URL=''

# Per-session file handoff for status-bar action buttons. Action enum 35
# doesn't interpolate \(user.*) reliably, so the `go` and `code` buttons
# read these files instead. Derive the cache dir from the script so the
# shell, hooks, and slash commands converge on the same path regardless
# of whether the install lives in the marketplace cache or a working tree.
_beacon_data_dir="$(python3 "$_BEACON_SCRIPT" data-dir)"
if [[ -z "$_beacon_data_dir" ]]; then
  echo "beacon.zsh: failed to resolve data dir via $_BEACON_SCRIPT" >&2
  return 1
fi
typeset -gr _BEACON_CACHE_DIR="$_beacon_data_dir/cache"
unset _beacon_data_dir
mkdir -p "$_BEACON_CACHE_DIR"

# Window title (TITLE-01): give an interactive pane its identity as the OS
# window title, so a beacon-dev pane isn't left showing the profile name (the
# profile disables OSC title-setting, so the shell can't printf a title like the
# badge). A plain shell has no task, so it shows the project when in one and its
# cwd otherwise — beacon_title carries that "project else cwd" value (published
# each precmd, mirroring the plugin's value-level badge fallback per BADGE-04).
#
# The session name is a single shared surface (TITLE-04): a Claude pane wants
# `project · task` from the plugin, not this taskless interactive title, and the
# two writers race. Backgrounded, this osascript can land last and strand an
# engaged pane on the interactive title. So defer to the plugin: poll briefly for
# its engagement marker (same GUID key as the handoff files) and skip the write
# once the pane is Claude-owned — the plugin is then the sole writer of an engaged
# pane's name, so there is nothing left to race. A plain pane never gets the
# marker, so the title lands after the short poll. Runs here (not up top with the
# fast-path OSC) because the marker lives under _BEACON_CACHE_DIR; backgrounded
# (`&!`) so neither the poll nor the osascript delays startup. The name is an
# interpolated string, rendered once the first precmd publishes beacon_title.
if [[ -n "$ITERM_SESSION_ID" ]]; then
  {
    _beacon_marker="${_BEACON_CACHE_DIR}/engaged-${ITERM_SESSION_ID##*:}"
    _beacon_engaged=0
    for _beacon_i in 1 2 3 4 5; do
      [[ -e "$_beacon_marker" ]] && { _beacon_engaged=1; break; }
      sleep 0.4
    done
    (( _beacon_engaged )) || \
      "$_BEACON_ITERM" set-name "$ITERM_SESSION_ID" '\(user.beacon_title)'
  } &>/dev/null &!
fi

_beacon_write_session_file() {
  # Skip when the pane id is unavailable (non-iTerm shell). Mirrors the
  # plugin's `if key:` guard: an empty id would write the shared
  # `cwd-.txt` / `url-.txt`, which the action buttons then serve to every
  # empty-id session.
  [[ -n "$ITERM_SESSION_ID" ]] || return 0
  # Key on the pane GUID (the segment after the last colon), not the full
  # ITERM_SESSION_ID: the `wNtNpN` prefix changes when the pane is moved, so
  # keying on it would leave the buttons reading a stale file after a move.
  # Mirrors _iterm_cache_key() in scripts/beacon and the CLI's GUID targeting.
  print -r -- "$2" > "${_BEACON_CACHE_DIR}/${1}-${ITERM_SESSION_ID##*:}.txt"
}

_beacon_precmd() {
  # BADGE-02: the plugin is the sole writer of `beacon_project`. The shell
  # snippet deliberately does NOT publish it from precmd — the badge text
  # follows intentional signals (overrides, SessionStart anchor) rather
  # than every `cd`. Status-bar user-vars (branch, project_full, url)
  # below are still published because the status bar IS meant to track
  # cwd — different surface, different contract.

  local -a binfo
  binfo=("${(@f)$(_beacon_branch_info)}")
  local b="${binfo[1]}" bstate="${binfo[2]}" bidentity="${binfo[4]}"
  # Hybrid branch color (#20): the default branch publishes one de-emphasized
  # slot whatever its state; a feature branch routes to its state slot. Exactly
  # one of the four is non-empty, so the profile's four branch components (each
  # a fixed color) resolve to a single visible one via remove-empty-components.
  local b_default="" b_clean="" b_diverged="" b_untracked=""
  if [[ "$bidentity" == "default" ]]; then
    b_default="$b"
  else
    [[ "$bstate" == "clean"     ]] && b_clean="$b"
    [[ "$bstate" == "diverged"  ]] && b_diverged="$b"
    [[ "$bstate" == "untracked" ]] && b_untracked="$b"
  fi

  if [[ "$b" != "$_BEACON_LAST_BRANCH" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch "$b"
    _BEACON_LAST_BRANCH="$b"
  fi
  if [[ "$bstate" != "$_BEACON_LAST_BRANCH_STATE" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch_state "$bstate"
    _BEACON_LAST_BRANCH_STATE="$bstate"
  fi
  if [[ "$b_default" != "$_BEACON_LAST_BRANCH_DEFAULT" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch_default "$b_default"
    _BEACON_LAST_BRANCH_DEFAULT="$b_default"
  fi
  if [[ "$b_clean" != "$_BEACON_LAST_BRANCH_CLEAN" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch_clean "$b_clean"
    _BEACON_LAST_BRANCH_CLEAN="$b_clean"
  fi
  if [[ "$b_diverged" != "$_BEACON_LAST_BRANCH_DIVERGED" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch_diverged "$b_diverged"
    _BEACON_LAST_BRANCH_DIVERGED="$b_diverged"
  fi
  if [[ "$b_untracked" != "$_BEACON_LAST_BRANCH_UNTRACKED" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch_untracked "$b_untracked"
    _BEACON_LAST_BRANCH_UNTRACKED="$b_untracked"
  fi

  local lp="$(_beacon_local_path)"
  if [[ "$lp" != "$_BEACON_LAST_LOCAL_PATH" ]]; then
    _beacon_write_session_file cwd "$PWD"
    _BEACON_LAST_LOCAL_PATH="$lp"
  fi

  # URL resolution is heavier (python startup + possible tack subprocess).
  # Only re-resolve when the signal changed; otherwise the cached URL is still
  # valid. Resolving here (before project_full publish) lets the chip
  # contextualize itself with the deliverable suffix via _beacon_deliverable_suffix.
  #
  # cwd and branch don't move when a deliverable/link is recorded on the route
  # mid-session, but the route file's mtime does — every tack write bumps it.
  # Folding that mtime into the key lets the badge upgrade to the route URL
  # within one prompt cycle, while the heavy resolve still fires only on a real
  # change. The route lives at `<routes>/<branch>.yaml` because the tack step
  # matches the route slug to the branch, so this adds signal exactly where the
  # tack step can produce a URL and is a no-op (empty mtime) elsewhere.
  local tack_mtime=""
  zstat -A tack_mtime +mtime -- "${_BEACON_TACK_ROUTES}/${b}.yaml" 2>/dev/null
  local url_signal="${lp}@${b}@${tack_mtime[1]:-}"
  if [[ "$url_signal" != "$_BEACON_LAST_URL_SIGNAL" ]]; then
    local raw="$(_beacon_resolve_url)"
    _BEACON_RESOLVED_URL="${raw%%	*}"
    _BEACON_LAST_URL_SIGNAL="$url_signal"
  fi
  local url="$_BEACON_RESOLVED_URL"

  local pf_base="$(_beacon_project_full)"
  local pf="$pf_base"
  [[ -n "$pf_base" ]] && pf="${pf_base}$(_beacon_deliverable_suffix "$url")"
  if [[ "$pf" != "$_BEACON_LAST_PROJECT_FULL" ]]; then
    "$_BEACON_ITERM" uservar beacon_project_full "$pf"
    _BEACON_LAST_PROJECT_FULL="$pf"
  fi

  # Window title value (TITLE-01): the project identity when in one, else the
  # cwd, so a plain shell outside any project shows where it is rather than a
  # blank title. Kept separate from beacon_project_full — the status-bar chip
  # collapses when empty, so it must NOT carry the cwd fallback. Local path is
  # never empty (PWD always set), so the title never goes blank.
  local title="${pf:-$lp}"
  if [[ "$title" != "$_BEACON_LAST_TITLE" ]]; then
    "$_BEACON_ITERM" uservar beacon_title "$title"
    _BEACON_LAST_TITLE="$title"
  fi

  if [[ "$url" != "$_BEACON_LAST_URL" ]]; then
    "$_BEACON_ITERM" uservar beacon_url "$url"
    _beacon_write_session_file url "$url"
    _BEACON_LAST_URL="$url"
  fi
}

_beacon_chpwd() {
  # Force re-publish on directory change — branch may have changed even if
  # project is the same, and project may have changed entirely.
  _BEACON_LAST_PROJECT_FULL='__unset__'
  _BEACON_LAST_TITLE='__unset__'
  _BEACON_LAST_BRANCH='__unset__'
  _BEACON_LAST_BRANCH_STATE='__unset__'
  _BEACON_LAST_BRANCH_CLEAN='__unset__'
  _BEACON_LAST_BRANCH_DIVERGED='__unset__'
  _BEACON_LAST_BRANCH_UNTRACKED='__unset__'
  _BEACON_LAST_LOCAL_PATH='__unset__'
  _BEACON_LAST_URL_SIGNAL='__unset__'
  _BEACON_LAST_URL='__unset__'
  _beacon_precmd
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd _beacon_precmd
add-zsh-hook chpwd  _beacon_chpwd

# Publish immediately on source so a fresh shell shows the right values
# without waiting for the first prompt.
_beacon_chpwd

typeset -g _BEACON_INSTALLED=1

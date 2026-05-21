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

# Critical escape sequences emitted FAST via raw printf — no python3 startup
# in the hot path. These determine how soon a freshly-split pane stops
# showing the parent's pause overlay.
#
# Clear inherited bg-image (OVERLAY-02): freshly-split panes inherit the
# parent's session OSC overrides, including any pause overlay. The clear is
# harmless when no overlay exists, and necessary when one does.
printf '\e]1337;SetBackgroundImageFile=\a'
# Badge format: project + optional task suffix. The task slot self-collapses
# when empty (beacon_task carries ": <task>" when set). The badge renders
# only after engagement (BADGE-14) populates beacon_project; until then both
# user vars are empty and the format evaluates to nothing, so a fresh
# terminal shows no badge.
printf '\e]1337;SetBadgeFormat=%s\a' \
  "$(printf '%s' '\(user.beacon_project)\(user.beacon_task)' | base64)"

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
# All three empty when not in a git repo.
_beacon_branch_info() {
  local name
  name="$(git symbolic-ref --short HEAD 2>/dev/null)" || { printf '\n\n\n'; return }
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
  local display="$name"
  [[ "$state" == "diverged" ]] && display="${ind} ${name}"
  print -r -- "$display"
  print -r -- "$state"
  print -r -- "$ind"
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
typeset -g _BEACON_LAST_BRANCH='__unset__'
typeset -g _BEACON_LAST_BRANCH_STATE='__unset__'
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

_beacon_write_session_file() {
  print -r -- "$2" > "${_BEACON_CACHE_DIR}/${1}-${ITERM_SESSION_ID}.txt"
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
  local b="${binfo[1]}" bstate="${binfo[2]}"
  local b_clean="" b_diverged="" b_untracked=""
  [[ "$bstate" == "clean"     ]] && b_clean="$b"
  [[ "$bstate" == "diverged"  ]] && b_diverged="$b"
  [[ "$bstate" == "untracked" ]] && b_untracked="$b"

  if [[ "$b" != "$_BEACON_LAST_BRANCH" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch "$b"
    _BEACON_LAST_BRANCH="$b"
  fi
  if [[ "$bstate" != "$_BEACON_LAST_BRANCH_STATE" ]]; then
    "$_BEACON_ITERM" uservar beacon_branch_state "$bstate"
    _BEACON_LAST_BRANCH_STATE="$bstate"
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
  # Only re-resolve when cwd or branch changed; otherwise the cached URL is
  # still valid. Resolving here (before project_full publish) lets the chip
  # contextualize itself with the deliverable suffix via _beacon_deliverable_suffix.
  local url_signal="${lp}@${b}"
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

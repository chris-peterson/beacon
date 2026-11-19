# beacon zsh integration — puts an interactive pane in the beacon profile and
# keeps its window title on the project (or cwd) at every prompt. Source from
# .zshrc:
#
#   source /path/to/beacon/shell/beacon.zsh

if [[ -n "${_BEACON_INSTALLED:-}" ]]; then
  return 0
fi

# Path to the beacon-iterm CLI, derived from this file's location.
typeset -g _BEACON_ITERM="${0:A:h:h}/bin/beacon-iterm"

if [[ ! -x "$_BEACON_ITERM" ]]; then
  echo "beacon.zsh: beacon-iterm not found at $_BEACON_ITERM" >&2
  return 1
fi

# Path to the plugin script — used by the source-time `shell-init` read below.
# The user-facing `beacon` command on PATH comes from a wrapper installed by
# `beacon install` to ~/.local/bin/beacon, NOT from a shell alias. The
# wrapper is what the SessionStart freshness hook (hooks/cli-freshness.sh)
# can see via `command -v beacon` from non-interactive shells; an alias
# wouldn't be visible there.
typeset -g _BEACON_SCRIPT="${0:A:h:h}/scripts/beacon"

# Source-time answers that need the plugin's own resolution: the data dir and
# the opt-in badge gate. Asking python for them costs an interpreter startup
# each, on every new terminal — the largest single item in this file's budget,
# spent on values that change only when the user edits a config. So cache the
# block and regenerate it only when an input changed. Every test below is a
# shell builtin, so the steady state forks nothing.
#
# The cache is keyed by plugin root: two installs (the marketplace copy and a
# working tree) resolve different data dirs, and one shared file would hand an
# install the other's answer.
_beacon_cfg_dir="${XDG_CONFIG_HOME:-$HOME/.config}/beacon"
_beacon_cfg="$_beacon_cfg_dir/config.json"
typeset -g _BEACON_INIT_CACHE="$_beacon_cfg_dir/shell-init${${0:A:h:h}//[^A-Za-z0-9]/_}.zsh"

_beacon_stale=1
if [[ -r "$_BEACON_INIT_CACHE" ]]; then
  source "$_BEACON_INIT_CACHE"
  _beacon_stale=''
  [[ "$_beacon_cfg"              -nt "$_BEACON_INIT_CACHE"
     || "$_beacon_cfg_dir/data-dir" -nt "$_BEACON_INIT_CACHE"
     || "$_BEACON_SCRIPT"           -nt "$_BEACON_INIT_CACHE" ]] && _beacon_stale=1
  # An mtime test can't see a *deleted* config: nothing is newer than the cache
  # afterwards, so the shell would keep the settings that file used to carry.
  # Compare its presence against what it was when the block was built.
  [[ -e "$_beacon_cfg" ]] && _beacon_present=1 || _beacon_present=''
  [[ "$_beacon_present" == "$_BEACON_INIT_HAD_CONFIG" ]] || _beacon_stale=1
fi

if [[ -n "$_beacon_stale" ]]; then
  mkdir -p "$_beacon_cfg_dir"
  if ! python3 "$_BEACON_SCRIPT" shell-init > "$_BEACON_INIT_CACHE"; then
    echo "beacon.zsh: failed to resolve source-time config via $_BEACON_SCRIPT" >&2
    rm -f "$_BEACON_INIT_CACHE"
    return 1
  fi
  source "$_BEACON_INIT_CACHE"
fi
unset _beacon_cfg_dir _beacon_cfg _beacon_stale _beacon_present

# Every surface below is painted by writing an escape sequence to the terminal
# device rather than to stdout, because `precmd` and `chpwd` also fire inside
# command-substitution subshells — where stdout is the value being captured, so
# publishing there splices escape bytes into `x=$(cd somedir; ...)`.
#
# Only an open attempt detects a missing controlling terminal; `-w` and `-c`
# both report success on the /dev/tty device node when opening it would fail.
if ! { : > /dev/tty } 2>/dev/null; then
  echo "beacon.zsh: /dev/tty is not writable — no terminal to paint" >&2
  return 1
fi

# Critical escape sequences emitted FAST via raw printf — no python3 startup
# in the hot path.
#
# Switch this pane into the beacon-dev profile (RENDER-05): it carries the badge
# sizing and the session switcher's keys (FOCUS-07), and is the dev cycle's base
# profile.
# beacon-dev is not iTerm2's default profile, so interactive panes activate it
# here; Claude panes do it at SessionStart. A non-iTerm terminal silently
# ignores the sequence.
printf '\e]1337;SetProfile=beacon-dev\a' > /dev/tty
# Badge (BADGE-15): opt-in, off by default — the tab (color + two-line
# identity) carries the identity now, so the badge is redundant in a tabs
# workflow. Emit its format only when the user config turns it on
# (`"badge": "on"` in ~/.config/beacon/config.json). Read once here at source,
# never in the per-prompt hot path. Set after SetProfile, which wipes session
# OSC overrides including SetBadgeFormat (§6.10).
if [[ -n "$_BEACON_BADGE_ON" ]]; then
  printf '\e]1337;SetBadgeFormat=%s\a' \
    "$(printf '%s' '\(user.beacon_project)\(user.beacon_task)' | base64)" > /dev/tty
fi

# Project markers (mirrors PROV-05 in docs/spec.md).
typeset -gra _BEACON_MARKERS=(
  .git package.json Cargo.toml pyproject.toml go.mod .hg pom.xml Gemfile
)

# These helpers answer through `_beacon_reply` rather than by printing. Every `$(...)` on the prompt path forks a subshell — four of them
# cost more than the one `git` call left in here.
typeset -g _beacon_reply=''

_beacon_project_root() {
  local dir="$PWD"
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    # Stop at $HOME — markers there (stray package.json, dotfiles .git) don't
    # represent the user's "current project".
    [[ "$dir" == "$HOME" ]] && return 1
    for m in $_BEACON_MARKERS; do
      [[ -e "$dir/$m" ]] && { _beacon_reply="$dir"; return 0 }
    done
    dir="${dir:h}"
  done
  return 1
}

# The project's name (e.g. `beacon`) — the remote's repo basename, else the
# project root's own directory name. Empty when not in a recognized project, so
# the caller can tell "no project" from "a project called X"; the window title
# floors that to the abbreviated cwd. Mirrors python's `_project_name_at`.
#
# The origin URL is memoized for the life of the shell: reading it costs a
# `git config` fork on a path that runs every prompt, and a repo's origin
# changes about once in its life — a `git remote set-url` shows up after the
# next `exec zsh`.
typeset -gA _BEACON_ORIGIN_URL

_beacon_project_name() {
  _beacon_project_root || { _beacon_reply=""; return }
  local root="$_beacon_reply"
  if (( ! ${+_BEACON_ORIGIN_URL[$root]} )); then
    local fresh=""
    if [[ -d "$root/.git" || -f "$root/.git" ]]; then
      fresh="$(git -C "$root" config --get remote.origin.url 2>/dev/null)"
    fi
    _BEACON_ORIGIN_URL[$root]="$fresh"
  fi
  local url="${_BEACON_ORIGIN_URL[$root]}"
  if [[ -n "$url" ]]; then
    local path="${url%/}"
    path="${path%.git}"
    _beacon_reply="${path:t}"
    return
  fi
  _beacon_reply="${root:t}"
}

# Track last-published values so we only emit on change. The sentinel ensures
# the first publish always fires — including when the resolved value is empty
# (e.g. shell starts in a non-project directory). Without this, an empty
# resolved value would match the initial empty state and we'd skip the publish.
typeset -g _BEACON_LAST_TITLE='__unset__'

# The engagement marker below lives in the data dir's cache, resolved by the
# plugin (shell-init) so the shell, hooks, and slash commands converge on one
# path whether the install is the marketplace copy or a working tree.
if [[ -z "$_BEACON_DATA_DIR" ]]; then
  echo "beacon.zsh: failed to resolve data dir via $_BEACON_SCRIPT" >&2
  return 1
fi
typeset -gr _BEACON_CACHE_DIR="$_BEACON_DATA_DIR/cache"
mkdir -p "$_BEACON_CACHE_DIR"

# Window title (TITLE-01): give an interactive pane its identity as the OS
# window title, so a beacon-dev pane isn't left showing the profile name (the
# profile disables OSC title-setting, so the shell can't printf a title like the
# badge). A plain shell has no task, so it shows the project when in one and its
# cwd otherwise — beacon_title carries that "project else cwd" value (published
# each precmd, mirroring the plugin's value-level badge fallback per BADGE-04).
#
# The session name is a single shared surface (TITLE-04): a Claude pane wants
# `project · task` from the plugin, not this taskless interactive title, so the
# marker (keyed on the pane GUID) says the pane is Claude-owned and
# this write is not wanted — the case being a shell that starts *inside* an
# already-engaged pane, an `exec zsh` most of all.
#
# Checked once, and the write fires immediately: the plugin re-asserts the
# managed name on its first render and after every profile swap, so a pane that
# engages later corrects itself within the turn. Waiting for the marker is what
# makes the two writers race — a deferred write is the one that lands last and
# strands an engaged pane on the interactive title — and it costs every plain
# tab the full wait, since a plain pane never gets a marker at all. Runs here
# (not up top with the fast-path OSC) because the marker lives under
# _BEACON_CACHE_DIR; backgrounded (`&!`) so the osascript round trip doesn't
# delay the first prompt. The name is an interpolated string, rendered once the
# first precmd publishes beacon_title.
#
# A shell Claude Code spawns carries CLAUDECODE and runs inside the pane Claude
# holds, so it never writes. The marker alone misses one of them: the snapshot
# shell Claude builds on its first Bash call sources this file with a terminal,
# and while two installs run at once the data dir it resolves can be the other
# install's, which holds no marker for this pane.
if [[ -n "$ITERM_SESSION_ID" && -z "${CLAUDECODE:-}" ]]; then
  {
    _beacon_marker="${_BEACON_CACHE_DIR}/engaged-${ITERM_SESSION_ID##*:}"
    [[ -e "$_beacon_marker" ]] || \
      "$_BEACON_ITERM" set-name "$ITERM_SESSION_ID" '\(user.beacon_title)'
  } &>/dev/null &!
fi

# Indexed 1-based, matching zsh's string subscripting.
typeset -gr _BEACON_B64_ALPHABET='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
typeset -g _beacon_b64_out=''

# Base64-encode $1 into `_beacon_b64_out`, UTF-8 first. iTerm2 wants SetUserVar
# values base64'd, and `| base64` would put a fork back on the path — the whole
# point here is that publishing a slot costs no process at all. The UTF-8 step
# is load-bearing rather than pedantic: a title can carry a non-ASCII path, and
# zsh's `#ch` yields a codepoint where base64 needs the bytes.
_beacon_b64() {
  # `multibyte` is the default but a user can turn it off, and with it off the
  # loop below reads bytes as codepoints and re-encodes each one — mojibake in
  # the title. Force it for the length of this function.
  setopt localoptions multibyte noksharrays
  local s=$1 i n=${#1} ch cp out=''
  local -a b
  for (( i = 1; i <= n; i++ )); do
    ch=${s[i]}
    cp=$(( #ch ))
    if (( cp < 0x80 )); then
      b+=($cp)
    elif (( cp < 0x800 )); then
      b+=($(( 0xC0 | cp >> 6 )) $(( 0x80 | cp & 63 )))
    elif (( cp < 0x10000 )); then
      b+=($(( 0xE0 | cp >> 12 )) $(( 0x80 | cp >> 6 & 63 )) $(( 0x80 | cp & 63 )))
    else
      b+=($(( 0xF0 | cp >> 18 )) $(( 0x80 | cp >> 12 & 63 )) \
          $(( 0x80 | cp >> 6 & 63 )) $(( 0x80 | cp & 63 )))
    fi
  done
  local c1 c2 c3
  n=${#b}
  for (( i = 1; i <= n; i += 3 )); do
    c1=$b[i]
    (( i + 1 <= n )) && c2=$b[i+1] || c2=0
    (( i + 2 <= n )) && c3=$b[i+2] || c3=0
    out+="${_BEACON_B64_ALPHABET[$(( (c1 >> 2) + 1 ))]}"
    out+="${_BEACON_B64_ALPHABET[$(( ((c1 & 3) << 4 | c2 >> 4) + 1 ))]}"
    if (( i + 1 > n )); then
      out+='=='
    elif (( i + 2 > n )); then
      out+="${_BEACON_B64_ALPHABET[$(( ((c2 & 15) << 2) + 1 ))]}="
    else
      out+="${_BEACON_B64_ALPHABET[$(( ((c2 & 15) << 2 | c3 >> 6) + 1 ))]}"
      out+="${_BEACON_B64_ALPHABET[$(( (c3 & 63) + 1 ))]}"
    fi
  done
  _beacon_b64_out=$out
}

# Publish `user.<name>` when it differs from what was last sent, and move the
# sentinel forward. The OSC goes out by raw printf for the same reason the
# profile activation above does: a prompt redraw can't afford a python start.
_beacon_publish() {
  local name=$1 value=$2 sentinel=$3
  [[ "$value" == "${(P)sentinel}" ]] && return
  _beacon_b64 "$value"
  printf '\e]1337;SetUserVar=%s=%s\a' "$name" "$_beacon_b64_out" > /dev/tty
  : ${(P)sentinel::=$value}
}

_beacon_precmd() {
  setopt localoptions noksharrays
  # BADGE-02: the plugin is the sole writer of `beacon_project`. The shell
  # snippet deliberately does NOT publish it from precmd — the badge text
  # follows intentional signals (overrides, SessionStart anchor) rather
  # than every `cd`.

  # Window title value (TITLE-01): the project identity when in one, else the
  # abbreviated cwd — a plain shell outside any project shows where it is
  # rather than a blank title. PWD is always set, so the title never goes blank.
  _beacon_project_name
  local title="${_beacon_reply:-${PWD/#$HOME/~}}"
  _beacon_publish beacon_title "$title" _BEACON_LAST_TITLE

  return 0
}

_beacon_chpwd() {
  # Force a re-publish on directory change: the project may have changed.
  _BEACON_LAST_TITLE='__unset__'
  _beacon_precmd
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd _beacon_precmd
add-zsh-hook chpwd  _beacon_chpwd

# Publish immediately on source so a fresh shell shows the right values
# without waiting for the first prompt.
_beacon_chpwd

typeset -g _BEACON_INSTALLED=1

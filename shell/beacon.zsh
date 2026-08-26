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
# Switch this pane into the beacon-dev profile (STATUS-BAR-01): it carries the
# status bar layout and badge sizing, and is the dev cycle's base profile.
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

# These helpers answer through `_beacon_reply` / `_beacon_binfo` rather than by
# printing. Every `$(...)` on the prompt path forks a subshell — four of them
# cost more than the one `git` call left in here.
typeset -g _beacon_reply=''
typeset -ga _beacon_binfo=()

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

# Outputs four lines: display, state, indicator, identity.
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
  setopt localoptions extendedglob noshwordsplit noksharrays
  # One `for-each-ref` supplies the branch name, its upstream, the ahead/behind
  # counts and the repo's default branch — the four `git` invocations this
  # replaced cost ~60ms of every prompt, against ~14ms here. Fields are
  # tab-separated because a ref name may contain `|` but never a control
  # character. Iterating all of refs/heads/ is what lets one call answer both
  # questions; it scales flat enough to not matter (~4ms extra at 500 branches).
  local -a rows row
  local line name="" upstream="" track="" default_branch=""
  rows=("${(@f)$(git for-each-ref \
      --format=$'%(HEAD)\t%(refname)\t%(upstream:short)\t%(upstream:track,nobracket)\t%(symref:short)' \
      refs/heads/ refs/remotes/origin/HEAD 2>/dev/null)}")
  for line in "$rows[@]"; do
    row=("${(@ps:\t:)line}")
    if [[ "${row[2]}" == "refs/remotes/origin/HEAD" ]]; then
      default_branch="${row[5]#origin/}"
    elif [[ "${row[1]}" == "*" ]]; then
      name="${row[2]#refs/heads/}"
      upstream="${row[3]}"
      track="${row[4]}"
    fi
  done
  # No `*` row means detached HEAD, no repo, or a branch with no commit yet —
  # an unborn HEAD points at a ref that `for-each-ref` cannot see. Only the last
  # of those has a name to show, and `symbolic-ref` is what distinguishes it,
  # so pay the extra call only here. `_detect_branch_info` in scripts/beacon
  # names an unborn branch too; without this the interactive prompt and a Claude
  # pane in the same fresh repo would disagree.
  if [[ -z "$name" ]]; then
    name="$(git symbolic-ref --short HEAD 2>/dev/null)" || {
      _beacon_binfo=('' '' '' ''); return
    }
  fi

  # An upstream that was deleted upstream reads as `gone`; it carries no counts,
  # so it classifies with the local-only branches rather than as diverged.
  local state="untracked" ind="" ahead=0 behind=0
  if [[ -n "$upstream" && "$track" != "gone" ]]; then
    if [[ -z "$track" ]]; then
      state="clean"
    else
      [[ "$track" == (#b)*"ahead "([0-9]##)*  ]] && ahead=$match[1]
      [[ "$track" == (#b)*"behind "([0-9]##)* ]] && behind=$match[1]
      state="diverged"
      (( ahead > 0 ))  && ind+="↑${ahead}"
      (( behind > 0 )) && ind+="↓${behind}"
    fi
  fi
  # Identity axis (#20): the default branch is de-emphasized whatever its state;
  # a feature branch reads by state. origin/HEAD names the default when it's set
  # (git clone / `git remote set-head`); when it isn't, fall back to the
  # conventional names so a fresh local repo still classifies main/master/trunk.
  local identity="feature"
  if [[ -z "$default_branch" ]]; then
    case "$name" in main|master|trunk) default_branch="$name" ;; esac
  fi
  [[ -n "$default_branch" && "$name" == "$default_branch" ]] && identity="default"
  local display="$name"
  [[ "$state" == "diverged" ]] && display="${ind} ${name}"
  _beacon_binfo=("$display" "$state" "$ind" "$identity")
}

# The project's name (e.g. `beacon`) — the remote's repo basename, else the
# project root's own directory name. Empty when not in a recognized project, so
# the caller can tell "no project" from "a project called X"; the status-bar
# chip floors that to the directory name, the window title to the abbreviated
# cwd. Mirrors python's `_project_name_at`.
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
typeset -g _BEACON_LAST_PROJECT_NAME='__unset__'
typeset -g _BEACON_LAST_TITLE='__unset__'
typeset -g _BEACON_LAST_BRANCH='__unset__'
typeset -g _BEACON_LAST_BRANCH_STATE='__unset__'
typeset -g _BEACON_LAST_BRANCH_DEFAULT='__unset__'
typeset -g _BEACON_LAST_BRANCH_CLEAN='__unset__'
typeset -g _BEACON_LAST_BRANCH_DIVERGED='__unset__'
typeset -g _BEACON_LAST_BRANCH_UNTRACKED='__unset__'
typeset -g _BEACON_LAST_LOCAL_PATH='__unset__'
typeset -g _BEACON_LAST_SSH_PATH_NL='__unset__'

# Set between an `ssh` preexec and the precmd that follows it — the window in
# which this pane's identity is a remote host rather than the local cwd.
typeset -g _BEACON_SSH_ACTIVE=0

# Per-session file handoff for status-bar action buttons. Action enum 35
# doesn't interpolate \(user.*) reliably, so the `go` and `code` buttons
# read these files instead. Derive the cache dir from the script so the
# shell, hooks, and slash commands converge on the same path regardless
# of whether the install lives in the marketplace cache or a working tree.
if [[ -z "$_BEACON_DATA_DIR" ]]; then
  echo "beacon.zsh: failed to resolve data dir via $_BEACON_SCRIPT" >&2
  return 1
fi
typeset -gr _BEACON_CACHE_DIR="$_BEACON_DATA_DIR/cache"
mkdir -p "$_BEACON_CACHE_DIR"

# A fresh shell is definitionally local, so any ssh marker here outlived the shell
# that wrote it — a pane killed mid-session, or an `exec zsh` from inside one.
# Without this the status-bar buttons would go on refusing forever.
[[ -n "$ITERM_SESSION_ID" ]] &&
  rm -f "${_BEACON_CACHE_DIR}/ssh-${ITERM_SESSION_ID##*:}.txt"

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
#
# beacon_ssh_path_nl is the remote cwd on line 2 during an ssh session (SSH-05),
# "" otherwise — the only slot a *remote* host writes, which is why line 1 stays
# a single locally-composed value. Both slots are set once here: iTerm2
# re-evaluates the name as either changes, so ssh needs no set-name of its own.
if [[ -n "$ITERM_SESSION_ID" ]]; then
  {
    _beacon_marker="${_BEACON_CACHE_DIR}/engaged-${ITERM_SESSION_ID##*:}"
    _beacon_engaged=0
    for _beacon_i in 1 2 3 4 5; do
      [[ -e "$_beacon_marker" ]] && { _beacon_engaged=1; break; }
      sleep 0.4
    done
    (( _beacon_engaged )) || \
      "$_BEACON_ITERM" set-name "$ITERM_SESSION_ID" \
        '\(user.beacon_title)\(user.beacon_ssh_path_nl)'
  } &>/dev/null &!
fi

_beacon_write_session_file() {
  # Skip when the pane id is unavailable (non-iTerm shell). Mirrors the
  # plugin's `if key:` guard: an empty id would write the shared `cwd-.txt`,
  # which the `↗ code` button then serves to every empty-id session.
  [[ -n "$ITERM_SESSION_ID" ]] || return 0
  # Key on the pane GUID (the segment after the last colon), not the full
  # ITERM_SESSION_ID: the `wNtNpN` prefix changes when the pane is moved, so
  # keying on it would leave the buttons reading a stale file after a move.
  # Mirrors _iterm_cache_key() in scripts/beacon and the CLI's GUID targeting.
  print -r -- "$2" > "${_BEACON_CACHE_DIR}/${1}-${ITERM_SESSION_ID##*:}.txt"
}

# Costs a fork, so it is only ever called on the ssh-exit path — once per
# session, never on the per-prompt path.
_beacon_rm_session_file() {
  [[ -n "$ITERM_SESSION_ID" ]] || return 0
  rm -f "${_BEACON_CACHE_DIR}/${1}-${ITERM_SESSION_ID##*:}.txt"
}

# Indexed 1-based, matching zsh's string subscripting.
typeset -gr _BEACON_B64_ALPHABET='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
typeset -g _beacon_b64_out=''

# Base64-encode $1 into `_beacon_b64_out`, UTF-8 first. iTerm2 wants SetUserVar
# values base64'd, and `| base64` would put a fork back on the path — the whole
# point here is that publishing a slot costs no process at all. The UTF-8 step
# is load-bearing rather than pedantic: the branch display carries ↑/↓ glyphs,
# and zsh's `#ch` yields a codepoint where base64 needs the bytes.
_beacon_b64() {
  # `multibyte` is the default but a user can turn it off, and with it off the
  # loop below reads bytes as codepoints and re-encodes each one — mojibake in
  # the branch chip. Force it for the length of this function.
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
# OpenSSH flags that consume the following word. Anything else is a boolean, so
# the first word that is neither a flag nor a flag's value is the destination.
typeset -gr _BEACON_SSH_VALUE_FLAGS='BbcDEeFIiJLlmOoPpQRSWw'

# Extract the display host from a command line into `_beacon_reply`, or fail.
# Non-zero means "paint nothing", which is the answer for most command lines.
#
# Parsing argv rather than asking `ssh -G` keeps this fork-free — it runs in
# preexec, on every command — and shows the alias the user typed, which is what
# they think in. The cost of that: an alias and a real hostname are
# indistinguishable here, so `build-01` may be either.
_beacon_ssh_target() {
  setopt localoptions noksharrays
  _beacon_reply=''
  # `(z)` splits into shell words, which is what surfaces control operators as
  # tokens of their own; `(Q)` strips one level of quoting so `ssh "my host"`
  # yields one word.
  local -a w
  w=( ${(Q)${(z)1}} )
  local n=${#w} i=1 tok

  # Prefixes that precede the real command: `FOO=bar ssh h`, `env ssh h`.
  while (( i <= n )); do
    tok=$w[i]
    case $tok in
      ([A-Za-z_]*=*)          (( i++ )) ;;
      (env|command|nohup|time) (( i++ )) ;;
      (*) break ;;
    esac
  done
  # The ssh must be the first command of the line. Anything else — `git push`,
  # `foo | ssh h`, a loop — is not this pane going somewhere.
  (( i <= n )) && [[ ${w[i]:t} == ssh ]] || return 1
  (( i++ ))

  local dest='' backgrounded='' chars j c
  while (( i <= n )); do
    case $w[i] in
      (';'|'|'|'||'|'&&'|'&') break ;;
      (-*)
        # Clustered booleans (`-tt`, `-4v`) and attached values (`-p2222`).
        chars=${w[i]#-}
        for (( j = 1; j <= ${#chars}; j++ )); do
          c=${chars[j]}
          # Quoted so a flag character is never itself read as a pattern.
          if [[ $_BEACON_SSH_VALUE_FLAGS == *"$c"* ]]; then
            # The value is the rest of this word when there is one, else the next.
            (( j < ${#chars} )) || (( i++ ))
            break
          fi
          [[ $c == f ]] && backgrounded=1
        done
        (( i++ ))
        ;;
      (*) dest=$w[i]; (( i++ )); break ;;
    esac
  done
  [[ -n $dest && -z $backgrounded ]] || return 1

  # A trailing remote command means ssh runs and returns — the pane is not
  # spending time elsewhere, and painting it would flicker the tab for the
  # length of one command.
  while (( i <= n )); do
    case $w[i] in
      (';'|'|'|'||'|'&&'|'&') break ;;
      (*) return 1 ;;
    esac
  done

  local h=$dest
  h=${h#ssh://}
  h=${h%%/*}
  h=${h##*@}
  if [[ $h == \[* ]]; then
    h=${${h#\[}%%\]*}
  elif [[ $h != *:*:* ]]; then
    h=${h%%:*}
  fi
  # Reduce a dotted name to its first label, but never an address literal:
  # build-01.prod.example.com is build-01, while 10.0.1.5 must stay whole.
  # The trade is that two hosts differing only by domain collapse to one label.
  [[ -n ${h//[0-9.]/} && $h != *:* ]] && h=${h%%.*}
  [[ -n $h ]] || return 1
  _beacon_reply=$h
}

_beacon_publish() {
  local name=$1 value=$2 sentinel=$3
  [[ "$value" == "${(P)sentinel}" ]] && return
  _beacon_b64 "$value"
  printf '\e]1337;SetUserVar=%s=%s\a' "$name" "$_beacon_b64_out" > /dev/tty
  : ${(P)sentinel::=$value}
}

# SSH-01: while ssh holds the prompt, this pane's identity is the host it is on,
# not the local directory it was launched from. The local shell prints no prompt
# for the whole session (it is blocked in waitpid), so preexec is the only moment
# it can say so.
_beacon_preexec() {
  # zsh supplies the three arguments only while the history mechanism is active.
  # $3 is the text actually being executed with *aliases expanded*, which is the
  # only form that sees `alias ssh='ssh -o …'` or `alias s=ssh`.
  (( $# >= 3 )) || return 0
  # One glob against the whole line keeps the word splitter off the hot path:
  # nearly every command is not an ssh.
  [[ $3 == *ssh* ]] || return 0
  _beacon_ssh_target "$3" || return 0
  _BEACON_SSH_ACTIVE=1
  # Line 1 is replaced, not decorated: the local project says nothing about what
  # a remote pane is doing. Composed here rather than in a slot of its own so
  # beacon_title keeps its one writer and its never-empty guarantee (TITLE-01).
  _beacon_publish beacon_title "🔗 $_beacon_reply" _BEACON_LAST_TITLE
  _beacon_write_session_file ssh "$_beacon_reply"
}

_beacon_precmd() {
  setopt localoptions noksharrays

  # SSH-02: precmd fires once after the foreground job returns however it ended
  # — clean exit, Ctrl-C, a dropped connection, `~.` — so this is the one place
  # the ssh identity can be retired, and no signal trap is needed.
  #
  # Invalidation is unconditional because the local sentinels describe only what
  # the *local* shell last sent. A remote snippet may have published any slot
  # since, so there is nothing here to diff against — and without the reset the
  # publishes below would all short-circuit and strand the tab on the host.
  if (( _BEACON_SSH_ACTIVE )); then
    _BEACON_SSH_ACTIVE=0
    _beacon_invalidate_sentinels
    _beacon_publish beacon_ssh_path_nl '' _BEACON_LAST_SSH_PATH_NL
    _beacon_rm_session_file ssh
  fi

  # BADGE-02: the plugin is the sole writer of `beacon_project`. The shell
  # snippet deliberately does NOT publish it from precmd — the badge text
  # follows intentional signals (overrides, SessionStart anchor) rather
  # than every `cd`. Status-bar user-vars (branch, project_full, url)
  # below are still published because the status bar IS meant to track
  # cwd — different surface, different contract.

  _beacon_branch_info
  local b="${_beacon_binfo[1]}" bstate="${_beacon_binfo[2]}" bidentity="${_beacon_binfo[4]}"
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

  # Publishing a slot costs no process: a `cd` used to spend ~570ms here, almost
  # all of it python interpreter startup paid once per slot.
  _beacon_publish beacon_branch           "$b"           _BEACON_LAST_BRANCH
  _beacon_publish beacon_branch_state     "$bstate"      _BEACON_LAST_BRANCH_STATE
  _beacon_publish beacon_branch_default   "$b_default"   _BEACON_LAST_BRANCH_DEFAULT
  _beacon_publish beacon_branch_clean     "$b_clean"     _BEACON_LAST_BRANCH_CLEAN
  _beacon_publish beacon_branch_diverged  "$b_diverged"  _BEACON_LAST_BRANCH_DIVERGED
  _beacon_publish beacon_branch_untracked "$b_untracked" _BEACON_LAST_BRANCH_UNTRACKED

  # Local cwd with $HOME substituted as ~ (STATUS-BAR-05).
  local lp="${PWD/#$HOME/~}"
  if [[ "$lp" != "$_BEACON_LAST_LOCAL_PATH" ]]; then
    _beacon_write_session_file cwd "$PWD"
    _BEACON_LAST_LOCAL_PATH="$lp"
  fi

  # The project chip is the project's *name* (STATUS-BAR-02), so it needs no
  # URL: it reads the same in a plain shell as under Claude, and outside a git
  # repo it floors on the directory rather than collapsing. That is what took
  # the per-prompt `resolve-url` (python startup plus a possible tack
  # subprocess) off this hot path entirely.
  _beacon_project_name
  local pname="$_beacon_reply"
  local chip="${pname:-${PWD:t}}"
  _beacon_publish beacon_project_name "$chip" _BEACON_LAST_PROJECT_NAME

  # Window title value (TITLE-01): the project identity when in one, else the
  # abbreviated cwd — a plain shell outside any project shows where it is
  # rather than a blank title. It floors differently from the chip on purpose:
  # a title has room for a path, a chip beside the branch does not. Local path
  # is never empty (PWD always set), so the title never goes blank.
  local title="${pname:-$lp}"
  _beacon_publish beacon_title "$title" _BEACON_LAST_TITLE

  return 0
}

_beacon_invalidate_sentinels() {
  _BEACON_LAST_PROJECT_NAME='__unset__'
  _BEACON_LAST_TITLE='__unset__'
  _BEACON_LAST_BRANCH='__unset__'
  _BEACON_LAST_BRANCH_STATE='__unset__'
  _BEACON_LAST_BRANCH_DEFAULT='__unset__'
  _BEACON_LAST_BRANCH_CLEAN='__unset__'
  _BEACON_LAST_BRANCH_DIVERGED='__unset__'
  _BEACON_LAST_BRANCH_UNTRACKED='__unset__'
  _BEACON_LAST_LOCAL_PATH='__unset__'
  _BEACON_LAST_SSH_PATH_NL='__unset__'
}

_beacon_chpwd() {
  # Force re-publish on directory change — branch may have changed even if
  # project is the same, and project may have changed entirely.
  _beacon_invalidate_sentinels
  _beacon_precmd
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd  _beacon_precmd
add-zsh-hook preexec _beacon_preexec
add-zsh-hook chpwd   _beacon_chpwd

# Publish immediately on source so a fresh shell shows the right values
# without waiting for the first prompt.
_beacon_chpwd

typeset -g _BEACON_INSTALLED=1

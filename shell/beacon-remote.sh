# beacon — remote half of the shell integration (SSH-05).
#
# Source this from a remote host's rc and the iTerm2 tab on the *local* machine
# gains that host's working directory and git branch. `beacon ssh-install <host>`
# puts it here; `beacon ssh-install --print` emits it for a hand install.
#
# It works because iTerm2 user vars are set by an escape sequence, and escape
# sequences are just bytes on the tty: written on the far side of an ssh
# connection they flow up the pty into the local iTerm2 untouched. So this file
# needs no beacon checkout, no python, no macOS, and knows nothing about iTerm2
# beyond three OSC strings.
#
# It publishes only the slots the local shell leaves to it — the remote cwd on
# line 2 of the tab label, and the status-bar chips, which the local snippet and
# the plugin already write with identical semantics (§6.4). It never emits
# SetProfile, SetColors or SetBadgeFormat: those carry the activity and mode axes,
# which are the local hooks' to own, and a remote host writing them would stomp a
# declared mode's background or overwrite a permission prompt's red tab. Line 1
# is likewise not ours — the local shell composes `🔗 <host>` from the name you
# actually typed, which is the one thing this side cannot know.
#
# Written for POSIX sh so one file serves zsh and bash. No arrays, no [[, no
# local — every name is prefixed `_bcn_` instead, since `local` is not POSIX.

# ---------------------------------------------------------------- guards

# The most important lines in the file. Without them these escapes are spliced
# into every non-interactive ssh: `scp`, `rsync`, `sftp` and `git` over ssh all
# run a remote shell and read its output as protocol. rsync hangs or corrupts.
case $- in
  *i*) ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac
[ -t 1 ] || return 0
[ -n "$TERM" ] && [ "$TERM" != dumb ] || return 0

# Writing to the tty rather than stdout, for the reason the local snippet
# documents: zsh runs chpwd/precmd inside command-substitution subshells, so
# stdout would splice escape bytes into `x=$(cd somedir; ...)`. Resolved once
# here — an open attempt is the only test that means anything on a device node.
if { : > /dev/tty; } 2>/dev/null; then
  _BCN_TTY=/dev/tty
else
  return 0
fi

# Base64 encoder, resolved once. zsh's parameter expansion can encode without a
# fork, but POSIX sh cannot, so this costs one subprocess — paid only for a slot
# whose value actually moved, which makes an unchanged prompt free.
if command -v base64 >/dev/null 2>&1; then
  _BCN_B64=base64
elif command -v openssl >/dev/null 2>&1; then
  _BCN_B64=openssl
elif command -v uuencode >/dev/null 2>&1; then
  _BCN_B64=uuencode
else
  return 0
fi

_bcn_last_path=__unset__
_bcn_last_dir=__unset__
_bcn_last_project=__unset__
_bcn_last_branch=__unset__
_bcn_last_state=__unset__
_bcn_last_default=__unset__
_bcn_last_clean=__unset__
_bcn_last_diverged=__unset__
_bcn_last_untracked=__unset__
_bcn_origin_root=
_bcn_origin_url=

# ---------------------------------------------------------------- emit

# LC_ALL=C is load-bearing, and for the reason the local encoder documents: the
# branch display carries ↑/↓, base64 needs *bytes*, and a UTF-8 locale makes the
# encoders character-oriented. `printf %s` avoids the trailing newline that would
# otherwise be encoded into every value.
_bcn_encode() {
  case $_BCN_B64 in
    base64)   printf %s "$1" | LC_ALL=C base64 | LC_ALL=C tr -d '\n' ;;
    openssl)  printf %s "$1" | LC_ALL=C openssl base64 -A ;;
    uuencode) printf %s "$1" | LC_ALL=C uuencode -m - | sed '1d;$d' | tr -d '\n' ;;
  esac
}

# Publish one user var, skipping the encode and the write when it has not moved.
# $1 slot, $2 value, $3 name of the sentinel variable holding the last value.
_bcn_publish() {
  eval "_bcn_prev=\$$3"
  [ "$2" = "$_bcn_prev" ] && return 0
  printf '\033]1337;SetUserVar=%s=%s\a' "$1" "$(_bcn_encode "$2")" > "$_BCN_TTY"
  eval "$3=\$2"
}

# ---------------------------------------------------------------- project

# Mirrors _beacon_project_root: walk up to a marker, stopping at $HOME so a
# stray package.json or dotfiles .git there isn't read as "the current project".
# Pure shell — no fork.
_bcn_project_root() {
  _bcn_root=
  _bcn_dir=$PWD
  # The marker list rides the positional parameters, and the loop reads them
  # with `for m do`, because an unquoted `$list` does not word-split in zsh —
  # it would test one path with every marker concatenated into it. Mirrors
  # _BEACON_MARKERS in shell/beacon.zsh.
  set -- .git package.json Cargo.toml pyproject.toml go.mod .hg pom.xml Gemfile
  while [ -n "$_bcn_dir" ] && [ "$_bcn_dir" != / ]; do
    [ "$_bcn_dir" = "$HOME" ] && return 1
    for _bcn_m do
      if [ -e "$_bcn_dir/$_bcn_m" ]; then
        _bcn_root=$_bcn_dir
        return 0
      fi
    done
    _bcn_dir=${_bcn_dir%/*}
  done
  return 1
}

# The project name: the origin remote's repo basename, else the root's own
# directory name — same precedence as _beacon_project_name, so a remote pane and
# a local pane in the same repo agree. The URL is memoized against the root, so
# the fork is paid once per project rather than once per prompt.
_bcn_project_name() {
  _bcn_project=
  _bcn_project_root || return 0
  if [ "$_bcn_origin_root" != "$_bcn_root" ]; then
    _bcn_origin_root=$_bcn_root
    _bcn_origin_url=$(git -C "$_bcn_root" remote get-url origin 2>/dev/null || printf '')
  fi
  if [ -n "$_bcn_origin_url" ]; then
    _bcn_project=${_bcn_origin_url%/}
    _bcn_project=${_bcn_project##*/}
    _bcn_project=${_bcn_project%.git}
  fi
  [ -n "$_bcn_project" ] || _bcn_project=${_bcn_root##*/}
}

# ---------------------------------------------------------------- branch

# One for-each-ref yields the branch, its upstream, the ahead/behind counts and
# the repo's default branch — mirroring _beacon_branch_info field for field so
# the two halves classify a branch identically. Sets _bcn_branch / _bcn_state /
# _bcn_identity.
_bcn_branch_info() {
  _bcn_branch=; _bcn_state=; _bcn_identity=
  [ -n "$_bcn_root" ] || return 0
  _bcn_name=; _bcn_upstream=; _bcn_track=; _bcn_default=

  # Tab-separated: a ref name may contain `|` but never a control character.
  _bcn_rows=$(git for-each-ref \
    --format='%(HEAD)	%(refname)	%(upstream:short)	%(upstream:track,nobracket)	%(symref:short)' \
    refs/heads/ refs/remotes/origin/HEAD 2>/dev/null)

  # `read` splits on IFS, which is the one splitting mechanism that behaves
  # identically in sh, bash and zsh — an unquoted `$rows` does not split in zsh
  # at all. The heredoc feeds the loop without a pipeline, so the assignments
  # below land in this shell rather than a subshell that exits.
  while IFS='	' read -r _bcn_f1 _bcn_f2 _bcn_f3 _bcn_f4 _bcn_f5; do
    if [ "$_bcn_f2" = refs/remotes/origin/HEAD ]; then
      _bcn_default=${_bcn_f5#origin/}
    elif [ "$_bcn_f1" = '*' ]; then
      _bcn_name=${_bcn_f2#refs/heads/}
      _bcn_upstream=$_bcn_f3
      _bcn_track=$_bcn_f4
    fi
  done <<BCN_REFS
$_bcn_rows
BCN_REFS

  # No `*` row means detached HEAD, no repo, or an unborn branch — only the last
  # has a name to show, and symbolic-ref is what tells them apart, so the extra
  # call is paid only there.
  if [ -z "$_bcn_name" ]; then
    _bcn_name=$(git symbolic-ref --short HEAD 2>/dev/null) || return 0
    [ -n "$_bcn_name" ] || return 0
  fi

  # An upstream deleted upstream reads as `gone` and carries no counts, so it
  # classifies with the local-only branches rather than as diverged.
  _bcn_state=untracked
  _bcn_ind=
  if [ -n "$_bcn_upstream" ] && [ "$_bcn_track" != gone ]; then
    if [ -z "$_bcn_track" ]; then
      _bcn_state=clean
    else
      _bcn_state=diverged
      case $_bcn_track in
        *ahead\ *) _bcn_a=${_bcn_track#*ahead }; _bcn_a=${_bcn_a%%[!0-9]*}
                   [ -n "$_bcn_a" ] && _bcn_ind="↑$_bcn_a" ;;
      esac
      case $_bcn_track in
        *behind\ *) _bcn_b=${_bcn_track#*behind }; _bcn_b=${_bcn_b%%[!0-9]*}
                    [ -n "$_bcn_b" ] && _bcn_ind="$_bcn_ind↓$_bcn_b" ;;
      esac
    fi
  fi

  # origin/HEAD names the default branch when it is set; when it isn't, fall
  # back to the conventional names so a fresh repo still classifies.
  if [ -z "$_bcn_default" ]; then
    case $_bcn_name in main|master|trunk) _bcn_default=$_bcn_name ;; esac
  fi
  _bcn_identity=feature
  [ -n "$_bcn_default" ] && [ "$_bcn_name" = "$_bcn_default" ] && _bcn_identity=default

  _bcn_branch=$_bcn_name
  [ "$_bcn_state" = diverged ] && _bcn_branch="$_bcn_ind $_bcn_name"
}

# ---------------------------------------------------------------- prompt hook

_bcn_precmd() {
  # Line 2 of the tab label: a leading newline and a two-space indent when set,
  # so the line self-collapses when empty — the same contract beacon_task_nl has.
  case $PWD in
    "$HOME")  _bcn_disp='~' ;;
    "$HOME"/*) _bcn_disp="~${PWD#"$HOME"}" ;;
    *)        _bcn_disp=$PWD ;;
  esac
  _bcn_publish beacon_ssh_path_nl "
  $_bcn_disp" _bcn_last_path
  # The absolute path, for `↗ code`'s vscode-remote:// URI — a `~` means nothing
  # to VS Code on the local side (SSH-08).
  _bcn_publish beacon_ssh_dir "$PWD" _bcn_last_dir

  _bcn_project_name
  _bcn_branch_info

  # Exactly one of the four slots is non-empty, so the profile's four
  # fixed-color branch components collapse to a single visible chip.
  _bcn_d=; _bcn_c=; _bcn_v=; _bcn_u=
  if [ "$_bcn_identity" = default ]; then
    _bcn_d=$_bcn_branch
  else
    case $_bcn_state in
      clean)     _bcn_c=$_bcn_branch ;;
      diverged)  _bcn_v=$_bcn_branch ;;
      untracked) _bcn_u=$_bcn_branch ;;
    esac
  fi

  # The chip floors on the directory name where the title floors on the path:
  # a chip beside the branch has no room for a path.
  _bcn_publish beacon_project_name "${_bcn_project:-${PWD##*/}}" _bcn_last_project
  _bcn_publish beacon_branch           "$_bcn_branch" _bcn_last_branch
  _bcn_publish beacon_branch_state     "$_bcn_state"  _bcn_last_state
  _bcn_publish beacon_branch_default   "$_bcn_d"      _bcn_last_default
  _bcn_publish beacon_branch_clean     "$_bcn_c"      _bcn_last_clean
  _bcn_publish beacon_branch_diverged  "$_bcn_v"      _bcn_last_diverged
  _bcn_publish beacon_branch_untracked "$_bcn_u"      _bcn_last_untracked
}

# Both branches are ordinary command words, so this file still *parses* under
# any shell — `precmd_functions+=(…)` would be a syntax error in sh even inside
# a branch sh never runs, and add-zsh-hook is the same registration the local
# snippet uses. A string assignment to precmd_functions would be worse than a
# syntax error: it is an array in zsh, so it would become one element named
# "existing _bcn_precmd" and never be called.
if [ -n "$ZSH_VERSION" ]; then
  autoload -Uz add-zsh-hook
  add-zsh-hook precmd _bcn_precmd
elif [ -n "$BASH_VERSION" ]; then
  case ";$PROMPT_COMMAND;" in
    *";_bcn_precmd;"*) ;;
    *) PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND;}_bcn_precmd" ;;
  esac
fi

# Paint before the first prompt rather than waiting for the second.
_bcn_precmd

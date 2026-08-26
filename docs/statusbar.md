# Status-bar buttons

The iTerm2 status bar carries two action buttons — `↖ web` at the left edge and
`↗ code` at the right — each paired with the data it acts on. This page is the
reference for pointing them somewhere else; for what the strip looks like and
what the chips between them mean, see [In iTerm2](/iterm).

Each button's text and what it runs come from `~/.config/beacon/config.json` — or `$XDG_CONFIG_HOME/beacon/config.json` when you have that variable set, which is the file every beacon command reads.

These are the defaults, so a config that says nothing behaves exactly like this:

```json
{
  "statusbar": {
    "buttons": {
      "web":  { "label": "↖ web",  "cmd": "" },
      "code": { "label": "↗ code", "cmd": "code" }
    }
  }
}
```

Set only what you're changing — a missing or blank field means the default.

**`cmd` applies on the next click.** Nothing to re-run. It's resolved on your `PATH` and then, failing that, by asking your login shell, so a git alias or a script both work (an action button doesn't inherit your interactive `PATH`, so `/opt/homebrew/bin` and friends are invisible to it). If neither can find it, the button says so and names the key to fix rather than quietly opening something else.

Both buttons hand your command the pane's directory, but not the same way:

| Button | How the directory arrives |
|:---|:---|
| `↗ code` | **appended as the last argument** — `"code -n"` runs `code -n /path/to/repo` |
| `↖ web` | as the **working directory**, with no argument added — which is what lets `git web` read your `origin` remote |

## Placing values yourself

When the end of the command isn't where you want the path, put it where you want it:

```json
{ "statusbar": { "buttons": { "code": {
      "cmd": "code -n {dir} --goto {dir}/README.md" } } } }
```

| Placeholder | Expands to | Outside a repo |
|:---|:---|:---|
| `{dir}` | the pane's directory | always available |
| `{project}` | the project's name | empty |
| `{branch}` | the current branch | empty |

- **`{dir}` turns off the automatic append** for `↗ code`, so the path lands only where you put it. `{project}` and `{branch}` don't — they say nothing about the path, so it's still appended.
- **A value never splits into extra arguments.** A directory called `My Repo` stays one argument.
- **An argument that expands to nothing disappears** rather than becoming an empty string, so `"ed {branch}"` outside a repo is just `ed`.
- **A misspelled placeholder is an error** that names the real ones. Want a literal brace? Double it: `{{`. A bare `{}` isn't a placeholder, so `find -exec … {} \;` is safe.

There's no shell involved: the command is split into a program and arguments and run directly, so `$(…)`, pipes, and redirection aren't available. If you need those, point the button at a script on your `$PATH` — it resolves the same way and gets the directory the same way.

**`label` applies on a re-render**, because iTerm2 stores a button's title in the profile rather than reading it live:

```bash
beacon refresh-iterm-profiles
```

That rewrites the profiles only — no reinstall of the wrapper, completions, or shell integration — and iTerm2 picks it up immediately, on panes that are already open.

You never need it on a fresh install: `beacon install` writes the profiles as one of its steps. It's a re-apply path, and these are the reasons to reach for it:

| Reason | Symptom |
|:---|:---|
| you edited a `label` | the button still shows the old title |
| your `python3` moved (a Homebrew upgrade, say) | the buttons stop doing anything — the interpreter is baked in absolute, because an action shell has no interactive `PATH` |
| you edited the beacon profile in iTerm2's GUI | whatever you changed, back to beacon's version |
| you changed the colors on your `Default` profile | beacon's panes keep the old scheme — the parent's colors are copied in when the profile loads, not read live |

After a **plugin upgrade**, use `/beacon:install-beacon` instead. The profiles embed the plugin's own paths, so re-rendering through a wrapper that still points at the old version would bake that version's paths back in.

## What `↖ web` opens

Left alone (`cmd` blank), it opens whatever beacon resolves for the session: the PR/MR/issue when there is one, else the branch or repo page. Resolution happens when you click, against that pane's directory — so the button is right even in a pane beacon isn't tracking, like a shell you're just poking around in, and there's no cached URL for it to get wrong.

Set a `cmd` and you get the repo's front page instead, or wherever else you point it:

```json
{ "statusbar": { "buttons": { "web": { "cmd": "git web" } } } }
```

`git web` isn't built into git — it's an alias you add to your own `~/.gitconfig`. This one is [line 48 of `chris-peterson/gitconfig`](https://github.com/chris-peterson/gitconfig/blob/main/.gitconfig#L48):

```gitconfig
[alias]
	web = !"git rev-parse --is-inside-work-tree >/dev/null && open \"https://$(git remote get-url origin | sed 's/git@//' | sed 's/\\.git$//' | sed 's/:/\\//' )\""
```

It builds the URL from your `origin` remote, so SSH remotes work on GitHub and GitLab alike, and it does nothing outside a work tree. It opens with macOS `open` — on Linux, swap that for `xdg-open`.

## What `↗ code` opens

The pane's working directory, in `code`. Add flags, or name a different editor entirely — whatever you put here gets the directory appended:

```json
{ "statusbar": { "buttons": { "code": { "cmd": "code -n" } } } }
```

The default passes no flags of its own, just the directory. Check any flag you add against your editor's own `--help`: VS Code hands an option it doesn't recognize to Electron/Chromium, and on a cold start that makes it drop the directory and open a Welcome window instead. There is no CLI flag for a maximized window — that's the `window.newWindowDimensions` setting in VS Code itself.

## On a pane that's ssh'd elsewhere

Both buttons act on the pane's working directory — which, during an ssh session, is the one you were in *before* you typed `ssh`. Acting on it gives a confident wrong answer, so neither does:

- **`↖ web`** tells you which host the pane is on, and stops there.
- **`↗ code`** opens the *remote* directory in VS Code over Remote-SSH (`vscode-remote://ssh-remote+<host><path>`). It needs two things: an editor with a remote-URI scheme — `code`, `codium`, `cursor`, `windsurf` — and `beacon ssh-install <host>` on the server, which is what reports the path. Missing either, it says so rather than opening something else.


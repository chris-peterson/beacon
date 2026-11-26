# What's new in 3.0

beacon 3.0 moves what it shows about a session out of iTerm2 and into Claude Code itself. Through 2.x, the session's lines lived in Claude Code's status line row and an iTerm2 status bar, and a declared mode repainted the whole pane. In 3.0 both live in one panel above the prompt, which Claude Code draws in any terminal. iTerm2 keeps the tab: its color, its two-line label, and the mode's glyph.

Coming from 2.x? [Migrating from 2.x](#migrating-from-2x) lists what to do, which for most installs is running `/beacon:install-beacon` once.

## The status panel

One panel sits above the prompt in every session, with nothing to turn on. Its top row names the session's project, its branch (colored by how it sits against its upstream, and linked to its page when it has one), and its task. Under that are the lines the status line used to carry: what the session shipped, and the change requests and issues it's working. Two buttons at the end of the top row open the project page and the session's directory in your editor; `w` and `c` press them once the panel has focus.

It replaces both the status line row and the iTerm2 status bar, and it works the same in Ghostty, WezTerm, VS Code's terminal, or anything else that runs Claude Code. See [the status panel](/statusline).

## Modes show in the panel

A mode you declare (`pause`, `release`, `done`) now opens the panel with a bar in the mode's own hue, carrying its glyph, its name, and your note. The mode's name also joins the labels at the right of Claude Code's footer, so it still shows with the panel collapsed. Your pane keeps its own background in every mode, and the bar's text meets WCAG AA contrast on every hue; the hues and their ratios are on [the palette](/palette).

**`pause`**: you've stepped away. Your next prompt lifts it.

![A paused session's panel: the purple bar reading "paused · waiting on design review before the toggle lands" with "type to resume" at its right, above what the session delivered and the change request it has open.](images/statusline-paused.png)

**`release`**: a release is underway. It stays until you leave it.

![A releasing session's panel: the navy bar reading "releasing · cutting v3.1.0: waiting on the canary", above a merged change request and the open one for the changelog.](images/statusline-release.png)

**`done`**: the session is finished and ready to hand off. Its bar is the dimmest, so a finished session reads as lights out.

![A finished session's panel: the near-black bar reading "done · handed off to on-call", above what the session merged and released.](images/statusline-done.png)

**`retro`**: writing up what happened. A retro runs long, so it has no bar: its note takes the panel's first line, led by its glyph, and the glyph also leads the top row, as it leads the tab.

![A retro session's panel: the purple line "writing up the dark mode rollout" led by a clipboard glyph, above the release the session shipped.](images/statusline-retro.png)

## The tab stack: every session's status panel, on top

The dashboard's **tab stack** button (Chrome and Edge) opens a small window that stays on top of everything else. It holds every session the dashboard shows, in the same order, each drawn the way Claude Code draws that session's status panel above its prompt: the mode's bar in its color, the project, branch, and task with `[ ↖ github ]` and `[ code ↗ ]`, and the change requests and issues underneath. Through 2.x this window was the pop-out, and it started with only the sessions waiting on you.

Both list the sessions with no headings, in **status** order: waiting on you, then working, then idle, then paused and finished sessions below a rule, on a darker ground. The sort switch in the top line shows which order is in force; click `recency` for newest first whatever the state, and the browser remembers your choice. Each tile adds the session's activity dot, its age, and `[ go ]` to raise its window. Click a tile's top row to show its latest turn, with its links as clickable labels rather than addresses. A paused or finished session gets a thin bar and dimmer text, so it recedes behind the ones still working.

![The tab stack: one column of status panels, the waiting sessions first, each with its project, branch, task, and buttons, and a purple bar over each paused session.](images/demo-popout.png ':size=480')

## Pick a session from the keyboard

Press **⌃G** at a zsh prompt and [`beacon pick`](/cli?id=beacon-pick) takes over the terminal with every session, two lines each, in the status order above: the project, branch, and task, then what it waits on or its latest turn. Type to narrow the list by project, branch, task, or note.

| Key | Does |
|:---|:---|
| ↑ ↓ | move |
| ↵ | raise the session's window |
| ⌥W / ⌥C | open its project page / its directory in your editor |
| Tab | flip between status and recency order |
| Esc | hand the terminal back to the shell |

It reads session state directly, so it works with `beacon serve` stopped, and the key binding comes with the shell integration, so it works in any terminal running zsh. `beacon config pick-key` changes the key (`^[p` for Option-P, `off` to bind none, `reset` for ⌃G); `exec zsh` picks up the change. For a key that works from any app, give an iTerm2 hotkey window's profile `beacon pick` as its text to send at start. Inside a Claude Code session, `/beacon switch` lists the other sessions in the same order in the panel.

## Also in 3.0

- **Colors meet WCAG AA.** Every color beacon draws in the terminal reaches 4.5:1 contrast on Dracula's background.
- **Turn off what beacon does with a sibling's announcement.** `git config --global beacon.subscribe.anchor false`, or `beacon.subscribe.tack false`, or one event at a time. See [turning a reaction off](/?id=turning-a-reaction-off).
- **Every session shows, however beacon was loaded.** State now lives in one place, `~/.local/state/beacon`, so a session loading beacon from a local checkout and one using the installed plugin both appear in the dashboard and `beacon wip`. Through 2.x each kept its own directory and the sessions view showed only one set.
- **`beacon config` offers the iTerm2 restart itself** when a tab or pane setting needs one, instead of telling you to run another command.

## Migrating from 2.x

**Update Claude Code to 2.1.287 or later**, which the panel needs. Then, after [updating beacon](/?id=upgrade), run this once in a Claude Code session:

```
/beacon:install-beacon
```

Run it as the slash command rather than `beacon install` from a shell: the shell's `beacon` still points at the version you're leaving until this rewrites it. That covers most installs. The first run copies your 2.x session state into its new home, `~/.local/state/beacon`. It also removes the `statusLine` 2.x wrote into `~/.claude/settings.json`, writes the new `beacon` iTerm2 profile, and removes the old ones. Open panes move to the new profile on their next update, with nothing to restart.

Check the rest against your setup:

| If you… | Then |
|:---|:---|
| sync `~/.claude/settings.json` from somewhere else | remove the `statusLine` that runs `beacon statusline` there too, or the row comes back and repeats the panel's lines. `beacon doctor` flags one that's still set. |
| set `statusbar.buttons.<name>.cmd` in `~/.config/beacon/config.json` | move it to `buttons.<name>.cmd`. beacon no longer reads the old key. Button labels are no longer configurable: the panel labels each button by what it opens. |
| named the `beacon-dev` profile in a script, an AppleScript, or a key binding | use `beacon`. The profile keeps its GUID, so iTerm2's default-profile setting and existing windows follow it on their own. |
| used `beacon config status-panel` or `/beacon on` / `off` | drop them: the panel is always on, so there is nothing to switch. |
| run your own dashboard against `beacon serve` | `/mode-bg/<mode>` is gone, since mode cards take the bar's hue. The tab stack's new `/panel/<hash>` and `/open` routes fall under the same `focus_origins` allowlist as the others. |

The pause, release, and done pane backgrounds and their watermarks are gone with nothing to replace them: the panel's bar and the tab's glyph carry the mode.

The full list of changes is in the [changelog](https://github.com/chris-peterson/beacon/blob/main/CHANGELOG.md).

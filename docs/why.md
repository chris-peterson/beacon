# Why beacon?

Running several Claude Code sessions at once costs you more than attention. You can only look at one, so the rest are working, or finished, or stuck on a permission prompt you haven't seen. You lose track of which branch and which deliverable each one is on. Coming back after an hour, you can't tell which window was the one that mattered. And the sessions accumulate — most never get closed, so whatever view you have of them fills up with work that ended days ago.

Plenty of tools address some of that. Most do it by asking you to adopt something: a different terminal, a multiplexer, or an app that starts your sessions for you. beacon connects what you already run instead — it reads the sessions you started yourself, in the terminal you already use, and reports on them.

Below is who else is in this space and what each one asks for in return.

> [!NOTE]
> Landscape as of **August 2026**. Every project named here was checked for liveness when this page was written; the category moves fast enough that Crystal, the reference orchestrator until February 2026, is now [Nimbalyst](https://github.com/Nimbalyst/nimbalyst).

## What each one asks for

| | Wants | Gives you | Costs you |
|:---|:---|:---|:---|
| **Agent-native terminals** | Your terminal emulator | A fleet UI built for agents | Your current terminal |
| **Multiplexer plugins** | tmux or Zellij | Agent state on its chrome | Running under that multiplexer |
| **Worktree orchestrators** | To start your sessions | Isolation, diffs, lifecycle | Sessions you no longer launch yourself |
| **Claude Code's `claude agents`** | Nothing — it's built in | A view of what *it* dispatched | Only covers background sessions |
| **iTerm2 tab-status tools** | An iTerm2 helper process | Attention state on the tab | A restart or a resident daemon |
| **beacon** | Nothing new | Both views, no daemon | Claude Code + iTerm2 for the rich path |

## Agent-native terminals

[agterm](https://github.com/umputun/agterm) is the closest competitor: a native macOS terminal built on Ghostty's engine, with a workspaces → sessions → panes sidebar, per-session status glyphs, a searchable attention palette sorted blocked-first, auto-follow of the oldest blocked session, and a grid dashboard of live panes. There are ports — [agterm-linux](https://github.com/melonamin/agterm-linux) (GTK4) and [agwinterm](https://github.com/yeroo/agwinterm) (Windows, which can be registered as the default terminal).

It reads Claude Code hooks the way beacon does, and it drives status through `agtermctl`, a CLI over a local socket. Its hook support is *wider* than beacon's: Claude Code, Codex, Pi, and OpenCode, against beacon's Claude Code only.

What it asks for is the terminal. Its fleet view is its own window, so you get it by switching emulators. beacon exists because that trade wasn't worth making with years of iTerm2 muscle memory behind it. Without that attachment, agterm is a serious option, and its own README says plainly that it makes "no attempt to invent a new way of working with agents."

## Multiplexer plugins

[tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator) paints agent state onto tmux's own chrome — pane borders, window-title colors, per-agent status-bar icons — from the same `UserPromptSubmit` / `PermissionRequest` / `Stop` hooks. [zellaude](https://github.com/ishefi/zellaude) does the Zellij equivalent, replacing the native tab bar with a Claude-aware one. Several siblings exist for both.

So the *mechanism* beacon uses is not unusual. What differs is where the state lives and how far it reaches:

- Both require you to run under that multiplexer. beacon's iTerm2 painting works in a plain pane, and its fleet view needs no multiplexer at all.
- tmux-agent-indicator's cross-session view is a row of status-bar dots — no listing command, no dashboard, no click-to-focus. Its scripts carry no notion of a project, a branch, a task, or an issue; they answer "does something need me?" and stop there.
- zellaude holds every session in the plugin's own memory, so nothing outside that Zellij process can read the fleet. Its open cross-session PR proposes adding state files, which is the design beacon starts from.

If you already live in tmux or Zellij, these are less work than beacon and cover the attention question well.

## Worktree orchestrators

[Nimbalyst](https://github.com/Nimbalyst/nimbalyst) (formerly Crystal) and [claude-squad](https://github.com/smtg-ai/claude-squad) give each agent its own git worktree and manage the sessions for you. Both let you review changes before applying them; Nimbalyst adds per-session diffs, build and test output, and a waiting-versus-running board.

This is a different job, and where it overlaps beacon it usually wins. They know the truth about a session because they spawned its process; beacon infers state from hooks and can drift if one is missed. They isolate working trees; beacon does not. They start and stop agents; beacon does neither.

What they don't do is drive the terminal you already have. Their sessions live inside their own app, in an embedded terminal. beacon assumes the opposite — that you opened the panes yourself and want them labeled where they already are.

Reach for an orchestrator when you want agents running unattended in parallel on isolated branches. Reach for beacon when you're driving the sessions and need to know which one wants you.

## The built-in view: `claude agents`

Worth knowing before you install anything: Claude Code ships a fleet view. `claude agents` lists the sessions it dispatched into the background, with per-row status — Working, Needs input, Done, Needs attention — plus `--json`, attach, and worktree-backed jobs.

An interactive session you started by typing `claude` in a pane doesn't get a row. Those are the sessions beacon is about, so the two don't overlap much — but if all your parallel work is backgrounded, the built-in view may be all you need.

The gap is easy to see for yourself. Opening it while driving seven interactive sessions reported `2 awaiting input · 0 working · 2 completed` — and both rows awaiting input were 33 days old. None of the live work was in it, because none of it was dispatched; what remained was what had been dispatched and never cleaned up. That's the scope difference and [the graveyard problem](#everything-in-this-category-becomes-a-graveyard) in one screen.

## iTerm2 tab-status tools

beacon is not the only thing painting iTerm2 tabs from Claude Code hooks. [claude-code-iterm2-tab-status](https://github.com/JasperSui/claude-code-iterm2-tab-status) puts a ⚡ / 💤 / 🔴 prefix on the tab title, and ships as a Claude Code plugin like beacon does. [iterm2-ai-tab-color](https://github.com/hanzhangzzz/iterm2-ai-tab-color) colors tabs by how *long* a session has been waiting — green on finishing, yellow past ten minutes, red past twenty — and supports Codex alongside Claude Code.

Both are smaller than beacon, and if attention state is all you want, that's the reason to prefer them. Three things separate them:

- **How much they carry.** Both surface one axis. beacon's tab carries the project over its task, colored by state, with mode cycles for pause / release / retro / done / handoff, plus a status bar, the window title, and a [status line](/iterm?id=the-status-line) listing the session's open PRs and issues.
- **What has to be running.** They need an iTerm2 Python AutoLaunch script (and an iTerm2 restart) or a resident LaunchAgent holding a websocket. beacon paints with escape sequences and a hot-reloaded profile, so neither is required. beacon's own `serve` is a daemon, but it's opt-in and only powers the dashboard.
- **Where it stops working.** They're macOS and iTerm2, entirely. beacon's fleet view is the primary product and runs anywhere Python does.

## What beacon claims

Two things.

**One: the state is on disk, so the fleet outlives any one UI.** Every session writes to `<DATA_DIR>/state/<hash>.<field>`. That's why `beacon wip`, `beacon watch`, the browser dashboard, and anything you write against `/wip.json` read the same records, from outside any running process, in any terminal, on any OS. Every alternative here keeps its fleet inside something: a plugin's memory, a window, an Electron app's database, a status-bar format string.

**Two: it paints a terminal it doesn't own.** The iTerm2 adapter drives that terminal's real chrome — tab color, two-line tab label, status bar, window title — from agent hooks, without being the terminal or requiring a multiplexer. It's an adapter behind a stateless CLI, so a second terminal is a new adapter rather than a rewrite. Windows Terminal is next, then WezTerm.

How much of the iTerm2 surface each one can carry differs. Windows Terminal covers two of them in-band: the **tab label**, because it honors the OSC 0 title sequence a shell writes for itself, and the **tab color**, via `DECAC` against palette indices 263/264 since v1.15. Three limits shape what that adapter can promise — the label is per-*tab*, so panes in a split can't be labeled side by side the way iTerm2's per-session name allows; the tab title takes no SGR, so the bold project accent flattens; and the runtime color resets on a settings edit or a keyboard-layout change, so it wants re-emitting per prompt.

WezTerm reaches further into the rest. `$WEZTERM_PANE` gives a pane the stable identity `$ITERM_SESSION_ID` gives an iTerm2 session, pane-directed `wezterm cli` commands take `--pane-id`, and it reads the same OSC 1337 `SetUserVar` channel beacon's status bar already uses — user vars scoped to a pane rather than a process, which is iTerm2's semantics. kitty is comparable but needs `allow_remote_control` switched on in `kitty.conf` first, so its adapter starts with a config edit rather than an escape sequence. Ghostty parses the iTerm2 OSC 1337 extensions without implementing them, so there's nothing to drive there yet.

## Where beacon is weaker

### Everything in this category becomes a graveyard

Session managers demo well and age badly, and beacon is not exempt. The demo has five sessions and every one of them means something. Six weeks later you have sixty, because sessions rarely get *terminated* — you finish the work, close the laptop, and the record stays. Whatever view you built to scan live work turns into a list of things that ended, with the signal you installed it for buried in it.

Nothing here has solved that, including the built-in view — [`claude agents`](#the-built-in-view-claude-agents) opened mid-flight listed four rows, two of them 33 days old, while seven live sessions went unmentioned. It's structural: an agent session has a clear beginning and no clear end, so there's no event to hang cleanup on. What beacon does about it is partial, and worth knowing precisely:

- The fleet view is **time-windowed by default** — `wip`, `watch`, and the dashboard show the last 24 hours, so an ordinary stale session falls out of sight without being deleted (`--since` widens the window, `--all` drops it).
- `beacon prune [--since 30d]` deletes state for long-idle panes, and `beacon forget <hash>` deletes one. The dashboard's `×` does the same for a card.
- A session in a **mode** — `pause`, `release`, `retro`, `done`, `handoff` — is exempt from that window, because a parked session is one you meant to come back to. The cost is that it never ages out on its own: the `done` you send to mark work finished is what keeps the card on the board until you prune it.

So the default is *hiding* rather than *ending*, the sessions you explicitly marked linger longest, and the cleanup is manual. If you want a tool that knows when work is over, an orchestrator that owns the session lifecycle is the answer.

### The rest

Being supplemental means inheriting the limits of what you plug into:

- **Claude Code only.** agterm, tmux-agent-indicator, claude-squad, and iterm2-ai-tab-color all handle Codex and others.
- **The rich painting is macOS + iTerm2.** Everywhere else you get the fleet view and nothing on the pane, which is why the dashboard is the primary surface rather than a bonus.
- **Hooks can be missed.** beacon reports what it was told. An orchestrator that owns the process never has to guess — tmux-agent-indicator ships process-detection as a fallback for exactly this reason.
- **No isolation, no lifecycle.** beacon will not give an agent its own worktree, and it will not start or stop anything.

If those matter more than keeping your terminal, one of the tools above is the better fit.

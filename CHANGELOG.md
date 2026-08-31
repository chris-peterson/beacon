# Changelog

## Unreleased

### `serve` refuses an opaque origin

2.9.0's origin gate read a literal `Origin: null` as the same fact as a missing header and served it. A browser sends `null` for every *opaque* origin — a sandboxed iframe, a `data:` URL, a cross-origin redirect — and any page can create one on demand, so a page you had open could still read the sessions feed, latest turn text included, and reach `focus` and `forget` through the preflight. A present `Origin: null` is now foreign, and rejected on every route.

A request that sends no `Origin` at all is unchanged: that is `curl` or a same-origin fetch, and a browser cannot suppress the header on a cross-origin request. The bundled dashboard at `http://127.0.0.1:8787/` and an allowlisted one are unaffected.

## 2.9.0

### `serve` answers only origins you allow

The sessions feed carries each session's most recent turn — your prompts and Claude's replies — and `serve`'s read routes answered any origin while ignoring the `Host` header. Any page open in your browser could read it, and the reads were open to DNS rebinding. Every route now requires a loopback `Host` and an allowed `Origin`.

The bundled dashboard at `http://127.0.0.1:8787/` is same-origin and unaffected, as is `https://chris-peterson.github.io`. A dashboard you host anywhere else needs its origin in `~/.config/beacon/config.json`, which now governs the reads as well as the focus and dismiss buttons:

```json
{ "focus_origins": ["https://your-dashboard.example"] }
```

### State files are owner-only, and they expire

Everything beacon writes under its data dir is created `0700` / `0600` rather than at your umask. On a `0755` home the turn text was readable by every other account on the machine. Files an earlier version wrote are corrected as they are rewritten.

`prune`'s 30-day sweep now also runs on its own at session start, at most once a day. Reachable only as a verb, it went unrun, so state accumulated for every pane ever opened.

### Fixes

- A recorded iTerm2 pane handle is validated before it reaches AppleScript or a `doctor` report.
- `wip --json` no longer reports a session focusable when its handle is one `focus` would refuse to act on.
- `configure --write`'s helper log gets an unguessable name instead of a fixed path in the temp dir.
- Compressed `export` dumps and state writes are no longer newline-translated on Windows.

## 2.8.0

### An uncolored tab paints itself again

The tab color is a per-session OSC override, and things other than beacon clear
it: any `SetProfile=` wipes it, including one a nested `claude` emits on its way
out — that OSC reaches the pane it was started in, while its state goes to a
bucket of its own. beacon painted the tab only when the activity moved, compared
against the last-rendered snapshot, so a wipe it hadn't caused was invisible to
it and the tab stayed uncolored for the rest of the session. A pane sitting at
`working` through a long run could go the whole run unpainted.

The color is now re-emitted on every render, the way the status-bar chips already
were and for the same reason: beacon can't tell whether the override it wrote
last is still there, so it writes it again. A lost tab color comes back on the
next hook.

### A release phase marks itself

Entering `release` mode meant remembering to run `beacon release` in the middle
of cutting one. beacon now watches for the release skill being invoked — the
agent calling `anchor:release`, or you typing `/anchor:release` or `/release` —
and enters the mode itself, so the 🚀 reaches the tab whether or not anyone
thought about the tab.

Nothing is asked of anchor, which has no idea beacon is listening, and nothing
changes about how you leave the mode. A note you set by declaring the phase
yourself survives the skill firing afterward.

## 2.7.2

### A nested `claude` no longer takes over the pane it was started in

Per-session state keys on the iTerm2 pane, which is what lets a pane keep one
identity across a `/clear` or a compaction. A `claude` started from *inside* a
live session — by a hook, a script, a terminal integration — inherits that pane
id, so its own SessionStart landed in the running session's state: wiping the
label, the turn history and the accumulated deliverables, and repinning the
session's project onto wherever the nested one happened to launch. A session
working in a repo would go on reporting a scratch directory as its project for
the rest of its life, on the tab, the window title and the dashboard.

A SessionStart that finds the pane already held by a different session now takes
a bucket of its own, and its later hooks follow it there. The host keeps its
anchor, its signals, its focus handle and its pane files.

`beacon set project` also reaches the sessions view now. The row read the
anchored project ahead of the pinned one, so pinning a label repaired the tab
and left the dashboard disagreeing with it.

### Every command, on the docs site, recorded from the binary

The docs sampled the handful of commands you type most and left the rest to
`beacon --help`. The site now carries a [CLI reference](https://chris-peterson.github.io/beacon/#/cli):
every command, its flags, what each one is for, and the notes and worked examples
help output has no room for — grouped by what they do, from session state through
the sessions view to the install steps.

It is generated, not written. shipyard runs `beacon --help` and each command's own
help, records the grammar into `spec/cli.yml`, and renders the page from that, so
the page says what the binary you have installed accepts. A command missing from
the page now fails the build instead of going unnoticed, which is how the handful
became the sample in the first place. The `cli` mark on the docs home page and on
the marketplace card is the way there.

## 2.7.1

### A session keeps its project when the agent works in a scratch directory

Claude Code re-fires SessionStart when it compacts a session's context, and the cwd it passes is its own live working directory rather than the one the session started in. beacon read that as a new session: it re-pinned the navigational anchor onto wherever the agent happened to be, and cleared the pinned label, the accumulated deliverables, and the status-line window along with it. A long session that compacted while working in a temp directory came back named after that directory. Compaction and forks now keep the anchor the session already has and refresh only the chips, the way the end of a turn does.

Outside a recognized project the project chain also named the bare directory, so a session in macOS's `$TMPDIR` read as a project called `T` on the tab while the sessions view showed the full path. The last chained tier now names a *project root* only, and where there is none the abbreviated path answers (PROV-06) — the same value the anchor already recorded, so the two surfaces agree.

## 2.7.0

### Tab labels come back on a machine with two iTerm2 builds

An Xcode build of iTerm2 installs as `iTerm2.app` where the release installs as `iTerm.app`, and beacon addressed iTerm2 by name — so on a machine carrying both, every Apple Events call went to the dev build and found no session there. Tab labels, window titles, and clicking a session in the dashboard to raise its window all stopped, with nothing on screen to say why. beacon now addresses iTerm2 by its bundle id, which resolves to the installed app.

### A new tab gets its name in a third of a second

Naming a new tab waited up to two seconds for a marker that a plain shell never receives, so a fresh tab read `Default` for two and a half seconds before its project appeared. It now names itself immediately — measured at 0.35s. A pane that Claude takes over later still gets the managed label; the wait was what made the two writers race in the first place.

### `beacon doctor` checks the install and reports what has been failing

A display failure must never crash a Claude Code hook, so beacon swallows every external command it runs. That is what let a broken tab label go a whole session unnoticed. Failures are now recorded to `<data-dir>/logs/errors.log`, and `beacon doctor` reads them back grouped by operation with advice for each, alongside live checks: whether every context resolves the same data directory, whether the state directory is writable, whether the `PATH` wrapper and Claude Code status line are wired, and — on iTerm2 — whether the dynamic profiles are present and this session's pane is still reachable. It exits non-zero when something is wrong, so it can gate a health check.

`beacon doctor --since 30d` widens the error window; `--json` emits the checks and entries for a script.

### `beacon --version` says when it is a working tree

A checkout and an installed plugin report the same version, so there was no way to tell which copy was about to run. A working tree now reports `2.7.0-dev+<ref>`, an installed one reports `2.7.0`.

### Also

- The error log is created empty at startup, so the path `doctor` prints is one you can open and tail before anything has gone wrong.
- New spec requirements: `DIAG-01..08` (the error log and `doctor`), `CMD-29` (`doctor`), `CMD-30` (`--version`), `NFR-12` (a swallowed failure is recorded rather than silent).

## 2.6.1

### The fleet view is the sessions view

"Fleet" was a metaphor you had to translate. The cross-session read behind `wip` / `watch` / `serve` is the **sessions view** now, and `dashboard` keeps the narrower meaning: the browser page `serve` hosts at `/`. Both words were doing both jobs before.

The dashboard masthead and page title read `beacon · sessions`, and the docs section is "Sessions view (any terminal)" — a bookmark to the old anchor needs updating. Nothing you type changes; no command, flag, or state field moved.

### Also

- The icon's three signal arcs are one purple at three opacities, the color of the group beacon and tack belong to. The green core and its pulse are unchanged.
- `STATUS.md` lists CLI-15 as live (`set-name`), not retired. Coverage is unchanged at 168 IDs, all covered.

## 2.6.0

### A parked session's tab stops reading as blocked

A paused or done session sits at an idle prompt by definition, so the idle timer always fired and red — the color that means Claude needs you — was the resting state of every parked tab. A halted mode now records nothing from an idle prompt. A permission prompt still paints red in every mode.

### A pause note reaches the tab strip

While a session is paused or done, its note takes line 2 of the tab label in place of the task, which a halted session has no live work to fill. The note's other home is the Claude Code status line, which exists only in the focused pane — so a note saying why a session is parked reached only the pane you were already looking at.

### `beacon layout` applies the recommended iTerm2 layout

The app-wide settings beacon recommends — tab position and size, status-bar position — were reachable only as `beacon-iterm configure`, a second executable nothing pointed at. They are `beacon layout` now, and `install` applies them instead of only listing them.

```
beacon layout            # audit; writes nothing
beacon layout --write    # apply (quits + relaunches iTerm2)
```

Applying used to revert silently: a running iTerm2 was detected with `pgrep -x iTerm2`, which never matches it, so the write landed in a live iTerm2 that restored the old values on quit. The audit now says when iTerm2 is running, since it reads a plist the running app overwrites.

The recommended tab-label font size is 22.

### A git worktree is the same project

Working in a linked worktree captioned the tab with that directory's name — an opaque id, where a tool cuts the tree. Sibling checkouts share a git dir, which is what now tells a second checkout from leaving the repository.

### Where a session is now reads on line 1

The tab shows `beacon @ ai-sdlc` over the task, rather than opening line 2 with a separator whose antecedent sat on the line above. The marker went only to the badge, which is opt-in, so by default it had no surface.

### Also

- A `url` override written before 2.5.0 no longer outranks the URL chain. `beacon set url` went away with 2.5.0, so nothing was left that could clear one.
- Tab completion offers `--clear-screen` on `pause`, `--timing` on `wip`, and `--print` on `completions`.
- The CLI cheat sheet in `docs/README.md` documented `beacon status waiting`, `beacon clear status`, and `beacon icon`, all of which 2.5.0 removed and all of which exit non-zero.
- `README.md` gains sequence diagrams for what beacon computes on each hook and prompt, and where the answers are cached.

## 2.5.0

### `status` splits into `mode` and `activity`

A session's state is now two independent fields rather than one. **`activity`** — idle, working, waiting — is what the hooks observe. **`mode`** — pause, release, retro, done — is what you or a skill declare.

They were one `status` field, merged by priority, and the declared value won. A session in `release` or `retro` could not report that it was blocked on you — entering a mode suppressed the signal meant to interrupt you. `release · waiting` had no representation at all.

With many tabs open, only one **pane** is visible, so the tab strip is where a session signals you when you're looking elsewhere. It has two slots, and there are now two axes:

| Slot | Now carries |
|:---|:---|
| tab **color** | `activity` — gray at rest, orange working, red when Claude needs you |
| tab **glyph** | `mode` — `⏸` pause, `🚀` release, `📋` retro, `🏁` done |

Nothing arbitrates between them, since they never share a surface: a release that hits a permission prompt is a red tab beside a `🚀`. The pane background still carries the mode, but only in the focused pane.

So a mode no longer hides whether a session needs you, and every mode is visible from a tab you aren't looking at. Previously only `paused` marked the tab label, leaving four of five modes distinguishable by hue alone.

### `beacon status` sets modes only

`beacon status working` is now an error naming the mode verbs. It used to pin the activity above the hooks, and the pin never expired: thirteen sessions in local state carried one, most 77–90 days old, and **eight contradicted the live hook signal** — tabs painted `working` while the session was blocked on the user. The hooks own activity; there is no longer a way to overrule them.

`beacon status dev` leaves whatever mode is set. `beacon pause` / `release` / `retro` / `done` are unchanged.

### Pausing no longer pins your project and task

Pausing used to snapshot the resolved project and task into overrides so the identity held still while parked, and resuming *kept* them. One pause therefore pinned a session's labels permanently, above every provider that would otherwise refresh them. Local state held tasks pinned to branch names the session had left and a project label a version and a half stale, none of it distinguishable from a label someone set deliberately.

Pause now writes the mode and its note, and nothing else. The fleet view already reads the last-rendered snapshot for the same stability, and a snapshot can't outrank a live provider.

### `beacon json` emits the payload CMD-15 specifies

The payload documented "signals, providers, description" and shipped three of the seven keys `resolve()` returns. `beacon json | jq -r .task` printed `null` unconditionally — not "no task set", but "never emitted".

```json
{
  "project": "beacon",   "project_provider": "git-remote",
  "task": "split status into mode and activity",
  "task_provider": "override",
  "mode": { "name": "release", "note": "cutting v2.5" },
  "activity": "waiting",
  "branch": "...", "url": "...", "cwd": "...", "claude_session": "..."
}
```

Every signal now ships with the provider that supplied it. That matters for `task` specifically: the branch name is the task chain's third tier, so `task` and `branch` are routinely byte-identical, and only the provider distinguishes a label you chose from a fallback. That pair is what [anchor#2](https://github.com/chris-peterson/anchor/issues/2) needed.

**Breaking:** `status` and `description` are gone from this payload, with no aliases. A `status` alias would have to merge the two axes back into one field, reproducing the defect for any consumer reading it.

### Announcing a break in prose no longer parks your session

Typing "brb" or "stepping away" used to park the session, mark it `⏸`, and exempt it from the fleet's activity window. Across three months of local state it authored **zero** notes — every one came from an explicit `pause`, `release`, `retro`, or `done`. Those phrases also now signal the opposite: they're what you say when handing work off to run unattended, so the pane was parked while the session kept working. Say it however you like; use `/beacon:pause` to park.

### A note belongs to its mode

A mode's note is stored with the mode and cleared with it, so it can't outlive what it annotates. It surfaces in the Claude Code status line (led by the mode's glyph) and the fleet view; it is never painted on the pane, where there's no room for prose. Recall context is `latest_turn`'s job — derived from the transcript, needing nothing from the agent.

### `retro` gets a new mark

`retro`'s watermark was a detailed illustration whose linework was illegible at watermark opacity. It's now a ticked clipboard matching its `📋` glyph, drawn from code (`iterm/marks.py`) rather than committed art, so the next adjustment is an edit rather than a redraw.

### The `handoff` mode is gone

The mode set is `dev`, `pause`, `release`, `retro`, `done`. `handoff` marked a session mid-transition to another tool or session, and what separated it from `done` was a single turn: it lifted on your next prompt. The phase it named — a work session closing out — is what `done` already says, and what a route tracker records durably rather than for one turn on a tab.

`beacon handoff` is gone, and `beacon status handoff` is an error naming the modes that remain. The automatic trigger goes with it: tack's session-close skill firing no longer moves the pane into a mode, so `/tack:end` leaves whatever mode is set. Declare `beacon done` when you want the finished pane to say so.

`install` sweeps the stale `beacon-handoff` profile, so run `/beacon:install-beacon` once to clear it from iTerm2's picker.

### Dashboard: stacked cards reveal on hover

Where several sessions share a project, the dashboard stacks their cards. Hovering a tucked-behind card now brings that whole card forward, above the front one — you read the real card. It replaces a floating tooltip that showed the tucked card's task and latest turn, a second and partial rendering of something you could just be shown. Clicking still pins the raise, and keyboard focus gets the same reveal.

### `cd` in a beacon shell is roughly 40x faster

A directory change in a beacon-integrated shell cost ~574ms, and a plain prompt redraw ~63ms. A `cd` is now ~15ms and a redraw ~14ms.

Nearly all of that was python interpreter startup: every prompt published seven iTerm2 user-var slots and paid a `beacon-iterm` process for each one. The shell writes those escape sequences itself now — straight to the terminal device, encoded by a zsh-native base64 — so a redraw spawns nothing. Branch resolution collapses four git invocations into one, and the origin URL is remembered per project root.

### Opening a terminal spawns no python

Sourcing beacon's shell integration asked the plugin two questions — where its data dir is, and whether the badge is on — and each answer cost a python interpreter startup, in every terminal you open. They now come from one cached block, rebuilt only when beacon itself, its data-dir record, or `~/.config/beacon/config.json` is newer than the cache. In the steady state, sourcing spawns nothing.

### Also

- The `url` and `icon` overrides are removed. Neither was carried by any session in three months of local state, and the icon reaches only the dashboard, never a terminal surface. Icon auto-discovery is unchanged.
- `beacon show` reports the two axes separately, with a provider on the signals that have a provider chain and none on the two that have a single writer each.
- The fleet view (`wip`, `watch`, the dashboard) shows both axes: `release·waiting` in the text views, and a mode-tinted card with a red dot in the dashboard.
- **Breaking:** `wip.json` carries `mode` as the same nested `{name, note}` tuple `beacon json` does, rather than a flat `mode` string beside a top-level `note`. Both payloads now describe the value identically, so a consumer reading either writes one accessor.
- `install` now sweeps stale beacon profiles by comparing against what it just wrote, instead of carrying a list of every profile name retired since 0.x.
- **Breaking:** `wip.json` and `beacon json` can no longer carry `handoff` as a mode name. A stored value this version doesn't recognize reads as `dev`, so a session left in the old mode reports the dev cycle rather than needing a migration.
- Fixed: mode watermarks on dashboard cards were sized from the card's *width*, and the assets are square while a card is far wider than it is tall — so the mark came out taller than the card and was cropped to a middle band, reading as an off-centre fragment. They size from the height now, the CSS analog of the Scale Aspect Fit the pane uses.
- Fixed: `beacon watch` column alignment with the new glyphs. `🚀` `📋` `🏁` are one character but two terminal columns wide, so padding by character count left every glyph-bearing row a column short.

## 2.4.1

### Panes keep your color scheme on a fresh install

A first install painted panes near-white. The base profile forced iTerm2's "Use Separate Colors for Light and Dark Mode" off, and that switch decides which color keys iTerm2 reads — off, a dark-mode pane resolves to the parent profile's *light* background. The switch is the parent profile's to answer now, and the two colors beacon does set in a profile, the mode backgrounds and the ready-gray badge default, are written for either setting.

### A long status-bar button label no longer blanks the button

An action button draws its title inside a width cap, under a layout that removes components rendering empty — so a `statusbar.buttons.<name>.label` wider than the six-character default erased the button instead of truncating it. The cap now grows with the label you configure.

### Splits open where the pane they split from is

A split off a beacon pane started at `$HOME`, so every split cost a re-navigation back into the project the parent pane was already in. It inherits the parent pane's directory now, in every mode. New tabs and windows stay your own profile's to answer.

### Two more layout recommendations from `beacon-iterm configure`

The audit now covers **tab bar always visible**: iTerm2 hides the bar at one tab per window, which is where a single-pane session lives, and it takes the tab color and two-line label with it. And it recommends the **status bar at the top** rather than the bottom, since the bottom of the pane is where Claude Code renders beacon's own status line.

### Upgrading

The internal `resolve-url` subcommand is gone. It had no caller left and was already hidden from completions; `copy-url` and `open-url` are the supported doors onto the same resolution.

## 2.4.0

### `/beacon:pause` is the only slash command left for state

Parking a session is the thing you reach for by hand, mid-turn, so `pause` gets a command of its own again.

`/beacon:session-mode` is gone with it. It was kept model-invocable so a skill owning a phase could enter the matching mode itself, and that caller never showed up — a skill runs `beacon release` in one shell call, where a slash command spends a whole model turn to reach the same subcommand. The skills that actually drive modes were written against the CLI from the start. The collision that folded `/beacon:release` and `/beacon:retro` into it is still resolved, more simply: with no mode command at all, there is nothing left to collide with the skills of those names.

### The `/beacon:beacon` wrapper and the beacon skill are gone

Both were doors onto the CLI that cost a model turn to walk through. `! beacon <anything>` from a Claude prompt is faster and needs no reasoning, so the wrapper earned nothing; the skill's two conventions — don't set a status the hooks own, don't narrate the invocation — now live in the `keep-session-labeled` ambient rule, which is in context from SessionStart instead of waiting to be loaded, and its CLI-freshness check was already the SessionStart hook's job.

The `project` slot moved into that rule with them: ask for the *session* or the *tab* to be labeled and Claude sets `project`, the leading line, rather than the task under it.

### `install-cli` folds into `install`

`install-cli` ran exactly `install`'s first two steps, and it was the one the drift nudge pointed you at — which made it the wrong answer to the situation you reached for it in. The `source` line in `.zshrc` is version-pinned the same way the wrapper is, and only `install` rewrites it, so refreshing the wrapper alone left your shell integration on the previous version. `--dir` moved onto `install`; `beacon completions zsh` still stands alone if that's all you want.

### `/beacon:install-beacon` for the upgrade path

The one thing a slash command can do that `! beacon` can't: run from the *newly installed* plugin root. A stale wrapper's `beacon install` re-points everything at the version it already names, which is why the freshness nudge has to name a plugin-root door. It now names `/beacon:install-beacon`, and says why the shell path won't do.

The plugin is in the name because the bare `/install-beacon` is what you end up typing, and every sibling plugin that puts a wrapper on `$PATH` needs the same door — a plain `/install` would be a four-way collision the moment a second one shipped.

### `install-profile` is now `refresh-iterm-profiles`

Same operation, better name. `install-` means the bootstrap now, and this was never one — `beacon install` writes the profiles itself, so you only reach for this to *re-apply* one. It also writes five profiles, not one.

Three things make a rendered profile stale, and only the first is something you did on purpose: a `statusbar.buttons.*.label` edit, a `python3` that moved out from under the baked absolute path (buttons silently stop working, and nothing tells you), and a profile you edited in iTerm2's GUI. After a plugin upgrade, use `/beacon:install-beacon` instead — the profiles embed the plugin's own paths, so re-rendering through a stale wrapper bakes the old version's paths back in.

### A `handoff` mode for a session passing control on

A session mid-transition to another tool, skill, or session had no mode that fit. `paused` freezes the badge identity, and `release` / `retro` / `done` persist until you explicitly resume — so routing a session close into `done` would leave the pane in a terminal mode while the session keeps working past the close.

`handoff` borrows the one trait that fits, auto-resume on the next prompt, and none of `paused`'s other semantics: no identity freeze, no watermark on the pane, just its own background and badge color. It enters automatically when tack's session-close skill fires — beacon watches for the skill rather than asking tack's skill text to name beacon, since tack is a separate, tool-agnostic project — and by hand with `beacon handoff [<note>]`.

### The fleet view finds your sessions when beacon is loaded from a directory

Claude Code hands hooks a `CLAUDE_PLUGIN_DATA`. Slash commands, the `~/.local/bin/beacon` wrapper, and the serve service get none, and derived the directory from the checkout's git remote instead, which always lands on the marketplace name. Load beacon from a local directory (`claude --plugin-dir .`) and the two halves disagreed: hooks wrote a full session record to `beacon-inline` while `wip`, the dashboard, and `statusline` read `beacon-chris-peterson` and found nothing there.

It presents as hooks that never fired, because the pane still paints correctly — a hook process holds a consistent view of its own directory. Every hook now records which install is loaded, at `~/.config/beacon/data-dir`, and the env-less callers read that pointer. One that is empty, unreadable, or names a directory since removed reads as absent, so a stale record can't strand every invocation on a dead path.

### The docs site splits, and the /iterm figures render again

The tab and status-bar figures on `/iterm` shared a `bcn-` class prefix with the stylesheet shipyard links into every plugin page. Its rules landed after the page's own, and its `.bcn-tab` background resolved through a variable these figures never set — so the ready and paused tabs came out white-on-white with the dot stacked over the label, and the branch chip rendered slate while the legend beside it called green "synced". The figures now sit in a `panefig` namespace nothing else claims. On a phone the status-bar strip clipped the `↗ code` button off while the legend still described it; the strip scrolls now. The tab-strip caption, which was 1.41:1 against a light background, takes the page's own text color.

The home page ran past 11,000px behind a five-entry sidebar, so the status-bar button configuration moves to its own [`/statusbar`](https://chris-peterson.github.io/beacon/#/statusbar) page and the sidebar goes flat. [`/why`](https://chris-peterson.github.io/beacon/#/why) is new: what to weigh beacon against tmux, Zellij, a worktree orchestrator, or a terminal built for agents — including where those win, and the problem none of the category has solved, that sessions have no clear end so any view of them drifts into a list of finished work.

### beacon won't carry session-to-session messages

Claude Code now has cross-session `SendMessage`, which sits close enough to what the fleet view computes that it's worth answering once: beacon is not going to surface or wrap it. beacon publishes state anything may read, where a message bus owes delivery to a named recipient — a different contract with different failure modes. The messaging primitives are also macOS and Linux only, and the fleet view runs wherever Python does, Windows included.

### Upgrading

| Change | What to do |
|:---|:---|
| `/beacon:beacon` removed | run the CLI: `! beacon <subcommand>` |
| `/beacon:session-mode <mode>` removed | run the CLI: `beacon release` / `retro` / `done` / `resume` |
| `/beacon:beacon install` removed | use `/beacon:install-beacon` |
| `beacon install-cli` removed | use `beacon install` (`--dir` moved there) |
| `beacon install-profile` renamed | use `beacon refresh-iterm-profiles` |
| beacon skill removed | nothing; the ambient rule covers it |
| new `beacon-handoff` mode profile | run `/beacon:install-beacon` to write it |

## 2.3.0

### `install` wires the status line for you

The status line only exists if `statusLine` is set in Claude Code's settings, and `install` printed that block for you to paste rather than writing it. So the row existed only where the block had been pasted — and pasted into a single project's `.claude/settings.local.json`, it is scoped to that one repo, which from every other repo looks exactly like a status line that never has anything to say.

`install` now writes the block into `~/.claude/settings.json` itself. It touches that one key and leaves the rest of the file alone, and it will not replace a `statusLine` you already set: if you have your own, it says so and prints beacon's for you to merge by hand.

### Open tacks reach the status-line row

2.2.1 scoped the row to one Claude session, and read "this session's work" as the tack in progress plus anything completed since the session started. Routes are commonly kept the other way — the tack is filed as `pending` and marked done at ship time — so on those routes nothing qualified while the work was actually happening, and the row stayed empty until the moment it shipped. The issues and CRs the route was carrying never appeared at all.

The row now takes the route's open work, `pending` as well as `in_progress`. Completed tacks are unchanged: they still need to have landed after the session started, which is what keeps the project's shipping history off a fresh session's row.

## 2.2.2

### The status-line link stops naming last session's PR

2.2.1 kept work from earlier sessions off the delivered row but left one way in. The link the row falls back to when a session has touched nothing is the resolved URL, and on a tack route with nothing open, that resolver nominates the most recently completed deliverable — so a fresh session still opened with the PR you merged yesterday, which is what the fix was supposed to end.

The link now skips a delivery that landed before the session started and takes the next answer down the chain: an open PR or MR for the current branch, else the branch page, else the repository. On a branch whose PR the route hasn't caught up with, that means the row shows your actual PR instead of the route's last one.

`↖ web` is unaffected — it resolves when you click it, it's asking where the project's work lives rather than what this session did, and an old merged PR is a fine place to land.

## 2.2.1

### `↗ code` lands in the right directory again

The button's default command was `code --maximized`. VS Code's CLI has no `--maximized` option — it hands one it doesn't recognize to Electron/Chromium, and on a cold start (nothing running yet) that makes it drop the directory and open a Welcome window. Click the button with VS Code already open and the directory arrived; click it as the day's first launch and you got an empty editor. It never maximized anything either: VS Code exposes no CLI flag for window state.

The default is now a bare `code`. If you want a maximized window, that's `"window.newWindowDimensions": "maximized"` in VS Code's own settings. Startup flags you add to `statusbar.buttons.code.cmd` are worth checking against your editor's `--help` first, for the same reason.

### The tab keeps its name when you exit Claude

Ending a session returns the pane to its unmanaged look, which blanks the user vars the tab label and window title interpolate. The name itself was left pointing at them, so the tab went blank on `exit`. It now hands the name back to the interactive title — the project you're in, else the directory — which the shell prompt keeps current.

The handback also moved ahead of the blanking. It runs over Apple Events, and if it didn't land, the pane stayed blank permanently — the shell sets the name once at startup and skips a pane Claude owns, so nothing came along later to reclaim it. Done in this order, a handback that fails leaves the last label you had instead.

If you have a pane already stuck this way, `beacon clear` in it restores the label.

### The status-line row is this session's work again

The delivered row is meant to cover one Claude session, and a new session cleared it. Acquisition then refilled it: it read every deliverable and tracker link the bound tack route held, and a route lives as long as the project does. So a session that had shipped nothing opened with a row of merged PRs and old release tags, and there was no way to tell that from a session that had genuinely just landed them.

A tack now reaches the row only if the session touched it: it's the one in progress, or it completed after the session started. The resolved URL is held to the same bar, which matters more than it sounds — with nothing open on a route, that resolver falls back to the most recently completed deliverable, so it kept nominating work from previous sessions. `↖ web` and the status line's own link still go there (a stale click target beats none), but the row no longer counts it as delivered.

Nothing to configure, and route hygiene still bounds what the row can show. A pane that was already running keeps its current row until its next session.

### `prune` collects the per-pane cache too

`prune` swept per-session state and left the pane cache alone — the working-directory handoff files and engagement markers the status-bar buttons and the shell read. Those are named by pane, so one accumulated for every pane you have ever opened and nothing removed them; long-running installs have thousands.

The same `--since` cutoff now applies to both, going by each file's own timestamp (both writers touch them continuously while a pane is alive, so an untouched one belongs to a pane that's gone). Your current pane is always kept.

The sweep also picks up the `url-` handoff files 2.0 stopped writing when `↖ web` moved to resolving at click time. Nothing has read those since, and on this machine they were about half the directory.

## 2.2.0

### The status line reads your whole tack route

The second status-line row — what the session has to show for itself — was fed by one thing: the deliverable the *current branch* points at. An issue filed from `main` with no branch and no open PR reached it not at all.

It now reads every deliverable and tracker link on the tack route bound to the session, plus the branch resolution as before. Nothing to configure: if a route is bound, the issue you filed through `/anchor:issue` and the CR that answers it are both on the row. With no route bound the row is what the branch resolver finds, as it was.

Each entry now carries the project **its own URL** names, so another project's `#9` renders `otherproj:#9` instead of passing for a local ref.

### GitLab work items, epics, and milestones

`/-/work_items/<n>` — GitLab's rename of `/-/issues/<n>`, and what the API hands back — is recognized as an issue. Epics (`&7`) and milestones (`%2`) are classified rather than ignored, and ride the issue line. Sigils are GitLab's own, so a ref reads the way you'd type it into a comment. An epic belongs to a group rather than a repo, so it reads bare when that group is the one your repo lives in — the tracker your own work is filed under shouldn't look like another project's.

### `beacon drop <ref>`

Takes one deliverable off the row and keeps it off:

```console
$ beacon drop otherproj:#9
dropped otherproj:#9 (3 deliverable(s) remaining)
```

A URL you pasted as a reference looks exactly like one you're working, and the row is capped at eight — so noise left in place evicts real work. Matches the ref as rendered, the bare ref, or the URL. Session-scoped: a fresh session starts clean.

### The docs lead with the tab

Since v1.26.0 the pane badge has been opt-in and off by default, and the tab carries what it used to: the color is the ready / busy / blocked state, and the label is `project` over an indented `task`. The docs hadn't caught up — they still introduced the badge as the surface you read a session from.

[In iTerm2](https://chris-peterson.github.io/beacon/#/iterm) and [The beacon palette](https://chris-peterson.github.io/beacon/#/palette) now describe the tab, and [Turning the badge on](https://chris-peterson.github.io/beacon/#/iterm?id=turning-the-badge-on) covers `"badge": "on"` for a one-window-at-a-time workflow, where the badge is still the bigger target.

The iTerm2 page also corrects what beacon claimed not to paint: it does own the window title now, via the session name, so a `/rename`d Claude session keeps its project in Mission Control and the window switcher.

## 2.1.0

### Customizable status-bar buttons

The `↖ web` and `↗ code` buttons take their label and their command from a `statusbar.buttons` block in `~/.config/beacon/config.json`, with `{dir}` / `{project}` / `{branch}` placeholders for positioning values in the command. See [Customizing the two buttons](https://chris-peterson.github.io/beacon/#/?id=customizing-the-two-buttons).

This replaces `web_cmd`, `code_app`, and `code_args`. A config still setting them renders the defaults rather than erroring, so move them:

| Was | Now |
|:---|:---|
| `"web_cmd": "git web"` | `"statusbar": { "buttons": { "web": { "cmd": "git web" } } }` |
| `"code_app": "code", "code_args": ["-n"]` | `"statusbar": { "buttons": { "code": { "cmd": "code -n" } } }` |

A changed `cmd` applies on the next click. A changed `label` applies on `beacon install-profile`, a new profile-only re-render: iTerm2 keeps an action button's title in the profile and gives it no way to read a user variable, so the label has to be baked in.

### The project chip is the project's name

The status bar's project chip showed an abbreviated forge identity with a deliverable ref pinned to it (`gh:acme/widgets#42`). It now shows the project's name (`widgets`).

That makes it work everywhere the old one didn't: outside a git repo, in a repo with no remote, and in a plain shell with no Claude session, the chip names the directory instead of collapsing to nothing. It also takes a `resolve-url` call — a Python start plus a possible `tack` subprocess — off the shell's every-prompt path, since a name needs no URL.

Which deliverable you're on is the [status line](https://chris-peterson.github.io/beacon/#/iterm?id=the-status-line)'s job, where the ref is a clickable link, and the `↖ web` button still opens it.

**Retired:** the `_beacon_resolve_url()` shell override (BADGE-08). Its only consumer was the chip's deliverable ref, so redefining it would now change nothing.

## 2.0.0

beacon's per-session context moves off iTerm2 and into the Claude Code status line — a footer Claude renders, that never overlaps terminal output, and that **any** terminal shows. What stays on the iTerm2 strip is what a footer can't do, rebuilt so it can't go stale.

## The status line is the new home for per-session detail

Wire `beacon statusline` into `settings.json` (`beacon install` prints the block) and you get a line per class of thing, empty ones omitted:

```text
⏸ waiting on CI
v1.26.0 released 🚀 · #19 closed ✓ · #27 merged 🏁
#28 Move per-session values into the Claude Code status line
#25 · #18 · #26 · #23
```

- **Every ref is a clickable link.** Refs in the current project render bare, refs elsewhere are qualified (`otherproj:#75`), so a session crossing repos still reads unambiguously.
- **Delivered work stays on screen.** Shipping is rare and it's what a session has to show for itself, so a merged CR, a closed issue, and a published release each keep their place, reading by verb and glyph in the green beacon reserves for releases.
- **Open change requests carry a title** — the same string the badge shows, so the two surfaces never describe one PR differently.
- **Issues trail, dimmed.** On GitHub a CR and an issue are both `#<n>`, so the line and the weight are what separate them.

"Delivered" follows your [tack](https://github.com/chris-peterson/tack) record: a tack that's `done` promotes its deliverable. That means it tracks the work *you* logged rather than the forge, and can drift if a tack goes stale — the trade is that the row costs no network call, which matters because it renders on every prompt. Releases need no tack: a release tag only exists once published.

The pause reason landed here first (1.27-era, #15); this builds the rest on top.

## The iTerm2 strip is smaller and steadier

`↖ web · project ⟷ branch ↗ code` — the project identity now sits beside the branch it describes.

- **`↖ web` resolves when you click it.** No cached URL means it can't disagree with the chip beside it, which is what made it flaky before (#5). It works in *any* pane — including a plain shell with no Claude session, which is exactly when you want to jump to a repo's web view.
- **Both buttons are configurable.** `code_app` / `code_args` choose the editor (default `code --maximized`); `web_cmd` hands the web button to your own command, e.g. `"git web"`. Both are read when you click, so changes take effect with no reinstall.
- **`⇄ review` is gone**, and so is the feature behind it. `beacon review`, its moor sidecar contract, the anchor delegation, and the `moor` / `anchor` soft dependencies are all removed. It went unused, and reviewing a diff is a job other tools already own.

## One command for session modes

`/beacon:release`, `/beacon:retro`, `/beacon:pause`, and `/beacon:done` become **`/beacon:session-mode <mode>`**. `/release` and `/retro` are common enough verbs that a bare invocation was ambiguous against the ai-sdlc skills of the same name — and beacon's wrappers were the interlopers. The CLI is unchanged: `beacon pause`, `beacon retro`, and friends work exactly as before.

## Upgrading

**Run `beacon install`.** The status-bar layout is baked into the iTerm2 dynamic profile, so the chip changes need a rewrite. iTerm2 reloads without restarting.

| Change | What to do |
|:---|:---|
| `/beacon:{release,retro,pause,done}` removed | use `/beacon:session-mode <mode>` |
| `beacon review` removed | use your difftool directly |
| `⇄ review` chip removed | — |
| `beacon_url` user variable no longer published | read `resolved.url` from session state |
| `url-<pane-guid>.txt` handoff file removed | internal; no action |
| `↗ code` default is now `code --maximized` | set `code_app` if `code` isn't on your `PATH` |

Fixes along the way: the `↗ code` button failed for anyone whose editor lives outside `/usr/bin` (an iTerm2 action shell has no interactive `PATH`, so it now asks your login shell), and several Windows path and encoding bugs.

## 1.26.0

## What's Changed
* Adopt shipyard for build tooling and CI by @chris-peterson in https://github.com/chris-peterson/beacon/pull/16
* Re-sync describe: annotate hook tool matchers by @chris-peterson in https://github.com/chris-peterson/beacon/pull/17
* Recommend and apply the iTerm2 fleet layout by @chris-peterson in https://github.com/chris-peterson/beacon/pull/21
* Split render model: land the stock-iTerm2 wins by @chris-peterson in https://github.com/chris-peterson/beacon/pull/24


**Full Changelog**: https://github.com/chris-peterson/beacon/compare/v1.25.0...v1.26.0

## 1.25.0

### Features
- Dashboard cards let you select and copy text without collapsing: a mouse-up after selecting turn text keeps the selection instead of toggling the card open/closed.
- The expanded turn now has its own copy button — it copies the full fetched turn text when the card has it, otherwise the on-screen excerpt, so a copy never returns less than what you see.
- Each real Claude session's card gains a `resume` row carrying its `claude --resume <id>` command, copyable in one click.
- New pop-out mode (Chromium browsers): an always-on-top floating panel that starts with the sessions waiting on you and pulls in others as they show activity while it's open. Clicking a row raises that session's iTerm2 window rather than expanding detail, and the panel auto-fits its height to its contents. A leave-confirmation guards against a stray tab close silently tearing the panel down.

### Other
- Removed the orphaned `dev/preview.py` and its `just preview` recipe, dead since the 1.0 marginalia-overlay retirement and failing to import (`ModuleNotFoundError: _compose`).
- Dashboard source cleanup: literal NUL bytes (turn-cache signature separator, no-group sentinel) replaced with the `\x00` escape used elsewhere, so the file stays reviewable text.

## 1.24.0

### Features

- Each session mode now paints a richer, illustrated watermark on the iTerm2 pane: a rocket while releasing, a checklist clipboard during a retro, a checkered finish-flag when done, and a pause button when paused. The retro mode, previously plain, now carries a mark of its own.
- The fleet dashboard's mode cards now show the same watermark the pane paints — served from the actual generated asset — so a card and its pane always match instead of drifting apart.

### Other

- Mode watermarks are now produced by a single shared pipeline: one command regenerates every pane asset and its dashboard thumbnail together, replacing three separate hand-drawn generators.
- Watermark source art and generated marks moved under `iterm/resources/`.
- Spec, palette, and command docs updated to the new marks.

## 1.23.0

### Features

- On the default branch, `beacon review` (the `⇄ review` status-bar button) now reviews uncommitted working-tree changes instead of reporting "nothing to review". A quick edit made directly on `main` gets the same review affordance branch work already has. When the [anchor](https://github.com/chris-peterson/anchor) plugin is installed and the working tree is dirty, beacon delegates to anchor's working-tree review (`review-diff.sh --local`) and relays its verdict.

### Notes

- anchor is an optional soft dependency, detected via Claude Code's plugin registry. Without anchor — or on a clean tree — `beacon review` stays inert on the default branch, exactly as before. Feature-branch review (branch vs. default) is unchanged.

## 1.22.1

### Fixes
- The iTerm2 window title on a Claude session now reliably shows `project · task`, mirroring the badge. Previously — on setups with many open windows — a plain shell's startup title write could win a race on the shared session-name surface and leave an engaged pane stuck showing the project (or cwd) with no task. The shell now defers to the plugin on a Claude-owned pane.

### Other
- Spec (TITLE-04) and CLAUDE.md reconciled to the new deferral mechanism.

## 1.22.0

## Status-bar buttons survive pane moves

- The ↖ web and ↗ code buttons stopped working once a pane was moved between windows, tabs, or splits: their handoff files keyed on the full `ITERM_SESSION_ID`, whose `wNtNpN` positional prefix iTerm2 rewrites on a move. The web button then opened a stale fallback and the code button silently did nothing.
- The handoff cache files, the engagement marker, and the per-session state bucket now key on the stable pane **GUID** (the same handle focus and set-name already target), so a moved pane keeps working.

## Web button follows the session's tack route

- The ↖ web URL now resolves by the session→route pin — the same route the fleet-view chip shows — instead of matching only the git branch slug. A route pinned to the session whose slug differs from the branch (e.g. an issue tacked mid-session) previously resolved to the branch tree; it now opens the pinned deliverable.

## Buttons report when there's nothing to open

- When no URL or working directory has been resolved, the buttons now surface a beacon-named alert instead of opening a generic search page (web) or silently doing nothing (code).

## Upgrade note

- Because per-session state now keys on the pane GUID rather than the full session id, sessions that were already open before upgrading do not carry their prior task/status across — they re-establish it on their next turn. Newly started sessions are unaffected.

## 1.21.0

## Window title, /rename, and wander rendering

- Interactive panes now show the current directory in the window title when outside a project, instead of going blank.
- Claude Code's `/rename` now updates the beacon task label — it's treated as shorthand for `beacon set task`, sharing one slot where the most recent of the two wins.
- The plugin reclaims the Claude-pane title once per session (a one-shot on the first turn boundary), so the shell's backgrounded startup title write can no longer clobber it.
- The wander overlay reads `home @ where · what` — a ` @ ` separator symmetric with the ` · ` task separator — instead of the old `home · @where: what`.

## Export / import state backup

- New `beacon export` dumps every session's raw per-session state into a versioned JSON envelope (gzip optional); `beacon import` restores it byte-for-byte, preserving mtimes so the activity window survives a restore. Each record carries `claude_session_id`, the join key to a tack export.
- zsh completions extended to the new commands (plus the previously-missing `json` / `open-url`), with a CI guard against argparse ↔ completion drift.

## Windows CI fixes

- UTF-8 encoding on template reads and export/import I/O, and `git difftool --no-symlinks`, so the review-feature tests and the moor sidecar verdict work on Windows.

## 1.20.0

## Window title

A `/rename`d window kept losing its project context, leaving concurrent sessions hard to tell apart in Mission Control, the window switcher, and the Dock. The OS window title now carries `project · task` — the same as the badge — and it sticks.

- **`project · task` in the title bar** — set via the iTerm2 session *name*, so it survives Claude Code's `/rename` and auto-titles. The profile disables terminal-set titles (`Allow Title Setting`), so nothing overwrites it; beacon owns the name out-of-band through Apple Events.
- **Reuses the badge template** — the title and badge are one source, so they never drift, and the title re-evaluates live as the project / task change.
- **Interactive shells get it too** — a plain `beacon-dev` pane shows its project in the title (project only; there's no task outside a Claude session).
- **Profiles unchanged** — no profile renames, same switch keys, so nothing else moves.

## Badge default

- **At-rest badge is now gray by default** — a fresh pane reads the dev-cycle gray before its first status render, instead of inheriting the parent profile's badge color.

Full detail in the [CHANGELOG](https://github.com/chris-peterson/beacon/blob/main/CHANGELOG.md).

## 1.19.0

### SDLC cycle profiles

- **Statuses are now SDLC cycles.** The everyday **dev** cycle (`idle` /
  `working` / `waiting`) rides the base `beacon-dev` profile with a dynamic
  badge stoplight; the mode cycles — `pause`, `release`, `retro`, `done` — each
  own a dedicated profile. `wrapping` is renamed **`retro`** and `releasing` is
  renamed **`release`**; the base profile is renamed `beacon` → `beacon-dev` and
  the mode profiles to `beacon-pause` / `beacon-release` / `beacon-retro` /
  `beacon-done` (an upgrade sweeps the old profile files).
- **`release` mode** — a new cycle for a ship-it / release flow (`beacon release`
  or `/beacon:release`): a deep launch-sky navy pane with a faint rocket
  watermark under a pinned **green** badge.
- **Green leaves the dev stoplight.** At rest the badge is now a neutral **gray**
  (a session's known default before its first turn), so green is reserved for
  `release` and reads unambiguously as "shipping."
- **`done` drops the task.** A completed session shows its project alone —
  the task slot is suppressed while `done` (reversibly, STATE-12) — plus a
  dim-gray badge and the powered-off pane.
- **`retro` recolored** to a white badge on its muted-green pane.
- **No more `||` badge glyph.** Every cycle now reads by background + color
  alone, consistently across the pane, the dashboard card, and the fleet list;
  the pause text glyph is gone.
- **New docs page — [The beacon palette](https://chris-peterson.github.io/beacon/#/palette)** — the cycle
  taxonomy and every color, plus refreshed fleet screenshots.

### Spec & internals

- New requirements STATE-11 (the `release` synonym), STATE-12 (`done` suppresses
  the task, keeps the project), and STATE-13 (the SDLC cycle vocabulary); the
  pre-existing STATE-10 (`pause --clear-screen`) is unchanged. BADGE-09 stoplight recolored (gray at
  rest), BADGE-11 rewritten (no glyph), and the `wrapping`/`releasing` →
  `retro`/`release` and `beacon` → `beacon-dev` renames threaded through STATE,
  CMD, RENDER, THEME, WIP, and §6.6. Colors stay Dracula-sourced (THEME-01), the
  `release` navy being a darkened `comment`.

## 1.18.0

### Fleet dashboard: grouping, project stacks, and a needs-you band

- **Automatic grouping** — the fleet view now groups sessions by their
  correlated route group; the flat/group toggle is gone. Sessions with no route
  group fall into an unlabeled section at the bottom.
- **Same-project stacks** — multiple sessions for one project collapse into an
  overlapping stack, newest in front, with the rest brought forward on click or
  Tab (an animated raise). Only the front card exposes its controls; a behind
  card is click-anywhere-to-raise and previews its task + latest turn on hover.
  An expanded card holds the front slot so a sibling's newer turn can't collapse
  what you're reading.
- **Needs-you band** — genuinely blocked sessions are hoisted into a pinned band
  above the calmer fleet. A parked/wrapping/done session stays in the fleet (its
  mode outranks a lingering attention marker), so it reads as set-aside rather
  than as needing you. Clicking a card's `waiting` pill focuses the session.
- **Mode-card treatment** — a paused/done card echoes its iTerm2 pane: a muted
  tint plus a large, faint, centered watermark (`||` for paused, a power-off ring
  for done); wrapping is tint-only.
- **Inline forget** — the card close (×) opens a small confirmation fly-out
  instead of the browser `confirm()` dialog (Keep / Esc / click-away to dismiss).

### Spec & internals

- New requirements WIP-15 (project stacks), WIP-16 (route grouping), WIP-17
  (mode-card treatment), RENDER-06 (suppress iTerm2's native notifications),
  HOOK-10 (SessionStart emits the bundled ambient rules); WIP-12 narrowed to the
  text-only views. Coverage ledger refreshed to 149 IDs; the duplicate CMD-16
  (`data-dir`) is renumbered to CMD-21.
- Removed the never-read pending-attention prompt-type plumbing (the `--type`
  hook flag and its state field).

## 1.17.0

### Branch review

- New `beacon review` subcommand diffs the whole branch against the default
  branch (`origin/HEAD` → `main` → `master`) through git's configured difftool
  with `MOOR_CONTEXT` set, relaying [moor](https://github.com/chris-peterson/moor)'s
  sidecar verdict (comments + exit code) on stdout. On the default branch, or
  outside a git repo, it reports there's nothing to review instead of opening an
  empty diff.
- The status bar gains a centered **`⇄ review`** action chip — an iTerm2 Send
  Text action that types `beacon review` into the pane. In a shell it opens moor
  for a manual review; in a live Claude session Claude runs it and acts on the
  `fix-now` comments, closing the review loop from one click. `bin/beacon-iterm`
  stays unaware of moor and Claude. (#11)

## 1.16.0

### Fleet dashboard

- Turn cards now render markdown **links** — `[text](url)` becomes a clickable
  link (new tab), including code chips inside links (`[`sha`](url)`) and links
  in table cells. Hrefs are scheme-sanitized (http(s)/relative/anchor only) and
  quote-escaped, so a `javascript:`/`data:` URL falls through as plain text.
- **Bold-wrapped inline code** (`` **`x`** ``) now renders as bold code, in the
  collapsed one-liner, the expanded panel, and table cells.

### Session control

- `beacon pause --clear-screen` clears the iTerm2 session's screen **and**
  scrollback (the Cmd+K / "Clear Buffer" equivalent) alongside pausing — for a
  clean stand-down, e.g. the retro launcher parking a spent session. It degrades
  gracefully outside iTerm2 or with no reachable tty: the pause still applies,
  the clear is skipped. (#8)

## 1.15.0

### Fleet dashboard: rich turn rendering

- Expanded session cards render Claude's replies as markdown — bold, inline &
  fenced code, bulleted/numbered lists, headings, and GFM tables — in a quoted
  transcript panel; the collapsed one-liner renders inline bold/code too. All
  rendering escapes before it formats, so turn text can't inject markup.
- The session description renders its own _italic_ and line breaks (beacon's
  status-overlay convention) instead of raw underscores; underscore-italic is
  word-boundaried so `snake_case` and paths in a recall note stay intact.

### Card layout & de-duplication

- `/color` reads as a compact identity pill on the project name rather than a
  full saturated header band that shouted over the status colors.
- The expanded quote block's left accent encodes role (you/claude); status
  stays on the dot + bottom bar, so the two no longer double-encode.
- The waiting badge moved to its own row above the title (short tasks no longer
  wrap) and absorbed the elapsed time; the standalone wait line is gone.
- Elapsed time in the footer gets a clock glyph; branch moved from a duplicated
  footer label to a copyable detail row; dropped the redundant footer status
  word and the turn-at detail.
- The grid caps at 4 columns on wide screens.

## 1.14.0

### Features
- **Fleet dashboard overhaul.** Visual weight now tracks how much a session needs you: a blocked or attention-flagged session keeps its red glow + `WAITING` flag wherever it sits, sorts first within its group, and floats its group to the top — no separate band. A grouping toggle (flat / group / project) in the masthead governs the whole view.
- **`/color` as the card's identity.** `agent_color` fills the whole title row behind the project icon (which stands in for the status dot); the status color moves to a bottom bar so identity and status don't compete.
- **Click-to-expand.** Reveals the full task, the full turn, and a detail block (cwd, turn time, session id) with copy buttons; a dedicated `go →` button focuses the window; the route chip is dropped when it just echoes the project.
- **Full turn on demand (WIP-14).** The plugin persists each turn's full text (`latest_turn_full`) and serves it at `GET /turn/<hash>`; the dashboard fetches it on expand. The bulk `/wip.json` stays single-line (WIP-11), so the cross-session feed stays small.
- **Bound-tack references (WIP-09).** Each bound tack carries its deliverable/link URLs classified `cr` / `issue` / `other`, rendered on the card as links emphasized change request → issue → other.

### Other
- The iTerm2 badge's project/task separator is now ` · ` (middle dot), matching the dashboard's `project · task` separator.

## 1.13.0

### Features
- **`/rename` and `/color` are now beacon signals.** Renaming a session with Claude Code's `/rename` sets its fleet-view **task** — ranked just below an explicit `beacon task`, above the PR-title and branch fallbacks — so the label you reach for naturally shows up across the fleet without a separate `beacon` command. Claude's auto-generated session title becomes the *weakest* task fallback, so a session you never labeled still carries a readable headline. Setting a session's **`/color`** surfaces that color in the fleet view (a swatch on each dashboard card, and an `agent_color` field in `/wip.json`); it does **not** repaint the badge, which stays the ready / busy / blocked status light.

### Fixes
- A Claude session that ends (or is cleared with `beacon clear`) while in a mode state (`paused` / `wrapping` / `done`) now restores its pane background instead of keeping the mode's darkened background.

## 1.12.0

### Features
- Sessions can now be marked **done** — a "session complete, ready to hand off" mode for a session that has finished and delegated (e.g. a retro that stands down). The pane drops to a near-black "powered off" look with a faint power-symbol watermark and a dim purple badge. Set it with `beacon done [note]` or `/beacon:done`. Like `wrap`, it persists until you `resume`/`clear` rather than auto-resuming on the next prompt, and it stays pinned in the fleet view as deliberately set aside.

## 1.11.1

### Other
- The `beacon` skill (and the `wrap` / `pause` commands) are now marked `disable-model-invocation`, dropping their descriptions from every session's always-resident context. Still available via `/`; Claude no longer auto-loads them.

## 1.11.0

### Fixes
- Fleet view no longer shows a raw `<task-notification>` as a session's latest turn. Harness wake-ups (prompts that arrive with a leading angle-bracket tag) are skipped at UserPromptSubmit, so the play-by-play keeps showing the prior real turn; the status still flips to working.
- Clicking a fleet-view card now focuses a session whose window was minimized to the Dock — the window is de-miniaturized before select/activate (a no-op when it wasn't minimized).

### Other
- Trimmed the `beacon` skill's `description` frontmatter to cut the always-resident context cost; the trigger enumeration is dropped in favor of one what/when sentence.

## 1.10.1

### Fixes
- The `↖ web` button's per-session URL handoff file is now rewritten every prompt, so if it is emptied out-of-band (a cache prune, a deleted file, a stale-id clobber) the button heals within one prompt cycle instead of falling back to a search-engine landing while the status chip still shows the deliverable.
- Paths substituted into the iTerm2 profile are now escaped, so a path with special characters no longer breaks the profile.
- The shell-completions freshness reminder is now keyed on `CLAUDE_CODE_SESSION_ID`.

## 1.10.0

### Features
- Paused sessions now dim the whole pane: the background switches to a muted
  purple with a faint `||` watermark, so a parked pane is recognizable at a
  glance — not just by its badge color. The `||` glyph also anchors the session
  on the badge and in the fleet view (`wip` / `watch` / dashboard).
- New `wrapping` mode for a post-work follow-up / retro phase. `beacon wrap
  [note]` (or `/beacon:wrap`) gives the session a muted-green pane background
  and a teal badge. Unlike pause, it persists until you `resume` or the session
  ends.

### Other
- Both modes are delivered by dedicated iTerm2 dynamic profiles
  (`beacon-paused`, `beacon-wrapping`) derived from the base profile at install,
  so a mode can paint a pane background the badge-color signal can't express.

## 1.9.0

Each fleet card now shows what a session is actually doing — not just its project and status — without relying on the agent to label itself.

### Features

- **The fleet view surfaces each session's most recent turn.** Every card now carries a `latest_turn` line — the latest human prompt (`›`) or agent reply (`↳`) — derived automatically from the session's transcript at hook time, so a session that never sets a task label still shows live context. The dashboard ellipsizes the line to the card's width. The task label becomes the durable headline layered over this play-by-play (WIP-11).

### Other

- The test suite is now portable to Windows CI.
- Added end-user docs for the `just demo` fleet and the iTerm2 per-pane views.

## 1.8.0

Makes the fleet view a first-class cross-platform surface, so beacon is useful beyond macOS + iTerm2. The per-pane painting stays iTerm2-only by design; everything below works in any terminal on any OS.

### Cross-platform fleet view

- `beacon watch` now runs on Windows and other terminals that lack POSIX terminal control, via a polling fallback (Ctrl-C to quit).
- Session identity seeds from `CLAUDE_CODE_SESSION_ID` when there's no iTerm pane id or tty, so concurrent windows on Windows / non-iTerm terminals no longer collide on a shared state bucket.

### Reference dashboard

- `beacon serve` now hosts a self-contained reference dashboard at `http://127.0.0.1:8787/` (data still at `/wip.json`). Open it in any browser to see your fleet — no dashboard of your own required. Clone and restyle it, or point your own consumer at the same `/wip.json` + `/focus` + `/forget` contract.

### Standalone labeling

- A `keep-session-labeled` ambient rule (emitted at SessionStart) keeps each session's task label current as the work shifts, so the fleet view has signal without tack or recipes — and defers to tack when a route is bound.

### Tooling

- Cross-platform CI matrix: ubuntu / macOS / Windows × Python 3.9–3.13.
- `just demo` (`dev/demo.py`) seeds an isolated fleet and serves a live simulation, so you can demo beacon without real Claude Code sessions.

Docs and the spec (WIP-10) updated to match.

## 1.7.0

### Features

- **The fleet view shows which tack each session is driving, not just which route.** `wip` records now carry a `tacks` field — the route-qualified tacks the session is bound to (in touch order, last = current focus), each tagged `existing` (work resumed on a tracked tack) or `emerging` (spun up fresh this session). Pairs with tack 0.18.0, which records the binding (WIP-09).
- **`/beacon:pause [note]`** — a dedicated slash command to park a session in one keystroke, instead of `/beacon:beacon pause`. The badge flips to the paused color immediately (CMD-18).

### Performance

- **The `wip` / `serve` fleet scan is dramatically faster on large fleets.** Profiling a 375-session fleet found the dashboard's default-window poll spending most of its time spawning a `git` subprocess per session and re-scanning the whole state directory per session. The scan now reads last-activity in a single pass, memoizes the branch probe per directory, and probes git only for the sessions it actually emits. Default-window scan: ~3.6s → ~0.3s; full history: ~3.6s → ~0.9s. Adds `beacon wip --timing` for profiling (PERF-01..04).

### Fixes

- **Pausing no longer makes a network call or drops your label.** Setting `paused` froze the badge's identity by re-resolving from scratch — which ran a `gh`/`glab` PR-title lookup in that hot path and discarded any active project/task override. It now freezes what the badge already shows (STATE-03).

## 1.6.0

### Features
- **Forget a single stale session from the fleet view.** A long-idle pane lingers in the dashboard — a paused or aged-out session you've moved on from. `prune` sweeps these in bulk by age; the new `forget <hash>` removes one named session now, and the always-on `serve` process exposes it as `POST /forget` so the dashboard's close button on a timed-out card deletes that session's state directly (FORGET-01..03). The route shares the `/focus` access model — loopback bind, DNS-rebind defense, the same origin allowlist — since it's a mutating endpoint. A forgotten session repaints on its next hook event, exactly as after a prune; forgetting a session with no state on disk is a no-op.

## 1.5.0

### Changes
- **Paused sessions stay in the fleet view however long they're parked.** `wip` / `serve` window by last-activity, so a session you set aside for days used to drop out of the snapshot once it aged past the window. A `paused` session is now exempt from the window — parking is deliberate, not idle decay — so it survives past the cutoff where an idle/working session of the same age is dropped (WIP-03). A dashboard can surface these alongside active work (the wip dashboard pins them to the right).

## 1.4.0

### Features
- **The fleet view now carries each project's icon.** beacon finds the project's favicon from its own files (`docs/favicon.svg`, a root `favicon.*`, the web-framework `public/` / `static/` / `app/` roots, `icon.*` / `logo.*`) and exposes it in the `wip` / `serve` payload's new `icon` field, so a dashboard can show the favicon and tell work streams apart at a glance. A local icon is served alongside the payload at `/icon/<hash>`; an `http(s)` icon URL loads from any origin. Point beacon at a custom icon with `beacon icon <path-or-url>`; the field is `null` when a project ships no icon.

## 1.3.0

### Features
- **Exiting a session now clears its badge.** A new `SessionEnd` hook disengages the pane when you leave Claude — the badge text and color clear and the pane looks like an unmanaged terminal again, instead of holding the last-painted color and project. `/clear` and resume are exempt, since those re-engage the same pane immediately. (Exit is best-effort: a hard crash or `kill -9` can't run the hook, so a stale badge there clears on the pane's next beacon-aware action.)

### Changes
- **The `@<project>` wander marker now clears when a session comes home.** The marker is live "where the session is working" context, so it shows only while the session is actively working. At rest — idle, blocked on a prompt, or paused — the task re-resolves from the session's anchor and the marker drops. A session that returns home and finishes its turn clears the marker at Stop, and a session that blocks or ends while away no longer freezes a stale marker into the fleet view.

## 1.2.0

### Changes
- **A wandering session now shows a compact `@<project>` marker plus what it's doing there.** When a session works in another project mid-task, the task slot read the full live path (`beacon: ~/src/getty/cpeterson/ai-sdlc`). It now reads `beacon: @ai-sdlc: <task>`, where the task is your explicit override if set, otherwise the PR title or branch resolved at the wandered location. With nothing to show there, the marker stands alone (`beacon: @ai-sdlc`). The marker now also coexists with an override instead of being suppressed by it.

## 1.1.0

### Features
- **A session that works in another project now shows where it went.** When a Claude session changes directory into a different project mid-task, the badge's task slot surfaces that location (e.g. `beacon: ~/src/ai-sdlc`) as secondary context. Navigating within the session's own project keeps the branch/PR task; an explicit task you've set always wins.

### Fixes
- **The badge project stays anchored to where the session started.** A session that changed directory mid-task used to repaint its badge with the new directory's project, so glancing across panes no longer identified each session by its home project. The badge now pins the project to the directory the session began in, and `beacon show` reports the same project and task the badge paints.
- **A dashboard deployed to a private host can now focus sessions on click.** `POST /focus` extends its origin allowlist (FOCUS-04) with the `focus_origins` list in `~/.config/beacon/config.json` — so a dashboard served off-machine (e.g. GitLab/Cloudflare Pages) clears the browser's CORS preflight without committing the origin to the source. The config is read at serve startup and persists across reinstalls. Reading `wip.json` was already open to any origin; only focus-on-click was gated.

## 1.0.0

### Breaking Changes
- **The iTerm2 marginalia overlay is retired in favor of the externalized fleet view.** Its raster-to-file rendering, permission grants, behind-text layering, and color-banding made it a poor surface. Removed with it: the `note` / background-image / clear-screen subcommands, the `_compose.py` helper and the Pillow dependency, the four per-state dynamic profiles and the `!` / `?` watermark assets, and the exclusive-configuration / default-profile / background-image-trust machinery. beacon no longer issues any `defaults write` — badge and tab color paint via OSC on a single base profile, activated by a runtime `set-profile`.

### Features
- **Click a session in the fleet dashboard to raise its iTerm2 window** (FOCUS-01..04). `beacon-iterm focus <id>` brings the window forward; the iTerm2 session GUID is recorded at SessionStart and exposed as a per-session `focusable` flag in `wip.json` without leaking the GUID. `serve` adds `POST /focus`, which resolves the hash to the handle server-side behind a loopback `Host` check and an `Origin` allowlist; `GET /wip.json` keeps its permissive CORS.
- **The session description is now recall context in the fleet view** rather than paint on the pane — it survives the overlay's removal.
- **`task` is part of the `wip.json` session payload** (WIP-01). One of beacon's three core signals (project / task / status), it was previously dropped from the payload, so the fleet view and the goals/WIP dashboard couldn't show what each session was working on. Sourced from the last-rendered snapshot, preferring a fresher explicit override.

## 0.23.0

### Features
- **The fleet dashboard (`wip` / `watch` / `serve`) now works in any terminal.** It reads across all sessions and paints no pane, so it no longer depends on iTerm2 — only the per-pane painting (badge, status bar, overlay) needs macOS + iTerm2.
- **`beacon install` is terminal-aware.** It detects iTerm2 (macOS + `iTerm.app`); when absent it installs only the CLI wrapper and completions and points you at the fleet dashboard, skipping the iTerm2-only setup instead of attempting it.
- **New `beacon serve install|uninstall|status`.** Keeps `serve` always running under a launchd agent (macOS) or systemd user unit (Linux) so an external dashboard has a stable endpoint that restarts on crash. Opt-in — `install` doesn't start it.

### Fixes
- **`beacon install` no longer reports success for an iTerm2 preference it couldn't set.** On a non-macOS box the `PerPaneBackgroundImage` write silently no-ops; install now reports the failure instead of printing a checkmark.

### Other
- Repositioned the spec and docs around beacon's two surfaces — the terminal-agnostic fleet view and the iTerm2 per-pane adapter. `docs/README.md` gains a Fleet dashboard section and an opt-in always-on service section.

## 0.22.0

### Breaking Changes
- **Bare `beacon` (no arguments) now prints the usage text** (to stderr, exit 1) instead of running `show` (CMD-17). Run `beacon show` for the resolved signal state. The `/beacon:beacon` slash command is unaffected — its shim passes `show` when given no arguments.

### Features
- **`beacon-iterm` with no arguments now prints the full help text** (to stderr, exit 1) instead of argparse's one-line "cmd required" error (CLI-16). `--help` / `-h` behavior is unchanged (full help to stdout, exit 0).
- **`beacon help` and `beacon-iterm help`** now work as aliases for `--help` (CMD-17, CLI-16).

## 0.21.0

### Features
- New `beacon watch`: a live, person-facing work-stream view. Sessions form a recency feed (most-recently-active on top), refreshing in place without the flicker of `watch beacon wip`. Press `q` to quit. The tack route is shown only when it carries signal the project name doesn't.
- `beacon` now respects standard color controls so output keeps its color through a pipe: a global `--color=auto|always|never` flag and the `NO_COLOR` / `FORCE_COLOR` / `CLICOLOR_FORCE` environment variables. This makes `watch --color 'beacon --color=always wip'` render in color, where `watch beacon wip` previously came through uncolored.

### Fixes
- Sessions started without an iTerm pane id (auto-spawned tabs, `claude --resume`, non-iTerm terminals) no longer share a single state bucket and cross-wire each other's project and URL.

### Other
- Refreshed STATUS.md to the current spec audit and trimmed an obsolete `tack find <pwd>` clause from the spec.

## 0.20.0

### Features
- `beacon wip` surfaces active work streams across every session, not just the current pane. It enumerates each session's stored state (status, anchored project/cwd, marginalia description, last activity, Claude session id) and prints a table grouped by tack route. Route correlation is authoritative-first: the Claude session id matched against tack's `sessions[]` block, then `.tack` pin, branch, or project name (whole or last path segment, so `owner/repo` maps to route `repo`). `--json` emits a structured snapshot; `--since <ISO-8601>` windows to a given time (e.g. the prior dashboard refresh); with no flag it defaults to the last 24h, and `--all` returns the full history.
- `beacon serve` exposes the same snapshot over `http://127.0.0.1:8787/wip.json` (loopback only, CORS-open, optional `?since=`) so a locally-opened dashboard can poll for near-realtime work-stream signal. The goals dashboard's "wip" tab consumes this to highlight which planned routes have a live session attached right now, falling back to a baked snapshot when the service isn't reachable.
- `--since` accepts a duration (`1d`, `2h`, `30m`) as well as an ISO-8601 timestamp.
- `beacon prune [--since 30d]` (alias `--keep`) garbage-collects per-session state for long-idle panes (including project-less sessions that never reached SessionStart), keeping the current session and everything active within the window.

### Other
- `wip` / `serve` / `prune` are read-only/maintenance surfaces — they paint no iTerm2 surface. New spec section §3.8 (WIP-01..06); CLAUDE.md and README updated; `tests/test_wip.py` added.

## 0.19.0

### Features
- The session note card is now a compact tile in the top-right corner instead of a tall panel down the side of the pane. It covers far less of the terminal and gets overwritten by output much less often. A longer note grows the card (up to ~2x its resting height) and shrinks its text to fit before truncating, so short notes stay small and long ones stay readable.

### Fixes
- `beacon pause` with no note now shows the paused gray badge and tab color — previously a note-less pause painted nothing (it tried to switch to a profile that doesn't exist).
- Clearing the note while a pane stays paused (e.g. `pause "x"` then `pause`) no longer leaves the old card on screen.
- A pane showing an idle-prompt notification alongside a note now reads red, matching its state, instead of the paused gray.
- Project / branch / URL chips stay pinned to where the session started instead of drifting with the working directory mid-session.

### Other
- The note card no longer shows a timestamp (low signal, and it went stale while a pane sat paused).
- Spec (OVERLAY-01, §4.1, CLI-05), CLAUDE.md, and tests updated; the card's type sizes and padding now scale from the card height.

## 0.18.1

### Fixes
- Marginalia card no longer renders faintly when a description is set while the session is also showing a permission/idle prompt. The `beacon-blocked` and `beacon-blocked-idle` profiles were forcing `Blend: 0.20` for the red `!` / `?` watermark; that dilution bled into the card painted on top via OSC. Blend is now `1.0` across every state profile, and the watermark PNGs carry their pre-faded alpha so they still read as a quiet backdrop.

### Migration
- Re-run `python3 scripts/beacon install` after upgrading so iTerm2 picks up the updated `beacon-blocked` / `beacon-blocked-idle` profile templates (without re-install, the cached profiles keep `Blend: 0.20`).

## 0.18.0

### Features
- Overlay descriptions now support bulleted lists (`* item` per line) and strikethrough (`~text~`), in addition to the existing `*bold*` and `_italic_` markers.

### Fixes
- Strikethrough renders as a single continuous line across struck words instead of one segment per word — no more visible gaps or wobble.
- Long overlay text no longer overflows past the card's bottom or right edge. Content past the card truncates with an ellipsis. Body text also stays at a consistent size across notes (previously the font shrank to fit, making the same overlay look different sizes for different inputs).

### Other
- Added `just preview` — renders an HTML gallery of representative overlays at `.preview/index.html` for visual iteration without launching iTerm2.
- Added 67 tests covering the overlay compositor (parser, block splitting, layout, strike-run merging, oversized-word truncation, smoke render).
- Spec updates: OVERLAY-01 and CLI-05 enumerate the expanded markdown subset; §6.11 names a daemon-backed headless renderer as the eventual escape hatch.

## 0.17.0

### Breaking Changes
- The `stage` signal is gone. `beacon stage …`, `beacon set stage …`, `beacon signal stage …`, and `beacon clear stage` no longer exist and fail with an argparse error. Stage never had a render surface (it only appeared in `beacon show`); folding the visible behaviors into `status` simplified the model.
- The `signal` subcommand is removed — it existed solely to feed `stage` from the skill. The skill no longer signals stage transitions on plan-mode entry or code-review requests.
- `beacon-iterm note` now requires a label: `note <label> <text>` (the uppercase status — `PAUSED`, `WAITING`, etc.). Direct callers must update; the plugin's internal callers are updated in this release.

### Features
- `status` accepts a free-text description that drives a marginalia card on the right edge of the pane: `beacon status waiting "bg data refresh ~30 min"` parks the card with that note while the badge flips to red. Useful for "I'm waiting on something async, not Claude."
- `paused` is now a fourth `status` value. The marginalia card renders for any user-set status with a description, not just paused; the card label tracks the live status (`PAUSED`, `WAITING`, …).
- `pause [<note>]` stays as shorthand for `status paused [<note>]` — muscle memory unaffected. Auto-resume on prompt submission fires only for `paused`; other user-set statuses survive the next turn.

### Other
- iTerm2 notification-center delivery and terminal-generated alerts are disabled on the beacon profile (`BM Growl: false`, `Send Terminal Generated Alerts: false`). They duplicated the badge color signal and could transiently overlay the badge.
- Spec rewrite: §1.3 (stage values) and §1.5 (stage vs status) deleted; §3.5 PAUSE renamed to STATE covering user-set status + description. `CMD-10` (`signal`) gone; `STATE-*` IDs replace `PAUSE-*`.
- Hook handlers no longer promote stage on `Write` / `Edit` / `Bash` / `ExitPlanMode`. The deploy regex is gone.

### Migration
- Re-run `python3 scripts/beacon install` after upgrading. The profile template gained `BM Growl: false` and `Send Terminal Generated Alerts: false` — without re-install the existing profile still fires Claude Code's permission/idle alerts as duplicate notifications.
- If any external scripts call `beacon stage …`, `beacon signal stage …`, or `beacon-iterm note <text>` (the single-arg form), update them. The arg surface changed.

## 0.16.0

### Features
- The pause overlay is now a left-anchored Dracula marginalia card — uppercase `PAUSED` label in pink, timestamp, short editorial rule, and your note body in foreground type — replacing the centered yellow post-it. The right side of the pane stays transparent so terminal content reads when you return.
- `/beacon pause "<note>"` no longer co-opts the badge's task slot. The note carries recall context for the overlay only; the badge's task slot keeps whatever PAUSE-01 snapshotted (PR title, branch, override). Long notes that previously overflowed the badge now stay where they belong.
- The pane's visible viewport is cleared before the overlay paints, so TUI content (Claude Code's chips, input, transcript) stops fighting the card for legibility. Scrollback is preserved — scroll up to see pre-pause history.

### Other
- New CLI subcommand `beacon-iterm clear-screen` (CLI-15) emits the CSI `2J` + `H` escapes used by the pause render path.
- Spec/doc sweep: "post-it overlay" → "pause overlay" / "marginalia card" across CLAUDE.md, STATUS.md, docs, shell snippet.

### Migration
- Run `python3 scripts/beacon install` after upgrading to land the `Blend: 1.0` setting on the base profile. Without it, the new card renders diluted against the terminal bg.

## 0.15.2

### Fixes
- Clicking the `↗ code` status-bar chip no longer leaks VS Code's "To read from stdin, append '-'" hint into the active pane (which previously landed in Claude's prompt input). The chip now opens the cwd via macOS `open -a "Visual Studio Code"` instead of the `code` CLI.

## 0.15.1

### Fixes
- Branch and URL status-bar chips now refresh during a Claude session. Previously, the chips were painted once at SessionStart and stayed frozen for the rest of the session — so a branch the agent created mid-turn, or a tack deliverable pinned mid-session, was invisible until you returned to a shell prompt. The plugin now re-resolves the chip slots from the session's anchor cwd at the end of each turn.

## 0.15.0

### Features
- The red blocked-state badge now distinguishes two prompt kinds via watermark: `!` for a permission prompt (Claude is hard-blocked on a human answer) and `?` for an idle prompt (softer — often spurious during background tools). Both still paint the badge red; the watermark lets a scan across panes separate "must answer now" from "might want to look."

### Fixes
- Idle prompts again paint the badge red. 0.14.0 narrowed the Notification matcher to `permission_prompt` only to suppress false positives during `run_in_background` work — but `permission_prompt` alone fires rarely enough that the red state was effectively gone. The matcher is back to catching both, with the `?` vs `!` watermark carrying the urgency distinction instead.

### Migration
- Run `python3 scripts/beacon install` after upgrading to land the new `beacon-blocked-idle` dynamic profile and its `?` watermark image.

## 0.14.0

### Features
- Badge labels are now shorter and consistent. Previously, projects with a `name` field in `package.json` / `Cargo.toml` / `pyproject.toml` showed the short name (`beacon`, `tack`) while everything else showed the full owner/repo path (`chris-peterson/beacon`). The badge now always renders the repo basename. The owner-bearing identity is still available as the `gh:owner/repo` status-bar chip for disambiguation; with `beacon set project <label>` available for custom overrides, the short form is the better default for the badge.

### Fixes
- The red `!` blocked-state badge no longer fires during background work. Previously, beacon caught both `idle_prompt` and `permission_prompt` Notifications. But Claude Code emits `idle_prompt` whenever the agent is idle — including while a `run_in_background` Bash is still in flight (e.g. `/wip`'s background refresh phase), even though no permission dialog is open. The matcher is now narrowed to `permission_prompt`, so red `!` reliably means "a permission dialog needs your answer."

### Other
- Spec entries PROV-01 and §6.2's badge-render example synced to match the new basename behavior.

## 0.13.0

### Breaking Changes
- The drift detection feature is removed. The badge no longer appends a `:<basename>` suffix when Claude's Bash subprocess wanders out of the SessionStart anchor, and there is no longer a separate cyan "drifted" badge color or `beacon-drifted` dynamic profile. In practice, the feature was firing on cases the suppression logic was supposed to catch (e.g. badges reading `chris-peterson/beacon:beacon` or `cpeterson/ai-sdlc:ai-sdlc`), and the cost of fixing it didn't justify the at-a-glance signal it was meant to provide.

### Migration
- Run `python3 scripts/beacon install` after upgrading. The install step rewrites the dynamic profile JSONs (three states now: ready / busy / blocked) and deletes the leftover `beacon-drifted.json` from `~/Library/Application Support/iTerm2/DynamicProfiles/` so it stops showing up in the iTerm2 profile picker.
- The `beacon_project_drift` iTerm user variable is no longer published. If you reference it in a custom iTerm profile or status-bar configuration, remove the reference.

## 0.12.0

### Features
- The badge now shows the resolved task as a `: <task>` suffix after the project (e.g. `beacon: render-on-badge`). When no task is set, the badge shows project alone — the slot self-collapses. Previously, `beacon set task` only updated `beacon show`; the visible badge stayed on project alone, leaving users without an at-a-glance signal of *what* they're working on within a given project.

### Migration
- Run `python3 scripts/beacon install` after upgrading to land the new dynamic profile JSON with the updated badge format. Existing iTerm panes pick up the format hot from the dynamic-profile reload; new panes pick it up via the refreshed shell snippet.

## 0.11.0

### Features
- The URL chain now probes `gh` (github hosts) or `glab` (gitlab hosts) for an open PR/MR on the current branch when tack has no link for it. The `↖ web` button lands on your MR/PR even when you haven't run `tack link add` — the common workflow gap. Soft integration: missing CLI or unrecognized forge host skips silently to the existing branch / project fallbacks.

## 0.10.0

### Features
- Freshly opened terminals stay unmanaged until a beacon-aware action engages them — no more giant badge spanning the pane the moment you open a tab. The badge only appears once you run `claude`, `beacon ...`, or invoke a beacon slash command in that pane. `beacon clear` fully disengages a pane, returning it to the same calm state as a fresh tab.
- Badge color is now translucent, so terminal content shows through. Mission Control / Exposé legibility is preserved while normal-zoom readability is no longer compromised. Badge sizing also shrinks (Max Height halved) so long repo names occupy less of the pane.
- The blocked state ships an `!` watermark behind the terminal — "Claude needs me" is now parseable in Mission Control where badge text isn't.
- `beacon set project <label>` overrides now stick in interactive shells. The shell snippet no longer republishes a cwd-derived value on every prompt and clobbers your explicit label.

### Fixes
- The `my-proj:my-proj` drift false positive — drift detection no longer adds a `:<basename>` suffix when the suffix would just repeat the anchor's last segment.
- `_publish_drift` self-heals when no SessionStart anchor exists: adopts the first observation as the anchor instead of running away with `:<basename>` suffixes on every PostToolUse Bash.
- `set project` overrides now propagate to the badge text (previously they updated `beacon show` but the badge stayed on the SessionStart anchor value).
- `skills/beacon/SKILL.md` previously told agents to use `beacon set task` for "badge labeling at session start", but task isn't on the badge. Replaced with a surface map and explicit "use set project" guidance.

### Other
- Spec restructured around an engagement precondition. New requirements: BADGE-13 (sizing + opacity), BADGE-14 (engagement-gated badging), BADGE-15 (state-driven background image), CLI-14 (`set-profile`), HOOK-09a (anchor self-healing), HOOK-09b (no-op drift suppression). The badge color mechanism pivoted from per-session OSC `SetColors=badge=` to one dynamic profile per state (`beacon-ready` / `-busy` / `-blocked` / `-drifted`), switched via `OSC SetProfile=`. Pause stays as an OSC overlay since its image is per-note.
- `iterm/images/blocked.png` bundled with the plugin.
- 22 unit tests (11 new this release) covering profile switching, OSC overlay for pause, engagement marker, first-render publish, and drift no-op condition.

### Migration
- Run `python3 scripts/beacon install` after upgrading — the new state profiles need to land in `~/Library/Application Support/iTerm2/DynamicProfiles/`.
- If you previously had `beacon-flicker-test.json` from manual testing in your DynamicProfiles dir, remove it.

## 0.9.0

### Features
- The status bar's project chip now collapses known forge hosts: `github.com/owner/repo` shows as `gh:owner/repo`, GitLab as `gl:`, Bitbucket as `bb:`. Unknown hosts pass through as `host/owner/repo`.
- When tack is tracking a deliverable for the current branch (or you've set a URL override pointing at a forge issue/PR/MR), the project chip appends `#42` for issues/PRs or `!17` for GitLab merge requests, e.g. `gh:chris-peterson/beacon#42`. The chip answers "what am I working on", not just "what repo am I in."
- Status bar reshaped: `↖ web · project │ branch · ↗ code`. The branch chip now sits next to the `↗ code` action so each end pairs an action with the data it acts on. The cwd chip is gone — the project chip now carries the spatial-context job alone.
- Badge renders the full nested-group path. `acmecorp/platform/auth-svc` shows in full instead of being collapsed to `acmecorp/.../auth-svc`. With the cwd chip gone, the badge owns spatial context and doesn't need to truncate.
- Branch chip drops the leading `@` sigil on the synced state — color (green / orange / dim gray) already carries the synced / diverged / untracked signal, and the bare name reads cleaner. Diverged (`↑3 main`) and untracked are unchanged.
- Drift hint format simplified from ` (@ <basename>)` to `:<basename>`, e.g. `chris-peterson/beacon:ai-sdlc`. The colon separator reads as a path tail and keeps the anchor in the same spatial column when scanning panes vertically.

### Fixes
- Badge sizing now uses iTerm2's Badge Max Width / Max Height knobs rather than a font-size suffix — more consistent across panes of different sizes.

### Other
- The docsify homepage (`docs/README.md`) gained a "Tack integration (optional)" section describing the soft dependency on tack and the `_beacon_resolve_url()` override hook for users wanting Linear / Jira / GitHub Issues / a custom provider.
- Root `README.md` trimmed to maintainer-focused content (clone-from-source, dependencies, repo layout, architecture). End-user install / verify / usage / upgrade / uninstall now live only on the docs site.
- Spec dropped PROV-01a (the nested-group abbreviation rule); PROV-01 now specifies the full `owner/.../repo` path.

## 0.8.0

### Features
- Project names with multi-level subgroups now display as `<top>/.../<repo>` instead of silently dropping intermediate segments. A remote at `acmecorp/platform/auth-svc` renders as `acmecorp/.../auth-svc`, so the displayed path is unambiguous. Two-segment paths render as before.
- Drift hint changed from ` (<basename>)` to ` (@ <basename>)` and now uses Dracula cyan. The `@` prefix reads as "currently at" — a transient location Claude has stepped into — so drift is visually distinct from the badge anchor identity.
- Freshly-sourced shell integration paints the badge calm green (`ready`) immediately, so a fresh pane doesn't inherit a stale red/orange color from whatever Claude session was last active there. Claude's hooks repaint to `busy` / `blocked` on the next turn as before.
- All iTerm2 surfaces beacon paints (badge, tab color, status-bar chips) now share a single Dracula palette with a strict one-role-per-hue rule: green/orange/red is the calm/working/blocked traffic light, cyan is reserved exclusively for drift, comment-gray is de-emphasis, and pink is the single "interactive" accent on action chips.

### Fixes
- Directories outside any recognized project (no `.git`, `package.json`, etc. before `$HOME`) now render consistently across every beacon surface. Previously `beacon show`, `beacon json`, and the in-Claude badge color path returned a literal `?` while the SessionStart anchor and shell integration showed the abbreviated cwd; now every surface uses the abbreviated cwd.

### Other
- Removed the `alias` feature from the spec and README. It was documented but never implemented, and no user had needed it; README examples referencing project-name shortening have been deleted.
- Internal: `docs/spec.md` was reconciled with the shipping code so every CLI subcommand and SKILL behavior has a requirement ID. New `STATUS.md` tracks per-requirement coverage.
- `.claude/` is now gitignored.

## 0.7.0

### Changes
- `beacon` is now exposed via a real wrapper at `~/.local/bin/beacon` (installed by `beacon install-cli`) rather than a zsh alias. The freshness check in `hooks/cli-freshness.sh` runs from non-interactive shells where aliases don't apply, so the prior alias-based setup silently bypassed drift detection. The wrapper matches the pattern used by tack and logbook. Run `/beacon:beacon install` after upgrading; `install` now drops the wrapper as part of its bootstrap, and `/beacon:beacon install-cli` refreshes just the wrapper for subsequent upgrades.

## 0.6.0

### Changes
- Badge now stays calm (green) between turns. Red is reserved for moments when Claude is actually blocked on you (permission or idle prompt), so across a wall of panes a red badge always means "this one needs me right now" — not "this one is between turns." Dock bounces follow the same rule and no longer fire on turn-end.
- Badge font reduced to `Menlo-Bold 10` so the badge text competes less with terminal content while staying readable in Mission Control.

### Fixes
- When Claude starts in a directory that isn't part of any recognized project (no `.git`, `package.json`, etc. before `$HOME`), the badge now shows the abbreviated cwd (e.g. `~/scratch`) instead of going empty. Drift hints render as `~/scratch (foo)` instead of a stranded `(foo)`.

## 0.5.0

### Features
- `SessionStart` hook now checks CLI wrapper freshness on every Claude Code session start, regardless of which surface invokes the CLI. Previously the freshness check lived in the `beacon` skill, which only fired on skill invocation — consumers calling `beacon` directly (other skills, shell, tooling) bypassed it. The hook compares `beacon --version` against `plugin.json#version` and emits an `additionalContext` nudge when they differ; silent on match, silent when the CLI isn't on PATH, never blocks the session.

## 0.4.0

### Features
- `beacon --version` (and `-v`) now reports the installed plugin version, sourced from `.claude-plugin/plugin.json`.
- The beacon skill now checks CLI freshness before its first invocation in a session. If the shell `beacon` wrapper (from `/beacon:beacon install`) is older than the running plugin, it surfaces a one-line note and offers to refresh.

### Other
- Documented the auto-update path for end users in the Upgrade section of the README.

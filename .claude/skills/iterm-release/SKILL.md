---
name: iterm-release
description: Read a new iTerm2 release against the surfaces beacon renders through (layout prefs, dynamic profile keys, OSC controls, profile loading, Apple Events) and say whether beacon is affected. Use when iTerm2 ships a release, when the user asks whether an iTerm2 update breaks beacon, or when `just iterm-release` reports releases to read.
---

# Read an iTerm2 release

`dev/iterm-release.py` (`just iterm-release`) fetches the iTerm2 clone, lands it
on the newest release tag, and scans the diff since the version recorded in
`dev/iterm-reviewed.json` for the symbols beacon depends on. The scan is a
filter, not a verdict. This skill is the read that follows it.

## 1. Run the scan

Run the script, not the recipe: the recipe's `-` prefix turns every exit into
0, and the exit is how this step reads the result.

```bash
python3 dev/iterm-release.py
```

- Exit 0 with "has been read": nothing to do. Report that and stop.
- Exit 2: a precondition failed (no clone, dirty clone, no recorded version).
  Surface the message as printed; don't work around it.
- Exit 1: releases are pending. Note the range (`vA..vB`), the clone path, and
  every surface marked `✗` with the files it names.

On the first run the clone moves to the newest tag. If a re-run is needed, pass
`--no-checkout`.

## 2. Read the notes

For each pending release, read `docs/notes-<version>.txt` in the clone. When
the report says `(no notes file)`, the release's notes are still accumulating
in `docs/notes-<major>.<minor>.txt`: read its diff over the range instead.

```bash
git -C <clone> diff <range> -- docs/notes-<major>.<minor>.txt
```

## 3. Read the commits

```bash
git -C <clone> log --oneline --no-merges <range>
```

Pick out every commit that could touch a surface beacon paints (AGENTS.md,
"Surfaces beacon paints"): tab color and label, window title and session name,
status bar, badge, dynamic profiles and their loading, OSC 8 links, `SetUserVar`
/ `SetColors` / `SetProfile`, AppleScript `select` / `activate`, tab-bar layout.
For each, `git -C <clone> show --stat <sha>` and read the message.

Then check the one class the scan can't judge from a hit alone: a changed
default. Look at the range's diff of the preference files and compare any
`DEFINE_*` second argument or `iTermPreferences.m` default against what
`RECOMMENDED_LAYOUT` in `bin/beacon-iterm` is tuned for.

```bash
git -C <clone> diff <range> -- sources/Settings/iTermAdvancedSettingsModel.m sources/Settings/iTermPreferences.m
```

For each `✗` surface from step 1, read the hunk that matched and decide whether
it changes what beacon writes or what iTerm2 does with it.

## 4. Report

Lead with the verdict: affected or not. Then a table of the commits that touch
a beacon surface only (sha, what changed, what it means for beacon), and one
line naming the areas the rest touch. Where beacon is affected, name the file
and requirement ID the fix belongs in and offer it as separate work.

## 5. Record the review

Only after the user agrees with the read:

```bash
python3 dev/iterm-release.py --ack
```

That rewrites `dev/iterm-reviewed.json`; commit it through `/anchor:commit`.

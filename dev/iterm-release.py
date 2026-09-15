#!/usr/bin/env python3
"""Update the iTerm2 clone to its latest release and report what beacon must read.

beacon renders through iTerm2's own surfaces — app-wide layout preferences,
dynamic profile keys, OSC controls, the AppleScript dictionary — and none of
them are versioned APIs. A release that renames a key or changes a default
breaks a surface silently, so each one has to be read against the set beacon
depends on.

The symbol set is derived from beacon's own sources rather than restated here:
a key beacon stops reading leaves the watch list on the same edit.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECORD = REPO / "dev" / "iterm-reviewed.json"
DEFAULT_CLONE = Path.home() / "src" / "github" / "gnachman" / "iTerm2"

# A release tag, as distinct from the beta and nightly tags that share the prefix.
RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class Failure(Exception):
    pass


def git(clone: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(clone), *args],
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise Failure(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


# --- the surfaces, read out of beacon's own sources -------------------------

def _load_cli():
    path = REPO / "bin" / "beacon-iterm"
    loader = importlib.machinery.SourceFileLoader("beacon_iterm", str(path))
    spec = importlib.util.spec_from_loader("beacon_iterm", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _layout_keys() -> list[str]:
    cli = _load_cli()
    keys = {s["key"] for s in cli.RECOMMENDED_LAYOUT}
    for family in cli.RESET_FAMILIES:
        keys.update(family["keys"])
    return sorted(keys)


def _profile_keys() -> list[str]:
    template = json.loads((REPO / "iterm" / "profile.json.template").read_text())
    keys = set()
    for profile in template.get("Profiles", []):
        keys.update(profile)
    # The mode profiles add these to the template at render time (RENDER-05).
    keys.update({"Background Image Location", "Background Image Mode"})
    return sorted(keys)


def surfaces() -> list[dict]:
    return [
        {"name": "Layout preferences",
         "why": "the app-wide keys `beacon layout` audits and `reset-layout` "
                "clears (CLI-18, CLI-20)",
         "match": "prefkey", "symbols": _layout_keys()},
        {"name": "Dynamic profile keys",
         "why": "what beacon writes into each profile it installs "
                "(STATUS-BAR-01, RENDER-05, TITLE-05)",
         "match": "quoted", "symbols": _profile_keys()},
        {"name": "OSC controls",
         "why": "the escape sequences every painted surface goes through",
         "match": "word",
         "symbols": ["SetProfile", "SetColors", "SetUserVar", "SetBadgeFormat"]},
        {"name": "Dynamic profile loading",
         "why": "whether iTerm2 still loads the files beacon writes, and the "
                "migration `remigrate-profiles` re-arms (CLI-19, DIAG-05)",
         "match": "quoted",
         "symbols": ["Is Dynamic Profile", "Dynamic Profile Filename",
                     "NoSyncMigratedDynamicProfileTagToFlag"],
         "paths": ["sources/Settings/Profiles/iTermDynamicProfileManager.m"]},
        {"name": "Apple Events",
         "why": "the dictionary `set-name` and `focus` are written against "
                "(CLI-15, CLI-17)",
         "paths": ["iTerm2.sdef"]},
    ]


# Generated artifacts and vendored binaries carry every symbol at once, so a
# match in one says nothing about iTerm2's behavior. The release notes are
# prose, and the pending releases already list them by name.
NOISE = re.compile(
    r"^(api/library/python/|ThirdParty/|docs/notes-)"
    r"|\.dSYM/|\.swiftinterface$|\.xcodeproj/"
)


# --- clone state ------------------------------------------------------------

def releases(clone: Path) -> list[tuple[tuple[int, int, int], str, str]]:
    out = git(clone, "for-each-ref", "--format=%(refname:short)\t%(creatordate:short)",
              "refs/tags")
    found = []
    for line in out.splitlines():
        tag, _, date = line.partition("\t")
        m = RELEASE_TAG.match(tag)
        if m:
            found.append((tuple(int(g) for g in m.groups()), tag, date))
    return sorted(found)


def reviewed() -> str | None:
    if not RECORD.exists():
        return None
    return json.loads(RECORD.read_text()).get("version") or None


def record(version: str) -> None:
    RECORD.write_text(json.dumps(
        {"version": version,
         "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        indent=2) + "\n")


def update_clone(clone: Path, tag: str) -> str:
    """Fetch, then land the clone on `tag`. Returns what it did."""
    git(clone, "fetch", "--tags", "--quiet", "origin")
    if git(clone, "rev-parse", "HEAD") == git(clone, "rev-parse", f"{tag}^{{commit}}"):
        return f"already on {tag}"
    if git(clone, "status", "--porcelain"):
        raise Failure(
            f"{clone} has uncommitted changes — not checking out {tag}. "
            "Clean the worktree, or pass --no-checkout to read without moving it."
        )
    was = git(clone, "rev-parse", "--short", "HEAD")
    git(clone, "checkout", "--quiet", tag)
    return f"checked out {tag} (was {was})"


# --- the scan ---------------------------------------------------------------

def _pattern(symbol: str, mode: str) -> re.Pattern:
    escaped = re.escape(symbol)
    if mode == "prefkey":
        # An app-wide preference reaches iTerm2 two ways. iTermPreferences.m
        # spells it as a string literal (`@"LeftTabBarWidth"`); an advanced
        # setting never appears as one, and is declared by identifier with the
        # defaults key being that identifier capitalized
        # (`DEFINE_FLOAT(compactMinimalTabBarHeight, 38, …)` →
        # `CompactMinimalTabBarHeight`), where the 38 is the default beacon's
        # recommendation is tuned against. Anchoring to the DEFINE_ macro is
        # what keeps `statusBarHeight` the local variable out of it.
        lower = re.escape(symbol[0].lower() + symbol[1:])
        return re.compile(rf'"{escaped}"|\bDEFINE_\w+\(\s*{lower}\b')
    if mode == "quoted":
        # A profile key is only ever a literal (`@"Badge Text"`). Bare-word
        # matching instead reports every `Name` and `Guid` in the codebase.
        return re.compile(rf'"{escaped}"')
    return re.compile(rf"\b{escaped}\b")


def scan(clone: Path, rng: str, surface: dict) -> dict:
    """Which of this surface's symbols and paths the range actually changes."""
    hits: dict[str, set[str]] = {}

    if surface.get("symbols"):
        patterns = [(s, _pattern(s, surface.get("match", "word")))
                    for s in surface["symbols"]]
        # --unified=0 so a symbol only counts where the range edits its line,
        # not where it happens to sit near an unrelated edit.
        diff = git(clone, "diff", "--unified=0", rng)
        current = None
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                current = line[6:]
                if NOISE.search(current):
                    current = None
            elif line[:1] in "+-" and not line.startswith(("+++", "---")) and current:
                for symbol, pattern in patterns:
                    if pattern.search(line):
                        hits.setdefault(symbol, set()).add(current)

    changed_paths = set(git(clone, "diff", "--name-only", rng).splitlines())
    for path in surface.get("paths", []):
        if path in changed_paths:
            hits.setdefault(path, set())

    return {name: sorted(files) for name, files in sorted(hits.items())}


# --- report -----------------------------------------------------------------

def report(clone: Path, last: str, latest: str, pending: list, moved: str,
           results: list[tuple[dict, dict]]) -> None:
    rng = f"{last}..{latest}"
    print(f"iTerm2 {last} → {latest} — {len(pending)} release"
          f"{'' if len(pending) == 1 else 's'} to read  ({moved})")
    print()
    for _, tag, date in pending:
        version = tag.lstrip("v")
        notes = clone / "docs" / f"notes-{version}.txt"
        where = notes.relative_to(clone) if notes.exists() else "(no notes file)"
        print(f"  {tag:<10} {date}   {where}")
    print()

    print("Surfaces beacon renders through")
    for surface, hits in results:
        mark = "✗" if hits else "✓"
        print(f"  {mark} {surface['name']}")
        if not hits:
            continue
        print(f"      └ {surface['why']}")
        for name, files in hits.items():
            print(f"      {name}")
            for path in files:
                print(f"          {path}")
        print()
    print()

    commits = git(clone, "rev-list", "--count", "--no-merges", rng)
    print(f"{commits} commits. Read them:")
    print(f"  git -C {clone} log --oneline --no-merges {rng}")
    print("Record the review once you have:  just iterm-release --ack")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Update the iTerm2 clone to its latest release and report "
                    "what changed on the surfaces beacon renders through.")
    p.add_argument("--clone", type=Path,
                   default=Path(os.environ.get("ITERM2_SRC") or DEFAULT_CLONE),
                   help="the iTerm2 checkout (default: $ITERM2_SRC, else "
                        f"{DEFAULT_CLONE})")
    p.add_argument("--no-checkout", action="store_true",
                   help="fetch and report without moving the clone's HEAD")
    p.add_argument("--ack", action="store_true",
                   help="record the latest release as read")
    p.add_argument("--since", metavar="VERSION",
                   help="read from this version instead of the recorded one")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    clone = args.clone.expanduser()
    if not (clone / ".git").exists():
        raise Failure(
            f"no iTerm2 checkout at {clone}. Clone it, or point --clone / "
            "$ITERM2_SRC at one: git clone https://github.com/gnachman/iTerm2"
        )

    git(clone, "fetch", "--tags", "--quiet", "origin")
    found = releases(clone)
    if not found:
        raise Failure(f"{clone} has no release tags — is it a full clone?")
    latest = found[-1][1]

    last = args.since or reviewed()
    if last and not last.startswith("v"):
        last = f"v{last}"
    if last is None:
        raise Failure(
            f"no reviewed version recorded in {RECORD.relative_to(REPO)}. "
            f"Seed it with --since <version>, or --ack to start from {latest}."
        )

    known = {tag for _, tag, _ in found}
    if last not in known:
        raise Failure(f"{last} is not a release tag in {clone}")

    last_key = next(key for key, tag, _ in found if tag == last)
    pending = [r for r in found if r[0] > last_key]

    if args.ack:
        record(latest.lstrip("v"))
        print(f"Recorded iTerm2 {latest.lstrip('v')} as read.")
        return 0

    if not pending:
        print(f"iTerm2 {latest} is the latest release, and it has been read.")
        return 0

    moved = "left where it was" if args.no_checkout else update_clone(clone, latest)
    rng = f"{last}..{latest}"
    results = [(s, scan(clone, rng, s)) for s in surfaces()]

    if args.json:
        print(json.dumps({
            "reviewed": last.lstrip("v"),
            "latest": latest.lstrip("v"),
            "pending": [tag.lstrip("v") for _, tag, _ in pending],
            "clone": str(clone),
            "surfaces": [{"name": s["name"], "hits": h} for s, h in results],
        }, indent=2))
    else:
        report(clone, last, latest, pending, moved, results)

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failure as exc:
        print(f"iterm-release: {exc}", file=sys.stderr)
        sys.exit(2)

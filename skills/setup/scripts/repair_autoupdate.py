#!/usr/bin/env python3
"""Repair the scripta-plugin auto-update binding in ~/.claude/settings.json.

Some configs declare `autoUpdate: true` on a marketplace keyed "scripta", which
does not match the installed marketplace ("scripta-plugin"). The flag then binds to nothing, so new
plugin versions silently never auto-update.

This renames that stale key to "scripta-plugin" and makes sure autoUpdate is on.
Idempotent and surgical: it only touches the scripta / scripta-plugin entry that
points at the team-blue-Hub/scripta repo, and leaves every other setting intact.
A JSON round-trip preserves key order; formatting normalises to 2-space indent.

Exit 0 always (a setup helper should never hard-fail); prints what it did.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
REPO = "team-blue-Hub/scripta"
GOOD = "scripta-plugin"
STALE = "scripta"


def main() -> int:
    if not SETTINGS.is_file():
        print("no ~/.claude/settings.json — nothing to repair")
        return 0
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"could not parse ~/.claude/settings.json ({e}) — left untouched")
        return 0

    if not isinstance(data, dict):
        print("~/.claude/settings.json is not a JSON object — left untouched")
        return 0

    mk = data.get("extraKnownMarketplaces")
    if not isinstance(mk, dict):
        print("no extraKnownMarketplaces block — nothing to repair")
        return 0

    def points_at_scripta(entry: object) -> bool:
        return isinstance(entry, dict) and entry.get("source", {}).get("repo") == REPO

    changed = False

    # 1. Rename the stale "scripta" key -> "scripta-plugin" (only if it's ours).
    if STALE in mk and points_at_scripta(mk[STALE]):
        entry = mk.pop(STALE)
        if GOOD in mk:
            # A scripta-plugin entry already exists; keep it, drop the stale dupe.
            print(f'removed duplicate stale "{STALE}" entry (kept existing "{GOOD}")')
        else:
            mk[GOOD] = entry
            print(f'renamed marketplace key "{STALE}" -> "{GOOD}"')
        changed = True

    # 2. Ensure the scripta-plugin entry auto-updates.
    if GOOD in mk and points_at_scripta(mk[GOOD]) and mk[GOOD].get("autoUpdate") is not True:
        mk[GOOD]["autoUpdate"] = True
        print(f'set "autoUpdate": true on "{GOOD}"')
        changed = True

    if not changed:
        print("auto-update binding already correct — no change")
        return 0

    # Back up, then write atomically (temp file + os.replace) so an interrupted
    # write can never leave the user's global settings.json half-written.
    backup = SETTINGS.with_name(SETTINGS.name + ".bak")
    tmp = SETTINGS.with_name(SETTINGS.name + ".tmp")
    try:
        mode = SETTINGS.stat().st_mode  # preserve perms — settings.json may hold secrets
    except Exception:
        mode = None

    def _chmod(p: Path) -> None:
        if mode is not None:
            try:
                os.chmod(p, mode)
            except Exception:
                pass

    try:
        backup.write_text(SETTINGS.read_text(encoding="utf-8"), encoding="utf-8")
        _chmod(backup)
    except Exception:
        pass  # best-effort backup; don't block the repair on it
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _chmod(tmp)  # so the replaced file keeps the original's permissions, not umask's
    os.replace(tmp, SETTINGS)  # atomic within the same directory
    print(f"updated ~/.claude/settings.json (backup: {backup.name}) — "
          "relaunch Claude Code for it to take effect")
    return 0


if __name__ == "__main__":
    sys.exit(main())

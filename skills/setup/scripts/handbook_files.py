#!/usr/bin/env python3
"""Start a new, empty team handbook, or check an existing one for the files
scripta's skills and hooks need.

    handbook_files.py check  <folder>
    handbook_files.py create <folder> --team NAME --owner "Full Name (@handle)"
                             [--date YYYY-MM-DD]
                             [--linear-workspace W --linear-team T --linear-label L]

`check` writes nothing. It lists each file as ok, missing or broken, and exits 1
when a must-have is missing or any file is broken.

`create` writes every template file the folder lacks and never overwrites one,
so it also fills the gaps in an existing handbook. It refuses a folder that
already holds other files and is not a handbook, so it cannot scatter handbook
files into a code repo. With the three --linear-* values it also writes
`linear` into scripta.json and a status.md for the digest's status lane.

Exit codes: 0 done (check: no must-have missing, nothing broken), 1 check found a missing must-have
or a broken file, 2 bad arguments or a folder create refuses.
"""

import argparse
import datetime
import json
import sys
import unicodedata
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "template"
# Template files written only when the handbook has Linear.
LINEAR_DIR = "linear"

# The hooks treat a folder as a handbook only when where-truth-lives.md is there.
# The digest writes decisions and adds their rows to both index files, document
# and curate cite AGENTS.md's rules by number, a page the digest creates follows
# page-format.md, and .claude/settings.json turns the plugin on in the repo.
MUST = ["where-truth-lives.md", "index.md", "decisions/README.md", "AGENTS.md",
        "page-format.md", ".claude/settings.json"]
# The digest's name check and the hardening interview read people/, and both
# skip cleanly without it.
GOOD = ["people/README.md"]
# What a fresh GitHub repo, or a folder a Mac's Finder opened, can hold before
# it is a handbook.
STARTER = {".git", "README.md", "LICENSE", "LICENSE.md", ".gitignore", ".DS_Store"}


def state(path):
    """'file' (a link to a file counts), 'absent', or 'broken': a link to nothing,
    or a folder where a file belongs. check and create both name a path this way,
    so they never disagree about it."""
    if path.is_file():
        return "file"
    if not path.exists() and not path.is_symlink():
        return "absent"
    return "broken"


def read_settings(folder):
    """scripta.json as a dict: {} when absent, None when it is broken or not a JSON object."""
    path = folder / "scripta.json"
    kind = state(path)
    if kind != "file":
        return {} if kind == "absent" else None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def needed(folder, settings):
    rows = [(p, "must-have") for p in MUST] + [(p, "good to have") for p in GOOD]
    if settings and settings.get("linear"):
        rows.append(("status.md", "needed by the Linear status lane"))
    return rows


def cmd_check(folder):
    if not folder.is_dir():
        print("No folder at %s." % folder)
        return 2
    settings = read_settings(folder)
    print("Handbook at %s:" % folder)
    failed = 0
    for rel, why in needed(folder, settings):
        # The same test create runs before it writes, so the two never disagree,
        # even for a file that is there but sits under a symlinked folder.
        problem = unsafe(folder, rel)
        if not problem and state(folder / rel) == "file":
            print("  ok       %s" % rel)
            continue
        if problem:
            # create refuses a broken path whatever its row says, so it fails here too.
            print("  broken   %s (%s)" % (rel, problem))
            failed += 1
            continue
        print("  missing  %s (%s)" % (rel, why))
        if why != "good to have":
            failed += 1
    if settings is None:
        print("  broken   scripta.json is not a JSON object")
        failed += 1
    if failed:
        print("%d needed file(s) missing or broken. `create` adds the missing ones and "
              "never overwrites a file." % failed)
        return 1
    print("Every file the skills need is there.")
    return 0


def is_litter(name):
    """A file an editor or Finder leaves in the template folder by accident."""
    return name == ".DS_Store" or name.endswith((".swp", "~"))


def targets(with_status):
    """(relative path, source) for every file create writes, where-truth-lives.md first.

    create and the hooks call a folder a handbook only once that file is there,
    so a run that stops partway can be run again.
    """
    found = []
    for src in sorted(TEMPLATE.rglob("*")):
        rel = src.relative_to(TEMPLATE)
        if src.is_file() and rel.parts[0] != LINEAR_DIR and not is_litter(src.name):
            found.append((rel.as_posix(), src))
    found.sort(key=lambda t: t[0] != "where-truth-lives.md")
    if with_status:
        found.append(("status.md", TEMPLATE / LINEAR_DIR / "status.md"))
    return found


def unsafe(folder, rel):
    """Why writing rel under folder could land somewhere else, or None when it is safe.

    A symlinked or non-folder parent would send the write outside the handbook,
    or make mkdir fail halfway, so create stops before it writes anything.
    """
    for parent in reversed(list(Path(rel).parents)[:-1]):
        p = folder / parent
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            return "%s is not a plain folder" % parent.as_posix()
    if state(folder / rel) == "broken":
        return "%s is a link to nothing, or not a file" % rel
    return None


# Lines the maps carry only when the handbook has a Linear, so status.md is
# named where every other page is. Without one, the whole line goes: a blank
# line would split the registry's table.
STATUS_LINES = {
    "status_row": "| What is moving now (a dated snapshot) | [`status.md`](status.md), **here** |",
    "status_link": "\n## Status\n\nWhat is moving now: [status.md](status.md).",
}


def substitute(text, values):
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def fill(text, values, with_status=False):
    for key, line in STATUS_LINES.items():
        text = text.replace("{{%s}}\n" % key, line + "\n" if with_status else "")
    head, sep, body = "", "", text
    if text.startswith("---\n") and "\n---\n" in text:
        head, _, body = text.partition("\n---\n")
        head, sep = head + "\n", "---\n"
    # A name can hold a colon or a hash, so a frontmatter value that carries one
    # is quoted whole (a JSON string is a YAML string). The body stays plain.
    lines = []
    for line in head.splitlines(keepends=True):
        key, colon, value = line.partition(": ")
        if colon and ("{{team}}" in value or "{{owner}}" in value):
            line = key + colon + json.dumps(substitute(value.rstrip("\n"), values), ensure_ascii=False) + "\n"
        lines.append(line)
    return substitute("".join(lines), values) + sep + substitute(body, values)


def write_new(folder, rel, text):
    dest = folder / rel
    if state(dest) == "file":
        print("  kept     %s" % rel)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("  created  %s" % rel)
    return True


def cmd_create(folder, team, owner, date, linear):
    if folder.exists() and not folder.is_dir():
        print("%s is a file, not a folder." % folder)
        return 2
    if folder.is_dir() and not (folder / "where-truth-lives.md").is_file():
        others = sorted(p.name for p in folder.iterdir() if p.name not in STARTER)
        if others:
            print("%s already holds files and is not a handbook (no where-truth-lives.md): %s. "
                  "Pick an empty folder, or a fresh clone of an empty repo."
                  % (folder, ", ".join(others[:5])))
            return 2
    settings = read_settings(folder) if folder.is_dir() else {}
    if settings is None:
        print("%s/scripta.json is not a JSON object. Fix it first; create never overwrites it."
              % folder)
        return 2
    # status.md is needed whenever the handbook has a Linear, whether this run sets
    # it or scripta.json already did, so check and create agree.
    files = targets(with_status=bool(linear or settings.get("linear")))
    reasons = [unsafe(folder, rel) for rel, _ in files]
    if linear and not settings.get("linear") and (folder / "scripta.json").is_symlink():
        reasons.append("scripta.json is a link, and create never writes through one")
    reasons = [r for r in reasons if r]
    if reasons:
        print("Not writing into %s: %s. Nothing was written." % (folder, reasons[0]))
        return 2
    folder.mkdir(parents=True, exist_ok=True)
    values = {"team": team, "owner": owner, "date": date}
    print("Handbook at %s:" % folder)
    with_status = any(rel == "status.md" for rel, _ in files)
    written = {}
    for rel, src in files:
        written[rel] = write_new(folder, rel, fill(src.read_text(encoding="utf-8"), values, with_status))
    if written.get("status.md") and not written.get("where-truth-lives.md"):
        print("  note     add status.md to where-truth-lives.md and index.md by hand: they existed already")
    if linear:
        if settings.get("linear"):
            print("  kept     scripta.json (it already names a Linear)")
        else:
            settings["linear"] = linear
            existed = (folder / "scripta.json").is_file()
            with open(folder / "scripta.json", "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(settings, indent=2) + "\n")
            print("  %s  scripta.json" % ("updated" if existed else "created"))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="list the needed files as ok or missing; writes nothing")
    check.add_argument("folder")
    create = sub.add_parser("create", help="write the missing files; never overwrites one")
    create.add_argument("folder")
    create.add_argument("--team", required=True, help="the team's name, as the index title shows it")
    create.add_argument("--owner", required=True, help='who owns the new pages: "Full Name (@handle)"')
    create.add_argument("--date", default=datetime.date.today().isoformat(), help="YYYY-MM-DD, default today")
    create.add_argument("--linear-workspace")
    create.add_argument("--linear-team")
    create.add_argument("--linear-label")
    args = parser.parse_args(argv)
    folder = Path(args.folder).expanduser()
    if args.cmd == "check":
        return cmd_check(folder)
    try:
        datetime.date.fromisoformat(args.date)
    except ValueError:
        print("--date must be YYYY-MM-DD, not %r." % args.date)
        return 2
    if not args.team.strip() or not args.owner.strip():
        print("--team and --owner must not be empty.")
        return 2
    if any(unicodedata.category(ch) == "Cc" for ch in args.team + args.owner):
        print("--team and --owner must not hold control characters (a tab or a line break).")
        return 2
    parts = (args.linear_workspace, args.linear_team, args.linear_label)
    if any(parts) and not all(parts):
        print("Give all three of --linear-workspace, --linear-team and --linear-label, or none.")
        return 2
    linear = dict(zip(("workspace", "team", "label"), parts)) if all(parts) else None
    return cmd_create(folder, args.team.strip(), args.owner.strip(), args.date, linear)


if __name__ == "__main__":
    sys.exit(main())

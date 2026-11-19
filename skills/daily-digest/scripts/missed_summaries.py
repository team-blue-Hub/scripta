#!/usr/bin/env python3
"""Missed summaries - name each call that has no summary in the handbook.

One day's digest PR holds every call's summary for that day, so a day with one
call summarized looks done while another call of that day has none. This check
reads the team's calls and their weekdays from the handbook's scripta.json,
looks back over the last weekdays, and names each call that has no summary, so
a missed one shows up the next morning.

A call counts as summarized on a date when the handbook has any one of:
  - its block "### <date> · <call>" in a week's update, at any point in the
    week PR's history (the Friday run deletes the blocks, so the history is
    read, not only the file);
  - a decision whose "## Source" names "<call>, <date>", on main or on an open
    digest PR;
  - a digest PR, open or merged, that lists "<call>, <date>" under "## Meetings".

It has no Zoom access, on purpose, so it runs anywhere, and so it cannot tell a
missed summary from a call that did not happen (a holiday, a cancelled call).

scripta.json, at the handbook root:

  { "digest": { "calls": [
      { "title": "Team - Daily", "days": "tue-fri", "owner": "gh-login", "backup": "gh-login" },
      { "title": "Team - Planning", "days": "mon", "owner": "gh-login" } ] } }

  title is the call's Zoom title, as the digest writes it. days uses the noon
  schedule's format: mon, tue-fri, mon,wed or all. owner and backup are GitHub
  logins, mentioned next to a missing call; both are optional.

Usage:
  missed_summaries.py [--handbook DIR] [--today YYYY-MM-DD] [--days N] [--issue]

  Prints the report. --issue also keeps one GitHub issue in the handbook repo up
  to date: it opens the issue when a call is missing, comments on each run while
  one is, and closes it once none is.

  Needs git and gh, run against a full (not shallow) clone of the handbook, with
  read access to its pull requests, and write access to its issues for --issue.

Exit codes: 0 when the check ran, missing calls or not; 1 when it could not run
(scripta.json, git or gh); 2 for a bad argument.

Runs on python3 3.9: no match statements, no 3.10+ calls.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from digest_schedule import adr_has_meeting, parse_days, week_names  # noqa: E402

ISSUE_TITLE = "Call summaries missing"
DEFAULT_DAYS = 5
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
DIGEST_BRANCH = re.compile(r"^digest/(\d{4}-\d{2}-\d{2})")
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
BLOCK = re.compile(r"^### (\d{4}-\d{2}-\d{2}) · (.+)$")
MEETING_LINE = re.compile(r"^\s*[-+]\s+(.+?),\s*(\d{4}-\d{2}-\d{2})\b")

FOOTER = ("A call counts as summarized when its block is in the week's update, a decision's "
          "Source names it, or a digest PR lists it under Meetings. A call that did not happen "
          "that day (a holiday, a cancelled call) shows up here too: ignore its line. "
          "The calls and their days are in `scripta.json`.")


class CheckError(Exception):
    pass


# ---------------------------------------------------------------- the seam

def run_cmd(argv, cwd=None, timeout=300):
    """Run one outside command (git or gh). Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "", str(e)


def clock_today():
    return dt.date.today()


def must(argv, hb, ok=(0,)):
    rc, out, err = run_cmd(argv, cwd=str(hb))
    if rc not in ok:
        last = (err or out).strip().splitlines()
        raise CheckError("`%s` failed: %s" % (" ".join(argv[:3]), last[-1] if last else "exit %d" % rc))
    return out


# ---------------------------------------------------------------- the calls

def norm(s):
    return re.sub(r"\s+", " ", s.strip()).lower()


def login(value, title, field):
    if value in (None, ""):
        return ""
    s = str(value).strip().lstrip("@")
    if not LOGIN.match(s):
        raise CheckError("%s: %s %r is not a GitHub login" % (title, field, value))
    return s


def load_calls(hb):
    path = Path(hb) / "scripta.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CheckError("No scripta.json at %s. It lists the calls to check." % path)
    except ValueError as e:
        raise CheckError("scripta.json is not valid JSON: %s" % e)
    digest = data.get("digest") if isinstance(data, dict) else None
    calls = digest.get("calls") if isinstance(digest, dict) else None
    if not isinstance(calls, list) or not calls:
        raise CheckError('scripta.json has no "digest": {"calls": [...]} list.')
    out = []
    for i, c in enumerate(calls, 1):
        title = c.get("title") if isinstance(c, dict) else None
        if not isinstance(title, str) or not title.strip():
            raise CheckError("Call %d in scripta.json has no title." % i)
        title = title.strip()
        try:
            days = parse_days(str(c.get("days", "all")))
        except ValueError as e:
            raise CheckError("%s: %s" % (title, e))
        out.append({"title": title, "days": days,
                    "owner": login(c.get("owner"), title, "owner"),
                    "backup": login(c.get("backup"), title, "backup")})
    return out


def window(day, n):
    """The n weekdays before day, oldest first. Today is not in it: its calls
    may not be summarized yet."""
    out, d = [], day
    while len(out) < n:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return sorted(out)


# ---------------------------------------------------------------- what the handbook holds

def meetings_in_body(body):
    """(normalized title, date) for each line under a PR body's '## Meetings'."""
    out, inside = [], False
    for line in (body or "").splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower() == "meetings"
            continue
        if inside:
            m = MEETING_LINE.match(line.replace("*", "").replace("`", ""))
            if m:
                out.append((norm(m.group(1)), m.group(2)))
    return out


def blocks_added(log_patch):
    """(normalized title, date) for each week block a commit added."""
    out = []
    for line in log_patch.splitlines():
        if line.startswith("+### "):
            m = BLOCK.match(re.sub(r"\s+", " ", line[1:].strip()))
            if m:
                out.append((norm(m.group(2)), m.group(1)))
    return out


def summaries(hb, dates, titles):
    """The (normalized title, date) pairs the handbook holds a summary for."""
    hb = str(hb)
    start = dates[0]
    want_dates = {d.isoformat() for d in dates}
    want = {norm(t): t for t in titles}
    found = set()

    def keep(pairs):
        for t, d in pairs:
            if t in want and d in want_dates:
                found.add((t, d))

    must(["git", "-C", hb, "fetch", "--quiet", "origin", "+refs/heads/main:refs/remotes/origin/main"], hb)
    try:
        prs = json.loads(must(["gh", "pr", "list", "--state", "all", "--limit", "300",
                               "--json", "number,headRefName,headRefOid,state,body"], hb))
    except ValueError:
        raise CheckError("`gh pr list` did not return JSON.")
    live = [p for p in prs if p.get("state") in ("OPEN", "MERGED")]

    def branch_day(p):
        m = DIGEST_BRANCH.match(p.get("headRefName") or "")
        return dt.date.fromisoformat(m.group(1)) if m else None

    # A summary for a date lands on that date's branch or a later one (a backfill).
    digest_prs = [p for p in live if branch_day(p) and branch_day(p) >= start]
    weeks = {week_names(d)[1] for d in dates}
    week_prs = [p for p in live if p.get("headRefName") in weeks]

    for p in digest_prs:
        keep(meetings_in_body(p.get("body")))

    # PR heads by commit id, so no local ref is made or left behind. GitHub keeps
    # refs/pull/<n>/head after a branch is deleted, so a merged week PR still reads.
    fetch = [p for p in digest_prs if p["state"] == "OPEN"] + week_prs
    if fetch:
        must(["git", "-C", hb, "fetch", "--quiet", "origin"]
             + ["refs/pull/%d/head" % p["number"] for p in fetch], hb)

    # Decisions: the Source lines on main and on every open digest PR.
    refs = ["origin/main"] + [p["headRefOid"] for p in digest_prs if p["state"] == "OPEN"]
    grep = ["git", "-C", hb, "grep", "-l", "-F"]
    for d in sorted(want_dates):
        grep += ["-e", d]
    out = must(grep + refs + ["--", "decisions/"], hb, ok=(0, 1))  # 1: nothing matched
    for line in out.splitlines():
        ref, _, path = line.partition(":")
        if not path.endswith(".md"):
            continue
        text = must(["git", "-C", hb, "show", "%s:%s" % (ref, path)], hb)
        for d in want_dates.intersection(DATE.findall(text)):
            for t, title in want.items():
                if adr_has_meeting(text, title, d):
                    found.add((t, d))

    # Week blocks: every block ever added on main or a week PR, since the Friday
    # run deletes them from the file. Merge commits show no diff, so each block
    # counts once, from the commit that wrote it.
    refs = ["origin/main"] + [p["headRefOid"] for p in week_prs]
    keep(blocks_added(must(["git", "-C", hb, "log", "-p", "--format=", "--no-color"]
                           + refs + ["--", "updates/"], hb)))
    return found


def missing_calls(hb, day, n):
    calls = load_calls(hb)
    dates = window(day, n)
    found = summaries(hb, dates, [c["title"] for c in calls])
    return dates, [(d, c) for d in dates for c in calls
                   if d.weekday() in c["days"] and (norm(c["title"]), d.isoformat()) not in found]


# ---------------------------------------------------------------- the report

def mentions(call):
    if call["owner"] and call["backup"]:
        return "@%s, backup @%s" % (call["owner"], call["backup"])
    if call["owner"] or call["backup"]:
        return "@" + (call["owner"] or call["backup"])
    return ""


def report(dates, missing):
    span = "%s to %s" % (dates[0].isoformat(), dates[-1].isoformat())
    if not missing:
        return "Every call from %s has a summary in the handbook." % span
    lines = ["%d call%s from %s %s no summary in the handbook:" % (
        len(missing), "" if len(missing) == 1 else "s", span, "has" if len(missing) == 1 else "have"), ""]
    for d, c in missing:
        who = mentions(c)
        lines.append("- %s · %s%s" % (d.isoformat(), c["title"], (" · " + who) if who else ""))
    return "\n".join(lines + ["", FOOTER])


def issue_intro(n):
    return ("This issue belongs to the missed-summaries check "
            "(`skills/daily-digest/scripts/missed_summaries.py` in scripta). Each weekday "
            "morning it looks back over the last %d weekdays and names each call that has no "
            "summary. It comments here while a call is missing and closes this issue once none "
            "is." % n)


def find_issue(hb):
    try:
        found = json.loads(must(["gh", "issue", "list", "--state", "open", "--limit", "20",
                                 "--search", '"%s" in:title' % ISSUE_TITLE,
                                 "--json", "number,title"], hb))
    except ValueError:
        raise CheckError("`gh issue list` did not return JSON.")
    for i in found:
        if i.get("title") == ISSUE_TITLE:
            return i["number"]
    return None


def update_issue(hb, text, missing, n):
    number = find_issue(hb)
    if missing and number is None:
        url = must(["gh", "issue", "create", "--title", ISSUE_TITLE,
                    "--body", issue_intro(n) + "\n\n" + text], hb).strip()
        return "Opened %s" % url
    if missing:
        must(["gh", "issue", "comment", str(number), "--body", text], hb)
        return "Commented on issue #%d" % number
    if number is not None:
        must(["gh", "issue", "close", str(number), "--comment", text], hb)
        return "Closed issue #%d" % number
    return "No open issue, nothing missing: no issue change"


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="missed_summaries.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--handbook", default=".", help="the handbook checkout (default: here)")
    ap.add_argument("--today", help="check as if today were this date, YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help="how many weekdays before today to check (default %d)" % DEFAULT_DAYS)
    ap.add_argument("--issue", action="store_true",
                    help="also open, comment on or close the handbook's '%s' issue" % ISSUE_TITLE)
    args = ap.parse_args(argv)
    if args.days < 1:
        ap.error("--days must be 1 or more")
    try:
        day = dt.date.fromisoformat(args.today) if args.today else clock_today()
    except ValueError:
        ap.error("--today must be a date like 2026-11-06")
    hb = Path(args.handbook).expanduser().resolve()
    try:
        dates, missing = missing_calls(hb, day, args.days)
        text = report(dates, missing)
        print(text)
        if args.issue:
            print(update_issue(hb, text, missing, args.days))
    except CheckError as e:
        print("The check could not run: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Unit tests for missed_summaries.py.

Stdlib unittest only. Every outside call goes through the seam in
missed_summaries (run_cmd, clock_today); here a fake `World` replaces it, so
nothing reaches the network, a real git repo or GitHub. The handbook folder is
a temp dir that holds a real scripta.json.

Run: cd skills/daily-digest/scripts && python3 -m unittest -v test_missed_summaries
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import missed_summaries as ms  # noqa: E402

SQ1 = "Hub - Daily - Sq1"
SQ2 = "Hub - Daily - Sq2"
PLANNING = "Hub - Planning - Sq1"
D = dt.date
TUE = D(2026, 11, 10)
WED = D(2026, 11, 11)
WEEK_BRANCH = ms.week_names(TUE)[1]


def adr(title, date):
    return "# Decision\n\n## Source\n%s, %s, 09:05:00\n> quote\n\n## Notes\nx\n" % (title, date)


def meetings_body(*pairs):
    return "## Summary\nx\n\n## Meetings\n" + "".join(
        "- **%s**, %s (Zoom)\n" % p for p in pairs) + "\n## Other\n"


def pr(number, branch, state, body="", oid=None):
    return {"number": number, "headRefName": branch, "headRefOid": oid or "oid%d" % number,
            "state": state, "body": body}


class World(object):
    """The fake outside world behind the seam."""

    def __init__(self):
        self.calls = []           # (argv, cwd)
        self.prs = []
        self.gh_list_fails = False
        self.grep_hits = []       # "ref:path" lines
        self.grep_rc = None       # force an exit code for git grep
        self.blobs = {}           # (ref, path) -> text
        self.log_patch = ""
        self.log_by_ref = {}      # when set, git log returns the patches of the refs it is given
        self.issues = []          # open issues, as gh returns them
        self.created = "https://github.com/x/y/issues/9\n"

    def run_cmd(self, argv, cwd=None, timeout=300):
        self.calls.append((list(argv), cwd))
        a = argv
        if a[:3] == ["gh", "pr", "list"]:
            if self.gh_list_fails:
                return 1, "", "no network"
            return 0, json.dumps(self.prs), ""
        if a[:3] == ["gh", "issue", "list"]:
            return 0, json.dumps(self.issues), ""
        if a[:3] == ["gh", "issue", "create"]:
            return 0, self.created, ""
        if a[:2] == ["gh", "issue"] and a[2] in ("comment", "close"):
            return 0, "", ""
        if a[0] == "git" and a[3] == "fetch":
            return 0, "", ""
        if a[0] == "git" and a[3] == "grep":
            if self.grep_rc is not None:
                return self.grep_rc, "", ""
            return (0, "\n".join(self.grep_hits) + "\n", "") if self.grep_hits else (1, "", "")
        if a[0] == "git" and a[3] == "show":
            ref, _, path = a[4].partition(":")
            if (ref, path) in self.blobs:
                return 0, self.blobs[(ref, path)], ""
            return 128, "", "not found"
        if a[0] == "git" and a[3] == "log":
            if self.log_by_ref:
                return 0, "".join(v for k, v in self.log_by_ref.items() if k in a), ""
            return 0, self.log_patch, ""
        raise AssertionError("unexpected call: %r" % (argv,))

    def gh_writes(self):
        return [c for c, _ in self.calls if c[:2] == ["gh", "issue"] and c[2] in ("create", "comment", "close")]


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.dir), True)
        self.world = World()
        for name, fn in (("run_cmd", self.world.run_cmd), ("clock_today", lambda: WED)):
            p = mock.patch.object(ms, name, fn)
            p.start()
            self.addCleanup(p.stop)

    def write_calls(self, calls):
        (self.dir / "scripta.json").write_text(json.dumps({"digest": {"calls": calls}}), encoding="utf-8")

    def one_call(self, title=SQ1, days="all"):
        self.write_calls([{"title": title, "days": days}])

    def missing(self, day=WED, n=1):
        dates, missing = ms.missing_calls(self.dir, day, n)
        return [(d.isoformat(), c["title"]) for d, c in missing]

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = ms.main(["--handbook", str(self.dir)] + list(args))
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue()


class LoadCalls(Base):
    def test_no_file(self):
        with self.assertRaises(ms.CheckError):
            ms.load_calls(self.dir)

    def test_bad_json(self):
        (self.dir / "scripta.json").write_text("{nope", encoding="utf-8")
        with self.assertRaises(ms.CheckError):
            ms.load_calls(self.dir)

    def test_no_calls_list(self):
        for data in ({}, {"digest": {}}, {"digest": {"calls": []}}, {"digest": {"calls": "x"}}, []):
            (self.dir / "scripta.json").write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ms.CheckError):
                ms.load_calls(self.dir)

    def test_call_without_title(self):
        for c in ({"days": "mon"}, {"title": "  "}, {"title": 3}, "str"):
            self.write_calls([c])
            with self.assertRaises(ms.CheckError):
                ms.load_calls(self.dir)

    def test_bad_days(self):
        self.write_calls([{"title": SQ1, "days": "funday"}])
        with self.assertRaises(ms.CheckError):
            ms.load_calls(self.dir)

    def test_bad_login(self):
        for field in ("owner", "backup"):
            self.write_calls([{"title": SQ1, field: "not a login!"}])
            with self.assertRaises(ms.CheckError):
                ms.load_calls(self.dir)

    def test_at_is_stripped_and_owner_backup_optional(self):
        self.write_calls([{"title": " %s " % SQ1, "days": "tue-fri", "owner": "@ann", "backup": "bob"},
                          {"title": SQ2}])
        a, b = ms.load_calls(self.dir)
        self.assertEqual((a["title"], a["owner"], a["backup"], a["days"]), (SQ1, "ann", "bob", [1, 2, 3, 4]))
        self.assertEqual((b["owner"], b["backup"], b["days"]), ("", "", [0, 1, 2, 3, 4]))


class Window(unittest.TestCase):
    def test_monday_returns_five_weekdays_before(self):
        got = ms.window(D(2026, 11, 9), 5)
        self.assertEqual([d.isoformat() for d in got],
                         ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"])

    def test_skips_weekend_and_never_today(self):
        got = ms.window(D(2026, 11, 9), 2)
        self.assertEqual([d.isoformat() for d in got], ["2026-11-05", "2026-11-06"])
        self.assertNotIn(D(2026, 11, 9), ms.window(D(2026, 11, 9), 5))
        self.assertTrue(all(d.weekday() < 5 for d in ms.window(D(2026, 11, 8), 7)))


class MeetingsInBody(unittest.TestCase):
    def test_three_formats(self):
        body = ("## Meetings\n"
                "- **Hub - Daily - Sq2**, 2026-11-06 ([recording](https://z.us/x))\n"
                "- **Hub - Daily - Sq2, 2026-11-04** (Zoom 123)\n"
                "- Hub - Planning - Sq1, 2026-10-26 (`abc`)\n")
        self.assertEqual(ms.meetings_in_body(body), [
            ("hub - daily - sq2", "2026-11-06"),
            ("hub - daily - sq2", "2026-11-04"),
            ("hub - planning - sq1", "2026-10-26")])

    def test_outside_section_does_not_count(self):
        body = "- Hub - Daily - Sq1, 2026-11-06 (x)\n## Notes\n- Hub - Daily - Sq1, 2026-11-05 (x)\n"
        self.assertEqual(ms.meetings_in_body(body), [])
        self.assertEqual(ms.meetings_in_body(None), [])

    def test_section_ends_at_next_heading(self):
        body = "## Meetings\n- A, 2026-11-06 (x)\n## Later\n- B, 2026-11-06 (x)\n"
        self.assertEqual(ms.meetings_in_body(body), [("a", "2026-11-06")])

    def test_nested_line_gives_no_call(self):
        body = ("## Meetings\n- **Hub - Daily - Sq2**, 2026-11-06 (x)\n"
                "  - Backfill: triaged on 2026-10-29, written on 2026-11-02 in commit 0b7fe08.\n")
        self.assertEqual(ms.meetings_in_body(body), [("hub - daily - sq2", "2026-11-06")])


class BlocksAdded(unittest.TestCase):
    def test_added_counts_with_case_and_spaces_folded(self):
        patch = "+### 2026-10-27 · Hub - Daily - Sq1\n+###   2026-10-28  ·  HUB - daily -   Sq2  \n"
        self.assertEqual(ms.blocks_added(patch), [("hub - daily - sq1", "2026-10-27"),
                                                  ("hub - daily - sq2", "2026-10-28")])

    def test_removed_and_context_lines_do_not(self):
        patch = "-### 2026-10-27 · Hub - Daily - Sq1\n ### 2026-10-27 · Hub - Daily - Sq1\n+text\n"
        self.assertEqual(ms.blocks_added(patch), [])


class EndToEnd(Base):
    def test_found_via_week_block_in_merged_week_pr_history(self):
        self.one_call()
        self.world.prs = [pr(3, WEEK_BRANCH, "MERGED", oid="wk1")]
        self.world.log_patch = "+### 2026-11-10 · Hub - Daily - Sq1\n+text\n"
        self.assertEqual(self.missing(), [])
        log = [c for c, _ in self.world.calls if c[3] == "log"][0]
        self.assertIn("wk1", log)
        self.assertIn("origin/main", log)

    def test_found_via_adr_source_on_open_digest_pr(self):
        self.one_call()
        self.world.prs = [pr(7, "digest/2026-11-10", "OPEN", oid="abc123")]
        self.world.grep_hits = ["abc123:decisions/d.md", "abc123:decisions/README.txt"]
        self.world.blobs[("abc123", "decisions/d.md")] = adr(SQ1, "2026-11-10")
        self.assertEqual(self.missing(), [])
        grep = [c for c, _ in self.world.calls if c[3] == "grep"][0]
        self.assertIn("abc123", grep)
        show = [c for c, _ in self.world.calls if c[3] == "show"]
        self.assertEqual([c[4] for c in show], ["abc123:decisions/d.md"])

    def test_found_via_merged_digest_pr_body(self):
        self.one_call()
        self.world.prs = [pr(8, "digest/2026-11-10", "MERGED", meetings_body((SQ1, "2026-11-10")))]
        self.assertEqual(self.missing(), [])

    def test_closed_pr_body_does_not_count(self):
        self.one_call()
        self.world.prs = [pr(8, "digest/2026-11-10", "CLOSED", meetings_body((SQ1, "2026-11-10")))]
        self.assertEqual(self.missing(), [("2026-11-10", SQ1)])

    def test_branch_date_before_window_start_is_not_used(self):
        self.one_call()
        self.world.prs = [pr(8, "digest/2026-11-09", "MERGED", meetings_body((SQ1, "2026-11-10")))]
        self.assertEqual(self.missing(), [("2026-11-10", SQ1)])

    def test_one_call_of_a_day_summarized_names_the_other(self):
        self.write_calls([{"title": SQ1}, {"title": SQ2}])
        self.world.prs = [pr(8, "digest/2026-11-10", "MERGED", meetings_body((SQ2, "2026-11-10")))]
        self.assertEqual(self.missing(), [("2026-11-10", SQ1)])

    def test_days_mon_not_expected_on_tuesday(self):
        self.one_call(title=PLANNING, days="mon")
        self.assertEqual(self.missing(), [])
        # and it is expected on a Monday
        self.assertEqual(self.missing(day=D(2026, 11, 10)), [("2026-11-09", PLANNING)])

    def test_git_grep_exit_1_is_not_a_failure(self):
        self.one_call()
        self.world.grep_rc = 1
        self.assertEqual(self.missing(), [("2026-11-10", SQ1)])

    def test_git_grep_exit_2_is_a_failure(self):
        self.one_call()
        self.world.grep_rc = 2
        rc, out, err = self.run_main("--days", "1")
        self.assertEqual(rc, 1)
        self.assertTrue(err.startswith("The check could not run"))

    def test_gh_pr_list_failing_makes_main_return_1(self):
        self.one_call()
        self.world.gh_list_fails = True
        rc, out, err = self.run_main("--today", "2026-11-11", "--days", "1")
        self.assertEqual(rc, 1)
        self.assertTrue(err.startswith("The check could not run"))
        self.assertEqual(out, "")

    def git_call(self, sub):
        return [c for c, _ in self.world.calls if c[0] == "git" and c[3] == sub][0]

    def test_week_pr_filter_ignores_closed_and_unrelated_prs(self):
        self.write_calls([{"title": SQ1}, {"title": SQ2}, {"title": PLANNING}])
        self.world.prs = [pr(3, WEEK_BRANCH, "MERGED", oid="wk1"),
                          pr(4, WEEK_BRANCH, "CLOSED", oid="wk2"),
                          pr(5, "docs/something", "OPEN", oid="oth")]
        self.world.log_by_ref = {"wk1": "+### 2026-11-10 · %s\n" % SQ1,
                                 "wk2": "+### 2026-11-10 · %s\n" % SQ2,
                                 "oth": "+### 2026-11-10 · %s\n" % PLANNING}
        self.assertEqual(self.missing(), [("2026-11-10", SQ2), ("2026-11-10", PLANNING)])
        log = self.git_call("log")
        self.assertEqual(log[log.index("--no-color") + 1:log.index("--")], ["origin/main", "wk1"])

    def test_window_across_two_weeks_reads_both_week_prs(self):
        self.write_calls([{"title": SQ1, "days": "wed"}, {"title": SQ2, "days": "tue"}])
        prev_week = ms.week_names(D(2026, 11, 4))[1]
        self.assertNotEqual(prev_week, WEEK_BRANCH)
        self.world.prs = [pr(3, prev_week, "MERGED", oid="wkA"), pr(4, WEEK_BRANCH, "MERGED", oid="wkB")]
        self.world.log_by_ref = {"wkA": "+### 2026-11-04 · %s\n" % SQ1,
                                 "wkB": "+### 2026-11-10 · %s\n" % SQ2}
        self.assertEqual(self.missing(n=5), [])
        log = self.git_call("log")
        self.assertIn("wkA", log)
        self.assertIn("wkB", log)

    def test_found_via_adr_source_on_main(self):
        self.one_call()
        self.world.grep_hits = ["origin/main:decisions/d.md"]
        self.world.blobs[("origin/main", "decisions/d.md")] = adr(SQ1, "2026-11-10")
        self.assertEqual(self.missing(), [])
        self.assertIn("origin/main", self.git_call("grep"))
        self.assertEqual(self.git_call("show")[4], "origin/main:decisions/d.md")

    def assert_failed_run_leaves_issue_alone(self):
        rc, out, err = self.run_main("--today", "2026-11-11", "--days", "1", "--issue")
        self.assertEqual(rc, 1)
        self.assertTrue(err.startswith("The check could not run"))
        self.assertEqual(self.world.gh_writes(), [])
        self.assertFalse([c for c, _ in self.world.calls if c[:3] == ["gh", "issue", "list"]])

    def test_failed_run_with_issue_flag_gh_pr_list_fails(self):
        self.one_call()
        self.world.issues = [{"number": 4, "title": ms.ISSUE_TITLE}]
        self.world.gh_list_fails = True
        self.assert_failed_run_leaves_issue_alone()

    def test_failed_run_with_issue_flag_git_grep_fails(self):
        self.one_call()
        self.world.issues = [{"number": 4, "title": ms.ISSUE_TITLE}]
        self.world.grep_rc = 2
        self.assert_failed_run_leaves_issue_alone()

    def test_main_prints_report_and_returns_0_with_missing(self):
        self.one_call()
        rc, out, err = self.run_main("--today", "2026-11-11", "--days", "1")
        self.assertEqual(rc, 0)
        self.assertIn("1 call from 2026-11-10 to 2026-11-10 has no summary", out)

    def test_no_real_git_or_gh_is_run(self):
        # The seam is patched: the only argv that went out are the fake's.
        self.one_call()
        self.run_main("--today", "2026-11-11", "--days", "1")
        self.assertTrue(self.world.calls)
        self.assertTrue(all(c[0] in ("git", "gh") for c, _ in self.world.calls))


class Report(unittest.TestCase):
    DATES = [D(2026, 11, 9), D(2026, 11, 10)]

    def call(self, owner="", backup=""):
        return {"title": SQ1, "days": [0], "owner": owner, "backup": backup}

    def test_all_clear(self):
        self.assertEqual(ms.report(self.DATES, []),
                         "Every call from 2026-11-09 to 2026-11-10 has a summary in the handbook.")

    def test_singular(self):
        text = ms.report(self.DATES, [(D(2026, 11, 9), self.call())])
        self.assertIn("1 call from 2026-11-09 to 2026-11-10 has no summary in the handbook:", text)
        self.assertIn("- 2026-11-09 · %s\n" % SQ1, text + "\n")

    def test_plural(self):
        text = ms.report(self.DATES, [(D(2026, 11, 9), self.call()), (D(2026, 11, 10), self.call())])
        self.assertIn("2 calls from 2026-11-09 to 2026-11-10 have no summary in the handbook:", text)
        self.assertTrue(text.endswith(ms.FOOTER))

    def test_mentions(self):
        self.assertEqual(ms.mentions(self.call("ann", "bob")), "@ann, backup @bob")
        self.assertEqual(ms.mentions(self.call("ann")), "@ann")
        self.assertEqual(ms.mentions(self.call(backup="bob")), "@bob")
        self.assertEqual(ms.mentions(self.call()), "")
        text = ms.report(self.DATES, [(D(2026, 11, 9), self.call("ann", "bob"))])
        self.assertIn("- 2026-11-09 · %s · @ann, backup @bob" % SQ1, text)


class Issue(Base):
    DATES = [D(2026, 11, 10)]

    def missing_one(self):
        return [(D(2026, 11, 10), {"title": SQ1, "days": [1], "owner": "", "backup": ""})]

    def test_missing_no_issue_creates_one(self):
        text = ms.report(self.DATES, self.missing_one())
        msg = ms.update_issue(self.dir, text, self.missing_one(), 5)
        writes = self.world.gh_writes()
        self.assertEqual(len(writes), 1)
        w = writes[0]
        self.assertEqual(w[2], "create")
        self.assertEqual(w[w.index("--title") + 1], "Call summaries missing")
        body = w[w.index("--body") + 1]
        self.assertTrue(body.startswith(ms.issue_intro(5)))
        self.assertTrue(body.endswith(text))
        self.assertEqual(msg, "Opened https://github.com/x/y/issues/9")

    def test_missing_with_open_issue_comments(self):
        self.world.issues = [{"number": 4, "title": ms.ISSUE_TITLE}]
        ms.update_issue(self.dir, "text", self.missing_one(), 5)
        writes = self.world.gh_writes()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][:4], ["gh", "issue", "comment", "4"])
        self.assertEqual(writes[0][-1], "text")

    def test_nothing_missing_with_open_issue_closes_it(self):
        self.world.issues = [{"number": 4, "title": ms.ISSUE_TITLE}]
        ms.update_issue(self.dir, "all good", [], 5)
        writes = self.world.gh_writes()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][:4], ["gh", "issue", "close", "4"])
        self.assertEqual(writes[0][writes[0].index("--comment") + 1], "all good")

    def test_nothing_missing_no_issue_writes_nothing(self):
        msg = ms.update_issue(self.dir, "all good", [], 5)
        self.assertEqual(self.world.gh_writes(), [])
        self.assertIn("no issue change", msg)

    def test_similar_title_is_not_ours(self):
        self.world.issues = [{"number": 4, "title": "Call summaries missing for Sq1"}]
        ms.update_issue(self.dir, "text", self.missing_one(), 5)
        self.assertEqual(self.world.gh_writes()[0][2], "create")
        self.world.calls[:] = []
        ms.update_issue(self.dir, "text", [], 5)
        self.assertEqual(self.world.gh_writes(), [])

    def test_main_issue_creates(self):
        self.one_call()
        rc, out, err = self.run_main("--today", "2026-11-11", "--days", "1", "--issue")
        self.assertEqual(rc, 0)
        self.assertEqual([w[2] for w in self.world.gh_writes()], ["create"])
        self.assertIn("Opened", out)

    def test_main_issue_closes(self):
        self.one_call()
        self.world.prs = [pr(8, "digest/2026-11-10", "MERGED", meetings_body((SQ1, "2026-11-10")))]
        self.world.issues = [{"number": 4, "title": ms.ISSUE_TITLE}]
        rc, out, err = self.run_main("--today", "2026-11-11", "--days", "1", "--issue")
        self.assertEqual(rc, 0)
        self.assertEqual([w[2] for w in self.world.gh_writes()], ["close"])

    def test_main_without_issue_flag_never_writes(self):
        self.one_call()
        self.run_main("--today", "2026-11-11", "--days", "1")
        self.assertEqual(self.world.gh_writes(), [])
        self.assertFalse([c for c, _ in self.world.calls if c[:3] == ["gh", "issue", "list"]])


class MainArgs(Base):
    def test_days_zero_exits_2(self):
        rc, out, err = self.run_main("--days", "0")
        self.assertEqual(rc, 2)
        self.assertEqual(self.world.calls, [])

    def test_bad_today_exits_2(self):
        rc, out, err = self.run_main("--today", "11/06/2026")
        self.assertEqual(rc, 2)
        self.assertEqual(self.world.calls, [])


if __name__ == "__main__":
    unittest.main()

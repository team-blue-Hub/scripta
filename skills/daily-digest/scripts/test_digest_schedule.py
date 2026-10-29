#!/usr/bin/env python3
"""Unit tests for digest_schedule.py.

Stdlib unittest only. Every outside call goes through the seam in
digest_schedule (run_cmd, which_on, clock, stdin_is_tty, ask); here a fake
`World` replaces it, so nothing reaches the real launchd, Terminal, git remote
or GitHub, and each test runs under its own temp home folder (see home_env). The one place real
processes run is on purpose: the loader string and the window command are
executed with `python3 -c` and `sh -c` against fake tools in a temp folder.

Run: cd skills/daily-digest/scripts && python3 -m unittest -v test_digest_schedule
"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import digest_schedule as ds  # noqa: E402

HOOK = Path(__file__).resolve().parents[3] / "hooks" / "load_scripta_context.py"

DAILY_SQ2 = "Hub - Daily - Sq2"
DAILY_ALL = "Hub - Daily - All"
PLANNING = "Hub - Planning - Sq2"
WED = "2026-10-14T12:00"   # Wednesday; previous weekday Tuesday 2026-10-13
TODAY = "2026-10-14"


def pr_url(n):
    return "https://github.com/team-blue-Hub/hub-scripta-handbook/pull/%d" % n


def adr_text(title, date):
    return ("---\nstatus: proposed\n---\n# Some decision\n\n## Context\nWhy.\n\n## Decision\nDo it.\n\n"
            "## Source\n%s, %s, 09:05:00\n> \"a verbatim quote\"\n\n## Notes\nnot part of the source\n"
            % (title, date))


class World(object):
    """The fake outside world behind the seam."""

    def __init__(self, home):
        self.home = home
        self.uname = "Darwin"
        self.tool_dirs = {"/fake/bin": {"claude", "git", "gh"}}
        self.calls = []            # (argv, cwd)
        self.which_paths = []
        self.prs = []
        self.files = {}            # pr number -> [paths]
        self.blobs = {}            # (ref, path) -> text
        self.gh_list_fails = False
        self.fetch_fails = False
        self.view_fails = False
        self.show_fails = False
        self.fail_fetch_refs = set()
        self.window_fails = False
        self.launchctl_list_rc = 0
        self.zoom = {}             # zoom id -> reply dict, or ("raw", stdout), or ("rc", code, stderr)
        self.claude_timeouts = []
        self.stdout_log = io.StringIO()
        self.inputs = []           # input_text of each call, in step with calls
        self.schtasks_fails = False
        self.task_exists = True
        self.task_cmd = ""
        self.delete_fails = False
        self.settings_fail = False
        self.detached = []         # detach flag of each call, in step with calls

    # --- seam replacements
    def run_cmd(self, argv, cwd=None, timeout=None, input_text=None, detach=False):
        self.calls.append((list(argv), cwd))
        self.inputs.append(input_text)
        self.detached.append(detach)
        if list(argv[1:]) == ["--version"]:
            return 0, "Python 3.9.6\n", ""
        a = argv
        if os.path.basename(a[0]) == "claude" and a[1] == "-p":
            self.claude_timeouts.append(timeout)
            return self.claude_reply(input_text if input_text is not None else a[2])
        if a[0] == "uname":
            return 0, self.uname + "\n", ""
        if a[0] == "schtasks":
            if a[1] == "/Create":
                return (1, "", "Access is denied.") if self.schtasks_fails else (0, "SUCCESS", "")
            if a[1] == "/Query":
                if not self.task_exists:
                    return 1, "", "ERROR: not found"
                if "/XML" in a:
                    return 0, "<Task><Actions><Exec><Command>%s</Command></Exec></Actions></Task>" % self.task_cmd, ""
                return 0, "", ""
            if a[1] == "/Delete":
                return (1, "", "Access is denied.") if self.delete_fails else (0, "", "")
            return 0, "", ""
        if a[0] == "cmd.exe":
            return (1, "", "boom") if self.window_fails else (0, "", "")
        if a[0] == "powershell.exe":
            if self.settings_fail and "Set-ScheduledTask" in a[-1]:
                return 1, "", "Access is denied."
            return 0, "", ""
        if a[0] == "launchctl":
            return (self.launchctl_list_rc if a[1] == "list" else 0), "", ""
        if a[0] == "osascript":
            return 0, "", ""
        if a[0] == "open":
            return (1, "", "boom") if self.window_fails else (0, "", "")
        if a[:3] == ["gh", "pr", "list"]:
            if self.gh_list_fails:
                return 1, "", "no network"
            return 0, json.dumps(self.prs), ""
        if a[:3] == ["gh", "pr", "view"]:
            if self.view_fails:
                return 1, "", "no network"
            return 0, json.dumps({"files": [{"path": p} for p in self.files.get(int(a[3]), [])]}), ""
        if a[0] == "git" and "fetch" in a:
            if self.fetch_fails or self.fail_fetch_refs & set(a):
                return 1, "", "no network"
            return 0, "", ""
        if a[0] == "git" and "show" in a:
            if self.show_fails:
                return 128, "", "bad object"
            ref, _, path = a[-1].partition(":")
            if (ref, path) in self.blobs:
                return 0, self.blobs[(ref, path)], ""
            return 128, "", "not found"
        if a[0].endswith("python3") or a[0].endswith("python"):
            return 0, "Python 3.9.6\n", ""
        raise AssertionError("unexpected outside call: %r" % (a,))

    def claude_reply(self, prompt):
        zid = re.search(r'meeting_number=(\d+)', prompt).group(1)
        r = self.zoom.get(zid)
        if isinstance(r, tuple) and r[0] == "raw":
            return 0, r[1], ""
        if isinstance(r, tuple) and r[0] == "rc":
            return r[1], "", r[2]
        if isinstance(r, tuple) and r[0] == "error":
            return 0, json.dumps({"result": "", "is_error": True, "total_cost_usd": 0.1}), ""
        return 0, json.dumps({"result": json.dumps(r), "is_error": False, "total_cost_usd": 0.18}), ""

    def attendance_calls(self):
        return [c for c in self.calls if os.path.basename(c[0][0]) == "claude"]

    def schtasks(self):
        return [c[0] for c in self.calls if c[0][0] == "schtasks"]

    def win_windows(self):
        return [c[0] for c in self.calls if c[0][0] == "cmd.exe"]

    def popups(self):
        return [c[0][-1] for c in self.calls if c[0][0] == "powershell.exe" and "Popup(" in c[0][-1]]

    def task_settings(self):
        return [c[0][-1] for c in self.calls if c[0][0] == "powershell.exe" and "Set-ScheduledTask" in c[0][-1]]

    def which_on(self, tool, path):
        self.which_paths.append((tool, path))
        for d in path.split(":"):
            if tool in self.tool_dirs.get(d, ()):
                return d + "/" + tool
        return None

    # --- fixtures
    def add_day_pr(self, date, number, state="OPEN", suffix="", adrs=()):
        branch = "digest/%s%s" % (date, suffix)
        self.prs.append({"number": number, "headRefName": branch, "state": state, "url": pr_url(number)})
        self.files[number] = ["README.md"] + [p for p, _ in adrs]
        ref = "origin/" + branch if state == "OPEN" else "origin/main"
        for p, text in adrs:
            self.blobs[(ref, p)] = text
        return branch

    def add_week_file(self, text, open_pr=True):
        fpath, branch = ds.week_names(dt.date(2026, 10, 14))
        assert fpath == "updates/2026-10-16-week-42.md" and branch == "weekly-update/2026-week-42"
        if open_pr:
            self.prs.append({"number": 900, "headRefName": branch, "state": "OPEN", "url": pr_url(900)})
            self.blobs[("origin/" + branch, fpath)] = text
        else:
            self.blobs[("origin/main", fpath)] = text

    # --- views of what happened
    def osa(self):
        return [c[0] for c in self.calls if c[0][0] == "osascript"]

    def windows(self):
        return [c[0] for c in self.calls if c[0][0] == "open"]

    def notes(self):
        return [a[2] for a in self.osa() if a[2].startswith("display notification")]

    def launchctl(self):
        return [c[0] for c in self.calls if c[0][0] == "launchctl"]




def home_env(path):
    """The env that points the home folder at path, on every OS.

    Path.home() reads HOME on macOS and Linux but USERPROFILE on Windows, so a
    test that set HOME alone wrote state.json and window-*.command files into
    the real home folder of whoever ran the suite on Windows.
    """
    return {"HOME": str(path), "USERPROFILE": str(path)}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        self.home.mkdir()
        self.world = World(self.home)
        env = {**home_env(self.home), "PATH": "/fake/bin:/usr/bin"}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for k in ("SCRIPTA_HANDBOOK_PATH", "CLAUDE_CONFIG_DIR"):
            os.environ.pop(k, None)
        # Fail here, before any write, if the temp home did not take on this OS.
        self.assertEqual(ds.home(), self.home, "the tests would write into the real home folder")
        for name, fn in (("run_cmd", self.world.run_cmd), ("which_on", self.world.which_on),
                         ("stdin_is_tty", lambda: False),
                         ("clock", lambda: dt.datetime(2026, 10, 14, 12, 0))):
            q = mock.patch.object(ds, name, fn)
            q.start()
            self.addCleanup(q.stop)
        self.handbook = self.make_handbook(self.home / "PROJECTS" / "hub-scripta-handbook")

    def make_handbook(self, path):
        path.mkdir(parents=True, exist_ok=True)
        (path / "where-truth-lives.md").write_text("map\n", encoding="utf-8")
        return path

    def set_state(self, meetings=(), **extra):
        state = {"meetings": [{"title": t, "days": d} for t, d in meetings],
                 "handbook": {"path": str(self.handbook), "source": "default"}}
        state.update(extra)
        ds.save_state(state)

    def state(self):
        return json.loads((self.home / ".scripta" / "digest-schedule" / "state.json").read_text())

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ds.main(list(argv))
        return code, out.getvalue()

    def run_at(self, iso, cmd="run"):
        return self.main(cmd, "--now", iso)[0]

    def prompt(self, date=TODAY):
        return (self.home / ".scripta" / "digest-schedule" / ("prompt-%s.txt" % date)).read_text()

    def plist(self):
        return plistlib.loads((self.home / "Library" / "LaunchAgents" / "blue.team.scripta.digest.plist").read_bytes())

    def give_prev_pr(self, date="2026-10-13", number=50):
        self.world.add_day_pr(date, number, "MERGED")


class RunGates(Base):
    def test_wednesday_noon_opens_one_window_and_records_today(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.give_prev_pr()
        self.assertEqual(self.run_at(WED), 0)
        self.assertEqual(len(self.world.windows()), 1)
        p = self.prompt()
        self.assertTrue(p.startswith("/scripta:daily-digest"))
        self.assertIn(TODAY, p)
        self.assertIn(str(self.handbook), p)
        self.assertIn(DAILY_SQ2, p)
        self.assertIn("noon schedule opened this window", p)
        self.assertEqual(self.state()["last_opened"], TODAY)

    def test_saturday_opens_nothing_and_says_nothing(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.run_at("2026-10-17T12:00")
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(self.world.notes(), [])

    def test_before_eleven_opens_nothing_and_does_not_record(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.run_at("2026-10-12T09:00")
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(self.world.notes(), [])
        self.assertNotIn("last_opened", self.state())

    def test_after_eighteen_posts_one_missed_notification(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.run_at("2026-10-13T19:30")
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(len(self.world.notes()), 1)
        self.assertIn("missed", self.world.notes()[0])
        self.assertNotIn("last_opened", self.state())

    def test_after_eighteen_is_silent_when_the_window_already_opened(self):
        self.set_state([], last_opened="2026-10-13")
        self.run_at("2026-10-13T19:30")
        self.assertEqual(self.world.notes(), [])

    def test_second_run_the_same_day_opens_nothing(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.run_at(WED)
        self.run_at("2026-10-14T15:00")
        self.assertEqual(len(self.world.windows()), 1)

    def test_missing_state_notifies_and_opens_nothing(self):
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(len(self.world.notes()), 1)
        self.assertIn("not set up", self.world.notes()[0])

    def test_handbook_missing_notifies_and_does_not_record(self):
        self.set_state([])
        (self.handbook / "where-truth-lives.md").unlink()
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])
        self.assertIn("handbook", self.world.notes()[0])
        self.assertNotIn("last_opened", self.state())

    def test_claude_not_on_path_notifies_by_name_and_does_not_record(self):
        self.set_state([])
        self.world.tool_dirs = {"/fake/bin": {"git", "gh"}}
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(len(self.world.notes()), 1)
        self.assertIn("claude", self.world.notes()[0])
        self.assertNotIn("last_opened", self.state())


class DoneCheck(Base):
    def test_all_meetings_on_an_open_day_pr_skips_and_names_the_pr(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4]), (DAILY_ALL, [0, 1, 2, 3, 4])])
        self.world.add_day_pr(TODAY, 61, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY)),
                                               ("decisions/b.md", adr_text(DAILY_ALL.upper(), TODAY))])
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(len(self.world.notes()), 1)
        self.assertIn(pr_url(61), self.world.notes()[0])
        self.assertNotIn("last_opened", self.state())

    def test_merged_day_pr_with_deleted_branch_reads_origin_main(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.world.add_day_pr(TODAY, 62, "MERGED", adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])
        self.assertIn(pr_url(62), self.world.notes()[0])
        shown = [c[0][-1] for c in self.world.calls if "show" in c[0]]
        self.assertTrue(all(s.startswith("origin/main:") for s in shown), shown)

    def test_a_suffixed_sibling_day_pr_counts(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.world.add_day_pr(TODAY, 63, suffix="-sq2", adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])

    def test_a_saved_title_that_is_a_prefix_of_another_meeting_does_not_count(self):
        self.set_state([("Hub - Daily", [0, 1, 2, 3, 4])])
        self.world.add_day_pr(TODAY, 65, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)

    def test_the_same_title_saved_twice_still_skips_when_done(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4]), (DAILY_SQ2, [2])])
        self.world.add_day_pr(TODAY, 66, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])

    def test_a_meeting_named_second_on_a_shared_source_line_counts(self):
        leads = "Hub - Daily - Leads"
        self.set_state([(leads, list(range(5)))])
        text = ("# A decision\n\n## Source\n%s, %s (both calls); %s, %s, 09:52:00\n"
                % (DAILY_ALL, TODAY, leads, TODAY))
        self.world.add_day_pr(TODAY, 69, adrs=[("decisions/a.md", text)])
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])

    def test_saved_meetings_but_none_today_opens_nothing(self):
        self.set_state([(DAILY_SQ2, [1, 2, 3, 4])])
        self.run_at("2026-10-12T12:00")
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(self.world.notes(), [])
        self.assertEqual(self.state()["last_run"]["outcome"], "skipped: no saved meeting today")

    def test_partly_done_through_the_week_file_names_where_it_was_found(self):
        self.set_state([(DAILY_SQ2, list(range(5))), (DAILY_ALL, list(range(5)))])
        self.give_prev_pr()
        self.world.add_week_file("### %s \u00b7 %s\n- x\n" % (TODAY, DAILY_SQ2))
        self.run_at(WED)
        p = self.prompt()
        self.assertIn(pr_url(900), p)
        self.assertNotIn("digest  already", p)
        self.assertIn("Still missing: %s." % DAILY_ALL, p)

    def test_week_block_alone_counts_as_done(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.world.add_day_pr(TODAY, 64, adrs=[])
        self.world.add_week_file("# Week 42\n\n### %s \u00b7 %s\n- Nothing finished was reported.\n" % (TODAY, DAILY_SQ2))
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(len(self.world.notes()), 1)

    def test_week_block_is_read_from_main_when_the_week_pr_merged(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.world.add_week_file("### %s \u00b7 %s\n- x\n" % (TODAY, DAILY_SQ2), open_pr=False)
        self.run_at(WED)
        self.assertEqual(self.world.windows(), [])

    def test_a_week_block_for_another_day_does_not_count(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.world.add_week_file("### 2026-10-13 \u00b7 %s\n- x\n" % DAILY_SQ2)
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)

    def test_two_of_three_found_opens_and_names_pr_and_the_missing_one(self):
        third = "Hub - Retro - All"
        self.set_state([(DAILY_SQ2, list(range(5))), (DAILY_ALL, list(range(5))), (third, list(range(5)))])
        self.give_prev_pr()
        self.world.add_day_pr(TODAY, 65, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY)),
                                               ("decisions/b.md", adr_text(DAILY_ALL, TODAY))])
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)
        p = self.prompt()
        self.assertIn(pr_url(65), p)
        self.assertRegex(p, r"Still missing: %s\." % re.escape(third))
        self.assertEqual(self.state()["last_opened"], TODAY)

    def test_adrs_dated_yesterday_leave_todays_meetings_missing(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.give_prev_pr()
        self.world.add_day_pr(TODAY, 66, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, "2026-10-13"))])
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)
        p = self.prompt()
        self.assertIn(pr_url(66), p)
        self.assertIn("none of these meetings: %s" % DAILY_SQ2, p)

    def test_no_saved_meetings_always_opens_even_with_a_full_day_pr(self):
        self.set_state([])
        self.give_prev_pr()
        self.world.add_day_pr(TODAY, 67, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn("today's team meetings: the dailies, and on Mondays the squad planning", self.prompt())

    def test_monday_expects_planning_not_a_tuesday_to_friday_daily(self):
        self.set_state([(DAILY_SQ2, [1, 2, 3, 4]), (PLANNING, [0])])
        mon = "2026-10-12"
        self.world.add_day_pr("2026-10-09", 40, "MERGED")
        self.world.add_day_pr(mon, 68, adrs=[("decisions/a.md", adr_text(PLANNING, mon))])
        self.run_at(mon + "T12:00")
        self.assertEqual(self.world.windows(), [], "planning is done and the Tue-Fri daily is not expected on Monday")
        # the planning is missing: the window opens and names only Monday's meeting
        w2 = World(self.home)
        w2.prs = [p for p in self.world.prs if p["number"] != 68]
        w2.files = dict(self.world.files)
        with mock.patch.object(ds, "run_cmd", w2.run_cmd), mock.patch.object(ds, "which_on", w2.which_on):
            st = self.state()
            st.pop("last_run", None)
            ds.save_state(st)
            self.run_at(mon + "T12:00")
        self.assertEqual(len(w2.windows()), 1)
        p = self.prompt(mon)
        self.assertIn(PLANNING, p)
        self.assertNotIn(DAILY_SQ2, p)

    def test_gh_failure_opens_anyway_says_so_and_records(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.world.gh_list_fails = True
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn("could not be checked", self.prompt())
        self.assertEqual(self.state()["last_opened"], TODAY)

    def test_git_fetch_failure_opens_anyway_says_so_and_records(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.world.fetch_fails = True
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn("could not be checked", self.prompt())
        self.assertEqual(self.state()["last_opened"], TODAY)

    def check_fails_open(self):
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn("could not be checked", self.prompt())
        self.assertEqual(self.state()["last_opened"], TODAY)

    def test_gh_pr_view_failure_opens_anyway(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.world.add_day_pr(TODAY, 70, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.world.view_fails = True
        self.check_fails_open()

    def test_reading_an_adr_failure_opens_anyway(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.world.add_day_pr(TODAY, 71, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.world.show_fails = True
        self.check_fails_open()

    def test_fetching_the_open_day_pr_branch_failure_opens_anyway(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        branch = self.world.add_day_pr(TODAY, 72, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.world.fail_fetch_refs = {branch}
        self.check_fails_open()

    def test_fetching_the_week_branch_failure_opens_anyway(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.world.add_week_file("### %s \u00b7 %s\n- x\n" % (TODAY, DAILY_SQ2))
        self.world.fail_fetch_refs = {"weekly-update/2026-week-42"}
        self.check_fails_open()

    def test_the_gh_list_runs_in_the_handbook_and_asks_for_all_states(self):
        self.set_state([])
        self.run_at(WED)
        listing = [c for c in self.world.calls if c[0][:3] == ["gh", "pr", "list"]]
        self.assertEqual(len(listing), 1)
        argv, cwd = listing[0]
        self.assertEqual(cwd, str(self.handbook))
        self.assertIn("all", argv)
        self.assertIn("number,headRefName,state,url", argv)


class PreviousWeekday(Base):
    def test_no_pr_for_the_previous_weekday_is_named_but_only_today_is_digested(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.run_at(WED)
        p = self.prompt()
        self.assertIn("2026-10-13, has no digest PR", p)
        self.assertIn("Digest only today's meetings", p)
        self.assertIn(DAILY_SQ2, p)

    def test_monday_looks_at_friday(self):
        self.set_state([])
        self.run_at("2026-10-12T12:00")
        self.assertIn("2026-10-09, has no digest PR", self.prompt("2026-10-12"))

    def test_a_merged_previous_day_pr_with_deleted_branch_is_not_called_missed(self):
        self.set_state([])
        self.give_prev_pr()
        self.run_at(WED)
        self.assertNotIn("has no digest PR", self.prompt())

    def test_a_closed_unmerged_previous_day_pr_does_not_count(self):
        self.set_state([])
        self.world.add_day_pr("2026-10-13", 51, "CLOSED")
        self.run_at(WED)
        self.assertIn("2026-10-13, has no digest PR", self.prompt())

    def test_nothing_is_claimed_about_the_previous_day_when_the_check_failed(self):
        self.set_state([])
        self.world.gh_list_fails = True
        self.run_at(WED)
        self.assertNotIn("has no digest PR", self.prompt())


class Window(Base):
    def open_with(self, handbook, config_dir=None):
        self.handbook = handbook
        extra = {"claude_config_dir": config_dir} if config_dir else {}
        self.set_state([], **extra)
        self.run_at(WED)
        return self.world.windows()[0]

    def script_arg(self, open_argv):
        return Path(open_argv[-1]).read_text(encoding="utf-8")

    def run_in_shell(self, cmd, out_dir):
        """Run the window command in sh with a fake claude that records what it got."""
        fake = Path(out_dir) / "bin"
        fake.mkdir()
        claude = fake / "claude"
        claude.write_text('#!/bin/sh\npwd -P > "$REC.cwd"\nprintf %s "$1" > "$REC.arg"\n'
                          'printf %s "${CLAUDE_CONFIG_DIR-unset}" > "$REC.cfg"\n')
        claude.chmod(0o755)
        rec = str(Path(out_dir) / "rec")
        env = {"PATH": "%s:/usr/bin:/bin" % fake, "REC": rec, **home_env(self.home)}
        subprocess.run(["sh", "-c", cmd], env=env, check=True)
        return (Path(rec + ".cwd").read_text().strip(), Path(rec + ".arg").read_text(),
                Path(rec + ".cfg").read_text())

    def test_a_handbook_path_with_a_space_and_a_quote_reaches_the_shell_as_one_path(self):
        weird = self.make_handbook(self.home / "PROJECTS" / "my hand's \"book\"")
        opened = self.open_with(weird)
        cmd = self.script_arg(opened)
        cwd, arg, cfg = self.run_in_shell(cmd, self.tmp.name)
        self.assertEqual(cwd, str(weird))
        self.assertEqual(arg, self.prompt().rstrip("\n"))  # $(cat) drops the last newline
        self.assertEqual(opened[:3], ["open", "-a", "Terminal"])

    def test_the_window_is_a_script_file_terminal_opens_without_apple_events(self):
        # A launchd job that asks for control of Terminal hangs or is refused
        # (seen on 2026-10-15). open -a needs no Automation permission.
        opened = self.open_with(self.handbook)
        script = Path(opened[-1])
        self.assertEqual(script.parent, ds.state_dir())
        self.assertEqual(script.name, "window-%s.command" % TODAY)
        self.assertTrue(os.access(str(script), os.X_OK))
        self.assertTrue(script.read_text(encoding="utf-8").startswith("#!/bin/bash\n"))
        self.assertFalse([a for a in self.world.osa() if any("do script" in x for x in a)])

    def test_a_saved_claude_config_dir_is_exported(self):
        cmd = self.script_arg(self.open_with(self.handbook, config_dir="/Users/x/claude profile"))
        _, _, cfg = self.run_in_shell(cmd, self.tmp.name)
        self.assertEqual(cfg, "/Users/x/claude profile")

    def test_without_a_saved_claude_config_dir_the_command_never_mentions_it(self):
        cmd = self.script_arg(self.open_with(self.handbook))
        self.assertNotIn("CLAUDE_CONFIG_DIR", cmd)

    def test_a_window_that_does_not_open_notifies_the_command_to_run_by_hand(self):
        self.world.window_fails = True
        self.set_state([])
        self.run_at(WED)
        notes = self.world.notes()
        self.assertEqual(len(notes), 1)
        self.assertIn("by hand", notes[0])
        self.assertIn("exec claude", notes[0])
        self.assertIn(str(self.handbook), notes[0])
        st = self.state()
        self.assertNotIn("last_opened", st)
        self.assertEqual(st["last_run"]["outcome"], "failed: window did not open")

    def test_a_later_run_the_same_day_tries_again_after_a_failed_open(self):
        self.world.window_fails = True
        self.set_state([])
        self.run_at(WED)
        self.world.window_fails = False
        self.run_at("2026-10-14T13:00")
        self.assertEqual(len(self.world.windows()), 2)
        self.assertEqual(self.state()["last_opened"], TODAY)


class TryCommand(Base):
    def test_try_on_a_sunday_at_eight_opens_and_does_not_record(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.run_at("2026-10-18T08:00", "try")
        self.assertEqual(len(self.world.windows()), 1)
        self.assertNotIn("last_opened", self.state())
        self.assertNotIn("last_run", self.state())

    def test_try_opens_again_even_after_a_real_window_opened_today(self):
        self.set_state([], last_opened=TODAY)
        self.run_at(WED, "try")
        self.assertEqual(len(self.world.windows()), 1)

    def test_try_when_today_is_done_still_opens_and_names_the_pr(self):
        self.set_state([(DAILY_SQ2, list(range(5)))])
        self.world.add_day_pr(TODAY, 70, adrs=[("decisions/a.md", adr_text(DAILY_SQ2, TODAY))])
        self.run_at(WED, "try")
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn(pr_url(70), self.prompt())
        self.assertNotIn("last_opened", self.state())

    def test_try_still_needs_claude(self):
        self.set_state([])
        self.world.tool_dirs = {"/fake/bin": {"git", "gh"}}
        self.run_at(WED, "try")
        self.assertEqual(self.world.windows(), [])
        self.assertIn("claude", self.world.notes()[0])

    def test_try_still_needs_the_handbook(self):
        self.set_state([])
        (self.handbook / "where-truth-lives.md").unlink()
        self.run_at(WED, "try")
        self.assertEqual(self.world.windows(), [])
        self.assertEqual(len(self.world.notes()), 1)


class Install(Base):
    def install(self, *meetings):
        argv = ["install"]
        for m in meetings:
            argv += ["--meeting", m]
        return self.main(*argv)

    def test_install_writes_the_plist_state_and_reloads(self):
        code, out = self.install()
        self.assertEqual(code, 0)
        pl = self.plist()
        self.assertEqual(pl["Label"], "blue.team.scripta.digest")
        self.assertEqual(pl["StartCalendarInterval"],
                         [{"Weekday": d, "Hour": 12, "Minute": 0} for d in (1, 2, 3, 4, 5)])
        h = str(self.home)
        self.assertEqual(pl["EnvironmentVariables"]["PATH"],
                         "%s/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" % h)
        self.assertNotIn("CLAUDE_CONFIG_DIR", pl["EnvironmentVariables"])
        self.assertEqual(pl["ProgramArguments"][:3], ["/usr/bin/env", "python3", "-c"])
        self.assertEqual(pl["ProgramArguments"][3], ds.LOADER)
        log = "%s/.scripta/digest-schedule/schedule.log" % h
        self.assertEqual((pl["StandardOutPath"], pl["StandardErrorPath"]), (log, log))
        plist_path = "%s/Library/LaunchAgents/blue.team.scripta.digest.plist" % h
        self.assertEqual(self.world.launchctl()[:2],
                         [["launchctl", "unload", plist_path], ["launchctl", "load", plist_path]])
        st = self.state()
        self.assertEqual(st["handbook"], {"path": str(self.handbook), "source": "default"})
        self.assertIn("try", out)

    def test_install_refuses_a_handbook_override_without_the_marker_file(self):
        empty = self.home / "elsewhere"
        empty.mkdir()
        os.environ["SCRIPTA_HANDBOOK_PATH"] = str(empty)
        code, out = self.install()
        self.assertEqual(code, 1)
        self.assertIn("handbook_path", out)
        self.assertFalse((self.home / ".scripta").exists())
        self.assertFalse((self.home / "Library").exists())
        self.assertEqual(self.world.launchctl(), [])

    def test_an_msys_python_on_windows_is_told_to_use_the_windows_one(self):
        self.world.uname = "MINGW64_NT-10.0-22631"
        code, out = self.install()
        self.assertEqual(code, 1)
        self.assertIn("py -3", out)
        self.assertFalse((self.home / ".scripta").exists())

    def test_install_refuses_off_macos_and_writes_nothing(self):
        self.world.uname = "Linux"
        code, out = self.install()
        self.assertEqual(code, 1)
        self.assertIn("macOS", out)
        self.assertFalse((self.home / ".scripta").exists())
        self.assertFalse((self.home / "Library").exists())
        self.assertEqual(self.world.launchctl(), [])

    def test_install_twice_leaves_one_plist_and_updates_state(self):
        self.install("%s=mon" % PLANNING)
        code, _ = self.install("%s=tue-fri" % DAILY_SQ2)
        self.assertEqual(code, 0)
        self.assertEqual(len(list((self.home / "Library" / "LaunchAgents").iterdir())), 1)
        self.assertEqual(self.state()["meetings"], [{"title": DAILY_SQ2, "days": [1, 2, 3, 4]}])
        self.assertEqual(len([c for c in self.world.launchctl() if c[1] == "load"]), 2)

    def test_install_keeps_the_recorded_day_so_a_reinstall_does_not_reopen(self):
        self.set_state([], last_opened=TODAY)
        self.install()
        self.assertEqual(self.state()["last_opened"], TODAY)

    def test_install_with_three_meetings_saves_them_and_status_lists_them(self):
        self.install("%s=tue-fri" % DAILY_SQ2, "%s=mon" % PLANNING, DAILY_ALL)
        self.assertEqual(self.state()["meetings"], [
            {"title": DAILY_SQ2, "days": [1, 2, 3, 4]},
            {"title": PLANNING, "days": [0]},
            {"title": DAILY_ALL, "days": [0, 1, 2, 3, 4]}])
        _, out = self.main("status")
        self.assertIn("%s (tue,wed,thu,fri)" % DAILY_SQ2, out)
        self.assertIn("%s (mon)" % PLANNING, out)
        self.assertIn("%s (mon,tue,wed,thu,fri)" % DAILY_ALL, out)

    def test_install_with_no_meetings_warns_and_installs(self):
        code, out = self.install()
        self.assertEqual(code, 0)
        self.assertIn("open every weekday", out)
        self.assertEqual(self.state()["meetings"], [])

    def test_reinstall_with_no_meetings_off_a_terminal_keeps_the_saved_ones(self):
        self.install("%s=tue-fri" % DAILY_SQ2)
        code, out = self.install()
        self.assertEqual(code, 0)
        self.assertEqual(self.state()["meetings"], [{"title": DAILY_SQ2, "days": [1, 2, 3, 4]}])
        self.assertIn("Keeping the saved meetings", out)

    def test_a_bad_meeting_argument_exits_2_and_writes_nothing(self):
        code, out = self.install("%s=funday" % DAILY_SQ2)
        self.assertEqual(code, 2)
        self.assertFalse((self.home / "Library").exists())

    def test_install_asks_for_meetings_on_a_terminal_when_none_are_given(self):
        answers = iter([DAILY_SQ2, "funday", "tue-fri", "", PLANNING, "mon", "", ""])
        with mock.patch.object(ds, "stdin_is_tty", lambda: True), \
                mock.patch.object(ds, "ask", lambda prompt: next(answers)):
            code, _ = self.install()
        self.assertEqual(code, 0)
        self.assertEqual(self.state()["meetings"], [{"title": DAILY_SQ2, "days": [1, 2, 3, 4]},
                                                    {"title": PLANNING, "days": [0]}])

    def test_install_never_asks_when_meetings_are_given(self):
        def boom(prompt):
            raise AssertionError("asked")
        with mock.patch.object(ds, "stdin_is_tty", lambda: True), mock.patch.object(ds, "ask", boom):
            self.assertEqual(self.install("%s=mon" % PLANNING)[0], 0)

    def test_claude_config_dir_set_at_install_goes_into_plist_and_state(self):
        os.environ["CLAUDE_CONFIG_DIR"] = "/Users/x/.claude-work"
        self.install()
        self.assertEqual(self.plist()["EnvironmentVariables"]["CLAUDE_CONFIG_DIR"], "/Users/x/.claude-work")
        self.assertEqual(self.state()["claude_config_dir"], "/Users/x/.claude-work")

    def test_state_is_written_through_a_temp_file_and_renamed(self):
        self.set_state([])
        names = sorted(p.name for p in (self.home / ".scripta" / "digest-schedule").iterdir())
        self.assertEqual(names, ["state.json"])


TEAM_DAILY = "Team - Daily"
MAIN_PERSON = "Alex Main"
TEAM_DAILY_SPEC = "%s=tue-fri;backup-for=%s;zoom=12345678901" % (TEAM_DAILY, MAIN_PERSON)


def call(date="2026-10-14", attendees=("Sam O'Brien", "Kim Lee"), hour="08:00:00",
         finished=True, end="08:30:00"):
    # The tests' clock is 12:00 local on 2026-10-14, well after an 08:30 UTC end in Europe and in UTC.
    return {"topic": "Team - Daily", "start_time": "%sT%sZ" % (date, hour),
            "end_time": ("%sT%sZ" % (date, end)) if finished else None,
            "finished": finished, "attendees": list(attendees)}


class Spec(unittest.TestCase):
    def test_old_specs_are_unchanged(self):
        self.assertEqual(ds.parse_meeting("Hub - Daily - Sq2=tue-fri"),
                         {"title": "Hub - Daily - Sq2", "days": [1, 2, 3, 4]})
        self.assertEqual(ds.parse_meeting("Hub - Daily - All"),
                         {"title": "Hub - Daily - All", "days": [0, 1, 2, 3, 4]})

    def test_backup_parts(self):
        self.assertEqual(ds.parse_meeting(TEAM_DAILY_SPEC),
                         {"title": TEAM_DAILY, "days": [1, 2, 3, 4], "backup_for": MAIN_PERSON, "zoom_id": "12345678901"})
        self.assertEqual(ds.parse_meeting("%s;zoom=5;backup-for=A B" % TEAM_DAILY)["backup_for"], "A B")

    def test_a_title_with_a_semicolon_still_works(self):
        self.assertEqual(ds.parse_meeting("Sync; Sq1=mon")["title"], "Sync; Sq1")

    def test_errors(self):
        for bad, word in (("%s=mon;backup-for=Alex" % TEAM_DAILY, "Zoom meeting number"),
                          ("%s=mon;backup-for=Alex;zoom=abc" % TEAM_DAILY, "numeric"),
                          ("%s=mon;backup-for=;zoom=1" % TEAM_DAILY, "backup-for"),
                          ("%s=mon;zoom=1;zoom=2" % TEAM_DAILY, "twice")):
            with self.assertRaises(ValueError) as cm:
                ds.parse_meeting(bad)
            self.assertIn(word, str(cm.exception))


class Attendance(Base):
    def setUp(self):
        super().setUp()
        q = mock.patch("sys.stdout", io.StringIO())  # the decision lines are logged to stdout
        q.start()
        self.addCleanup(q.stop)
        self.world.zoom["12345678901"] = call()

    def backup_state(self, **extra):
        ds.save_state({"meetings": [{"title": TEAM_DAILY, "days": [0, 1, 2, 3, 4], "backup_for": MAIN_PERSON,
                                     "zoom_id": "12345678901"}],
                       "handbook": {"path": str(self.handbook), "source": "default"}, **extra})

    def att(self, name=MAIN_PERSON, day=dt.date(2026, 10, 14)):
        return ds.check_attendance("12345678901", name, day)

    def test_main_person_in_attendees_is_present_ignoring_case_spaces_and_accents(self):
        self.world.zoom["12345678901"] = call(attendees=("alex  MAIN", "Sam O'Brien"))
        self.assertEqual(self.att(), "present")
        self.world.zoom["12345678901"] = call(attendees=("Àlex Máin",))
        self.assertEqual(self.att(), "present")

    def test_present_even_when_the_call_is_still_running(self):
        self.world.zoom["12345678901"] = call(attendees=(MAIN_PERSON,), finished=False)
        self.assertEqual(self.att(), "present")

    def test_absent_when_finished_and_not_in_attendees(self):
        self.assertEqual(self.att(), "absent")

    def test_not_yet_when_still_running_and_not_in_attendees(self):
        self.world.zoom["12345678901"] = call(finished=False)
        self.assertEqual(self.att(), "not_yet")

    def test_not_yet_when_no_call_today(self):
        self.world.zoom["12345678901"] = call(date="2026-10-13")
        self.assertEqual(self.att(), "not_yet")
        self.world.zoom["12345678901"] = {"attendees": [], "reason": "no call today yet"}
        self.assertEqual(self.att(), "not_yet")
        self.world.zoom["12345678901"] = call(attendees=())
        self.assertEqual(self.att(), "not_yet")

    def test_absent_only_ten_minutes_after_the_call_ended(self):
        noon = dt.datetime(2026, 10, 14, 12, 0).astimezone()  # the tests' clock
        for minutes_ago, want in ((5, "not_yet"), (15, "absent")):
            end = (noon - dt.timedelta(minutes=minutes_ago)).astimezone(dt.timezone.utc)
            self.world.zoom["12345678901"] = call(end=end.strftime("%H:%M:%S"))
            self.assertEqual(self.att(), want, minutes_ago)

    def test_an_unreadable_end_time_is_not_finished(self):
        reply = call()
        reply["end_time"] = "null"
        self.world.zoom["12345678901"] = reply
        self.assertEqual(self.att(), "not_yet")

    def test_access_failure_in_the_reason_is_an_error(self):
        self.world.zoom["12345678901"] = {"attendees": [], "reason": "403 Permission denied"}
        d = ds.attendance_detail("12345678901", MAIN_PERSON, dt.date(2026, 10, 14))
        self.assertEqual((d["status"], d["permission"]), ("error", True))

    def test_a_tool_error_is_an_error(self):
        self.world.zoom["12345678901"] = {"attendees": [], "error": "search failed"}
        self.assertEqual(self.att(), "error")

    def test_failures_are_errors(self):
        for reply in ({"attendees": [], "error": "403 Permission denied"},
                      ("rc", 127, "timed out"), ("raw", "not json"),
                      ("raw", json.dumps({"result": "sorry, no", "is_error": False})),
                      ("error",)):
            self.world.zoom["12345678901"] = reply
            self.assertEqual(self.att(), "error", reply)

    def test_norm_name_folds_accents(self):
        self.assertEqual(ds.norm_name("  León  GARCÍA "), ds.norm_name("Leon Garcia"))

    def test_no_claude_is_an_error(self):
        self.world.tool_dirs = {}
        self.assertEqual(self.att(), "error")
        self.assertEqual(self.world.attendance_calls(), [])

    def test_the_command_timeout_cwd_and_log(self):
        self.att()
        argv, cwd = self.world.attendance_calls()[0]
        self.assertEqual(self.world.claude_timeouts, [180])
        self.assertEqual(cwd, str(self.home / ".scripta" / "digest-schedule"))
        self.assertEqual(argv[3:5], ["--model", "sonnet"])
        self.assertIn("search_meetings", argv[6])
        self.assertEqual(argv[-2:], ["--output-format", "json"])

    def test_the_prompt_names_the_tool_number_utc_day_and_zone(self):
        self.att()
        prompt = self.world.attendance_calls()[0][0][2]
        start, end, zone = ds.day_window_utc(dt.date(2026, 10, 14))
        for want in ("search_meetings", "meeting_number=12345678901", 'from="%s"' % start,
                     'to="%s"' % end, zone, "time zone", "attendees", "user_name", "union"):
            self.assertIn(want, prompt)
        self.assertRegex(start, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertNotIn("get_meeting_assets", prompt)

    def test_decision_and_cost_are_logged(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.att()
        self.assertIn("attendance cost: $0.18", out.getvalue())
        self.assertIn("absent", out.getvalue())

    # --- run_digest

    def test_main_person_present_skips_and_opens_nothing(self):
        self.world.zoom["12345678901"] = call(attendees=(MAIN_PERSON,))
        self.backup_state()
        out = self.main("run", "--now", WED)[1]
        self.assertEqual(self.world.windows(), [])
        self.assertIn("skipped: %s was in %s" % (MAIN_PERSON, TEAM_DAILY), out)
        self.assertEqual(self.state()["concluded"], TODAY)
        self.run_at("2026-10-14T12:30")
        self.assertEqual(len(self.world.attendance_calls()), 1)

    def test_main_person_absent_opens_with_the_backup_line(self):
        self.backup_state()
        self.run_at(WED)
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn("%s was not in %s today, so this is your summary as backup." % (MAIN_PERSON, TEAM_DAILY),
                      self.prompt())
        self.assertEqual(self.state()["last_opened"], TODAY)

    def test_not_yet_before_17_waits_and_records_pending(self):
        self.world.zoom["12345678901"] = call(date="2026-10-13")
        self.backup_state()
        self.run_at("2026-10-14T16:55")
        self.assertEqual(self.world.windows(), [])
        self.assertNotIn("last_opened", self.state())
        self.assertTrue(self.state()["last_run"]["outcome"].startswith("waiting"))
        self.world.zoom["12345678901"] = call()
        self.run_at("2026-10-14T17:00")   # a later run tries again
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn("was not in", self.prompt())

    def test_not_yet_at_17_05_opens_with_the_could_not_tell_line(self):
        self.world.zoom["12345678901"] = call(date="2026-10-13")
        self.backup_state()
        self.run_at("2026-10-14T17:05")
        self.assertEqual(len(self.world.windows()), 1)
        p = self.prompt()
        self.assertIn("could not tell whether %s was in %s" % (MAIN_PERSON, TEAM_DAILY), p)
        self.assertNotIn("so this is your summary as backup", p)

    def test_errors_wait_like_not_yet_and_open_at_17(self):
        for reply in ({"present": None, "reason": "403 Permission denied"},
                      ("rc", 127, "timed out"), ("raw", "not json")):
            self.world.zoom["12345678901"] = reply
            self.backup_state()
            self.world.calls.clear()
            self.run_at("2026-10-14T13:00")
            self.assertEqual(self.world.windows(), [], reply)
            self.run_at("2026-10-14T17:00")
            self.assertEqual(len(self.world.windows()), 1, reply)
            self.assertIn("could not tell", self.prompt())
            self.backup_state()  # reset last_opened for the next reply

    def test_a_backup_meeting_already_in_the_digest_is_not_checked(self):
        self.world.add_day_pr(TODAY, 77, adrs=[("decisions/0001-x.md", adr_text(TEAM_DAILY, TODAY))])
        self.backup_state()
        self.run_at(WED)
        self.assertEqual(self.world.attendance_calls(), [])
        self.assertEqual(self.world.windows(), [])

    def test_a_main_only_meeting_next_to_a_backup_one_is_never_checked(self):
        self.set_state([(DAILY_ALL, [0, 1, 2, 3, 4])])
        st = self.state()
        st["meetings"].append({"title": TEAM_DAILY, "days": [0, 1, 2, 3, 4], "backup_for": MAIN_PERSON,
                               "zoom_id": "12345678901"})
        ds.save_state(st)
        self.world.zoom["12345678901"] = call(attendees=(MAIN_PERSON,))
        self.run_at(WED)
        self.assertEqual(len(self.world.attendance_calls()), 1)
        self.assertEqual(len(self.world.windows()), 1)
        self.assertIn(DAILY_ALL, self.prompt())
        self.assertNotIn(TEAM_DAILY, self.prompt())

    def test_main_install_never_calls_claude_p(self):
        self.set_state([(DAILY_SQ2, [0, 1, 2, 3, 4])])
        self.run_at(WED)
        self.assertEqual(self.world.attendance_calls(), [])

    # --- plist, install, status, check

    def test_plist_has_retries_only_for_a_backup_install(self):
        self.main("install", "--meeting", "%s=tue-fri" % DAILY_SQ2)
        self.assertEqual(len(self.plist()["StartCalendarInterval"]), 5)
        self.main("install", "--meeting", TEAM_DAILY_SPEC)
        iv = self.plist()["StartCalendarInterval"]
        self.assertEqual(len(iv), 5 * 11)
        mon = [(i["Hour"], i["Minute"]) for i in iv if i["Weekday"] == 1]
        self.assertEqual(mon[0], (12, 0))
        self.assertEqual(mon[1], (12, 30))
        self.assertEqual(mon[-1], (17, 0))

    def test_install_prints_the_check_and_status_names_the_backup(self):
        code, out = self.main("install", "--meeting", TEAM_DAILY_SPEC)
        self.assertEqual(code, 0)
        self.assertIn("%s: your Zoom can see who joined meeting 12345678901 in the last 7 days" % TEAM_DAILY, out)
        self.assertIn("(backup for %s, Zoom 12345678901)" % MAIN_PERSON, out)
        self.assertEqual(self.state()["meetings"][0]["zoom_id"], "12345678901")

    def test_install_without_zoom_is_refused(self):
        code, out = self.main("install", "--meeting", "%s=mon;backup-for=%s" % (TEAM_DAILY, MAIN_PERSON))
        self.assertEqual(code, 2)
        self.assertIn("Zoom meeting number", out)

    def test_install_asks_for_the_backup_on_a_terminal(self):
        answers = iter([TEAM_DAILY, "tue-fri", MAIN_PERSON, "abc", "12345678901", ""])
        with mock.patch.object(ds, "stdin_is_tty", lambda: True), \
                mock.patch.object(ds, "ask", lambda prompt: next(answers)):
            self.main("install")
        self.assertEqual(self.state()["meetings"],
                         [{"title": TEAM_DAILY, "days": [1, 2, 3, 4], "backup_for": MAIN_PERSON, "zoom_id": "12345678901"}])

    def test_check_sentences(self):
        self.backup_state()
        self.world.zoom["12345678901"] = call(date="2026-10-09", attendees=(MAIN_PERSON, "X"))
        out = self.main("check")[1]
        self.assertIn("%s: your Zoom can see who joined meeting 12345678901 in the last 7 days, "
                      "and %s is among them." % (TEAM_DAILY, MAIN_PERSON), out)
        self.world.zoom["12345678901"] = call(date="2026-10-09")
        self.assertIn("but %s is not among them. Check that the name matches their Zoom name." % MAIN_PERSON,
                      self.main("check")[1])
        self.world.zoom["12345678901"] = {"attendees": [], "error": "403 Permission denied"}
        out = self.main("check")[1]
        self.assertIn("%s: your Zoom cannot open this call (permission denied). "
                      "Ask the host for access." % TEAM_DAILY, out)
        self.world.zoom["12345678901"] = {"attendees": [], "reason": "no call found"}
        self.assertIn("found no call for meeting 12345678901 in the last 7 days (no call found). Check the "
                      "meeting number and that you joined the call.", self.main("check")[1])
        self.assertEqual(self.world.windows(), [])

    def test_check_looks_back_seven_days_and_run_only_today(self):
        self.backup_state()
        self.main("check")
        week_from = ds.day_window_utc(dt.date(2026, 10, 14), 7)[0]
        today_from = ds.day_window_utc(dt.date(2026, 10, 14))[0]
        self.assertIn('from="%s"' % week_from, self.world.attendance_calls()[0][0][2])
        self.att()
        self.assertIn('from="%s"' % today_from, self.world.attendance_calls()[1][0][2])
        self.assertNotEqual(week_from, today_from)

    def test_the_week_check_names_the_earliest_call_not_the_latest(self):
        self.world.zoom["12345678901"] = call(date="2026-10-09", attendees=(MAIN_PERSON,))
        week = ds.attendance_detail("12345678901", MAIN_PERSON, dt.date(2026, 10, 14), days_back=7)
        self.assertEqual(week["reason"], "calls found in the last 7 days, the earliest on 2026-10-09")
        today = ds.attendance_detail("12345678901", MAIN_PERSON, dt.date(2026, 10, 14))
        self.assertEqual(today["reason"], "latest call is from 2026-10-09, not today")

    def test_access_wordings_in_the_reason_are_errors(self):
        for reason in ("Insufficient permissions to view this meeting", "Access denied",
                       "401 Unauthorized", "HTTP 403"):
            self.world.zoom["12345678901"] = {"attendees": [], "reason": reason}
            d = ds.attendance_detail("12345678901", MAIN_PERSON, dt.date(2026, 10, 14))
            self.assertEqual((d["status"], d["permission"]), ("error", True), reason)

    def test_a_403_inside_a_number_is_not_an_access_error(self):
        self.world.zoom["12345678901"] = {"attendees": [], "reason": "no call for 14031234"}
        self.assertEqual(self.att(), "not_yet")

    def test_check_with_no_backup_meeting_says_so(self):
        self.set_state([(DAILY_SQ2, [1])])
        self.assertIn("No backup meetings", self.main("check")[1])
        self.assertEqual(self.world.attendance_calls(), [])


class HandbookParity(unittest.TestCase):
    """KTD6: the script's lookup and the hook's lookup give the same answer."""

    def scenarios(self):
        def hb(home, rel):
            p = home / rel
            p.mkdir(parents=True, exist_ok=True)
            (p / "where-truth-lives.md").write_text("x")
            return p

        def cfg(home, value):
            c = home / ".config" / "scripta"
            c.mkdir(parents=True)
            (c / "config.json").write_text(json.dumps({"handbook_path": value}))

        def nothing(home, env):
            pass

        def default_new(home, env):
            hb(home, "PROJECTS/hub-scripta-handbook")

        def default_old(home, env):
            hb(home, "PROJECTS/scripta")

        def both_defaults(home, env):
            hb(home, "PROJECTS/hub-scripta-handbook")
            hb(home, "PROJECTS/scripta")

        def env_valid(home, env):
            env["SCRIPTA_HANDBOOK_PATH"] = str(hb(home, "elsewhere"))

        def env_invalid_default_valid(home, env):
            hb(home, "PROJECTS/hub-scripta-handbook")
            (home / "empty").mkdir()
            env["SCRIPTA_HANDBOOK_PATH"] = str(home / "empty")

        def config_valid(home, env):
            cfg(home, str(hb(home, "elsewhere")))

        def config_invalid_default_valid(home, env):
            hb(home, "PROJECTS/hub-scripta-handbook")
            (home / "empty").mkdir()
            cfg(home, str(home / "empty"))

        def env_beats_config(home, env):
            env["SCRIPTA_HANDBOOK_PATH"] = str(hb(home, "from-env"))
            cfg(home, str(hb(home, "from-config")))

        return [nothing, default_new, default_old, both_defaults, env_valid, env_invalid_default_valid,
                config_valid, config_invalid_default_valid, env_beats_config]

    def test_script_and_hook_agree(self):
        spec = importlib.util.spec_from_file_location("hook_under_test", str(HOOK))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        for setup in self.scenarios():
            with self.subTest(setup.__name__), tempfile.TemporaryDirectory() as t:
                home = Path(t).resolve()
                env = home_env(home)
                setup(home, env)
                with mock.patch.dict(os.environ, env), \
                        mock.patch.object(hook, "CONFIG_FILE", home / ".config" / "scripta" / "config.json"):
                    os.environ.pop("SCRIPTA_HANDBOOK_PATH", None) if "SCRIPTA_HANDBOOK_PATH" not in env else None
                    want = hook.locate_repo()
                    got, _ = ds.find_handbook()
                self.assertEqual(got, want)


class Uninstall(Base):
    def test_uninstall_unloads_removes_the_plist_and_keeps_the_log(self):
        self.main("install")
        log = self.home / ".scripta" / "digest-schedule" / "schedule.log"
        log.write_text("earlier runs\n")
        self.world.calls[:] = []
        code, _ = self.main("uninstall")
        self.assertEqual(code, 0)
        plist_path = "%s/Library/LaunchAgents/blue.team.scripta.digest.plist" % self.home
        self.assertEqual(self.world.launchctl(), [["launchctl", "unload", plist_path]])
        self.assertFalse(Path(plist_path).exists())
        self.assertEqual(log.read_text(), "earlier runs\n")
        self.assertEqual(self.world.windows(), [])

    def test_uninstall_when_not_installed_says_so_and_succeeds(self):
        code, out = self.main("uninstall")
        self.assertEqual(code, 0)
        self.assertIn("not installed", out.lower())
        self.assertEqual(self.world.launchctl(), [])


class Status(Base):
    def test_three_states_read_differently(self):
        _, not_installed = self.main("status")
        self.main("install")
        self.world.launchctl_list_rc = 1
        _, not_loaded = self.main("status")
        self.world.launchctl_list_rc = 0
        _, loaded = self.main("status")
        first = [o.splitlines()[0] for o in (not_installed, not_loaded, loaded)]
        self.assertEqual(len(set(first)), 3, first)
        self.assertIn("not installed", first[0])
        self.assertIn("NOT loaded", first[1])
        self.assertIn("installed and loaded", first[2])

    def test_tools_are_looked_up_on_the_plists_path_not_the_shells(self):
        self.main("install")
        job_bin = "%s/.local/bin" % self.home
        self.world.tool_dirs = {job_bin: {"claude", "git"}, "/outside/bin": {"gh", "python3"}}
        os.environ["PATH"] = "/outside/bin:/usr/bin"
        self.world.which_paths[:] = []
        _, out = self.main("status")
        self.assertIn("claude: %s/claude" % job_bin, out)
        self.assertIn("gh: not found on the job's PATH", out)
        self.assertIn("python3: not found on the job's PATH", out)
        self.assertTrue(all(p == self.plist()["EnvironmentVariables"]["PATH"] for _, p in self.world.which_paths))

    def test_status_shows_handbook_rule_python_version_scripta_version_and_last_run(self):
        os.environ["SCRIPTA_HANDBOOK_PATH"] = str(self.handbook)
        self.main("install")
        self.world.tool_dirs = {"%s/.local/bin" % self.home: {"python3", "claude", "git", "gh"}}
        cache = self.home / ".claude" / "plugins" / "cache" / "scripta-plugin" / "scripta"
        for v in ("0.9.5", "0.12.1"):
            f = cache / v / "skills" / "daily-digest" / "scripts" / "digest_schedule.py"
            f.parent.mkdir(parents=True)
            f.write_text("")
        st = self.state()
        st["last_run"] = {"date": "2026-10-13", "outcome": "opened"}
        ds.save_state(st)
        _, out = self.main("status")
        self.assertIn("%s (found by: env)" % self.handbook, out)
        self.assertIn("Python 3.9.6", out)
        self.assertIn("version the job runs: 0.12.1", out)
        self.assertIn("Last run: 2026-10-13, opened", out)


class Windows(Base):
    """The Windows path: Task Scheduler, a PowerShell window, a popup. Runs on any
    OS with is_windows() patched; the fake world answers schtasks, cmd.exe and
    powershell.exe, and the Mac commands would fail the test if called."""

    PYW = "C:\\Python312\\pythonw.exe"

    def setUp(self):
        super().setUp()
        for name, fn in (("is_windows", lambda: True), ("task_python", lambda: self.PYW)):
            q = mock.patch.object(ds, name, fn)
            q.start()
            self.addCleanup(q.stop)
        self.world.uname = "never asked on Windows"

    def install(self, *meetings):
        argv = ["install"]
        for m in meetings:
            argv += ["--meeting", m]
        return self.main(*argv)

    def created(self):
        made = [a for a in self.world.schtasks() if a[1] == "/Create"]
        self.assertEqual(len(made), 1)
        return made[0]

    def test_install_creates_one_noon_weekday_task_that_runs_the_loader_file(self):
        code, out = self.install("%s=tue-fri" % DAILY_SQ2)
        self.assertEqual(code, 0, out)
        loader = self.home / ".scripta" / "digest-schedule" / "loader.py"
        self.assertEqual(self.created(),
                         ["schtasks", "/Create", "/F", "/TN", "blue.team.scripta.digest", "/SC", "WEEKLY",
                          "/D", "MON,TUE,WED,THU,FRI", "/ST", "12:00",
                          "/TR", '"%s" "%s"' % (self.PYW, loader)])
        self.assertTrue(loader.read_text(encoding="utf-8").endswith(ds.LOADER))
        self.assertFalse((self.home / "Library").exists())
        self.assertEqual(self.world.launchctl(), [])
        self.assertIn("installed in Task Scheduler", out)

    def test_a_backup_install_repeats_every_thirty_minutes_through_seventeen(self):
        self.install(TEAM_DAILY_SPEC)
        argv = self.created()
        self.assertEqual(argv[argv.index("/RI") + 1], "30")
        self.assertEqual(argv[argv.index("/DU") + 1], "05:01")  # 12:00 + 5h01 lets 17:00 fire

    def test_claude_config_dir_goes_into_the_loader_since_a_task_has_no_env(self):
        os.environ["CLAUDE_CONFIG_DIR"] = "C:\\Users\\d\\claude profile"
        self.install()
        text = (self.home / ".scripta" / "digest-schedule" / "loader.py").read_text(encoding="utf-8")
        self.assertIn("os.environ.setdefault('CLAUDE_CONFIG_DIR', 'C:\\\\Users\\\\d\\\\claude profile')", text)

    def test_a_refused_task_fails_the_install_and_says_why(self):
        self.world.schtasks_fails = True
        code, out = self.install()
        self.assertEqual(code, 1)
        self.assertIn("Access is denied.", out)

    def test_the_window_is_powershell_started_through_cmd_start(self):
        self.set_state([])
        self.run_at(WED)
        opened = self.world.win_windows()
        self.assertEqual(len(opened), 1)
        script = ds.state_dir() / ("window-%s.ps1" % TODAY)
        self.assertEqual(opened[0], ["cmd.exe", "/c", "start", "", "powershell.exe", "-NoExit", "-NoProfile",
                                     "-ExecutionPolicy", "Bypass", "-File", str(script)])
        self.assertEqual(self.world.windows(), [])  # no `open -a Terminal`
        # No pipes: PowerShell would inherit them and hold the run until it closes.
        self.assertTrue(self.world.detached[self.world.calls.index((opened[0], None))])
        self.assertEqual(self.state()["last_opened"], TODAY)

    def test_the_window_gives_claude_one_line_that_names_the_prompt_file(self):
        weird = self.make_handbook(self.home / "PROJECTS" / "the team's book")
        self.handbook = weird
        self.set_state([], claude_config_dir="C:\\Users\\d\\cfg")
        self.run_at(WED)
        raw = (ds.state_dir() / ("window-%s.ps1" % TODAY)).read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))  # Windows PowerShell 5.1 needs the BOM
        lines = raw.decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0], "$ErrorActionPreference = 'Stop'")
        lines = lines[1:]
        self.assertEqual(lines[0], "Set-Location -LiteralPath '%s'" % str(weird).replace("'", "''"))
        self.assertEqual(lines[1], "$env:CLAUDE_CONFIG_DIR = 'C:\\Users\\d\\cfg'")
        pf = (ds.state_dir() / ("prompt-%s.txt" % TODAY)).as_posix()
        self.assertEqual(lines[2], "claude '/scripta:daily-digest The noon schedule wrote today''s details "
                                   "to %s. Read that file first and follow it.'" % pf)
        self.assertIn("/scripta:daily-digest for", self.prompt())  # the full prompt is still in the file

    def test_a_window_that_does_not_open_pops_up_the_by_hand_command(self):
        self.world.window_fails = True
        self.set_state([])
        self.run_at(WED)
        pops = self.world.popups()
        self.assertEqual(len(pops), 1)
        self.assertIn("The PowerShell window did not open", pops[0])
        self.assertIn("Set-Location -LiteralPath ''%s''; claude, then type /scripta:daily-digest"
                      % str(self.handbook).replace("'", "''''"), pops[0])
        self.assertNotIn("&&", pops[0])
        self.assertTrue(pops[0].startswith("(New-Object -ComObject WScript.Shell).Popup("))
        self.assertEqual(self.world.osa(), [])
        self.assertNotIn("last_opened", self.state())

    def test_a_popup_message_with_a_quote_stays_one_powershell_string(self):
        with contextlib.redirect_stdout(io.StringIO()):
            ds.notify("Today's digest")
        self.assertEqual(self.world.popups(),
                         ["(New-Object -ComObject WScript.Shell).Popup('Today''s digest', 10, 'Scripta digest') | Out-Null"])

    def test_attendance_calls_claude_by_full_path_with_the_prompt_on_stdin(self):
        self.world.zoom["12345678901"] = call()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ds.check_attendance("12345678901", MAIN_PERSON, dt.date(2026, 10, 14)), "absent")
        (argv, _), = self.world.attendance_calls()
        self.assertEqual(argv[:2], ["/fake/bin/claude", "-p"])
        self.assertNotIn("meeting_number", " ".join(argv))
        sent = self.world.inputs[self.world.calls.index(self.world.attendance_calls()[0])]
        self.assertIn("meeting_number=12345678901", sent)

    def test_uninstall_deletes_the_task_and_the_loader_and_keeps_the_log(self):
        self.install()
        log = self.home / ".scripta" / "digest-schedule" / "schedule.log"
        log.write_text("earlier runs\n")
        self.world.calls[:] = []
        code, _ = self.main("uninstall")
        self.assertEqual(code, 0)
        self.assertIn(["schtasks", "/Delete", "/F", "/TN", "blue.team.scripta.digest"], self.world.schtasks())
        self.assertFalse((self.home / ".scripta" / "digest-schedule" / "loader.py").exists())
        self.assertEqual(log.read_text(), "earlier runs\n")

    def test_install_lets_the_task_run_on_battery_and_catch_up_a_missed_noon(self):
        code, _ = self.install()
        self.assertEqual(code, 0)
        settings, = self.world.task_settings()
        for flag in ("-AllowStartIfOnBatteries", "-DontStopIfGoingOnBatteries", "-StartWhenAvailable"):
            self.assertIn(flag, settings)
        self.assertIn("-TaskName 'blue.team.scripta.digest'", settings)
        order = [a[1] if a[0] == "schtasks" else "settings" for a, _ in self.world.calls
                 if a[0] == "schtasks" and a[1] == "/Create" or "Set-ScheduledTask" in a[-1]]
        self.assertEqual(order, ["/Create", "settings"])

    def test_a_refused_settings_change_warns_and_keeps_the_task(self):
        self.world.settings_fail = True
        code, out = self.install()
        self.assertEqual(code, 0)
        self.assertIn("Warning: could not let the task run on battery", out)
        self.assertIn("installed in Task Scheduler", out)

    def test_status_says_when_the_python_the_task_starts_is_gone(self):
        self.install()
        self.world.task_cmd = str(self.home / "Python311" / "pythonw.exe")
        _, out = self.main("status")
        self.assertIn("the Python it starts (%s) is gone. Run install again." % self.world.task_cmd,
                      out.splitlines()[0])
        here = self.home / "pythonw.exe"
        here.write_text("")
        self.world.task_cmd = str(here)
        _, out = self.main("status")
        self.assertEqual(out.splitlines()[0], "Schedule: installed in Task Scheduler")

    def test_a_failed_delete_keeps_the_loader_and_says_the_task_is_still_on(self):
        self.install()
        self.world.delete_fails = True
        code, out = self.main("uninstall")
        self.assertEqual(code, 1)
        self.assertIn("Access is denied.", out)
        self.assertTrue((self.home / ".scripta" / "digest-schedule" / "loader.py").exists())

    def test_uninstall_and_status_when_no_task_exists(self):
        self.world.task_exists = False
        code, out = self.main("uninstall")
        self.assertEqual(code, 0)
        self.assertIn("not installed", out.lower())
        self.assertNotIn("/Delete", [a[1] for a in self.world.schtasks()])
        _, status = self.main("status")
        self.assertEqual(status.splitlines()[0], "Schedule: not installed")


class WindowsRunCmd(unittest.TestCase):
    """run_cmd's Windows arguments, checked against subprocess.run itself: the
    fake World replaces run_cmd, so without this nothing pins them."""

    def call(self, *argv, **kw):
        seen = {}

        def fake_run(args, **kwargs):
            seen.update(kwargs)
            return subprocess.CompletedProcess(args, 0, "out", "")
        with mock.patch.object(ds, "is_windows", lambda: True), mock.patch.object(subprocess, "run", fake_run):
            ds.run_cmd(list(argv), **kw)
        return seen

    def test_children_get_no_window_and_read_utf8(self):
        kw = self.call("git", "status")
        self.assertEqual(kw["creationflags"], 0x08000000)
        self.assertEqual((kw["encoding"], kw["errors"]), ("utf-8", "replace"))
        self.assertEqual(kw["stdin"], subprocess.DEVNULL)

    def test_input_text_goes_on_stdin_as_utf8(self):
        kw = self.call("claude", "-p", input_text="Mattéo Łukasz")
        self.assertEqual(kw["input"], "Mattéo Łukasz")
        self.assertEqual(kw["encoding"], "utf-8")
        self.assertNotIn("stdin", kw)

    def test_detach_uses_no_pipes(self):
        kw = self.call("cmd.exe", "/c", "start", "", "powershell.exe", detach=True)
        self.assertEqual((kw["stdin"], kw["stdout"], kw["stderr"]),
                         (subprocess.DEVNULL, subprocess.DEVNULL, subprocess.DEVNULL))
        self.assertNotIn("capture_output", kw)
        self.assertEqual(kw["creationflags"], 0x08000000)

    def test_mac_gets_none_of_it(self):
        seen = {}

        def fake_run(args, **kwargs):
            seen.update(kwargs)
            return subprocess.CompletedProcess(args, 0, "", "")
        with mock.patch.object(ds, "is_windows", lambda: False), mock.patch.object(subprocess, "run", fake_run):
            ds.run_cmd(["git", "status"])
        self.assertNotIn("creationflags", seen)
        self.assertNotIn("encoding", seen)


class WindowsLoaderBranch(unittest.TestCase):
    """The loader's os.name == 'nt' lines, run in-process with os.name and
    subprocess.call replaced (a POSIX host cannot run pythonw)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        p = mock.patch.dict(os.environ, home_env(self.home))
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.assertEqual(Path.home(), self.home, "the tests would write into the real home folder")

    def exec_loader(self):
        calls = []

        def fake_call(argv, **kw):
            calls.append((argv, kw))
            return 0
        with mock.patch.object(os, "name", "nt"), mock.patch.object(subprocess, "call", fake_call):
            with self.assertRaises(SystemExit):
                exec(compile(ds.LOADER, "loader", "exec"), {"__name__": "loader"})
        for _, kw in calls:
            if "stdout" in kw:
                kw["stdout"].close()
        return calls

    def test_the_run_is_hidden_and_writes_utf8_to_schedule_log(self):
        f = self.home / ".claude" / "plugins" / "cache" / "scripta-plugin" / "scripta" / "0.13.3" / \
            "skills" / "daily-digest" / "scripts" / "digest_schedule.py"
        f.parent.mkdir(parents=True)
        f.write_text("")
        (argv, kw), = self.exec_loader()
        self.assertEqual(argv[1:], [str(f), "run"])
        self.assertEqual(kw["creationflags"], 0x08000000)
        self.assertEqual(kw["stderr"], subprocess.STDOUT)
        self.assertEqual(kw["stdout"].name, str(self.home / ".scripta" / "digest-schedule" / "schedule.log"))
        self.assertEqual(kw["env"]["PYTHONIOENCODING"], "utf-8")

    def test_no_plugin_pops_up_a_windows_notice_not_osascript(self):
        (argv, _), = self.exec_loader()
        self.assertEqual(argv[0], "powershell.exe")
        self.assertIn("Popup('No scripta plugin found for the noon digest.", argv[-1])


class Loader(unittest.TestCase):
    """The plist's loader string, run for real with python3 -c against a fake plugin cache."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        osa = bin_dir / "osascript"
        osa.write_text('#!/bin/sh\necho "$@" >> "$OSA_LOG"\n')
        osa.chmod(0o755)
        self.mark = self.root / "mark"
        self.osa_log = self.root / "osa.log"
        self.env = {**home_env(self.home), "PATH": "%s:/usr/bin:/bin" % bin_dir,
                    "MARK": str(self.mark), "OSA_LOG": str(self.osa_log)}

    def plant(self, config_dir, version):
        f = Path(config_dir) / "plugins" / "cache" / "scripta-plugin" / "scripta" / version / \
            "skills" / "daily-digest" / "scripts" / "digest_schedule.py"
        f.parent.mkdir(parents=True)
        f.write_text('import os, sys\nopen(os.environ["MARK"], "w").write("%s " + " ".join(sys.argv[1:]))\n' % version)

    def load(self, **extra):
        env = dict(self.env)
        env.update(extra)
        return subprocess.run([sys.executable, "-c", ds.LOADER], env=env).returncode

    def test_picks_the_highest_numeric_version_and_calls_run(self):
        base = self.home / ".claude"
        self.plant(base, "0.9.5")
        self.plant(base, "0.12.1")
        (base / "plugins" / "cache" / "scripta-plugin" / "scripta" / "notes").mkdir()
        self.assertEqual(self.load(), 0)
        self.assertEqual(self.mark.read_text(), "0.12.1 run")
        self.plant(base, "0.13.0")
        self.assertEqual(self.load(), 0)
        self.assertEqual(self.mark.read_text(), "0.13.0 run")

    def test_nothing_installed_notifies_and_exits_non_zero(self):
        self.assertNotEqual(self.load(), 0)
        self.assertFalse(self.mark.exists())
        self.assertIn("display notification", self.osa_log.read_text())

    def test_loader_and_status_pick_the_same_version(self):
        base = self.home / ".claude"
        for v in ("0.9.0", "0.10.0", "0.12.0"):
            self.plant(base, v)
        self.assertEqual(self.load(), 0)
        cache = base / "plugins" / "cache" / "scripta-plugin" / "scripta"
        self.assertEqual(self.mark.read_text(), "%s run" % ds.newest_version(cache))
        self.assertEqual(ds.newest_version(cache), "0.12.0")

    def test_the_windows_loader_file_runs_and_carries_the_claude_config_dir(self):
        other = self.root / "profile"
        self.plant(self.home / ".claude", "9.9.9")
        self.plant(other, "0.5.0")
        loader = self.root / "loader.py"
        loader.write_text(ds.build_loader(str(other)), encoding="utf-8")
        self.assertEqual(subprocess.run([sys.executable, str(loader)], env=self.env).returncode, 0)
        self.assertEqual(self.mark.read_text(), "0.5.0 run")
        loader.write_text(ds.build_loader(""), encoding="utf-8")
        self.assertEqual(subprocess.run([sys.executable, str(loader)], env=self.env).returncode, 0)
        self.assertEqual(self.mark.read_text(), "9.9.9 run")

    def test_claude_config_dir_moves_the_search_to_that_folder(self):
        self.plant(self.home / ".claude", "9.9.9")
        other = self.root / "profile"
        self.plant(other, "0.5.0")
        self.assertEqual(self.load(CLAUDE_CONFIG_DIR=str(other)), 0)
        self.assertEqual(self.mark.read_text(), "0.5.0 run")


class PowerShellQuoting(unittest.TestCase):
    def test_ps_str_doubles_straight_and_curly_quotes(self):
        for q in ("'", "\u2018", "\u2019", "\u201a", "\u201b"):
            self.assertEqual(ds.ps_str("a%sb" % q), "'a%s%sb'" % (q, q))

    def test_window_script_doubles_curly_apostrophe_in_handbook_path(self):
        out = ds.window_script_windows("C:\\Users\\a\\Team\u2019s handbook", "C:\\p\\prompt.md", "")
        self.assertIn("Team\u2019\u2019s handbook", out)


if __name__ == "__main__":
    unittest.main()

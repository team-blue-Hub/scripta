#!/usr/bin/env python3
"""Digest schedule - open the daily digest in a terminal window at 12:00.

A scheduled job on an opted-in laptop (launchd on a Mac, Task Scheduler on
Windows) runs `run` every weekday at noon. `run` decides
whether today's digest still needs doing and, if so, opens a visible terminal
window in the handbook checkout with an interactive Claude session already
started on /scripta:daily-digest. The person triages there as always. Nothing
here changes a digest step (a person runs the digest and
screens its output).

On Windows, Task Scheduler takes launchd's place, the window is a PowerShell
window, and notifications are a small popup (see "Windows" below).

Commands:
  install    turn the schedule on (Mac or Windows); takes the person's meetings
  uninstall  turn it off; open windows are left alone
  status     show what is installed, found and last run
  try        open the window now, for a first test (no gates, day not recorded)
  run        what the scheduled job calls (gates, once-a-day, done check, window)
  check      for each saved backup meeting, test now whether your Zoom can see
             the call and who joined it (never opens a window)

  install --meeting "Team - Daily=tue-fri" --meeting "Team - Planning=mon"
  A meeting is its Zoom title, then = and the weekdays it runs: a day (mon), a
  range (tue-fri), a list (mon,wed) or "all". No "=" means every weekday.
  Run by hand with no --meeting on a terminal, install asks for them.

  A backup meeting adds ;backup-for=<main person's Zoom name>;zoom=<meeting number>:
  install --meeting "Team - Daily=tue-fri;backup-for=Alex Doe;zoom=12345678901"
  The backup's Mac reads from Zoom who joined that call and opens the window
  only when the main person did not join it (or at 17:00 if it cannot tell).
  A backup install also retries every 30 minutes from 12:30 to 17:00.

State lives in ~/.scripta/digest-schedule/ (state.json, prompt-<date>.txt and
schedule.log). On a Mac the plist is the only installed piece; on Windows it is
the task plus loader.py. Either one finds the newest
installed scripta version at run time and calls this file's `run`, so a plugin
update needs no reinstall.

Windows: one Task Scheduler task (same name as the plist label) runs the loader,
saved as ~/.scripta/digest-schedule/loader.py, with pythonw at 12:00 Monday to
Friday, repeating every 30 minutes until 17:00 for a backup install. The loader
appends to schedule.log itself, since a task has no StandardOutPath. The window
is PowerShell started through `cmd.exe /c start`.
Claude gets a one-line prompt that points at the prompt
file, because a multi-line argument does not survive the .cmd shim npm installs;
for the same reason the attendance check sends its prompt on stdin there.

Every outside call (launchctl, osascript, open, schtasks, cmd.exe, powershell.exe,
git, gh, uname, tool lookup, the clock, the keyboard, the OS) goes through the seam
functions below; tests replace them.

Runs on the system python3 of a Mac (3.9): no match statements, no 3.10+ calls.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

LABEL = "blue.team.scripta.digest"
TITLE = "Scripta digest"
DAYS = ["mon", "tue", "wed", "thu", "fri"]
JOB_PATH_PARTS = ["~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin",
                  "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
OPEN_FROM = 11 * 60   # minutes since midnight: before this, nothing opens
OPEN_UNTIL = 18 * 60  # after this, nothing opens and a notification says so
DECIDE_BY = 17 * 60   # a backup meeting still unclear at this time opens anyway
RETRY_STEP = 30       # minutes between retries for a backup install (12:30 to 17:00)
ATTENDANCE_TIMEOUT = 180
CHECK_DAYS = 7        # how far back `check` looks for the meeting
SETTLE_MIN = 10       # minutes after a call ends before "did not join" counts

# Runs inside launchd: pick the newest installed scripta by numeric version and
# call its `run`. Kept as a string so the plist carries it and a test can run it.
# Same scan as newest_version(); a test keeps the two in step.
LOADER = """\
import os, subprocess, sys
c = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')
r = os.path.join(c, 'plugins', 'cache', 'scripta-plugin', 'scripta')
rel = os.path.join('skills', 'daily-digest', 'scripts', 'digest_schedule.py')
found = []
for v in (os.listdir(r) if os.path.isdir(r) else []):
    try:
        k = tuple(int(x) for x in v.split('.'))
    except ValueError:
        continue
    if os.path.isfile(os.path.join(r, v, rel)):
        found.append((k, v))
msg = 'No scripta plugin found for the noon digest. Reinstall scripta, then run digest_schedule.py install.'
if not found:
    try:
        if os.name == 'nt':
            subprocess.call(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                             "(New-Object -ComObject WScript.Shell).Popup('" + msg + "', 10, 'Scripta digest') | Out-Null"])
        else:
            subprocess.call(['osascript', '-e', 'display notification "' + msg + '" with title "Scripta digest"'])
    except OSError:
        pass
    sys.exit(1)
kw = {}
if os.name == 'nt':
    d = os.path.join(os.path.expanduser('~'), '.scripta', 'digest-schedule')
    os.makedirs(d, exist_ok=True)
    # The run's own output goes to schedule.log (a task has no StandardOutPath),
    # as UTF-8 so a name the locale code page lacks cannot crash a log line, and
    # with CREATE_NO_WINDOW so the run itself stays hidden.
    kw = {'stdout': open(os.path.join(d, 'schedule.log'), 'ab'), 'stderr': subprocess.STDOUT,
          'creationflags': 0x08000000, 'env': dict(os.environ, PYTHONIOENCODING='utf-8')}
sys.exit(subprocess.call([sys.executable, os.path.join(r, max(found)[1], rel), 'run'], **kw))
"""


# ---------------------------------------------------------------- the seam

CREATE_NO_WINDOW = 0x08000000


def run_cmd(argv, cwd=None, timeout=120, input_text=None, detach=False):
    """Run one outside command. Returns (returncode, stdout, stderr). input_text,
    when given, is sent on stdin; otherwise stdin is empty.

    detach runs it with no pipes at all and returns empty output: for a launcher
    whose child keeps running (cmd.exe start), whose inherited pipe would hold
    the run until that child exits.

    On Windows the run itself has no console (pythonw), so every console child
    gets CREATE_NO_WINDOW, or it would flash a window of its own; and output is
    read as UTF-8, since the locale code page cannot decode what git, gh and
    claude print."""
    flags = {"creationflags": CREATE_NO_WINDOW} if is_windows() else {}
    text = {"encoding": "utf-8", "errors": "replace"} if is_windows() else {}
    try:
        if detach:
            p = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=timeout, **flags)
            return p.returncode, "", ""
        stdin = {"input": input_text} if input_text is not None else {"stdin": subprocess.DEVNULL}
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           **dict(stdin, **flags, **text))
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError, UnicodeError) as e:
        return 127, "", str(e)


def is_windows():
    return os.name == "nt"


def which_on(tool, path):
    """Find a tool on the given PATH string (not the shell's)."""
    return shutil.which(tool, path=path)


def clock():
    return dt.datetime.now()


def stdin_is_tty():
    return sys.stdin.isatty()


def ask(prompt):
    return input(prompt)


# ---------------------------------------------------------------- paths and state

def home():
    return Path.home()


def state_dir():
    return home() / ".scripta" / "digest-schedule"


def state_file():
    return state_dir() / "state.json"


def log_file():
    return state_dir() / "schedule.log"


def plist_file():
    return home() / "Library" / "LaunchAgents" / (LABEL + ".plist")


def loader_file():
    """Windows only: the loader the task runs, since /TR cannot carry LOADER inline."""
    return state_dir() / "loader.py"


def task_python():
    """Windows only: pythonw next to this interpreter, so a task run opens no console."""
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.is_file() else exe)


def config_file():
    return home() / ".config" / "scripta" / "config.json"


def job_path():
    if is_windows():
        return os.environ.get("PATH", "")  # a task runs with the person's own PATH
    return ":".join(os.path.expanduser(p) for p in JOB_PATH_PARTS)


def load_state():
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save_state(state):
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix="state.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp, str(state_file()))


def log(msg):
    print("[%s] %s" % (clock().strftime("%Y-%m-%d %H:%M:%S"), msg))


def as_str(s):
    """Escape for an AppleScript string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def ps_str(s):
    """Quote for a PowerShell single-quoted string."""
    return "'" + re.sub("['\u2018\u2019\u201a\u201b]", lambda m: m.group(0) * 2, str(s)) + "'"


def notify(msg):
    log("notify: " + msg)
    if is_windows():
        # A popup that closes itself after 10 s: it needs no toast registration and
        # never waits on an answer the task cannot give.
        run_cmd(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "(New-Object -ComObject WScript.Shell).Popup(%s, 10, %s) | Out-Null"
                 % (ps_str(msg), ps_str(TITLE))])
        return
    run_cmd(["osascript", "-e",
             'display notification "%s" with title "%s"' % (as_str(msg), TITLE)])


# ---------------------------------------------------------------- handbook

def find_handbook():
    """Same rules as hooks/load_scripta_context.py locate_repo. (path, source) or (None, "")."""
    env = os.environ.get("SCRIPTA_HANDBOOK_PATH", "")
    cfg = ""
    if not env:
        try:
            cfg = str(json.loads(config_file().read_text(encoding="utf-8")).get("handbook_path") or "")
        except Exception:
            cfg = ""
    override = env or cfg
    if override:
        cands = [(Path(override).expanduser(), "env" if env else "config")]
    else:
        cands = [(home() / "PROJECTS" / "hub-scripta-handbook", "default"),
                 (home() / "PROJECTS" / "scripta", "default")]
    for path, source in cands:
        if (path / "where-truth-lives.md").is_file():
            return path, source
    return None, ""


# ---------------------------------------------------------------- meetings

def parse_days(spec):
    spec = spec.strip().lower()
    if spec in ("all", "daily"):
        return list(range(5))
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            if a not in DAYS or b not in DAYS or DAYS.index(a) > DAYS.index(b):
                raise ValueError("bad weekday range %r" % part)
            out.update(range(DAYS.index(a), DAYS.index(b) + 1))
        elif part in DAYS:
            out.add(DAYS.index(part))
        else:
            raise ValueError("bad weekday %r (use mon to fri, a range like tue-fri, or all)" % part)
    return sorted(out)


EXTRA_PART = re.compile(r"^\s*(backup-for|zoom)\s*=(.*)$", re.IGNORECASE)


def parse_meeting(arg):
    """'<title>[=<days>][;backup-for=<name>][;zoom=<id>]'. The extra parts are read
    from the end, so a title that holds a ';' still works."""
    parts = arg.split(";")
    extras = {}
    while len(parts) > 1:
        m = EXTRA_PART.match(parts[-1])
        if not m:
            break
        key = m.group(1).lower()
        if key in extras:
            raise ValueError("%s given twice" % key)
        extras[key] = m.group(2).strip()
        parts.pop()
    head = ";".join(parts)
    title, sep, spec = head.rpartition("=")
    if not sep:
        title, spec = head, "all"
    title = title.strip()
    if not title:
        raise ValueError("a meeting needs a title")
    meeting = {"title": title, "days": parse_days(spec)}
    backup = extras.get("backup-for", "")
    zoom = extras.get("zoom", "")
    if "backup-for" in extras and not backup:
        raise ValueError("backup-for needs the main person's Zoom name")
    if "zoom" in extras and not re.fullmatch(r"\d+", zoom):
        raise ValueError("zoom must be the numeric Zoom meeting number, got %r" % zoom)
    if backup and not zoom:
        raise ValueError("a backup meeting needs the Zoom meeting number: add ;zoom=<number> "
                         "after backup-for=%s" % backup)
    if backup:
        meeting["backup_for"] = backup
    if zoom:
        meeting["zoom_id"] = zoom
    return meeting


def ask_meetings():
    print("Which meetings do you attend? Use their Zoom titles. Blank title to finish.")
    out = []
    while True:
        title = ask("Meeting title: ").strip()
        if not title:
            return out
        while True:
            spec = ask("Weekdays for '%s' (for example tue-fri, mon, all) [all]: " % title).strip() or "all"
            try:
                meeting = {"title": title, "days": parse_days(spec)}
                break
            except ValueError as e:
                print(str(e))
        backup = ask("Are you the backup for someone on this call? "
                     "Their Zoom name, or blank if it's your own call: ").strip()
        if backup:
            while True:
                zoom = ask("The Zoom meeting number for this call: ").strip()
                if re.fullmatch(r"\d+", zoom):
                    break
                print("The Zoom meeting number is digits only, for example 12345678901.")
            meeting["backup_for"] = backup
            meeting["zoom_id"] = zoom
        out.append(meeting)


def is_backup(m):
    return bool(m.get("backup_for"))


def meeting_text(m):
    text = "%s (%s)" % (m["title"], days_text(m["days"]))
    if is_backup(m):
        text += " (backup for %s, Zoom %s)" % (m["backup_for"], m.get("zoom_id", "?"))
    return text


def days_text(days):
    return ",".join(DAYS[d] for d in days)


# ---------------------------------------------------------------- weeks

def previous_weekday(day):
    d = day - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def week_names(day):
    """File and branch of the week's update, from that week's Friday (Step 5c)."""
    fri = day + dt.timedelta(days=4 - day.weekday())
    nn = "%02d" % fri.isocalendar()[1]
    return "updates/%s-week-%s.md" % (fri.isoformat(), nn), "weekly-update/%d-week-%s" % (fri.year, nn)


# ---------------------------------------------------------------- the done check

class Check(object):
    def __init__(self):
        self.failed = False
        self.today_prs = []      # day PRs for today (open or merged)
        self.done = []           # saved titles found in today's digest
        self.urls = []           # where they were found
        self.prev_has_pr = None  # None when unknown


def source_bodies(text):
    """Bodies of every '## Source' section."""
    out, cur = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            if cur is not None:
                out.append("\n".join(cur))
            cur = [] if line[3:].strip().lower() == "source" else None
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        out.append("\n".join(cur))
    return out


def adr_has_meeting(text, title, date):
    """A Source line reads '<meeting title>, <date>, <time>', and one line can name
    several meetings separated by ';'. The whole title must match."""
    want = title.strip().lower()
    pattern = re.compile(r"^\s*(.+?),\s*%s\b" % re.escape(date))
    for body in source_bodies(text):
        for line in body.splitlines():
            for part in line.split(";"):
                m = pattern.match(part)
                if m and m.group(1).strip().lower() == want:
                    return True
    return False


def week_has_block(text, title, date):
    want = ("### %s · %s" % (date, title)).lower()
    return any(re.sub(r"\s+", " ", line.strip()).lower() == want for line in text.splitlines())


def gh_json(argv, handbook):
    rc, out, _ = run_cmd(argv, cwd=str(handbook))
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def git_fetch(handbook, *refs):
    return run_cmd(["git", "-C", str(handbook), "fetch", "origin"] + list(refs))[0] == 0


def git_show(handbook, ref, path):
    rc, out, _ = run_cmd(["git", "-C", str(handbook), "show", "%s:%s" % (ref, path)])
    return out if rc == 0 else None


def check_digest(handbook, day, titles):
    c = Check()
    date = day.isoformat()
    prev = previous_weekday(day).isoformat()
    prs = gh_json(["gh", "pr", "list", "--state", "all", "--limit", "100",
                    "--json", "number,headRefName,state,url"], handbook)
    if not isinstance(prs, list):
        c.failed = True
        return c
    live = [p for p in prs if p.get("state") in ("OPEN", "MERGED")]
    c.prev_has_pr = any(p["headRefName"].startswith("digest/" + prev) for p in live)
    c.today_prs = [p for p in live if p["headRefName"].startswith("digest/" + date)]
    if not titles:
        return c

    if not git_fetch(handbook, "main"):
        c.failed = True
        return c

    def mark(title, url):
        if title not in c.done:
            c.done.append(title)
        if url not in c.urls:
            c.urls.append(url)

    for pr in c.today_prs:
        data = gh_json(["gh", "pr", "view", str(pr["number"]), "--json", "files"], handbook)
        if not isinstance(data, dict):
            c.failed = True
            return c
        paths = [f["path"] for f in data.get("files", [])
                 if f["path"].startswith("decisions/") and f["path"].endswith(".md")]
        ref = "origin/main"
        if pr["state"] == "OPEN":
            ref = "origin/" + pr["headRefName"]
            if not git_fetch(handbook, pr["headRefName"]):
                c.failed = True
                return c
        for path in paths:
            text = git_show(handbook, ref, path)
            if text is None:
                c.failed = True
                return c
            for t in titles:
                if adr_has_meeting(text, t, date):
                    mark(t, pr["url"])

    left = [t for t in titles if t not in c.done]
    if left:
        wfile, wbranch = week_names(day)
        wprs = [p for p in prs if p["headRefName"] == wbranch and p.get("state") == "OPEN"]
        ref = "origin/main"
        if wprs:
            ref = "origin/" + wbranch
            if not git_fetch(handbook, wbranch):
                c.failed = True
                return c
        text = git_show(handbook, ref, wfile)  # no file yet is not a failure: no block
        for t in left:
            if text is not None and week_has_block(text, t, date):
                mark(t, wprs[0]["url"] if wprs else wfile + " on main")
    return c


# ---------------------------------------------------------------- the attendance check

ATTENDANCE_PROMPT = (
    'Use the Zoom tool search_meetings with meeting_number=%s (an integer), from="%s" and to="%s" '
    '(both UTC, the person\'s local days in time zone %s), and '
    'page_size 50. If the result is saved to a file, read it with jq. Each record has a topic, '
    'meeting_start_time, meeting_end_time, meeting_category and attendees (a list of '
    'objects with user_name). If several records come back (the call was reopened), combine '
    'them: attendees is the union of all of them, start_time the earliest meeting_start_time, '
    'end_time the latest meeting_end_time, or null if any record has none. '
    'Reply with ONE line of JSON and nothing else: '
    '{"topic": <topic>, "start_time": <meeting_start_time>, "end_time": <meeting_end_time or null>, '
    '"finished": <true only if every record has meeting_category "history" or a meeting_end_time>, '
    '"attendees": [<unique user_name values>], '
    '"error": <the tool\'s error message if the call failed, else null>}. '
    'If no record comes back, reply the same JSON with an empty attendees list and a "reason" '
    'of a few words.')
ATTENDANCE_TOOLS = "mcp__claude_ai_Zoom_for_Claude__search_meetings Bash(jq:*) Read"
# Matched on the tool's error or the reply's reason: joining needs no recording access.
PERMISSION_WORDS = re.compile(r"\b40[13]\b|forbidden|permission|access denied|"
                              r"not authori[sz]ed|unauthori[sz]ed", re.IGNORECASE)


def norm_name(s):
    """Name for comparing: spaces and case ignored, accents folded (León = Leon)."""
    text = unicodedata.normalize("NFKD", str(s))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split()).casefold()


def day_window_utc(day, days_back=0):
    """(from, to, zone name): the person's local calendar day, or that day and the
    days_back days before it, as UTC ISO strings."""
    start = dt.datetime.combine(day - dt.timedelta(days=days_back), dt.time(0, 0, 0)).astimezone()
    end = dt.datetime.combine(day, dt.time(23, 59, 59)).astimezone()
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    utc = dt.timezone.utc
    zone = "%s, UTC%s" % (start.tzname(), start.strftime("%z"))
    return start.astimezone(utc).strftime(fmt), end.astimezone(utc).strftime(fmt), zone


def parse_utc(stamp):
    """A Zoom UTC timestamp as an aware datetime, or None when it cannot be read."""
    if not isinstance(stamp, str):
        return None
    text = re.sub(r"\.\d+", "", stamp.strip())
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        when = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when


def local_date(start_time):
    """Local calendar date of a Zoom UTC timestamp, or None when it cannot be read."""
    when = parse_utc(start_time)
    return when.astimezone().date() if when else None


def reply_object(text):
    """The one JSON object in the model's reply (tolerates a code fence around it)."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        return None
    try:
        obj = json.loads(text[a:b + 1])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def attendance_detail(zoom_id, name, day, days_back=0):
    """Ask the person's own Zoom connector, through a headless claude, who joined
    the latest call of this meeting on `day`. Returns a dict: status ("present",
    "absent", "not_yet" or "error"), reason, call_date (local date of the call it
    found, or None), attendees, present (by attendees, whatever the date) and
    permission (True when Zoom refused access)."""
    d = {"status": "error", "reason": "", "call_date": None, "attendees": [],
         "present": None, "permission": False}

    def done(status, reason=""):
        d["status"], d["reason"] = status, reason
        log("attendance %s, Zoom %s, %s: %s%s" % (name, zoom_id, day.isoformat(), status,
                                                    (" (%s)" % reason) if reason else ""))
        return d

    claude = which_on("claude", os.environ.get("PATH", ""))
    if not claude:
        return done("error", "claude not found")
    state_dir().mkdir(parents=True, exist_ok=True)
    start, end, zone = day_window_utc(day, days_back)
    prompt = ATTENDANCE_PROMPT % (zoom_id, start, end, zone)
    flags = ["--model", "sonnet", "--allowedTools", ATTENDANCE_TOOLS, "--output-format", "json"]
    if is_windows():
        # The full path, since a bare "claude" does not find claude.cmd, and the
        # prompt on stdin: its quotes and braces do not survive the .cmd shim.
        rc, out, err = run_cmd([claude, "-p"] + flags, cwd=str(state_dir()),
                               timeout=ATTENDANCE_TIMEOUT, input_text=prompt)
    else:
        rc, out, err = run_cmd(["claude", "-p", prompt] + flags, cwd=str(state_dir()),
                               timeout=ATTENDANCE_TIMEOUT)
    if rc != 0:
        said = err.strip()
        try:
            said = str(json.loads(out).get("result") or said)
        except (ValueError, AttributeError):
            said = said or out.strip()
        return done("error", "claude failed: %s" % ((said.splitlines() or ["no output"])[0][:120]))
    try:
        wrapper = json.loads(out)
    except ValueError:
        return done("error", "bad JSON from claude")
    if not isinstance(wrapper, dict):
        return done("error", "bad JSON from claude")
    cost = wrapper.get("total_cost_usd")
    if cost is not None:
        log("attendance cost: $%s" % cost)
    if wrapper.get("is_error"):
        return done("error", "claude reported an error")
    reply = reply_object(str(wrapper.get("result", "")))
    if reply is None:
        return done("error", "bad JSON in the reply")
    reason = str(reply.get("reason") or "")
    tool_error = str(reply.get("error") or "")
    attendees = reply.get("attendees")
    attendees = [str(x) for x in attendees if x] if isinstance(attendees, list) else []
    if tool_error:
        if PERMISSION_WORDS.search(tool_error):
            d["permission"] = True
        return done("error", tool_error[:120])
    if not attendees:
        if PERMISSION_WORDS.search(reason):
            d["permission"] = True
            return done("error", reason[:120])
        return done("not_yet", reason or "no call today yet")
    d["attendees"] = attendees
    d["call_date"] = local_date(reply.get("start_time"))
    d["present"] = norm_name(name) in [norm_name(x) for x in attendees]
    if d["call_date"] is None:
        return done("not_yet", "no usable start_time")
    if d["call_date"] != day:
        if days_back:
            # Over several days the reply merges every call and keeps the earliest start.
            return done("not_yet", "calls found in the last %d days, the earliest on %s" % (
                days_back, d["call_date"].isoformat()))
        return done("not_yet", "latest call is from %s, not today" % d["call_date"].isoformat())
    if d["present"]:
        return done("present")  # joined, even if the call is still running
    ended = parse_utc(reply.get("end_time"))
    if reply.get("finished") is not True or ended is None:
        return done("not_yet", "call still running, %s not in it yet" % name)
    if clock().astimezone() < ended + dt.timedelta(minutes=SETTLE_MIN):
        return done("not_yet", "call just ended, waiting %d minutes for Zoom's list" % SETTLE_MIN)
    return done("absent")


def check_attendance(zoom_id, name, day):
    """One of "present", "absent", "not_yet", "error". The seam for tests of run_digest."""
    return attendance_detail(zoom_id, name, day)["status"]


# ---------------------------------------------------------------- the window

def window_command(handbook, prompt_file, claude_config_dir):
    cmd = "cd %s && " % shlex.quote(str(handbook))
    if claude_config_dir:
        cmd += "export CLAUDE_CONFIG_DIR=%s && " % shlex.quote(claude_config_dir)
    return cmd + 'exec claude "$(cat %s)"' % shlex.quote(str(prompt_file))


def open_window(cmd, script):
    """Open a Terminal window that runs cmd, from a .command file.

    `open -a Terminal` needs no Apple Events, so no Automation permission. A
    launchd job that asks to control Terminal through osascript hangs on the
    permission prompt or is refused, so the window never opened.
    """
    try:
        script.write_text("#!/bin/bash\n" + cmd + "\n", encoding="utf-8")
        script.chmod(0o755)
    except OSError:
        return False
    rc, _, _ = run_cmd(["open", "-a", "Terminal", str(script)])
    return rc == 0


def window_script_windows(handbook, prompt_file, claude_config_dir):
    """The PowerShell the Windows window runs. Claude gets one line naming the
    prompt file: the multi-line prompt itself would be cut at the first line break
    by the .cmd shim npm installs."""
    # Stop on the first error: a Set-Location that fails must not start claude
    # in the home folder instead of the handbook.
    lines = ["$ErrorActionPreference = 'Stop'", "Set-Location -LiteralPath %s" % ps_str(handbook)]
    if claude_config_dir:
        lines.append("$env:CLAUDE_CONFIG_DIR = %s" % ps_str(claude_config_dir))
    lines.append("claude %s" % ps_str(
        "/scripta:daily-digest The noon schedule wrote today's details to %s. "
        "Read that file first and follow it." % Path(prompt_file).as_posix()))
    return "\n".join(lines) + "\n"


def open_window_windows(text, script):
    """Open a PowerShell window that runs the script. `start ""` returns at once,
    so the run does not wait on the window."""
    try:
        # With a BOM: Windows PowerShell 5.1 reads a .ps1 without one as the
        # ANSI code page, which garbles a non-ASCII path.
        script.write_text(text, encoding="utf-8-sig")
    except OSError:
        return False
    rc, _, _ = run_cmd(["cmd.exe", "/c", "start", "", "powershell.exe", "-NoExit", "-NoProfile",
                        "-ExecutionPolicy", "Bypass", "-File", str(script)], detach=True)
    return rc == 0


def build_prompt(day, handbook, todays, check, prev_missing, backup_notes=None):
    date = day.isoformat()
    names = ", ".join(m["title"] for m in todays)
    what = names if names else "today's team meetings: the dailies, and on Mondays the squad planning"
    lines = ["/scripta:daily-digest for %s." % what,
             "Today is %s. The handbook is at %s." % (date, handbook),
             "The noon schedule opened this window. It changes no digest step: "
             "I triage with you as usual."]
    if check is None or check.failed:
        lines.append("Today's digest could not be checked (a git or gh error, maybe no network yet). "
                     "Check it in Step 0.7 with me before digesting.")
    else:
        titles = [m["title"] for m in todays]
        missing = [t for t in titles if t not in check.done]
        pr = check.today_prs[0]["url"] if check.today_prs else ""
        if titles and not missing:
            lines.append("Every one of these meetings is already in today's digest (%s). "
                         "Step 0.7 decides with me whether to digest any again." % ", ".join(check.urls or [pr]))
        elif check.done:
            lines.append("Today's digest already holds: %s (%s). Still missing: %s. "
                         "Step 0.7 decides with me." % (", ".join(check.done), ", ".join(check.urls),
                                                       ", ".join(missing)))
        elif pr:
            lines.append("Today's digest PR %s exists but holds none of these meetings"
                         "%s. Step 0.7 decides with me." % (pr, (": " + ", ".join(missing)) if missing else ""))
    for m in todays:
        note = (backup_notes or {}).get(m["title"])
        if note == "absent":
            lines.append("%s was not in %s today, so this is your summary as backup."
                         % (m["backup_for"], m["title"]))
        elif note == "unknown":
            lines.append("The check could not tell whether %s was in %s today. "
                         "Step 0.7 decides with me whether this is my summary as backup."
                         % (m["backup_for"], m["title"]))
    if prev_missing:
        lines.append("The previous weekday, %s, has no digest PR. Digest only today's meetings; "
                     "do not add that day." % prev_missing)
    return "\n".join(lines) + "\n"


def by_hand_command(handbook):
    if is_windows():
        return "Set-Location -LiteralPath %s; claude, then type /scripta:daily-digest" % ps_str(handbook)
    return "cd %s && claude, then type /scripta:daily-digest" % shlex.quote(str(handbook))


# ---------------------------------------------------------------- run / try

def run_digest(now, try_mode):
    """The decision in the flowchart. Returns an exit code."""
    state = load_state()
    if state is None:
        notify("The noon digest is not set up. Run digest_schedule.py install.")
        return 0
    day = now.date()
    date = day.isoformat()
    minutes = now.hour * 60 + now.minute

    def record(outcome):
        if not try_mode:
            state["last_run"] = {"date": date, "outcome": outcome}
            save_state(state)

    def finish(outcome):
        record(outcome)
        log(outcome)
        return 0

    if not try_mode:
        if day.weekday() >= 5:
            return finish("skipped: weekend")
        if minutes < OPEN_FROM:
            return finish("skipped: before 11:00")
        if state.get("last_opened") == date:
            log("skipped: window already opened today")
            return 0
        if state.get("concluded") == date:
            log("skipped: today's backup check already concluded")
            return 0
        if minutes > OPEN_UNTIL:
            notify("Today's noon digest was missed. Start it by hand when you can.")
            return finish("missed: after 18:00")

    todays = [m for m in state.get("meetings", []) if day.weekday() in m["days"]]
    if not try_mode and state.get("meetings") and not todays:
        return finish("skipped: no saved meeting today")

    hb = Path(state.get("handbook", {}).get("path") or "/nonexistent-handbook")
    if not (hb / "where-truth-lives.md").is_file():
        notify("The handbook checkout was not found at %s. Fix the path, then start the digest by hand: %s"
               % (hb, by_hand_command(hb)))
        return finish("failed: handbook missing")
    if not which_on("claude", os.environ.get("PATH", "")):
        notify("claude was not found on the job's PATH. Install it or link it into ~/.local/bin, "
               "then start the digest by hand: %s" % by_hand_command(hb))
        return finish("failed: claude not found")

    titles = [m["title"] for m in todays]
    check = check_digest(hb, day, titles)

    if not try_mode and not check.failed and titles and set(titles) <= set(check.done):
        notify("Today's digest is done: %s are in %s." % (", ".join(titles), ", ".join(check.urls)))
        if any(is_backup(m) for m in todays):
            state["concluded"] = date
        return finish("skipped: done")

    # Backup meetings (try skips this: it opens the window now, with no checks).
    # A person is in practice either main or backup, so a mixed install stays
    # simple: the one window opens once nothing is pending any more (or at 17:00),
    # with every meeting that remains.
    backup_notes = {}
    has_backup = any(is_backup(m) for m in todays)
    if has_backup and not try_mode:
        known = state.setdefault("attendance", {}).setdefault(date, {})
        for k in [k for k in state["attendance"] if k != date]:
            del state["attendance"][k]
        kept, pending = [], []
        for m in todays:
            if not is_backup(m) or (not check.failed and m["title"] in check.done):
                kept.append(m)
                continue
            result = known.get(m["title"])
            if result is None:
                result = check_attendance(m["zoom_id"], m["backup_for"], day)
                if result in ("present", "absent"):
                    known[m["title"]] = result  # a settled answer is not asked again today
            if result == "present":
                log("skipped: %s was in %s" % (m["backup_for"], m["title"]))
                continue
            kept.append(m)
            if result == "absent":
                backup_notes[m["title"]] = "absent"
            else:
                backup_notes[m["title"]] = "unknown"
                pending.append(m)
        if pending and minutes < DECIDE_BY:
            return finish("waiting: cannot tell yet whether the main person was in %s" % ", ".join(m["title"] for m in pending))
        if not kept or (not check.failed and all(m["title"] in check.done for m in kept)):
            state["concluded"] = date
            return finish("skipped: nothing left to digest today")
        todays = kept

    prev_missing = ""
    if not check.failed and check.prev_has_pr is False:
        prev_missing = previous_weekday(day).isoformat()
    prompt = build_prompt(day, hb, todays, check, prev_missing, backup_notes)

    state_dir().mkdir(parents=True, exist_ok=True)
    pf = state_dir() / ("prompt-%s.txt" % date)
    pf.write_text(prompt, encoding="utf-8")
    if not try_mode:
        state["last_opened"] = date
    record("opened")
    cfg = state.get("claude_config_dir", "")
    if is_windows():
        cmd = by_hand_command(hb)
        opened = open_window_windows(window_script_windows(hb, pf, cfg),
                                     state_dir() / ("window-%s.ps1" % date))
    else:
        cmd = window_command(hb, pf, cfg)
        opened = open_window(cmd, state_dir() / ("window-%s.command" % date))
    if opened:
        log("opened window")
    else:
        notify("The %s window did not open. Run this by hand: %s"
               % ("PowerShell" if is_windows() else "Terminal", cmd))
        if not try_mode:
            state.pop("last_opened", None)  # no window opened, so a later run today may try again
        record("failed: window did not open")
    return 0


# ---------------------------------------------------------------- install / uninstall / status

def schedule_times(retries):
    """(hour, minute) pairs: noon, plus every 30 minutes to 17:00 for a backup install."""
    times = [(12, 0)]
    if retries:
        t = 12 * 60 + RETRY_STEP
        while t <= DECIDE_BY:
            times.append((t // 60, t % 60))
            t += RETRY_STEP
    return times


def build_plist(claude_config_dir, retries=False):
    env = {"PATH": job_path()}
    if claude_config_dir:
        env["CLAUDE_CONFIG_DIR"] = claude_config_dir
    out = str(log_file())
    return {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/env", "python3", "-c", LOADER],
        "StartCalendarInterval": [{"Weekday": d, "Hour": h, "Minute": mi}
                                  for d in range(1, 6) for h, mi in schedule_times(retries)],
        "EnvironmentVariables": env,
        "StandardOutPath": out,
        "StandardErrorPath": out,
    }


def build_task(retries):
    """Windows: the schtasks /Create call. Noon Monday to Friday like the plist;
    a backup install repeats every RETRY_STEP minutes to DECIDE_BY (the extra
    minute lets the 17:00 run fire). /TR keeps one level of quotes per path:
    schtasks parses it again when the task fires."""
    argv = ["schtasks", "/Create", "/F", "/TN", LABEL, "/SC", "WEEKLY",
            "/D", "MON,TUE,WED,THU,FRI", "/ST", "12:00",
            "/TR", '"%s" "%s"' % (task_python(), loader_file())]
    if retries:
        h, m = divmod(DECIDE_BY - 12 * 60 + 1, 60)
        argv += ["/RI", str(RETRY_STEP), "/DU", "%02d:%02d" % (h, m)]
    return argv


def build_loader(claude_config_dir):
    """Windows: the loader file. A task cannot set environment variables, so a
    CLAUDE_CONFIG_DIR given at install goes in here."""
    head = "import os\n"
    if claude_config_dir:
        head += "os.environ.setdefault('CLAUDE_CONFIG_DIR', %r)\n" % claude_config_dir
    return head + LOADER


def task_installed():
    return run_cmd(["schtasks", "/Query", "/TN", LABEL])[0] == 0


# schtasks /Create cannot set these, and its defaults skip a noon run on battery
# and never catch up a missed one, so a laptop that is unplugged or asleep at
# 12:00 would lose the day with nothing in the log.
TASK_SETTINGS = ("$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
                 "-StartWhenAvailable; Set-ScheduledTask -TaskName %s -Settings $s | Out-Null")


def task_command():
    """The program the installed task starts, or "" when it cannot be read."""
    rc, out, _ = run_cmd(["schtasks", "/Query", "/TN", LABEL, "/XML"])
    m = re.search(r"<Command>(.*?)</Command>", out or "", re.S) if rc == 0 else None
    return m.group(1).strip().strip('"') if m else ""


def cmd_install(meeting_args):
    if is_windows():
        system = "Windows"
    else:
        _, out, _ = run_cmd(["uname"])
        system = "Darwin" if out.strip() == "Darwin" else ""
        if re.match(r"(MINGW|MSYS|CYGWIN)", out.strip()):
            print("This python is the MSYS or Cygwin one, which cannot use Task Scheduler. Run install "
                  "with the Windows Python: py -3 (or python) instead of python3.")
            return 1
    if not system:
        print("The noon schedule runs on macOS and Windows only. Run install on your Mac or Windows PC.")
        return 1
    hb, source = find_handbook()
    if hb is None:
        print("No handbook checkout found. Clone your team's handbook, then set "
              "handbook_path in ~/.config/scripta/config.json and run install again.")
        return 1
    try:
        meetings = [parse_meeting(a) for a in meeting_args]
    except ValueError as e:
        print("Bad --meeting: %s" % e)
        return 2
    state = load_state() or {}
    if not meetings:
        if stdin_is_tty():
            meetings = ask_meetings()
        elif state.get("meetings"):
            meetings = state["meetings"]
            print("Keeping the saved meetings: %s" % ", ".join(m["title"] for m in meetings))
    if not meetings:
        print("No meetings saved: the window will open every weekday at 12:00, "
              "even when the digest is already done.")
    state["meetings"] = meetings
    state["handbook"] = {"path": str(hb), "source": source}
    cfg = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if cfg:
        state["claude_config_dir"] = cfg
    else:
        state.pop("claude_config_dir", None)
    save_state(state)
    retries = any(is_backup(m) for m in meetings)
    if system == "Windows":
        loader_file().write_text(build_loader(cfg), encoding="utf-8")
        rc, _, err = run_cmd(build_task(retries))
        if rc != 0:
            print("Task Scheduler refused the task: %s" % (err.strip() or "no reason given"))
            print("Task creation is blocked in some locked-down shells. Run install from a normal "
                  "terminal, then check with status.")
            return 1
        rc, _, err = run_cmd(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                              TASK_SETTINGS % ps_str(LABEL)])
        if rc != 0:
            print("Warning: could not let the task run on battery or catch up a missed noon (%s). "
                  "It runs only on mains power and while the laptop is awake at 12:00."
                  % (err.strip() or "no reason given"))
    else:
        plist = plist_file()
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(plistlib.dumps(build_plist(cfg, retries)))
        run_cmd(["launchctl", "unload", str(plist)])
        rc, _, err = run_cmd(["launchctl", "load", str(plist)])
        if rc != 0:
            print("launchctl load failed: %s" % err.strip())
            return 1
    print("Installed.")
    cmd_status()
    if any(is_backup(m) for m in meetings):
        print("Backup meetings found. Testing that your Zoom can see who joined:")
        cmd_check()
    print("Next: run `digest_schedule.py try` to open a window now and see it work.")
    return 0


def cmd_uninstall():
    if is_windows():
        if not task_installed():
            print("Schedule not installed.")
            return 0
        rc, _, err = run_cmd(["schtasks", "/Delete", "/F", "/TN", LABEL])
        if rc != 0:
            print("Task Scheduler did not remove the task: %s. It is still on; the loader stays "
                  "so it keeps working." % (err.strip() or "no reason given"))
            return 1
        try:
            loader_file().unlink()
        except OSError:
            pass
        print("Schedule removed. Open windows and %s are left as they were." % log_file())
        return 0
    plist = plist_file()
    if not plist.exists():
        print("Schedule not installed.")
        return 0
    run_cmd(["launchctl", "unload", str(plist)])
    plist.unlink()
    print("Schedule removed. Open windows and %s are left as they were." % log_file())
    return 0


def newest_version(cache_root):
    found = []
    try:
        names = os.listdir(str(cache_root))
    except OSError:
        return ""
    for v in names:
        try:
            k = tuple(int(x) for x in v.split("."))
        except ValueError:
            continue
        if (cache_root / v / "skills" / "daily-digest" / "scripts" / "digest_schedule.py").is_file():
            found.append((k, v))
    return max(found)[1] if found else ""


def cmd_status():
    state = load_state() or {}
    plist = plist_file()
    installed = plist.exists()
    path = job_path()
    if is_windows():
        if not task_installed():
            print("Schedule: not installed")
        else:
            cmd = task_command()
            if cmd and not Path(cmd).is_file():
                print("Schedule: installed in Task Scheduler, but the Python it starts (%s) is gone. "
                      "Run install again." % cmd)
            else:
                print("Schedule: installed in Task Scheduler")
    elif installed:
        try:
            path = plistlib.loads(plist.read_bytes())["EnvironmentVariables"]["PATH"]
        except Exception:
            pass
        loaded = run_cmd(["launchctl", "list", LABEL])[0] == 0
        print("Schedule: installed and loaded" if loaded else
              "Schedule: installed but NOT loaded (run install again)")
    else:
        print("Schedule: not installed")
    meetings = state.get("meetings") or []
    if meetings:
        print("Meetings:")
        for m in meetings:
            print("  " + meeting_text(m))
    else:
        print("Meetings: none saved (the window opens every weekday)")
    hb = state.get("handbook") or {}
    print("Handbook: %s (found by: %s)" % (hb.get("path", "not saved"), hb.get("source", "-")))
    cfg = state.get("claude_config_dir") or os.environ.get("CLAUDE_CONFIG_DIR", "")
    cache = Path(cfg or str(home() / ".claude")) / "plugins" / "cache" / "scripta-plugin" / "scripta"
    ver = newest_version(cache)
    print("Scripta version the job runs: %s (in %s)" % (ver or "none found", cache))
    # On Windows the task runs task_python(); pythonw prints nothing, so ask its python.
    py = sys.executable if is_windows() else which_on("python3", path)
    if py:
        _, o, e = run_cmd([py, "--version"])
        print("python3: %s (%s)" % (py, (o or e).strip()))
    else:
        print("python3: not found on the job's PATH")
    for tool in ("claude", "git", "gh"):
        found = which_on(tool, path)
        print("%s: %s" % (tool, found if found else "not found on the job's PATH"))
    last = state.get("last_run")
    print("Last run: %s" % ("%s, %s" % (last["date"], last["outcome"]) if last else "never"))
    return 0


def cmd_check():
    """Test the attendance check now for every saved backup meeting. Opens nothing."""
    meetings = [m for m in (load_state() or {}).get("meetings", []) if is_backup(m)]
    if not meetings:
        print("No backup meetings saved. Add one with install --meeting "
              "\"<title>=<days>;backup-for=<name>;zoom=<number>\".")
        return 0
    day = clock().date()
    for m in meetings:
        # The last CHECK_DAYS days, not only today: this proves access and the name
        # before the first call, without waiting for one today.
        d = attendance_detail(m.get("zoom_id", ""), m["backup_for"], day, days_back=CHECK_DAYS)
        who, zid = m["backup_for"], m.get("zoom_id", "?")
        if d["permission"]:
            said = "your Zoom cannot open this call (permission denied). Ask the host for access."
        elif d["status"] == "error":
            said = "the check failed (%s)." % d["reason"]
        elif d["attendees"] and d["present"]:
            said = "your Zoom can see who joined meeting %s in the last %d days, and %s is among them." % (
                zid, CHECK_DAYS, who)
        elif d["attendees"]:
            said = ("your Zoom can see who joined meeting %s in the last %d days, but %s is not among "
                    "them. Check that the name matches their Zoom name." % (zid, CHECK_DAYS, who))
        else:
            said = ("your Zoom found no call for meeting %s in the last %d days (%s). Check the "
                    "meeting number and that you joined the call." % (zid, CHECK_DAYS,
                                                                      d["reason"] or "none found"))
        print("%s: %s" % (m["title"], said))
    return 0


# ---------------------------------------------------------------- CLI

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="digest_schedule.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    pi = sub.add_parser("install", help="turn the noon schedule on")
    pi.add_argument("--meeting", action="append", default=[],
                    help='"<Zoom title>=<weekdays>[;backup-for=<name>;zoom=<number>]", repeatable, '
                         'e.g. "Team - Daily=tue-fri"')
    sub.add_parser("uninstall", help="turn it off")
    sub.add_parser("status", help="show the schedule's state")
    sub.add_parser("check", help="test now whether your Zoom can see who joined each backup meeting's call")
    for name in ("run", "try"):
        p = sub.add_parser(name, help="what the scheduled job calls" if name == "run" else "open the window now")
        p.add_argument("--now", help="pretend it is this ISO datetime, e.g. 2026-10-14T12:00")
    args = ap.parse_args(argv)
    if args.command == "install":
        return cmd_install(args.meeting)
    if args.command == "uninstall":
        return cmd_uninstall()
    if args.command == "status":
        return cmd_status()
    if args.command == "check":
        return cmd_check()
    try:
        now = dt.datetime.fromisoformat(args.now) if args.now else clock()
    except ValueError:
        print("--now must be an ISO datetime like 2026-10-14T12:00")
        return 2
    return run_digest(now, args.command == "try")


if __name__ == "__main__":
    sys.exit(main())

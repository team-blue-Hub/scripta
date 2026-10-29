#!/usr/bin/env python3
"""SessionStart hook: point sessions at the handbook without loading it.

Emits a short pointer only — the handbook path, what it's authoritative for, and
where to read the rest. It does NOT inject the map pages (index.md,
where-truth-lives.md) anymore. That over-anchored sessions on the handbook: it got
consulted even for questions about the live in-session work or the code, and the
model sometimes concluded things didn't exist because they weren't in the handbook
(For example, asked "what did we build an hour ago", the model checked the
handbook, found nothing, and said nothing was built.)

The fix:
    1. This hook shrinks to the pointer below. It still runs every SessionStart
       and still does the freshness pull, and spends tokens only on the
       pointer, not the full maps.
    2. hooks/load_scripta_on_prompt.py (UserPromptSubmit) injects the full maps,
       and only when the user's prompt looks like a team-fact question. It
       imports assemble_maps_payload() and locate_repo() from this module, so the
       assembly logic below (frontmatter stripping, index compaction, the
       MAX_BYTES guard) is shared by both hooks.

This is NOT the per-prompt injection that was measured and rejected on
context bloat / session speed / token cost — this version fires only on
trigger-matched prompts, a small fraction of turns. But it is also NOT yet
measured: those old numbers don't carry over to a triggered design, and this
needs its own measurement before team-wide rollout.

Size still matters for the on-demand payload: Claude Code offloads hook output
bigger than ~10KB to a file and puts only a ~2KB preview into context, which
silently destroys the injection (an append-only list can double the
payload in weeks). Two defenses, still
in force for whatever calls assemble_maps_payload():
    1. compact_index() replaces the per-ADR bullets — the only unbounded
       section — with a one-line pointer to decisions/; frontmatter is
       stripped from both pages.
    2. A hard MAX_BYTES guard trims the assembled payload with a visible
       notice, so future handbook growth degrades loudly, never silently.

Registration is automatic: this hook is declared in hooks/hooks.json next to this
file, so it loads wherever scripta is enabled (per-project via enabledPlugins)
and ${CLAUDE_PLUGIN_ROOT} resolves to the installed plugin dir at runtime — no
versioned paths in anyone's settings, and it survives plugin updates. Where no
handbook checkout is found it stays silent (see main() below), so it is harmless
even when the plugin is enabled globally. Nothing to wire by hand.

(The hooks.json command invokes `python3`. On Windows, `python` or `py -3` may be needed.)

Handbook location, in order of precedence:
    1. SCRIPTA_HANDBOOK_PATH env var
    2. "handbook_path" in ~/.config/scripta/config.json
    3. default: ~/PROJECTS/hub-scripta-handbook, then ~/PROJECTS/scripta
The config file is the elegant way to point at a checkout outside ~/PROJECTS —
no env var to persist for the hook's subprocess, no symlink.

Config (env, all optional):
    SCRIPTA_HOOK_TTL_MIN    minutes between freshness pulls (default: 30)

Freshness: a git pull runs at most once per TTL window (marker file in .git/).
A failed pull is swallowed — slightly stale truth beats a blocked session start.

Link warning: the links in where-truth-lives.md can be dead, or ones this person
cannot open, and a session that follows them gets nothing back and says nothing.
So the hook adds one line naming the links that did not open for this person.
It never does the check itself (no network at session start). It reads a cache in
.git/ and, when the cache is stale, starts the checker in a detached background
process, at most once per window, with the person's own `gh` login. The warning
never blocks anything.
    SCRIPTA_LINK_CHECK=0        turn the feature off (no read, no refresh)
    SCRIPTA_LINK_CHECK_HOURS    hours between checks (default: 24)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

MAP_PAGES = ("index.md", "where-truth-lives.md")
LINKS_PAGE = MAP_PAGES[1]
PULL_MARKER = "scripta-hook-last-pull"
LINK_CACHE = "scripta-link-check.json"
LINK_LOCK = "scripta-link-check.started"
LINK_LOCK_MIN = 15  # a refresh that died leaves its lock behind; ignore it after this
LINK_SHOWN_CAP = 5
LINK_WARN_CLASSES = {"no-access": "no access", "gone": "gone"}
CONFIG_FILE = Path.home() / ".config" / "scripta" / "config.json"

# Claude Code offloads hook output near 10KB; stay clearly under so the whole
# payload always lands inline. Includes headroom for slow catalog growth.
MAX_BYTES = 9_000
REGISTRY_CELL_CAP = 140  # compact_registry: max chars kept of a home cell
SELF_LINK = re.compile(r"\[`?([^\]`]+?)`?\]\(\1\)")  # compact_registry: [`p`](p) -> `p`


def strip_frontmatter(text: str) -> str:
    """Drop a leading YAML frontmatter block — metadata for the repo, not the model."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4:].lstrip("\n")


def compact_index(text: str) -> str:
    """Replace the per-ADR bullets in index.md with a one-line pointer.

    The ADR list is append-only, so it is the payload's only unbounded section
    (and it grows with every digest). The titles are
    discoverable on demand (`ls decisions/`); what the session needs inline is
    that the log exists and where it lives.
    """
    out: list[str] = []
    in_decisions = False
    dropping = False  # inside a dropped bullet: swallow its wrapped/nested lines too
    dropped = 0

    def flush_pointer() -> None:
        nonlocal dropped
        if dropped:
            noun = "ADR" if dropped == 1 else "ADRs"
            out.append(f"{dropped} dated {noun} — list `decisions/` and read the relevant one on demand.")
            out.append("")
            dropped = 0

    for line in text.splitlines():
        if line.startswith("## "):
            flush_pointer()
            in_decisions = line.strip().lower().startswith("## decisions")
            dropping = False
            out.append(line)
            continue
        if in_decisions:
            if line.lstrip().startswith("- [") and not line[:1].isspace():
                dropped += 1
                dropping = True
                continue
            if dropping and line[:1].isspace() and line.strip():
                continue  # continuation or sub-bullet of the dropped entry above
            dropping = False
        out.append(line)
    flush_pointer()
    return "\n".join(out)


def compact_registry(text: str) -> str:
    """Shorten where-truth-lives.md table rows to fact + first pointer.

    The registry is the router: every fact-to-home pair must reach the session,
    which the blunt tail-trim below cannot guarantee. What CAN go is the prose that grew into the home cells — owners,
    history, caveats — which lives one Read away on the page itself. Each home
    cell keeps its first sentence-or-pointer fragment, capped at
    REGISTRY_CELL_CAP chars, with an ellipsis marking the cut. Non-table lines
    pass through untouched.
    """
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        # Not a row, or a separator row (only pipes/dashes/colons/spaces).
        if not stripped.startswith("|") or set(stripped) <= set("|-: "):
            out.append(line)
            continue
        # Two-column split on the FIRST cell boundary only: a literal `|`
        # inside the home cell (a shell pipeline in backticks, say) must not
        # shear the row apart.
        inner = stripped[1:-1] if stripped.endswith("|") else stripped[1:]
        fact, sep, home = (part.strip() for part in inner.partition(" | "))
        if not sep or fact.lower() == "the fact":  # malformed or header row
            out.append(line)
            continue
        # A link whose text is its own target says the path twice:
        # [`legal/x.md`](legal/x.md). The session only needs it once, as a path
        # it can Read, so it arrives as `legal/x.md`. Nothing is lost.
        # Links whose text differs from the
        # target (a repo name, a dashboard) are left alone.
        home = SELF_LINK.sub(r"`\1`", home)
        # Anchor the cut on the first markdown link when there is one: the
        # pointer IS the row's payload, and a bare sentence-split eats it when
        # an abbreviation ("J. Smith", "e.g.") precedes the link. A
        # link-anchored fragment is kept whole even past the cap —
        # a home without its home defeats the row; the ladder still checks
        # the total against MAX_BYTES.
        if len(home) <= REGISTRY_CELL_CAP:
            out.append(f"| {fact} | {home} |")
            continue
        to_link = re.match(r"(.*?\[[^\]]*\]\([^)]*\))", home)
        if to_link and len(to_link.group(1)) <= REGISTRY_CELL_CAP:
            cut = to_link.group(1)
        elif to_link:
            # Pre-link prose alone blows the cap: the prose is expendable,
            # the pointer is not — keep just the first link.
            cut = re.search(r"\[[^\]]*\]\([^)]*\)", home).group(0)
        else:
            cut = re.split(r"(?<=[.;]) | — ", home)[0]
            if len(cut) > REGISTRY_CELL_CAP:
                cut = cut[:REGISTRY_CELL_CAP].rstrip() + "…"
        if cut != home and not cut.endswith("…"):
            cut = cut.rstrip() + " …"
        out.append(f"| {fact} | {cut} |")
    return "\n".join(out)


def skeletal_index(text: str) -> str:
    """Drop the per-page descriptions from index bullets, keeping only the links.

    The third rung of the size ladder: when even compacted registry rows leave
    the payload over budget, the index gives way before the registry does — the
    catalog is browsable on demand, the router is not optional. Applied on top
    of compact_index()'s output.
    """
    return "\n".join(
        re.sub(r"^(\s*- \[[^\]]+\]\([^)]+\))\s+—.*$", r"\1", line)
        for line in text.splitlines()
    )


def configured_path() -> str:
    """Handbook path from ~/.config/scripta/config.json, or "" if absent/invalid.

    Lets a teammate point at a checkout outside ~/PROJECTS without an env var or
    symlink. The env var still wins over this; a missing or malformed file falls
    through to the defaults silently.
    """
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return str(cfg.get("handbook_path") or "")
    except Exception:
        return ""


def index_pointer(_text: str) -> str:
    """Replace the whole index with one line naming where it is.

    The fourth rung. The index is a catalog: useful, and readable on demand from
    the checkout. The registry is the router, and a router that arrives with
    rows missing sends a session to the wrong place, or to nowhere. When the two
    cannot both fit, the catalog is the one that gives way.
    """
    return "(not inlined — read index.md from the checkout for the full catalog)"


def registry_table_only(text: str) -> str:
    """Keep the registry's table and drop the prose around it.

    The fifth rung, and the last one before the blunt cut. Applied on top of
    compact_registry(), so every fact-to-home pair still arrives; what goes is
    the page's own framing, which the header above already says in fewer words.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.lstrip().startswith("| The fact")), None)
    if start is None:
        return text
    # Blank lines do not end the table: a grouping break between rows would
    # otherwise drop every row below it, silently, while the rung's note still
    # claims the table arrived whole. Prose ends it.
    rest = lines[start:]
    prose = next((i for i, line in enumerate(rest)
                  if line.strip() and not line.strip().startswith("|")),
                 len(rest))
    return "\n".join(line for line in rest[:prose] if line.strip())


def locate_repo() -> Path | None:
    """Find the handbook checkout, honoring the override/default precedence above.

    Returns None if no candidate has a where-truth-lives.md — the shared "is there
    a handbook here at all" check used by both hooks before they do anything else.
    """
    override = os.environ.get("SCRIPTA_HANDBOOK_PATH", "") or configured_path()
    candidates = [Path(override).expanduser()] if override else [
        Path.home() / "PROJECTS" / "hub-scripta-handbook",
        Path.home() / "PROJECTS" / "scripta",  # legacy checkout path
    ]
    return next((c for c in candidates
                 if (c / "where-truth-lives.md").is_file()), None)


def freshen(repo: Path, ttl_min: int) -> None:
    marker = repo / ".git" / PULL_MARKER
    # Inside the TTL window: skip the pull WITHOUT re-stamping. The marker must
    # measure time since the last pull *attempt*, not the last session — stamping
    # here would reset the window on every session, so a user opening sessions
    # more often than the TTL would never pull again (the throttle never expires).
    if marker.exists() and (time.time() - marker.stat().st_mtime) < ttl_min * 60:
        return
    try:
        subprocess.run(
            ["git", "-C", str(repo), "pull", "--ff-only", "--quiet"],
            timeout=15, capture_output=True, check=False,
        )
    except Exception:
        pass  # never block a session on freshness
    finally:
        # Stamp on any pull *attempt* (incl. timeout/failure), so a flaky network
        # throttles to one attempt per TTL window instead of re-pulling and stalling
        # up to 15s on EVERY subsequent session until it recovers.
        try:
            marker.touch()
        except Exception:
            pass


def _is_windows() -> bool:
    return os.name == "nt"


def _read_link_cache(repo: Path) -> dict | None:
    try:
        data = json.loads((repo / ".git" / LINK_CACHE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _page_sha(repo: Path) -> str | None:
    try:
        return hashlib.sha256((repo / LINKS_PAGE).read_bytes()).hexdigest()
    except Exception:
        return None


def link_warning(repo: Path) -> str:
    """One line naming handbook links that did not open for this person, or "".

    Reads the cache only. A finding counts when it is no-access or gone and its
    target is still on the page, so a link fixed since the check drops out.
    """
    try:
        cache = _read_link_cache(repo)
        if not cache:
            return ""
        page = (repo / LINKS_PAGE).read_text(encoding="utf-8")
        seen: dict[str, str] = {}
        for f in cache.get("findings") or []:
            label = LINK_WARN_CLASSES.get(f.get("error_class"))
            target = f.get("target")
            if label and isinstance(target, str) and target in page:
                seen.setdefault(target, label)
        if not seen:
            return ""
        items = list(seen.items())
        shown = ", ".join(f"{t} ({label})" for t, label in items[:LINK_SHOWN_CAP])
        if len(items) > LINK_SHOWN_CAP:
            shown += f", and {len(items) - LINK_SHOWN_CAP} more"
        day = str(cache.get("checked_at") or "")[:10]
        return (f"Handbook links that did not open for you (checked {day}): {shown}. "
                "If an answer depends on one, say you could not read it; do not guess its content.")
    except Exception:
        return ""


def maybe_refresh_links(repo: Path, hours: float) -> None:
    """Start a detached background check when the cache is stale. Never waits."""
    try:
        cache = _read_link_cache(repo)
        stale = True
        if cache:
            checked = datetime.fromisoformat(str(cache["checked_at"]).replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - checked).total_seconds() / 3600
            stale = age_h >= hours or cache.get("page_sha256") != _page_sha(repo)
        if not stale:
            return
        lock = repo / ".git" / LINK_LOCK
        if lock.exists() and (time.time() - lock.stat().st_mtime) < LINK_LOCK_MIN * 60:
            return
        lock.touch()
        kwargs: dict = {}
        if _is_windows():
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--refresh-links", str(repo)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception:
        pass  # a link check must never touch session start


def _write_link_cache(repo: Path, sha: str | None, status: str, findings: list) -> None:
    body = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "page_sha256": sha,
        "status": status,
        "findings": findings,
    }
    git_dir = repo / ".git"
    fd, tmp = tempfile.mkstemp(dir=git_dir, prefix=LINK_CACHE + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(body, fh)
        os.replace(tmp, git_dir / LINK_CACHE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def refresh_links(repo: Path) -> int:
    """Run the reference checker on the links page and cache what it finds.

    A checker that cannot run is cached as skipped with no findings, so the
    window is waited out instead of retried at every session start.
    """
    try:
        sha = _page_sha(repo)
        checker = (Path(__file__).resolve().parent.parent
                   / "skills" / "curate" / "scripts" / "reference_check.py")
        status, findings = "skipped: checker not found", []
        if checker.is_file():
            try:
                run = subprocess.run(
                    [sys.executable, str(checker), "--path", str(repo),
                     "--only", LINKS_PAGE, "--json"],
                    timeout=300, capture_output=True, text=True, check=False,
                )
                if run.returncode in (0, 1):
                    report = json.loads(run.stdout)
                    findings = [{"target": f["target"], "error_class": f["error_class"]}
                                for f in report.get("findings", [])]
                    status = "checked"
                else:
                    status = f"skipped: checker exited {run.returncode}"
            except subprocess.TimeoutExpired:
                status = "skipped: checker timed out"
            except Exception:
                status = "skipped: checker output unreadable"
        _write_link_cache(repo, sha, status, findings)
    except Exception:
        pass
    return 0


def _assemble_maps(repo: Path) -> tuple[str | None, int, int]:
    """Assemble the full map-pages body: both pages, compacted, frontmatter-stripped,
    MAX_BYTES-guarded. Returns None if neither page is present.

    This payload is not injected on every session. It
    backs two on-demand paths: a human reading the checkout directly,
    and hooks/load_scripta_on_prompt.py injecting it when a prompt looks like a
    team-fact question. The framing (additive, never outranks code/READMEs/memory) is load-bearing here.
    """
    def build(index_extra, registry_fn, note: str) -> str | None:
        sections = []
        for name in MAP_PAGES:
            page = repo / name
            if page.is_file():
                text = strip_frontmatter(page.read_text(encoding="utf-8"))
                if name == "index.md":
                    text = index_extra(compact_index(text))
                else:
                    text = registry_fn(text)
                sections.append(f"--- {name} ---\n\n{text}")
        if not sections:
            return None
        return header + "\n\n".join(sections) + note

    # Scoped on purpose: the handbook is authoritative for
    # TEAM facts only — it must never read as outranking code, READMEs, or the
    # user's own memory, which made sessions skip sources they should use.
    header = (
        f"Team handbook: the repo at `{repo}` — the team's record of decisions, "
        "strategy, org, and how-we-work. For those facts, a dated page here "
        "beats a Slack thread or a Notion draft.\n"
        "This context is additive and changes nothing else: code and READMEs "
        "stay the record for how things work, your feature-flag source for what's live, "
        "the data dictionaries for schema, dashboards for metrics, and session "
        "memory for the user's own work state. If memory and a handbook page "
        "disagree on a team fact and the answer matters, verify against the "
        "primary source and fix the stale side (a handbook fix is a small PR; "
        "a memory fix is an edit).\n"
        "The registry below maps each kind of fact to its official home. Read "
        "handbook pages from the checkout on demand; do not re-read these maps, "
        "and do not bulk-read the repo.\n\n"
    )
    # The size ladder: prefer completeness, then give up the least
    # load-bearing detail first — registry prose, then index descriptions, then
    # the index itself, then the registry page's own prose. The registry
    # arrives with every fact-to-home pair intact on rungs 2-5, which is the
    # whole point: a router missing rows sends a session nowhere.
    #
    # Rungs 4 and 5 exist because rungs 1-3 can still overflow the cap on a
    # large handbook, cutting rows silently.
    compact_note = (
        "\n\n[scripta hook: registry rows shortened to fit the inline "
        "limit — the full home cells are in where-truth-lives.md]"
    )
    skeletal_note = (
        "\n\n[scripta hook: registry rows shortened and index descriptions "
        "dropped to fit the inline limit — read where-truth-lives.md and "
        "index.md from the checkout for either in full]"
    )
    no_index_note = (
        "\n\n[scripta hook: every registry row is inlined, long home cells "
        "shortened; index.md is not, read it from the checkout for the catalog]"
    )
    table_only_note = (
        "\n\n[scripta hook: the registry table is inlined without the page's "
        "own prose, and index.md is not inlined — read both from the checkout]"
    )
    identity = lambda t: t  # noqa: E731 — a name for "rung keeps this page as is"
    rungs = (
        (identity, identity, ""),
        (identity, compact_registry, compact_note),
        (skeletal_index, compact_registry, skeletal_note),
        (index_pointer, compact_registry, no_index_note),
        (index_pointer,
         lambda t: registry_table_only(compact_registry(t)), table_only_note),
    )
    # Returns (body, rung, size): the rung that fit (1-5), or TRIMMED when none
    # did, and the bytes that rung needed. On TRIMMED the size is what even the
    # last rung wanted before the cut, which is the number a fix has to beat.
    body = None
    for rung, (index_extra, registry_fn, note) in enumerate(rungs, 1):
        body = build(index_extra, registry_fn, note)
        if body is None:
            return None, 0, 0
        size = len(body.encode("utf-8"))
        if size <= MAX_BYTES:
            return body, rung, size
    needed = len(body.encode("utf-8"))
    notice = (
        "\n\n[scripta hook: payload trimmed to stay under Claude Code's "
        "inline hook-output limit — read index.md and where-truth-lives.md "
        "from the checkout for the full maps]"
    )
    # Rebuild the last rung without its own note before slicing: cutting
    # through the note and appending this one would leave a garbled double
    # tail.
    body = build(index_pointer,
                 lambda t: registry_table_only(compact_registry(t)), "")
    keep = MAX_BYTES - len(notice.encode("utf-8"))
    return body.encode("utf-8")[:keep].decode("utf-8", errors="ignore") + notice, TRIMMED, needed


# What each rung gives up, in words a person reading a CI log or a session
# warning can act on. Rung 4 is the last one that still carries the registry
# page's own rules; rung 5 drops them, and TRIMMED loses registry rows.
TRIMMED = 6
MAX_OK_RUNG = 4
RUNG_NAMES = {
    1: "both pages in full",
    2: "registry rows shortened",
    3: "registry rows shortened, index descriptions dropped",
    4: "index.md not inlined, every registry row and the page's own rules arrive",
    5: "the registry page's own rules dropped",
    TRIMMED: "the tail cut off, so the last registry rows never arrive",
}


def assemble_maps_payload(repo: Path) -> str | None:
    """The body a session receives. See _assemble_maps for how it is built."""
    return _assemble_maps(repo)[0]


def maps_payload_report(repo: Path) -> dict | None:
    """What a session receives from this handbook, and whether it is whole.

    ok is True while the payload fits at rung MAX_OK_RUNG or better. This is the
    one measurement the handbook's CI, the scheduled check and the prompt hook's
    warning all use, so there is no second copy of the rules to drift from.
    """
    body, rung, size = _assemble_maps(repo)
    if body is None:
        return None
    return {"body": body, "rung": rung, "bytes": size, "cap": MAX_BYTES,
            "ok": rung <= MAX_OK_RUNG, "what": RUNG_NAMES[rung]}


def check_maps_cli(path: str) -> int:
    """`--check-maps <handbook dir>`: 0 when the maps arrive whole, 1 when not,
    2 when neither map page is there."""
    report = maps_payload_report(Path(path))
    if report is None:
        print(f"handbook maps: no index.md or where-truth-lives.md under {path}")
        return 2
    rung, size, cap, what = report["rung"], report["bytes"], report["cap"], report["what"]
    if report["ok"]:
        print(f"handbook maps fit: {size:,} of {cap:,} bytes at step {rung} of 5 ({what}), "
              f"{cap - size:,} bytes to spare.")
        return 0
    if rung == TRIMMED:
        print(f"handbook maps too big: even step 5 needs {size:,} of {cap:,} bytes, so {what}. "
              "Retire or merge a row in where-truth-lives.md.")
    else:
        print(f"handbook maps too big: they fit only at step {rung} of 5 ({what}), {size:,} of "
              f"{cap:,} bytes. Shorten or retire a row in where-truth-lives.md.")
    return 1


def _pointer_text(repo: Path) -> str:
    """The minimal SessionStart payload: a pointer, not the maps themselves."""
    return (
        f"A team handbook exists at `{repo}`. It is authoritative for TEAM facts "
        "only — decisions, strategy, org, how-we-work — and never outranks the "
        "current session's work, the code, READMEs, your feature-flag source, dashboards, or "
        "your own memory.\n"
        "The full maps (index.md, where-truth-lives.md) aren't loaded here; read "
        "them from the checkout on demand, or a companion prompt hook will "
        "surface them automatically when a prompt looks like a team-fact "
        "question."
    )


def main() -> int:
    repo = locate_repo()
    if repo is None:
        return 0  # no handbook checkout here — stay silent

    try:
        ttl = int(os.environ.get("SCRIPTA_HOOK_TTL_MIN", "30"))
    except ValueError:
        ttl = 30
    freshen(repo, ttl)

    try:
        text = _pointer_text(repo)
    except Exception:
        return 0  # must never crash session start
    if os.environ.get("SCRIPTA_LINK_CHECK") != "0":
        try:
            hours = float(os.environ.get("SCRIPTA_LINK_CHECK_HOURS", "24"))
            if not hours > 0 or hours == float("inf"):
                hours = 24.0
        except ValueError:
            hours = 24.0
        maybe_refresh_links(repo, hours)
        warning = link_warning(repo)
        if warning:
            text += "\n" + warning

    try:
        json.dump({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }}, sys.stdout)
    except Exception:
        return 0  # must never crash session start
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--refresh-links":
        raise SystemExit(refresh_links(Path(sys.argv[2])))
    if len(sys.argv) >= 2 and sys.argv[1] == "--check-maps":
        raise SystemExit(check_maps_cli(sys.argv[2] if len(sys.argv) > 2 else "."))
    raise SystemExit(main())

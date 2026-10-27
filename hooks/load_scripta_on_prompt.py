#!/usr/bin/env python3
"""UserPromptSubmit hook: inject the handbook's map pages, gated on relevance.

Companion to hooks/load_scripta_context.py (the SessionStart hook), which
emits only a short pointer to the handbook. This hook injects the
full maps, but only when the user's prompt looks like a team-fact
question (decisions, org, strategy, how-we-work, "where does X live", etc).

Injecting the maps on every prompt costs too much context, so this hook fires
only on prompts that match the triggers below.

Fast path matters: the common case is no match, and that must stay cheap. The
trigger check is a single regex pass over the prompt text, done BEFORE any file
read or subprocess call. Only a match proceeds to locate the repo, freshen it,
and read the map pages.

Never crashes a prompt: every step is wrapped so a malformed hook payload, a
missing repo, or an unreadable page all fall through to "output nothing, exit 0"
— same discipline as the SessionStart hook.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_scripta_context import freshen, locate_repo, maps_payload_report

# Starter set of word/phrase triggers that suggest the prompt is asking about
# a team fact rather than the code or the live session. Tune it to your team. Deliberately broad on a few entries ("where do",
# "brand") — expect false positives. "scripta" and "handbook" are both in here too,
# so naming either is already the manual escape hatch — no separate check needed.
_WORD_TRIGGERS = r"decid\w*|adrs?|handbook|scripta|strateg\w*|roadmap|onboard\w*|brand\w*|registr\w*"
_PHRASE_TRIGGERS = (
    r"source of truth|org chart|who owns|who is responsible|expert on|"
    r"how we work|where do(?:es)?\b|notification family|privacy status|feature flag"
)
# "where is/are X stored/live/documented" — the wildcard variant.
_WHERE_STORED = r"\bwhere\s+(?:is|are)\b.{0,60}?\b(?:stored|lives?|documented)\b"

_TRIGGER_RE = re.compile(
    rf"\b(?:{_WORD_TRIGGERS})\b|{_PHRASE_TRIGGERS}|{_WHERE_STORED}",
    re.IGNORECASE,
)


def is_team_fact_prompt(prompt: str) -> bool:
    """True if the prompt plausibly asks about a team fact (decisions, org,
    strategy, how-we-work) rather than the code or in-session work.

    Cheap on purpose: one regex search, no I/O. This is what keeps the hook
    free on the common, unrelated prompt.
    """
    return bool(_TRIGGER_RE.search(prompt))


def _lead_line() -> str:
    return (
        "Consult the team handbook below if this prompt is a team-fact question "
        "(decisions, strategy, org, how-we-work). If it doesn't answer, look "
        "beyond it — it never overrides the current session's work or your own "
        "memory.\n\n"
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    try:
        data = json.loads(raw) if raw else {}
        prompt = data.get("prompt", "")
    except Exception:
        return 0

    if not isinstance(prompt, str) or not prompt:
        return 0

    # Fast path: no trigger match, return before touching the repo at all.
    if not is_team_fact_prompt(prompt):
        return 0

    try:
        repo = locate_repo()
        if repo is None:
            return 0  # no handbook checkout here — stay silent

        try:
            ttl = int(os.environ.get("SCRIPTA_HOOK_TTL_MIN", "30"))
        except ValueError:
            ttl = 30
        freshen(repo, ttl)

        report = maps_payload_report(repo)
        if report is None:
            return 0

        out = {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": _lead_line() + report["body"],
        }}
        # Said to the person, not only to the model. The notice inside the
        # payload reaches only the model, which has no reason to raise it.
        # A person who sees this can open the one-line PR that fixes it.
        if not report["ok"]:
            out["systemMessage"] = (
                "scripta: the handbook maps no longer fit what a session receives "
                f"({report['what']}). Shorten or retire a row in where-truth-lives.md; "
                "`python3 hooks/load_scripta_context.py --check-maps <handbook>` "
                "shows by how much.")
        json.dump(out, sys.stdout)
    except Exception:
        return 0  # a malformed/unreadable map page must never crash the prompt
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

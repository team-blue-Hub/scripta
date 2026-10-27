---
name: catch-up
description: What did I miss — the returner's briefing from the team source of truth. Reads the handbook's decision log, merged PRs, and changed pages for a given absence window and answers in one screen. Use when someone says "/scripta:catch-up", "what did I miss", "I was away since <date>", "catch me up on last week", or comes back from vacation/sick leave. Read-only by design — it never writes, posts, or opens anything.
---

# catch-up

The read half of the closed loop: digest and document put team knowledge INTO the
handbook; **catch-up plays it back to someone who was away.** One screen, newest
first, decisions before details. Read-only: this skill never writes to the repo,
never posts, never opens PRs.

A returner asks "what did I miss?" and gets the recent decisions from the log,
without reading every PR.

## Step 0 — locate the source-of-truth repo

Find the team handbook: a local checkout containing `where-truth-lives.md` and
`decisions/`. Look in the order the session hook uses: the folder in `SCRIPTA_HANDBOOK_PATH`
if it is set, otherwise `handbook_path` in `~/.config/scripta/config.json` if it is set,
otherwise `~/PROJECTS/hub-scripta-handbook`, then `~/PROJECTS/scripta`.
A set `SCRIPTA_HANDBOOK_PATH` or `handbook_path` is used alone: when that folder is not a handbook, ask, and never fall back to the `~/PROJECTS` folders.
The hook already did this at session start: when its note says "A team handbook exists at
`<path>`", use that path. If none of them is a handbook, ask the user for the path. `git pull` main first —
a stale checkout produces a stale briefing, silently.

## Step 1 — fix the window

1. The user names it ("since July 14", "last two weeks", "I was out Monday–Friday")
   → use exactly that, converted to dates.
2. No window given → ask ONE question: "Since when were you away?" Never guess a
   window; a wrong one silently hides decisions.
3. Sanity-cap at 90 days. Longer than that → say the briefing will be decisions-only
   (page-level noise across months isn't a briefing, it's an archive dump) and offer
   the strategy pages instead.

## Step 2 — gather (repo and GitHub only, in this order)

All read-only. Skip any source that errors and say so in the output — a partial
briefing that admits its gaps beats a silently incomplete one.

1. **Decisions:** every ADR in `decisions/` whose frontmatter `date:` falls in the
   window. The number, the title, one sentence from its context if the title alone
   doesn't stand — nothing more per entry.
2. **Merged changes:** `gh pr list --state merged --search "merged:>=<start>"` on the
   handbook repo. Group by area (onboarding / people / engineering / decisions /
   registry) using the changed paths.
3. **Live threads that involve the returner:** open PRs where they are a requested
   reviewer (`gh pr list --state open --search "review-requested:<their handle>"`),
   plus open PRs touching pages whose frontmatter `owner:` is them.
4. **People changes:** any `people/` page added or edited in the window (arrivals,
   departures, handovers get called out explicitly — they change who to ask).

Never reach into Slack, Notion, or Zoom here. The handbook is the team's memory;
if something the returner needs isn't in it, that absence is itself a finding
(name it in the briefing so it can be fixed via the document skill).

## Step 3 — the briefing (one screen, this shape)

```
Catch-up: <start> → today

DECISIONS (<n>)
- 0047 — <title, plain words>            <- newest first
- ...

WHO / WHAT CHANGED
- <people changes: joined, left, handover>
- <pages that materially changed, grouped, one line per group>

WAITING ON YOU (<n>)
- <PR> — you are the reviewer
- <page you own> — edited by <who>, worth a look

NOT IN THE HANDBOOK
- <known gap the gather step hit, if any — otherwise omit this section>
```

Rules: plain language, no repo jargon in the decision lines (the returner may be a
marketer); every line links to its source; nothing speculative — if it isn't in the
repo or on GitHub, it isn't in the briefing. If the window produced nothing at all,
say exactly that in one line; don't pad.

## Step 4 — offer depth, once

End with one line: "Want the full text of any of these, or a longer window?"
Then stop. No follow-up nagging, no auto-expansion.

## Guardrails

- Read-only, always: no commits, no PRs, no comments, no messages, no file writes.
- Never summarize an ADR beyond its own text — link it instead of paraphrasing
  rationale (paraphrased rationale drifts).
- The briefing states its window and its sources in the first line, so a wrong
  window is visible at a glance.

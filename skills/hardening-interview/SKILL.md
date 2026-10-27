---
name: hardening-interview
description: Interview one team member about their domain of expertise and turn the answers into verified repo facts — re-stamp what is still true, fix what changed, route what they don't know. Runs on the people/ expertise map in the team source-of-truth repo. Use when the user says "harden my area", "interview me", "run the hardening interview", "/hardening-interview", or asks to verify a teammate's pages with them. Short sessions by design (max 10 questions); recurring, not one-shot. Per-user, so the interviewee answers for their own domain only, and every change lands as a draft PR a human merges.
---

# hardening-interview

One loop: **pick an expert → ask "is this still true?" → answers become a draft PR.**
The repo gets harder every session without one person doing all the checking. The human
is always in the loop: the expert answers, a human merges. If in doubt, ask — never assume.

## Step 0 — locate the repo and the expertise map

Find the team source-of-truth repo: a local checkout containing `where-truth-lives.md` and
`decisions/`. Look in the order the session hook uses: the folder in `SCRIPTA_HANDBOOK_PATH`
if it is set, otherwise `handbook_path` in `~/.config/scripta/config.json` if it is set,
otherwise `~/PROJECTS/hub-scripta-handbook`, then `~/PROJECTS/scripta`.
A set `SCRIPTA_HANDBOOK_PATH` or `handbook_path` is used alone: when that folder is not a handbook, ask, and never fall back to the `~/PROJECTS` folders.
The hook already did this at session start: when its note says "A team handbook exists at
`<path>`", use that path. If none of them is a handbook, ask. `git pull` main before anything.

The expertise map is `people/` — one page per team member (see `people/README.md` for its
scope rules). If `people/` is not on main yet, check for an open branch/PR that adds it
(e.g. `people/roster`), use it read-only, and tell the user their interview PR will depend
on that one merging first.

Read `LEARNINGS.md` next to this file if it exists (same contract as daily-digest:
evidence-quoted entries, capped, pruned).

## Step 1 — pick the interviewee

Default: the runner. Or the person they name ("interview <name>"). Read that person's
`people/<name>.md` — the expertise bullets and "Owns / go-to for" define the whole scope
of this session. Nothing outside their domain gets asked or changed.

## Step 2 — build the question queue (max 10, oldest and shakiest first)

Collect candidate questions from four places, then rank:

1. **Their person page itself** — role, expertise list, owns-list: "still accurate?"
   (Each person is the owner of their own page.)
2. **Pages they own** — grep frontmatter `owner:` across the repo for their name. For each
   page take the 1–3 most load-bearing claims (numbers, dates, "is live on", cadences),
   NOT the whole page. Oldest `last-verified` first.
3. **Explicit uncertainty in their domain** — markers like "to be verified", "estimated",
   "pending", "not sure" in pages their expertise covers, and open questions in ADRs.
4. **Decisions they made** — ADRs whose `deciders:` include them, newest first: "does the
   Consequences section match what actually happened?"

Rank: expiring facts > uncertainty markers > plain re-stamps. Cap the session at 10
questions (~20 minutes). Say up front how many there are and that stopping early is fine.

## Step 3 — the interview

One question at a time, never a wall. **Ask like a colleague, not like a git log**: the question is about the FACT, in plain words — no file paths,
no last-verified dates, no process words ("re-stamp", "route", branch/PR numbers), no
option text that requires knowing how the repo works.

- Bad: *"engineering/repo-map.md (last verified Jul 6) lists internal tooling as ONLY:
  project-a (active) and project-b (paused). Is the internal-tooling table still accurate?"*
- Good: *"We tell newcomers the team has two internal tool projects: the shared skills
  and the paused search project. Since last week you built two more. Should the overview
  mention them?"*

One fact per question. Where the answer will land (which file, what edit) belongs in the
wrap-up summary at the end, never in the question. When the harness has a structured
question tool (Claude Code: `AskUserQuestion`), use it with these options:

- **Still true** — as written, today.
- **Changed** — they explain what's true now (free text).
- **Don't know / not mine** — routes elsewhere, never guessed.
- **Skip** — no answer recorded.

Record answers verbatim; the answer text is evidence, treat it like a transcript quote.
Stop at the cap or when they say stop. Whatever was not asked goes into the "not covered"
list — the next session starts there.

## Step 4 — outputs: one draft PR (the only write step)

Branch `harden/<person>-<date>`, one draft PR via `gh pr create --draft`, reviewer = the
interviewee. Per answer:

- **Still true** → bump that page's `last-verified:` to today. Nothing else changes.
- **Changed** → edit the claim to what they said, bump `last-verified:`, and cite the
  interview in the PR body: *per <person>, <date>: "<their verbatim answer>"*.
- **Don't know / not mine** → do NOT touch the fact. Propose the routing instead: either
  the right owner (update `owner:` in the same PR) or an entry in the team's ask list.
- **New fact they volunteer** → put it where `where-truth-lives.md` says it belongs; if it
  has no home, propose one in the PR body rather than inventing a page.

PR body: what was asked, what changed, what was re-stamped, the "not covered" list, and
absolute `https://github.com/<org>/<repo>/blob/<branch>/<path>` links (relative paths in a
PR body land on an empty Compare page). Load the `writing` skill and run it on all new
prose — it owns the four questions, the `last-verified` rule, the
relative-time→absolute-dates rule and the deslop handoff.
Verbatim interview answers are exempt: they are evidence.

NEVER merge, never push to main, never mark ready-for-review. The interviewee's approval
IS the hardening; without it the session produced nothing.

## Recurrence — why this is not one-shot

The queue is computed from `last-verified` dates and uncertainty markers, so it empties
itself: what a session re-stamps falls out, what ages comes back. Running monthly per
person keeps every domain fresh without anyone owning "check everything". There is no
session state to store — the repo IS the state.

## Guardrails

- Only the interviewee's own domain. Facts owned by others get routed, never edited.
- HR and personal content is out of scope, same as `people/README.md`'s rules.
- Answers are quotes: never paraphrase an expert's correction into something they didn't say.
- If an answer contradicts an accepted decision in `decisions/`, don't edit the decision
  (append-only) — flag it in the PR body as a superseding-ADR candidate for daily-digest.

## Eval

To test it: interview the person who owns the most pages. Expected: correct queue (their person page + pages they own, oldest first), max 10
questions, a draft PR with only `last-verified` bumps and verbatim-cited edits, zero facts
invented. Run this check after every prompt change to this file.

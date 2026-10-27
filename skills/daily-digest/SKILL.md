---
name: daily-digest
description: Turn a meeting into team knowledge — digest a transcript (from the runner's own Zoom connector, a transcript file, or pasted text) into a structured summary with candidate decisions and per-person tasks, then, after human triage, open draft ADR PRs against the team handbook repo, and, where the handbook's weekly lane is on (the Hub's by default), add the meeting's confirmed finished work to the week's weekly-update draft PR. Use after any meeting ("digest today's daily", "run the digest on this transcript", "what did we decide in the sprint planning"), or whenever the user wants decisions from a call captured in the decision log. Per-user by design — only ever uses the runner's own connectors and access.
---

# daily-digest

One loop: **transcript in → digest for humans → confirmed decisions out as draft PRs.**
The human is always in the loop: nothing merges, posts, or becomes team-visible without
explicit confirmation. If in doubt at any step, ask — never assume.
A session the noon schedule opened ("Run it every day at noon", below) runs every step as usual, triage included.

## Step 0 — locate the source-of-truth repo

Find the team handbook repo: a local checkout containing `where-truth-lives.md` and `decisions/`.
Look in the order the session hook uses: the folder in `SCRIPTA_HANDBOOK_PATH` if it is set,
otherwise `handbook_path` in `~/.config/scripta/config.json` if it is set, otherwise
`~/PROJECTS/hub-scripta-handbook`, then `~/PROJECTS/scripta`.
A set `SCRIPTA_HANDBOOK_PATH` or `handbook_path` is used alone: when that folder is not a handbook, ask, and never fall back to the `~/PROJECTS` folders.
The hook already did this at session start: when its note says "A team handbook exists at
`<path>`", use that path. If none of them is a handbook, ask the user for the path. Do not proceed without it —
the ADR format and naming come from its `decisions/` directory.

## Step 0.5 — read LEARNINGS.md

Read `LEARNINGS.md` next to this file before anything else. It holds calibration lessons
from past runs (what survives triage, reviewer preferences). Its own header states its
rules: evidence-quoted entries only, hard cap, prune on every write.

## Step 0.6 — the handbook's Linear and weekly lane

The task lane (Step 5) and the status lane (Step 5b) use one Linear workspace, team and
label. They belong to the handbook, not to this plugin, so read them from `scripta.json`
at the handbook root:

```json
{ "linear": { "workspace": "<workspace>", "team": "<team name>", "label": "<label>" } }
```

- **The file names all three.** Use them.
- **No `scripta.json`, or no `linear` in it.** Read the handbook's origin with
  `git -C <handbook> remote get-url origin`. When it is the Hub's handbook
  (`team-blue-Hub/hub-scripta-handbook`, over https or ssh, with or without `.git`), use the
  Hub's values: workspace `tbhub`, team `TB Hub`, label `from-digest`.
- **Anything else** (another handbook with no `linear`, or a `linear` that misses a field):
  the Linear lanes are off for this run. Say so once, in one line, and name the missing
  field when there is one. Never read or write Linear in this run. The digest and the ADR
  PRs run as usual, and the weekly lane follows its own setting below.

### The weekly lane

The weekly lane (Step 5c) feeds a weekly update, so it runs only for a handbook that has one.
Read it from the same `scripta.json`:

```json
{ "weekly": { "enabled": true } }
```

- **`weekly.enabled` is `true` or `false`.** Run Step 5c, or skip it.
- **No `scripta.json`, or no `weekly` in it.** On the Hub's handbook (the same origin check as
  above), Step 5c runs, as it always has. On any other handbook it is off.
- **Any other value.** The lane is off, and the one line below names the value.

When the lane is off, say so once, in one line. Never read or write a week branch, week file
or week PR in this run. The digest and the ADR PRs run as usual, and the task and status
lanes follow the Linear setting above.

## Step 0.7 — check today's digest branch BEFORE acquiring anything

Step 4 checks for the day's shared PR at the write step, and that check stays there: it guards
the race window while you work. But it is the wrong place to catch a squad that digested the
same meeting an hour ago, because by then the human has already read a digest and triaged it.
So check at the start as well, in the handbook checkout:

```
git ls-remote --heads origin 'digest/<today>*'
```

`<today>` is the run's calendar day, and the trailing `*` catches a suffixed sibling
(`digest/<today>-sq2`), which counts —
same branch rules as Step 4. If a branch exists, `git fetch` it and read the `## Source` blocks
of the ADRs committed on it, which carry each digested meeting's title and date. Then:

- **A meeting you were about to digest is already there** (title + date match under Step 4's
  distinctive-vs-generic rule) → say so before Step 1 and let the runner choose: skip that
  meeting, or digest it anyway to extend the existing PR with what the first pass missed.
  Never re-digest one silently, and never skip one silently either.
- **The branch exists, your meeting is not on it** → tell the runner this run will piggyback
  onto today's PR, then digest as normal.
- **No branch** → proceed; you are likely opening today's PR.

One command, run before the expensive part. Skipping it spends the runner's triage on
candidates that were decided and committed before they sat down.

## Step 1 — acquire the transcript (pluggable; never assume Zoom)

In order of precedence:

1. **File path given** → read it. Accept `.vtt`, `.txt`, or the `start  Speaker: text` line format.
2. **Pasted text** → use as-is.
3. **Meeting described in words** ("today's daily", "Friday's planning") → use the RUNNER'S OWN
   Zoom connector: `search_meetings` (resolve the right instance by date/topic), then
   `get_meeting_assets` with the meeting UUID. WHERE the transcript lives in the response
   depends on the connector version — check in this order:
   - **New shape**: `meeting_transcript.transcript_items` — each item:
     `start`, `end`, `text`; the speaker is embedded in `text` as a `"Name: utterance"`
     prefix (`display_name` and `zm_user_id` are null) — parse it off the front. The
     prefix is only the leading name before the FIRST `": "` at line start; a colon later
     in the utterance is not a prefix, and a leading word that matches no attendee
     ("Note:", "Well:") is content, not a speaker. A line with no speaker prefix has an
     unknown speaker — its content still counts for topics and decisions, but never
     attribute it to a person. Under this shape `recording` carries only
     `play_url`/`duration`/`processing`: a missing `recording.transcripts` array is
     NORMAL here, not the no-access stub.
   - **Old shape** (older connector versions): `recording.transcripts[].timeline`
     (each item: `ts`, `display_name`, `text`).
   - **Neither path present**: check `recording.processing` first — if true, the recording
     is still being produced: wait (the processing rule below), don't call it unknown.
     Otherwise the "No permission" triage below applies — the no-access stub is
     `has_permission: false` with BOTH transcript paths absent. Neither path present, not
     processing, but `has_permission: true` is an unknown shape: say so, don't guess.
   If the result is large it lands in a file — process it with jq/python, don't read it whole.
4. **Nothing provided** → list the user's recent meetings (their connector) and ask which one.

Access rules: only meetings the runner attended. If the transcript is not accessible, say so
and stop — never ask for someone else's credentials, never suggest a workaround.

Zoom "No permission" triage.

Endpoint discipline first:

- Use `get_meeting_assets` only. `get_recording_resource` works for some users'
  connectors and permanently 403s for others — per-user, on every meeting, so
  its failure tells you nothing. `has_transcript_permission: false` from
  `search_meetings` is equally meaningless: it stays false even on meetings
  whose transcripts fetch fine.
- Differential test before any diagnosis: fetch assets of an already-digested
  past meeting. If that returns its transcript, the connection is healthy and
  the problem is access to THIS recording, not auth.

The access model (best-supported explanation): Zoom appears to switch on a user's API access
to a recording when that user first OPENS the recording's share link in the
browser. Until that first click, `get_meeting_assets` returns only a stub —
`has_permission: false`, no `transcripts` — and no amount of waiting changes it
(observed unchanged 1.5h→3h post-meeting, then full transcript SECONDS after
the runner clicked the link). So when a fresh meeting's assets have no
transcript: give the runner the `play_url` from the response — the no-access
stub still carries a populated `recording.play_url` (verified on four stub
responses); if `recording` ever comes back null, take the link from
`search_meetings` or ask the host — say in plain words "open this link once,
then I can read the transcript", and retry as soon as they confirm. Never diagnose a connection failure, never suggest
reconnecting the connector. A reconnect only looks like a fix because the runner
opened the recording meanwhile.

The one case where waiting IS right: `recording.processing: true` (or error
code 3301) means the recording itself is still being produced — that clears
within the hour, and the click rule applies after it.

### Dual-channel cleanup (Zoom quirk, mandatory before digesting)

Zoom sometimes runs two speech models in parallel (e.g. English + Italian) and writes BOTH
into the transcript: each utterance appears twice at the same timestamp — one clean, one
phonetic garbage ("Sold Younders Standard, Drys Canyde Porden Cubers…"). The dedupe key is
shape-specific: new shape → group by `(start, speaker parsed from the "Name: " prefix)`;
old shape → group by `(ts, display_name)`. When a pair exists, keep the line with the LOWER
share of mid-sentence Capitalized words:

```python
def garble_score(text):
    body = text.split(": ", 1)[-1]
    words = body.split()
    if not words: return 0
    caps = sum(1 for i, w in enumerate(words)
               if i > 0 and re.match(r'^[A-Z][a-z]+$', w)
               and words[i-1][-1:] not in '.!?')
    return caps / len(words)
```

Orphan garbled lines (no clean twin) can sometimes be deciphered phonetically from context —
mark any such reconstruction explicitly as `[reconstructed — verify against recording at HH:MM:SS]`.

## Step 2 — digest (source-agnostic; this layer never mentions Zoom)

Produce a markdown digest with exactly these sections:

1. **Meeting** — title, date, duration, attendees.
2. **Topics** — one short paragraph per major topic, in meeting order, with timestamps.
3. **Candidate decisions** — the heart. For each: a one-line decision statement, who made or
   confirmed it, timestamp, and a short VERBATIM quote as evidence. Add a confidence tag:
   `firm` (explicitly agreed), `likely` (stated, not objected), `weak` (implied).
   A decision = a choice that changes what the team does or believes. Status updates,
   opinions, and open questions are NOT decisions — list those under Open questions instead.
   Informal verbal agreements on direction ("ok let's do it that way", "va bene, facciamo così")
   DO count — tag them `weak`. When quoting from a garbled transcript section, prefer the
   cleanest adjacent line that carries the same meaning over a heavily garbled one.
4. **Tasks** — per person: what, any deadline mentioned, timestamp.
5. **Open questions** — raised but unresolved.

Calibration: a typical 2-hour demo+planning yields roughly 8–12 candidate decisions.
Zero found in a long meeting means you missed some; twenty means you're counting
status updates. When unsure, tag `weak` rather than dropping or promoting.

Known triage-mortality classes: deploy/timing calls ("ship tomorrow morning", "campaign runs until
Sunday"), one person's stated intent ("I want to use this for every test"), and pure
tasks — even firm ones — rarely or never survive triage. List them under Tasks or Open
questions instead of Candidate decisions, or tag them `weak` and say you expect them
to die.

**Check each candidate against what is already recorded, before triage.** Find the
candidate's owning page through `where-truth-lives.md`, then grep that page and
`decisions/` for the rule it states: the atom, not the words. If a page or an ADR already
states the same choice with the same scope, and the meeting changes nothing about it
(value, scope, owner or reason), tag the candidate `recorded` with the path that holds it,
and recommend killing it as `duplicate` in Step 3. A meeting that repeats a rule shows the
rule is known; it is not a new decision. A candidate that narrows, extends or reverses a
recorded rule is new: keep it, and the reconcile pass links or supersedes the old one.

## Step 3 — human triage (MANDATORY, never skip)

Show the digest. Then ask the user to triage the candidate decisions: which are real and
worth the decision log? Only confirmed ones proceed.
If the user is not the decision owner, suggest they check with whoever made the call.
For each killed candidate, ask for a one-word reason (task / ephemeral / duplicate / wrong /
not-agreed) — that's the raw material for Step 6, costs the user nothing extra.

**How to ask:** when the harness has a structured question tool (Claude Code:
`AskUserQuestion`), use it instead of a wall of text — multi-select, candidates in groups
of up to 4 per question, one line per candidate (decision + who + confidence). Mark your
recommendation "(Recommended)" and put it first; state in the surrounding text which ones
you'd kill and why, so accepting the recommendation is one click. Kill reasons come free:
an unselected candidate inherits the reason you stated. On harnesses without such a tool,
fall back to a numbered list and let the user reply with numbers. Same pattern for the
task-lane triage table (Step 5): one multi-select per batch, UPDATE/ADD/SKIP as the text.

If the Linear lanes are on (Step 0.6) and the runner has a Linear connector, also offer the
task lane (Step 5): "want the tasks as Linear drafts too?" Never run it unasked.

The status lane (Step 5b) is not offered — it RUNS here, whenever the Linear lanes are on
(Step 0.6) and the Linear connector is reachable. Test that by reading one Linear issue in
the Step 0.6 team; treat an auth error, a missing connector, or a forbidden team as "not
reachable" and skip the lane silently. It asks nothing at this point: its human gate is the triage table in Step 5b,
where the runner reviews work already drafted rather than deciding whether to start it.
Say in the run which window it read (`status.md`'s snapshot date to today), and say so
again in the day-PR body when that window is wider than the gap between digests — a wide
window means a large diff, and the reviewer should read it as expected rather than as a
fault.

The weekly lane (Step 5c) is not offered either. When Step 0.6 has it on, it runs on every
digest, after the day PR is written, and needs no connector, so it runs whether or not
Linear is reachable. It asks nothing here: its gate is its own triage question in Step 5c.

## Step 4 — draft ADR PRs (the first write step)

**Sync + day-PR check first** (one PR per day, shared by every squad — see below):

The model is **one digest PR per calendar day, not one per meeting.** All squads' dailies
land in the same day's PR: the first run of the day opens it, every later run that day
appends to it. The branch is keyed to the **run's** calendar day: `digest/<date>` where
`<date>` is today, the day you run the digest (e.g. `digest/2026-07-29`), NOT the meeting's
date. So a backfill (digesting Monday's daily on Wednesday) lands in Wednesday's shared PR,
and the meeting's own date is carried inside the ADR, not in the branch name. Same-day runs
find the same branch. What must never happen twice is the SAME meeting; different meetings on
the same day are expected to share the PR.

1. `git pull` main in the handbook checkout, so the reconcile grep below sees what's actually
   merged.
2. Look for today's digest branch/PR:
   `git ls-remote --heads origin 'digest/*'` plus `gh pr list --state open --search "digest"`.
   Step 0.7 already ran this once; run it again anyway, because a squad may have opened the
   day's PR while you were digesting.
   The branch name is deterministic (`digest/<date>`). A suffixed sibling for the same date
   (`digest/<date>-sq2`, `digest/<date>-all`) is the SAME day's PR. Treat any `digest/<date>`
   or `digest/<date>-*` match as today's shared branch, never open a parallel one. Then:
   - **A branch/PR exists for this date** → it's today's shared PR. `git fetch`, check out
     that branch, and `git pull` it FIRST, then dedupe against what's committed on it: grep
     the branch's `decisions/` ADRs for this meeting's identity. The `## Source` blocks record
     the meeting title + date (the fields the ADR spec carries; there is no UUID). Read from
     the committed ADRs, NOT the PR body: the branch is compare-and-swap protected on push,
     the PR body is not, so two racing runs editing the body would clobber each other's
     meeting list and re-digest a meeting. Since title + date is now the whole key, the
     criterion for confident-vs-ambiguous is the title itself: a **distinctive** title that
     matches exactly (a specific project, topic, or one-off) → confident match, the meeting
     was already digested; STOP, show the runner the existing PR, offer to review or extend it.
     A **generic** title two squads could independently reuse ("Daily", "Standup", "Sync",
     "<squad> daily") → ambiguous by definition, because those are exactly the titles that
     collide under one-PR-per-day; do NOT auto-STOP: show the runner the candidate and let
     them confirm, since a false "already digested" silently drops a squad's whole digest. No
     match → you're **piggybacking**: add this run's ADRs on top (Step 4.3) and push to the
     same branch so they appear in the existing PR. Do NOT open a second PR.
   - **No branch/PR for this date** → you open today's PR (Step 4.3): create the branch and
     open a fresh draft PR named for the day.
   Different-date digest branches are fine; leave them alone.
3. **Two runs at once.** This check and the write in Step 4.3 are minutes apart (reconcile,
   ADR authoring, deslop), so a second squad may start in that gap. Guard the window:
   - Re-run the branch/PR check right before you create or push. If a day-PR appeared while
     you were working, switch to piggybacking onto it; never open a second.
   - Run it once more right AFTER the create or push lands. Two runs can both pass the
     pre-create check inside the same minute and both create a PR; only a check after the
     write sees the sibling that resulted. Report what you find in the same breath as the
     link you hand back, rather than leaving the next run to trip over it.
   - A push to the shared branch can be rejected because someone pushed first. `git pull
     --rebase` onto the branch, then push again. NEVER `git push --force`, which would drop
     the other squad's ADRs. ADRs are per-decision date+slug files so they
     almost never collide; the one residual case is two runs on the same date independently
     deriving the same slug and writing the same path (an add/add conflict, but not impossible). Resolve it by renaming your file to
     a free id (a `-2` suffix) and fixing its references, never `--ours`/`--theirs` (which
     drops a whole decision). The shared index files (`index.md`, `decisions/README.md`) can
     conflict too, since both runs append rows: keep BOTH sides' added rows there, never
     `--ours`/`--theirs`.
   - If two open same-day PRs exist anyway, STOP and show the runner both, never silently
     pick one.

Then do the **reconcile pass** (this is what makes the repo a brain
instead of a filing cabinet). For each confirmed decision:

- Grep/read the existing `decisions/` and the snapshot pages (`strategy/`, `engineering/`,
  `onboarding/`, `org/`) for content this decision touches, contradicts, or supersedes.
- If it changes an earlier ADR: the new ADR states "Supersedes <id>" in its header block
  and links it, where `<id>` is the old ADR's filename without `.md` (a number like `0042`
  for the frozen ones, or a `YYYY-MM-DD-slug` id for newer ones). NEVER edit the old ADR
  (append-only contract in decisions/README.md).
- **Update the concept page, not only the ADR.** The ADR records the decision and its why;
  it is not where a reader should have to reconstruct the current truth from a chain of old,
  partial ADRs. So for each decision, find the page that owns its concept (a snapshot page in
  `engineering/`, `strategy/`, `onboarding/`, `org/`, or a `where-truth-lives.md` registry
  row) and update THAT page in the SAME PR to state what is true now, with the new ADR
  linked inline as the history. Do this whether or not the page was contradicted: a page that
  simply lacks the decision is as stale as one that disagrees with it. Tag the page's
  `owner:` as a reviewer alongside the deciders. Date the new claim inline ("as of
  YYYY-MM-DD") and leave `last-verified:` alone: that field means the whole page was
  re-checked end to end (the `writing` skill owns this rule), and bumping it on an additive
  edit hides real staleness on the rest of the page from curate's scan.
- If the owning registry row points OUTSIDE the handbook (Notion, another repo, per
  `where-truth-lives.md`), the row stays a pointer. Update the row itself only if the home
  moved, link the ADR from it, and name the external page's needed update in the PR body as
  a follow-up for that home's owner (same branch as the `document` skill). Never write the
  truth prose into the row itself.
- **If no page owns the concept, propose creating it through the runner, not silently.**
  Ask one structured question (same tool as Step 3): CREATE `<proposed path>` in this PR, or
  FLAG-ONLY in the PR body. Recommend CREATE only when all three hold: the concept is a
  durable team fact that will keep accruing decisions (not a one-off or a single project's
  internals); its truth is stable prose, not a fast-changing value (those get a
  `where-truth-lives.md` pointer row instead, never a page); and it has an obvious owner
  from `people/` (a page nobody owns rots). Otherwise recommend FLAG-ONLY: the PR body names
  the concept and the proposed page name, so the gap is visible rather than buried in the
  ADR stream. A created page follows `page-format.md`, starts minimal (the decision's
  current truth plus the ADR link, nothing speculative), gets its `where-truth-lives.md`
  registry row in the SAME PR (nothing has two homes, per `document`'s page-plus-row
  pattern; without the row the next run re-classifies the concept as unowned and proposes
  a second page), and tags its proposed owner as reviewer (the owner accepting the page
  IS the merge).
- **A decision the repo already states gets no ADR.** Human confirmation at triage says
  "this was decided", not "this is new", so run this check on confirmed candidates too.
  If the owning page or an earlier ADR already states the same choice with the same scope,
  and the meeting changes nothing about it (value, scope, owner or reason), write no ADR
  and leave the page alone. Name it in the PR body as `duplicate: <path>`. A second record
  of one rule gives the next correction two places to miss.
- If genuinely nothing existing is affected, say so in the PR body ("reconcile pass: no
  conflicts") — the reviewer should know the check happened, not assume it.

**Write gate, first pass — before you name anything.** Load the `writing` skill here, not
at substep 5, and run its four questions over the decision statement you are about to turn
into a title and a slug. The gate's instruction is to ask them before the draft exists,
"not on a finished diff, where sunk cost argues back"; substep 1 below fixes the filename,
substep 2 the title, and substep 3 pushes both. Its relative-time rule is why this pass
exists: a relative date in a title ("starts next sprint") is wrong once it merges.

Then, for each confirmed decision, in the handbook checkout:

1. Id = the decision's date plus a short kebab-case slug: file `YYYY-MM-DD-slug.md`, the id
   being the filename without `.md` (no running number, so parallel
   digests never renumber, and collide only on the rare same-date same-slug coincidence). The
   date is the `date:` below (the day the decision was made). If a same-date same-slug file
   already exists, add a `-2` suffix. Older numbered ADRs
   keep their old numeric ids and are never renamed; do not continue the number sequence.
2. Follow the existing ADR format exactly — frontmatter:
   ```yaml
   ---
   type: decision
   title: <short imperative title>
   tags: [decision]
   status: accepted
   date: <date the decision was made, not today>
   deciders: "<who, with roles — from the transcript>"
   ---
   ```
   Body: `# <title>` (drop the leading id from the H1 for date-slug ADRs; the old numeric
   ones keep their `# NNNN — title` heading), then `## Context`, `## Decision`,
   `## Consequences`, `## Source`.
   In Source: meeting name, date, timestamp, and the verbatim quote. Match the register of
   existing ADRs (read one first).
   **Verify every person name before it lands.** Names in `deciders`, the `## Source` quote,
   and the body come from the transcript, and Zoom mistranscribes them. Reconcile each spoken name against the team roster in `people/` (the
   expertise map), matching on first name or handle, case-insensitively; if
   one spoken first name matches two roster people, treat that ambiguity as a flag too. A
   name with no match goes in the PR body as "name unverified — <as heard>" rather than
   guessed at, which also stops step 3's "tag the deciders as reviewers" from tagging a
   nonexistent user. Two things keep the flag honest: `people/` is the **team** roster
   only (per its README), so a correctly-spelled name from outside the team (an external or
   detached-pod person) will also flag — read "unverified" as "not
   on the team roster", a cue to check the spelling by hand, not proof of a mistranscription;
   and if `people/` isn't in the checkout, skip the check and say so in the PR body (as
   `hardening-interview` Step 0 does).
3. One branch per DAY (`digest/<date>`), shared by every squad's digest that day.
   - **Opening today's PR** (no branch existed in the sync check): create the branch, put
     this run's ADRs on it, open one **draft** PR via `gh pr create --draft`, titled for the
     day (e.g. `digest 2026-07-29`).
   - **Piggybacking** (the branch already existed): you are already on it from the sync
     check — add this run's ADRs and push; no new PR.
   Either way the PR body has a **Meetings** section listing each digested meeting (title +
   date, plus the Zoom UUID when you have it — the ADR spec carries no UUID, but Step 0 has
   it from `get_meeting_assets`, so the body can), and a decisions list with each decision's
   quote; tag the deciders as
   reviewers. When piggybacking, APPEND your meeting and its decisions to those sections
   rather than replacing them. The PR body is for humans; it is NOT the dedupe source (that
   is the committed ADR `## Source` blocks, per the sync check), because a body edit has no
   compare-and-swap and racing runs would clobber each other's list.
   Update EVERY index that lists ADRs in the same PR — at minimum `index.md` AND
   `decisions/README.md` (grep for the previous ADR's filename to find them all).
4. The `## Source` section must link VERIFIABLE artifacts, not just name the transcript:
   the meeting recording URL when available, plus related existing artifacts — check
   `where-truth-lives.md` for the official home of anything the decision touches, and
   cross-link the relevant repo docs, ADRs, or registry rows. Read one recent ADR's Source
   section first and match its citation density.
   Also WEAVE links inline through Context/Decision/Consequences where a concept is first
   mentioned — a link footer alone is a filing cabinet,
   not a brain. Same for the PR body: link every ADR file, every touched page, and the
   recording; a PR description with no links is a dead end for the reviewer.
   Link form differs by location: INSIDE repo files use relative paths
   (`0007-slug.md`, `../where-truth-lives.md`); in the PR BODY use full
   `https://github.com/<org>/<repo>/blob/<branch>/<path>` URLs — relative paths in a PR
   description get parsed as branch names and land the reader on an empty Compare page.
   New files → link via the PR branch; existing files → main.
5. **Write gate, second pass.** Re-read the full diff as a hostile reviewer and run the
   four questions again over **the ADR title, the filename slug, the ADR bodies and the
   PR description**. Naming the title and the slug is the point: the first pass ran on a
   sentence, this one runs on what that sentence became. For each question, name what you
   removed or say "clean"; a run that cannot say what the gate removed did not run the
   gate. It owns the four questions, the `last-verified` rule, the
   relative-time→absolute-dates rule, and the deslop handoff that AGENTS.md rule 6 makes
   mandatory. Verbatim transcript quotes in `## Source` are exempt — a recorded meeting is
   primary evidence, and the `writing` skill states that exemption once, for the callers
   that have it and the one that doesn't.
6. NEVER merge, never push to main, never mark ready-for-review. The human does that.

## Step 5 — task lane: propose board updates (second output lane, same contract)

Only on explicit opt-in (Step 3). The digest's per-person Tasks become **proposed
updates to the team's Linear board** through the same loop: match → human triages →
write. **Matching against existing issues matters more than adding new ones** — most
meeting statements are progress on known work, and blind creation makes duplicates.

**Where the board is:** the Linear workspace and team from Step 0.6; the "Sprint /
ticket status" row in `where-truth-lives.md` is the pointer.

1. **Load the board and match.** Read the team's issues in the active cycle plus
   Backlog — a bounded match set, not every open issue the board has ever grown.
   For each digest task, find the issue it corresponds to — by owner, keywords,
   and topic. Classify:
   - **UPDATE** — an issue exists and the meeting moved it: done, blocked, progressed,
     re-owned. Carry the verbatim quote + timestamp as evidence — pull it from the
     transcript (still in this session), never from a paraphrased digest line.
   - **ADD** — real new work with an owner, said in the meeting but absent from the
     board.
   - **SKIP** — vague intentions, personal/1:1 content, or already on the board
     unchanged.
2. **Human triage (mandatory, same as decisions).** One table: task → UPDATE / ADD /
   SKIP, with the matched issue quoted for updates. Only approved rows proceed. One
   addition for ADDs: when the transcript never says what done means, ask the runner
   for one sentence here — triage is the only place the issue's **Done means** field
   can honestly come from.
3. **Write like a colleague, not a bot.** Every title, description and comment the
   lane writes gets the deslop pass before it lands (the same pass the `writing`
   skill hands off to — its closing section names where deslop lives and the
   fallback when it isn't installed): plain words, no jargon, no filler. The four
   questions do NOT run here — the `writing` skill scopes them to handbook pages —
   but verbatim transcript quotes stay exempt, same as in `## Source`: a recorded
   meeting is primary evidence.
4. **Write to the board.** Comments on matched issues for approved UPDATEs: first
   line `📥 digest — <meeting name>, <YYYY-MM-DD>`, then the verbatim quote +
   timestamp, plus the handbook link when the update's concept has an owning page.
   That first line is the rerun key (item 7), not decoration — never drop it. New
   issues only for approved ADDs — **in Backlog**, never the
   cycle (the PMs' daily sweep promotes), labeled with the Step 0.6 label. Status
   changes only when the transcript is explicit ("the testing PR is ready" →
   In Review); never close, cancel, or reassign without a per-item yes.
5. **Every ADD follows one issue shape.** Title: imperative, plain words.
   Description: two to four human sentences (what and why — no meeting narration),
   then a final section a future AI session can work from:

   ```
   ## Context for AI
   - **Source:** <meeting name>, <YYYY-MM-DD>
   - **Evidence:** "<verbatim quote>" — <speaker>, <timestamp>
   - **Intent:** <why this task exists, one or two sentences>
   - **Done means:** <as stated in the meeting, or as confirmed at triage>
   - **Links:** <owning handbook page or ADR; any PR or issue named in the meeting>
   ```

   All fields mandatory except Links. If the runner declined a Done means at triage,
   write "not defined at creation — clarify with <owner>" rather than inventing one;
   a guessed definition of done is worse than a named gap. For Links, grep the
   handbook's `decisions/`
   and snapshot pages (`engineering/`, `strategy/`, `onboarding/`, `org/`) for the
   task's concept — here, not only in Step 4's reconcile pass, because a tasks-only
   meeting (zero confirmed decisions) never triggers that pass. Links are absolute
   GitHub URLs; a repo-relative path breaks when rendered inside Linear. No owning
   page — no link, never a guessed one.
6. **Close the loop.** End by linking what was written (the comments / the issues)
   and tell the runner to give the PMs a heads-up — new Backlog issues surface in
   their daily sweep, but a heads-up beats a surprise.
7. **Reruns don't duplicate**: one proposal per meeting. The dedup key is the
   meeting name + date this run already stamps on everything it writes — the
   `Source:` field in each created issue's Context for AI, and the `📥 digest`
   first line on each comment. Before writing, a rerun searches issues with the
   Step 0.6 label and the matched issues' comments for that key; hits are updated in
   place (edit the comment, amend the issue), never duplicated. Same contract as
   Step 4's dedup, where the key is the `## Source` block's meeting title + date.

## Step 5b — status lane: consolidate shipped work, then refresh the snapshot (third output lane, same contract)

Runs whenever the Linear lanes are on (Step 0.6) and the connector is reachable (Step 3
fires it; no opt-in). Two pages share the work:
each project's **own page** holds the standing picture — one cohesive body of what the
product does — and the handbook's `status.md` holds only the **movement**: Now, Planned,
and the pointer to that standing picture. Shipped work is never a diary anywhere. The
lane rides the same day-PR as Step 4, so the human merge that signs off the digest signs
off both writes.

**Lanes are a shape, not a list.** This is the third output lane and the second that turns outside
state into handbook pages (Step 5c is the fourth). A new lane needs: one owning page, one bounded read, one triage table, and it
rides the PR whose merge signs off that page: the day PR for decisions and status, the
week's PR for the week's entry (Step 5c). Do not invent other write paths.

**When a lane may fire unasked.** A lane that writes only inside the handbook, behind its
triage table and a human merge of a handbook PR, fires without asking: the runner reviews a
drafted diff instead of authorising work sight-unseen. A lane that WRITES outside the
handbook, as the task lane does to the Linear board, asks first: its writes land where no
handbook merge reaches. That is why Step 5 offers and Steps 5b and 5c do not.

1. **Bounded read.** Linear issues in the Step 0.6 team completed since `status.md`'s own
   snapshot date (the `**Snapshot of <date>**` line — that date is the rerun key), plus
   anything the meeting itself declared shipped, newly started, or newly planned.
   Nothing else.
2. **Consolidate each shipped item into its project's own page — never append it.**
   This is Step 4's "update the concept page" rule with a different trigger: find the
   page the project's standing picture lives on (`status.md`'s **Standing picture**
   pointer names it), read the whole page, and rewrite the sentences the shipped thing
   touches so the feature list stays one cohesive body — a minor or incremental change
   merges into an existing sentence, a contradiction gets resolved in place, and only a
   genuinely new capability earns a new sentence. When no page owns the project (the
   pointer says so), propose creating one through the runner, never silently — with this
   lane's own criterion, not Step 4's: recommend CREATE when the project has an obvious
   page owner and durable prose to hold. Step 4's concept-page test excludes "a single
   project's internals", which is exactly what a project page is, so deferring to it
   would flag forever and leave the Standing-picture pointer with nowhere to point.
3. **Refresh `status.md` as a diff.** `Now` gains what visibly started and drops what
   completed; `Planned` follows the board and the meeting; the **Standing picture**
   pointer stays — unless item 2 created the project's page this run, in which case the
   pointer now names that page (left stale, the next run re-reads "no page owns the
   project" and proposes a second one — the same failure mode Step 4 names for its
   missing row); bump the snapshot date. Keep the fixed shape exactly (one `##` per
   project, `**Now:**` / `**Planned:**` / `**Standing picture:**` bullets) — the shape
   is what makes the next refresh mechanical. Nothing shipped is listed on this page.
4. **Human triage, same as everything.** One table showing both writes — the owning-page
   consolidation diffs and the snapshot diff. A ticket marked Done that the runner knows
   is not shipped gets dropped here; the pages state what someone was willing to sign,
   not raw board state.
5. **Write gate applies in full** (both are handbook pages): the four questions — Q4,
   one atom, IS the consolidation move — dates not relative time, deslop last. One line
   per fact; the Linear link carries the rest. Never enumerate what the board already
   lists.

## Step 5c: weekly lane, the day's finished work into the week's update (fourth output lane, same contract)

Runs on every digest where Step 0.6 has the weekly lane on (by default on the Hub's handbook),
after Step 4 and after Steps 5 and 5b when they ran. When it is off, skip this step. No
opt-in, no connector. It writes one block for this meeting into the week's `weekly-update`
draft, so the person who was in the meeting confirms what shipped on the day it shipped. Friday's
`weekly-update` run builds the entry from those blocks instead of rebuilding the week from
summaries, and the PMs confirm and merge the week's PR: that merge is this lane's gate.

The blocks live on the week's branch, in a section Friday's run deletes, so nothing
diary-shaped ever merges (Step 5b: shipped work is never a diary). If someone merges the
collecting PR early, the section sits on `main` until Friday's run deletes it (item 4).

1. **Which week.** The meeting's week, never the run's: Monday's daily digested on
   Wednesday belongs to Monday's week, and a weekend meeting to the week that just ended.
   The file and branch follow `weekly-update`'s "Where the draft goes" rule, from that
   week's Friday: `updates/<Friday>-week-<NN>.md` on the week branch
   `weekly-update/<YYYY>-week-<NN>`, including its rule for the year of a January entry.
2. **Draft the block**, from this session's transcript and the ADRs Step 4 actually wrote
   (a candidate dropped at reconcile as already recorded never reaches the week).
   - Shipped work: only what the meeting itself reported as finished, filtered by
     `weekly-update`'s "What goes in, what stays out" and its Rule 1 test. Never Linear
     issues: the week reports what the dailies said.
   - Decisions: the day's ADRs whose effect a reader outside the team would see, one line
     each.
   - Label shipped lines `Delivery`, `Brand activation` or `Legal and privacy`, and every
     line from an ADR `Decided`, never `Delivery`. Labels are hints; Friday sorts the entry.
   - A shipped line ends with its evidence: speaker, timestamp and a verbatim quote of 20
     words or fewer. A decided line ends with its ADR id, as plain text, never a link: the
     day branch a link would point at is deleted when it merges.
   - The privacy guardrail applies: a 1:1 or personal content never becomes a line.
   - Run deslop on the lines. The `writing` gate's four questions run on Friday's entry,
     the text that merges. Verbatim quotes stay exempt, as everywhere else.

   The heading is the block's identity, the same meeting title and date Step 4 reads from
   `## Source` blocks:

   ```
   ### <meeting date> · <meeting title>
   - Delivery: <item> (<speaker>, <hh:mm:ss>: "<short quote>")
   - Decided: <decision item> (ADR <id>)
   ```

   A meeting with nothing finished still gets a block, with the one line
   `Nothing finished was reported.`, so Friday can tell "met, nothing shipped" from "not
   digested".
3. **Triage, one question.** Show the block and ask which lines go to week <NN>'s update,
   in Step 3's format. Recommend the lines that clearly pass the filter. Leave a borderline
   line unrecommended, with a one-word reason: shown or demoed but not live, internal
   tooling with no reader-visible surface, a brand name you could not verify. Name the
   destination: the week's PR, plus, for a late block, one comment there and a return to
   draft (item 4). Dropped lines are gone; if every line is dropped, the block says
   nothing finished was reported.
4. **Find the week's PR**: `git ls-remote --heads origin '<week branch>'` and
   `gh pr list --head '<week branch>' --state all`. A merged PR's branch may be deleted,
   so the PR list decides. When it lists more than one PR, an open one decides; a merged or
   closed one decides only when no PR is open, and among those the newest. Before you
judge a merged one, run `git fetch origin main` and read the week's file with
`git show origin/main:<file>`: the PR may have merged minutes ago, after this run last
pulled `main`. Then:
   - **No branch, no PR.** This is the week's first digest. Branch from `origin/main`,
     create the file with the previous entry's frontmatter and heading shape
     (`weekly-update` Rule 2) for this week's date and number, and under the H1 put the
     section `## From the dailies (the Friday run deletes this section)` holding your
     block. Commit and push the branch first (item 5), then open the PR with
     `gh pr create --draft --head '<week branch>'`, titled
     `weekly update: week <NN> (collecting until Friday, do not merge)`. The body's first
     line, in bold: do not merge this PR, Friday's `weekly-update` run writes the entry and
     the PMs merge that. Then that the section collects the week's blocks for the Friday run. If GitHub
     answers that a PR for that branch already exists, another run opened it a moment
     ago: use that one.
   - **Branch exists, no PR.** An earlier run pushed the branch but could not open the PR.
     Add your block on that branch as in the open cases below, push, then open the draft PR as
     above.
   - **Open, entry not drafted** (no entry lines above the section). Add your block to the
     section, in meeting-date order. A block with the same date and a title that matches
     ignoring case, spacing and punctuation means a rerun of the meeting (two same-date
     titles that are merely close: ask the runner): merge into it, keeping every line
     already there unless the runner dropped it at triage, and add the new ones. If the
     block held only `Nothing finished was reported.`, replace that sentence with the new
     lines. Never two blocks for one meeting.
   - **Open, entry drafted** (entry lines above the section, or the section is gone). Add
     your block the same way, re-creating the section under the entry if Friday's run
     deleted it. Tell the runner the draft needs a `weekly-update` rerun, and leave one
     comment on the week's PR naming the meeting that added a block.
   - **Either open case, PR not a draft.** Someone, or a bot requesting reviewers, marked
     it ready. Return it to draft (`gh pr ready --undo`) before your push, so it is
     never mergeable with the section in the file, and tell the runner.
   - **Merged, and the week's file on `origin/main` still has the section, with no entry
     lines above it.** Someone merged the collecting PR before Friday's run, so the week is
     not published: the blocks are on `main` and there is no entry. Keep collecting. The
     handbook deletes a branch when its PR merges, so branch the week branch from
     `origin/main` with `git worktree add -B '<week branch>' <path> origin/main`: `-B`
     resets a local week branch an earlier run left on this machine, whose history is the
     one the squash replaced. Add your block to the section already in that file as in the open
     cases, push, and open a new draft PR as in "No branch, no PR". If the old branch is
     still there, do not re-branch: first `git merge origin/main` into it (a squash merge
     left its commits outside `main`, and without this merge the new PR conflicts on the
     week's file). If the merge conflicts on the week's file, a run pushed a block after
     the merge: keep both sides' blocks as in item 5, never `--ours` or `--theirs`. Then
     add your block as in "Branch exists, no PR". Never `--force`. Its body also names the merged PR and says this one carries on
     collecting for the Friday run. Tell the runner, and end the day PR body's weekly-lane
     line with `(the first week PR was merged before Friday; this one carries on)`.
   - **Merged, and the week's file is missing from `origin/main`** even after the fetch.
     Write nothing and ask the runner: a merged week PR always leaves its file on `main`.
   - **Merged, and the file on `origin/main` has no section, or has entry lines above
     it.** The week is published (a section under an entry is a late digest's, merged with
     the entry): write nothing to it. List the confirmed lines in the day PR body under
     `Not added to week <NN> (already published)`, or in your report to the runner when
     this run opened no day PR, so a PM can file a revision.
   - **Closed without merging.** Write nothing and ask the runner. Never two open PRs for
     one week.
5. **Write from a separate worktree** on the week branch (`git worktree add` in a temporary
   path), so the handbook checkout stays on the day branch: every write in item 4,
   creating the file included, happens there. If the branch is still checked out in a
   worktree an earlier run left behind (`git worktree list` shows it), free it first with
   `git worktree remove --force <path>`: `git worktree prune` alone does not. Commit only the week's file.
   Pushing follows Step 4's "Two runs at once": re-check the branch right before and right
   after the push, `git pull --rebase` on a rejection and never `--force`, and in a
   conflict inside the section keep both sides' blocks, as for the shared index files, then
   merge any two blocks that share a heading into one. When the conflict is the whole file
   (two first digests created it in the same minute), take the winner's file and add only
   your own block, as in "Branch exists, no PR". Two open PRs for one week: stop and
   show the runner both. Remove the worktree when done.
6. **Report.** Give the runner the block as written and the week PR link, and add one line
   to the day PR body, when this run opened or extended one: `Weekly lane: block added to
   week <NN>` with that link. Re-read the body right before you edit it, since another
   squad's run may have just changed it. The week PR stays a draft until the PMs finish on Friday:
   draft pushes do not start the handbook's review workflow, so a push a day costs no
   review run.

## Step 6 — retrospective (after the PR merges or closes, not before)

Close the learning loop in `LEARNINGS.md`, under that file's own rules (evidence-quoted
entries only, 12-entry cap, prune on every write):

1. Compare proposed → survived → merged: which candidates died at triage (and the one-word
   reasons), what the reviewer commented, what got edited before merge.
2. A delta that matches an existing entry: update that entry's "Seen" count — never add a
   duplicate. A new delta: add an entry with its verbatim evidence. No evidence, no entry.
3. A lesson at 2–3 runs gets promoted into the relevant step of this file via a normal PR,
   and its entry deleted.
4. If nothing new was learned, write nothing. An empty retrospective is a valid outcome.

## Run it every day at noon (optional, Mac or Windows)

`scripts/digest_schedule.py` (next to this file) opens this skill in a terminal window at 12:00 on weekdays, for the meetings one person attends, unless all of them are already in today's digest. It suits someone whose own Zoom account can read those calls. The window runs every step above as usual, and triage stays with the person. Where the weekly lane is off (Step 0.6), a meeting digested with no ADR leaves no mark the check can find, so the window still opens for it.

- **Turn it on:** `python3 "$(dirname <this SKILL.md>)/scripts/digest_schedule.py" install --meeting "<Zoom title of the daily>=tue-fri" --meeting "<Zoom title of planning>=mon"`. Each meeting is its Zoom title, then `=` and the weekdays it runs: `mon`, `tue-fri`, `mon,wed` or `all`. Ask the person which meetings they attend and on which weekdays before you run it. On a weekday with none of the saved meetings, nothing opens. With no meetings saved, the window opens every weekday, and running install again with none given keeps the saved list.
- **See it work now:** `... digest_schedule.py try` opens the window without the time checks.
- **Check it:** `... digest_schedule.py status` shows whether it is loaded, the saved meetings, the handbook, the scripta version and tools the job finds, and the last run.
- **Backup for a call:** each daily has a main person and a backup, and the backup makes the summary only when the main person was not in the call. The backup installs it on their own laptop: `... install --meeting "Team - Daily=tue-fri;backup-for=Alex Doe;zoom=12345678901"` (Zoom name of the main person, numeric Zoom meeting number).
  Their laptop reads from Zoom who joined the call and opens the window only when the main person did not join, or by 17:00 if it cannot tell. It retries every 30 minutes from 12:30. `... digest_schedule.py check` tests that their Zoom can see who joined the call, and opens nothing.
- **Turn it off:** `... digest_schedule.py uninstall`. An open window stays open.

State lives in `~/.scripta/digest-schedule/`, and every run writes to `schedule.log` there. If no window ever opens, check `status`, then that log. On a Mac, endpoint security can remove `~/Library/LaunchAgents/blue.team.scripta.digest.plist`. On Windows, check that Task Scheduler still has the task `blue.team.scripta.digest`.

On Windows, run the same commands in the Bash tool (Git Bash), with `py -3` or `python` in place of `python3`: there `python3` is often the Microsoft Store stub, which runs nothing. Use the Windows Python, not an MSYS one; install says so if it gets the wrong one. Task Scheduler holds one task, `blue.team.scripta.digest`, set to run on battery and to catch up a noon the laptop slept through, and the window is PowerShell. `install` needs a normal, not locked-down, terminal.

## Guardrails

- Human merges everything; the skill only ever produces drafts.
- The task lane (Step 5) never runs without the user's explicit yes for THAT run, and
  never writes to a team/workspace the user didn't confirm. The status lane (Step 5b) only
  reads Linear and writes handbook pages behind the triage table, so it fires unasked.
  The weekly lane (Step 5c), when Step 0.6 has it on, writes only to the week's draft PR in
  the handbook, behind its triage question, so it fires unasked too; the privacy rule below
  applies to its blocks.
- Quote, don't paraphrase, in `## Source` — paraphrase drifts, quotes don't.
- Privacy: 1:1s and personal/HR content are digestible for the runner's own notes but NEVER
  become PR content unless the runner explicitly says so.
- If the transcript quality is too poor to be confident, say so instead of guessing.

## Eval (keep passing before shipping changes)

No test transcript ships with the plugin; use one of your own. Test on a real daily transcript you have already digested by hand: score the digest against
your own list of decisions (with verbatim quotes). Expected: at least two thirds of them found, zero
hallucinated decisions. Run the eval after every prompt change to this file.

### Status lane: trigger check (by hand)

The recall eval above only scores decision-finding recall; it says nothing about whether a
lane fires. Since Step 5b runs unasked, its trigger needs its own check. Run these four by
hand after any change to Step 3 or Step 5b:

1. **Connector reachable.** The lane runs, nothing asks permission for it, and the run
   states the window it read.
2. **Connector unreachable** (no connector, auth error, or a forbidden team). The lane is
   skipped silently. Nothing errors and nothing asks.
3. **Connector reachable, task lane declined.** The task lane does not run; the status lane
   still does. This is the check that the two lanes' triggers stayed independent.
4. **Window wider than the gap between digests.** The run says so, and says so again in the
   day-PR body.

**This is a scenario read and run by a person, not an automated harness.** There is none in
this repo for prompt-level behaviour — `skills/curate/` has a build-time fixture eval, but
that check is a deterministic Python script with an exit code, and a lane trigger is prose
an agent interprets. The two are not interchangeable, so this stays manual until something
can actually execute a digest and assert on its output.

### Weekly lane, by hand

Step 5c has no automated harness either. Run these after any change to Step 5c or to
`weekly-update`'s naming rule, against a sandbox handbook whose `origin` is a local bare
repo and a stand-in `gh` that holds each PR's state (open, draft or ready, merged,
closed), never the team's. That origin is not the Hub's, so for items 1 to 11 the
sandbox's `scripta.json` holds `{ "weekly": { "enabled": true } }`; item 12 removes it.

1. **First digest of a week.** The week's file, branch and draft PR appear, holding one
   block, and the PR is titled `weekly update: week <NN> (collecting until Friday, do not
   merge)`.
2. **Another meeting, same week.** Its block joins the same section; no second PR.
3. **The same meeting again.** Still one block: the first run's lines kept, new ones added.
4. **Nothing finished.** The block says so, and it is still written.
5. **Week already published** (the week PR merged, and `main`'s file has the entry and no
   section). Nothing is pushed to the week branch; the lines are in the
   day PR body.
6. **Entry already drafted.** The block is added, one comment is left, and a ready PR goes
   back to draft.
7. **PR marked ready mid-week, entry not drafted.** The block is added and the PR goes back
   to draft.
8. **A 1:1.** No line carries personal content.
9. **Week PR closed without merging.** Nothing is written and the runner is asked.
10. **Week PR merged before Friday, section still on `main`.** A new draft PR opens on the
    same week branch, from `main`; the block joins the section already in the file, the PR
    body names the merged PR, and nothing is force-pushed. Variants: the local `main` is
    older than the merge (the fetch in item 4 still finds the section), and the old branch
    still exists (`origin/main` is merged into it first, and the new PR has no conflict),
    and the runner who opened the first PR still has the week branch locally (`-B` resets
    it to `origin/main`; nothing from the old local history is pushed).
11. **An open week PR next to an earlier merged one.** The block goes to the open one; no
    third PR.
12. **Lane off.** A sandbox handbook whose `origin` is not the Hub's, with no `weekly` in
    `scripta.json`: no week branch, file or PR, and one line says the lane is off. With
    `{ "weekly": { "enabled": true } }` added back, the lane runs as in item 1.

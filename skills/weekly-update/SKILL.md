---
name: weekly-update
description: Draft the weekly update for the Hub, for any PM to run, and hand it back as a draft the PMs confirm before it is published. Reads the blocks each daily digest added to the week's draft PR, the dailies only where a block is missing, plus the fixed number sources; splits delivery from brand activation from legal, and ends with four or five points to agree on. Use on "run the weekly update", "draft this week's update", "/weekly-update".
---

Built for the Hub's weekly update (its notification numbers, brand and legal sections, Friday cadence). Another team can skip this skill; nothing else in scripta needs it.

# Weekly update

## What this produces

One draft per week, for the person who briefs the leadership team.

The draft is written on Friday morning and confirmed the same afternoon. It is
not published by whoever ran it. A PM reads it, corrects it, and answers the
confirm block at the end. Only then does it go out.

One run covers the whole Hub. There is no per-squad run and no merge step.

## Where the draft goes

The draft is a file in the handbook repo, opened as a **draft pull request**.
That is the review step: the PMs correct it in the PR, and merging it publishes
it.

- Find the handbook repo the way `daily-digest` does: a local checkout
  containing `where-truth-lives.md` and `decisions/`. Look in the order the
  session hook uses: the folder in `SCRIPTA_HANDBOOK_PATH` if it is set,
  otherwise `handbook_path` in `~/.config/scripta/config.json` if it is set,
  otherwise `~/PROJECTS/hub-scripta-handbook`, then `~/PROJECTS/scripta`.
  A set `SCRIPTA_HANDBOOK_PATH` or `handbook_path` is used alone: when that folder is not a handbook, ask, and never fall back to the `~/PROJECTS` folders.
  The hook already did this at session start: when its note says "A team handbook exists at
  `<path>`", use that path. If none of them is a handbook, ask. Do not guess a path.
- Write to `updates/<YYYY-MM-DD>-week-<NN>.md`, where the date is the entry's
  own Friday and `<NN>` its ISO week, zero-padded. Same shape as the archived
  entries and as the repo's ADRs. One file per week.
- Branch `weekly-update/<YYYY>-week-<NN>`, titled `weekly update: week <NN>`.
  The year there is the Friday's own calendar year, not an ISO week-year, so a
  January entry can read as week 53 of the year it is dated in. Never merge it
  yourself, whoever you are. `daily-digest`'s weekly lane names the file and
  branch by this same rule.
- By Friday the PR usually exists: the week's first digest opened it as a draft,
  and every digest since added its block to the file (see "The collected
  blocks"). Push to that branch; commits from several digest runners on it are
  expected. Only when no digest ran all week, or in the merged-early case below, do you create the branch and open
  it with `gh pr create --draft`. Two drafts for one week is still the thing
  this replaces.
- The digests title that PR `weekly update: week <NN> (collecting until Friday,
  do not merge)`, and open its body with a bold line saying not to merge it, so
  nobody merges the collected blocks as if they were the entry. When you push the
  entry, set the title back to `weekly update: week <NN>` and remove that bold first
  line (`gh pr edit --title`, `gh pr edit --body`). If the branch has a merged PR and
  an open one (the first was merged before Friday and a digest opened another), push
  to the open one.
- If the week's only PR is merged, run `git fetch origin main` and read the week's
  file with `git show origin/main:<file>`. If that file still has the collecting
  section with no entry above it, the PR was merged before you ran and the week is
  not published. If the file is missing from `origin/main` even after the fetch,
  write nothing and ask the runner. The handbook deletes a branch when its PR merges, so
  branch from `origin/main` (`git checkout -B '<week branch>' origin/main`, so a
  leftover local week branch is reset; if the old branch is still on GitHub, work on it instead,
  after `git merge origin/main` into it so the PR does not conflict; on a conflict in
  the week's file, keep both sides' blocks), write the entry
  above the section and delete the section in the same commit, then open a draft PR
  titled `weekly update: week <NN>` whose body names the merged PR. With several merged
  PRs and none open, the newest decides.

The published entries stay in the same folder, so last week's is one directory
listing away. `updates/README.md` explains the folder and holds the index.

## The collected blocks

Each `daily-digest` run adds one block for its meeting to the week's file, under
`## From the dailies (the Friday run deletes this section)`. A block is headed
`### <meeting date> · <meeting title>`, and each line carries a label and its
evidence:

- `Delivery`, `Brand activation` or `Legal and privacy`: shipped work the meeting
  reported, with speaker, timestamp and a short quote, confirmed that day by the
  digest runner, who was in the meeting.
- `Decided`: an ADR from that day whose effect a reader outside the team would
  see, with its id. The ADR usually still sits on an open day PR, so look the id
  up on `main` and on the open `digest/*` branches before calling it missing. An
  id found on neither is a broken citation: name it in the confirm block, never
  drop it silently. An id found only on an open day PR is a decision still in
  review: if you keep the line, say so in the confirm block, so a PM can hold it
  until that PR merges.
- `Nothing finished was reported.`: the meeting ran and shipped nothing. That is
  coverage, not a gap.

The labels are hints; this run sorts the entry by the four-line rules below.
Fill Delivery from shipped lines first and use `Decided` lines only within the
item budget that is left. A `Decided` line you keep goes in the entry, on the
line its effect belongs to (usually Delivery). It is a decision, not a
delivery, so it is also named in the confirm block's "near the not shipped
line" point.

The section is working material, not the entry. Write the entry above it and
delete the section in the same commit, so the merged file is the entry alone;
the branch history keeps the lines for anyone tracing an item. The PR body says
how many blocks you used, from which meetings and days.

**A rerun**, usually after Friday's own dailies are digested. A late digest
re-creates the section under your entry, comments on the PR, and returns it to
draft if it was ready. On the rerun:

- Count as covered every block ever committed to the section on this branch:
  the file as it stood just before your draft commit, plus every block added
  since. Read transcripts only for cells still without a block.
- Add only the new blocks' lines to the entry. Keep the PMs' edits, and do not
  bring back an item a PM cut.
- Delete the section again in the same commit.

Digests keep pushing to this branch while you work. If your push is rejected,
`git pull --rebase`, fold in any block that arrived, and push again; never
`--force`, which would drop a squad's block.

## This is not the status page

`status.md` says what is moving now, per project, and the daily digest refreshes
it. This says what was finished in one week, for one reader, on one date.

They share a subject and never a tense. Do not write `status.md` from this run,
and do not read it as a source. It records intentions, and an intention is not a
delivery.

## The write gate

This lands prose in the handbook, so it runs the shared gate like every other
scripta skill that does.

**Load the `writing` skill and run its four questions before drafting**: is this
source of truth, does it need saying, is it the fewest words, is it one atom
with what the repo already says. The gate owns what goes on the page; the rules
below own this entry's own shape, sources and length.

One thing the gate says that this skill leans on hard: it is not a voice filter,
and it calls deslop last. Run deslop on the finished entry.

**Report what the gate did, in the PR body, one line:** the word delta plus, per
question, either "clean" or what it removed. A run that cannot say what the gate
removed did not run the gate.

## Who runs it

Any PM. This skill names no person: where it needs a human it says "the runner",
and the runner is whoever typed the command. A skill that names one person is a
skill only that person can run.

The runner is not the approver. The draft always goes back to the group.

## The four lines, kept apart

Brand activation and legal status are not one thing. Never report them as one,
because a reader who needs one of them would have to unpick the other.

So the draft carries four separate lines, in this order:

1. **Delivery.** What the team shipped this week.
2. **Brand activation.** How many brands have at least one notification
   family active.
3. **Legal and privacy.** Privacy updates.
4. **Performance.** The six frozen metrics below, and nothing else.

Named brands going live is delivery, not activation: activation is the
per-notification family count, and one family going live is not a full
launch.

A number never appears on more than one line. If a stat could sit in either
activation or legal, it is legal.

Each line is one paragraph, opening with its name and a colon, items separated
by ` / ` as they always were:

```
Delivery: <item> / <item> / <item>

Brand activation: <item> / <item>

Legal and privacy: <item> / <item>

Performance (<Monday> to <Sunday>): <the six, in order>
```

The separator and the item style come from the previous entry. The four opening
labels do not: take them from this skill.

## Rule 1 — short, but never cryptic

Items stay short. The old rule "state the fact, not the mechanism" is right and
stays: cut the why, the how, and the consequence clause.

What is added: **an item must be understandable by someone who was not in the
dailies.** Short is not the same as compressed past the point of meaning.

The test is one question, asked per item: *could a reader who missed this week
say what changed?* If the answer needs a follow-up question, the item fails.

| Fails | Passes |
| --- | --- |
| Planning consolidated into Linear | Planning moved from GitHub issues into Linear, one card per activity |
| Webnode gaps triaged and fixed | Webnode's four missing consent fields fixed |
| Reconciliation complete | Purchase reconciliation job complete, verifying the run on data team |

Both columns are about the same length. The fix is naming the subject, not
adding words. An item that grows past 25 words to pass this test is two items,
or it is one item carrying detail that should be cut instead.

## Rule 2 — the previous entry is the template for shape only

Fetch the most recent published entry before drafting. Copy its heading style,
indentation, separator and length.

Do not copy its content decisions, and do not expect it to show you the four
lines. Copy the separator and the item style from
it, take the four labels from the block above. The split, the frozen metric set
and the word ceiling hold whatever the previous entry did.

One exception to "shape only": when a name in a transcript is plainly mangled,
the previous entries are the place to check the real spelling. Correcting a
brand name is not taking a fact from them.

## Rule 3 — stay inside the week

Only what was said in that week's dailies, plus what the runner supplies and
the fixed number sources below. The collected blocks are that week's dailies,
already extracted and confirmed. Nothing from other weeks, other meetings or
prior knowledge.

Anything dropped for being out of scope is listed at the end of the draft, so a
PM can put it back rather than discover the gap later.

## Sources

| What | Where | Rule |
| --- | --- | --- |
| What shipped | The collected blocks in the week's file | The main source. A line the digest runner confirmed on the day beats any summary |
| What shipped, where a block is missing | That meeting's transcript, for each weekday and daily meeting without a block (see Coverage) | Read the transcript, not the Zoom summary, and take only finished work, with speaker, timestamp and quote, the way a block does. Summaries are where shipped work got lost |
| What was decided | The `Decided` lines in the blocks; the handbook's `decisions/` for the same dates, on `main` and on open `digest/*` branches, where a day has no block | The digest already attributed these. A decision is an item when a reader outside the team would see its effect: what a brand gets, what a notification does, what the product now is. A decision about how the team itself runs is not |
| Privacy updated count | The handbook's `engineering/brand-privacy-status.md` | Done means the notification clause is in status `cross-brand` **and** the account activation column is ✅. A ⚠️ does not count: it marks a clause that is there but does not hold, so the control does not pass. Reported on the legal line, not activation |
| Per-notification counts | config-store, `features/production.json` | Count brands with at least one notification family flag enabled: `tldNotifications`, `tldCctldNotifications`, `socialNotifications`, `windsorNotifications`, `welcomeNotification`. A brand in `content/allow-notifications.json` with no family armed is not counted. `demosite` is not a brand |
| Performance numbers | The `hub-daily-report` skill's own queries and exclusions | Never write new SQL for these |

## Coverage

Before drafting, build the week's grid: each weekday, Monday to Friday, against
each daily meeting. The meetings are the titles in the collected blocks, the
dailies the runner's Zoom shows for the week, and at least one row per squad in
the handbook's `org/hub-org-chart.md`, so a squad nobody digested still shows up
as a row. Each cell is a block, a transcript read, or a gap.

- A cell with a block is covered. Do not reread its transcript.
- A cell without a block: read its transcript when the runner can reach it.
- Every cell without a block goes in the confirm block as one grouped point,
  meeting and days, each marked "read from the transcript, not confirmed in a
  digest" or "not reachable". A week built mostly from transcripts says so.
- Friday's own dailies usually have no block yet when this runs, because they
  are digested later in the day. List them in the PR body and say a rerun
  follows once they are digested. That is the normal Friday path.

When two lines disagree across days, the later one wins: shipped Tuesday and
rolled back Thursday is not live. The pair goes in the confirm block.

## The performance window

The previous complete Monday-to-Sunday week, in UTC.

Resolve it from the entry's own date `D`, never from the day the skill runs.
Monday is `D` − 11 and Sunday is `D` − 5, which for a Friday entry is the
Monday-to-Sunday week ending five days before it. The same entry must produce
the same line whenever it is regenerated, including weeks later.

The narrative week and the measured week never overlap. Week N describes week
N's work and reports week N−1's numbers. That is the convention, not an
anomaly, and it is not caveated in the entry.

**The metric set is frozen.** Six metrics, this order, every week:

1. unique users who **viewed** at least one notification
2. expand rate
3. CTR
4. secondary CTR
5. dismiss rate
6. reconciled purchases, with revenue and the "preliminary" marker

If one genuinely cannot be computed, publish the line with it marked
unavailable and say why in the draft. Never silently shorten the line.

If several are unavailable at once, name them together in one sentence rather
than one sentence each.

## When to stop instead of drafting

This applies to the whole run, not only the metrics.

Stop, say what was unreachable, and draft nothing when **every** numbered source
is unreachable: `brand-privacy-status.md`, config-store and the performance
queries together. Three of the four lines would then carry no fact, and an
entry that is mostly the word unavailable is worse than no entry.

Stop when **fewer than three** of the week's days are covered, a day counting
when it has a block or a transcript the runner can reach. Delivery built from
two days of a five-day week is a guess about the other three.

Stop when a squad is missing entirely: no block from its dailies all week, no
transcript the runner can reach, and no summary its own people supplied. The
entry covers the whole Hub, and each squad's dailies are reachable only by
someone on that meeting's invite, so a runner who sits in one squad can reach
one squad. A digest block from that squad's runner is how the others reach it
now. Counting days alone
hides this: four days of one squad passes the check above and still reports
half the Hub, and the half that is missing is the half nobody in the room
notices. Say which squad is missing and ask its own people for that week's
summaries, which Rule 3 already allows as runner-supplied material. A squad
missing on some days only is not a stop: it is a gap in the coverage grid and a
point in the confirm block.

Otherwise carry on and mark what is missing. One unreachable source is a gap in
a line, not a reason to abandon the week.

## What goes in, what stays out

**In:** code shipped, brands activated, decisions taken, documents signed off,
proofs of concept finished, findings closed, milestones reached. Concrete
gating status on something finished, naming who it waits on.

**Out:**

- Work that has not shipped. Opened, in staging, and any percentage complete.
- Internal ways of working. Demo cadence, checklists, our own process decisions.
  This wins over "decisions taken" above when a decision is both, which is
  common: who attends which daily is a decision and still stays out. A decision
  is an item when the thing it decided is visible to a reader outside the team.
- Ticket ids and task counts. Counts of delivered things are fine.
- Per-brand paperwork listed brand by brand. Aggregate into one sentence.
- Infrastructure tuning with no reader-visible surface.
- Personnel, except joiners. Name the person and the role, nothing else.
- Any claim about how much work something took. The numbers carry that.

## The blind spot check

Check that the draft covers platform work, not only brand activation. Before
drafting, check explicitly for:

- authentication and platform plumbing that went live
- WhatsApp and the chat and social assistant flows
- the AI and MCP tooling
- anything reported as built or demoed outside the main brand workstream

A draft with no platform item is a draft with a hole in it, not a quiet week.
Say so positively when the week genuinely had none.

## Length

- **350 words maximum** for the whole entry, and never more than the previous
  published one. Measure, do not estimate.
- **Around 12 substantial items**, not 20 thin ones. A workstream that produced
  an increment earns nothing.
- Median item 17 words or fewer. At most two items over 35.
- Over budget means cutting elaboration inside items, never whole items.

## The confirm block

Every draft ends with this, and it is the point of the whole run. Four or five
points, each one something a PM can answer with yes or a correction.

```
Before this goes out, four things to confirm:

1. <the item most likely to be wrong, stated as a claim>
2. <a number that moved hard against last week, with both figures>
3. <anything attributed without a clear owner in the dailies>
4. <anything included that sits near the "not shipped yet" line>

Dropped as out of scope: <list, or "nothing">
```

Pick these by what is actually uncertain in this week's draft. When the
coverage grid has cells without a block, one point is always the grouped
coverage point. Do not fill four slots with filler. Three real questions beat
four invented ones. If no number
moved hard this week, that slot goes to the next most uncertain thing, not to a
number dressed up as one.

The confirm block and the dropped list sit outside the word budget. They are
for the PMs, and they do not go out with the entry: they go in the PR body,
never in the file, because merging publishes the file as it stands.

## Style

- Past tense, active voice, direct.
- No camel case. `scripta` is always lowercase.
- Prefer "live" to "implemented and deployed".
- Introduce a list with `: `, not ` - `.
- Never attribute work to a squad.
- No corporate filler, no emoji headings, no user-story format.
- Proofread brand names. A brand-name typo is the most common defect.

## Checks before handing the draft back

- [ ] Delivery, brand activation, legal and performance are four separate lines
- [ ] No number appears on two of those lines
- [ ] Window is `D` − 11 to `D` − 5, from the entry's own date, never from today
- [ ] Every item names its subject and passes the "what changed" test
- [ ] Every item traceable to this week's dailies, that week's `decisions/`, or the runner
- [ ] Every squad's dailies represented, not just three days' worth from one
- [ ] Per-notification count read from the family flags in `features/production.json`, never from `allow-notifications.json` alone, `demosite` excluded
- [ ] Privacy updated count read from `brand-privacy-status.md`, done means `cross-brand` notification clause and account activation ✅, ⚠️ does not count
- [ ] All six frozen metrics present, in order, verb is "viewed"
- [ ] Word count measured, at or under 350 and not over the previous entry
- [ ] Around 12 items, none kept to pad
- [ ] At least one platform item, or a positive check that there was none
- [ ] Nothing unshipped, no ways-of-working items, no ticket ids
- [ ] Confirm block present, and its questions are real
- [ ] The write gate's line is in the PR body: word delta, and per question clean or what went
- [ ] Out-of-scope items listed, not silently dropped
- [ ] Collected section deleted from the file, block count in the PR body
- [ ] Every collected line used, merged into an item, or listed as dropped
- [ ] Every weekday and meeting without a block named in the confirm block
- [ ] Delivery filled from shipped lines first; any `Decided` line kept is named in the confirm block
- [ ] No collected section in the file when the PR is marked ready
- [ ] PR title is `weekly update: week <NN>`, with no "do not merge", and the body has no do-not-merge line, with the rest of the body kept

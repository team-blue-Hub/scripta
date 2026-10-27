---
name: writing
description: The shared write gate for every scripta skill that lands prose in the team handbook — document, curate, daily-digest, hardening-interview, weekly-update. Four questions, asked per sentence BEFORE the draft exists. Is this source of truth, does it need saying, is it the fewest words, and is it one atom with what the repo already says. Load it before drafting any handbook prose. Not a voice filter — that is deslop, which this gate calls last.
---

# writing

Five scripta skills write to the handbook: `document` (chat), `daily-digest`
(meetings), `hardening-interview` (interview answers), `curate` (rewrites and stamps),
`weekly-update` (one week's finished work). This is the gate all five run before
committing. It owns what goes ON a page. Each caller keeps its
own routing, triage and PR mechanics.

**This is not a voice filter.** deslop is, and this gate calls it last. deslop judges
whether a sentence reads well; this judges whether the sentence should exist.

## The four questions

Ask them per sentence, in writing, BEFORE the draft exists — not on a finished diff,
where sunk cost argues back. Each default removes text: silence deletes. The question is
never "may I keep this", it is "what forced this in".

### 1. Is this source of truth, or does it belong somewhere else?

Read the target page's own `description:` frontmatter and answer against it. A sentence
outside that scope does not belong on that page, however true it is.

Then route what fails: rationale and "we chose X because" → `decisions/`. Query-level
schema detail → the repo that owns the schema. Live values → a pointer, never a copy.
How to read a dashboard, narration of the edit, or context for the reviewer → the PR
body, or nowhere.

Most sentences that fail this question are not wrong. They are homeless — and a page is
not a home just because the subject matches.

**Write the decision, do not propose it.** A page states what is true now, and merging the
PR is what makes it true. The page and the decision are one act: there is no separate room
where the call gets made, and no later edit that promotes a proposal into a record. Write
the outcome in the present tense and let review argue it. A decision that needs its own
rationale goes to `decisions/` as an ADR, where the same thing holds — merging the ADR is
the decision.

What fails is the hedge: "pending", "to be confirmed", "still to discuss", "the leads
confirm this at the next daily". The tell is a sentence that asks the reader to do
something rather than know something. A page carrying a task is a page where the reader
can no longer tell which lines they may rely on.

If you cannot state it flat, the PR is not ready. Either the call is not yours, and the
person whose it is writes the page, or you are missing a fact, and you go get it. Not
being sure is a reason to hold the PR, never a reason to ship the doubt onto the page.

Worked example: a team meeting cadence
landed on the page hedged as still open for discussion in the PR and in the daily. It
should have stated the cadence flat. Any lead who disagreed had the review to say so, and
their approval is what settles it.

**Never enumerate a set that code owns.** If a type, a config file or a schema already
lists the members — an id union, a brand list, a flag set, an event list — point at it and
state only what the code cannot say: what the set is *for*, what sits outside it and why,
which surface answers "is this live". An enumeration copied into a page is a promise to
re-check it forever, and it is the one kind of bloat that also goes silently wrong. If a
reader would have to compare your list against the code to trust it, the list should not
be there. A pointer cannot drift.

### 2. Does it need saying at all?

Two shapes, both delete-by-default:

- **Obvious to this page's reader.** They know the domain and are looking something up,
  not being taught. A sentence that earns "yes, obviously" was bloat.
- **An explanation that a corrected fact would beat.** This one hides. When a sentence
  exists to explain a trap, a gotcha, why something is not what you would expect, or why
  an earlier claim was wrong — the explanation is a workaround for a fact that is missing
  or badly stated. Fix the fact; delete the explanation. Never ship both: a correction
  plus a paragraph justifying it leaves the reader two things to keep true, and the
  justification is what goes stale first.

Worked example: a run corrected
"a per-notification funnel starts at eligible" to "starts at shown", and also added two
sentences on why eligible was never a meaningful step. The corrected fact needed no
defence. The next day the funnel top moved again, to viewed, so the correction had to be
made twice and the defence rewritten with it.

### 3. Is it the fewest words that survive without the conversation?

The reader has none of the context you have. Cut everything that is not the fact, then
cut the words that only smooth it.

Count words, not lines. Appending a clause to an existing paragraph is nearly free in a
line count and is the most common way these pages grow. Where a caller reports a size,
report the word delta.

### 4. Is it one atom with what the repo already says?

The dangerous case is not the contradiction — callers already check for that. It is
**adjacent and non-conflicting**: two true sentences about one atom, in different places,
neither wrong. Nothing flags them, and the next correction reaches only one of them.

Before writing, grep the WHOLE checkout for the atom — the thing the fact is about, not
the words you were about to use — and list every sentence that touches it. Then:

- Would a reader consult the new fact and an existing sentence together to answer one
  question? → they are one atom. **Rewrite the existing sentence to carry both**, citing
  both sources. This is the default.
- A separate new sentence needs a reason you can state in one line. "It is also true" is
  not one.

The tell in a diff: the `-` line and the `+` line are the same paragraph with a tail
appended.

Worked example: one run appended the atom "the family is the counting unit" to three
different paragraphs of a single page, in one diff. Nothing conflicted, the de-dupe check
passed, and the page then stated one atom three times. The underlying fact changed the
next day, and the correcting PR touched one of the three — leaving the other two to be
found by hand, which is how a page starts disagreeing with its own decision log.

## Verbatim quotes: evidence, or thinking out loud

Stated once here, because the callers differ by nature and each was drawing the line
for itself.

- **Evidence, exempt from every gate above:** a quote from a recorded meeting transcript
  (`daily-digest`) or an interview answer (`hardening-interview`). It is the primary
  source, it belongs in `## Source`, and it is never edited.
- **Not evidence:** a chat message. Someone typing at an assistant is thinking out loud —
  mid-decision, often a question, often not in English. It reads like a decision only
  because it sits next to one. `document` therefore gets NO verbatim exemption: its
  source line is `<Full Name>, <date>, working session` and nothing else. No quote, no
  paste, no transcript line numbers.

This matters most on the ADR path, which is append-only: a chat quote landed there
cannot be cleaned up later, only superseded.

Words a human wants on the record verbatim go in the PR body, where the reviewer reads
them once — or into an ADR only when that human explicitly says so.

## `last-verified`

Bump it only when the page's claims were re-checked end to end. Never for a cross-link,
a typo, an additive row, a one-line correction, an index entry, or a new section beside
untouched text. A cosmetic bump invents a verification that never happened (AGENTS.md
rule 2) and hides real staleness (rule 5).

## Relative time → absolute dates

A date never rots. Prefer "live since 2026-05" to "live now", "shipped 2026-07-16" to
"recently shipped". Where a figure's vintage is known, stamp it with that vintage, not
with the run date.

The same holds forward. "next sprint", "next week", "the day before", "by Monday",
"until then" all read as facts and decay into puzzles: the reader has to recover the
write date and do the arithmetic, and an agent reading the page later will guess instead.
Resolve the anchor against the page's own date and write it. "the sprint beginning
2026-08-03", not "next sprint".

Three cases, in order:

- **Resolvable** — the date is in the source, the transcript, or the frontmatter. Write
  the date. This is nearly always the case, and it is usually one subtraction away.
- **Not yet resolvable** — the anchor is a real event with no date agreed yet. Name the
  event and say so: "the next sprint (start date not set as of 2026-07-30)". Never invent
  a plausible date to satisfy this rule. A wrong date is worse than the relative phrase,
  because it stops looking like something to check.
- **Verbatim quote** — exempt, like every other gate here. A speaker saying "next week"
  keeps saying "next week". Where the quote carries the anchor, resolve it in the prose
  around it.

**Titles and filenames hardest of all.** A relative reference in an ADR title cannot be
corrected later (AGENTS.md rule 4, decisions are append-only) and it is the string that
propagates into `index.md`, `decisions/README.md`, and every cross-link. Callers that
name a file or a heading run this rule before they name it, not on the finished diff.

Worked example (an ADR whose title said "next sprint"):
the title, the filename and four body sentences turned on "next sprint" and "this
sprint", while the transcript quoted in the same file pinned the sprint to the Monday
after a Thursday meeting. That is 2026-08-03, one subtraction from the frontmatter
`date:`. The anchor was on the page. The gate ran on the body and not on the title, so
the one string that can never be fixed is the one that kept the relative phrase.

## Last step: deslop

Run every new sentence through a deslop skill when one is installed (the Hub's is in its
ai-recipes `core` plugin, `skills/writing/deslop`). Never vendor a copy into scripta; it would drift.
Stamps, dates and evidence quotes are exempt. No deslop skill installed → minimum scan
yourself: rule-of-three triplets, mid-sentence em-dashes tacking on a clause, consultant
verbs, marketing adverbs.

## Reporting back to the caller

The caller puts one line in its PR body: the word delta, plus for each of the four
questions either "clean" or what it removed. A caller that cannot say what the gate
removed did not run the gate.

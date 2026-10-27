---
name: document
description: The save button for the team source of truth — take a verified fact from the current conversation and land it in the right handbook page as a small PR. Use when the user says "document this", "save this to scripta", "publish into the handbook / the repository", "add this to the source of truth", or confirms a nugget worth keeping. Its sweep mode — find ALL the candidate nuggets in a long chat and triage them with the human — is exposed as its own command, /scripta:compound. Facts only — rationale routes to decisions/ (via daily-digest's ADR format), fast-changing values become pointers, and nothing merges without a human.
---

# document

The general-purpose write half of the engine (digest = meeting ingest, **document = chat
ingest**, answers = query, curate = lint). One loop: **fact in conversation → verified →
minimal edit in its one home → PR a human merges.**

The human is always in the loop: nothing merges or becomes team-visible without explicit
confirmation. If in doubt at any step, ask — never assume.

## Step 0 — locate the source-of-truth repo

Find the team handbook: a local checkout containing `where-truth-lives.md` and
`decisions/`. Look in the order the session hook uses: the folder in `SCRIPTA_HANDBOOK_PATH`
if it is set, otherwise `handbook_path` in `~/.config/scripta/config.json` if it is set,
otherwise `~/PROJECTS/hub-scripta-handbook`, then `~/PROJECTS/scripta`.
A set `SCRIPTA_HANDBOOK_PATH` or `handbook_path` is used alone: when that folder is not a handbook, ask, and never fall back to the `~/PROJECTS` folders.
The hook already did this at session start: when its note says "A team handbook exists at
`<path>`", use that path. If none of them is a handbook, ask the user for the path. `git pull` main first —
routing and de-dupe are only as good as the checkout. Read the handbook's `AGENTS.md`;
its rules bind every step below.

## Step 1 — pin down the fact, then verify it

1. State the candidate fact back to the user as ONE plain sentence (or the smallest
   set of sentences that stands alone). No approval of the exact wording → no write.
2. **Verify against the primary source before writing** (AGENTS.md rule 2): trace the
   claim to the code, config, PR, dashboard, or person — not to memory, not to another
   doc. If the conversation itself established it against a primary source, cite that.
   Unverifiable → STOP and say so. A smaller true repo beats a bigger one with an
   invented fact.
3. **Source list before prose.** Write the sources out first — one row per clause,
   each a `file:line`, a URL, or a person + date — and show it in-session before any
   page text exists. A clause with no row does not get written.
   Never draft first and verify after: the order is the fix, not more care.

## Step 2 — classify, then route

Classify the fact first; the class decides where (and whether) it lives:

- **Timeless / months-scale** (how something works, a name, a URL that won't move) →
  store the fact itself.
- **Dated snapshot** (a figure, a state that was true when measured) → store it stamped
  (`as of YYYY-MM-DD`), on a page with `owner:` + `last-verified:`.
- **Fast-changing value** (rollout status, live metrics, meeting links, anything that
  changed recently or predictably will) → NEVER store the value. Store a **pointer** to
  its one live home (AGENTS.md rule 3: you can't drift what you don't duplicate). If
  `where-truth-lives.md` lacks a row for that kind of fact, the edit IS the new row.
- **A decision or its rationale** ("we chose X because…") → not a page edit at all;
  it's an ADR. First find the concept's owning page through `where-truth-lives.md`, then
  grep that page and `decisions/` for the rule it states: the atom, not the words. If a page
  or an ADR already states the same choice with the same scope, and the chat changes nothing
  about it (value, scope, owner or reason), there is nothing to write: tell the user where
  it lives and stop. A decision that narrows, extends or reverses a recorded rule is new.
  Otherwise hand off to the daily-digest ADR format in
  `decisions/` (append-only, rule 4). Never bolt a why-paragraph onto a fact page.

Then route the fact via `where-truth-lives.md` → its ONE home page. Nothing has two
homes. No home fits → propose page + registry row, ask the human, create on approval.

**Data facts route by kind, not by asker**: query-level detail — what a
field means, joins, traps, new pipeline fields — goes to the data dictionaries in
the databridge-elt repo (open the PR THERE, not in the handbook); orientation-level
knowledge goes to the handbook's data page; numbers follow the dated-snapshot rule
above wherever they land. The runner never decides this by feel — the kind decides.

## Step 3 — de-dupe: update in place, never append a twin

Search the target page (and `index.md`) for the fact's subject before writing:

- Already there and still true → nothing to do; tell the user, stop.
- There but outdated → correct that line in place. The old claim gets fixed, not
  neighbored by a new one.
- Contradicts something elsewhere → fix both in this PR or flag the conflict in the PR
  body for the owner. Never leave the repo disagreeing with itself.
- **Adjacent and non-conflicting** → the common case, and the one that quietly rots the
  repo. Two true sentences about one atom, neither wrong, nothing to flag — and the next
  correction reaches only one. Grep the whole checkout for the atom (the thing the fact
  is about, not the words you were about to use) and list every sentence touching it. If
  a reader would consult the new fact and an existing sentence together to answer one
  question, they are one atom: **rewrite that sentence to carry both**. Adding a separate
  sentence needs a one-line reason; "it is also true" is not one. Full rule and the
  worked example: the `writing` skill, question 4.
- Genuinely new → add it at the smallest sensible spot in the existing structure.

## Step 4 — write minimal (the style gate)

**Load the `writing` skill and run its four questions before drafting** — is this source
of truth, does it need saying, is it the fewest words, is it one atom with what the repo
already says. It owns the gate; it also owns the `last-verified` rule, the verbatim
policy, the relative-time→absolute-dates rule, and the deslop handoff. Do not restate
those here.

`document`-specific on top of it:

- One to three sentences is the norm. A new section is a smell; a new page is an event —
  say so and get the human's yes BEFORE drafting it, not a defence after.
- **No origin citations in repo content.** "(Origin: <person>, <date> — ...)", "(per the
  X call)", quoted rationale — none of it lands on a page or in a skill file. Provenance
  belongs in the PR body, where the reviewer reads it once and the repo stays clean.
- Frontmatter: `owner:` confirmed (rule 5); `last-verified:` per the `writing` skill's
  rule, which is narrower than "materially changed" and mostly means leave it alone.
  New page → full frontmatter + `index.md` entry in the same PR.

## Step 4.5 — the review pass (mandatory, never skipped)

The first draft is never the PR.

Re-read the full diff as a hostile reviewer. For each of the `writing` skill's four
questions, name what you removed or say "clean". Any question you cannot answer that way
→ rewrite and re-check. Then:

1. **Every sentence is load-bearing:** delete it mentally — if the fact still stands,
   delete it actually.
2. **It reads like the page around it:** same voice, same heading depth, same list
   style. A reviewer should not be able to tell where the old text ends and the new
   begins.
3. **The Step 2 classification still holds for what's actually written** — drafts
   drift: a "pointer" that grew a copied value, a "timeless" fact that picked up a
   date, go back to Step 2.
4. **Report the word delta, not the line delta** (`git diff --word-diff` / count added
   words). A clause appended to an existing paragraph is nearly free in lines and is the
   main way these pages grew; a line count cannot see it.

In the PR body, one line: the word delta plus, per question, what the gate removed. Not
"review pass: 2 drafts" — that is unfalsifiable.

## Step 5 — the mechanical gate

Run curate's vendored linter TWICE — the script scans the whole checkout, not single
files, and the repo carries a few known accepted baseline findings, so a single run
can't tell yours from theirs:

    python3 <plugin>/skills/curate/scripts/freshness_lint.py --path <handbook checkout> --json

once BEFORE your edits and once AFTER; compare the two outputs. (One rule: every stored
fact must be timeless, dated, or a pointer — config in the handbook's `.freshness.json`.)
Only a finding present after and absent before is yours, and it means the edit is
wrong-shaped: reclassify (Step 2) and rewrite. Baseline findings are curate's problem,
not yours — leave them. Don't stamp cosmetically to silence anything, and don't ship
a finding you introduced.

## Step 6 — the PR

1. **Duplicate check first** (two runners documenting the same fact must not both
   write): `git ls-remote --heads origin 'document/*'` plus
   `gh pr list --state open --search "<fact subject>"`. A hit that covers this fact →
   STOP, show the runner the existing branch/PR, and offer to extend that PR instead
   of opening a twin.
2. Branch `document/<yyyy-mm-dd>-<slug>` off main, and **assert the base before the first
   commit** (`git merge-base --is-ancestor origin/main HEAD` on a freshly pulled main;
   `git log --oneline origin/main..HEAD` must list only your commits).
   One fact, or one tightly-coupled cluster of at most three, per PR — a grab-bag PR gets
   rubber-stamped, which defeats the review gate.
3. `gh pr create` — **ready for review, not draft**. The human gate already happened
   at Step 1 (wording approved in-session); a draft on top of that is a second gate
   nobody needs. Use `--draft` ONLY when the human has not
   yet approved the exact wording — and then they mark it ready the same day.
   Body, in this order and nothing else: the fact as written; how it was verified
   (Step 1, as a source list — `file:line`, URL, or person + date); the Step 4.5 line;
   and only if routing was non-obvious, one line on why this home. No `## Process`
   section narrating the skill run, no defence of the diff's size, no generated-with
   footer — the body is provenance a reviewer reads once, not an essay. If it runs past
   a screen, the diff is probably the thing that needs cutting. Tag the page's `owner:`
   as reviewer; when the owner IS the runner (GitHub rejects author-as-reviewer) or the
   handle doesn't resolve, say so in the PR body and leave the reviewer slot to the human.
4. The owner merges. Never merge your own work (rule 1).

## Sweep mode — "compound this chat"

The end-of-session harvest:
the runner shouldn't have to notice each nugget — the sweep finds candidates, the
human picks. Same pipeline, plural input, one extra gate.

1. **Scan the whole conversation** for candidates. A candidate is something that
   would survive Step 1 on its own: verified against a primary source during the
   chat (or verifiable now), and it survives without the conversation. Explicitly
   NOT candidates: speculation, opinions, half-finished threads, fast-changing state
   (unless the pointer form is itself the nugget), anything personal or ephemeral,
   and anything a quick grep shows the handbook already has.
2. **Triage list, then stop** (the extra gate — same shape as daily-digest's candidate
   decisions): a numbered list, each entry ONE line — the fact as it would be written,
   its class (timeless / dated / pointer / decision→ADR), its home page. Calibrate
   honestly: zero candidates from a long working session usually means you missed
   some; a dozen from a casual chat means you're padding. The human keeps, drops, or
   rewords each entry. Nothing proceeds unsorted, and dropped means dropped — don't
   re-propose it next sweep unless new evidence appeared.
3. **Each survivor runs the standard pipeline** (Steps 2–6 including 4.5: classify, route,
   de-dupe, minimal write, review pass, lint gate). Group the output: one PR per home page, not one PR per
   fact — a sweep that opens ten one-line PRs defeats the review gate as surely as a
   grab-bag PR does. Say the grouping in the PR body.
4. **Decisions found in the sweep** go to the ADR path only with the human's explicit
   yes, sourced as `<Full Name>, <date>, working session` — never fabricate a
   meeting-shaped source for a chat-born decision, and **never paste the chat**. Chat is
   thinking out loud, not evidence; `document` has no verbatim exemption (the `writing`
   skill draws the line). ADRs are append-only, so a chat quote there can only be superseded, never cleaned.
5. Sweep never runs unprompted. It's invoked, or offered ONCE at a natural end of a
   session that plainly produced durable knowledge — never nagged.

## Guardrails

- Nothing leaves the working tree until Step 6 — no commits, no pushes, no PRs —
  and Step 6 produces PRs a human has already gated (Step 1) but never merges.
- Never edit ADRs (append-only) and never auto-create one without the human's yes.
- Refuse to store what the classifier calls fast-changing, even if asked twice —
  offer the pointer form instead and say why in one sentence.
- When unsure: ask, or leave it out.

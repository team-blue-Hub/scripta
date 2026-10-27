# LEARNINGS — daily-digest calibration from real runs

Rules for this file (hard constraints, in this order of importance):

1. **Evidence or it doesn't exist.** Every entry quotes its source verbatim — a triage reply,
   a PR review comment, a merge diff. No quote, no entry. This is the anti-hallucination gate.
2. **Cap: 12 entries / ~80 lines.** At the cap, adding an entry means deleting the weakest one.
3. **Prune on every write.** Delete entries that were promoted into SKILL.md, proved wrong,
   or stopped applying.
4. **Promotion threshold:** a lesson seen in 2–3 separate runs graduates into a SKILL.md rule
   via a normal PR, then its entry is deleted from here. One-off feedback stays here only.

Read this file at the start of every digest run, before acquiring the transcript.

---

## 2026-07-16 · ADR writing · Consequences must follow from THIS decision

- **Seen:** 1 run
- **Lesson:** the Consequences section carries only what follows from the decision itself.
  Adjacent facts from the same discussion (parallel workstreams, things riding the same
  release, open verifications) belong in the digest's Topics/Tasks, not the ADR — even
  when they share the timestamp range.
- **Evidence:** a handbook PR, first human inline comment on any digest PR (a reviewer,
  on an ADR's Consequences): "this and the next point are not related to this
  decision" — the ingestion-check and a brand's bullets, both true, both from the same
  conversation, neither a consequence of ship-with-current-UX.

## 2026-07-16 · review · approved batches merge unchanged; names are the residual error class

- **Seen:** 2 runs (one PR: 12→7 proposed, 7 merged verbatim, zero human edits;
  another: 9→8 survived triage, both reviewer comments were
  name corrections, no decision or quote challenged)
- **Lesson:** when triage is done by the runner and quotes are verbatim, reviewers approve
  the substance without edits — the human effort concentrates at triage, not review. What
  still draws comments is *names* (people and brands), so verification effort belongs there.
- **Evidence:** The first PR was approved by two reviewers exactly as pushed. The second was approved
  after two non-blocking inline comments, both names: "correct name is <brand>" and
  "<person>, correct - Legal counselor"; fixed pre-merge, no other edits requested.

## 2026-07-24 · ADR writing · brand names drift too — check the brand list, not just the roster

- **Seen:** 1 run
- **Lesson:** Step 4 verifies person names against `people/`, but brand and product names
  have the same failure mode — transcript spelling and repo precedent can both be wrong
  (the handbook itself had a wrong brand spelling in ten merged ADRs). Check brand spellings against
  the team's brand list before they land in titles and index lines.
- **Evidence:** a reviewer's inline comment on a digest PR: "FYI, not a blocker, correct name is <brand> /
  full list of brands with names and IDs: [link] / happy to wait for when we import data to
  fix this." New ADRs fixed pre-merge; merged ADRs left append-only.

## 2026-08-05 · process · a piggybacked digest run splits the review gate on the day's PR

- **Seen:** 1 run
- **Lesson:** one-PR-per-day means a later run lands its commits on the already-open digest
  PR. If the later runner is also that PR's reviewer, their approval cannot cover their own
  commits. When piggybacking: say in the PR which commits are yours and name who must review
  them before merge; when reviewing a PR you piggybacked on, scope the approval explicitly.
- **Evidence:** a reviewer, approving a handbook PR: "the last commit (the three ADRs from
  another team's daily) is my own digest run piggybacking on the day's PR, so my approval
  doesn't cover it. That part needs a review from someone else before merge."

## 2026-08-04 · CI · the linear-code bot red X is not about your digest; a human push clears it

- **Seen:** 2 runs (one digest PR needed a human-actor push; the same workaround is on
  record for another PR's cycle)
- **Lesson:** digest PRs can show a failing check from the linear-code bot that has nothing
  to do with the digest content. Do not rewrite or re-triage chasing it; any human push
  un-sticks it. Root cause is tracked in the org's issue tracker — delete this entry when
  that closes.
- **Evidence:** commit in a digest PR's history: "ci: human-actor push to clear the
  linear-code bot check rejection"; the runner's own note quoted on another PR:
  "until then a human push un-sticks a red X."


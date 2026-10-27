---
name: deep-plan
description: The enforced plan → clear → execute flow — think with full context, write the plan to a file, then execute from a fresh session that reads only the plan. Use when the user says "/deep-plan", "plan this properly", "let's not burn context", "execute PLAN-<anything>.md" (that phrase IS this skill's execute phase), or "/deep-plan handoff" / "capture state, I'm running out of context" mid-task. The token-saving best practice as one command instead of a habit everyone must remember.
---

# deep-plan

One loop: **explore fat → plan to a file → clear → execute thin.** The context spent
understanding a problem is dead weight during execution; this skill makes dropping it
the default instead of a discipline. The fix is a flow, not a reminder.

Do NOT use the built-in plan mode (EnterPlanMode/ExitPlanMode) inside this flow: its
approve-then-proceed step continues in the same fat session, which is exactly what
Phase 2 exists to prevent. This skill replaces it here, not wraps it.

## Phase 1 — plan (this session, context is disposable)

1. Explore as widely as the task needs — read code, search, ask the user. This session's
   context is about to be thrown away, so spending it is free.
2. Write the plan to `PLAN-<slug>.md` in the current repo root. Immediately append
   `PLAN-*.md` to that repo's `.git/info/exclude` (NOT `.gitignore` — no PR, works in
   any checkout, keeps the file out of `git add -A` sweeps and out of the handbook's
   freshness lint). Work spanning multiple repos: ONE plan file, in the repo where
   execution starts; every file reference in it is an absolute path.
3. The plan must be executable by a session that has seen NOTHING except this file.
   Hard test for every line: "does this sentence survive without the conversation?"
   It starts with this header, verbatim, so the flow survives even if this skill
   doesn't load in the fresh session:

   > This is a deep-plan execution file. Read only the files named here — do not
   > re-explore. Work the steps in order, checking each off in this file as it lands.
   > A fact missing here is a plan bug: ask, then append the answer here.

   Then:
   - **Goal** — one sentence, plus how to verify it's done (command, test, URL).
   - **Start in** — the absolute directory the execute session should run from.
   - **Context a stranger needs** — files involved (absolute paths + line refs),
     constraints/conventions found while exploring, decisions already made with the
     user. Facts, not narration of the exploration.
   - **Steps** — numbered checkboxes, each independently checkable, smallest that works.
   - **Not doing** — what was considered and excluded, so the executor doesn't
     re-litigate it.
4. Show the user the plan. Iterate until they approve. No approval → no phase 2.

## Phase 1b — mid-task handoff (entering with the context already fat)

"/deep-plan handoff", "capture state", or the user is deep in a task at high context:
same as Phase 1 but the exploration already happened — capture instead of explore.
The plan file additionally records **current state** (what already works), **changes
made so far** (files touched, committed or not), and **next steps** as the Steps list.
Then hand off exactly as Phase 2. This is the "save my session before it drowns" path.

## Phase 2 — the handoff (the enforced part)

On approval, do NOT keep working. Give the user this handoff (with the actual
filename, not the placeholder) and stop:

> Plan saved to `PLAN-<slug>.md`. Run `/clear`, then say: **execute PLAN-<slug>.md**.

That stop is the skill's entire value: continuing in the fat session is what burns the
tokens. Do not "just do step 1 quickly" in the planning session. If the user says
"execute it" / "go ahead" WITHOUT having cleared — this session still contains the
Phase 1 exploration — refuse once and repeat the handoff line; executing fat because
the user forgot defeats the flow silently, which is worse than a reminder.

## Phase 3 — execute (fresh session, context is precious)

When invoked as "execute PLAN-<file>.md":

1. Read the plan file, `cd` to its **Start in** directory. Read ONLY the files it
   names. Do not re-explore; the plan is the exploration's output. Missing fact in
   the plan → that's a plan bug: ask the user, then append the answer to the plan
   file so the next session has it too.
2. Work the steps in order, checking each off in the plan file (`- [x]`) as it lands —
   the file is the progress tracker, so an interrupted run resumes by reading it.
3. Done = the Goal's verify line passes. Then delete the plan file (or offer to), and
   if real decisions or durable facts surfaced, offer `/document` (facts → handbook)
   or the daily-digest ADR path (decisions) — don't let them die with the session.

## Guardrails

- Plan files are scaffolding, never committed (`.git/info/exclude` in Phase 1 enforces
  it). Durable facts belong in the handbook via `/document`, decisions in `decisions/`
  — not in plan files.
- Self-invoked on a size judgment (the user didn't ask): confirm in one line first —
  "this looks big; plan-then-clear, or straight through?" — the ceremony is only worth
  it when the user agrees the task is big.
- User-invoked: Phase 1 always ends at the handoff, even when the task turned out small.
- Phase 3 that finds the plan wrong stops and says so; it never silently re-plans.
  Re-planning is Phase 1, and it's the user's call to restart it.

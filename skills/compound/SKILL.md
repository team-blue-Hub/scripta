---
name: compound
description: The end-of-session sweep as its own slash command — find ALL the candidate nuggets in this conversation, triage them with the human, land the survivors in the handbook as small PRs. Use at the natural end of a working session, or when the user says "/scripta:compound", "compound this chat", "sweep this conversation", "what's worth saving from this session". A named entry point for the document skill's sweep mode, so it's reachable from the slash menu instead of phrase-triggering.
---

# compound

A named entry point, not a second pipeline. Read `${CLAUDE_PLUGIN_ROOT}/skills/document/SKILL.md`
and execute its **Sweep mode** section end to end — same candidate rules, same
triage gate (nothing proceeds unsorted), same one-PR-per-home-page grouping, same
guardrails. Everything the document skill forbids, this command forbids.

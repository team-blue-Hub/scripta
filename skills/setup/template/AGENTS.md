---
type: reference
title: AGENTS.md, how to work in this handbook (read this first)
description: Operating rules for any AI agent or person making changes in this repo
tags: [reference, agents]
timestamp: {{date}}
owner: {{owner}}
last-verified: {{date}}
---

# AGENTS.md, read this first

If you are a Claude session (or any AI agent) opening this repo, read this before you change anything.

## What this repo is

The {{team}} team's source of truth: human-written Markdown in Git. If it is written here, it is the team's official version. When this repo and a chat thread, a note or a memory disagree, this repo wins, or it gets fixed with a pull request.

The map of everything is [index.md](index.md). Where each kind of fact officially lives is [where-truth-lives.md](where-truth-lives.md).

## The rules

The skills cite these by number, so keep the numbers.

1. **AI drafts, a human approves.** Every change lands as a pull request. Nobody pushes to `main` directly, and nobody merges their own work.
2. **Never invent facts. Verify against the primary source before you write.** Trace a claim, a name or a date to the code, the pull request, the config or the person, not to memory or to another page that may be stale. If you cannot verify it, say so.
3. **Point, don't copy.** Link to the one official home and never copy live state, such as numbers that change or "is it live yet". You can't drift what you don't duplicate.
4. **Decisions are append-only.** One dated file per decision in [decisions/](decisions/README.md). Never edit a past decision to change what it says. A new decision supersedes it.
5. **Every living page has an owner and a `last-verified` date** in its header, as `owner: Full Name (@handle)`. If you create a page or change most of it, set both. Stale must be visible, never silent.
6. **Write short and plain.** No filler and no chatbot phrasing. Stay faithful to what was decided.

## How to change something

1. Branch.
2. Edit or add the page.
3. Open a pull request.
4. A person reviews it (is this what we decided, are the facts right, is anything invented) and merges.

## When you're unsure

Ask, or leave it out. A smaller true repo beats a bigger one with an invented fact in it.

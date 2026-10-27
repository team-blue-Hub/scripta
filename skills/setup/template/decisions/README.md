---
type: index
title: Decisions
description: The team's decision log, one dated, append-only file per decision
tags: [index, decisions]
timestamp: {{date}}
owner: {{owner}}
last-verified: {{date}}
---

# Decisions

One dated file per decision, append-only. Changed your mind? Write a new decision that supersedes the old one, and never edit the old one ([AGENTS.md](../AGENTS.md) rule 4).

## How a decision file looks

The file is `YYYY-MM-DD-slug.md`, dated the day the decision was made. Its id is the file name without `.md`. Until this folder holds real decisions, copy this shape:

```markdown
---
type: decision
title: <short imperative title>
tags: [decision]
status: accepted
date: YYYY-MM-DD
deciders: "<who proposed, with role>; <who agreed>"
---

# <short imperative title>

## Context

Why this came up, in two or three sentences, with links to the pages it touches.

## Decision

What was decided, in plain words.

## Consequences

What follows from this decision, and only from it.

## Source

The meeting name, date and timestamp, the verbatim quote, and a link to the recording
or the thread when there is one.
```

## The log

One line per decision, oldest first: `- [<title>](<id>.md)`.

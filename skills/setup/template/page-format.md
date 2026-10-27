---
type: reference
title: Page format, the header every page carries
description: The header for living pages and for decisions, and the page types
tags: [reference, format]
timestamp: {{date}}
owner: {{owner}}
last-verified: {{date}}
---

# Page format

Every page starts with the same YAML header. Decisions have their own, shorter one.

## Living pages

```yaml
type: index | concept | reference | guide | person
title: what the page is, in one line
description: optional one-liner, used by maps and search
tags: [<the type>, <topic>]
timestamp: YYYY-MM-DD          # when the page was created
owner: Full Name (@handle)     # co-owners comma-separated
last-verified: YYYY-MM-DD      # when someone last confirmed the whole page true
```

`owner` and `last-verified` are required ([AGENTS.md](AGENTS.md) rule 5). `last-verified` moves only when someone re-checked the whole page, not when a line was added.

## Decisions

```yaml
type: decision
title: the decision, in one line
tags: [decision]
status: accepted               # or: superseded by <id>
date: YYYY-MM-DD               # the day it was decided
deciders: who proposed; who agreed
```

No owner and no `last-verified`: a decision is never edited, only superseded ([AGENTS.md](AGENTS.md) rule 4). The file is `decisions/YYYY-MM-DD-slug.md`, and its id is the file name without `.md`. Its heading is `# <title>`. The sections and an example are in [decisions/README.md](decisions/README.md).

## Page types

| type | what it is |
|---|---|
| `index` | a map of other pages, like index.md and each folder's README.md |
| `concept` | explains one idea the team relies on |
| `reference` | a factual lookup, like this page |
| `guide` | how to do one thing, step by step |
| `person` | one team member: handle, role and what they can vouch for |
| `decision` | one decision, append-only |

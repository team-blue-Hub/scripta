# scripta

**A team brain for your coding agents.** scripta turns what your team decides in meetings
and chats into a handbook that every teammate, and every agent session, reads from. AI
writes the drafts, and a person on the team merges every change.

*Verba volant, scripta manent:* spoken words fly away, written words remain.

[Get started](docs/getting-started.md) · [Without and with](#your-agent-without-and-with-scripta) · [How it works](#how-it-works) ·
[Principles](#principles) · [FAQ](#faq) · [Reference](docs/reference.md)

## Why

Coding agents start every session from zero, so you end up explaining the same things again
and again: who owns what, what the team decided last week, why the API looks the way it
does. The answers usually exist somewhere, spread over meeting recordings and a wiki nobody
fully trusts any more, so the agent can't find them and you become its context.

The two obvious fixes both make it worse:

- **Let the AI write the docs.** An AI describing your code mostly tells the agent what it
  could read by itself, and [a 2026 study of `AGENTS.md` files](https://arxiv.org/abs/2602.11988)
  found that repository overviews don't make coding agents succeed more often, while context
  files push cost up by over 20%. And once people find a few wrong pages, they stop trusting
  the whole thing.
- **Point the agent at the raw sources.** Transcripts and threads contradict each other and
  still carry every idea the team dropped, so an agent answering from them has to guess.

scripta goes the other way: AI drafts short pages from your meetings and sessions into a git
repo, and a teammate approves each one before any session reads it.

## Your agent, without and with scripta

| When you | Without scripta | With scripta |
|---|---|---|
| Start a task | You paste the context in, or the agent reads the codebase to work out what you meant | Each session knows where the handbook is, and loads its map as soon as you ask about the team |
| Learn something worth keeping | It stays in that one chat, and the next session starts without it | It becomes a small pull request, with the owner of the page tagged to review it |
| Need what the team decided last week | It sits in a recording the agent has never seen | It is a decision record, with the quote that backs it |
| Ask where a fact lives, like a feature flag or a metric | It greps, guesses, or asks you | `where-truth-lives.md` names the one home and links to it |
| Hit two sources that disagree | It has no way to tell which one is current | The home wins, and the other one gets fixed |
| Bring in a new teammate | They pick things up from meetings for weeks | They and their agent read the same handbook from day one |
| Face a judgment call | It comes back to you, every time | Your team's standards are written down, so fewer calls come back to you |

It also compounds, because every fact one person saves makes every later session better for
the whole team. At the [team.blue](https://team.blue) Hub, where scripta has run since July
2026, about 20 people had opened over 550 handbook pull requests and recorded more than 360
decisions as of October 2026, while the team grew from 9 to 19 people. It helped us double the
productivity of our development team.

## How it works

```
   meetings            chats              long sessions
       │                 │                      │
 /scripta:daily-digest  "document this"   "compound this chat"
       └─────────────────┼──────────────────────┘
                         ▼
                 small pull request
                         │   a teammate merges it
                         ▼
          your team's handbook: Markdown in git
                         │   a hook points each session at it
                         ▼
          every teammate's agent sessions start from it
```

There are two repos. **scripta** (this one) is the plugin. **Your handbook** is your
team's content, in its own repo, private if you like. `/scripta:setup` creates an empty one
from a template the first time.

**Per-user access, shared knowledge.** scripta runs in *your* agent with *your* connectors:
your Zoom sees your meetings, nobody else's. What it drafts lands as pull requests in the
shared handbook, and that is where private access turns into team knowledge.

**Nothing migrates.** Code, specs, tickets and recordings stay where they are today. The
handbook holds the facts that change slowly, and points to where the fast ones live.

**No servers.** scripta is a plugin and a git repo, guarded by the GitHub permissions your
team already has. There is no scripta service and nothing always-on.

## Principles

1. **One source of truth.** Each kind of fact has one home, listed in the handbook's
   `where-truth-lives.md`. When two places disagree, the home wins and the other gets fixed.
2. **A person merges every change.** AI drafts, a person merges, and nobody merges their
   own work. Agents left to update a knowledge base on their own drift, and once people
   catch a few wrong pages they stop trusting the rest.
3. **Decisions, not transcripts.** A meeting enters the handbook as the decisions it made,
   with the quote that backs each one. Raw notes stay out, so the handbook stays small and
   does not contradict itself.
4. **Intent, not a description of the code.** The handbook says what things are for and
   why the team chose them. The code already says how.
5. **Store slow facts, point to fast ones.** Decisions and strategy are stored here.
   Anything that changes weekly stays in its own tool, and the handbook links to it. You
   can't drift what you don't duplicate.
6. **Freshness is checked, never auto-fixed.** Every page has an owner and a
   `last-verified` date. `/scripta:curate` finds stale pages and asks each owner to
   confirm or fix theirs, because only the owner knows whether it still holds.
7. **Small context.** The handbook's `index.md` lists every page, so an agent opens the page
   it needs instead of reading the whole handbook. The hooks load the two map pages only when
   a prompt is about the team.

## Works with

| Agent | What works |
|---|---|
| **Claude Code** | Everything, including the hooks that point every session at the handbook |
| **OpenCode** | The skills load (verified on OpenCode 1.18.16, 2026-08-10). No hooks, so you point a session at the handbook yourself, and a few skills do less: see [docs/opencode.md](docs/opencode.md) |
| **Any other agent** | The handbook is plain Markdown in git with an `AGENTS.md` at its root, so any agent that reads files can use it. The skills are untested there. |

## Get started

You need Claude Code, git, the GitHub CLI signed in (`gh auth login`), Python 3 as
`python3`, and one teammate to review what scripta proposes. In Claude Code:

```
/plugin marketplace add team-blue-Hub/scripta
/plugin install scripta@scripta-plugin
```

Start a new session so the skills load, then run:

```
/scripta:setup
```

Setup finds your team's handbook, or creates a new one from the template if your team has
none.

**Then start with the daily digest.** After your next meeting, run `/scripta:daily-digest`.
It finds the meeting through the Zoom connector, or takes a transcript you paste, and shows
you the candidate decisions; the ones you keep go into a draft pull request. Ask a teammate
to merge it, and that is your team's first decision on record.

[Getting started](docs/getting-started.md) walks a team from nothing to that first merged
decision, with auto-updates and bringing in teammates.

## The working rhythm

1. **Once:** `/scripta:setup`.
2. **After a meeting:** `/scripta:daily-digest`. On a Mac or Windows PC it can open itself
   at noon on weekdays.
3. **When a fact worth keeping comes up in a chat:** say "document this" right away, because
   facts saved for later tend to get forgotten.
4. **At the end of a long session:** "compound this chat".
5. **Back from time off:** `/scripta:catch-up`.
6. **Before a big, context-heavy task:** `/scripta:deep-plan`.
7. **Every couple of weeks:** `/scripta:curate`, and answer the hardening interview when it
   asks.

Document first, curate after: one puts knowledge in, the other keeps it true.

Typical prompts:

- `digest today's daily`: after any meeting you attended (Zoom connector), about 30 minutes
  after it ends
- `run the digest on this transcript: <path or pasted text>`: no Zoom needed
- `document this` mid-chat, when a fact is worth keeping, and `compound this chat` at the end
  of a long one
- `curate the handbook` or `check freshness`: the maintenance sweep
- `also propose the task updates`, during a digest run: drafts board updates for the PM to
  apply, and asks you before every write

## The skills

| Skill | Use it to |
|---|---|
| `/scripta:setup` | Connect your agent to the handbook, or create one. Safe to re-run |
| `/scripta:daily-digest` | Turn a meeting into draft decision records, and optionally task updates for your board |
| `/scripta:document` | Save one fact from the current chat as a small pull request |
| `/scripta:compound` | Sweep a long session for everything worth saving, and pick |
| `/scripta:catch-up` | Read what was decided while you were away. Writes nothing |
| `/scripta:curate` | Find stale pages and ask their owners to check them |
| `/scripta:hardening-interview` | Answer up to ten questions that re-check the pages you own |
| `/scripta:deep-plan` | Plan a large task, then build it from a fresh session that reads only the plan |
| `/scripta:weekly-update` | Build the team's weekly update from the week's digests. Off unless your handbook's `scripta.json` turns it on |

`writing` is not a command: it is the check every skill above runs on new text before it
commits. Every skill shows you what it found before it writes anything, and nothing reaches
the handbook's `main` until a person merges it. Each skill in detail:
[Reference](docs/reference.md#every-skill-in-detail).

The same marketplace also has `/prototype`, a separate plugin that turns an idea into a
shareable web page: [plugins/prototype](plugins/prototype/README.md).

## FAQ

**Why not Notion or Confluence?** Keep them, as the sketchpad. A wiki has no review step
and no mark for "this is the current version", so pages go stale together and an agent
cannot tell which one to believe. scripta keeps the small canonical part in git, where every
change is dated and someone signed it off, and agents read it with the file tools they
already have.

**Why not let the agent read our transcripts directly?** Transcripts contradict each other
and keep every idea the team dropped, so an agent answering from them guesses more. scripta
pulls each decision out once and a person confirms it, so every later session reads the
confirmed version.

**Won't all those pull requests be a burden?** Each one is small: one fact, or the
decisions from one meeting. The skill has already shown you its findings before it opens the
pull request, so review means reading a few lines and merging.

**Does everyone need to know git?** They need a GitHub account and the ability to review a
pull request in the browser.

**Where does our content go?** Into your own handbook repo, and nowhere else. scripta runs
inside each person's agent with their own connectors. There is no scripta server.

**What isn't done yet?** See [Known issues](docs/reference.md#known-issues--not-yet).

## About

scripta is built by the Hub team at [team.blue](https://team.blue), a European group of 60+
digital-services brands for small businesses, from hosting and domains to website builders
and compliance. The Hub is building one place where those businesses can create and run
their business online, across the group's brands, and scripta is how the team keeps its own
knowledge straight while it does.

## Contributing

scripta started at the Hub and is meant for any team. Issues and pull requests are welcome,
and anything that confused you during install is worth an issue.

## License

Apache 2.0, see [LICENSE](LICENSE). Two files under `skills/curate/` come from the Open
Knowledge Metabolism standard and keep their own MIT notice.

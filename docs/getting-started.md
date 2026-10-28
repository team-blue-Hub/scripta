# Getting started with scripta

scripta keeps your team's handbook up to date. The handbook is a git repo of short pages:
what you decided, who knows what, and where each fact lives. scripta reads your meetings
and chats and turns what is worth keeping into pull requests. A person on your team reviews
and merges every one.

This page takes a team from nothing to its first merged decision.

## What you need

- Claude Code.
- git, and the GitHub CLI signed in (`gh auth login`).
- Python 3, as `python3`. The plugin's hooks call `python3`, so `python3 --version` must
  work, on Windows too.
- A GitHub organization or account where your handbook repo can live.
- At least one teammate, to review and merge what scripta proposes.

Optional:

- **Zoom.** Connect it in your claude.ai connector settings, and the digest finds your
  meetings by itself. Without it, you give the digest a transcript file or paste the text.
- **Linear.** Connect it in your claude.ai connector settings, and add your Linear
  settings to the handbook (see [Settings](#settings)). The digest then also brings
  `status.md` up to date from Linear, and offers to draft task updates. You check both
  before anything is written. Without Linear, everything else works the same.

## 1. Install the plugin

In Claude Code, run:

```
/plugin marketplace add team-blue-Hub/scripta
/plugin install scripta@scripta-plugin
```

Start a new session and type `/scripta`. The skills show up in the menu.

A marketplace added this way does not update itself. To get new versions as they come out,
add this to `~/.claude/settings.json`:

```json
{ "extraKnownMarketplaces": {
    "scripta-plugin": { "source": { "source": "github", "repo": "team-blue-Hub/scripta" },
                        "autoUpdate": true } } }
```

## 2. Make your handbook

Run:

```
/scripta:setup
```

Tell it your team has no handbook yet. It asks for:

- your team's name,
- who owns the first pages (full name and GitHub handle),
- the folder (it suggests `~/PROJECTS/<team>-scripta-handbook`),
- whether your team uses Linear, and if so, the workspace, the team and a label.

Setup writes an empty handbook into that folder and makes the first commit. Then it offers
to create a private repo on GitHub and push to it. Say yes: the skills open pull requests
against that repo, so a handbook that is only on your machine cannot take a digest. One step
is yours: protect `main` in
the repo's settings on GitHub, so every change goes through a pull request. (GitHub's free
plans allow this on public repos only. On a free plan with a private repo, skip this step: the
handbook's own rules in `AGENTS.md` already say nobody merges their own work.)

The new handbook holds:

| File | What it is for |
|---|---|
| `where-truth-lives.md` | Each kind of fact, and the one place it lives |
| `index.md` | The list of pages |
| `decisions/` | One file per decision, with a template |
| `AGENTS.md` | The rules the skills follow when they write |
| `page-format.md` | How a page is laid out |
| `people/` | Who knows what (optional) |
| `.claude/settings.json` | Turns scripta on for anyone who opens the folder in Claude Code |
| `scripta.json`, `status.md` | Only with Linear: your Linear settings, and a page of what is moving now |

**Already have a handbook?** Run `/scripta:setup` and point it at your checkout. It lists
any files the skills need that are missing, and on your yes, adds them in a pull request.

## 3. Check that it works

Open a new session inside the handbook folder and ask: "what's our source of truth?"

If Claude names your handbook without being told where it is, you are set up. If not, run
`/scripta:setup` again. It skips what is done and fixes what is missing.

## 4. Your first week

Start with the digest. Run it after your next meeting. It opens a draft pull request: read
it, mark it ready, and ask a teammate to review and merge it. The handbook's own rules
(`AGENTS.md`) say nobody merges their own work.

| You want to | Type | You give it | You get |
|---|---|---|---|
| Keep what a meeting decided | `/scripta:daily-digest` | A Zoom meeting, a transcript file, or pasted text | A summary. You pick what to keep, and it goes into one draft pull request for the day. |
| Keep one fact from a chat | "document this", or `/scripta:document` | The fact, from the chat | One small pull request |
| Keep everything from a long session | `/scripta:compound` | Nothing, it reads the chat | A list to pick from, then small pull requests |
| Catch up after time off | `/scripta:catch-up` | When you were away | A one-screen summary. It writes nothing. |
| Find pages that went stale | `/scripta:curate` | Nothing | A list of stale pages, then draft pull requests that ask each owner to check |
| Check that your own pages are still true | `/scripta:hardening-interview` | Your answers to a short interview. It needs your own page in `people/`. | Up to ten questions, then a draft pull request |

Nothing reaches `main` until a person merges it.

Two skills you can skip: `/scripta:weekly-update` is built for one team's weekly report,
and `/scripta:deep-plan` plans code work and does not touch the handbook.

## 5. Bring in your teammates

First, give each teammate access to the handbook repo on GitHub, so they can clone it and
review pull requests. Then each person:

1. Clones the handbook: `git clone https://github.com/<org>/<repo> <folder>`.
2. Installs the plugin (step 1).
3. Runs `/scripta:setup` and points it at the clone.
4. Adds a page about themselves, `people/<first-last>.md`, in a pull request. The shape is in
   `people/README.md`. The digest checks the names it hears in a meeting against these
   pages, and the hardening interview starts from them.

scripta runs with each person's own connectors. Your Zoom sees your meetings, not your
teammates'. The handbook is what you share.

## Settings

**`scripta.json`**, at the handbook root. It is committed, so the whole team shares it.
Setup writes it when it starts a new handbook for a team that uses Linear. For a handbook
you already have, add it by hand:

```json
{ "linear": { "workspace": "<workspace>", "team": "<team name>", "label": "<label>" } }
```

The digest reads that Linear team and uses that label for the tasks it drafts. With no `linear`
here, the digest runs without Linear.

**`~/.config/scripta/config.json`**, on your own machine. Setup writes it:

```json
{ "handbook_path": "/absolute/path/to/your-handbook" }
```

It tells scripta where your checkout is. The `SCRIPTA_HANDBOOK_PATH` environment variable,
when set, wins over it.

## When something goes wrong

- **Claude does not know about your handbook.** Check that `python3 --version` works, then
  run `/scripta:setup` again.
- **New versions do not arrive.** Check the auto-update setting in step 1, or run
  `/plugin update scripta@scripta-plugin`.
- **The digest cannot find your meeting.** Paste the transcript or give it the file. For
  Zoom problems, see [Zoom troubleshooting](reference.md#zoom-troubleshooting-read-before-your-first-digest).

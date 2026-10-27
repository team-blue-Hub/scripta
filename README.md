# scripta

The team second brain, as a Claude Code plugin. Turns meetings and scattered sources into
**reviewable PRs** against your team's handbook repo.

## The model in one paragraph

**Per-user access, shared knowledge.** The plugin runs in *your* Claude Code with *your*
connectors — your Zoom sees your meetings, nobody else's. The output (decisions, tasks,
digests) lands as PRs in the shared handbook repo, where a human merges (document opens ready-for-review because its wording is approved in-session; skills whose output the human has not yet seen still open drafts). Private access
converges into team knowledge at the PR gate. Nothing migrates: docs stay in their repos,
specs stay in Notion, meetings stay in Zoom — the handbook indexes where truth lives and this
plugin keeps that index fresh. (Humans
author, no auto-generated canon, no always-on infra.)

## Install (zero → working, ~5 minutes)

New team, with no handbook yet? Follow [Getting started](docs/getting-started.md) instead.

**1. GitHub CLI, authenticated.** Skip if `gh auth status` already shows you are logged in.

```bash
brew install gh        # macOS; other platforms: https://cli.github.com
gh auth login          # choose GitHub.com → HTTPS → login with browser
```

**2. A local handbook checkout.** Skip if you already have one.

```bash
git clone https://github.com/<your-org>/<your-handbook> ~/PROJECTS/<your-handbook>
```

Any location works: `/scripta:setup` finds it, or asks you once. (At the Hub, the handbook is
`team-blue-Hub/hub-scripta-handbook`.)

**3. The plugin.** Inside Claude Code:

```
/plugin marketplace add team-blue-Hub/scripta
/plugin install scripta@scripta-plugin
```

**4. A deslop skill (optional).** The skills run their new text through a deslop skill when
one is installed, and do a short check of their own when none is. (At the Hub, it comes with
`core@ai-recipes`.)

**5. Verify.** Type `/scripta` in Claude Code — the skills should appear in the slash
menu. Pick `/scripta:daily-digest`; if it offers to find a meeting or asks for a transcript,
you're done. (`python3` is also needed for curate's lint script; every macOS has it.)

**Updating later — turn on auto-updates (recommended).** A marketplace added via
`/plugin marketplace add` does NOT update itself. Declare it in `~/.claude/settings.json` with
`"autoUpdate": true` and it refreshes on every session start:

```json
{ "extraKnownMarketplaces": {
    "scripta-plugin": { "source": { "source": "github", "repo": "team-blue-Hub/scripta" },
                 "autoUpdate": true } } }
```

Manual alternative: `/plugin update scripta@scripta-plugin`, or the "Update now" button
under `/plugin` → Installed.

**Zoom connector (optional).** Connect Zoom in your claude.ai connector settings and
daily-digest pulls transcripts of meetings you attended, by itself. Without it, hand the
skill a transcript file or paste text — same result, one manual step more.

**OpenCode.** The scripta skills also run in OpenCode, but its setup is not covered here yet.
The commands, the agent and the hooks do not work there.

## The skills, and what to type

Ten skills, all under the `scripta:` namespace in the slash menu:

| Skill | Status | What it does |
|---|---|---|
| `setup` | shipped | gets your Claude Code wired to the handbook: clone/locate the repo, folder config, auto-update repair. A team with no handbook gets a new, empty one from the template, and an existing one is checked for the files the skills need. Idempotent — safe to re-run |
| `daily-digest` | shipped | transcript (your Zoom / file / paste) → digest + candidate decisions → **you triage** → draft ADR PRs to the handbook, plus (opt-in) proposed task updates for your task board — matches existing items before proposing new ones, never edits the board itself. Where the handbook's weekly lane is on (the Hub's by default), every run also adds the meeting's confirmed finished work to the week's weekly-update draft PR. Optional on a Mac or Windows PC: a noon schedule opens it at 12:00 on weekdays for your own meetings (see the skill's "Run it every day at noon"). |
| `document` | shipped | saves a verified fact from the current chat into the right handbook page as a small PR, in about 30 seconds |
| `compound` | shipped | the end-of-session sweep as its own command: finds every nugget worth saving in a long session and triages them with you (document's sweep mode as a menu item) |
| `catch-up` | shipped | the returner's briefing: "what did I miss" answered from the decision log and merged changes for your absence window. Read-only |
| `deep-plan` | shipped | the enforced plan → clear → execute flow: plan with full context, write the plan to a file, execute from a fresh session that reads only the plan |
| `curate` | shipped, in use | the declutter step: freshness lint + `last-verified` scan over the handbook → **you triage** → owner-nudge PRs |
| `hardening-interview` | shipped | a short interview (max 10 questions) that re-verifies the pages in your own domain, from the handbook's `people/` map |
| `weekly-update` | shipped | the blocks each digest added to the week's draft PR (the dailies only where a block is missing) plus the fixed number sources → one draft entry for the whole team → **the PMs confirm it in a draft PR** → merging publishes it. Writes to the handbook's `updates/`, never to `status.md` |
| `writing` | shipped | **not a command** — the shared write gate the five handbook-writing skills load before they commit. Four questions per sentence: is this source of truth, does it need saying, is it the fewest words, is it one atom with what the repo already says. Also the single home for the `last-verified` rule, the verbatim-quote boundary, and the deslop handoff |

### A second plugin in this marketplace: `prototype`

`/prototype` (plugin `prototype`) turns a described idea into a self-contained
web page and opens it locally for you to review. When you ask to publish, it opens a PR
to your team's prototypes repo and returns an unguessable GitHub Pages URL. Prototypes are one kind of page it builds; dashboards, screens and
report mocks are equally in scope. It routes on whether the page needs a durable,
linkable URL, not on whether it is product-shaped: a product-shaped page gets the live
styles and the live widget, a design page gets the team's generated token artifact and
no widget, and a genuinely throwaway page nobody links to afterwards goes to a Claude
artifact instead. The prototypes repo is the default destination, not the only one: ask
for the page in your own project and it is built there, styled the same way, with no
repo and no PR. Generic by
design: the target repo comes from the `TB_PROTOTYPES_REPO` env var (`org/name`), set
once per team in a shared `.claude/settings.json`; when it's not set, the skill uses
`<org>/prototypes` for that run if exactly one of your orgs has it, with Pages served
from `main` and push access, else it asks and stops instead of writing anywhere else.
It's a standalone plugin on purpose, not a
skill bundled into the `scripta` pack — generic so any team can adopt
it without company-specific tooling.

Being a separate plugin means it needs its own one-time install: the marketplace clone
auto-updates over time, but that only refreshes plugins already installed, never a
brand-new one that just appeared in the listing. Run `/plugin` in Claude Code, find
"prototype" under the scripta-plugin marketplace, and click Install. After that,
`/prototype` is available and auto-updates like any other installed plugin. Details:
[plugins/prototype/README.md](plugins/prototype/README.md).

### The flow

1. **Day one:** `/scripta:setup` — once.
2. **After a meeting:** `/scripta:daily-digest`. On a Mac or Windows PC, the noon schedule can start it for you each weekday: see the daily-digest skill's "Run it every day at noon".
3. **The moment a fact worth keeping shows up in a chat:** "document this". Don't batch it for later — later forgets.
4. **End of a long working session:** "compound this chat".
5. **Before a big, context-heavy task:** `/scripta:deep-plan`.
6. **Once in a while (a couple of weeks):** `/scripta:curate`, and answer the hardening interview when it pings you.

Document first, curate after: one puts knowledge in, the other keeps the whole true.

Typical prompts:

- `digest today's daily` — after any meeting you attended (Zoom connector), ~30 min after it ends
- `run the digest on this transcript: <path or pasted text>` — no Zoom needed
- `document this` — mid-chat, when a fact is worth keeping; `compound this chat` at the end of a long one
- `curate the handbook` or `check freshness` — the maintenance sweep
- `also propose the task updates` — during a digest run; drafts board updates for the PM to apply, asks you before every write

Every skill stops and shows you its findings before writing anything. Nothing is pushed or merged
without your explicit yes.

## Zoom troubleshooting (read before your first digest)

1. **"No permission" on transcript/summary of a meeting you attended** — the host's
   recording-share settings gate attendee access, and Zoom does NOT update permissions
   when attendees are added to an existing invite. Fix is host-side: tell the host,
   don't work around it.
2. **The meeting's assets come back with no transcript (`has_permission: false`)** — do NOT
   reconnect the connector, it does not help. Zoom switches on your API access to a recording
   when you first open its share link in the browser. Open the `play_url` once, then retry —
   the transcript appears within seconds. If `processing: true`, the recording itself isn't
   ready yet; that clears within the hour, and the click rule applies after.
3. Old meetings from before an invite recreation stay invisible. That's expected;
   ask the host for the transcript file instead.

## The knowledge hooks — relevance-gated, not every session

Two hooks work together:

- `hooks/load_scripta_context.py` (SessionStart) points every session at the handbook
  without loading it: the path, that it's authoritative for team facts only (decisions,
  strategy, org, how-we-work), and that it never outranks the current session's work,
  the code, or the user's own memory. It still runs the freshness `git pull` at most
  every 30 min (`SCRIPTA_HOOK_TTL_MIN`).
- `hooks/load_scripta_on_prompt.py` (UserPromptSubmit) injects the full map pages
  (`index.md` + `where-truth-lives.md`, ~2k tokens) only when the prompt looks like a
  team-fact question, via a conservative trigger match checked before any file or git
  access. Everything else passes through untouched.

Handbook location defaults to `~/PROJECTS/hub-scripta-handbook`, falling back to
`~/PROJECTS/scripta`. To point at a checkout elsewhere, set
`"handbook_path"` in `~/.config/scripta/config.json`, or the `SCRIPTA_HANDBOOK_PATH`
env var (env wins). Every skill looks in the same order as the hooks, and `setup` writes
`handbook_path` for any checkout that is not `~/PROJECTS/hub-scripta-handbook`.

A handbook names its own Linear in `scripta.json` at its root:
`{ "linear": { "workspace": "...", "team": "...", "label": "..." } }`. The daily
digest's task and status lanes use it. Without the file, the Hub's handbook keeps
the Hub's Linear, and any other handbook runs the digest with no Linear.

The same file turns the digest's weekly lane on or off: `{ "weekly": { "enabled": true } }`.
Without it, the lane runs on the Hub's handbook, as before, and is off on any
other handbook, since only the Hub has a weekly update today.

Registration is automatic — both hooks are declared in `hooks/hooks.json`, so they load
wherever `scripta` is enabled (per-project via `enabledPlugins`) and resolve
`${CLAUDE_PLUGIN_ROOT}` at runtime. Nothing to wire by hand, and they survive plugin
updates. Both stay silent where no handbook checkout is found, so a global enable is
harmless. (The commands use `python3`; on Windows you may need `python` or `py -3` instead.)

## Known issues / not yet

- Two attendees digesting the same meeting create duplicate decision PRs — dedup by meeting
  UUID in the ADR Source header is planned; until then the PR reviewer catches it.
- Zoom dual-channel transcripts (two speech models writing garbage twins) are handled;
  orphan garbled lines are reconstructed and explicitly flagged for verification.
- The knowledge hooks are new and not yet measured at scale. Per-prompt injection of every prompt stays off the table
  (measured and rejected); the trigger-gated version above is a different shape
  and has not itself been measured yet.
- Report anything confusing during install as an issue.

## License

Apache 2.0, see [LICENSE](LICENSE). Two files under `skills/curate/` come from the Open
Knowledge Metabolism standard and keep their own MIT notice.

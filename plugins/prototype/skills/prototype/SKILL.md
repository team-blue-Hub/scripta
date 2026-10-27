---
name: prototype
description: One command from idea to shareable page. Turns a described idea, design or dashboard into a self-contained web page, opens it as a local preview to review and iterate on, and only when the user asks publishes it as a PR to the team's prototypes repo, served at an unguessable GitHub Pages URL, or builds it where the user is already working when they ask for that. Use when the user says "/prototype", "prototype this", "make this clickable", "mock this up as a page", or asks for a dashboard, screen, report or design page the team will review and link to. A genuinely throwaway page nobody links to afterwards is better served as a Claude artifact, no repo needed.
---

# prototype

Idea in, preview first, URL when asked. The user describes a thing; this skill
builds it as one self-contained web page and opens it locally for them to look
at and iterate on. Only when they ask does it land the page in the team's
**prototypes repo** via PR and hand back a GitHub Pages link. What it builds
are sketches, not products: no build step, no framework, no production code.

Publishing waits for the ask because a first draft is rarely worth sharing:
when every quick test became a PR, pages still being iterated on sat as open
PRs in the prototypes repo.

That is the default, not the only destination. A user who wants the page in
their own working directory gets it there, styled the same way, with no repo
involved.

Prototypes are one kind of page this skill builds. Dashboards, screens, report
mocks and other design pages are equally in scope.

## Step 0 — route: does this page need the repo?

"Prototype this" hides more than one need, and the deciding question is not
whether the thing is a prototype. It is whether the page needs a durable,
linkable URL of its own.

**Build it here when any of these is true:**

- **It must look like the real product**: live CSS, the live widget loader,
  remote assets. An artifact's sandbox blocks outside scripts; a Pages page
  doesn't.
- **It is a design page the team will review**: a dashboard, a screen, a
  layout, a report mock. It gets linked from Linear, the handbook or Slack and
  read by people who weren't in the chat that made it.
- **It will be iterated on**: the same page changes over days and the URL has
  to stay put.

**Build it where the user is already working** when there is a page of theirs
to work on: they name a path, a project or a file they already have, and want
this skill's styling applied to it. That is the whole test. It exists because
applying the team's tokens to a page is useful on its own, and a page someone
is already building in their own repo does not become the prototypes repo's to
hold.

Two things are not this signal, and both look like it:

- **Not wanting to share it.** A page nobody will link to and that does not
  exist yet is the artifact case, and it stays the artifact case. "Nobody else
  needs to see it" says nothing about where the page lives.
- **Step 1 failing to resolve a repo.** That is ask-and-stop, unchanged. This
  route is chosen because the user pointed at their own work, never because the
  prototypes repo was unavailable.

**Route to a Claude artifact and stop** only when the page is genuinely
throwaway: one look, one person, nothing links to it afterwards, no live
assets.

When in doubt, build it here. A page in the repo costs a folder; a page lost in
a chat costs the work. And never turn a page away for not being a prototype.
That is not what this skill is gated on.

## Step 1 — resolve the target repo (ask-and-stop, never scatter)

Skip this step entirely when Step 0 routed to build-in-place. There is no repo
to resolve: the page belongs to the user, at the path they named.

**Run it only when the user asks to publish (Step 3).** Building and previewing
need no repo, so a page that is never published never resolves one. It sits
here, before the build, because it decides where a published page goes; it
does not run first.

The target repo comes from the env var **`TB_PROTOTYPES_REPO`** (`org/name`,
e.g. `team-blue-Hub/prototypes`). Teams set it once in a shared
`.claude/settings.json` (`"env"` block); individuals can set it in
`~/.claude/settings.json`.

- **Set and the repo exists** → proceed.
- **Not set** → discover it before asking, for this run only. Nothing is
  written to any settings file: the lookup is cheap, so it runs again next
  time. The candidates are `<org>/prototypes` for each org the user belongs
  to (`gh api user/orgs --jq '.[].login'`), never the git remote's owner, so
  a fork or a personal account cannot win. A candidate qualifies only when
  both hold:
  - `gh api repos/<org>/prototypes/pages` returns 200 with `source.branch`
    `main` and `source.path` `/`. Step 4 merges to `main`, so a site served
    from `gh-pages` or a workflow would 404 the link.
  - `gh api repos/<org>/prototypes --jq .permissions.push` is `true`, so a
    read-only repo fails here and not at Step 4.

  Exactly one qualifies → treat it as `TB_PROTOTYPES_REPO` for the rest of
  this run, say so in one line with the settings snippet that pins it, and
  proceed. None, or more than one → fall through to ask-and-stop, listing
  the qualifying repos when there are several.
- **Still unresolved, the repo doesn't exist, or the runner can't create
  it** → STOP and ask. Show the user exactly two things: the settings
  snippet to paste, and (if the repo is missing) the `gh repo create`
  command you propose to run, then wait for their yes. No fallback — never
  another repo, a gist, or a local folder. Falling back scatters pages and
  breaks "one repo per team". Using the one qualifying team repo above is
  discovery, not scattering; creating a new one, or pinning the env var,
  still always needs the user's explicit yes.
- On first-time repo creation (after the yes): create it **private** — the
  published Pages site is still world-readable on most GitHub plans (confirm yours), but a private repo keeps the source
  and the page list unenumerable. Then enable Pages from `main`, root:
  `gh api -X POST repos/<org>/<name>/pages -f 'source[branch]=main' -f 'source[path]=/'`
  (409 = Pages already enabled — fine, move on).

## Step 2 — build the page

1. Work out what to build from the user's words and anything they attached
   (screenshot, Figma export, an existing page). If the core interaction is
   ambiguous, ask ONE question, not a questionnaire.
2. One folder per page, named **unguessably**: `<slug>-<random>` where
   `<random>` is 12+ hex chars (`openssl rand -hex 6`). The public URL is only
   as private as its path — a guessable name defeats the whole arrangement.
   The random name is only for pages headed to the prototypes repo; a
   build-in-place page goes at the path the user named. Name it now, before
   the preview, and keep the name when it is published: the preview folder is
   the folder that ships. Build it under
   `~/.claude/.tb-prototypes/previews/<folder>/`.
3. The folder holds a single **self-contained `index.html`** — inline CSS and
   JS, no CDN libraries, no build step. Assets it truly needs sit beside it in
   the same folder. Keep it responsive; it will be opened from a phone.
4. **Never invent brand styling.** Take it from the right place for the kind
   of page. This is the same wherever the page lands, and it is the whole
   value of the build-in-place route: the tokens are the point, the repo was
   never the point.
   - **Product-shaped page** → load what the team already serves live: the live
     widget loader (the exact loader line is in ai-recipes
     `skills/widget-verification/brand-activation/SKILL.md`) and the published
     storybook.
   - **Design page** (dashboard, screen, report) → these usually have no widget
     on them, and bolting one on is wrong. Take the styling from the team's
     generated token artifact instead, and load no widget. For the Hub that is
     `hub-design-tokens`, whose GitHub Release assets (`library.css`,
     `tokens.json`) are the generated values; inline the ones the page uses,
     and say in the PR body which version tag they came from. The handbook's
     `engineering/design-tokens.md` explains the pipeline and names this skill
     as one of its consumers.
   - **Neither reference exists** → clean neutral styling. Inventing a brand
     look is the one thing never to do.
5. A dashboard or report is only as good as the numbers on it, and the numbers
   here are always fake. Make that visible on the page itself with a small
   "sample data" marker, so a screenshot of it can't be mistaken for a real
   readout.

## Step 3 — preview locally, publish only when asked

1. Open the page for the user: `open <folder>/index.html` on macOS,
   `xdg-open` on Linux, `start` on Windows. Also give its `file://` link with
   the full absolute path, which is the fallback when the opener fails.
2. When the page loads remote scripts that refuse `file://` (the live widget
   loader, module scripts, `fetch`), serve the folder instead and open that:
   `python3 -u -m http.server 0 --bind 127.0.0.1 --directory <folder>`. Port
   `0` makes the OS pick a free port, which the server prints ("Serving HTTP
   on 127.0.0.1 port <port>"), so two sessions never share one. Binding to
   `127.0.0.1` keeps the draft off the network. Keep the server running until
   the user publishes or moves on, then stop it.
3. Iterate here. "Change the button", "make it dark" → edit the same preview
   folder and reopen it. Nothing is cloned, branched, committed or pushed
   while the page is a preview.
4. Publish only when the user asks: "publish it", "open the PR", "give me the
   link", "share it". When the original request explicitly asked for the link,
   the PR, to publish or to share, that is the ask: open the preview, then
   publish in the same run without waiting. Asking for a page "for the team to
   review" is not an explicit ask. Otherwise, for a page headed for the
   prototypes repo, end the preview turn by saying the page is not published
   yet and that asking to publish ships it. A build-in-place page says where
   the file is and nothing about publishing (Step 4).

## Step 4 — ship it as a PR

**Build-in-place stops before this step.** Write the page at the path the user
named, open the preview (Step 3), tell them where it is, and stop. Never
clone, never branch, never commit, never push, and never open a PR in a repo of
theirs: what they do with the file is theirs to decide. If they later want the
durable URL after all, the page is one copy away from the normal flow.

1. Resolve the repo (Step 1). Clone or pull it into
   `~/.claude/.tb-prototypes/<name>` (shallow clone is fine; this cache dir,
   previews included, is the skill's only workspace).
2. Copy the preview folder into the clone unchanged, under its existing name.
   Branch (`prototype/<slug>`), add the folder, commit (`prototype: <slug>`),
   push the branch, open a PR with a one-paragraph body: what the page is for
   and the Pages URL it will get. The PR is the share point and the paper
   trail; merging is one click by any teammate (or the runner, since these are
   sketches, so self-merge is fine if the team allows it).
3. Tell the user, in one short message:
   - the PR link
   - the Pages URL it serves after merge:
     `https://<org>.github.io/<name>/<folder>/`
   - that Pages takes a minute or two after merge before the URL is live.

## Step 5 — iterate in place

After publishing, "change the button", "make it dark" → edit the SAME folder in
the clone (new PR or push to the open one), not the old preview folder, which
is no longer the copy to edit; the URL stays stable. Preview the edit from the
clone before pushing it, as in Step 3. A build-in-place page is edited in
place the same way, at the path it already has. A genuinely different idea
gets a new folder. Never edit someone else's folder unless the user
explicitly asks.

## Guardrails

- **Nothing is published before the user asks.** No clone, branch, commit,
  push or PR until they ask to publish, up front or after the preview
  (Step 3).
- The ONLY repo this skill ever writes to is `TB_PROTOTYPES_REPO`, or the one
  repo Step 1 discovered for this run. Unset → try that discovery first,
  and never write a settings file; still unresolved, or
  unreachable → ask and stop. Build-in-place is not an exception to this: it
  writes a file where the user asked and never runs a git command, so nothing
  is committed to any repo by this skill.
- **No index page on the published site, ever** — a browsable index would
  enumerate every page and defeat the unguessable names. If the team wants a
  catalog, it lives in the private repo's README.
- Pages may contain fake data only — never real customer data, secrets,
  tokens, or anything from production. This bites hardest on dashboards and
  reports, where real figures are exactly what makes the mock feel convincing.
  If the user pastes real data for realism, replace it with lookalike fake
  values and say so.
- This is not a deploy tool: no custom domains, no DNS, no S3/CloudFront, no
  external hosting. GitHub Pages or nothing.
- Never treat any of this as production-ready, and say so if someone proposes
  shipping one as-is.

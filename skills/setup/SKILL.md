---
name: setup
description: Get a team member's Claude Code fully set up for the team handbook, and repair the auto-update binding while you're at it. Does the scriptable parts — clone, locate or start the handbook, check it for missing files, write the folder config, fix the scripta-plugin auto-update mismatch, verify the SessionStart hook fires — and hands off the plugin install/enable clicks that only the Manage Plugins UI can do. Use when someone says "set me up", "finish my scripta setup", "onboard my Claude Code", "/setup", when their handbook context isn't loading, or when a team wants to start its own handbook. Idempotent and safe to re-run; the doc version of this checklist is onboarding/setup.md in the handbook.
---

# setup

One loop: **finish the parts a machine can do, name the two clicks it can't.**
Idempotent — safe to re-run any time; each step skips what's already done. Everything
here is local to the runner's machine, except two steps that run only on the runner's yes:
putting a new handbook on GitHub (Step 1b) and a pull request that adds missing files (Step 1c).

## What this can and can't do

- **Can (scripted here):** locate or clone the handbook, start a new one from the
  template, check one for missing files, set the folder config, repair the auto-update
  binding, run the hook to verify context loads.
- **Can't (UI only):** adding the marketplace and installing/enabling the `scripta`
  plugin happen in Manage Plugins — there is no command for it. This skill tells the
  runner exactly what to click; it does not pretend to do it.

Mirror of the human checklist: `onboarding/setup.md` in the handbook. The Hub's copy is linked
under "The Hub's defaults" below.

## Step 1 — the handbook checkout

The hook reads a local clone. Look for one in the order the hook uses: the folder in
`SCRIPTA_HANDBOOK_PATH` if it is set, otherwise `handbook_path` in
`~/.config/scripta/config.json` if it is set, otherwise `~/PROJECTS/hub-scripta-handbook`,
then `~/PROJECTS/scripta`. A folder counts when it has
`where-truth-lives.md`. A set `SCRIPTA_HANDBOOK_PATH` or `handbook_path` is used alone: when that folder is not a handbook, ask, and never fall back to the `~/PROJECTS` folders. The hook already did this at session start: when its note says
"A team handbook exists at `<path>`", use that path. If the team has no handbook yet, start
one with Step 1b instead of cloning.

1. One of them is a handbook → use it.
2. None is → ask the runner which handbook repo to clone and where to put it (default
   `~/PROJECTS/<repo name>`). For a Hub member, offer the Hub's repo from "The Hub's
   defaults" below as the default. Then clone it:
   `git clone https://github.com/<owner>/<repo> <path>`.
3. When the checkout is anywhere other than `~/PROJECTS/hub-scripta-handbook`, write its
   path to the folder config (Step 1a), even when it sits under `~/PROJECTS` with another
   name. The hook and the skills only look in `~/PROJECTS/hub-scripta-handbook` and
   `~/PROJECTS/scripta` by themselves.

### Step 1a — folder config (for any checkout not at ~/PROJECTS/hub-scripta-handbook)

Write `~/.config/scripta/config.json` with the checkout's absolute path:
```json
{ "handbook_path": "/absolute/path/to/the-handbook" }
```
The hook's precedence is env var → this file → the `~/PROJECTS` defaults, so this is the
clean alternative to a `SCRIPTA_HANDBOOK_PATH` env var or a symlink.

### Step 1b — start a new handbook (only when the team has none)

`scripts/handbook_files.py` (next to this file) writes an empty handbook from `template/`:
the registry, the index, the decision log with its template, the rules the skills cite,
the page format, a people folder, and the settings that turn the plugin on in the repo.

1. Ask the runner for the team's name, who owns the starting pages (their full name and
   GitHub handle), and the folder (default `~/PROJECTS/<team>-scripta-handbook`). Ask
   whether the team keeps its tasks in Linear; only on a yes, ask for the workspace, the
   team and the label the digest should use.
2. Create it:
   ```
   python3 "<this skill dir>/scripts/handbook_files.py" create <folder> --team "<team>" --owner "<Full Name> (@<handle>)"
   ```
   With Linear, add `--linear-workspace <w> --linear-team "<team>" --linear-label <label>`:
   that writes `scripta.json` and a `status.md` for the digest's status lane. Without it, the
   digest runs with Linear off. The script never overwrites a file and refuses a folder that
   holds other files; on a refusal, ask for another folder.
3. Make it a git repo with a first commit, all local. The folder is already a clone when
   `git -C <folder> rev-parse --show-toplevel` prints the folder itself; otherwise run
   `git -C <folder> init -b main`, even when the folder sits inside another repo. Then
   `git -C <folder> add -A` and `git -C <folder> commit -m "Start the <team> handbook"`.
4. GitHub, only on the runner's yes. When the folder is a clone, it already has its repo:
   show `git -C <folder> push origin main` instead. Otherwise show
   `gh repo create <org>/<team>-scripta-handbook --private --source <folder> --push` and ask
   for the org. Run it once they say yes. Then tell them to protect `main` in the repo's
   settings, so every change goes through a pull request as the new `AGENTS.md` asks. That
   click is theirs.
5. Write the folder config (Step 1a): the new folder is not `~/PROJECTS/hub-scripta-handbook`.
   When `~/.config/scripta/config.json` already names another handbook, show it and ask
   before replacing it: every session on this machine follows that one line.

### Step 1c — check the handbook for missing files

```
python3 "<this skill dir>/scripts/handbook_files.py" check <folder>
```
It writes nothing and lists each file the skills need as ok, missing or broken. Exit 0: go
on. Exit 1: show the runner those lines. A `broken` line (a link to nothing, a folder where a
file belongs, or a `scripta.json` that is not a JSON object) is the runner's to fix by hand
first, so stop there: `create` refuses while one is broken. Otherwise, on the runner's yes,
add the missing files on a branch from the latest `main`, never on `main` itself:

1. Look first: `git -C <folder> status --porcelain` must print nothing and
   `git -C <folder> branch --show-current` must print `main`. If either is off, stop and show
   the runner what it printed; never switch away from uncommitted changes. A
   `scripta-setup-files-*` branch means an earlier run stopped before its last step: ask
   whether to go on with that branch or switch back to `main`. Then
   `git -C <folder> fetch origin main` and
   `git -C <folder> switch -C scripta-setup-files-<YYYY-MM-DD> origin/main`, with today's date,
   so a branch an earlier setup pull request left behind never collides with this one.
2. The Step 1b `create` command for that folder, with `--team` and `--owner` (ask the runner
   for them). It adds only what is missing and prints each file it created.
3. `git -C <folder> add` with only the paths `create` printed as created, then
   `git -C <folder> commit -m "Add the files scripta needs" -- <those paths>`, so nothing
   else staged rides along.
4. Show the push (`git -C <folder> push -u origin scripta-setup-files-<YYYY-MM-DD>`) and the
   draft pull request commands, and run them on the runner's yes. A rejected push means a
   branch of that name is already on the remote, from a setup run earlier today: stop, show
   the runner the error and the branch, and never force-push.
5. `git -C <folder> switch main`, so the checkout the hook pulls stays on `main`. Do this on
   every way out of steps 1 to 4, a refusal, a rejected push or a no included.

A `people/README.md` marked "good to have" is optional; the skills skip it cleanly.

## Step 2 — repair the auto-update binding

Run the shipped script (next to this file):
```
python3 "<this skill dir>/scripts/repair_autoupdate.py"
```
It fixes a silent bug: some configs declare
`autoUpdate: true` on a marketplace key named `scripta` that does not match the installed
`scripta-plugin`. The flag binds to nothing and new plugin versions never auto-update.
The script renames the stale key and ensures `autoUpdate` is on. Idempotent — it prints
"already correct" and changes nothing when the binding is fine. Its change takes effect
on the next full Claude Code relaunch.

## Step 3 — verify the hook fires

Run the installed SessionStart hook directly and confirm it emits the map pages:
```
echo '{"hook_event_name":"SessionStart"}' | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/load_scripta_context.py"
```
Expect JSON whose `hookSpecificOutput.additionalContext` starts with "A team handbook exists
at `<the handbook path>`". It is a short pointer: the maps themselves (`index.md`,
`where-truth-lives.md`) load later, when a prompt asks a team-fact question. Empty output
means no checkout was found — recheck Step 1.

## Step 4 — the two clicks only the UI can do

Tell the runner (do not claim to do it):

1. **Manage Plugins → Marketplaces →** if `scripta-plugin` isn't listed, **Add**
   `team-blue-Hub/scripta`. If it is listed, hit **↻ refresh** so it picks up the latest.
2. **Plugins tab → Install / enable `scripta`.** In the handbook repo it enables
   itself (the repo's `.claude/settings.json` lists it); for other projects, enable
   `scripta@scripta-plugin` there.

## Step 5 — confirm end to end

Have the runner open a **new** session in the handbook folder and ask
"what's our source of truth?". If it names the handbook on its own — without being
pointed at it — setup is done. If not, recheck Steps 1 (checkout) and 4 (plugin enabled).

## The Hub's defaults

The Hub's own values, for a Hub member. Another team uses its own and skips this section.

- Handbook repo: `team-blue-Hub/hub-scripta-handbook`.
- Human checklist: [`onboarding/setup.md`](https://github.com/team-blue-Hub/hub-scripta-handbook/blob/main/onboarding/setup.md).

## Guardrails

- Idempotent: re-running never double-applies. Report what changed and what was already fine.
- Local by default: this configures the runner's machine. The only team-visible writes are
  a new handbook's GitHub repo (Step 1b) and a pull request adding missing files (Step 1c),
  and each runs only after the runner says yes to the exact command.
- Never fabricate success: if the hook output is empty or the plugin isn't enabled, say so
  and point at the step to fix, rather than reporting "done".

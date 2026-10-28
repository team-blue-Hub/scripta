# scripta in OpenCode

The scripta skills load in [OpenCode](https://opencode.ai). Verified on OpenCode 1.18.16
(macOS) on 2026-08-10. OpenCode v2 is a separate package and has not been checked yet.

## What works, and what does not

- **Works:** every skill loads, `/prototype` included. You call them by name.
- **Does not work:** the hooks, the slash commands and the agent. Without the hooks, no
  session knows about your handbook until you tell it (see step 3).
- **Does less:** the daily digest cannot find your Zoom meetings, because OpenCode does not
  have your claude.ai connectors: give it a transcript. `setup` repairs Claude Code's plugin
  settings and checks its hooks, which mean nothing here. `deep-plan` expects Claude Code's
  fresh-session flow.

## 1. Check out the repo

OpenCode does not read Claude Code's plugin folder (`~/.claude/plugins`), so a marketplace
install is invisible to it. It needs a real clone:

```bash
git clone https://github.com/team-blue-Hub/scripta.git ~/PROJECTS/scripta
```

Any folder works; adjust the path in step 2. OpenCode reads the working tree, so `git pull`
is the update.

## 2. Point OpenCode at it

In `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "skills": {
    "paths": ["~/PROJECTS/scripta"]
  }
}
```

Point `paths` at the repo root, not at `skills/`. OpenCode looks for `**/SKILL.md` at any
depth, and `/prototype` lives under `plugins/prototype/`, so pointing at `skills/` drops it.

The same scan also reaches into `node_modules`. If a dependency there ships its own
`SKILL.md`, it loads as if it were yours. Deny it by name under `permission.skill` in the
same file.

## 3. Point the session at your handbook

Start the session with "use the handbook at `<path to your handbook>` as reference". The
handbook's `AGENTS.md`, `index.md` and `where-truth-lives.md` tell the agent the rest.

OpenCode asks before it reads outside the project folder (`external_directory` defaults to
`ask`), so it will ask to read the handbook: allow it. `opencode run` has no one to ask, and on
1.18.16 it refuses the read.

## 4. Check

Ask OpenCode to run the daily digest. If it asks for a transcript, the skills are loaded.

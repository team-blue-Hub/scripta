# prototype

One command from idea to shareable page. `/prototype` builds a described idea as a
self-contained web page, opens a PR to your team's prototypes repo, and hands back an
unguessable GitHub Pages URL.

Prototypes are one kind of page it builds. Dashboards, screens, report mocks and other
design pages are equally in scope: the skill routes on whether the page needs a durable,
linkable URL, not on whether it is product-shaped. A product-shaped page gets the live
widget and live styles; a design page gets the team's design reference and shared tokens
and no widget. A genuinely throwaway page nobody links to afterwards doesn't need this,
since a Claude artifact already renders and shares those.

The prototypes repo is the default destination, not the only one. Say you want the page
in your own project ("not in the prototypes repo", "just apply the tokens to this") and
it gets built at the path you name, styled the same way, with no clone, no PR and no
Pages URL. The skill writes the file and stops there; committing it is yours to decide.

## A separate plugin, not part of the scripta pack

`prototype` ships as its own standalone plugin in the scripta marketplace. It is not a
skill bundled into the `scripta` pack. That's on
purpose: keeping it generic means any team can install it without
pulling in team-specific tooling.

## Install

The scripta marketplace clone updates itself over time, but that auto-update only
refreshes plugins you already have installed. It never installs a brand-new plugin
that just showed up in the marketplace listing. So `prototype` needs one manual step,
once:

1. Run `/plugin` in Claude Code.
2. Find "prototype" under the scripta-plugin marketplace.
3. Click Install.

After that one-time step, `/prototype` is available, and it auto-updates like any
other installed plugin from then on.

## First run

The first time you run `/prototype`, it looks for your team's prototypes repo (the
`TB_PROTOTYPES_REPO` env var, `org/name`). If it isn't set, it checks
`<org>/prototypes` in each GitHub org you belong to. If exactly one exists with
GitHub Pages served from `main` and you can push to it, that run uses it and tells
you so in one line; nothing is saved. Otherwise it asks and stops. Set the env var
once in a shared `.claude/settings.json` to skip the lookup.

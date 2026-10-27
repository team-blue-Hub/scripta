# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then grows as new terms come up; direct edits are fine. Glossary only, not a spec or catch-all.

## Meeting digestion

### Digest
The structured summary the daily-digest skill produces from one meeting transcript — topics, candidate decisions with verbatim evidence, per-person tasks, and open questions — which a human triages before anything becomes team-visible.

### Transcript shape
The schema variant a Zoom connector version uses to deliver a meeting transcript: which container holds the transcript items and which fields each item carries. Shapes drift between connector versions without announcement, so the runner detects the shape by checking known container paths in a documented order (newest first, older shapes as fallback) instead of assuming one.

### No-access stub
The connector response signalling the runner has no API access to a recording: a negative permission flag together with no transcript present at any known transcript shape's location. Absence of a single expected path is never the stub by itself — that can equally mean a new transcript shape. The same compound-evidence discipline governs the reference error classes in handbook curation: one ambiguous signal never becomes a confident diagnosis.

### Click-to-unlock model
The working hypothesis that Zoom switches on a user's API access to a recording the first time that user opens the recording's share link in a signed-in browser. Unconfirmed: one trial supports it, one later observation contradicts it.

### Dual-channel transcript
A Zoom transcript in which two speech models' outputs are interleaved: each utterance appears twice at the same timestamp, one clean and one phonetic garbage. Cleanup pairs the twins by timestamp and speaker (resolved per the active transcript shape) and keeps the cleaner line.

### Differential test
The acquisition discipline of fetching assets for a meeting that was already digested successfully before diagnosing a fresh meeting's failure. If the old meeting's transcript still fetches, the connection is healthy and the problem is specific to the new recording — access or transcript shape — not authentication.

### Noon schedule
The opt-in launchd job that opens the daily digest in a visible Terminal window at 12:00 on weekdays, for the meetings one person attends, unless all of them are already in today's digest. A person still runs and triages the digest in that window; the digest's steps do not change.

### Handbook settings
`scripta.json` at the root of a handbook: what that handbook is connected to, committed with it so it is the same for everyone on the team. Today it holds `linear` (workspace, team and label) for the daily digest's task and status lanes, and `weekly` (`enabled`) for its weekly lane. Where the handbook sits on one machine is not in it: that is `handbook_path` in `~/.config/scripta/config.json`.

## Handbook curation

### Reference error classes
How the reachability check names a failed handbook citation: `no-access` (the runner's credentials cannot read it), `gone` (the target no longer exists — requires compound evidence, never a single 404, because GitHub answers 404 for both private and deleted), `transient` (timeout, rate limit, 5xx — retried once, reported, never a run-failure by itself), and `unknown` (mixed or unsafe evidence, said out loud instead of guessed). Classes gate the remedy: grant, fix the citation, retry, or investigate.

### Skipped-by-design
A reference declared expected-unreachable in the handbook's `.references.json` (SSO dashboards, per-person shares). The check reports it with its declared reason instead of counting it as a failure — never silently omitted, so a reader can always tell "verified" from "declared out of reach". `per-user` entries are still probed; only their failures downgrade.

### Needs-agent-result row
A connector-only citation (Notion, Zoom, Confluence, Slack) the checker script cannot probe: it emits the row with an empty result and the curate run must fill it through the runner's connectors. `reference_check.py --verify` refuses success while any such row is unfilled — closure is enforced by the script, not by agent diligence.

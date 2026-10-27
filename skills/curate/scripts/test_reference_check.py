#!/usr/bin/env python3
"""Unit tests for reference_check.py.

No framework, no fixtures beyond tempfile - stdlib unittest only, same bar as
freshness_lint.py's own test discipline. All network (probe_http) and
subprocess (run_gh) calls are monkeypatched; nothing here touches a real
socket or spawns a real `gh` process except the two dedicated safety tests
that exercise the real probe_http with only socket.getaddrinfo / _open_url
monkeypatched (KTD12 proof).

Run: python3 skills/curate/scripts/test_reference_check.py
"""
from __future__ import annotations

import io
import json
import socket
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))
import reference_check as rc  # noqa: E402


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def run_main(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = rc.main(["reference_check.py"] + argv)
    return code, out.getvalue(), err.getvalue()


class FakeGh:
    """Programmable stand-in for run_gh, keyed by the gh subcommand shape."""

    def __init__(self, auth_ok=True, login="tester", endpoints=None):
        self.auth_ok = auth_ok
        self.login = login
        self.endpoints = endpoints or {}
        self.calls: list[list[str]] = []

    def __call__(self, args, timeout=rc.DEFAULT_TIMEOUT):
        self.calls.append(list(args))
        if args[:2] == ["api", "user"]:
            if not self.auth_ok:
                return {"returncode": 1, "stdout": "", "stderr": "gh: not logged in"}
            return {"returncode": 0, "stdout": json.dumps({"login": self.login}), "stderr": ""}
        if args[0] == "api":
            endpoint = args[-1]
            spec = self.endpoints.get(endpoint, {"status": 200})
            status = spec["status"]
            if status == 200:
                return {"returncode": 0, "stdout": "{}", "stderr": ""}
            return {"returncode": 1, "stdout": "", "stderr": f"gh: some error (HTTP {status})"}
        raise AssertionError(f"unexpected gh args: {args}")


class RouteTarget(unittest.TestCase):
    def test_sso_host_without_allowlist_is_error_never_probed(self):
        routing = rc.route_target("https://linear.app/team/issue/1", [], rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "sso-error")

    def test_sso_host_with_allowlist_skips(self):
        allow = [{"match": "linear.app", "class": "sso", "reason": "sso-gated dashboard"}]
        routing = rc.route_target("https://linear.app/team/issue/1", allow, rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "skip")
        self.assertEqual(routing.text, "sso-gated dashboard")

    def test_connector_only_without_allowlist_needs_agent(self):
        routing = rc.route_target("https://notion.so/some-page", [], rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "needs-agent")

    def test_github_repo_url_routes_to_probe_github(self):
        routing = rc.route_target("https://github.com/octo/hello", [], rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "probe-github")
        self.assertEqual(routing.github_info["endpoint"], "/repos/octo/hello")

    def test_plain_web_routes_to_probe_plain(self):
        routing = rc.route_target("https://example.com/page", [], rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "probe-plain")

    def test_unmappable_github_url_is_unknown_never_probed(self):
        routing = rc.route_target("https://github.com/octo/hello/actions", [], rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "unknown")

    def test_unsupported_scheme_is_unknown(self):
        routing = rc.route_target("ftp://example.com/f", [], rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "unknown")

    def test_allowlisted_probeable_target_skips_before_probing(self):
        allow = [{"match": "https://example.com/dead", "class": "other", "reason": "retired page"}]
        routing = rc.route_target("https://example.com/dead", allow, rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "skip")

    def test_per_user_allowlist_still_routes_to_probe(self):
        allow = [{"match": "example.com", "class": "per-user", "reason": "personal doc"}]
        routing = rc.route_target("https://example.com/doc", allow, rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "probe-plain")

    def test_slack_host_routes_to_needs_agent_not_plain_web(self):
        # F3: SKILL.md/CONCEPTS.md promise Slack is connector-only, but the
        # default host set never listed it - a cited Slack URL used to be
        # anonymously plain-web probed instead.
        routing = rc.route_target("https://example.slack.com/archives/C1/p123", [],
                                   rc.DEFAULT_SSO_HOSTS, rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "needs-agent")

    def test_allowlisted_mailto_url_routes_to_skip_not_unknown(self):
        # F10: a non-http(s) scheme used to be rejected before the allowlist
        # was even consulted, so "allowlist it" silently did nothing for it.
        allow = [{"match": "mailto:security@example.com", "class": "other",
                  "reason": "contact address, not a live page"}]
        routing = rc.route_target("mailto:security@example.com", allow, rc.DEFAULT_SSO_HOSTS,
                                   rc.DEFAULT_CONNECTOR_HOSTS)
        self.assertEqual(routing.action, "skip")


class GithubUrlMapping(unittest.TestCase):
    def test_repo_url(self):
        info = rc.parse_github_target("https://github.com/octo/hello")
        self.assertEqual(info["endpoint"], "/repos/octo/hello")
        self.assertEqual(info["kind"], "repo")

    def test_blob_url_maps_to_contents(self):
        info = rc.parse_github_target("https://github.com/octo/hello/blob/main/docs/x.md")
        self.assertEqual(info["endpoint"], "/repos/octo/hello/contents/docs/x.md?ref=main")
        self.assertEqual(info["kind"], "contents")

    def test_tree_url_maps_to_contents(self):
        info = rc.parse_github_target("https://github.com/octo/hello/tree/main/docs")
        self.assertEqual(info["endpoint"], "/repos/octo/hello/contents/docs?ref=main")

    def test_blob_url_offers_every_ref_cut_shortest_first(self):
        # A branch called `document/2026-08-24-x` is indistinguishable from ref
        # `document` plus a path starting `2026-08-24-x/`, so both cuts are on
        # offer and the shortest stays primary.
        info = rc.parse_github_target(
            "https://github.com/octo/hello/blob/document/2026-08-24-x/docs/x.md")
        self.assertEqual([s["ref"] for s in info["splits"]],
                         ["document", "document/2026-08-24-x", "document/2026-08-24-x/docs"])
        self.assertEqual(info["endpoint"], info["splits"][0]["endpoint"])
        self.assertEqual(info["splits"][1]["endpoint"],
                         "/repos/octo/hello/contents/docs/x.md?ref=document/2026-08-24-x")

    def test_ref_cuts_stop_before_swallowing_the_whole_path(self):
        # The last segment is the file, so it is never offered as part of a ref.
        info = rc.parse_github_target("https://github.com/octo/hello/blob/main/docs/x.md")
        self.assertEqual([s["ref"] for s in info["splits"]], ["main", "main/docs"])

    def test_ref_cuts_are_capped(self):
        info = rc.parse_github_target(
            "https://github.com/octo/hello/blob/a/b/c/d/e/f/x.md")
        self.assertEqual(len(info["splits"]), rc.MAX_REF_SEGMENTS)

    def test_an_unsafe_segment_ends_the_walk_but_keeps_the_shorter_cuts(self):
        # `my%20docs` cannot be part of a ref (the owner/repo/ref charset has no
        # `%`) but is a legal path segment. The walk ends there rather than
        # skipping it: a later cut would otherwise offer `main/my%20docs/sub`,
        # a ref built over a segment already rejected. The cut collected before
        # it survives, so the URL is still probed instead of dropped.
        info = rc.parse_github_target(
            "https://github.com/octo/hello/blob/main/my%20docs/sub/x.md")
        self.assertEqual([s["ref"] for s in info["splits"]], ["main"])
        self.assertEqual(info["endpoint"],
                         "/repos/octo/hello/contents/my%20docs/sub/x.md?ref=main")

    def test_blob_url_without_a_path_has_one_cut(self):
        info = rc.parse_github_target("https://github.com/octo/hello/tree/main")
        self.assertEqual([s["ref"] for s in info["splits"]], ["main"])
        self.assertEqual(info["endpoint"], "/repos/octo/hello/contents/?ref=main")

    def test_issue_and_pull_map_to_issues_endpoint(self):
        i1 = rc.parse_github_target("https://github.com/octo/hello/issues/42")
        i2 = rc.parse_github_target("https://github.com/octo/hello/pull/42")
        self.assertEqual(i1["endpoint"], "/repos/octo/hello/issues/42")
        self.assertEqual(i2["endpoint"], "/repos/octo/hello/issues/42")

    def test_unsafe_owner_repo_chars_unmappable(self):
        self.assertIsNone(rc.parse_github_target("https://github.com/oc%to/hello"))

    def test_path_with_leading_dash_unmappable(self):
        self.assertIsNone(rc.parse_github_target("https://github.com/octo/hello/blob/main/-x"))

    def test_dot_dot_segment_unmappable(self):
        # F13(a): OWNER_REPO_CHARS allows "." so ".."  used to pass the
        # regex untouched in any owner/repo/ref position.
        self.assertIsNone(rc.parse_github_target("https://github.com/../hello"))
        self.assertIsNone(rc.parse_github_target("https://github.com/octo/.."))
        self.assertIsNone(rc.parse_github_target("https://github.com/octo/hello/blob/../x"))
        self.assertIsNone(rc.parse_github_target("https://github.com/.."))

    def test_non_github_host_is_none(self):
        self.assertIsNone(rc.parse_github_target("https://example.com/octo/hello"))

    def test_root_unmappable_but_profile_maps(self):
        self.assertIsNone(rc.parse_github_target("https://github.com/"))
        info = rc.parse_github_target("https://github.com/octo")
        self.assertEqual(info["kind"], "profile")


class ClassifyHost(unittest.TestCase):
    def test_github_exact_host_only(self):
        self.assertEqual(rc.classify_host("github.com", rc.DEFAULT_SSO_HOSTS, rc.DEFAULT_CONNECTOR_HOSTS),
                          "github")
        self.assertEqual(rc.classify_host("gist.github.com", rc.DEFAULT_SSO_HOSTS, rc.DEFAULT_CONNECTOR_HOSTS),
                          "plain-web")

    def test_sso_defaults(self):
        for host in ("linear.app", "figma.com", "app.amplitude.com", "cloud.langfuse.com"):
            self.assertEqual(rc.classify_host(host, rc.DEFAULT_SSO_HOSTS, rc.DEFAULT_CONNECTOR_HOSTS),
                              "sso-gated")

    def test_connector_defaults(self):
        for host in ("notion.so", "zoom.us", "example.zoom.us"):
            self.assertEqual(rc.classify_host(host, rc.DEFAULT_SSO_HOSTS, rc.DEFAULT_CONNECTOR_HOSTS),
                              "connector-only")

    def test_atlassian_subdomain_matches_suffix(self):
        self.assertEqual(
            rc.classify_host("example.atlassian.net", rc.DEFAULT_SSO_HOSTS, rc.DEFAULT_CONNECTOR_HOSTS),
            "connector-only")

    def test_config_extends_but_cannot_drop_defaults(self):
        sso = set(rc.DEFAULT_SSO_HOSTS) | {"extra-sso.example.com"}
        self.assertEqual(rc.classify_host("figma.com", sso, rc.DEFAULT_CONNECTOR_HOSTS), "sso-gated")
        self.assertEqual(rc.classify_host("extra-sso.example.com", sso, rc.DEFAULT_CONNECTOR_HOSTS),
                          "sso-gated")


class GitHub404Classification(unittest.TestCase):
    """Covers R3: compound evidence, never a bare 'gone'."""

    def setUp(self):
        rc._PARENT_PROBE_CACHE.clear()
        rc._REF_PROBE_CACHE.clear()

    def test_slash_named_branch_is_read_not_reported_gone(self):
        # The false "gone" this guards: ref `feature` does not exist, so the
        # first cut 404s; the real branch is `feature/foo` and the file is live.
        url = "https://github.com/octo/hello/blob/feature/foo/docs/x.md"
        gh = FakeGh(endpoints={
            "/repos/octo/hello/commits/feature": {"status": 404},
            "/repos/octo/hello/contents/foo/docs/x.md?ref=feature": {"status": 404},
            "/repos/octo/hello": {"status": 200},
        })
        rc.run_gh = gh
        outcome = rc.classify_github(url, rc.parse_github_target(url))
        self.assertEqual(outcome["class"], "ok")

    def test_no_ref_matches_any_cut_is_unknown_never_gone(self):
        url = "https://github.com/octo/hello/blob/deleted-branch/docs/x.md"
        gh = FakeGh(endpoints={
            "/repos/octo/hello/commits/deleted-branch": {"status": 404},
            "/repos/octo/hello/commits/deleted-branch/docs": {"status": 404},
            "/repos/octo/hello": {"status": 200},
        })
        rc.run_gh = gh
        outcome = rc.classify_github(url, rc.parse_github_target(url))
        self.assertEqual(outcome["class"], "unknown")
        self.assertIn("deleted-branch", outcome["text"])

    def test_missing_file_on_a_ref_that_exists_still_upgrades_to_gone(self):
        url = "https://github.com/octo/hello/blob/main/docs/x.md"
        gh = FakeGh(endpoints={
            "/repos/octo/hello/commits/main": {"status": 200},
            "/repos/octo/hello/contents/docs/x.md?ref=main": {"status": 404},
            "/repos/octo/hello": {"status": 200},
        })
        rc.run_gh = gh
        outcome = rc.classify_github(url, rc.parse_github_target(url))
        self.assertEqual(outcome["class"], "gone")

    def test_transient_ref_lookup_never_hardens_into_missing(self):
        url = "https://github.com/octo/hello/blob/main/docs/x.md"
        gh = FakeGh(endpoints={"/repos/octo/hello/commits/main": {"status": 503}})
        rc.run_gh = gh
        outcome = rc.classify_github(url, rc.parse_github_target(url))
        self.assertEqual(outcome["class"], "transient")

    def test_ref_lookup_is_cached_across_links(self):
        gh = FakeGh(endpoints={"/repos/octo/hello/commits/main": {"status": 200}})
        rc.run_gh = gh
        for name in ("a.md", "b.md", "c.md"):
            url = f"https://github.com/octo/hello/blob/main/docs/{name}"
            rc.classify_github(url, rc.parse_github_target(url))
        ref_calls = [c for c in gh.calls if c[-1] == "/repos/octo/hello/commits/main"]
        self.assertEqual(len(ref_calls), 1)

    def test_404_with_no_parent_evidence_stays_no_access(self):
        gh = FakeGh(endpoints={
            "/repos/octo/hello": {"status": 404},
            "/users/octo": {"status": 404},
            "/orgs/octo": {"status": 404},
        })
        rc.run_gh = gh
        outcome = rc.classify_github("https://github.com/octo/hello",
                                      {"kind": "repo", "owner": "octo", "repo": "hello",
                                       "endpoint": "/repos/octo/hello"})
        self.assertEqual(outcome["class"], "no-access")
        self.assertIn("possibly gone", outcome["text"])
        self.assertNotEqual(outcome["class"], "gone")

    def test_404_with_readable_parent_upgrades_to_gone(self):
        gh = FakeGh(endpoints={
            "/repos/octo/hello/contents/docs/x.md?ref=main": {"status": 404},
            "/repos/octo/hello": {"status": 200},
        })
        rc.run_gh = gh
        outcome = rc.classify_github(
            "https://github.com/octo/hello/blob/main/docs/x.md",
            {"kind": "contents", "owner": "octo", "repo": "hello",
             "endpoint": "/repos/octo/hello/contents/docs/x.md?ref=main"})
        self.assertEqual(outcome["class"], "gone")

    def test_repo_level_404_never_upgrades_even_with_visible_owner(self):
        # Private repos are hidden from listings, so a readable owner proves
        # nothing about a 404ing repo: it must stay no-access, never gone.
        gh = FakeGh(endpoints={
            "/repos/octo/hello": {"status": 404},
            "/users/octo": {"status": 200},
            "/orgs/octo": {"status": 200},
        })
        rc.run_gh = gh
        outcome = rc.classify_github("https://github.com/octo/hello",
                                      {"kind": "repo", "owner": "octo", "repo": "hello",
                                       "endpoint": "/repos/octo/hello"})
        self.assertEqual(outcome["class"], "no-access")
        self.assertIn("possibly gone", outcome["text"])

    def test_ambiguous_parent_evidence_is_unknown(self):
        gh = FakeGh(endpoints={
            "/repos/octo/hello/contents/docs/x.md?ref=main": {"status": 404},
            "/repos/octo/hello": {"status": 500},
        })
        rc.run_gh = gh
        outcome = rc.classify_github(
            "https://github.com/octo/hello/blob/main/docs/x.md",
            {"kind": "contents", "owner": "octo", "repo": "hello",
             "endpoint": "/repos/octo/hello/contents/docs/x.md?ref=main"})
        self.assertEqual(outcome["class"], "unknown")


class ConfigLoading(unittest.TestCase):
    def test_missing_file_gives_builtin_defaults_and_named_warning(self):
        with tempfile.TemporaryDirectory() as d:
            config, warnings = rc.load_config(Path(d))
            self.assertEqual(config["allowlist"], [])
            self.assertTrue(any("no .references.json found" in w for w in warnings))

    def test_malformed_json_raises_config_error(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".references.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(rc.ConfigError):
                rc.load_config(Path(d))

    def test_unknown_top_level_key_warns_but_loads(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".references.json").write_text(
                json.dumps({"allowlist": [], "unexpectedKey": 1}), encoding="utf-8")
            config, warnings = rc.load_config(Path(d))
            self.assertTrue(any("unexpectedKey" in w for w in warnings))

    def test_valid_config_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            payload = {"allowlist": [{"match": "x.com", "class": "other", "reason": "r"}],
                       "hostClasses": {"internal.example.com": "sso-gated"}}
            (Path(d) / ".references.json").write_text(json.dumps(payload), encoding="utf-8")
            config, warnings = rc.load_config(Path(d))
            self.assertEqual(config["allowlist"], payload["allowlist"])
            self.assertEqual(warnings, [])

    def test_bare_tld_allowlist_match_rejected(self):
        # F5: a dotless host-form match like "com" suffix-matches enormous
        # swaths of the web via _host_matches.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".references.json").write_text(
                json.dumps({"allowlist": [{"match": "com", "class": "other", "reason": "x"}]}),
                encoding="utf-8")
            with self.assertRaises(rc.ConfigError):
                rc.load_config(Path(d))

    def test_bare_tld_hostclasses_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".references.json").write_text(
                json.dumps({"hostClasses": {"com": "connector-only"}}), encoding="utf-8")
            with self.assertRaises(rc.ConfigError):
                rc.load_config(Path(d))

    def test_full_url_allowlist_match_exempt_from_dot_check(self):
        # A full scheme-prefixed match (matched exactly, never by suffix) is
        # not subject to the bare-host dot rule even without a dot, e.g. a
        # mailto: address at a bare host like localhost.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".references.json").write_text(
                json.dumps({"allowlist": [{"match": "mailto:root@localhost", "class": "other",
                                            "reason": "x"}]}),
                encoding="utf-8")
            config, warnings = rc.load_config(Path(d))  # must not raise
            self.assertEqual(len(config["allowlist"]), 1)

    def test_unknown_hostclasses_value_rejected(self):
        # F6: "sso" (a typo for "sso-gated") used to be silently ignored,
        # falling the host through to an anonymous plain-web probe.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".references.json").write_text(
                json.dumps({"hostClasses": {"weird.example.com": "sso"}}), encoding="utf-8")
            with self.assertRaises(rc.ConfigError):
                rc.load_config(Path(d))

    def test_unknown_allowlist_class_rejected(self):
        # F6: a typo'd allowlist class ("retired" instead of
        # "retired-but-cited") used to still silently route-skip the target.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".references.json").write_text(
                json.dumps({"allowlist": [{"match": "https://example.com/x", "class": "retired",
                                            "reason": "x"}]}),
                encoding="utf-8")
            with self.assertRaises(rc.ConfigError):
                rc.load_config(Path(d))


class ExtractionExemptZones(unittest.TestCase):
    def test_code_fence_and_blockquote_urls_are_exempt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", (
                "# Page\n\n"
                "live: https://example.com/live\n\n"
                "```\nhttps://example.com/in-a-fence\n```\n\n"
                "> https://example.com/in-a-quote\n"
            ))
            by_target, exempt = rc.extract_citations(root)
            self.assertIn("https://example.com/live", by_target)
            self.assertNotIn("https://example.com/in-a-fence", by_target)
            self.assertNotIn("https://example.com/in-a-quote", by_target)
            self.assertEqual(exempt, 2)

    def test_dated_heading_section_is_exempt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", (
                "# Page\n\n"
                "## 2024-01-01 old entry\n\n"
                "old link https://example.com/old\n\n"
                "## Current\n\n"
                "current link https://example.com/current\n"
            ))
            by_target, exempt = rc.extract_citations(root)
            self.assertNotIn("https://example.com/old", by_target)
            self.assertIn("https://example.com/current", by_target)

    def test_duplicate_citation_recorded_once_per_target_with_all_occurrences(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "a.md", "see https://example.com/shared\n")
            write(root, "b.md", "also see https://example.com/shared\n")
            by_target, _ = rc.extract_citations(root)
            self.assertEqual(len(by_target["https://example.com/shared"]), 2)

    def test_heading_line_url_outside_exempt_zone_becomes_citation(self):
        # F7: a URL living directly on a heading line used to `continue`
        # before extraction ever ran - neither cited, exempted, nor
        # inventoried (live instance: a Notion DB cited in an h2).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", (
                "# Page\n\n"
                "## Source DB https://notion.so/db-abc\n\n"
                "body text\n"
            ))
            by_target, exempt = rc.extract_citations(root)
            self.assertIn("https://notion.so/db-abc", by_target)
            self.assertEqual(exempt, 0)

    def test_heading_line_url_inside_dated_zone_is_exempt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", (
                "# Page\n\n"
                "## 2024-01-01 old entry\n\n"
                "### https://example.com/old-nested-heading\n"
            ))
            by_target, exempt = rc.extract_citations(root)
            self.assertNotIn("https://example.com/old-nested-heading", by_target)
            self.assertEqual(exempt, 1)

    def test_dated_stem_file_urls_count_toward_exempt_not_citations(self):
        # F8: whole-file exemptions (freshness: snapshot / dated stem) used
        # to `return [], 0` - the page's citations vanished from every
        # count, breaking the "N citations in exempt zones" boundary.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "2026-01-01-old-log.md", (
                "# Old log\n\n"
                "see https://example.com/a and https://example.com/b\n"
            ))
            by_target, exempt = rc.extract_citations(root)
            self.assertEqual(by_target, {})
            self.assertEqual(exempt, 2)

    def test_snapshot_frontmatter_urls_count_toward_exempt_not_citations(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "strategy.md", (
                "---\nfreshness: snapshot\n---\n"
                "as of 2026-05: see https://example.com/snapshot-source\n"
            ))
            by_target, exempt = rc.extract_citations(root)
            self.assertEqual(by_target, {})
            self.assertEqual(exempt, 1)


class AddressSafety(unittest.TestCase):
    """The address gate is a positive check, so ranges no denylist names are out."""

    def test_cgnat_and_tailnet_addresses_are_unsafe(self):
        for raw in ("100.64.0.1", "100.100.100.100", "100.127.255.255"):
            self.assertFalse(rc._ip_is_safe(raw), raw)

    def test_the_usual_unsafe_ranges_stay_unsafe(self):
        for raw in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.1.1",
                    "0.0.0.0", "::1", "fe80::1", "fc00::1"):
            self.assertFalse(rc._ip_is_safe(raw), raw)

    def test_public_addresses_are_still_reachable(self):
        for raw in ("8.8.8.8", "93.184.216.34", "2001:4860:4860::8888"):
            self.assertTrue(rc._ip_is_safe(raw), raw)


class ProbeSafety(unittest.TestCase):
    """KTD12: real probe_http, only the network primitives are faked."""

    def test_private_address_never_fetched(self):
        real_getaddrinfo = socket.getaddrinfo
        real_open = rc._open_url

        def fake_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, None, None, "", ("127.0.0.1", 0))]

        def boom(*a, **kw):
            raise AssertionError("must not open a connection to an unsafe target")

        rc.socket.getaddrinfo = fake_getaddrinfo
        rc._open_url = boom
        try:
            result = rc.probe_http("https://internal.example.com/x")
        finally:
            rc.socket.getaddrinfo = real_getaddrinfo
            rc._open_url = real_open
        self.assertEqual(result["error"], "unsafe-target")

    def test_cross_host_redirect_not_followed(self):
        real_open = rc._open_url
        real_getaddrinfo = socket.getaddrinfo
        calls = []

        def fake_open(req, timeout, safe_ip=None):
            calls.append(req.full_url)
            hdrs = Message()
            hdrs["Location"] = "https://evil.example.org/elsewhere"
            raise urllib.error.HTTPError(req.full_url, 302, "Found", hdrs, None)

        def fake_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, None, None, "", ("93.184.216.34", 0))]

        rc._open_url = fake_open
        rc.socket.getaddrinfo = fake_getaddrinfo
        try:
            result = rc.probe_http("https://good.example.com/start")
        finally:
            rc._open_url = real_open
            rc.socket.getaddrinfo = real_getaddrinfo
        self.assertEqual(len(calls), 1)  # never followed the redirect
        self.assertEqual(result["error"], "redirect")
        self.assertIn("evil.example.org", result.get("detail", ""))

    def test_unsupported_scheme_never_resolved(self):
        real_getaddrinfo = socket.getaddrinfo

        def boom(*a, **kw):
            raise AssertionError("must not resolve a non-http(s) scheme")

        rc.socket.getaddrinfo = boom
        try:
            result = rc.probe_http("ftp://example.com/f")
        finally:
            rc.socket.getaddrinfo = real_getaddrinfo
        self.assertEqual(result["error"], "unsupported-scheme")

    def test_dns_rebinding_after_check_is_caught_at_connect(self):
        # F2: the safety check (getaddrinfo) sees a public IP, but the
        # literal connect - simulating a low-TTL record swapped out between
        # the check and the real connect - lands on a private one. The
        # post-connect peer check must refuse, proving the pin isn't just a
        # second resolve of the same (now-rebound) hostname.
        real_getaddrinfo = socket.getaddrinfo
        real_connect = rc._connect_to_safe_ip

        class FakePeerSocket:
            def getpeername(self):
                return ("127.0.0.1", 443)

            def close(self):
                pass

        def fake_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, None, None, "", ("93.184.216.34", 0))]

        def fake_connect(safe_ip, port, timeout, source_address):
            self.assertEqual(safe_ip, "93.184.216.34")  # connected to the validated IP...
            return FakePeerSocket()  # ...but the socket that came back peers elsewhere

        rc.socket.getaddrinfo = fake_getaddrinfo
        rc._connect_to_safe_ip = fake_connect
        try:
            result = rc.probe_http("https://good.example.com/start")
            classified = rc.classify_plain_web("https://good.example.com/start")
        finally:
            rc.socket.getaddrinfo = real_getaddrinfo
            rc._connect_to_safe_ip = real_connect
        self.assertEqual(result["error"], "unsafe-target")
        self.assertIn("post-connect peer", result.get("detail", ""))
        self.assertEqual(classified["class"], "unknown")
        self.assertIn("unsafe-target", classified["text"])

    def test_dns_temporary_failure_is_transient_not_unsafe_target(self):
        # F9: a resolver hiccup (EAI_AGAIN) must not get the same confident
        # "unsafe-target" diagnosis as a resolved private address - it needs
        # to be retried, not filed as a security finding.
        real_getaddrinfo = socket.getaddrinfo

        def fake_getaddrinfo(host, *a, **kw):
            raise socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution")

        rc.socket.getaddrinfo = fake_getaddrinfo
        try:
            outcome = rc.classify_plain_web("https://flaky-dns.example.com/x")
        finally:
            rc.socket.getaddrinfo = real_getaddrinfo
        self.assertEqual(outcome["class"], "transient")

    def test_dns_nxdomain_is_no_access_not_transient(self):
        real_getaddrinfo = socket.getaddrinfo

        def fake_getaddrinfo(host, *a, **kw):
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

        rc.socket.getaddrinfo = fake_getaddrinfo
        try:
            outcome = rc.classify_plain_web("https://ghost-domain-does-not-exist.example/x")
        finally:
            rc.socket.getaddrinfo = real_getaddrinfo
        self.assertEqual(outcome["class"], "no-access")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self._real_run_gh = rc.run_gh
        self._real_probe_http = rc.probe_http

    def tearDown(self):
        rc.run_gh = self._real_run_gh
        rc.probe_http = self._real_probe_http

    def test_happy_path_zero_errors(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", (
                "repo: https://github.com/octo/hello\n"
                "site: https://example.com/ok\n"
            ))
            rc.run_gh = FakeGh(endpoints={"/repos/octo/hello": {"status": 200}})
            rc.probe_http = lambda url, timeout=rc.DEFAULT_TIMEOUT, _hop=0: {"status": 200, "error": None}

            code, out, err = run_main(["--path", str(root), "--json"])
            report = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(report["errors"], 0)
            self.assertEqual(report["findings"], [])

    def test_nonallowlisted_unreachable_citation_exits_nonzero_with_full_finding(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "dead link https://example.com/dead\n")
            rc.probe_http = lambda url, timeout=rc.DEFAULT_TIMEOUT, _hop=0: {"status": 404, "error": None}

            code, out, err = run_main(["--path", str(root), "--json"])
            report = json.loads(out)
            self.assertEqual(code, 1)
            self.assertEqual(len(report["findings"]), 1)
            f = report["findings"][0]
            self.assertEqual(f["file"], "page.md")
            self.assertEqual(f["line"], 1)
            self.assertEqual(f["target"], "https://example.com/dead")
            self.assertEqual(f["error_class"], "no-access")
            self.assertEqual(f["identity"], "anonymous HTTP")

    def test_allowlisted_target_is_skipped_by_design_and_exit_unaffected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "dead link https://example.com/dead\n")
            write(root, ".references.json", json.dumps({
                "allowlist": [{"match": "https://example.com/dead", "class": "retired-but-cited",
                                "reason": "kept for history", "owner": "team"}]
            }))
            probe = MagicMock(side_effect=AssertionError("allowlisted target must never be probed"))
            rc.probe_http = probe

            code, out, err = run_main(["--path", str(root), "--json"])
            report = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(len(report["findings"]), 1)
            f = report["findings"][0]
            self.assertEqual(f["error_class"], "skipped-by-design")
            self.assertEqual(f["text"], "kept for history")
            probe.assert_not_called()

    def test_per_user_allowlisted_gone_target_stays_error(self):
        # F4: a compound-evidence "gone" (deleted for EVERYONE, not just
        # this identity) must never be swallowed by the per-user downgrade -
        # only per this-identity failures should skip.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "gone: https://github.com/octo/hello/blob/main/docs/x.md\n")
            write(root, ".references.json", json.dumps({
                "allowlist": [{"match": "github.com", "class": "per-user", "reason": "personal repo"}]
            }))
            rc.run_gh = FakeGh(endpoints={
                "/repos/octo/hello/contents/docs/x.md?ref=main": {"status": 404},
                "/repos/octo/hello": {"status": 200},
            })
            code, out, err = run_main(["--path", str(root), "--json"])
            report = json.loads(out)
            self.assertEqual(code, 1)
            f = report["findings"][0]
            self.assertEqual(f["error_class"], "gone")

    def test_sso_host_never_probed_errors_without_allowlist(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "dash: https://linear.app/team/issue/1\n")
            probe = MagicMock(side_effect=AssertionError("sso-gated host must never be HTTP-probed"))
            rc.probe_http = probe

            code, out, err = run_main(["--path", str(root), "--json"])
            report = json.loads(out)
            self.assertEqual(code, 1)
            probe.assert_not_called()
            f = report["findings"][0]
            self.assertEqual(f["error_class"], "sso-gated-no-allowlist")

    def test_timeout_retried_once_then_transient_not_exit_affecting(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "flaky: https://example.com/flaky\n")
            calls = []

            def flaky(url, timeout=rc.DEFAULT_TIMEOUT, _hop=0):
                calls.append(url)
                return {"status": None, "error": "timeout"}

            rc.probe_http = flaky
            code, out, err = run_main(["--path", str(root), "--json"])
            report = json.loads(out)
            self.assertEqual(len(calls), 2)  # retried exactly once
            self.assertEqual(code, 0)  # transient alone does not force non-zero
            self.assertEqual(report["findings"][0]["error_class"], "transient")
            self.assertEqual(report["findings"][0]["severity"], "warning")

    def test_duplicate_citation_probed_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "a.md", "see https://example.com/dead\n")
            write(root, "b.md", "also https://example.com/dead\n")
            probe = MagicMock(return_value={"status": 404, "error": None})
            rc.probe_http = probe

            code, out, err = run_main(["--path", str(root), "--json"])
            report = json.loads(out)
            self.assertEqual(probe.call_count, 1)
            self.assertEqual(len(report["findings"]), 2)  # one finding per citing occurrence
            self.assertEqual(code, 1)

    def test_gh_missing_exits_2_with_named_error_no_per_target_findings(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "repo: https://github.com/octo/hello\n")
            rc.run_gh = FakeGh(auth_ok=False)

            code, out, err = run_main(["--path", str(root), "--json"])
            self.assertEqual(code, 2)
            self.assertIn("gh not installed", err)
            self.assertEqual(out, "")  # no per-target findings printed at all

    def test_malformed_config_exits_2_named_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "x https://example.com/x\n")
            write(root, ".references.json", "{not json")

            code, out, err = run_main(["--path", str(root), "--json"])
            self.assertEqual(code, 2)
            self.assertIn(".references.json", err)

    def test_inventory_mode_counts_without_probing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", (
                "https://github.com/octo/hello\n"
                "https://example.com/plain\n"
                "https://notion.so/page\n"
                "https://linear.app/x\n"
            ))
            probe = MagicMock(side_effect=AssertionError("inventory must not probe"))
            gh = MagicMock(side_effect=AssertionError("inventory must not shell out to gh"))
            rc.probe_http = probe
            rc.run_gh = gh

            code, out, err = run_main(["--path", str(root), "--json", "--inventory"])
            report = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(report["counts"]["github"], 1)
            self.assertEqual(report["counts"]["plain-web"], 1)
            self.assertEqual(report["counts"]["connector-only"], 1)
            self.assertEqual(report["counts"]["sso-gated"], 1)
            probe.assert_not_called()
            gh.assert_not_called()

    def test_verify_requires_path(self):
        # F1: --verify used to accept a bare results file and trust it
        # blindly. It now must recompute the authoritative connector-only
        # set from a real handbook checkout.
        with tempfile.TemporaryDirectory() as d:
            results_path = Path(d) / "results.json"
            results_path.write_text(json.dumps({"findings": []}), encoding="utf-8")
            code, out, err = run_main(["--verify", str(results_path)])
            self.assertEqual(code, 2)

    def test_verify_flags_unfilled_connector_row(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "db: https://notion.so/x\n")
            results_path = root / "results.json"
            results_path.write_text(json.dumps({"findings": [
                {"error_class": "needs-agent-result", "target": "https://notion.so/x",
                 "file": "page.md", "line": 1, "result": None},
            ]}), encoding="utf-8")
            code, out, err = run_main(["--path", str(root), "--verify", str(results_path)])
            self.assertNotEqual(code, 0)
            self.assertIn("https://notion.so/x", out)

    def test_verify_passes_when_connector_row_filled(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "db: https://notion.so/x\n")
            results_path = root / "results.json"
            results_path.write_text(json.dumps({"findings": [
                {"error_class": "needs-agent-result", "target": "https://notion.so/x",
                 "file": "page.md", "line": 1, "result": "verified reachable via MCP"},
            ]}), encoding="utf-8")
            code, out, err = run_main(["--path", str(root), "--verify", str(results_path)])
            self.assertEqual(code, 0)

    def test_verify_fails_when_expected_target_missing_from_results(self):
        # F1 hole (b): an empty/mismatched results file used to pass
        # silently because nothing cross-checked it against the real
        # citation set.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "db: https://notion.so/x\n")
            results_path = root / "results.json"
            results_path.write_text(json.dumps({"findings": []}), encoding="utf-8")
            code, out, err = run_main(["--path", str(root), "--verify", str(results_path)])
            self.assertEqual(code, 1)
            self.assertIn("https://notion.so/x", out)

    def test_verify_fails_when_filled_result_carries_failure_class(self):
        # F1 hole (a): a row filled with a FAILING result used to pass
        # because cmd_verify only checked truthiness, never the class.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "db: https://notion.so/x\n")
            results_path = root / "results.json"
            results_path.write_text(json.dumps({"findings": [
                {"error_class": "needs-agent-result", "target": "https://notion.so/x",
                 "file": "page.md", "line": 1,
                 "result": {"error_class": "no-access", "identity": "notion:workspace"}},
            ]}), encoding="utf-8")
            code, out, err = run_main(["--path", str(root), "--verify", str(results_path)])
            self.assertEqual(code, 1)
            self.assertIn("https://notion.so/x", out)

    def test_verify_passes_when_filled_result_is_transient_dict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root, "page.md", "db: https://notion.so/x\n")
            results_path = root / "results.json"
            results_path.write_text(json.dumps({"findings": [
                {"error_class": "needs-agent-result", "target": "https://notion.so/x",
                 "file": "page.md", "line": 1,
                 "result": {"error_class": "transient", "identity": "notion:workspace"}},
            ]}), encoding="utf-8")
            code, out, err = run_main(["--path", str(root), "--verify", str(results_path)])
            self.assertEqual(code, 0)


class TestRelativeLinksSkipped(unittest.TestCase):
    def test_relative_and_anchor_links_are_not_citations(self):
        line = "See [start here](onboarding/start-here.md) and [above](#the-registry) and [repo](https://github.com/x/y)."
        urls = rc._extract_urls(line)
        self.assertEqual(urls, ["https://github.com/x/y"])

    def test_scheme_carrying_non_http_still_extracted(self):
        urls = rc._extract_urls("[mail](mailto:a@b.c)")
        self.assertEqual(urls, ["mailto:a@b.c"])


class TestProfileAndBacktick(unittest.TestCase):
    def test_profile_url_maps_to_users_endpoint(self):
        info = rc.parse_github_target("https://github.com/octocat")
        self.assertEqual(info["kind"], "profile")
        self.assertEqual(info["endpoint"], "/users/octocat")

    def test_org_profile_404_stays_no_access(self):
        gh = FakeGh(endpoints={"/users/ghostuser": {"status": 404}})
        rc.run_gh = gh
        outcome = rc.classify_github("https://github.com/ghostuser",
                                      {"kind": "profile", "owner": "ghostuser", "repo": None,
                                       "endpoint": "/users/ghostuser"})
        self.assertEqual(outcome["class"], "no-access")

    def test_trailing_backtick_stripped_from_bare_url(self):
        urls = rc._extract_urls("see https://example.com/x` in code")
        self.assertEqual(urls, ["https://example.com/x"])


if __name__ == "__main__":
    unittest.main()

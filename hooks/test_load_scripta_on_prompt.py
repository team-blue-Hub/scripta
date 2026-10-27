#!/usr/bin/env python3
"""Unit tests for the trigger matcher in load_scripta_on_prompt.py.

Run: python3 hooks/test_load_scripta_on_prompt.py
No framework, no fixtures — stdlib unittest only, same bar as the other hook tests.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_scripta_on_prompt import is_team_fact_prompt


class PositiveTriggers(unittest.TestCase):
    def test_decide_variant_of_decision(self):
        self.assertTrue(is_team_fact_prompt("what did we decide about the pricing page"))

    def test_where_does_x_live(self):
        self.assertTrue(is_team_fact_prompt("where does the brand list live"))

    def test_bare_scripta_mention(self):
        self.assertTrue(is_team_fact_prompt("check scripta"))

    def test_bare_handbook_mention(self):
        self.assertTrue(is_team_fact_prompt("does the handbook say anything about this"))

    def test_adr_token(self):
        self.assertTrue(is_team_fact_prompt("is there an ADR for this"))

    def test_source_of_truth_phrase(self):
        self.assertTrue(is_team_fact_prompt("what's the source of truth for feature flags"))

    def test_who_owns_phrase(self):
        self.assertTrue(is_team_fact_prompt("who owns the notification-copywriter skill"))

    def test_where_is_stored_wildcard(self):
        self.assertTrue(is_team_fact_prompt("where is the brand registry stored"))

    def test_org_chart_phrase(self):
        self.assertTrue(is_team_fact_prompt("who's on the org chart for the team"))

    def test_expert_on_phrase(self):
        self.assertTrue(is_team_fact_prompt("who's the expert on ISIC classification"))

    def test_case_insensitive(self):
        self.assertTrue(is_team_fact_prompt("SCRIPTA has the answer"))


class NegativeTriggers(unittest.TestCase):
    def test_what_did_we_build(self):
        self.assertFalse(is_team_fact_prompt("what did we build an hour ago"))

    def test_fix_this_bug(self):
        self.assertFalse(is_team_fact_prompt("fix this bug"))

    def test_run_the_tests(self):
        self.assertFalse(is_team_fact_prompt("run the tests"))

    def test_plain_code_question(self):
        self.assertFalse(is_team_fact_prompt("why is this function returning None"))

    def test_empty_string(self):
        self.assertFalse(is_team_fact_prompt(""))

    def test_adr_not_matched_inside_other_words(self):
        # "quadrant"/"squadron" contain the letters a-d-r but aren't ADR mentions;
        # the word-boundary regex must not fire on them.
        self.assertFalse(is_team_fact_prompt("plot the four points in each quadrant"))


class WarnsThePerson(unittest.TestCase):
    """The prompt hook tells the person, not only the model, when maps are cut."""

    def _main_output(self, rows):
        import io, json, tempfile
        from unittest import mock
        import load_scripta_on_prompt as hook
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            body = "\n".join(f"| fact {i} | [h{i}](h{i}.md) |" for i in range(rows))
            (tmp / "index.md").write_text("# Index\n", encoding="utf-8")
            (tmp / "where-truth-lives.md").write_text(
                "| The fact | Home |\n|---|---|\n" + body + "\n", encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(hook, "locate_repo", return_value=tmp), \
                 mock.patch.object(hook, "freshen"), \
                 mock.patch("sys.stdin", io.StringIO(json.dumps({"prompt": "where does x live"}))), \
                 mock.patch("sys.stdout", out):
                hook.main()
            return json.loads(out.getvalue())

    def test_whole_maps_carry_no_warning(self):
        self.assertNotIn("systemMessage", self._main_output(5))

    def test_cut_maps_warn_the_person(self):
        out = self._main_output(600)
        self.assertIn("no longer fit", out["systemMessage"])
        self.assertIn("additionalContext", out["hookSpecificOutput"], "the maps still arrive")


if __name__ == "__main__":
    unittest.main()

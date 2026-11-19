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


def _handbook(tmp: Path, rows: int) -> Path:
    body = "\n".join(f"| fact {i} | [h{i}](h{i}.md) |" for i in range(rows))
    (tmp / "index.md").write_text("# Index\n", encoding="utf-8")
    (tmp / "where-truth-lives.md").write_text(
        "| The fact | Home |\n|---|---|\n" + body + "\n", encoding="utf-8")
    return tmp


def _run(repo: Path, argv=(), prompt="where does x live", freshen_later=None):
    """Run the hook once, as Claude Code would run one of its registrations."""
    import io, json
    from unittest import mock
    import load_scripta_on_prompt as hook
    out = io.StringIO()
    later = freshen_later or mock.Mock()
    with mock.patch.object(hook, "locate_repo", return_value=repo) as locate, \
         mock.patch.object(hook, "freshen_later", later), \
         mock.patch("sys.argv", ["load_scripta_on_prompt.py", *argv]), \
         mock.patch("sys.stdin", io.StringIO(json.dumps({"prompt": prompt}))), \
         mock.patch("sys.stdout", out):
        hook.main()
    text = out.getvalue()
    return (json.loads(text) if text else None), later, locate


class WarnsThePerson(unittest.TestCase):
    """The prompt hook tells the person, not only the model, when maps are cut."""

    def _main_output(self, rows):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            return _run(_handbook(Path(d), rows))[0]

    def test_whole_maps_carry_no_warning(self):
        self.assertNotIn("systemMessage", self._main_output(5))

    def test_cut_maps_warn_the_person(self):
        out = self._main_output(1400)
        self.assertIn("no longer fit", out["systemMessage"])
        self.assertIn("additionalContext", out["hookSpecificOutput"], "the maps still arrive")


class SendsOnePart(unittest.TestCase):
    """Each registration of the hook sends one slice of the same maps."""

    LEAD = "Consult the team handbook below"

    def _context(self, out):
        return out["hookSpecificOutput"]["additionalContext"]

    def test_each_part_sends_its_own_slice(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            repo = _handbook(Path(d), 500)
            first, second, third = (_run(repo, ["--part", str(k)])[0] for k in (1, 2, 3))
        self.assertTrue(self._context(first).startswith(self.LEAD))
        self.assertIn("part 1 of 2", self._context(first))
        self.assertIn("part 2 of 2", self._context(second))
        self.assertNotIn(self.LEAD, self._context(second))
        self.assertIsNone(third, "a part past the payload sends nothing")

    def test_only_part_one_warns_the_person(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            repo = _handbook(Path(d), 1400)
            first, second = (_run(repo, ["--part", str(k)])[0] for k in (1, 2))
        self.assertIn("systemMessage", first)
        self.assertNotIn("systemMessage", second)

    def test_a_prompt_that_is_not_a_team_fact_sends_and_reads_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            for k in (1, 2, 3):
                out, later, locate = _run(_handbook(Path(d), 500), ["--part", str(k)],
                                          prompt="run the tests")
                self.assertIsNone(out)
                locate.assert_not_called()
                later.assert_not_called()

    def test_the_pull_lands_for_the_next_prompt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            repo = _handbook(Path(d), 5)
            page = repo / "where-truth-lives.md"

            def pull(*_):
                page.write_text(page.read_text(encoding="utf-8") + "| late fact | [l](l.md) |\n",
                                encoding="utf-8")

            from unittest import mock
            out, later, _ = _run(repo, ["--part", "1"], freshen_later=mock.Mock(side_effect=pull))
            later.assert_called_once()
            self.assertNotIn("late fact", self._context(out), "this prompt reads before the pull")
            out, _, _ = _run(repo, ["--part", "1"])
            self.assertIn("late fact", self._context(out), "the next prompt sees it")

    def test_only_part_one_starts_the_pull(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            repo = _handbook(Path(d), 500)
            for k in (2, 3):
                _run(repo, ["--part", str(k)])[1].assert_not_called()

    def test_a_malformed_part_is_part_one(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            repo = _handbook(Path(d), 5)
            for argv in ([], ["--part"], ["--part", "x"], ["--part", "0"]):
                self.assertTrue(self._context(_run(repo, argv)[0]).startswith(self.LEAD))


if __name__ == "__main__":
    unittest.main()

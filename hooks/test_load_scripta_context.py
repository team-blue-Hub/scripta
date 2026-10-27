#!/usr/bin/env python3
"""Unit tests for the pure payload-assembly helpers in load_scripta_context.py.

Run: python3 hooks/test_load_scripta_context.py
No framework, no fixtures — stdlib unittest only, same bar as the hook itself.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load_scripta_context import (MAX_BYTES, REGISTRY_CELL_CAP, assemble_maps_payload,
                                  compact_index, compact_registry, index_pointer,
                                  registry_table_only, skeletal_index,
                                  strip_frontmatter)


class StripFrontmatter(unittest.TestCase):
    def test_strips_closed_block(self):
        self.assertEqual(strip_frontmatter("---\ntitle: x\n---\n\n# X"), "# X")

    def test_no_frontmatter_passthrough(self):
        self.assertEqual(strip_frontmatter("# plain"), "# plain")

    def test_unclosed_block_left_alone(self):
        self.assertEqual(strip_frontmatter("---\nnever closed"), "---\nnever closed")


class CompactIndex(unittest.TestCase):
    def test_adr_bullets_become_pointer(self):
        text = (
            "# Index\n\n## Decisions (ADRs)\n\nFull log:\n\n"
            "- [0001](decisions/0001.md)\n- [0002](decisions/0002.md)\n\n## Strategy\n\n- [plan](strategy/plan.md)\n"
        )
        out = compact_index(text)
        self.assertIn("2 dated ADRs", out)
        self.assertNotIn("0001", out)
        self.assertIn("- [plan](strategy/plan.md)", out)  # other sections keep bullets

    def test_no_decisions_section_passthrough(self):
        text = "# T\n\n## Other\n\n- [a](a.md) — keep\n"
        self.assertEqual(compact_index(text), text.rstrip("\n"))

    def test_decisions_as_last_section_still_flushes(self):
        out = compact_index("## Decisions (ADRs)\n\n- [0001](d/1.md)\n- [0002](d/2.md)")
        self.assertIn("2 dated ADRs", out)

    def test_wrapped_and_nested_lines_dropped_with_their_bullet(self):
        text = (
            "## Decisions (ADRs)\n\n"
            "- [0001](d/1.md) title\n"
            "  continuation line that wraps\n"
            "- [0002](d/2.md) other\n"
            "  - nested sub bullet\n"
            "  - [0003-looking nested link](d/3.md)\n"
        )
        out = compact_index(text)
        self.assertNotIn("continuation line", out)
        self.assertNotIn("nested sub bullet", out)
        self.assertNotIn("0003", out)
        self.assertIn("2 dated ADRs", out)  # nested lines swallowed, not counted

    def test_indented_text_without_dropped_parent_survives(self):
        text = "## Decisions (ADRs)\n\nintro line\n  indented note under intro\n- [0001](d/1.md)\n"
        out = compact_index(text)
        self.assertIn("indented note under intro", out)
        self.assertIn("1 dated ADR —", out)  # singular when only one bullet dropped


class CompactRegistry(unittest.TestCase):
    def test_every_fact_cell_survives(self):
        text = (
            "| The fact | Its one official home |\n|---|---|\n"
            "| Why we decided | [`decisions/`](decisions/) — dated ADRs. Long prose here about history and owners. |\n"
            "| Live state | [config-store](https://x) — flags |\n"
        )
        out = compact_registry(text)
        self.assertIn("Why we decided", out)
        self.assertIn("Live state", out)

    def test_long_home_cell_cut_at_first_pointer_and_marked(self):
        text = "| A fact | [home](h.md) — owner: X. " + "More prose. " * 20 + "|"
        out = compact_registry(text)
        self.assertIn("[home](h.md) …", out)
        self.assertNotIn("More prose", out)

    def test_cell_under_cap_with_trailing_prose_untouched(self):
        text = "| A fact | [home](h.md) — owner: X. A little prose. |"
        self.assertEqual(compact_registry(text), text)

    def test_long_first_fragment_hard_capped(self):
        text = "| F | " + "x" * (REGISTRY_CELL_CAP + 60) + " |"
        out = compact_registry(text)
        cell = out.split("|")[2].strip()
        self.assertLessEqual(len(cell), REGISTRY_CELL_CAP + 1)  # +1 for the ellipsis
        self.assertTrue(cell.endswith("…"))

    def test_short_cell_untouched(self):
        text = "| F | [Zenlytic](https://z) dashboards |"
        self.assertEqual(compact_registry(text), text)

    def test_abbreviation_before_link_keeps_the_pointer(self):
        out = compact_registry("| Live state | Owner: J. Smith — see [config-store](https://x) for flags |")
        self.assertIn("[config-store](https://x)", out)

    def test_literal_pipe_in_home_cell_does_not_shear_the_row(self):
        text = "| CLI pipeline example | Run `cmd1 | cmd2` to see it |"
        self.assertEqual(compact_registry(text), text)

    def test_link_past_cap_kept_whole(self):
        home = "p" * (REGISTRY_CELL_CAP + 40) + " [home](h.md) tail prose"
        out = compact_registry(f"| F | {home} |")
        self.assertIn("[home](h.md)", out)

    def test_non_table_lines_pass_through(self):
        text = "# Where truth lives\n\n> Every fact has one home.\n"
        self.assertEqual(compact_registry(text), text.rstrip("\n"))


class SkeletalIndex(unittest.TestCase):
    def test_bullet_descriptions_dropped_links_kept(self):
        text = "- [data](engineering/data.md) — the data sources and where to look"
        self.assertEqual(skeletal_index(text), "- [data](engineering/data.md)")

    def test_non_bullet_lines_untouched(self):
        text = "## Engineering\n\nplain paragraph — with a dash"
        self.assertEqual(skeletal_index(text), text)


class AssembleLadder(unittest.TestCase):
    def _repo(self, tmp, index_body, registry_body):
        (tmp / "index.md").write_text(index_body, encoding="utf-8")
        (tmp / "where-truth-lives.md").write_text(registry_body, encoding="utf-8")
        return tmp

    def test_small_pages_ship_untouched(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(Path(d), "# Index\n- [a](a.md) — desc\n",
                              "| The fact | Home |\n|---|---|\n| F | [h](h.md) long prose. tail |\n")
            body = assemble_maps_payload(repo)
            self.assertIn("— desc", body)          # index descriptions kept
            self.assertIn("long prose", body)       # registry prose kept
            self.assertNotIn("rows shortened", body)

    def test_oversized_registry_compacts_but_every_row_arrives(self):
        import tempfile
        rows = "\n".join(f"| fact {i} | [h{i}](h{i}.md) — " + "prose " * 60 + "|" for i in range(40))
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(Path(d), "# Index\n", "| The fact | Home |\n|---|---|\n" + rows + "\n")
            body = assemble_maps_payload(repo)
            self.assertLessEqual(len(body.encode()), MAX_BYTES)
            for i in range(40):
                self.assertIn(f"fact {i} ", body)   # no row lost to a tail cut
            self.assertIn("rows shortened to fit", body)  # rung-2 note: index survives here
            self.assertNotIn("payload trimmed", body)

    def test_rung2_and_rung3_notes_differ(self):
        import tempfile
        # Rung 2: registry needs compacting, index descriptions still fit.
        rows = "\n".join(f"| fact {i} | [h{i}](h{i}.md) — " + "prose " * 60 + "|" for i in range(30))
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(Path(d), "# Index\n- [a](a.md) — a description that must survive rung 2\n",
                              "| The fact | Home |\n|---|---|\n" + rows + "\n")
            body2 = assemble_maps_payload(repo)
            self.assertIn("a description that must survive rung 2", body2)
            self.assertIn("rows shortened to fit", body2)
            self.assertNotIn("index descriptions dropped", body2)
        # Rung 3: even skeletal index is needed.
        rows = "\n".join(f"| fact {i} | [h{i}](h{i}.md) — " + "prose " * 60 + "|" for i in range(40))
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(Path(d), "# Index\n" + "\n".join(f"- [p{i}](p{i}.md) — long description here {i} " + "d" * 200 for i in range(40)) + "\n",
                              "| The fact | Home |\n|---|---|\n" + rows + "\n")
            body3 = assemble_maps_payload(repo)
            self.assertIn("index descriptions dropped", body3)
            self.assertNotIn("long description here 5", body3)


class RegistryTableOnlyKeepsEveryRow(unittest.TestCase):
    """A blank line between rows is a grouping break, not the end of the table.

    The first cut of this rung sliced from the header to the first blank line.
    On a table with one break in it that dropped 29 of 57 rows while the rung's
    note still said the table was inlined in full: the exact failure this PR
    exists to stop, one layer down.
    """

    TABLE = ["| The fact | Its one official home |",
             "|---|---|",
             "| One | [a](a.md) |",
             "| Two | [b](b.md) |",
             "| Three | [c](c.md) |"]

    def rows(self, text):
        return [l for l in text.splitlines() if l.startswith("| ")]

    def test_a_break_between_rows_keeps_them_all(self):
        broken = "\n".join(self.TABLE[:4] + [""] + self.TABLE[4:])
        self.assertEqual(len(self.rows(registry_table_only(broken))),
                         len(self.rows("\n".join(self.TABLE))))

    def test_prose_after_the_table_still_ends_it(self):
        page = "\n".join(self.TABLE + ["", "Some prose about the table.",
                                        "", "| Not | [the registry](x.md) |"])
        out = registry_table_only(page)
        self.assertNotIn("Some prose", out)
        self.assertNotIn("Not", out)
        self.assertEqual(len(self.rows(out)), len(self.rows("\n".join(self.TABLE))))

    def test_frontmatter_and_heading_above_the_table_are_dropped(self):
        page = "\n".join(["# Where truth lives", "", "> A quote.", ""]
                         + self.TABLE)
        self.assertEqual(len(self.rows(registry_table_only(page))),
                         len(self.rows("\n".join(self.TABLE))))


class RungsFourAndFive(unittest.TestCase):
    """The index gives way before the registry, and the registry never loses a row.

    Rungs 1-3 stopped being enough: the real handbook wanted 19,798
    bytes at rung 3, so the blunt tail-trim fired on every injection and cut the
    registry mid-row. These two rungs are what keeps the router whole.
    """

    def _repo(self, tmp, index_body, registry_body):
        (tmp / "index.md").write_text(index_body, encoding="utf-8")
        (tmp / "where-truth-lives.md").write_text(registry_body, encoding="utf-8")
        return tmp

    def _big_registry(self, rows, page_prose=1):
        body = "\n".join(f"| fact {i} | [h{i}](h{i}.md) — " + "prose " * 40 + "|"
                         for i in range(rows))
        intro = "Framing prose the page carries about itself. " * page_prose
        return (intro + "\n\n| The fact | Home |\n|---|---|\n" + body
                + "\n\nA closing paragraph.\n")

    def test_rung4_drops_the_index_before_any_registry_row(self):
        import tempfile
        # An index too big to survive even skeletal, plus a registry that fits
        # once compacted: the index must go, every row must stay.
        index = "# Index\n" + "\n".join(f"- [p{i}](p{i}.md)" for i in range(600)) + "\n"
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(Path(d), index, self._big_registry(25))
            body = assemble_maps_payload(repo)
            self.assertLessEqual(len(body.encode()), MAX_BYTES)
            self.assertNotIn("payload trimmed", body)
            self.assertIn("index.md is not", body)
            self.assertNotIn("p500", body)                 # index gave way
            for i in range(25):
                self.assertIn(f"fact {i} ", body)          # router intact

    def test_rung5_keeps_every_row_when_the_page_prose_must_go(self):
        import tempfile
        index = "# Index\n" + "\n".join(f"- [p{i}](p{i}.md)" for i in range(600)) + "\n"
        with tempfile.TemporaryDirectory() as d:
            # Page prose heavy enough that rung 4 still overflows: only
            # dropping it, not a single row, brings the payload under.
            repo = self._repo(Path(d), index, self._big_registry(60, page_prose=200))
            body = assemble_maps_payload(repo)
            self.assertLessEqual(len(body.encode()), MAX_BYTES)
            self.assertNotIn("payload trimmed", body)
            self.assertNotIn("Framing prose the page carries", body)
            self.assertNotIn("A closing paragraph", body)
            for i in range(60):
                self.assertIn(f"fact {i} ", body)

    def test_registry_table_only_keeps_the_table_and_nothing_else(self):
        text = ("intro\n\n| The fact | Home |\n|---|---|\n| F | [h](h.md) |\n\noutro\n")
        out = registry_table_only(text)
        self.assertIn("| F | [h](h.md) |", out)
        self.assertNotIn("intro", out)
        self.assertNotIn("outro", out)

    def test_registry_table_only_passes_a_page_with_no_table_through(self):
        text = "no table here\n"
        self.assertEqual(registry_table_only(text), text)

    def test_index_pointer_names_where_to_read_it(self):
        self.assertIn("index.md", index_pointer("# Index\nanything\n"))


class FallbackTrim(unittest.TestCase):
    def test_last_resort_has_single_clean_notice(self):
        import tempfile
        # Registry so large even compacted rows overflow: forces the tail-trim.
        rows = "\n".join(f"| fact {i} | [h{i}](h{i}.md) |" for i in range(400))
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "index.md").write_text("# Index\n", encoding="utf-8")
            (tmp / "where-truth-lives.md").write_text(
                "| The fact | Home |\n|---|---|\n" + rows + "\n", encoding="utf-8")
            body = assemble_maps_payload(tmp)
            self.assertLessEqual(len(body.encode()), MAX_BYTES)
            self.assertIn("payload trimmed", body)
            self.assertNotIn("index descriptions dropped", body)  # rung-3 note not doubled


def _handbook(tmp: Path, rows: int, prose: str = "") -> Path:
    body = "\n".join(f"| fact {i} | [`p/h{i}.md`](p/h{i}.md) |" for i in range(rows))
    (tmp / "index.md").write_text("# Index\n", encoding="utf-8")
    (tmp / "where-truth-lives.md").write_text(
        "# Where truth lives\n\n| The fact | Home |\n|---|---|\n" + body + "\n\n" + prose, encoding="utf-8")
    return tmp


class SelfLinks(unittest.TestCase):
    def test_a_link_to_itself_arrives_once_as_a_path(self):
        out = compact_registry("| Legal | [`legal/x.md`](legal/x.md) — **here** |")
        self.assertIn("`legal/x.md`", out)
        self.assertNotIn("](legal/x.md)", out)

    def test_a_link_whose_text_differs_is_left_alone(self):
        row = "| Live flags | [config-store](https://github.com/o/config-store) |"
        self.assertIn("[config-store](https://github.com/o/config-store)", compact_registry(row))
        self.assertIn("[the page](a.md)", compact_registry("| X | [the page](a.md) |"))


class MapsReport(unittest.TestCase):
    def test_a_small_handbook_fits_whole_and_is_ok(self):
        import tempfile
        from load_scripta_context import maps_payload_report
        with tempfile.TemporaryDirectory() as d:
            r = maps_payload_report(_handbook(Path(d), 5))
            self.assertTrue(r["ok"])
            self.assertEqual(r["rung"], 1)
            self.assertEqual(r["body"], assemble_maps_payload(Path(d)))

    def test_fitting_only_by_dropping_the_page_rules_is_not_ok(self):
        import tempfile
        from load_scripta_context import maps_payload_report
        # Rows that fit on their own, page prose that pushes rung 4 over the cap.
        with tempfile.TemporaryDirectory() as d:
            r = maps_payload_report(_handbook(Path(d), 150, prose="## The rule\n\n" + "word " * 1200))
            self.assertEqual(r["rung"], 5)
            self.assertFalse(r["ok"])

    def test_a_cut_tail_is_not_ok_and_reports_what_it_needed(self):
        import tempfile
        from load_scripta_context import TRIMMED, maps_payload_report
        with tempfile.TemporaryDirectory() as d:
            r = maps_payload_report(_handbook(Path(d), 600))
            self.assertEqual(r["rung"], TRIMMED)
            self.assertFalse(r["ok"])
            self.assertGreater(r["bytes"], MAX_BYTES, "the size is what the last rung wanted before the cut")
            self.assertLessEqual(len(r["body"].encode()), MAX_BYTES, "the body itself is still cut to fit")

    def test_no_map_pages_means_no_report(self):
        import tempfile
        from load_scripta_context import maps_payload_report
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(maps_payload_report(Path(d)))


class CheckMapsCli(unittest.TestCase):
    def _run(self, path):
        import io, contextlib
        from load_scripta_context import check_maps_cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = check_maps_cli(str(path))
        return code, buf.getvalue()

    def test_exit_codes_and_messages(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(_handbook(Path(d), 5))
            self.assertEqual(code, 0); self.assertIn("fit", out)
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(_handbook(Path(d), 600))
            self.assertEqual(code, 1); self.assertIn("too big", out); self.assertIn("never arrive", out)
        with tempfile.TemporaryDirectory() as d:
            code, _ = self._run(Path(d))
            self.assertEqual(code, 2)


class GuardContract(unittest.TestCase):
    def test_max_bytes_is_under_offload_threshold(self):
        # Claude Code offloads hook output near 10KB; the guard must stay under.
        self.assertLess(MAX_BYTES, 10_000)


SKILLS = Path(__file__).resolve().parent.parent / "skills"

# The order locate_repo() uses: the env var, then the config file, then the
# two ~/PROJECTS defaults. Every skill that looks for the handbook names the
# same order, so a session and its skills never end up in different folders.
LOOKUP_ORDER = ["SCRIPTA_HANDBOOK_PATH", "handbook_path",
                "~/PROJECTS/hub-scripta-handbook", "~/PROJECTS/scripta"]
SESSION_NOTE = "A team handbook exists at"
# locate_repo() uses a set override alone and never falls back to the defaults.
OVERRIDE_ALONE = "is used alone"


class SkillsUseTheHookOrder(unittest.TestCase):
    def test_hook_order_is_the_documented_order(self):
        import load_scripta_context as hook
        src = Path(hook.__file__).read_text(encoding="utf-8")
        body = src[src.index("def locate_repo"):src.index("def freshen")]
        at = [body.index(t) for t in ('"SCRIPTA_HANDBOOK_PATH"', "configured_path()",
                                      '"hub-scripta-handbook"', '"scripta"')]
        self.assertEqual(at, sorted(at))

    def test_every_lookup_names_the_hook_order(self):
        for name in ("catch-up", "daily-digest", "document", "hardening-interview",
                     "weekly-update", "setup"):
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                found = [text.find(t) for t in LOOKUP_ORDER]
                self.assertNotIn(-1, found, "a lookup step is missing")
                self.assertEqual(found, sorted(found), "the steps are out of order")
                # A session that cannot read the env var or the config file (a
                # denied read, a headless run) still has the hook's own answer.
                self.assertIn(SESSION_NOTE, text, "the skill ignores the hook's note")
                self.assertIn(OVERRIDE_ALONE, text, "a set override must not fall back")

    def test_the_note_the_skills_name_is_what_the_hook_says(self):
        import load_scripta_context as hook
        self.assertIn(SESSION_NOTE, Path(hook.__file__).read_text(encoding="utf-8"))


class DigestLinearComesFromSettings(unittest.TestCase):
    """The Hub's Linear names live in one place: the Step 0.6 fallback.

    Anywhere else in the digest, a hard-coded workspace, team or label would
    send another team's tasks to the Hub's board.
    """

    def test_hub_linear_names_only_in_the_fallback(self):
        text = (SKILLS / "daily-digest" / "SKILL.md").read_text(encoding="utf-8")
        start = text.index("## Step 0.6")
        end = text.index("\n## ", start + 1)
        outside = text[:start] + text[end:]
        for name in ("tbhub", "TB Hub", "from-digest"):
            with self.subTest(name=name):
                self.assertIn(name, text[start:end])
                self.assertNotIn(name, outside)


class DigestWeeklyLaneIsASetting(unittest.TestCase):
    """The weekly lane feeds the Hub's weekly update, so it is a setting.

    The Hub's handbook keeps it on with no setting, any other handbook has it
    off unless its scripta.json turns it on, and Step 5c obeys that.
    """

    def section(self, heading):
        text = (SKILLS / "daily-digest" / "SKILL.md").read_text(encoding="utf-8")
        start = text.index(heading)
        return text[start:text.index("\n## ", start + 1)]

    def test_step_0_6_names_the_setting_and_both_defaults(self):
        step = self.section("## Step 0.6")
        self.assertIn('{ "weekly": { "enabled": true } }', step)
        self.assertIn("Step 5c runs, as it always has", step)
        self.assertIn("On any other handbook it is off", step)

    def test_step_5c_runs_only_when_step_0_6_has_it_on(self):
        step = self.section("## Step 5c")
        self.assertIn("where Step 0.6 has the weekly lane on", step)
        self.assertIn("When it is off, skip this step", step)


class SkillsNameNoHubRepoOutsideTheFallbacks(unittest.TestCase):
    """Another team installs scripta and starts its own handbook.

    Outside the documented fallbacks, no skill names the Hub's handbook repo or
    its GitHub org. The fallbacks are the default folder, the default folder in
    the noon schedule's code, the plugin's own repo, the digest's Step 0.6, and
    setup's "The Hub's defaults" section.
    The weekly update is built for the Hub and says so, and test files and the
    reference-check fixtures need real URLs, so those are skipped.
    """

    ALLOWED = ("~/PROJECTS/hub-scripta-handbook", '"PROJECTS" / "hub-scripta-handbook"',
               "team-blue-Hub/scripta")
    FALLBACK_SECTIONS = (("daily-digest/SKILL.md", "## Step 0.6"),
                         ("setup/SKILL.md", "## The Hub's defaults"))

    def test_hub_repo_names_only_in_the_fallbacks(self):
        found = []
        for path in sorted(SKILLS.rglob("*")):
            if not path.is_file() or path.suffix not in (".md", ".py"):
                continue
            rel = path.relative_to(SKILLS)
            if rel.parts[0] == "weekly-update" or path.name.startswith("test_") \
                    or "fixtures" in rel.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for skill, heading in self.FALLBACK_SECTIONS:
                if rel.as_posix() == skill:
                    start = text.index(heading)
                    end = text.index("\n## ", start + 1)
                    text = text[:start] + text[end:]
            for line in text.splitlines():
                rest = line
                for ok in self.ALLOWED:
                    rest = rest.replace(ok, "")
                if "hub-scripta-handbook" in rest or "team-blue-Hub" in rest:
                    found.append(f"{rel}: {line.strip()[:80]}")
        self.assertEqual(found, [])

    def test_setup_keeps_the_hub_default_in_its_section(self):
        text = (SKILLS / "setup" / "SKILL.md").read_text(encoding="utf-8")
        start = text.index("## The Hub's defaults")
        end = text.index("\n## ", start + 1)
        section = text[start:end]
        self.assertIn("`team-blue-Hub/hub-scripta-handbook`", section)
        self.assertIn("hub-scripta-handbook/blob/main/onboarding/setup.md", section)


if __name__ == "__main__":
    unittest.main()

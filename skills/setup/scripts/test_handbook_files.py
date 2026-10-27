"""Tests for handbook_files.py: a new handbook from the template, and the check.

Run from this folder: python3 -m unittest -v test_handbook_files
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import handbook_files as hf  # noqa: E402

HOOK = HERE.parents[2] / "hooks" / "load_scripta_context.py"
LINT = HERE.parents[1] / "curate" / "scripts" / "freshness_lint.py"
OWNER = "Alex Main (@alexmain)"


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = hf.main([str(a) for a in argv])
    return code, out.getvalue()


def create(folder, *extra):
    return run("create", folder, "--team", "Acme", "--owner", OWNER, "--date", "2026-10-23", *extra)


def frontmatter(path):
    """The page's frontmatter as a dict, reading a quoted value as a YAML string."""
    head = path.read_text(encoding="utf-8").split("\n---\n")[0].splitlines()[1:]
    found = {}
    for line in head:
        key, _, value = line.partition(": ")
        found[key] = json.loads(value) if value.startswith('"') else value
    return found


LINEAR = ("--linear-workspace", "acme", "--linear-team", "Acme Team", "--linear-label", "from-digest")


class Create(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.hb = self.root / "acme-scripta-handbook"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_new_folder_gets_every_needed_file_and_passes_the_check(self):
        code, out = create(self.hb)
        self.assertEqual(code, 0, out)
        for rel in hf.MUST + hf.GOOD:
            self.assertTrue((self.hb / rel).is_file(), rel)
            self.assertIn("created  %s" % rel, out)
        self.assertEqual(run("check", self.hb)[0], 0)

    def test_the_template_and_the_two_lists_name_the_same_files(self):
        listed = set(hf.MUST + hf.GOOD)
        written = {rel for rel, _ in hf.targets(with_status=False)}
        self.assertEqual(written, listed)

    def test_placeholders_are_filled(self):
        create(self.hb)
        for path in self.hb.rglob("*"):
            if path.is_file():
                self.assertNotIn("{{", path.read_text(encoding="utf-8"), path)
        self.assertIn("# Acme handbook", (self.hb / "index.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter(self.hb / "AGENTS.md")["owner"], OWNER)
        self.assertIn("last-verified: 2026-10-23", (self.hb / "page-format.md").read_text(encoding="utf-8"))

    def test_where_truth_lives_is_written_first(self):
        self.assertEqual(hf.targets(with_status=False)[0][0], "where-truth-lives.md")
        self.assertEqual(hf.targets(with_status=True)[0][0], "where-truth-lives.md")

    def test_a_create_that_stops_partway_can_be_run_again(self):
        real = hf.write_new
        calls = []

        def stops_on_the_third(folder, rel, text):
            calls.append(rel)
            if len(calls) == 3:
                raise OSError("disk full")
            return real(folder, rel, text)

        with mock.patch.object(hf, "write_new", stops_on_the_third):
            with self.assertRaises(OSError):
                create(self.hb)
        self.assertTrue((self.hb / "where-truth-lives.md").is_file())
        self.assertEqual(run("check", self.hb)[0], 1)
        code, out = create(self.hb)
        self.assertEqual(code, 0, out)
        self.assertIn("kept     where-truth-lives.md", out)
        self.assertEqual(run("check", self.hb)[0], 0)

    def test_names_with_a_colon_or_a_hash_stay_valid_frontmatter(self):
        team, owner = "R&D: Platform", "Ops #1 (@ops)"
        code, out = run("create", self.hb, "--team", team, "--owner", owner, "--date", "2026-10-23")
        self.assertEqual(code, 0, out)
        self.assertEqual(frontmatter(self.hb / "index.md")["title"], "R&D: Platform handbook, the index")
        for path in self.hb.rglob("*.md"):
            self.assertEqual(frontmatter(path)["owner"], owner, path)
        self.assertIn("# R&D: Platform handbook", (self.hb / "index.md").read_text(encoding="utf-8"))
        self.assertIn("The R&D: Platform team", (self.hb / "AGENTS.md").read_text(encoding="utf-8"))

    def test_a_filled_handbook_passes_the_freshness_lint(self):
        run("create", self.hb, "--team", "R&D: Platform", "--owner", "Ops #1 (@ops)",
            "--date", "2026-10-23", *LINEAR)
        done = subprocess.run([sys.executable, str(LINT), "--path", str(self.hb), "--strict"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_control_characters_in_a_name_are_refused(self):
        for team, owner in (("Acme\nowner: x", OWNER), ("Acme", "Alex\tMain")):
            code, out = run("create", self.hb, "--team", team, "--owner", owner)
            self.assertEqual(code, 2, out)
            self.assertIn("control characters", out)
        self.assertFalse(self.hb.exists())

    def test_agents_keeps_the_six_numbered_rules_the_skills_cite(self):
        create(self.hb)
        text = (self.hb / "AGENTS.md").read_text(encoding="utf-8")
        for n, words in ((1, "AI drafts"), (2, "Verify against the primary source"),
                         (3, "Point, don't copy"), (4, "append-only"),
                         (5, "owner and a `last-verified`"), (6, "short and plain")):
            self.assertRegex(text, r"\n%d\. \*\*[^\n]*%s" % (n, words))

    def test_the_settings_turn_the_plugin_on(self):
        create(self.hb)
        settings = json.loads((self.hb / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertTrue(settings["enabledPlugins"]["scripta@scripta-plugin"])
        self.assertIn("scripta-plugin", settings["extraKnownMarketplaces"])

    def test_without_linear_there_is_no_scripta_json_and_no_status(self):
        create(self.hb)
        self.assertFalse((self.hb / "scripta.json").exists())
        self.assertFalse((self.hb / "status.md").exists())
        self.assertFalse((self.hb / "linear").exists())

    def test_linear_writes_the_setting_and_a_status_page(self):
        code, out = create(self.hb, *LINEAR)
        self.assertEqual(code, 0, out)
        settings = json.loads((self.hb / "scripta.json").read_text(encoding="utf-8"))
        self.assertEqual(settings, {"linear": {"workspace": "acme", "team": "Acme Team",
                                               "label": "from-digest"}})
        self.assertIn("**Snapshot of 2026-10-23**", (self.hb / "status.md").read_text(encoding="utf-8"))

    def registry_rows(self):
        text = (self.hb / "where-truth-lives.md").read_text(encoding="utf-8")
        start = text.index("| The fact |")
        block = text[start:text.index("\n\n", start)]
        return block.splitlines()

    def test_with_linear_the_maps_name_status(self):
        create(self.hb, *LINEAR)
        rows = self.registry_rows()
        self.assertTrue(any("[`status.md`](status.md)" in r for r in rows), rows)
        self.assertTrue(all(r.startswith("|") for r in rows), rows)  # one unbroken table
        self.assertIn("[status.md](status.md)", (self.hb / "index.md").read_text(encoding="utf-8"))
        self.assertEqual(run("check", self.hb)[0], 0)

    def test_without_linear_the_maps_leave_status_out_and_the_table_whole(self):
        create(self.hb)
        rows = self.registry_rows()
        self.assertEqual(len(rows), 7, rows)  # header, separator, five rows
        self.assertNotIn("status.md", (self.hb / "where-truth-lives.md").read_text(encoding="utf-8"))
        self.assertNotIn("status.md", (self.hb / "index.md").read_text(encoding="utf-8"))

    def test_linear_added_later_says_the_maps_need_the_row(self):
        create(self.hb)
        code, out = create(self.hb, *LINEAR)
        self.assertEqual(code, 0, out)
        self.assertIn("created  status.md", out)
        self.assertIn("note     add status.md to where-truth-lives.md and index.md", out)

    def test_linear_needs_all_three_values(self):
        code, out = create(self.hb, "--linear-workspace", "acme")
        self.assertEqual(code, 2)
        self.assertIn("all three", out)
        self.assertFalse(self.hb.exists())

    def test_linear_keeps_the_other_settings(self):
        self.hb.mkdir()
        (self.hb / "where-truth-lives.md").write_text("# mine\n", encoding="utf-8")
        (self.hb / "scripta.json").write_text('{"weekly": {"enabled": false}}', encoding="utf-8")
        create(self.hb, *LINEAR)
        settings = json.loads((self.hb / "scripta.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["weekly"], {"enabled": False})
        self.assertEqual(settings["linear"]["team"], "Acme Team")

    def test_a_linear_already_set_gets_its_status_page_without_the_flags(self):
        create(self.hb, *LINEAR)
        (self.hb / "status.md").unlink()
        self.assertEqual(run("check", self.hb)[0], 1)
        code, out = create(self.hb)
        self.assertEqual(code, 0, out)
        self.assertIn("created  status.md", out)
        self.assertEqual(run("check", self.hb)[0], 0)

    def test_a_dangling_symlink_is_broken_for_check_and_create_alike(self):
        create(self.hb)
        outside = self.root / "outside.md"
        (self.hb / "AGENTS.md").unlink()
        (self.hb / "index.md").unlink()
        os.symlink(str(outside), str(self.hb / "AGENTS.md"))
        code, out = run("check", self.hb)
        self.assertEqual(code, 1)
        self.assertIn("broken   AGENTS.md (AGENTS.md is a link to nothing, or not a file)", out)
        code, out = create(self.hb)
        self.assertEqual(code, 2)
        self.assertIn("AGENTS.md is a link to nothing", out)
        self.assertFalse(outside.exists())
        self.assertFalse((self.hb / "index.md").exists())  # stopped before any write

    def test_a_link_to_a_real_file_is_ok_for_both(self):
        create(self.hb)
        real = self.root / "rules.md"
        real.write_text("# shared rules\n", encoding="utf-8")
        (self.hb / "AGENTS.md").unlink()
        os.symlink(str(real), str(self.hb / "AGENTS.md"))
        self.assertEqual(run("check", self.hb)[0], 0)
        code, out = create(self.hb)
        self.assertEqual(code, 0, out)
        self.assertIn("kept     AGENTS.md", out)
        self.assertEqual(real.read_text(encoding="utf-8"), "# shared rules\n")

    def test_a_dangling_scripta_json_is_broken_and_never_written_through(self):
        create(self.hb)
        outside = self.root / "outside.json"
        os.symlink(str(outside), str(self.hb / "scripta.json"))
        code, out = run("check", self.hb)
        self.assertEqual(code, 1)
        self.assertIn("scripta.json is not a JSON object", out)
        self.assertEqual(create(self.hb, *LINEAR)[0], 2)
        self.assertFalse(outside.exists())

    def test_scripta_json_linked_elsewhere_is_not_rewritten(self):
        create(self.hb)
        outside = self.root / "shared.json"
        outside.write_text('{"weekly": {"enabled": true}}', encoding="utf-8")
        os.symlink(str(outside), str(self.hb / "scripta.json"))
        code, out = create(self.hb, *LINEAR)
        self.assertEqual(code, 2)
        self.assertIn("never writes through one", out)
        self.assertEqual(outside.read_text(encoding="utf-8"), '{"weekly": {"enabled": true}}')

    def test_a_symlinked_folder_stops_create_before_any_write(self):
        self.hb.mkdir()
        (self.hb / "where-truth-lives.md").write_text("# mine\n", encoding="utf-8")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        os.symlink(str(elsewhere), str(self.hb / "decisions"))
        code, out = create(self.hb)
        self.assertEqual(code, 2)
        self.assertIn("decisions is not a plain folder", out)
        self.assertEqual(list(elsewhere.iterdir()), [])
        self.assertFalse((self.hb / "index.md").exists())

    def test_a_file_under_a_symlinked_folder_is_broken_for_check_too(self):
        self.hb.mkdir()
        (self.hb / "where-truth-lives.md").write_text("# mine\n", encoding="utf-8")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "README.md").write_text("# decisions\n", encoding="utf-8")
        os.symlink(str(elsewhere), str(self.hb / "decisions"))
        code, out = run("check", self.hb)
        self.assertEqual(code, 1)
        self.assertIn("broken   decisions/README.md (decisions is not a plain folder)", out)

    def test_a_file_where_a_folder_goes_stops_create(self):
        self.hb.mkdir()
        (self.hb / "where-truth-lives.md").write_text("# mine\n", encoding="utf-8")
        (self.hb / "people").write_text("not a folder\n", encoding="utf-8")
        code, out = run("check", self.hb)
        self.assertEqual(code, 1)
        self.assertIn("broken   people/README.md (people is not a plain folder)", out)
        code, out = create(self.hb)
        self.assertEqual(code, 2)
        self.assertIn("people is not a plain folder", out)

    def test_editor_and_finder_litter_in_the_template_is_skipped(self):
        for name in (".DS_Store", "AGENTS.md.swp", "index.md~"):
            self.assertTrue(hf.is_litter(name), name)
        self.assertFalse(hf.is_litter("AGENTS.md"))

    def test_it_never_overwrites_a_file(self):
        self.hb.mkdir()
        (self.hb / "where-truth-lives.md").write_text("# our registry\n", encoding="utf-8")
        (self.hb / "AGENTS.md").write_text("# our rules\n", encoding="utf-8")
        code, out = create(self.hb)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.hb / "AGENTS.md").read_text(encoding="utf-8"), "# our rules\n")
        self.assertEqual((self.hb / "where-truth-lives.md").read_text(encoding="utf-8"), "# our registry\n")
        self.assertIn("kept     AGENTS.md", out)
        self.assertIn("created  index.md", out)

    def test_it_refuses_a_folder_that_holds_other_files(self):
        self.hb.mkdir()
        (self.hb / "src").mkdir()
        (self.hb / "src" / "main.py").write_text("print(1)\n", encoding="utf-8")
        code, out = create(self.hb)
        self.assertEqual(code, 2)
        self.assertIn("is not a handbook", out)
        self.assertEqual(sorted(p.name for p in self.hb.iterdir()), ["src"])

    def test_a_fresh_clone_of_an_empty_repo_is_fine(self):
        self.hb.mkdir()
        (self.hb / ".git").mkdir()
        (self.hb / "README.md").write_text("# acme-scripta-handbook\n", encoding="utf-8")
        code, out = create(self.hb)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.hb / "README.md").read_text(encoding="utf-8"), "# acme-scripta-handbook\n")
        self.assertTrue((self.hb / "where-truth-lives.md").is_file())

    def test_a_folder_finder_opened_is_still_empty(self):
        self.hb.mkdir()
        (self.hb / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
        code, out = create(self.hb)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.hb / "where-truth-lives.md").is_file())

    def test_bad_date_and_empty_owner_are_refused(self):
        self.assertEqual(run("create", self.hb, "--team", "Acme", "--owner", OWNER, "--date", "23/10")[0], 2)
        self.assertEqual(run("create", self.hb, "--team", "Acme", "--owner", "  ")[0], 2)
        self.assertFalse(self.hb.exists())


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hb = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_empty_folder_lists_every_must_have_as_missing(self):
        code, out = run("check", self.hb)
        self.assertEqual(code, 1)
        for rel in hf.MUST:
            self.assertIn("missing  %s (must-have)" % rel, out)
        self.assertIn("missing  people/README.md (good to have)", out)

    def test_check_writes_nothing(self):
        run("check", self.hb)
        self.assertEqual(list(self.hb.iterdir()), [])

    def test_only_a_good_to_have_missing_still_passes(self):
        create(self.hb)
        (self.hb / "people" / "README.md").unlink()
        code, out = run("check", self.hb)
        self.assertEqual(code, 0, out)
        self.assertIn("missing  people/README.md (good to have)", out)

    def test_a_broken_good_to_have_path_fails_like_create_refuses_it(self):
        create(self.hb)
        (self.hb / "people" / "README.md").unlink()
        (self.hb / "people" / "README.md").mkdir()  # a folder where a file belongs
        code, out = run("check", self.hb)
        self.assertEqual(code, 1, out)
        self.assertIn("broken   people/README.md", out)
        self.assertEqual(create(self.hb)[0], 2)

    def test_with_linear_set_status_is_needed(self):
        create(self.hb, *LINEAR)
        self.assertEqual(run("check", self.hb)[0], 0)
        (self.hb / "status.md").unlink()
        code, out = run("check", self.hb)
        self.assertEqual(code, 1)
        self.assertIn("missing  status.md (needed by the Linear status lane)", out)

    def test_a_broken_scripta_json_is_named(self):
        create(self.hb)
        (self.hb / "scripta.json").write_text("{not json", encoding="utf-8")
        code, out = run("check", self.hb)
        self.assertEqual(code, 1)
        self.assertIn("scripta.json is not a JSON object", out)

    def test_no_folder(self):
        self.assertEqual(run("check", self.hb / "nope")[0], 2)


class TheHooksSeeANewHandbook(unittest.TestCase):
    """The new handbook is one the hooks find, and its maps fit the budget."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hb = Path(self.tmp.name) / "acme-scripta-handbook"
        create(self.hb)
        spec = importlib.util.spec_from_file_location("load_scripta_context", HOOK)
        self.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hook)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_hook_locates_it(self):
        old = os.environ.get("SCRIPTA_HANDBOOK_PATH")
        os.environ["SCRIPTA_HANDBOOK_PATH"] = str(self.hb)
        try:
            self.assertEqual(self.hook.locate_repo(), self.hb)
        finally:
            if old is None:
                del os.environ["SCRIPTA_HANDBOOK_PATH"]
            else:
                os.environ["SCRIPTA_HANDBOOK_PATH"] = old

    def test_the_maps_reach_a_session_whole(self):
        report = self.hook.maps_payload_report(self.hb)
        self.assertTrue(report["ok"], report["what"])
        self.assertIn("Why we decided something", report["body"])

    def test_the_budget_check_passes(self):
        done = subprocess.run([sys.executable, str(HOOK), "--check-maps", str(self.hb)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()

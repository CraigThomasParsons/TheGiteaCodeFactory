"""Outside-in tests for scripts/install-skills.py.

Contract: copies every directory under the kit's skills/ that has a SKILL.md
into --destination, never replacing an existing entry. The source is the
skills/ folder next to the helper's own scripts/ folder.
"""

import os
import unittest

from support import HelperTestCase, base_env, run_tool, tool_path


def source_skills():
    root = tool_path("install_skills").parent.parent / "skills"
    return sorted(p.name for p in root.iterdir() if (p / "SKILL.md").is_file())


def tree(path):
    files = set()
    for parent, dirs, names in os.walk(path):
        for name in names:
            files.add(os.path.relpath(os.path.join(parent, name), path))
    return files


class InstallSkillsTest(HelperTestCase):
    def install(self, destination):
        return run_tool("install_skills", ["--destination", destination], env=base_env(self.home))

    def test_fresh_install_copies_every_skill(self):
        names = source_skills()
        self.assertTrue(names)
        destination = self.tmp / "target" / ".agents" / "skills"
        result = self.install(destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f"Installed {len(names)} skills in {destination}; existing agent settings unchanged.\n")
        self.assertEqual(sorted(os.listdir(destination)), names)
        source = tool_path("install_skills").parent.parent / "skills"
        for name in names:
            expected = {f for f in tree(source / name) if "__pycache__" not in f and not f.endswith(".pyc")}
            self.assertEqual(tree(destination / name), expected, name)
            self.assertEqual((destination / name / "SKILL.md").read_bytes(),
                             (source / name / "SKILL.md").read_bytes())

    def test_no_bytecode_is_copied(self):
        destination = self.tmp / "skills"
        self.assertEqual(self.install(destination).returncode, 0)
        leftovers = [f for f in tree(destination) if "__pycache__" in f or f.endswith(".pyc")]
        self.assertEqual(leftovers, [])

    def test_existing_skill_is_preserved_and_nothing_is_written(self):
        names = source_skills()
        destination = self.tmp / "skills"
        (destination / names[0]).mkdir(parents=True)
        (destination / names[0] / "mine.txt").write_text("keep me")
        result = self.install(destination)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, f"Existing skills preserved; choose an empty destination: {names[0]}\n")
        self.assertEqual(os.listdir(destination), [names[0]])
        self.assertEqual(os.listdir(destination / names[0]), ["mine.txt"])

    def test_all_conflicts_are_listed_including_dangling_symlinks(self):
        names = source_skills()
        destination = self.tmp / "skills"
        destination.mkdir()
        (destination / names[-1]).write_text("a file")
        if len(names) > 1:
            (destination / names[0]).symlink_to(self.tmp / "missing")
        result = self.install(destination)
        self.assertEqual(result.returncode, 1)
        listed = result.stderr.strip().split(": ", 1)[1].split(", ")
        self.assertEqual(listed, sorted({names[0], names[-1]}))

    def test_unrelated_entries_are_left_alone(self):
        destination = self.tmp / "skills"
        destination.mkdir()
        (destination / "someone-elses-skill").mkdir()
        result = self.install(destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("someone-elses-skill", os.listdir(destination))

    def test_destination_is_required(self):
        result = run_tool("install_skills", [], env=base_env(self.home))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(os.listdir(self.home), [])


if __name__ == "__main__":
    unittest.main()

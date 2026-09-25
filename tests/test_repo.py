"""The repository itself is part of the product: a person installs it in one line, so the
manifests have to be valid, every skill a skill promises has to exist, and nothing here may ask
for a key, a payment or a `pip install`. These checks fail loudly rather than surprising someone
after publication."""

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = ["setup", "take", "push", "brief", "watch", "handoff", "scout"]
SCRIPTS = ["tracker.py", "brief.py", "guard.py", "routine.py"]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class Manifests(unittest.TestCase):
    def test_plugin_json(self):
        data = json.loads(read(".claude-plugin", "plugin.json"))
        self.assertEqual(data["name"], "chasecall")
        self.assertEqual(data["license"], "Apache-2.0")
        for key in ("description", "version", "author", "homepage", "repository"):
            self.assertIn(key, data)
        self.assertIn("vadimchernets/chasecall", data["repository"])

    def test_marketplace_json(self):
        data = json.loads(read(".claude-plugin", "marketplace.json"))
        self.assertEqual(data["name"], "chasecall")
        plugins = data["plugins"]
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["name"], "chasecall")
        self.assertEqual(plugins[0]["source"], "./")

    def test_hooks_json(self):
        data = json.loads(read("hooks", "hooks.json"))["hooks"]
        self.assertIn("SessionStart", data)
        self.assertIn("PreToolUse", data)
        flat = json.dumps(data)
        self.assertIn("tracker.py", flat)
        self.assertIn("due --brief", flat)
        self.assertIn("guard.py", flat)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", flat)


class Files(unittest.TestCase):
    def test_every_skill_exists_with_frontmatter(self):
        for name in SKILLS:
            text = read("skills", name, "SKILL.md")
            self.assertTrue(text.startswith("---\n"), name)
            head = text.split("---", 2)[1]
            self.assertIn("name: " + name, head)
            self.assertIn("description:", head)
            self.assertIn("## Never", text, name)

    def test_scripts_and_legal_files_exist(self):
        for name in SCRIPTS:
            self.assertTrue(os.path.exists(os.path.join(ROOT, "scripts", name)), name)
        for name in ("README.md", "LICENSE", "NOTICE", "SECURITY.md", "CONTRIBUTING.md",
                     "CITATION.cff", ".gitignore"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, name)), name)

    def test_readme_names_the_one_line_install(self):
        readme = read("README.md")
        self.assertIn("/plugin install chasecall --marketplace vadimchernets/chasecall", readme)
        self.assertIn("/chasecall:setup", readme)


class NothingWeDoNotWant(unittest.TestCase):
    """No keys, no paid dependencies, no install step, no personal paths, no other product's name."""

    def walk(self):
        skip = {".git", "__pycache__", ".github"}
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in skip]
            for name in files:
                if name.endswith((".md", ".py", ".json", ".cff", ".txt")):
                    path = os.path.join(base, name)
                    if os.path.basename(path) == "test_repo.py":
                        continue
                    with open(path, encoding="utf-8") as handle:
                        yield os.path.relpath(path, ROOT), handle.read()

    def test_no_pip_install_and_no_third_party_import(self):
        # A real install step is a line that starts with the command; the README is allowed to
        # promise the opposite in prose ("no `pip install`").
        command = re.compile(r"^\s*(sudo\s+)?(python3?\s+-m\s+)?pip\s+install", re.M)
        for rel, text in self.walk():
            found = command.search(text)
            self.assertIsNone(found, "%s: %s" % (rel, found.group(0) if found else ""))
        for name in SCRIPTS:
            text = read("scripts", name)
            for line in text.splitlines():
                if line.startswith("import ") or line.startswith("from "):
                    module = re.split(r"[ .]", line.split()[1])[0]
                    self.assertIn(module, {
                        "argparse", "json", "os", "re", "sqlite3", "sys", "datetime", "pathlib",
                        "shutil", "subprocess", "textwrap", "typing", "platform", "stat", "time",
                        "collections", "contextlib", "unicodedata", "__future__",
                        "tracker", "brief", "guard", "routine",  # our own modules
                    }, "%s imports %s" % (name, module))

    def test_no_secrets_or_personal_paths(self):
        bad = re.compile(r"(sk-[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{8,}|/Users/[a-z]+/Desktop|"
                         r"api[_-]?key\s*[:=]\s*[\"'][^\"']+[\"'])", re.I)
        for rel, text in self.walk():
            found = bad.search(text)
            self.assertIsNone(found, "%s: %s" % (rel, found.group(0) if found else ""))

    def test_no_other_products_name(self):
        other = re.compile(r"\bwajo\b", re.I)
        for rel, text in self.walk():
            self.assertIsNone(other.search(text), rel)


if __name__ == "__main__":
    unittest.main()

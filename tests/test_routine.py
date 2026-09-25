"""The background has to be honest: on a Mac we install nothing (a launchd agent is cut off by the system's
privacy protection the moment it touches the person's files), we hand over the prompt for Claude Code's own
Routine, and we schedule something only where it really works and only when the person says yes.

No network, no writing outside a temporary folder - and nothing installed anywhere by these tests.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import routine  # noqa: E402
import tracker  # noqa: E402

FAKE_CLAUDE = "/usr/local/bin/claude"


class Base(unittest.TestCase):
    KEYS = ("CHASECALL_DB", "CHASECALL_NOW", "CHASECALL_LANG", "CHASECALL_CLAUDE_BIN")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {key: os.environ.get(key) for key in self.KEYS}
        for key in self.KEYS:
            os.environ.pop(key, None)
        self.db = os.path.join(self.tmp.name, "chasecall.db")
        os.environ["CHASECALL_DB"] = self.db

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def cli(self, *args, **kwargs):
        env = dict(os.environ)
        env.update(kwargs.get("env_extra") or {})
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "routine.py")] + list(args),
                              capture_output=True, text=True, env=env, timeout=60)
        try:
            data = json.loads(done.stdout)
        except ValueError:
            data = None
        return done.returncode, data, done.stdout, done.stderr

    def files_made(self):
        made = []
        for folder, _, names in os.walk(self.tmp.name):
            made += [os.path.join(folder, name) for name in names]
        return sorted(os.path.relpath(path, self.tmp.name) for path in made)


class NothingIsInstalledByItself(unittest.TestCase):
    def test_the_script_cannot_quietly_grow_a_launchd_agent_again(self):
        with open(os.path.join(SCRIPTS, "routine.py"), "r", encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("plistlib", "launchctl", "plistlib.dumps", "LaunchAgents/"):
            self.assertNotIn(forbidden, source, forbidden)


class Status(Base):
    def test_it_does_not_fall_over_when_claude_is_not_in_path(self):
        data = routine.status(binary=None, platform="darwin")
        self.assertFalse(data["claude_found"])
        self.assertIn("will not set up a background run", data["warning"])
        self.assertIn("next session", data["warning"])
        self.assertTrue(routine.render_status(data, "en"))

    def test_the_command_line_says_it_plainly_with_an_empty_path(self):
        code, _, out, err = self.cli("status", env_extra={"PATH": ""})
        self.assertEqual((code, err.strip()), (0, ""))
        self.assertIn("claude in PATH: no", out)

    def test_on_a_mac_it_promises_nothing_and_points_at_the_routine(self):
        data = routine.status(lang="en", platform="darwin", binary=FAKE_CLAUDE)
        self.assertFalse(data["installs_anything"])
        self.assertIn("Routines -> New routine -> Local", data["how_to"])
        self.assertIn("install nothing by myself", data["note"])
        self.assertNotIn("windows_command", data)

    def test_it_reports_our_own_database_and_the_last_sweep(self):
        conn = tracker.connect()
        try:
            task = tracker.add(conn, "Refund", "money back", first_step_now=True)["task"]
            tracker.log(conn, task["id"], "sent", "first letter")
        finally:
            conn.close()
        data = routine.status(binary=FAKE_CLAUDE)
        self.assertEqual(data["db"], self.db)
        self.assertTrue(data["db_exists"])
        self.assertEqual(data["open_tasks"], 1)
        self.assertIsNotNone(data["last_sweep"])
        self.assertIn("last sweep:", routine.render_status(data, "en"))

    def test_an_absent_database_is_reported_not_created(self):
        data = routine.status(binary=FAKE_CLAUDE)
        self.assertFalse(data["db_exists"])
        self.assertIsNone(data["last_sweep"])
        self.assertEqual(data["open_tasks"], 0)
        self.assertFalse(os.path.exists(self.db))         # asking a question creates nothing
        self.assertIn("never", routine.render_status(data, "en"))

    def test_both_languages_explain_the_same_four_steps(self):
        english = routine.status(lang="en", platform="darwin", binary=FAKE_CLAUDE)
        russian = routine.status(lang="ru", platform="darwin", binary=FAKE_CLAUDE)
        self.assertIn("Open the Claude app", english["how_to"])
        self.assertIn("Откройте приложение Claude", russian["how_to"])
        self.assertIn("Routines -> New routine -> Local", russian["how_to"])   # the buttons keep their names
        self.assertIn("фон не поставлю", routine.status(lang="ru", binary=None)["warning"])


class Prompt(Base):
    def test_the_prompt_carries_the_real_path_of_the_tracker(self):
        code, data, out, _ = self.cli("prompt", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(data["tracker"], os.path.join(SCRIPTS, "tracker.py"))
        self.assertIn(os.path.join(SCRIPTS, "tracker.py") + " due --json", data["prompt"])
        self.assertIn("Bash(python3 %s*)" % os.path.join(SCRIPTS, "tracker.py"), data["allowed_tools"])
        self.assertIn("tracker.py", self.cli("prompt")[2])

    def test_the_prompt_repeats_the_rules_the_person_is_trusting_us_with(self):
        text = routine.prompt_text()
        self.assertIn("Send nothing, pay nothing, cancel nothing, delete nothing", text)
        self.assertIn("human <id>", text)
        self.assertIn("22:00 and 08:00", text)
        self.assertIn("--evidence", text)
        self.assertEqual(text.count("\n"), 0)             # one line, so it pastes into a Routine box


class Windows(Base):
    def test_without_yes_nothing_is_scheduled_and_nothing_is_written(self):
        data = routine.windows(yes=False, platform="win32", binary=FAKE_CLAUDE)
        self.assertFalse(data["installed"])
        self.assertIn("nothing is scheduled without --yes", data["reason"])
        self.assertIn("schtasks", data["command"])
        self.assertIn("/tn", data["argv"])
        self.assertEqual(self.files_made(), [])

    def test_the_command_says_how_often_and_what_it_runs(self):
        data = routine.windows(yes=False, platform="win32", binary=FAKE_CLAUDE, hours=12)
        self.assertEqual(data["argv"][-3:], ["/mo", "12", "/f"])
        self.assertIn("/sc", data["argv"])
        self.assertIn(FAKE_CLAUDE, data["command"])
        self.assertIn("--allowedTools", data["command"])

    def test_a_yes_on_a_mac_still_runs_no_schtasks(self):
        data = routine.windows(yes=True, platform="win32", binary=FAKE_CLAUDE)
        self.assertFalse(data["installed"])
        self.assertIn("not running schtasks on", data["reason"])
        self.assertEqual(self.files_made(), [])

    def test_off_windows_it_sends_the_person_to_the_routine_instead(self):
        data = routine.windows(yes=True, platform="darwin", binary=FAKE_CLAUDE)
        self.assertFalse(data["installed"])
        self.assertIn("Routine", data["reason"] + data["how_to"])

    def test_without_claude_there_is_nothing_to_schedule(self):
        data = routine.windows(yes=True, platform="win32", binary=None)
        self.assertFalse(data["ok"])
        self.assertFalse(data["installed"])
        self.assertIn("next session", data["reason"])
        self.assertEqual(self.cli("windows", "--platform", "win32", "--yes", env_extra={"PATH": ""})[0], 3)


class Cron(Base):
    def test_a_line_to_copy_and_nothing_else(self):
        data = routine.cron(platform="linux", binary=FAKE_CLAUDE)
        self.assertFalse(data["installed"])
        self.assertTrue(data["cron_line"].startswith("0 */6 * * * "))
        self.assertIn("tracker.py", data["cron_line"])
        self.assertIn("I do not touch your crontab", data["reason"])
        self.assertEqual(self.files_made(), [])

    def test_the_interval_reaches_the_line(self):
        self.assertTrue(routine.cron(platform="linux", binary=FAKE_CLAUDE, hours=24)["cron_line"]
                        .startswith("0 */24 * * * "))

    def test_the_quoting_survives_an_apostrophe_in_the_prompt(self):
        line = routine.cron_line("/usr/bin/claude")
        self.assertNotIn("'\"'", line.split(" -p ")[0])
        self.assertIn("'/usr/bin/claude'", line)

    def test_linux_status_offers_the_line_too(self):
        data = routine.status(platform="linux", binary=FAKE_CLAUDE)
        self.assertIn("cron_line", data)
        self.assertIn("crontab line (put it in yourself)", routine.render_status(data, "en"))


class CommandLine(Base):
    def test_every_command_answers_in_both_shapes_and_leaves_no_trace(self):
        for args in (["status"], ["status", "--lang", "ru"], ["prompt"], ["cron"],
                     ["windows", "--platform", "win32"], ["--lang", "ru", "status"]):
            code, _, out, err = self.cli(*args, env_extra={"CHASECALL_CLAUDE_BIN": FAKE_CLAUDE})
            self.assertEqual((code, err.strip()), (0, ""), args)
            self.assertTrue(out.strip(), args)
        for args in (["status", "--json"], ["prompt", "--json"], ["cron", "--json"]):
            code, data, _, _ = self.cli(*args, env_extra={"CHASECALL_CLAUDE_BIN": FAKE_CLAUDE})
            self.assertEqual((code, data["ok"]), (0, True), args)
        self.assertEqual(self.files_made(), [])
        self.assertEqual(self.cli("status", "--lang", "klingon")[0], 2)


if __name__ == "__main__":
    unittest.main()

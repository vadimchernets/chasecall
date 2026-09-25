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

    def test_the_screen_speaks_the_persons_language_all_the_way_down(self):
        """The four steps were translated and the five lines above them were not, so a Russian reader got
        `claude in PATH:` and `last sweep: never` over the top of their own instructions."""
        russian = routine.render_status(routine.status(lang="ru", binary=None), "ru")
        self.assertIn("файл с делами:", russian)
        self.assertIn("дел в работе:", russian)
        self.assertIn("ни разу", russian)
        for english in ("claude in PATH", "database:", "tasks alive", "last sweep", "never"):
            self.assertNotIn(english, russian, english)
        self.assertIn("claude in PATH", routine.render_status(routine.status(binary=None), "en"))

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
        self.assertIn("Never send, call, pay, cancel or delete anything", text)
        self.assertIn("human <id>", text)
        self.assertIn("22:00-08:00", text)
        self.assertEqual(text.count("\n"), 0)             # one line, so it pastes into a Routine box

    def test_the_background_run_only_prepares_and_never_spends_an_attempt(self):
        """The skill forbids sending, so the prompt must not tell the routine to count a letter as sent:
        three quiet mornings would otherwise use up all three attempts with nothing posted."""
        text = routine.prompt_text()
        self.assertIn("log <id> note", text)
        self.assertIn("never run `wait`", text)
        self.assertNotIn("log <id> sent", text.replace("never run `wait` or `log <id> sent`", ""))
        self.assertNotIn("--for", text)

    def test_the_prompt_and_the_watch_skill_tell_the_same_story(self):
        with open(os.path.join(ROOT, "skills", "watch", "SKILL.md"), "r", encoding="utf-8") as handle:
            skill = handle.read()
        text = routine.prompt_text()
        for promise in ("log <id> note", "human <id>"):
            self.assertIn(promise, skill, promise)
            self.assertIn(promise, text, promise)
        self.assertNotIn("log <id> sent", skill)


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

    def test_nobody_on_a_mac_is_shown_a_windows_command_to_copy(self):
        """`routine.py windows` printed the `schtasks /create ...` line first, whatever machine it was run on -
        an instruction the person cannot follow, in front of somebody who does not know that."""
        if sys.platform.startswith("win"):
            self.skipTest("on Windows the command is exactly what should be shown")
        code, _, out, err = self.cli("windows", "--lang", "ru", env_extra={"CHASECALL_CLAUDE_BIN": FAKE_CLAUDE})
        self.assertEqual((code, err.strip()), (0, ""))
        self.assertNotIn("schtasks", out)
        self.assertNotIn("--allowedTools", out)
        self.assertIn("это для Windows", out)
        self.assertIn("Routines -> New routine -> Local", out)
        code, data, out, _ = self.cli("windows", "--json", env_extra={"CHASECALL_CLAUDE_BIN": FAKE_CLAUDE})
        self.assertIn("schtasks", data["command"])     # still there for a machine that asks in JSON

    def test_without_claude_there_is_nothing_to_schedule(self):
        data = routine.windows(yes=True, platform="win32", binary=None)
        self.assertFalse(data["ok"])
        self.assertFalse(data["installed"])
        self.assertIn("next session", data["reason"])


class NoCron(Base):
    """`routine.py cron` and `cron_line()` were in here, unreachable from any skill, while the README sold the
    absence of cron as a feature ("No cron, nothing hidden"). Code that contradicts the promise is the promise
    that goes, so the code went instead."""

    def test_there_is_no_cron_anywhere_in_the_script(self):
        with open(os.path.join(SCRIPTS, "routine.py"), "r", encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("crontab", "cron_line", "*/%d * * *"):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertFalse(hasattr(routine, "cron"))
        self.assertFalse(hasattr(routine, "cron_line"))

    def test_the_command_line_does_not_answer_to_cron(self):
        self.assertEqual(self.cli("cron")[0], 2)

    def test_on_linux_status_says_what_it_can_and_offers_no_line_to_paste(self):
        data = routine.status(platform="linux", binary=FAKE_CLAUDE)
        self.assertNotIn("cron_line", data)
        self.assertIn("Routines -> New routine -> Local", routine.render_status(data, "en"))


class NothingPretendsToBeAnotherComputer(Base):
    """`--platform` let anything on the command line make the script describe a machine the person is not
    sitting at. It stays a named argument of the functions - the tests ask "and on Windows?" - and is gone from
    the command line."""

    def test_the_flags_only_the_tests_ever_used_are_off_the_command_line(self):
        for args in (["status", "--platform", "win32"], ["status", "--interval-hours", "12"],
                     ["windows", "--platform", "win32"]):
            self.assertEqual(self.cli(*args)[0], 2, args)
        # `platform=` stays a named argument of the functions, and the Windows tests above are what use it:
        # they ask "and what would you say on Windows?". A test that only asked the function to hand its own
        # argument back ("and does `platform="win32"` still say win32?") stood here and proved nothing at all.


class CommandLine(Base):
    def test_every_command_answers_in_both_shapes_and_leaves_no_trace(self):
        for args in (["status"], ["status", "--lang", "ru"], ["prompt"], ["windows"],
                     ["--lang", "ru", "status"]):
            code, _, out, err = self.cli(*args, env_extra={"CHASECALL_CLAUDE_BIN": FAKE_CLAUDE})
            self.assertEqual((code, err.strip()), (0, ""), args)
            self.assertTrue(out.strip(), args)
        for args in (["status", "--json"], ["prompt", "--json"]):
            code, data, _, _ = self.cli(*args, env_extra={"CHASECALL_CLAUDE_BIN": FAKE_CLAUDE})
            self.assertEqual((code, data["ok"]), (0, True), args)
        self.assertEqual(self.files_made(), [])
        self.assertEqual(self.cli("status", "--lang", "klingon")[0], 2)

    def test_the_watch_skill_really_calls_status_so_the_russian_words_can_be_reached(self):
        """`status` and `--lang` were written and then never called from anywhere: every Russian string in this
        script was unreachable. Step 1 of the skill runs it now, in the person's language."""
        with open(os.path.join(ROOT, "skills", "watch", "SKILL.md"), "r", encoding="utf-8") as handle:
            skill = handle.read()
        self.assertIn("routine.py status --lang", skill)
        self.assertIn("Откройте приложение Claude", routine.status(lang="ru", binary=FAKE_CLAUDE)["how_to"])


if __name__ == "__main__":
    unittest.main()

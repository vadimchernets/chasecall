"""The brief is the screen the person actually reads, so it has to be true in both languages and never hide the
one line that matters: what we cannot do without them.

No network, no writing outside a temporary folder.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import brief  # noqa: E402
import tracker  # noqa: E402

NOW = "2026-09-24T14:00:00+00:00"
DAY = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)      # only the hour is read: daytime
NIGHT = datetime(2026, 9, 24, 23, 30, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    KEYS = ("CHASECALL_DB", "CHASECALL_NOW", "CHASECALL_LANG")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {key: os.environ.get(key) for key in self.KEYS}
        for key in self.KEYS:
            os.environ.pop(key, None)
        self.db = os.path.join(self.tmp.name, "chasecall.db")
        os.environ["CHASECALL_DB"] = self.db
        os.environ["CHASECALL_NOW"] = NOW                     # a frozen clock, so the counts cannot drift
        self.conn = tracker.connect()

    def tearDown(self):
        self.conn.close()
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def cli(self, *args, **kwargs):
        env = dict(os.environ)
        env.update(kwargs.get("env_extra") or {})
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "brief.py")] + list(args),
                              capture_output=True, text=True, env=env, timeout=60)
        try:
            data = json.loads(done.stdout)
        except ValueError:
            data = None
        return done.returncode, data, done.stdout, done.stderr

    def collect(self, local=DAY):
        return brief.collect(self.conn, local=local)


class EmptyDatabase(Base):
    def test_an_empty_list_invites_instead_of_showing_four_empty_boxes(self):
        data = self.collect()
        self.assertEqual(data["counts"], {"done_24h": 0, "waiting": 0, "needs_you": 0, "mine_today": 0})
        english = brief.render(data, "en")
        russian = brief.render(data, "ru")
        self.assertIn("chase <the thing>", english)
        self.assertIn("добейся", russian)
        self.assertNotIn("Waiting for an answer", english)

    def test_the_command_line_survives_an_empty_database(self):
        for args in (["--lang", "en"], ["--lang", "ru"], ["--json"]):
            code, _, out, err = self.cli(*args)
            self.assertEqual((code, err.strip()), (0, ""), args)
            self.assertTrue(out.strip())


class FourSections(Base):
    def setUp(self):
        super().setUp()
        self.closed = tracker.add(self.conn, "Visa appointment", "a date in the calendar",
                                  counterpart="visa@centre.example")["task"]
        tracker.done(self.conn, self.closed["id"], "appointment 12 Oct, letter in the inbox")
        self.waiting = tracker.add(self.conn, "Refund for order 1182", "the money is back on the card",
                                   counterpart="support@shop.example", first_step_now=True)["task"]
        tracker.wait(self.conn, self.waiting["id"], "48h")
        self.yours = tracker.add(self.conn, "Bank card block", "the card works again",
                                 channel="phone", counterpart="+1 555 0199")["task"]
        tracker.human(self.conn, self.yours["id"], "call the bank, code word is the dog's name")
        self.mine = tracker.add(self.conn, "Broken heater", "a repair man on a named day",
                                counterpart="care@landlord.example", first_step_now=True)["task"]

    def test_every_task_lands_in_exactly_the_right_section(self):
        data = self.collect()
        self.assertEqual(data["counts"], {"done_24h": 1, "waiting": 1, "needs_you": 1, "mine_today": 1})
        self.assertEqual(data["done_24h"][0]["id"], self.closed["id"])
        self.assertEqual(data["waiting"][0]["id"], self.waiting["id"])
        self.assertEqual(data["needs_you"][0]["id"], self.yours["id"])
        self.assertEqual(data["mine_today"][0]["id"], self.mine["id"])

    def test_what_was_closed_yesterday_is_no_longer_news(self):
        self.conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?",
                          ("2026-09-22T09:00:00+00:00", self.closed["id"]))
        self.conn.commit()
        self.assertEqual(self.collect()["counts"]["done_24h"], 0)

    def test_a_task_due_in_three_days_is_not_mine_today(self):
        tracker.add(self.conn, "Insurance papers", "the policy in the mail", every="3d")
        self.assertEqual(self.collect()["counts"]["mine_today"], 1)

    def test_a_task_out_of_attempts_moves_to_the_person_even_without_the_human_command(self):
        for _ in range(3):
            tracker.wait(self.conn, self.mine["id"], "1m")
        data = self.collect()
        ids = [task["id"] for task in data["needs_you"]]
        self.assertIn(self.mine["id"], ids)
        self.assertNotIn(self.mine["id"], [task["id"] for task in data["mine_today"]])
        self.assertIn("attempts used up", brief.render(data, "en"))
        self.assertIn("попытки кончились", brief.render(data, "ru"))

    def test_both_languages_show_the_same_tasks_in_their_own_words(self):
        data = self.collect()
        english, russian = brief.render(data, "en"), brief.render(data, "ru")
        for text in (english, russian):
            for title in ("Visa appointment", "Refund for order 1182", "Bank card block", "Broken heater"):
                self.assertIn(title, text)
            self.assertIn("call the bank", text)
        self.assertIn("Done in the last 24 hours (1)", english)
        self.assertIn("Needs you (1)", english)
        self.assertIn("Сделано за сутки (1)", russian)
        self.assertIn("Нужно от вас (1)", russian)
        self.assertNotIn("Сделано", english)
        self.assertNotIn("Done in the last", russian)

    def test_the_waiting_line_says_when_we_come_back_and_which_attempt_it_is(self):
        text = brief.render(self.collect(), "en")
        self.assertIn("next step 2026-09-26", text)
        self.assertIn("attempt 1/3", text)

    def test_the_last_line_always_answers_what_do_i_have_to_do(self):
        self.assertIn("1 task(s) wait for your move", brief.render(self.collect(), "en"))
        tracker.done(self.conn, self.yours["id"], "the bank unblocked it on the phone")
        self.assertIn("nothing is waiting on you", brief.render(self.collect(), "en"))
        self.assertIn("от вас сейчас ничего не нужно", brief.render(self.collect(), "ru"))

    def test_at_night_the_brief_says_it_is_not_writing_to_anyone(self):
        self.assertTrue(self.collect(local=NIGHT)["night"])
        self.assertIn("I am not writing to anyone now", brief.render(self.collect(local=NIGHT), "en"))
        self.assertIn("сейчас никому не пишу", brief.render(self.collect(local=NIGHT), "ru"))
        self.assertNotIn("not writing to anyone", brief.render(self.collect(local=DAY), "en"))

    def test_json_carries_the_same_numbers_as_the_screen(self):
        code, data, _, _ = self.cli("--json")
        self.assertEqual(code, 0)
        self.assertEqual(data["counts"]["needs_you"], 1)
        self.assertEqual(sorted(data.keys()),
                         ["counts", "date", "done_24h", "mine_today", "needs_you", "night", "now", "ok", "waiting"])

    def test_the_language_flag_is_the_only_way_to_switch_and_a_wrong_one_is_refused(self):
        self.assertIn("Needs you", self.cli("--lang", "en")[2])
        self.assertIn("Нужно от вас", self.cli("--lang", "ru")[2])
        self.assertIn("Нужно от вас", self.cli(env_extra={"CHASECALL_LANG": "ru"})[2])
        self.assertEqual(self.cli("--lang", "klingon")[0], 2)


if __name__ == "__main__":
    unittest.main()

"""The brief is the screen the person actually reads, so it has to be true in both languages and never hide the
one line that matters: what we cannot do without them.

And it is the one thing Chasecall can put outside the computer. `--to` leaves it in a folder that syncs to
Google Drive or Dropbox, with the titles of the tasks, the counterparts, the phone numbers and the notes in it -
so it may not be written until the person has said yes to that folder, it is written 0600 like the database, and
a file of the same name that is not ours is left alone and named out loud.

No network, no writing outside a temporary folder.
"""
import json
import os
import stat
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
import inbox  # noqa: E402
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
        self.root = os.path.realpath(self.tmp.name)           # what we remember of a folder is its real path
        self.db = os.path.join(self.root, "chasecall.db")
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


class FolderBase(Base):
    def setUp(self):
        super().setUp()
        self.yours = tracker.add(self.conn, "Bank card block", "the card works again",
                                 channel="phone", counterpart="+1 555 0199")["task"]
        tracker.human(self.conn, self.yours["id"], "call the bank, code word is the dog's name")
        self.folder = os.path.join(self.root, "From the phone")
        os.makedirs(self.folder)

    def agree(self, folder=None):
        """The person has been asked, in an earlier session, and said yes."""
        conn = inbox.connect()
        try:
            inbox.set_setting(conn, brief.CONSENT_KEY % (folder or self.folder), "yes")
        finally:
            conn.close()

    def read_file(self, name, folder=None):
        with open(os.path.join(folder or self.folder, name), encoding="utf-8") as handle:
            return handle.read()


class NothingLeavesTheComputerWithoutAYes(FolderBase):
    """The brief carries the titles of the tasks, who is being chased, phone numbers and the notes - in the test
    above, the code word of a bank. `--to` puts that into Google Drive. The product's first promise is that
    nothing goes anywhere without the person's yes, so the yes is asked for, once, and remembered."""

    def test_the_first_time_nothing_is_written_and_the_question_is_handed_over(self):
        code, _, out, err = self.cli("--lang", "ru", "--to", self.folder)
        self.assertEqual(code, brief.NOT_WRITTEN)
        self.assertIn("Нужно от вас", out)                    # the screen is unchanged either way
        self.assertEqual(os.listdir(self.folder), [])
        self.assertIn("ничего не записано", err)
        self.assertIn("Google", err)
        self.assertIn("--agreed", err)

    def test_the_question_is_in_the_language_the_person_reads(self):
        self.assertIn("Класть?", self.cli("--lang", "ru", "--to", self.folder)[3])
        self.assertIn("Shall I?", self.cli("--lang", "en", "--to", self.folder)[3])

    def test_a_yes_writes_it_and_is_remembered_so_nobody_is_asked_twice(self):
        code, _, _, err = self.cli("--lang", "en", "--to", self.folder, "--agreed")
        self.assertEqual(code, 0)
        self.assertIn("brief written to", err)
        self.assertEqual(os.listdir(self.folder), ["brief.txt"])
        os.remove(os.path.join(self.folder, "brief.txt"))
        code, _, _, err = self.cli("--lang", "en", "--to", self.folder)    # no flag this time
        self.assertEqual(os.listdir(self.folder), ["brief.txt"])
        self.assertNotIn("--agreed", err)

    def test_a_no_is_remembered_too_so_nobody_is_pestered(self):
        self.assertEqual(self.cli("--lang", "en", "--to", self.folder, "--declined")[0], brief.NOT_WRITTEN)
        self.assertEqual(os.listdir(self.folder), [])
        code, _, out, err = self.cli("--lang", "en", "--to", self.folder)
        self.assertEqual(code, brief.NOT_WRITTEN)
        self.assertIn("said no", err)
        self.assertNotIn("Shall I?", err)
        self.assertEqual(os.listdir(self.folder), [])

    def test_the_yes_is_for_that_one_folder_and_not_for_every_folder(self):
        self.cli("--lang", "en", "--to", self.folder, "--agreed")
        other = os.path.join(self.root, "Some other cloud")
        os.makedirs(other)
        self.assertIn("--agreed", self.cli("--lang", "en", "--to", other)[3])
        self.assertEqual(os.listdir(other), [])

    def test_the_file_is_readable_by_its_owner_only_like_the_database(self):
        """Under a umask that takes bits away, the temporary file `mkstemp` makes comes out at 0400 and the
        database at 0400 too - readable, but not writable by the person who owns them. It is our own `chmod`
        that puts both at exactly 0600, so the umask has to be moved for this test to be about anything: with it
        left alone, `mkstemp`'s own 0600 would pass the test whether we chmod or not."""
        was = os.umask(0o377)
        try:
            self.cli("--lang", "ru", "--to", self.folder, "--agreed")
            here = os.path.join(self.root, "fresh.db")
            self.cli("--lang", "ru", env_extra={"CHASECALL_DB": here})
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.folder, "сводка.txt")).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(here).st_mode), 0o600)
        finally:
            os.umask(was)

    def test_and_nobody_else_can_read_it_however_open_the_umask_is(self):
        was = os.umask(0)
        try:
            self.cli("--lang", "ru", "--to", self.folder, "--agreed")
            mode = stat.S_IMODE(os.stat(os.path.join(self.folder, "сводка.txt")).st_mode)
        finally:
            os.umask(was)
        self.assertEqual(mode, 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.db).st_mode), 0o600)

    def test_the_exit_code_says_whether_the_file_is_there_or_not(self):
        """Both answers used to be 0, so the only way to tell "it is in your cloud folder" from "it is not" was
        to read our English prose on stderr and guess. The screen is the same either way; the file is not.

        Every line here used to go through the symbol, and the symbol is what the bug would change: set
        `NOT_WRITTEN = 0` and the product was back to answering 0 to both, with all of these still green. So the
        number is written out once, in figures, and the two answers are required to differ - the same way
        `DEFAULT_MAX_ATTEMPTS` is pinned to the three the README promises."""
        self.assertEqual(brief.NOT_WRITTEN, 3)
        not_there = self.cli("--lang", "en", "--to", self.folder)[0]
        self.assertEqual(not_there, 3)
        self.assertEqual(os.listdir(self.folder), [])
        there = self.cli("--lang", "en", "--to", self.folder, "--agreed")[0]
        self.assertEqual(there, 0)
        self.assertNotEqual(not_there, there)          # "asked for the file and did not get it" is not success
        self.assertEqual(os.listdir(self.folder), ["brief.txt"])
        self.assertEqual(self.cli("--lang", "en")[0], 0)                   # and no folder asked for is no trouble

    def test_the_json_says_that_it_is_waiting_for_a_yes(self):
        code, data, _, _ = self.cli("--json", "--lang", "en", "--to", self.folder)
        self.assertEqual((code, data["written_to"], data["needs_consent"]), (brief.NOT_WRITTEN, None, True))
        code, data, _, _ = self.cli("--json", "--lang", "en", "--to", self.folder, "--agreed")
        self.assertEqual((code, data["needs_consent"]), (0, False))
        self.assertTrue(os.path.exists(data["written_to"]))

    def test_a_folder_we_would_never_point_at_is_refused_here_too(self):
        code, _, _, err = self.cli("--lang", "en", "--to", os.path.expanduser("~"), "--agreed")
        self.assertEqual(code, brief.NOT_WRITTEN)
        self.assertNotIn("brief written", err)
        self.assertFalse(os.path.exists(os.path.join(os.path.expanduser("~"), "brief.txt")))


class SomebodyElsesFileIsNeverDestroyed(FolderBase):
    """A shared cloud folder is shared. `brief.txt` and `сводка.txt` are ordinary names, and `is_junk()` keeps
    both of them out of the inbox listing - so a file quietly replaced here would never surface again either."""

    def test_a_file_of_that_name_which_is_not_ours_is_left_exactly_as_it_is(self):
        self.agree()
        theirs = os.path.join(self.folder, "сводка.txt")
        with open(theirs, "w", encoding="utf-8") as handle:
            handle.write("моя сводка по даче: столбы, крыша, счётчик")
        code, _, out, err = self.cli("--lang", "ru", "--to", self.folder)
        self.assertEqual(code, brief.NOT_WRITTEN)
        self.assertIn("Нужно от вас", out)                    # the screen still works
        self.assertEqual(self.read_file("сводка.txt"), "моя сводка по даче: столбы, крыша, счётчик")
        self.assertIn("не наш", err)
        self.assertIn("сводка.txt", err)

    def test_our_own_file_is_recognised_and_replaced(self):
        self.cli("--lang", "en", "--to", self.folder, "--agreed")
        first = self.read_file("brief.txt")
        self.assertIn(brief.MARK, first)
        tracker.done(self.conn, self.yours["id"], "the bank unblocked it on the phone")
        code, _, _, err = self.cli("--lang", "en", "--to", self.folder)
        self.assertIn("brief written to", err)
        self.assertNotIn("call the bank", self.read_file("brief.txt"))

    def test_a_file_we_cannot_even_read_is_not_overwritten_on_a_guess(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read anything, so the check proves nothing")
        self.agree()
        theirs = os.path.join(self.folder, "brief.txt")
        with open(theirs, "w", encoding="utf-8") as handle:
            handle.write("somebody else's notes")
        os.chmod(theirs, 0)
        try:
            self.assertIn("not ours", self.cli("--lang", "en", "--to", self.folder)[3])
        finally:
            os.chmod(theirs, 0o600)
        self.assertEqual(self.read_file("brief.txt"), "somebody else's notes")

    def test_the_mark_that_says_the_file_is_ours_is_there_in_both_languages(self):
        """And the mark is the whole of it: with every memory of having written those paths taken out of the
        settings, both files are still recognised as ours, because the answer is inside them."""
        self.cli("--lang", "ru", "--to", self.folder, "--agreed")
        self.cli("--lang", "en", "--to", self.folder, "--agreed")
        self.assertIn(brief.MARK, self.read_file("сводка.txt"))
        self.assertIn(brief.MARK, self.read_file("brief.txt"))
        self.forget_that_we_wrote_them()
        for name in ("сводка.txt", "brief.txt"):
            self.assertTrue(brief.is_ours(os.path.join(self.folder, name)), name)

    def test_the_note_the_person_left_where_our_brief_used_to_be_is_never_destroyed(self):
        """The one that cost a telephone number. We write our brief, so the settings remember that path as ours
        for ever. The person deletes it, and puts their own note under the same name - a shared cloud folder is
        shared. A memory that says "ours" about a file nobody has read is not knowledge, it is a licence to
        destroy: the content decides, or nothing does."""
        self.cli("--lang", "ru", "--to", self.folder, "--agreed")
        os.remove(os.path.join(self.folder, "сводка.txt"))
        theirs = "ВАЖНО: telefon vracha 555-0100, zvonit do 18:00\n"
        with open(os.path.join(self.folder, "сводка.txt"), "w", encoding="utf-8") as handle:
            handle.write(theirs)

        code, _, out, err = self.cli("--lang", "ru", "--to", self.folder)
        self.assertEqual(code, brief.NOT_WRITTEN)
        self.assertIn("Нужно от вас", out)                    # the screen still works
        self.assertEqual(self.read_file("сводка.txt"), theirs)
        self.assertIn("555-0100", self.read_file("сводка.txt"))
        self.assertIn("чужой файл", err)                      # and it says what happened, not only "not ours"
        self.assertIn("сводка.txt", err)

    def test_and_the_settings_alone_never_answer_the_question(self):
        target = os.path.join(self.folder, "сводка.txt")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("somebody else's note, no mark in it anywhere")
        conn = inbox.connect()
        try:
            inbox.set_setting(conn, brief.FILE_KEY % target, "ours")       # we did write here once
        finally:
            conn.close()
        self.assertFalse(brief.is_ours(target))

    def test_a_brief_too_big_for_one_read_is_still_our_own_brief(self):
        """The mark is written in the last line. At 120 tasks the brief is 16 KB, the mark sits at 14 982, and a
        look at the first 8 KB only made the plugin disown its own file and ask the person what it was."""
        for number in range(200):
            tracker.add(self.conn, "Refund for order %d, the long-running one" % number,
                        "the money is back on the card", counterpart="support-%d@shop.example" % number,
                        first_step_now=True)
        self.cli("--lang", "en", "--to", self.folder, "--agreed")
        target = os.path.join(self.folder, "brief.txt")
        body = self.read_file("brief.txt")
        self.assertGreater(len(body.encode("utf-8")), brief.MARK_WINDOW * 2)
        self.assertNotIn(brief.MARK, body[:brief.MARK_WINDOW])             # not where a single read would find it
        self.assertTrue(brief.is_ours(target))

        self.forget_that_we_wrote_them()                                   # nothing but the file itself to go on
        tracker.done(self.conn, self.yours["id"], "the bank unblocked it on the phone")
        code, _, _, err = self.cli("--lang", "en", "--to", self.folder)
        self.assertEqual(code, 0)
        self.assertIn("brief written to", err)
        self.assertNotIn("call the bank", self.read_file("brief.txt"))

    def forget_that_we_wrote_them(self):
        conn = inbox.connect()
        try:
            conn.execute("DELETE FROM inbox_settings WHERE key LIKE 'brief_file:%'")
            conn.commit()
        finally:
            conn.close()


class IntoTheFolderThePhoneCanSee(FolderBase):
    """`--to` leaves the same screen as a file in the shared folder. It is the one file Chasecall writes outside
    its own database, and it must never change what the terminal shows."""

    def setUp(self):
        super().setUp()
        self.agree()

    def test_the_file_appears_with_the_name_of_the_language(self):
        self.assertEqual(self.cli("--lang", "en", "--to", self.folder)[0], 0)
        self.assertEqual(os.listdir(self.folder), ["brief.txt"])
        self.assertEqual(self.cli("--lang", "ru", "--to", self.folder)[0], 0)
        self.assertEqual(sorted(os.listdir(self.folder)), ["brief.txt", "сводка.txt"])
        self.assertIn("Needs you", self.read_file("brief.txt"))
        self.assertIn("Нужно от вас", self.read_file("сводка.txt"))
        self.assertIn("call the bank", self.read_file("сводка.txt"))

    def test_what_the_person_sees_on_the_screen_does_not_change_one_character(self):
        plain = self.cli("--lang", "ru")
        with_file = self.cli("--lang", "ru", "--to", self.folder)
        self.assertEqual(with_file[0], 0)
        self.assertEqual(with_file[2], plain[2])
        self.assertIn(plain[2].strip(), self.read_file("сводка.txt"))
        self.assertIn("Обновлено", self.read_file("сводка.txt"))

    def test_the_file_is_replaced_whole_and_nothing_else_in_the_folder_is_touched(self):
        with open(os.path.join(self.folder, "IMG_1.HEIC"), "w", encoding="utf-8") as handle:
            handle.write("a photograph")
        self.cli("--lang", "en", "--to", self.folder)
        tracker.done(self.conn, self.yours["id"], "the bank unblocked it on the phone")
        self.cli("--lang", "en", "--to", self.folder)
        self.assertEqual(sorted(os.listdir(self.folder)), ["IMG_1.HEIC", "brief.txt"])   # no half-written leftover
        self.assertNotIn("call the bank", self.read_file("brief.txt"))
        self.assertEqual(self.read_file("IMG_1.HEIC"), "a photograph")

    def test_a_folder_that_is_not_there_costs_the_brief_nothing(self):
        gone = os.path.join(self.root, "not synced yet")
        code, _, out, err = self.cli("--lang", "en", "--to", gone)
        self.assertEqual(code, brief.NOT_WRITTEN)
        self.assertIn("Needs you", out)
        self.assertIn("not on this computer", err)
        self.assertFalse(os.path.exists(gone))

    def test_json_still_json_and_it_says_where_the_file_went(self):
        code, data, _, _ = self.cli("--json", "--lang", "ru", "--to", self.folder)
        self.assertEqual(code, 0)
        self.assertEqual(data["counts"]["needs_you"], 1)
        self.assertEqual(data["written_to"], os.path.join(self.folder, "сводка.txt"))
        self.assertTrue(os.path.exists(data["written_to"]))
        self.assertIn("Нужно от вас", self.read_file("сводка.txt"))

    def test_without_the_flag_nothing_is_written_anywhere(self):
        """The trap has to be armed for this to mean anything, so it is armed here and then checked: the folder
        is the remembered phone folder, the person has already said yes to the brief living in it, and a brief
        that went looking for somewhere to put itself would land there without another question. Without `--to`,
        nothing does - the flag is the whole of the decision."""
        conn = inbox.connect()
        try:
            inbox.set_folder(conn, self.folder)
            self.assertEqual(inbox.get_folder(conn), self.folder)
            self.assertEqual(inbox.get_setting(conn, brief.CONSENT_KEY % self.folder), "yes")
        finally:
            conn.close()
        self.assertEqual(self.cli("--lang", "ru", "--to", self.folder)[0], 0)     # with the flag it does land
        self.assertEqual(os.listdir(self.folder), ["сводка.txt"])
        os.remove(os.path.join(self.folder, "сводка.txt"))
        for args in (["--lang", "ru"], ["--lang", "en"], ["--json"]):
            code, _, out, err = self.cli(*args)
            self.assertEqual((code, err.strip()), (0, ""), args)
            self.assertTrue(out.strip())
            self.assertEqual(os.listdir(self.folder), [], args)


if __name__ == "__main__":
    unittest.main()

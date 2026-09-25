"""The tracker keeps the promises the product makes: nothing closes without proof, nobody is pushed a fourth
time, nobody is written to at night, and the clock stops the moment a task becomes the person's move.

No network, no writing outside a temporary folder: `CHASECALL_DB` points every test at its own database.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import tracker  # noqa: E402

NIGHT = datetime(2026, 9, 24, 23, 30, tzinfo=timezone.utc)   # only the hour matters to the night window
EARLY = datetime(2026, 9, 24, 3, 5, tzinfo=timezone.utc)
DAY = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    """A fresh database per test, in a temporary folder, with the environment put back afterwards."""

    KEYS = ("CHASECALL_DB", "CHASECALL_NOW", "CHASECALL_LANG", "CHASECALL_CLAUDE_BIN")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {key: os.environ.get(key) for key in self.KEYS}
        for key in self.KEYS:
            os.environ.pop(key, None)
        self.db = os.path.join(self.tmp.name, "chasecall.db")
        os.environ["CHASECALL_DB"] = self.db
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
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "tracker.py")] + list(args),
                              capture_output=True, text=True, env=env, timeout=60)
        try:
            data = json.loads(done.stdout)
        except ValueError:
            data = None
        return done.returncode, data, done.stdout, done.stderr

    def a_task(self, **kwargs):
        options = {"title": "Refund for order 1182", "goal": "the money is back on the card",
                   "channel": "email", "counterpart": "support@shop.example", "every": "24h"}
        options.update(kwargs)
        return tracker.add(self.conn, **options)["task"]


class Helpers(unittest.TestCase):
    def test_interval_words_we_accept_and_refuse(self):
        self.assertEqual(tracker.parse_every("30m"), timedelta(minutes=30))
        self.assertEqual(tracker.parse_every("24h"), timedelta(hours=24))
        self.assertEqual(tracker.parse_every("3d"), timedelta(days=3))
        self.assertEqual(tracker.parse_every("2w"), timedelta(weeks=2))
        for bad in ("soon", "", "24", "0h", "-3d", "3y"):
            with self.assertRaises(tracker.TrackerError, msg=bad):
                tracker.parse_every(bad)

    def test_iso_round_trip_and_z_suffix(self):
        moment = datetime(2026, 9, 24, 21, 0, tzinfo=timezone.utc)
        self.assertEqual(tracker.parse_iso(tracker.iso(moment)), moment)
        self.assertEqual(tracker.parse_iso("2026-09-24T21:00:00Z"), moment)
        self.assertEqual(tracker.parse_iso("2026-09-24T21:00:00"), moment)   # naive is read as UTC
        with self.assertRaises(tracker.TrackerError):
            tracker.parse_iso("tomorrow")

    def test_night_window_is_22_to_08_local(self):
        for hour in list(range(22, 24)) + list(range(0, 8)):
            self.assertTrue(tracker.is_night(DAY.replace(hour=hour)), hour)
        for hour in range(8, 22):
            self.assertFalse(tracker.is_night(DAY.replace(hour=hour)), hour)

    def test_night_ends_at_the_next_eight(self):
        self.assertEqual(tracker.night_ends_at(NIGHT).day, 25)
        self.assertEqual(tracker.night_ends_at(NIGHT).hour, tracker.NIGHT_END)
        self.assertEqual(tracker.night_ends_at(EARLY).day, 24)

    def test_humanize_reads_like_a_person_speaks(self):
        self.assertEqual(tracker.humanize(30), "a moment")
        self.assertEqual(tracker.humanize(600), "10m")
        self.assertEqual(tracker.humanize(7200), "2h")
        self.assertEqual(tracker.humanize(2 * 86400 + 3 * 3600), "2d 3h")


class AddAndStore(Base):
    def test_a_new_task_starts_open_with_no_attempts_and_a_next_step(self):
        now = tracker.now_utc()
        task = self.a_task()
        self.assertEqual((task["state"], task["attempts"], task["max_attempts"]), ("open", 0, 3))
        self.assertEqual((task["evidence"], task["needs_human"], task["human_note"]), ("", 0, ""))
        step = tracker.parse_iso(task["next_step_at"])
        self.assertAlmostEqual((step - now).total_seconds(), 24 * 3600, delta=5)

    def test_first_step_now_puts_the_task_in_due_at_once(self):
        task = self.a_task(first_step_now=True)
        self.assertEqual(tracker.due(self.conn, local=DAY)["count"], 1)
        self.assertEqual(tracker.due(self.conn, local=DAY)["tasks"][0]["id"], task["id"])

    def test_a_task_needs_a_title_a_goal_a_known_channel_and_a_readable_interval(self):
        with self.assertRaises(tracker.TrackerError):
            tracker.add(self.conn, "  ", "a goal")
        with self.assertRaises(tracker.TrackerError):
            tracker.add(self.conn, "a title", "   ")
        with self.assertRaises(tracker.TrackerError):
            tracker.add(self.conn, "a title", "a goal", channel="telepathy")
        with self.assertRaises(tracker.TrackerError):
            tracker.add(self.conn, "a title", "a goal", every="whenever")

    def test_the_database_is_the_only_file_we_make_and_only_the_owner_reads_it(self):
        self.a_task()
        self.assertTrue(os.path.exists(self.db))
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["chasecall.db"])
        self.assertEqual(os.stat(self.db).st_mode & 0o777, 0o600)

    def test_an_unknown_task_is_said_out_loud_not_swallowed(self):
        for call in (lambda: tracker.show(self.conn, 404),
                     lambda: tracker.done(self.conn, 404, "proof"),
                     lambda: tracker.wait(self.conn, 404, "24h"),
                     lambda: tracker.human(self.conn, 404, "call them")):
            with self.assertRaises(tracker.TrackerError):
                call()


class Lifecycle(Base):
    def test_from_taken_to_closed_with_every_step_written_down(self):
        task = self.a_task(first_step_now=True)
        tracker.log(self.conn, task["id"], "sent", "first letter to support@shop.example")
        waited = tracker.wait(self.conn, task["id"], "48h")
        self.assertEqual((waited["state"], waited["attempts"]), ("waiting", 1))
        step = tracker.parse_iso(waited["next_step_at"])
        self.assertAlmostEqual((step - tracker.now_utc()).total_seconds(), 48 * 3600, delta=5)

        tracker.log(self.conn, task["id"], "reply", "they ask for the order number")
        closed = tracker.done(self.conn, task["id"], "refund #77-19 confirmed in their reply")
        self.assertEqual(closed["state"], "done")

        shown = tracker.show(self.conn, task["id"])
        self.assertEqual(shown["task"]["evidence"], "refund #77-19 confirmed in their reply")
        self.assertEqual([e["kind"] for e in shown["events"]], ["note", "sent", "note", "reply", "note"])
        self.assertEqual(tracker.due(self.conn, local=DAY)["count"], 0)

    def test_closing_needs_evidence_a_feeling_is_not_enough(self):
        task = self.a_task()
        for nothing in ("", "   ", None):
            with self.assertRaises(tracker.TrackerError):
                tracker.done(self.conn, task["id"], nothing)
        self.assertEqual(tracker.show(self.conn, task["id"])["task"]["state"], "open")
        code, _, _, err = self.cli("done", str(task["id"]), "--evidence", "")
        self.assertEqual(code, 1)
        self.assertIn("evidence", err)
        self.assertEqual(self.cli("done", str(task["id"]))[0], 2)          # the flag itself is required

    def test_waiting_counts_the_attempt_and_a_closed_task_is_not_waited_on(self):
        task = self.a_task(first_step_now=True)
        for expected in (1, 2, 3):
            self.assertEqual(tracker.wait(self.conn, task["id"], "1m")["attempts"], expected)
        tracker.done(self.conn, task["id"], "they answered")
        with self.assertRaises(tracker.TrackerError):
            tracker.wait(self.conn, task["id"], "24h")

    def test_the_person_move_stops_our_clock_and_shows_up_as_theirs(self):
        task = self.a_task(first_step_now=True)
        moved = tracker.human(self.conn, task["id"], "call +1 555 0199 and ask for the refund by hand")
        self.assertEqual((moved["state"], moved["needs_human"]), ("blocked", 1))
        row = tracker.show(self.conn, task["id"])["task"]
        self.assertIsNone(row["next_step_at"])                              # we stop nagging ourselves
        result = tracker.due(self.conn, local=DAY)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["blocked_count"], 1)
        self.assertIn("call +1 555 0199", result["blocked"][0]["human_note"])
        with self.assertRaises(tracker.TrackerError):
            tracker.human(self.conn, task["id"], "  ")

    def test_dropping_needs_a_reason(self):
        task = self.a_task()
        with self.assertRaises(tracker.TrackerError):
            tracker.drop(self.conn, task["id"], "")
        self.assertEqual(tracker.drop(self.conn, task["id"], "we booked elsewhere")["state"], "dropped")
        self.assertEqual(tracker.due(self.conn, local=DAY)["count"], 0)

    def test_only_the_five_event_kinds_go_into_the_history(self):
        task = self.a_task()
        for kind in tracker.EVENT_KINDS:
            tracker.log(self.conn, task["id"], kind, "x")
        with self.assertRaises(tracker.TrackerError):
            tracker.log(self.conn, task["id"], "shouted", "x")


class DueAndNight(Base):
    def test_a_task_not_yet_due_is_left_alone(self):
        self.a_task(every="3d")
        self.assertEqual(tracker.due(self.conn, local=DAY)["count"], 0)
        self.assertEqual(tracker.list_tasks(self.conn, "open")["count"], 1)

    def test_by_day_we_propose_the_next_push(self):
        self.a_task(first_step_now=True)
        result = tracker.due(self.conn, local=DAY)
        self.assertFalse(result["night"])
        task = result["tasks"][0]
        self.assertTrue(task["may_write"])
        self.assertIn("push #1", task["action"])
        self.assertIn("support@shop.example", task["action"])

    def test_at_night_we_show_but_never_propose_writing(self):
        self.a_task(first_step_now=True)
        for local in (NIGHT, EARLY):
            result = tracker.due(self.conn, local=local)
            self.assertTrue(result["night"], local)
            self.assertEqual(result["count"], 1)                            # still visible
            self.assertFalse(result["tasks"][0]["may_write"])
            self.assertIn("night window", result["tasks"][0]["action"])
            self.assertIsNotNone(result["night_until"])

    def test_when_the_attempts_are_used_up_we_call_the_person_in(self):
        task = self.a_task(first_step_now=True, max_attempts=2)
        tracker.wait(self.conn, task["id"], "1m")
        tracker.wait(self.conn, task["id"], "1m")
        result = tracker.due(self.conn, now=tracker.now_utc() + timedelta(minutes=2), local=DAY)
        found = result["tasks"][0]
        self.assertTrue(found["escalate"])
        self.assertFalse(found["may_write"])
        self.assertIn("human", found["action"])
        self.assertIn("2/2", found["action"])

    def test_due_is_ordered_by_who_waited_longest(self):
        old = self.a_task(title="older", first_step_now=True)
        tracker.wait(self.conn, old["id"], "1m")
        self.a_task(title="newer", first_step_now=True)
        result = tracker.due(self.conn, now=tracker.now_utc() + timedelta(minutes=5), local=DAY)
        self.assertEqual([t["title"] for t in result["tasks"]], ["newer", "older"])


class StandingTasks(Base):
    """"Look at what is new" every seven days is a habit, not a chase: it can never run out of attempts."""

    def test_a_standing_task_never_runs_out_of_attempts_and_is_never_handed_over(self):
        task = tracker.add(self.conn, "Look at what is new", "one line about what changed",
                           channel="web", every="7d", standing=True, first_step_now=True)["task"]
        self.assertEqual(task["standing"], 1)
        for _ in range(5):
            result = tracker.wait(self.conn, task["id"], "7d")
            self.assertEqual((result["attempts"], result["state"]), (0, "open"))
        row = tracker.show(self.conn, task["id"])["task"]
        self.assertEqual((row["attempts"], row["state"]), (0, "open"))
        found = tracker.due(self.conn, now=tracker.now_utc() + timedelta(days=8), local=DAY)["tasks"][0]
        self.assertFalse(found["escalate"])
        self.assertTrue(found["may_write"])
        self.assertIn("standing task", found["action"])
        self.assertNotIn("human", found["action"])

    def test_the_standing_flag_reaches_the_database_from_the_command_line(self):
        code, data, _, _ = self.cli("add", "Look at what is new", "--goal", "one line about what changed",
                                    "--channel", "web", "--every", "7d", "--standing", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(data["task"]["standing"], 1)
        self.assertEqual(self.cli("add", "Plain task", "--goal", "g", "--json")[1]["task"]["standing"], 0)

    def test_the_column_is_in_the_schema_and_no_silent_alter_pretends_otherwise(self):
        """`MIGRATIONS = ("ALTER TABLE tasks ADD COLUMN standing ...",)` sat here with `except: pass` around it,
        on a version that has never been released and therefore has no older databases. It could only ever fail
        and be swallowed: care for nobody, and a place for a real failure to hide in later."""
        columns = [row[1] for row in self.conn.execute("PRAGMA table_info(tasks)").fetchall()]
        self.assertIn("standing", columns)
        self.assertIn("standing INTEGER NOT NULL DEFAULT 0", " ".join(tracker.SCHEMA.split()))
        self.assertFalse(hasattr(tracker, "MIGRATIONS"))
        with open(os.path.join(SCRIPTS, "tracker.py"), "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual([line for line in lines
                          if "ALTER TABLE" in line.upper() and not line.strip().startswith("#")], [])


class TheFileIsSharedWithTheBackground(Base):
    """A routine run and a live session use the same database. `connect` used to fail the moment the other one
    held the write lock, and the failure reached the person as a Python traceback.

    "Busy" and "we are not allowed to write here" are two different accidents, and the advice is the opposite in
    each: one passes by itself in a moment, the other never will. The tests that stood here proved neither -
    they took a file with the wrong permissions and asserted the word "busy" on it, which is how the product
    came to tell a person with a read-only database to try again in a minute, for ever.
    """

    def hold_the_write_lock(self, path):
        """As far as sqlite is concerned, another process: a connection sitting inside an exclusive transaction."""
        other = tracker.connect(path)
        other.execute("BEGIN EXCLUSIVE")
        return other

    def test_the_patience_we_actually_ship_is_ten_seconds(self):
        """Every test in this class moves it to a fraction of a second, which is right for a test and means the
        number the person's own computer uses was checked by nobody: set it to 0 and all of them stayed green
        while the product gave up on a busy file instantly. It is pinned here in figures, once."""
        self.assertEqual(tracker.BUSY_WAIT_SECONDS, 10.0)

    def test_we_really_wait_for_the_other_process_before_we_give_up(self):
        path = os.path.join(self.tmp.name, "shared.db")
        other = self.hold_the_write_lock(path)
        patience = tracker.BUSY_WAIT_SECONDS
        tracker.BUSY_WAIT_SECONDS = 0.4                    # ten seconds is right in life and wrong in a test
        started = time.monotonic()
        try:
            with self.assertRaises(tracker.TrackerError) as caught:
                tracker.connect(path)
            waited = time.monotonic() - started
        finally:
            tracker.BUSY_WAIT_SECONDS = patience
            other.rollback()
            other.close()
        self.assertIn("busy", str(caught.exception))       # and it is the busy sentence, not the other one
        self.assertNotIn("sqlite3", str(caught.exception))
        self.assertGreater(waited, 0.3)                    # we really waited for the other one
        self.assertLess(waited, 3.0)                       # and we waited *our* patience, not sqlite's own

    def test_the_wait_is_over_the_moment_the_other_one_is_done(self):
        path = os.path.join(self.tmp.name, "shared.db")
        other = self.hold_the_write_lock(path)
        other.rollback()                                   # the routine run has finished its write
        conn = tracker.connect(path)
        try:
            self.assertEqual(tracker.add(conn, "Refund", "money back")["task"]["state"], "open")
        finally:
            conn.close()
            other.close()

    def test_a_database_we_are_not_allowed_to_write_to_is_not_called_busy(self):
        """It will not pass in a minute, so we must not say it will."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can write to anything, so the check proves nothing")
        unwritable = os.path.join(self.tmp.name, "read-only.db")
        open(unwritable, "w").close()                      # an empty file is a valid, empty database
        os.chmod(unwritable, 0o444)
        try:
            with self.assertRaises(tracker.TrackerError) as caught:
                tracker.connect(unwritable)
            said = str(caught.exception)
            self.assertIn("permissions", said)
            self.assertIn(unwritable, said)
            self.assertNotIn("in a moment", said)
            self.assertNotIn("sqlite3", said)
            os.environ["CHASECALL_DB"] = unwritable
            code, _, _, err = self.cli("stats")
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", err)
            self.assertIn("permissions", err)
        finally:
            os.chmod(unwritable, 0o600)

    def test_the_brief_says_it_in_a_sentence_too_and_in_the_persons_own_language(self):
        """The Russian sentence was written and then never reachable: `tracker.connect` threw the English one
        first, and `--lang ru` never got a word in."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can write to anything, so the check proves nothing")
        unwritable = os.path.join(self.tmp.name, "read-only.db")
        open(unwritable, "w").close()
        os.chmod(unwritable, 0o444)
        try:
            for args, expected, absent in ((["--lang", "en"], "permissions", "права"),
                                           (["--lang", "ru"], "права", "permissions")):
                for script in ("brief.py", "inbox.py"):
                    argv = [sys.executable, os.path.join(SCRIPTS, script)] + args
                    argv += ["list"] if script == "inbox.py" else []
                    done = subprocess.run(argv, capture_output=True, text=True, timeout=60,
                                          env=dict(os.environ, CHASECALL_DB=unwritable))
                    self.assertEqual(done.returncode, 1, (script, args))
                    self.assertNotIn("Traceback", done.stderr)
                    self.assertIn(expected, done.stderr, (script, args))
                    self.assertNotIn(absent, done.stderr, (script, args))
        finally:
            os.chmod(unwritable, 0o600)

    def test_the_busy_sentence_reaches_the_person_in_their_own_language_too(self):
        path = os.path.join(self.tmp.name, "shared.db")
        other = self.hold_the_write_lock(path)
        patience = tracker.BUSY_WAIT_SECONDS
        tracker.BUSY_WAIT_SECONDS = 0.2
        try:
            for lang, expected, absent in (("en", "busy", "занят"), ("ru", "занят", "busy")):
                with self.assertRaises(tracker.TrackerError) as caught:
                    tracker.connect(path, lang)
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn(absent, str(caught.exception))
        finally:
            tracker.BUSY_WAIT_SECONDS = patience
            other.rollback()
            other.close()


class AFileThatIsNotOurs(Base):
    """`CHASECALL_DB` can be pointed at anything, and a person who moves their files around will point it at the
    wrong thing one day. Neither of these two was a sentence before: a text file came back as a raw
    `sqlite3.DatabaseError`, and a database with a `tasks` of its own that is not a table walked past the
    `CREATE TABLE IF NOT EXISTS` (a silent no-op on a view) to blow up one line later."""

    def not_a_database(self):
        path = os.path.join(self.tmp.name, "notes.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("this is not a database, it is the shopping list")
        return path

    def tasks_is_not_a_table(self):
        """The worst case the check after the CREATEs is there for: every statement of ours runs without a word
        of complaint (`CREATE TABLE IF NOT EXISTS` skips the view, `CREATE INDEX IF NOT EXISTS` skips the index
        that is already there under that name), and `tasks` is still not a table. Nothing raises; only the
        looking finds it."""
        path = os.path.join(self.tmp.name, "shadowed.db")
        plain = sqlite3.connect(path)
        plain.executescript("""CREATE TABLE x (id INTEGER, state TEXT, next_step_at TEXT);
                               CREATE VIEW tasks AS SELECT * FROM x;
                               CREATE INDEX idx_tasks_due ON x(state, next_step_at);""")
        plain.commit()
        plain.close()
        return path

    def test_it_is_one_sentence_in_both_languages_and_never_a_traceback(self):
        for path in (self.not_a_database(), self.tasks_is_not_a_table()):
            for lang, expected, absent in (("en", "not a Chasecall task file", "не файл дел"),
                                           ("ru", "не файл дел", "not a Chasecall")):
                with self.assertRaises(tracker.TrackerError) as caught:
                    tracker.connect(path, lang)
                said = str(caught.exception)
                self.assertIn(expected, said, path)
                self.assertNotIn(absent, said, path)
                self.assertIn(path, said)
                self.assertNotIn("sqlite3", said)

    def test_the_command_line_says_it_and_stops(self):
        for path in (self.not_a_database(), self.tasks_is_not_a_table()):
            code, _, out, err = self.cli("stats", env_extra={"CHASECALL_DB": path})
            self.assertEqual(code, 1, path)
            self.assertNotIn("Traceback", err)
            self.assertIn("not a Chasecall task file", err)
            self.assertEqual(out, "")

    def test_and_nothing_in_the_file_is_touched(self):
        path = self.not_a_database()
        with open(path, encoding="utf-8") as handle:
            before = handle.read()
        self.cli("add", "Refund", "--goal", "money back", env_extra={"CHASECALL_DB": path})
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), before)


class ThreeAttemptsIsAPromiseNotASetting(Base):
    """`--max-attempts` was on the command line, so a session could raise the ceiling on a task that felt
    important - and the README promises the person three, and a human after that. The column stays; the flag
    does not."""

    def test_the_command_line_does_not_offer_to_change_it(self):
        self.assertEqual(self.cli("add", "Refund", "--goal", "money back", "--max-attempts", "9")[0], 2)

    def test_every_task_made_from_the_command_line_gets_the_promised_three(self):
        code, data, _, _ = self.cli("add", "Refund", "--goal", "money back", "--json")
        self.assertEqual((code, data["task"]["max_attempts"]), (0, 3))
        self.assertEqual(tracker.DEFAULT_MAX_ATTEMPTS, 3)
        # The column itself is still read by the code that escalates: `DueAndNight
        # .test_when_the_attempts_are_used_up_we_call_the_person_in` makes a task with two and gets "2/2".


class ListingAndStats(Base):
    def test_list_by_state_and_all(self):
        first = self.a_task(title="one")
        second = self.a_task(title="two")
        tracker.done(self.conn, second["id"], "done and proven")
        self.assertEqual(tracker.list_tasks(self.conn, "open")["count"], 1)
        self.assertEqual(tracker.list_tasks(self.conn, "done")["count"], 1)
        self.assertEqual(tracker.list_tasks(self.conn, "all")["count"], 2)
        self.assertEqual(tracker.list_tasks(self.conn)["tasks"][0]["id"], first["id"])
        with self.assertRaises(tracker.TrackerError):
            tracker.list_tasks(self.conn, "sleeping")

    def test_stats_counts_what_the_person_would_ask_about(self):
        first = self.a_task(title="one", first_step_now=True)
        tracker.wait(self.conn, first["id"], "1m")
        second = self.a_task(title="two")
        tracker.done(self.conn, second["id"], "proof")
        third = self.a_task(title="three")
        tracker.human(self.conn, third["id"], "sign the form")
        result = tracker.stats(self.conn, now=tracker.now_utc() + timedelta(minutes=2))
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["by_state"], {"open": 0, "waiting": 1, "blocked": 1, "done": 1, "dropped": 0})
        self.assertEqual((result["attempts"], result["done_7d"], result["overdue"], result["needs_human"]),
                         (1, 1, 1, 1))


class CommandLine(Base):
    def test_json_works_on_both_sides_of_the_command(self):
        code, data, _, _ = self.cli("add", "Ticket refund", "--goal", "money back", "--first-step-now", "--json")
        self.assertEqual(code, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(self.cli("--json", "list")[1]["count"], 1)
        self.assertEqual(self.cli("list", "--json")[1]["count"], 1)
        self.assertTrue(self.cli("due", "--json")[1]["tasks"][0]["action"])
        self.assertIn("by_state", self.cli("stats", "--json")[1])

    def test_text_output_is_for_a_person_not_for_a_parser(self):
        self.cli("add", "Ticket refund", "--goal", "money back", "--counterpart", "help@air.example",
                 "--first-step-now")
        code, _, out, _ = self.cli("due")
        self.assertEqual(code, 0)
        self.assertIn("Ticket refund", out)
        self.assertIn("goal: money back", out)

    def test_due_brief_says_nothing_when_nothing_burns(self):
        code, _, out, err = self.cli("due", "--brief")
        self.assertEqual((code, out.strip(), err.strip()), (0, "", ""))
        self.cli("add", "Ticket refund", "--goal", "money back", "--first-step-now")
        self.assertIn("Ticket refund", self.cli("due", "--brief")[2])

    def test_the_session_start_hook_makes_no_task_file_of_its_own(self):
        """`due --brief` is what the SessionStart hook runs, in every session on this computer. It opened the
        database, so `~/.claude/chasecall/chasecall.db` appeared the first time the person started Claude Code
        with the plugin installed - before `/chasecall:setup`, whose first step says in as many words that it is
        the one that makes the file, and before anybody had agreed to anything. There is nothing to show someone
        who has no tasks yet, so: make nothing, say nothing, exit 0."""
        nowhere = os.path.join(self.tmp.name, "not asked for", "chasecall.db")
        code, _, out, err = self.cli("due", "--brief", env_extra={"CHASECALL_DB": nowhere})
        self.assertEqual((code, out.strip(), err.strip()), (0, "", ""))
        self.assertFalse(os.path.exists(nowhere))
        self.assertFalse(os.path.exists(os.path.dirname(nowhere)))      # not even the folder around it
        # and the moment the person really asks for something, the file is made exactly as it always was
        self.assertEqual(self.cli("add", "Refund", "--goal", "money back", "--first-step-now",
                                  env_extra={"CHASECALL_DB": nowhere})[0], 0)
        self.assertTrue(os.path.exists(nowhere))
        self.assertIn("Refund", self.cli("due", "--brief", env_extra={"CHASECALL_DB": nowhere})[2])

    def test_a_refusal_leaves_the_exit_code_saying_so(self):
        self.cli("add", "Ticket refund", "--goal", "money back")
        self.assertEqual(self.cli("log", "1", "shouted", "x")[0], 2)         # unknown event kind
        self.assertEqual(self.cli("wait", "1", "--for", "soon")[0], 1)
        self.assertEqual(self.cli("show", "99")[0], 1)

    def test_the_database_follows_chasecall_db(self):
        other = os.path.join(self.tmp.name, "elsewhere", "other.db")
        self.cli("add", "Ticket refund", "--goal", "money back", env_extra={"CHASECALL_DB": other})
        self.assertTrue(os.path.exists(other))
        self.assertEqual(self.cli("list", "--json")[1]["count"], 0)          # our own database stayed empty


if __name__ == "__main__":
    unittest.main()

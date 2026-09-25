"""The tracker keeps the promises the product makes: nothing closes without proof, nobody is pushed a fourth
time, nobody is written to at night, and the clock stops the moment a task becomes the person's move.

No network, no writing outside a temporary folder: `CHASECALL_DB` points every test at its own database.
"""
import json
import os
import subprocess
import sys
import tempfile
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

    def test_a_database_from_before_the_standing_column_is_brought_up_to_date(self):
        old = os.path.join(self.tmp.name, "old.db")
        import sqlite3
        conn = sqlite3.connect(old)
        conn.executescript("""CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '', channel TEXT NOT NULL DEFAULT 'email',
            counterpart TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'open',
            attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3, next_step_at TEXT,
            "interval" TEXT NOT NULL DEFAULT '24h', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            evidence TEXT NOT NULL DEFAULT '', needs_human INTEGER NOT NULL DEFAULT 0,
            human_note TEXT NOT NULL DEFAULT '');
            INSERT INTO tasks (title, created_at, updated_at) VALUES ('older task', '2026-09-01T10:00:00+00:00',
            '2026-09-01T10:00:00+00:00');""")
        conn.commit()
        conn.close()
        upgraded = tracker.connect(old)
        try:
            self.assertEqual(tracker.list_tasks(upgraded)["tasks"][0]["standing"], 0)
            self.assertEqual(tracker.connect(old).execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
        finally:
            upgraded.close()


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

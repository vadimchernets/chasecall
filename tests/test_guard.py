"""The gate holds rule 2: a letter, a payment, a cancellation, a deletion - only after the person says yes, and
only for the fifteen minutes after they said it. And it never gets in the way of reading.

No network, no writing outside a temporary folder.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import guard  # noqa: E402
import tracker  # noqa: E402

NOW = "2026-09-24T14:00:00+00:00"

IRREVERSIBLE = {
    "the mail command": 'echo "Where is my refund?" | mail -s "Order 1182" support@shop.example',
    "sendmail": "sendmail -t < /tmp/letter.txt",
    "Mail.app": "osascript -e 'tell application \"Mail\" to send the front message'",
    "a mail API": "curl -X POST https://api.mailgun.net/v3/x/messages -d to=support@shop.example",
    "python smtplib": "python3 -c 'import smtplib; smtplib.SMTP(\"localhost\").sendmail(1, 2, 3)'",
    "stripe": "stripe charges create --amount 4000 --currency usd",
    "a payment": "curl https://shop.example/pay --data amount=40",
    "a checkout": "node checkout.js --confirm",
    "a card": "python3 buy.py --card 4242424242424242",
    "rm -rf": "rm -rf ~/Documents/old-tickets",
    "rm with a wildcard": "rm ~/Downloads/*.pdf",
    "rm of a single file of theirs": "rm ~/Desktop/photo.jpg",
    "rm behind xargs": "ls ~/Downloads | xargs rm -rf",
    "DELETE FROM": 'sqlite3 ~/notes.db "DELETE FROM notes WHERE id = 7"',
    "DROP TABLE": 'sqlite3 ~/notes.db "DROP TABLE notes"',
    "a cancellation": "curl -X POST https://api.air.example/booking/77/cancel",
    "an unsubscribe": "curl -X POST https://news.example/unsubscribe --data email=me@example.com",
    "danger hidden in a substitution": 'echo "tidying" && echo $(rm -rf ~/Desktop/notes)',
}
HARMLESS = {
    "reading a letter": "cat ~/Desktop/letter.txt",
    "searching for the word mail": "grep -ri mail ~/Documents/notes",
    "listing files": "ls -la ~/Documents",
    "git status": "git status",
    "git checkout": "git checkout main",
    "git log with the word payment in it": 'git log --grep="payment" --oneline',
    "our own due": "python3 /x/scripts/tracker.py due --json",
    "our own evidence about a card": 'python3 /x/scripts/tracker.py done 3 --evidence "money back on the card"',
    "our own human line about a payment": 'python3 /x/scripts/tracker.py human 3 "pay the 40 USD yourself"',
    "the brief": "python3 /x/scripts/brief.py --lang ru",
    "running the tests": "python3 -m unittest discover -s tests -q",
    "a date": "date -u",
    "finding a file": 'find ~/Documents -name "*mail*"',
    "writing a draft": "python3 -c \"open('/tmp/draft.txt','w').write('Dear support')\"",
    "clearing a scratch file": "rm -rf /tmp/chasecall-scratch",
    "everyday work in a repository": "git commit -m 'fix the payment page'",
    "installing something": "npm install",
    "opening a page in the browser": "open -a 'Google Chrome' https://shop.example",
}


def event(command, tool="Bash"):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}})


class Base(unittest.TestCase):
    KEYS = ("CHASECALL_DB", "CHASECALL_NOW", "CHASECALL_LANG")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {key: os.environ.get(key) for key in self.KEYS}
        for key in self.KEYS:
            os.environ.pop(key, None)
        self.db = os.path.join(self.tmp.name, "chasecall.db")
        os.environ["CHASECALL_DB"] = self.db
        os.environ["CHASECALL_NOW"] = NOW
        self.now = tracker.now_utc()

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def decide(self, command, tool="Bash", now=None):
        return guard.decide(event(command, tool), now=now)

    def approve_a_task(self, minutes_ago=0, state="waiting"):
        """A task with the person's yes written down `minutes_ago` minutes ago."""
        conn = tracker.connect()
        try:
            os.environ["CHASECALL_NOW"] = tracker.iso(self.now - timedelta(minutes=minutes_ago))
            task = tracker.add(conn, "Refund for order 1182", "money back", counterpart="support@shop.example",
                               first_step_now=True)["task"]
            tracker.log(conn, task["id"], "approved", "the person said yes to the letter")
            os.environ["CHASECALL_NOW"] = NOW
            if state == "done":
                tracker.done(conn, task["id"], "they refunded it")
            elif state == "dropped":
                tracker.drop(conn, task["id"], "we gave up")
            return task
        finally:
            conn.close()


class WithoutAYes(Base):
    def test_everything_irreversible_is_stopped(self):
        for what, command in IRREVERSIBLE.items():
            verdict = self.decide(command, now=self.now)
            self.assertEqual(verdict["decision"], "block", "%s: %s" % (what, command))
            self.assertIn("without the person's yes", verdict["reason"])

    def test_the_reason_tells_the_session_exactly_how_to_get_the_yes(self):
        reason = self.decide("rm -rf ~/Documents/old", now=self.now)["reason"]
        self.assertIn("log <id> approved", reason)
        self.assertIn("human <id>", reason)
        self.assertIn("15 minutes", reason)
        self.assertIn("rm -rf ~/Documents/old", reason)

    def test_reading_and_ordinary_work_are_never_touched(self):
        for what, command in HARMLESS.items():
            verdict = self.decide(command, now=self.now)
            self.assertEqual(verdict["decision"], "approve", "%s: %s" % (what, command))

    def test_tools_that_are_not_a_command_line_are_not_ours_to_judge(self):
        for tool in ("Read", "Grep", "Glob", "WebFetch", "Edit"):
            self.assertEqual(guard.decide(json.dumps(
                {"tool_name": tool, "tool_input": {"file_path": "/tmp/x", "command": "rm -rf /"}}),
                now=self.now)["decision"], "approve", tool)

    def test_the_gate_names_the_family_it_recognised(self):
        self.assertEqual(self.decide("sendmail -t < x", now=self.now)["family"], "mail")
        self.assertEqual(self.decide("stripe charges create", now=self.now)["family"], "money")
        self.assertEqual(self.decide("rm -rf ~/Desktop/x", now=self.now)["family"], "delete")
        self.assertEqual(self.decide("curl -X POST https://x.example/cancel", now=self.now)["family"], "cancel")


class WithAYes(Base):
    def test_a_yes_from_five_minutes_ago_opens_the_gate(self):
        self.approve_a_task(minutes_ago=5)
        verdict = self.decide("sendmail -t < /tmp/letter.txt", now=self.now)
        self.assertEqual(verdict["decision"], "approve")
        self.assertIn("said yes 5 minutes ago", verdict["reason"])

    def test_a_yes_from_yesterday_is_not_a_yes_today(self):
        self.approve_a_task(minutes_ago=20)
        self.assertEqual(self.decide("sendmail -t < /tmp/letter.txt", now=self.now)["decision"], "block")

    def test_a_yes_on_a_task_that_is_over_does_not_open_anything(self):
        for state in ("done", "dropped"):
            self.tearDown()
            self.setUp()
            self.approve_a_task(minutes_ago=2, state=state)
            self.assertEqual(self.decide("rm -rf ~/x", now=self.now)["decision"], "block", state)

    def test_the_window_closes_on_the_minute(self):
        self.approve_a_task(minutes_ago=0)
        inside = self.now + timedelta(seconds=guard.APPROVAL_WINDOW_S - 5)
        outside = self.now + timedelta(seconds=guard.APPROVAL_WINDOW_S + 5)
        self.assertEqual(self.decide("rm -rf ~/x", now=inside)["decision"], "approve")
        self.assertEqual(self.decide("rm -rf ~/x", now=outside)["decision"], "block")

    def test_a_note_that_merely_talks_about_a_yes_is_not_a_yes(self):
        conn = tracker.connect()
        try:
            task = tracker.add(conn, "Refund", "money back", first_step_now=True)["task"]
            tracker.log(conn, task["id"], "note", "the person will probably approve this")
        finally:
            conn.close()
        self.assertEqual(self.decide("rm -rf ~/x", now=self.now)["decision"], "block")


class NeverInTheWay(Base):
    def test_what_it_cannot_read_it_does_not_block(self):
        for raw in ("", "not json at all", "[]", '{"tool_name": "Bash"}', '{"tool_name": "Bash", "tool_input": 5}',
                    '{"tool_input": {"command": "rm -rf /"}}', "null"):
            self.assertEqual(guard.decide(raw, now=self.now)["decision"], "approve", repr(raw))

    def test_a_missing_database_means_no_yes_but_no_crash(self):
        os.environ["CHASECALL_DB"] = os.path.join(self.tmp.name, "nowhere", "chasecall.db")
        self.assertEqual(self.decide("rm -rf ~/x", now=self.now)["decision"], "block")
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "nowhere")))   # a hook creates nothing

    def test_a_broken_database_does_not_take_the_session_down(self):
        with open(self.db, "w", encoding="utf-8") as handle:
            handle.write("this is not a database")
        self.assertEqual(self.decide("rm -rf ~/x", now=self.now)["decision"], "block")
        self.assertEqual(self.decide("cat ~/notes.txt", now=self.now)["decision"], "approve")

    def test_an_empty_command_is_nothing_to_judge(self):
        self.assertEqual(self.decide("   ", now=self.now)["decision"], "approve")


class CommandLine(Base):
    def run_guard(self, stdin):
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "guard.py")], input=stdin,
                              capture_output=True, text=True, env=dict(os.environ), timeout=60)
        return done.returncode, json.loads(done.stdout), done.stderr

    def test_the_hook_answers_in_the_shape_claude_code_expects(self):
        code, data, err = self.run_guard(event("rm -rf ~/Documents"))
        self.assertEqual((code, data["decision"], err), (0, "block", ""))
        self.assertTrue(data["reason"])
        code, data, _ = self.run_guard(event("ls ~/Documents"))
        self.assertEqual((code, data), (0, {"decision": "approve"}))

    def test_the_hook_survives_rubbish_on_its_input(self):
        code, data, _ = self.run_guard("}{")
        self.assertEqual((code, data["decision"]), (0, "approve"))


if __name__ == "__main__":
    unittest.main()

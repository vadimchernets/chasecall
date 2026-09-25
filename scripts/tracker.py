#!/usr/bin/env python3
"""The memory of a chased task: what it is, what counts as done, how many pushes it took, when to come back.

Product rules this file defends, so that no prompt has to remember them:
- a task closes only with evidence (`done --evidence "<what proves it>"`), never on a feeling that it went through;
- no more than `max_attempts` pushes on one channel: after that `due` stops proposing another letter and calls the
  human in (`human`), because a fourth identical reminder is spam, not chasing;
- night silence 22:00-08:00 local time: `due` still shows what is burning, but never proposes writing at night;
- the only file we ever touch is our own database (`CHASECALL_DB`, default `~/.claude/chasecall/chasecall.db`).

Standard library only, no network, no pip. Runs as a CLI and imports cleanly from the tests.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DEFAULT_DB = os.path.join("~", ".claude", "chasecall", "chasecall.db")

STATES = ("open", "waiting", "blocked", "done", "dropped")
LIVE_STATES = ("open", "waiting", "blocked")       # a task that still exists for us
DUE_STATES = ("open", "waiting")                   # a task we may still push ourselves
CLOSED_STATES = ("done", "dropped")
CHANNELS = ("email", "phone", "web", "person", "other")
EVENT_KINDS = ("note", "sent", "reply", "escalated", "approved")

NIGHT_START = 22   # local hour when we go quiet
NIGHT_END = 8      # local hour when we may write again
DEFAULT_INTERVAL = "24h"
DEFAULT_MAX_ATTEMPTS = 3

# The background routine and a live session share one database file. How long we wait for the other one to
# finish writing before we give up - and what we say when we do, because a person aged 68 is not going to be
# shown a Python traceback. Both languages: this sentence reaches the person through `brief.py --lang ru` and
# `inbox.py --lang ru`, and an English one there would be the only English line on their screen.
BUSY_WAIT_SECONDS = 10.0
BUSY_MESSAGES = {
    "en": ("the task file is busy right now - something else is writing to it. Nothing was changed; "
           "try again in a moment."),
    "ru": ("файл с делами сейчас занят - в него пишет что-то другое. Ничего не изменено, "
           "попробуйте ещё раз через минуту."),
}
# Not the same thing at all, and the difference is the whole of the advice: a lock passes by itself in a moment,
# permissions do not, and "try again in a moment" sends the person round that loop for ever.
UNWRITABLE_MESSAGES = {
    "en": ("the task file %s cannot be written to - the permissions on it do not allow it. Nothing was changed, "
           "and this one will not pass by itself."),
    "ru": ("в файл с делами %s не записать - права на него этого не позволяют. Ничего не изменено, и само это "
           "не пройдёт."),
}
# And the third thing that can be wrong with a file: it is not our file. A text file, half a download, or a
# database somebody else made with a `tasks` of their own that is not a table. We read nothing out of it and we
# write nothing into it - and the person is told which file we mean, because they chose it.
NOT_OURS_MESSAGES = {
    "en": ("%s is not a Chasecall task file - nothing was read from it and nothing was written to it. Move it "
           "aside, or say where the real one is."),
    "ru": ("%s - это не файл дел Chasecall: из него ничего не прочитано и в него ничего не записано. Уберите "
           "его в сторону или скажите, где настоящий."),
}
BUSY_WORDS = ("locked", "busy")                    # what sqlite says when it is the other process, not the mode
PERMISSION_WORDS = ("readonly", "read-only", "permission", "denied", "unable to open")

DUR_RE = re.compile(r"^\s*(\d+)\s*([mhdw])\s*$", re.IGNORECASE)
DUR_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    goal          TEXT    NOT NULL DEFAULT '',
    channel       TEXT    NOT NULL DEFAULT 'email',
    counterpart   TEXT    NOT NULL DEFAULT '',
    state         TEXT    NOT NULL DEFAULT 'open',
    attempts      INTEGER NOT NULL DEFAULT 0,
    max_attempts  INTEGER NOT NULL DEFAULT 3,
    next_step_at  TEXT,
    "interval"    TEXT    NOT NULL DEFAULT '24h',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    evidence      TEXT    NOT NULL DEFAULT '',
    needs_human   INTEGER NOT NULL DEFAULT 0,
    human_note    TEXT    NOT NULL DEFAULT '',
    standing      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  INTEGER NOT NULL REFERENCES tasks(id),
    ts       TEXT    NOT NULL,
    kind     TEXT    NOT NULL DEFAULT 'note',
    text     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(state, next_step_at);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, ts);
"""

TASK_FIELDS = ("id", "title", "goal", "channel", "counterpart", "state", "attempts", "max_attempts",
               "next_step_at", "interval", "created_at", "updated_at", "evidence", "needs_human", "human_note",
               "standing")
# There is deliberately no migration list here. `standing` has been in SCHEMA since before the first release, so
# the one `ALTER TABLE ... ADD COLUMN standing` that used to sit here could only ever fail and be swallowed -
# a line that looked like care for old databases while doing nothing, on a version that has no old databases.
# When a column really is added later, it belongs here with a test that a database without it is brought up to
# date, not with a bare `except: pass`.


class TrackerError(Exception):
    """Something the person (or the skill) asked for that we refuse to do, with a reason they can read."""


def in_words(mapping, lang):
    return mapping.get(lang if lang in mapping else "en", mapping["en"])


def db_trouble(exc, path=None, lang="en"):
    """The sentence for a database we could not prepare: the person's language, and the right problem.

    Three different accidents with opposite advice, and telling them apart is the whole point: the other process
    will be finished in a moment, the permissions will not change by themselves, and a file that is not ours will
    never become ours. One sentence for all three sent a person with a read-only file round the same loop for ever.
    """
    text = str(exc).lower()
    if any(word in text for word in BUSY_WORDS):
        return TrackerError(in_words(BUSY_MESSAGES, lang))
    if any(word in text for word in PERMISSION_WORDS):
        return TrackerError(in_words(UNWRITABLE_MESSAGES, lang) % (path or db_path()))
    return TrackerError(in_words(NOT_OURS_MESSAGES, lang) % (path or db_path()))


def tables_of(conn, names):
    """Which of `names` are really tables in this database - asked after the CREATEs, because a statement that
    ran is not the same thing as a table that is there: `CREATE TABLE IF NOT EXISTS tasks` is a silent no-op on a
    database where `tasks` is somebody's view, and every line after it would be a traceback."""
    holes = ", ".join("?" for _ in names)
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (%s)" % holes, tuple(names)).fetchall()}


# ---------------------------------------------------------------- time


def now_utc():
    """Current moment in UTC. `CHASECALL_NOW` (ISO-8601) freezes it for the tests and for the hooks' own tests."""
    raw = os.environ.get("CHASECALL_NOW")
    if raw:
        return parse_iso(raw)
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_iso(text):
    """ISO-8601 in, aware UTC datetime out. A naive stamp is read as UTC, because that is what we write."""
    value = str(text).strip()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise TrackerError("cannot read the time %r (expected ISO-8601, e.g. 2026-09-24T21:00:00+00:00)" % text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_every(text):
    """'30m' | '24h' | '3d' | '2w' -> timedelta. Anything else is a mistake we say out loud."""
    match = DUR_RE.match(str(text))
    if not match:
        raise TrackerError("cannot read the interval %r; use 30m, 24h, 3d or 2w" % text)
    amount = int(match.group(1))
    if amount <= 0:
        raise TrackerError("the interval %r must be greater than zero" % text)
    return timedelta(**{DUR_UNITS[match.group(2).lower()]: amount})


def local_of(dt):
    """The same moment in the person's own time zone: night is 22:00-08:00 where they live, not in UTC."""
    return dt.astimezone()


def is_night(dt):
    return dt.hour >= NIGHT_START or dt.hour < NIGHT_END


def night_ends_at(dt_local):
    """The next local 08:00 after `dt_local` (used only for the human-readable line)."""
    day = dt_local.replace(hour=NIGHT_END, minute=0, second=0, microsecond=0)
    if dt_local.hour >= NIGHT_START:
        day = day + timedelta(days=1)
    return day


def fmt_local(iso_text):
    """An ISO stamp from the database as the person reads it: local time, no seconds, no time zone noise."""
    if not iso_text:
        return "-"
    try:
        return local_of(parse_iso(iso_text)).strftime("%Y-%m-%d %H:%M")
    except TrackerError:
        return str(iso_text)


def humanize(seconds):
    """A rough distance in time, for lines like 'overdue for 2d 3h'."""
    seconds = int(abs(seconds))
    if seconds < 60:
        return "a moment"
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 86400:
        hours, rest = divmod(seconds, 3600)
        return "%dh" % hours if rest < 600 else "%dh %dm" % (hours, rest // 60)
    days, rest = divmod(seconds, 86400)
    hours = rest // 3600
    return "%dd" % days if hours == 0 else "%dd %dh" % (days, hours)


# ---------------------------------------------------------------- database


def db_path():
    return os.path.expanduser(os.environ.get("CHASECALL_DB") or DEFAULT_DB)


def connect(path=None, lang="en"):
    """Open (and on first use create) our own database. Nothing outside this file is ever written.

    A background routine run and a live session share this one file, so a write may find it locked. `timeout` is
    sqlite's own busy timeout: we wait that long for the other process instead of failing at once, and if the
    wait runs out we say it in one sentence the person can read - in their language, and never as a traceback.
    """
    path = path or db_path()
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, mode=0o700, exist_ok=True)
    fresh = not os.path.exists(path)
    conn = sqlite3.connect(path, timeout=BUSY_WAIT_SECONDS)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    except sqlite3.DatabaseError as exc:           # locked, read-only, or not a database at all
        conn.close()
        raise db_trouble(exc, path, lang)
    # There is no "and are the tables really there?" check here, and it is not an oversight. Both our tables are
    # indexed by SCHEMA, and `CREATE INDEX ... ON tasks(...)` refuses out loud on anything called `tasks` that is
    # not a table - so by this line they exist. A check that cannot be made to fail is not a guard, it is a line
    # nobody can test; `inbox.migrate` keeps one because there it really can fire (`inbox_settings` has no index)
    # and a test makes it fire.
    if fresh:
        try:                                      # letters and phone numbers: readable by their owner only
            os.chmod(path, 0o600)
        except OSError:
            pass
    return conn


def _task_row(conn, task_id):
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(task_id),)).fetchone()
    if row is None:
        raise TrackerError("there is no task #%s" % task_id)
    return row


def task_dict(row):
    data = {key: row[key] for key in TASK_FIELDS}
    data["needs_human"] = int(data["needs_human"] or 0)
    data["standing"] = int(data["standing"] or 0)
    return data


def add_event(conn, task_id, kind, text):
    if kind not in EVENT_KINDS:
        raise TrackerError("unknown event kind %r; use one of: %s" % (kind, ", ".join(EVENT_KINDS)))
    conn.execute("INSERT INTO events (task_id, ts, kind, text) VALUES (?, ?, ?, ?)",
                 (int(task_id), iso(now_utc()), kind, text or ""))


def touch(conn, task_id, **fields):
    fields["updated_at"] = iso(now_utc())
    columns = ", ".join('"%s" = ?' % name for name in fields)
    conn.execute("UPDATE tasks SET %s WHERE id = ?" % columns, list(fields.values()) + [int(task_id)])


# ---------------------------------------------------------------- commands


def add(conn, title, goal, channel="email", counterpart="", every=DEFAULT_INTERVAL, first_step_now=False,
        max_attempts=DEFAULT_MAX_ATTEMPTS, standing=False, now=None):
    title = (title or "").strip()
    goal = (goal or "").strip()
    if not title:
        raise TrackerError("a task needs a title")
    if not goal:
        raise TrackerError("a task needs a goal: what exactly counts as done")
    if channel not in CHANNELS:
        raise TrackerError("unknown channel %r; use one of: %s" % (channel, ", ".join(CHANNELS)))
    if int(max_attempts) < 1:
        raise TrackerError("max_attempts must be at least 1")
    now = now or now_utc()
    step = now if first_step_now else now + parse_every(every)
    cur = conn.execute(
        """INSERT INTO tasks (title, goal, channel, counterpart, state, attempts, max_attempts, next_step_at,
                              "interval", created_at, updated_at, evidence, needs_human, human_note, standing)
           VALUES (?, ?, ?, ?, 'open', 0, ?, ?, ?, ?, ?, '', 0, '', ?)""",
        (title, goal, channel, counterpart or "", int(max_attempts), iso(step), str(every), iso(now), iso(now),
         1 if standing else 0))
    task_id = cur.lastrowid
    add_event(conn, task_id, "note", "%s created (%s -> %s)"
              % ("standing task" if standing else "task", channel, counterpart or "nobody named yet"))
    conn.commit()
    return {"ok": True, "id": task_id, "task": task_dict(_task_row(conn, task_id))}


def log(conn, task_id, kind, text):
    """Write down what happened. The tracker never guesses: what is not logged did not happen."""
    row = _task_row(conn, task_id)
    add_event(conn, row["id"], kind, text)
    touch(conn, row["id"])
    conn.commit()
    return {"ok": True, "id": row["id"], "kind": kind, "text": text or "", "state": row["state"]}


def wait(conn, task_id, for_, now=None):
    """One push has gone out; we now wait for a reply. This is where the attempt counter grows.

    Not for a standing task ("look at what is new", every 7 days, forever): there is nobody to push and nothing to
    run out of, so it only gets its next date - otherwise three weeks of a harmless habit would end with us
    solemnly telling the person their reminder needs a phone call.
    """
    row = _task_row(conn, task_id)
    if row["state"] in CLOSED_STATES:
        raise TrackerError("task #%s is %s; reopen it before waiting on it" % (row["id"], row["state"]))
    now = now or now_utc()
    step = now + parse_every(for_)
    if int(row["standing"] or 0):
        touch(conn, row["id"], next_step_at=iso(step), **{"interval": str(for_)})
        add_event(conn, row["id"], "note", "standing task: coming back at %s" % iso(step))
        conn.commit()
        return {"ok": True, "id": row["id"], "state": row["state"], "standing": 1,
                "attempts": int(row["attempts"]), "max_attempts": int(row["max_attempts"]),
                "next_step_at": iso(step)}
    attempts = int(row["attempts"]) + 1
    touch(conn, row["id"], state="waiting", attempts=attempts, next_step_at=iso(step), **{"interval": str(for_)})
    add_event(conn, row["id"], "note", "attempt %d/%d sent; waiting until %s"
              % (attempts, int(row["max_attempts"]), iso(step)))
    conn.commit()
    return {"ok": True, "id": row["id"], "state": "waiting", "standing": 0, "attempts": attempts,
            "max_attempts": int(row["max_attempts"]), "next_step_at": iso(step)}


def human(conn, task_id, what):
    """Hand the task to the person: a call, a payment, a signature - the things we never do for them."""
    row = _task_row(conn, task_id)
    what = (what or "").strip()
    if not what:
        raise TrackerError("say what exactly the person has to do")
    # No next step of ours: the clock stops until the person acts, so `due` stops nagging and `brief` asks instead.
    touch(conn, row["id"], state="blocked", needs_human=1, human_note=what, next_step_at=None)
    add_event(conn, row["id"], "escalated", what)
    conn.commit()
    return {"ok": True, "id": row["id"], "state": "blocked", "needs_human": 1, "human_note": what}


def done(conn, task_id, evidence):
    """Closing needs proof. Without it we would only be closing the chat window, not the task."""
    row = _task_row(conn, task_id)
    evidence = (evidence or "").strip()
    if not evidence:
        raise TrackerError("a task closes only with evidence: what proves it (booking number, reply, screenshot)")
    touch(conn, row["id"], state="done", evidence=evidence, needs_human=0, next_step_at=None)
    add_event(conn, row["id"], "note", "done: %s" % evidence)
    conn.commit()
    return {"ok": True, "id": row["id"], "state": "done", "evidence": evidence}


def drop(conn, task_id, why):
    row = _task_row(conn, task_id)
    why = (why or "").strip()
    if not why:
        raise TrackerError("say why the task is dropped")
    touch(conn, row["id"], state="dropped", needs_human=0, next_step_at=None)
    add_event(conn, row["id"], "note", "dropped: %s" % why)
    conn.commit()
    return {"ok": True, "id": row["id"], "state": "dropped", "why": why}


def next_action(task, night, escalate):
    """The one line that tells the session what to do with this task right now."""
    if escalate:
        return ("attempts are used up (%d/%d) - stop writing and call the person in: "
                'tracker.py human %d "<what they must do>"' % (task["attempts"], task["max_attempts"], task["id"]))
    if night:
        return ("night window (%02d:00-%02d:00 local) - show it, do not write; prepare the draft and send after "
                "%02d:00" % (NIGHT_START, NIGHT_END, NIGHT_END))
    if task["standing"]:
        return ("standing task - go and look, tell the person what is new in one line, then tracker.py wait %d "
                "--for %s" % (task["id"], task["interval"]))
    return ("push #%d by %s to %s: a new angle, not 'just reminding'; then tracker.py wait %d --for %s"
            % (task["attempts"] + 1, task["channel"], task["counterpart"] or "the counterpart",
               task["id"], task["interval"]))


def due(conn, now=None, local=None):
    """What is overdue and what to do next. Shows at night, proposes writing only by day."""
    now = now or now_utc()
    local = local or local_of(now)
    night = is_night(local)
    rows = conn.execute(
        """SELECT * FROM tasks WHERE state IN (?, ?) AND next_step_at IS NOT NULL AND next_step_at <= ?
           ORDER BY next_step_at""", DUE_STATES + (iso(now),)).fetchall()
    tasks = []
    for row in rows:
        task = task_dict(row)
        escalate = not int(row["standing"] or 0) and int(row["attempts"]) >= int(row["max_attempts"])
        task["overdue_for"] = humanize((now - parse_iso(row["next_step_at"])).total_seconds())
        task["escalate"] = escalate
        task["may_write"] = bool(not night and not escalate)
        task["action"] = next_action(task, night, escalate)
        tasks.append(task)
    blocked = [task_dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE state = 'blocked' OR needs_human = 1 ORDER BY updated_at").fetchall()
        if r["state"] not in CLOSED_STATES]
    return {"ok": True, "now": iso(now), "night": night,
            "night_until": iso(night_ends_at(local)) if night else None,
            "count": len(tasks), "tasks": tasks, "blocked_count": len(blocked), "blocked": blocked}


def list_tasks(conn, state="all"):
    order = ("CASE state WHEN 'open' THEN 0 WHEN 'waiting' THEN 1 WHEN 'blocked' THEN 2 WHEN 'done' THEN 3 "
             "ELSE 4 END, next_step_at IS NULL, next_step_at, id")
    if state in (None, "all"):
        rows = conn.execute("SELECT * FROM tasks ORDER BY " + order).fetchall()
    else:
        if state not in STATES:
            raise TrackerError("unknown state %r; use one of: %s, all" % (state, ", ".join(STATES)))
        rows = conn.execute("SELECT * FROM tasks WHERE state = ? ORDER BY next_step_at IS NULL, next_step_at, id",
                            (state,)).fetchall()
    tasks = [task_dict(r) for r in rows]
    return {"ok": True, "state": state or "all", "count": len(tasks), "tasks": tasks}


def show(conn, task_id):
    row = _task_row(conn, task_id)
    events = [{"ts": e["ts"], "kind": e["kind"], "text": e["text"]} for e in conn.execute(
        "SELECT ts, kind, text FROM events WHERE task_id = ? ORDER BY ts, id", (row["id"],)).fetchall()]
    return {"ok": True, "task": task_dict(row), "events": events}


def stats(conn, now=None):
    now = now or now_utc()
    by_state = {state: 0 for state in STATES}
    for row in conn.execute("SELECT state, COUNT(*) AS n FROM tasks GROUP BY state").fetchall():
        by_state[row["state"]] = int(row["n"])
    week_ago = iso(now - timedelta(days=7))
    done_7d = conn.execute("SELECT COUNT(*) FROM tasks WHERE state = 'done' AND updated_at >= ?",
                           (week_ago,)).fetchone()[0]
    overdue = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE state IN (?, ?) AND next_step_at IS NOT NULL AND next_step_at <= ?",
        DUE_STATES + (iso(now),)).fetchone()[0]
    attempts = conn.execute("SELECT COALESCE(SUM(attempts), 0) FROM tasks").fetchone()[0]
    return {"ok": True, "db": db_path(), "total": sum(by_state.values()), "by_state": by_state,
            "attempts": int(attempts), "done_7d": int(done_7d), "overdue": int(overdue),
            "needs_human": int(by_state["blocked"]), "events": conn.execute(
                "SELECT COUNT(*) FROM events").fetchone()[0]}


# ---------------------------------------------------------------- human-readable output


def task_line(task):
    counter = "%d/%d" % (task["attempts"], task["max_attempts"])
    who = (" -> " + task["counterpart"]) if task["counterpart"] else ""
    return "#%s [%s %s] %s%s (%s)" % (task["id"], task["state"], counter, task["title"], who, task["channel"])


def render_due(result, brief=False):
    lines = []
    if result["count"]:
        head = "%d task(s) need a step now" % result["count"]
        if result["night"]:
            head += " - night window, showing only (quiet until %s)" % fmt_local(result["night_until"])
        lines.append(head)
        for task in result["tasks"]:
            lines.append("  " + task_line(task) + "  overdue for " + task["overdue_for"])
            lines.append("      goal: " + task["goal"])
            lines.append("      next: " + task["action"])
    elif not brief:
        lines.append("Nothing is due. Next steps are scheduled; nothing to chase this minute.")
    if result["blocked_count"]:
        lines.append("%d task(s) are waiting for you:" % result["blocked_count"])
        for task in result["blocked"]:
            lines.append("  #%s %s - %s" % (task["id"], task["title"], task["human_note"] or "your move"))
    return "\n".join(lines)


def render_list(result):
    if not result["count"]:
        return "No tasks yet."
    lines = ["%d task(s), state: %s" % (result["count"], result["state"])]
    for task in result["tasks"]:
        when = fmt_local(task["next_step_at"]) if task["next_step_at"] else "-"
        lines.append("  " + task_line(task) + "  next step: " + when)
    return "\n".join(lines)


def render_show(result):
    task = result["task"]
    lines = [task_line(task),
             "  goal:        " + (task["goal"] or "-"),
             "  next step:   " + (fmt_local(task["next_step_at"]) if task["next_step_at"] else "-"),
             "  interval:    " + task["interval"],
             "  created:     " + fmt_local(task["created_at"]),
             "  updated:     " + fmt_local(task["updated_at"])]
    if task["evidence"]:
        lines.append("  evidence:    " + task["evidence"])
    if task["needs_human"]:
        lines.append("  needs you:   " + (task["human_note"] or "your move"))
    lines.append("  history:")
    for event in result["events"]:
        lines.append("    %s  %-9s %s" % (fmt_local(event["ts"]), event["kind"], event["text"]))
    return "\n".join(lines)


def render_stats(result):
    states = ", ".join("%s %d" % (name, count) for name, count in result["by_state"].items() if count)
    return "\n".join([
        "tasks: %d (%s)" % (result["total"], states or "none"),
        "overdue now: %d   waiting for you: %d   done in 7 days: %d" % (
            result["overdue"], result["needs_human"], result["done_7d"]),
        "pushes sent: %d   events: %d" % (result["attempts"], result["events"]),
        "database: " + result["db"]])


def render(command, result, brief=False):
    if command == "due":
        return render_due(result, brief)
    if command == "list":
        return render_list(result)
    if command == "show":
        return render_show(result)
    if command == "stats":
        return render_stats(result)
    if command == "add":
        task = result["task"]
        return "Task #%s taken: %s\n  goal: %s\n  first step: %s" % (
            task["id"], task["title"], task["goal"], fmt_local(task["next_step_at"]))
    if command == "wait":
        if result.get("standing"):
            return "Task #%s is a standing one: coming back %s" % (result["id"], fmt_local(result["next_step_at"]))
        return "Task #%s: attempt %d/%d logged, next step %s" % (
            result["id"], result["attempts"], result["max_attempts"], fmt_local(result["next_step_at"]))
    if command == "human":
        return "Task #%s is yours now: %s" % (result["id"], result["human_note"])
    if command == "done":
        return "Task #%s closed. Evidence: %s" % (result["id"], result["evidence"])
    if command == "drop":
        return "Task #%s dropped: %s" % (result["id"], result["why"])
    if command == "log":
        return "Task #%s: %s logged." % (result["id"], result["kind"])
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------- CLI


def build_parser():
    # `--json` is accepted on both sides of the command (`tracker.py --json due` and `tracker.py due --json`),
    # because that is how a person - and a session in a hurry - actually types it.
    # The subcommands get their own copy of the flag with no default of its own, so that a `--json` given before
    # the command is not quietly overwritten by the command's default.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print JSON instead of text")
    parser = argparse.ArgumentParser(prog="tracker.py",
                                     description="chasecall task tracker (standard library only)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_parser(name, **kwargs):
        return sub.add_parser(name, parents=[common], **kwargs)

    p_add = add_parser("add", help="take a new task")
    p_add.add_argument("title")
    p_add.add_argument("--goal", required=True, help="what exactly counts as done")
    p_add.add_argument("--channel", default="email", choices=list(CHANNELS))
    p_add.add_argument("--counterpart", default="")
    p_add.add_argument("--every", default=DEFAULT_INTERVAL, help="how often to come back: 24h, 3d, 1w")
    p_add.add_argument("--first-step-now", action="store_true", help="the first step is due right now")
    # No `--max-attempts` on the command line on purpose: three pushes on one channel is a promise the README
    # makes to the person, not a number a session may raise because this task feels important today.
    p_add.add_argument("--standing", action="store_true",
                       help="a habit, not a chase: it repeats forever, counts no attempts, calls nobody in")

    p_due = add_parser("due", help="what is overdue and what to do next")
    p_due.add_argument("--brief", action="store_true", help="say nothing when nothing is due (for SessionStart)")

    p_list = add_parser("list", help="all tasks, or one state")
    p_list.add_argument("--state", default="all", choices=list(STATES) + ["all"])

    p_show = add_parser("show", help="one task with its history")
    p_show.add_argument("id", type=int)

    p_log = add_parser("log", help="write down what happened")
    p_log.add_argument("id", type=int)
    p_log.add_argument("kind", choices=list(EVENT_KINDS))
    p_log.add_argument("text")

    p_wait = add_parser("wait", help="a push went out; wait for a reply")
    p_wait.add_argument("id", type=int)
    p_wait.add_argument("--for", dest="for_", required=True, help="48h, 3d, 1w")

    p_human = add_parser("human", help="the person has to do this one (call, pay, sign)")
    p_human.add_argument("id", type=int)
    p_human.add_argument("what")

    p_done = add_parser("done", help="close the task - evidence required")
    p_done.add_argument("id", type=int)
    p_done.add_argument("--evidence", required=True, help="what proves it: booking number, reply, screenshot")

    p_drop = add_parser("drop", help="let the task go")
    p_drop.add_argument("id", type=int)
    p_drop.add_argument("why")

    add_parser("stats", help="how the chasing is going")
    return parser


def nothing_yet(now=None):
    """The answer `due` gives when there is no task file at all: nothing is due, and nobody has been told."""
    now = now or now_utc()
    return {"ok": True, "now": iso(now), "night": is_night(local_of(now)), "night_until": None,
            "count": 0, "tasks": [], "blocked_count": 0, "blocked": []}


def run(args):
    if args.command == "due" and getattr(args, "brief", False) and not os.path.exists(db_path()):
        # `due --brief` is what the SessionStart hook runs, at the start of every session on this computer -
        # before `/chasecall:setup`, and before the person has agreed to anything at all. Opening the database
        # here created `~/.claude/chasecall/chasecall.db` on its own, while the setup skill's first step says in
        # as many words that it is the one that makes it. There is nothing to show a person whose file does not
        # exist yet, so we make nothing and say nothing. Every other command creates it as it always did.
        return nothing_yet()
    conn = connect()
    try:
        if args.command == "add":
            return add(conn, args.title, args.goal, args.channel, args.counterpart, args.every,
                       args.first_step_now, DEFAULT_MAX_ATTEMPTS, args.standing)
        if args.command == "due":
            return due(conn)
        if args.command == "list":
            return list_tasks(conn, args.state)
        if args.command == "show":
            return show(conn, args.id)
        if args.command == "log":
            return log(conn, args.id, args.kind, args.text)
        if args.command == "wait":
            return wait(conn, args.id, args.for_)
        if args.command == "human":
            return human(conn, args.id, args.what)
        if args.command == "done":
            return done(conn, args.id, args.evidence)
        if args.command == "drop":
            return drop(conn, args.id, args.why)
        if args.command == "stats":
            return stats(conn)
        raise TrackerError("unknown command %r" % args.command)
    finally:
        conn.close()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except TrackerError as exc:
        payload = {"ok": False, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else ("chasecall: %s" % exc),
              file=sys.stdout if args.json else sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        text = render(args.command, result, brief=getattr(args, "brief", False))
        if text:
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""One screen the person can read in ten seconds: done, waiting, your move, mine today.

Product rule this file defends: the person must never have to ask "what is happening with my thing?" and must
never discover a task only when it is too late. Everything a chased task can be is on this one screen, and the
line that matters most - what we cannot do without them - is always there, even when it is empty.

The repository speaks English; this screen speaks to the person, in any of the five languages the plugin
knows: `--lang en|ru|es|pt|uk`.

With `--to <folder>` the same screen is also left as a file (`brief.txt` in English, or the matching
per-language name from lang/<code>.json's "brief.file" - e.g. lang/ru.json's) in the folder the phone can
see, so the person can read it in the street without asking anyone.

That folder is usually Google Drive or Dropbox, so the file leaves the computer - and the brief carries the
titles of the tasks, who is being chased, phone numbers and notes. The product's first promise is that nothing
goes anywhere without the person's yes, so:

- nothing is written until the person has agreed to *that* folder, once, in words (`--agreed`; `--declined`
  remembers a no, so they are not asked again);
- the file is written 0600, like the database, and not 0644;
- it is written whole or not at all, and it replaces only a file that carries our own mark inside it - a
  `brief.txt` somebody else put in that folder is left exactly as it is, and we say so out loud instead of
  quietly destroying it. What is in the file decides that, never what our settings remember about the path.

`--json` is the same screen as data (and says whether the file was left in the folder), for when something
needs a number rather than a sentence. Exit 0 means everything asked for was done; exit 3 means the brief is
on the screen and the copy in the folder is not there.

Standard library only, no network. Runs as a CLI and imports cleanly from the tests.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import inbox  # noqa: E402
import tracker  # noqa: E402

LANGS = tracker.LANGS

# What the command line says when the brief itself is fine and the copy in the folder is not: the person asked
# for a file in their cloud folder and there is no file there. 1 is kept for "no brief at all".
NOT_WRITTEN = 3

# The line that says this file is ours to rewrite. It is written into the file itself, and it is the only thing
# that can say so: a file of the same name without it belongs to somebody else and is not touched, whatever our
# own settings remember about that path.
MARK = "chasecall:brief"
# How much we read from each end of the file when we look for the mark. The mark goes into the very last line,
# and a brief of 120 tasks is bigger than one read - so the end is looked at as well as the beginning.
MARK_WINDOW = 8192
CONSENT_KEY = "brief_to:%s"        # -> "yes" | "no", one answer per folder, remembered
FILE_KEY = "brief_file:%s"         # -> "ours", the paths we have written; a hint for the refusal, never a permission

# Every line of the brief comes from lang/<code>.json now (key "brief") - one table per language, on equal
# footing, built once at import time. The mark baked into "updated" there already matches MARK above.
WORDS = {code: tracker.load_lang(code)["brief"] for code in LANGS}


def collect(conn, now=None, local=None):
    """Everything the screen shows, as plain data - so `--json` and both languages read the same numbers."""
    now = now or tracker.now_utc()
    local = local or tracker.local_of(now)
    day_ago = tracker.iso(now - timedelta(days=1))
    end_of_day = tracker.iso(local.replace(hour=23, minute=59, second=59, microsecond=0))

    done = [tracker.task_dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE state = 'done' AND updated_at >= ? ORDER BY updated_at DESC",
        (day_ago,)).fetchall()]
    waiting = [tracker.task_dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE state = 'waiting' ORDER BY next_step_at IS NULL, next_step_at").fetchall()]
    needs_you = [tracker.task_dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE needs_human = 1 AND state NOT IN ('done', 'dropped') ORDER BY updated_at"
    ).fetchall()]
    mine = [tracker.task_dict(r) for r in conn.execute(
        """SELECT * FROM tasks WHERE state IN ('open', 'waiting') AND needs_human = 0
           AND next_step_at IS NOT NULL AND next_step_at <= ? AND attempts < max_attempts
           ORDER BY next_step_at""", (end_of_day,)).fetchall()]
    out_of_attempts = [tracker.task_dict(r) for r in conn.execute(
        """SELECT * FROM tasks WHERE state IN ('open', 'waiting') AND attempts >= max_attempts AND standing = 0
           ORDER BY next_step_at IS NULL, next_step_at""").fetchall()]
    return {"ok": True, "now": tracker.iso(now), "date": local.strftime("%Y-%m-%d"),
            "night": tracker.is_night(local), "done_24h": done, "waiting": waiting,
            "needs_you": needs_you + out_of_attempts, "mine_today": mine,
            "counts": {"done_24h": len(done), "waiting": len(waiting),
                       "needs_you": len(needs_you) + len(out_of_attempts), "mine_today": len(mine)}}


def _line(task, words, with_next=False, with_evidence=False, with_attempt=False):
    parts = ["  #%s %s" % (task["id"], task["title"])]
    if task["counterpart"]:
        parts.append(" -> " + task["counterpart"])
    tail = []
    if with_next and task["next_step_at"]:
        tail.append("%s %s" % (words["next_step"], tracker.fmt_local(task["next_step_at"])))
    if with_attempt:
        tail.append("%s %d/%d" % (words["attempt"], task["attempts"], task["max_attempts"]))
    if with_evidence and task["evidence"]:
        tail.append("%s: %s" % (words["evidence"], task["evidence"]))
    if tail:
        parts.append("  (" + ", ".join(tail) + ")")
    return "".join(parts)


def render(data, lang="en"):
    words = WORDS[lang if lang in WORDS else "en"]
    counts = data["counts"]
    lines = [words["header"] % data["date"], ""]
    if not any(counts.values()):
        lines.append(words["empty_all"])
        return "\n".join(lines)

    lines.append(words["done"] + " (%d)" % counts["done_24h"])
    lines += [_line(t, words, with_evidence=True) for t in data["done_24h"]] or [words["empty_section"]]
    lines.append("")

    lines.append(words["waiting"] + " (%d)" % counts["waiting"])
    lines += [_line(t, words, with_next=True, with_attempt=True) for t in data["waiting"]] \
        or [words["empty_section"]]
    lines.append("")

    lines.append(words["needs_you"] + " (%d)" % counts["needs_you"])
    if data["needs_you"]:
        for task in data["needs_you"]:
            note = task["human_note"] or words["out_of_attempts"]
            lines.append("  #%s %s - %s" % (task["id"], task["title"], note))
    else:
        lines.append(words["nothing_for_you"])
    lines.append("")

    lines.append(words["mine"] + " (%d)" % counts["mine_today"])
    lines += [_line(t, words, with_next=True) for t in data["mine_today"]] or [words["empty_section"]]
    if data["night"]:
        lines.append("  " + words["night"] % (tracker.NIGHT_START, tracker.NIGHT_END))
    lines.append("")
    lines.append(words["tail"] % (words["tail_some"] % counts["needs_you"] if counts["needs_you"]
                                  else words["tail_nothing"]))
    return "\n".join(lines)


def file_name(lang="en"):
    return WORDS[lang if lang in WORDS else "en"]["file"]


def words_for(lang):
    return WORDS[lang if lang in WORDS else "en"]


def is_ours(path):
    """Is the file lying at `path` our own brief, or somebody else's?

    Only the file itself may answer that, and only by carrying our mark. What our settings remember about a path
    is a memory of the past, never a permission for the present: the person deletes our brief, puts their own
    note under that same name - "IMPORTANT: the doctor's number is ..." - and a memory that said "ours" would
    have us destroy it without reading a byte. A file we are not sure about is never ours.

    The mark is written in the last line, so both ends of the file are looked at: a brief of 120 tasks is 16 KB,
    and reading only the beginning made us disown our own brief and ask the person what that file was.
    """
    needle = MARK.encode("utf-8")
    try:
        with open(path, "rb") as handle:
            if needle in handle.read(MARK_WINDOW):
                return True
            size = handle.seek(0, os.SEEK_END)
            if size <= MARK_WINDOW:
                return False                       # already read whole: the mark is not in it
            handle.seek(size - MARK_WINDOW)
            return needle in handle.read(MARK_WINDOW)
    except OSError:
        return False                               # a file we cannot even read is not one we may replace


def write_to(folder, text, lang="en", now=None, conn=None, agreed=False, declined=False):
    """Leave the brief in the shared folder as a file the phone can open - once the person has said yes.

    Refusals, in the order they are met: no folder named; a folder we will not point at at all; a folder that is
    not on this computer (the cloud client has not synced it - we do not create a look-alike empty one); nobody
    has agreed to this folder yet; the person said no; a file of that name is already there and does not carry
    our mark - whatever we may have written at that path before.
    Only past all of those is anything written, and then whole (a temporary name of our own in the same folder,
    then `os.replace`) and readable by its owner only.
    """
    said = words_for(lang)
    name = file_name(lang)
    empty = {"ok": False, "path": None, "error": "", "ask": "", "need_consent": False}
    raw = str(folder or "").strip()
    if not raw:
        return dict(empty, error=said["no_folder"])
    try:
        base = inbox.check_path(raw, lang)
    except tracker.TrackerError as exc:
        return dict(empty, error=said["bad_folder"] % exc)
    target = os.path.join(base, name)
    if not os.path.isdir(base):
        return dict(empty, path=target, error=said["not_here"] % base)

    close_after = conn is None
    if close_after:
        conn = inbox.connect(lang=lang)
    try:
        key = CONSENT_KEY % base
        if declined:
            inbox.set_setting(conn, key, "no")
        elif agreed:
            inbox.set_setting(conn, key, "yes")
        answer = inbox.get_setting(conn, key)
        if answer == "no":
            return dict(empty, path=target, error=said["declined"] % base)
        if answer != "yes":
            return dict(empty, path=target, error=said["not_agreed"] % base, ask=said["ask"], need_consent=True)
        if os.path.lexists(target) and not is_ours(target):
            # We may have written a brief at this very path once. That explains the sentence; it does not change
            # it - what is lying there now is somebody else's file and stays exactly as it is.
            key = "occupied_again" if inbox.get_setting(conn, FILE_KEY % target) else "occupied"
            return dict(empty, path=target, error=said[key] % (name, base))

        stamp = tracker.fmt_local(tracker.iso(now or tracker.now_utc()))
        body = text.rstrip("\n") + "\n\n" + (said["updated"] % stamp) + "\n"
        handle_id, temp = tempfile.mkstemp(prefix="." + name + ".", suffix=".part", dir=base)
        try:
            with os.fdopen(handle_id, "w", encoding="utf-8") as handle:
                handle.write(body)
            os.chmod(temp, 0o600)                  # the same as the database: names and phone numbers are theirs
            os.replace(temp, target)
        except OSError as exc:
            try:
                os.remove(temp)
            except OSError:
                pass
            return dict(empty, path=target, error=said["failed"] % (target, exc))
        inbox.set_setting(conn, FILE_KEY % target, "ours")
    finally:
        if close_after:
            conn.close()
    return {"ok": True, "path": target, "error": "", "ask": "", "need_consent": False}


def build_parser():
    parser = argparse.ArgumentParser(prog="brief.py", description="chasecall one-screen brief")
    parser.add_argument("--lang", default=os.environ.get("CHASECALL_LANG", "en"), choices=list(LANGS))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--to", default=None, metavar="FOLDER",
                        help="also leave the brief as a file in this folder, for the phone to read")
    agree = parser.add_mutually_exclusive_group()
    agree.add_argument("--agreed", action="store_true",
                       help="the person has just said yes to the brief living in that folder")
    agree.add_argument("--declined", action="store_true",
                       help="the person said no; remember it and stop asking")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        conn = inbox.connect(lang=args.lang)
    except tracker.TrackerError as exc:
        print("chasecall: %s" % exc, file=sys.stderr)
        return 1
    try:
        data = collect(conn)
        text = render(data, args.lang)
        written = write_to(args.to, text, args.lang, conn=conn,
                           agreed=args.agreed, declined=args.declined) if args.to else None
    finally:
        conn.close()
    if args.json:
        if written is not None:
            data = dict(data, written_to=written["path"] if written["ok"] else None,
                        write_error=written["error"], needs_consent=written["need_consent"])
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(text)
    if written is not None:
        if written["ok"]:
            print("chasecall: brief written to " + written["path"], file=sys.stderr)
        else:
            print("chasecall: " + written["error"], file=sys.stderr)
            if written["ask"]:
                print("chasecall: say this to the person, in their own words - " + written["ask"],
                      file=sys.stderr)
                print("chasecall: " + words_for(args.lang)["ask_how"], file=sys.stderr)
            # The screen is right either way, so this is not a failure of the brief - but "asked for the file
            # and did not get it" and "got it" cannot both be 0, or the only way to tell them apart is to read
            # our English prose on stderr and guess.
            return NOT_WRITTEN
    return 0


if __name__ == "__main__":
    sys.exit(main())

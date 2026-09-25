#!/usr/bin/env python3
"""One screen the person can read in ten seconds: done, waiting, your move, mine today.

Product rule this file defends: the person must never have to ask "what is happening with my thing?" and must
never discover a task only when it is too late. Everything a chased task can be is on this one screen, and the
line that matters most - what we cannot do without them - is always there, even when it is empty.

The repository speaks English; this screen speaks to the person, so it is bilingual: `--lang ru|en`.

With `--to <folder>` the same screen is also left as a file (`сводка.txt`, or `brief.txt` in English) in the
folder the phone can see, so the person can read it in the street without asking anyone.

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

LANGS = ("en", "ru")

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

WORDS = {
    "en": {
        "header": "chasecall - %s",
        "done": "Done in the last 24 hours",
        "waiting": "Waiting for an answer",
        "needs_you": "Needs you",
        "mine": "I take these today",
        "empty_all": "Nothing on the list yet. Say: \"chase <the thing>\" - and I will take it and keep at it.",
        "empty_section": "  nothing",
        "next_step": "next step",
        "attempt": "attempt",
        "evidence": "proof",
        "goal": "goal",
        "night": "Night window %02d:00-%02d:00: I am not writing to anyone now, I will send in the morning.",
        "nothing_for_you": "  nothing - you do not have to do anything right now",
        "out_of_attempts": "attempts used up, I am handing it over",
        "tail": "One line for you: %s",
        "tail_nothing": "nothing is waiting on you",
        "tail_some": "%d task(s) wait for your move",
        "file": "brief.txt",
        "updated": ("Updated %s (" + MARK + "). This file is rewritten every time; nothing else in the folder "
                    "is touched."),
        "ask": ("I can leave this brief in that folder as a file, so you can read it on your phone. It has the "
                "names of your tasks in it, who you are chasing, the phone numbers and the notes. That folder "
                "goes to your cloud - Google Drive or Dropbox - so the file goes there too. Shall I?"),
        "not_agreed": ("nothing was written: nobody has said yes to leaving the brief in %s, and it travels to "
                       "the cloud from there"),
        "ask_how": ("ask the person the question above, in their own words, and run the same command with "
                    "--agreed on a yes, or with --declined on a no"),
        "declined": "the brief is not left in %s: the person said no. Nothing was written.",
        "occupied": ("there is already a file called %s in %s and it is not ours. It was left exactly as it is "
                     "and nothing was written - ask the person what that file is, or use another folder."),
        "occupied_again": ("the file called %s in %s is not the one we wrote: our brief is gone from there and "
                           "somebody else's file is under that name now. It was left exactly as it is and "
                           "nothing was written - ask the person what that file is, or use another folder."),
        "no_folder": "say which folder the brief should be left in",
        "not_here": "the folder %s is not on this computer right now; the brief was not written",
        "bad_folder": "%s",
        "failed": "could not write %s: %s",
    },
    "ru": {
        "header": "chasecall - %s",
        "done": "Сделано за сутки",
        "waiting": "Ждёт ответа",
        "needs_you": "Нужно от вас",
        "mine": "Возьму сам сегодня",
        "empty_all": "Пока пусто. Скажите: «добейся <чего>» - и я возьму дело и буду вести его до результата.",
        "empty_section": "  ничего",
        "next_step": "следующий шаг",
        "attempt": "попытка",
        "evidence": "доказательство",
        "goal": "цель",
        "night": "Ночное окно %02d:00-%02d:00: сейчас никому не пишу, отправлю утром.",
        "nothing_for_you": "  ничего - от вас сейчас ничего не требуется",
        "out_of_attempts": "попытки кончились, передаю вам",
        "tail": "Одной строкой: %s",
        "tail_nothing": "от вас сейчас ничего не нужно",
        "tail_some": "дел, ждущих вашего шага: %d",
        "file": "сводка.txt",
        "updated": ("Обновлено %s (" + MARK + "). Файл переписывается заново каждый раз; больше в этой папке "
                    "ничего не трогается."),
        "ask": ("Я могу класть эту сводку в ту папку файлом, чтобы вы читали её с телефона. В ней названия "
                "ваших дел, с кем вы их ведёте, телефоны и заметки. Эта папка уходит в ваше облако - Google "
                "Диск или Dropbox, - значит, и файл уедет туда. Класть?"),
        "not_agreed": ("ничего не записано: никто не говорил «да» на то, чтобы сводка лежала в %s, а оттуда "
                       "она уезжает в облако"),
        "ask_how": ("задайте человеку вопрос выше его словами и повторите ту же команду с --agreed на «да» "
                    "или с --declined на «нет»"),
        "declined": "сводку в %s не кладу: человек сказал «нет». Ничего не записано.",
        "occupied": ("файл %s в папке %s уже есть, и он не наш. Он оставлен как есть, ничего не записано - "
                     "спросите человека, что это за файл, или возьмите другую папку."),
        "occupied_again": ("файл %s в папке %s - не тот, что писали мы: нашей сводки там больше нет, а под этим "
                           "именем лежит чужой файл. Он оставлен как есть, ничего не записано - спросите "
                           "человека, что это за файл, или возьмите другую папку."),
        "no_folder": "скажите, в какую папку класть сводку",
        "not_here": "папки %s сейчас нет на этом компьютере; сводка не записана",
        "bad_folder": "%s",
        "failed": "не удалось записать %s: %s",
    },
}


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

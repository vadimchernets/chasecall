#!/usr/bin/env python3
"""The bridge from the phone: one shared folder, and a memory of what has already been looked at.

The person is out in the town. They photograph a letter, jot a line, record twenty seconds of voice, and use the
system "Share" to drop it into a folder that both their phone and their computer can see (Google Drive or
Dropbox - not iCloud, which does not exist on Android). At home, Claude Code opens that folder and turns what is
in it into tasks.

Product rules this file defends:
- **nothing is read here.** This script lists names, kinds, dates and sizes, and nothing else. What is *inside* a
  photo or a note is for the session to look at with its own eyes, after the person is in the room;
- **nothing is deleted and nothing is overwritten.** A sorted file is moved into a `done/` subfolder of the same
  folder, by this script and never by a shell command: names come from a phone and from a shared cloud folder,
  so a name like `note" ; rm -rf ~ ; "x.txt` must be a name and nothing else. If `done/` already holds a file of
  that name, the new one is given a free name next to it - both survive;
- **only the one folder the person named.** The path is checked before it is remembered: not `/`, not the home
  folder, not `~/Documents`, and not a folder that already holds somebody's whole life;
- **what was shown once is not shown again** - the folder is a queue, not a list that grows louder every morning.
  A file that has been shown but not yet sorted is still reachable (scope `pending`), so nothing is lost silently;
- a file that is still arriving (zero bytes: the cloud has made the name but not the contents) is reported and
  *not* counted as shown, so it comes back when it is whole.

The state lives in the tracker's own database, in a `seen_files` table created on first use.

`--json` on every command is part of the interface on purpose: the sentences here are written for a person,
in one of two languages, and a session that needs a *number* - how many are new, was the file renamed, where
did it land - reads the JSON instead of parsing prose it wrote itself.

Standard library only, no network. Runs as a CLI and imports cleanly from the tests.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import tracker  # noqa: E402

InboxError = tracker.TrackerError

FOLDER_KEY = "inbox_folder"

# Where a sorted file goes, inside the folder the person named. These two names, and no others: `--into` is
# checked against this tuple, so nothing can be built out of a name that came from a phone.
DONE_DIRS = ("done", "разобрано")

# A folder with more than this many things in it is not a place somebody drops a photo from the street; it is
# their Documents, their Desktop or the whole of their Dropbox. We refuse it instead of offering to sort it.
CROWDED_FOLDER = 200

KINDS = (
    ("photo", (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp", ".tif", ".tiff")),
    ("note", (".txt", ".md", ".rtf", ".markdown")),
    ("voice", (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".caf", ".amr", ".aiff")),
    ("video", (".mov", ".mp4", ".m4v", ".3gp", ".avi")),
    ("document", (".pdf", ".doc", ".docx", ".pages", ".odt", ".xls", ".xlsx", ".csv", ".numbers")),
)

# Half-arrived downloads and the litter every sync client leaves behind. Not the person's material.
JUNK_NAMES = {".ds_store", "desktop.ini", "thumbs.db", "icon\r", ".localized"}
JUNK_SUFFIXES = (".tmp", ".part", ".partial", ".crdownload", ".download", ".icloud", "~")
# Our own brief, left in the same folder for the phone to read (`brief.py --to`). It did not come from the phone,
# so it is never offered back to the person as something to sort.
OURS = {"brief.txt", "сводка.txt"}

LANGS = ("en", "ru")

# Everything the person is shown, in their own language. No command names live in here: a command on the screen
# of someone who has never opened a terminal is noise at best and an instruction they cannot follow at worst.
WORDS = {
    "en": {
        "kinds": {"photo": "photo", "note": "note", "voice": "voice recording", "video": "video",
                  "document": "document", "other": "file"},
        "sizes": ("B", "KB", "MB", "GB"),
        "no_folder_yet": "No folder from the phone has been named yet.",
        "folder_is": "The folder from the phone: %s",
        "folder_not_here": " - it is not on this computer right now",
        "folder_gone": "The folder %s is not on this computer right now, so there is nothing to look at.",
        "head_new": "%d new from the phone:",
        "head_pending": "%d not sorted yet:",
        "head_all": "%d in the folder:",
        "in_folder": "(in %s)",
        "nothing_new": "Nothing new from the phone. (in %s)",
        "arriving": "not all of it is here yet - it will be whole next time",
        "is_sorted": "sorted",
        "shown_before": "%d more were shown earlier and are still not sorted.",
        "pending_of_all": "%d of them are not sorted yet.",
        "marked": "Written down as sorted: %s. The file itself was not touched.",
        "moved": "%s now lies in the %s folder inside the same folder. Nothing was deleted.",
        "moved_renamed": ("%s now lies in the %s folder inside the same folder, under the name %s: a file of the "
                          "first name was already there, and both are still here."),
        "already_done": "%s was already in the %s folder; only the note was written down.",
        # refusals
        "need_folder": "Say which folder both the phone and this computer can see.",
        "no_folder_set": "No folder from the phone has been named yet.",
        "too_high": ("I will not take %s: that is the home folder or a folder at the very top, with everything "
                     "you own inside it. Name the one folder in Google Drive or Dropbox that you share things "
                     "into from the phone - a folder of its own, inside them."),
        "crowded": ("%s already holds %d things, and nothing new from the street would be visible among them. "
                    "If this is not the folder you share into from the phone, name that one instead. If it is "
                    "the right one, the things you have already dealt with can move into the done folder inside "
                    "it - I do that after your yes - or you can put them away into folders of your own by hand; "
                    "then name it again."),
        "not_a_folder": "%s is a file, not a folder.",
        "need_name": "Say which file.",
        "no_such_file": "There is no file called %s in the folder from the phone.",
        "outside": ("%s is not in the folder from the phone. That one folder is the only place I touch, so I am "
                    "not moving it."),
        "bad_into": "A sorted file goes into %s and nowhere else.",
        "move_failed": "%s could not be moved: %s. Nothing was lost; it is where it was.",
    },
    "ru": {
        "kinds": {"photo": "фотография", "note": "записка", "voice": "голосовая запись", "video": "видео",
                  "document": "документ", "other": "файл"},
        "sizes": ("Б", "КБ", "МБ", "ГБ"),
        "no_folder_yet": "Папка с телефона пока не названа.",
        "folder_is": "Папка с телефона: %s",
        "folder_not_here": " - сейчас её на этом компьютере нет",
        "folder_gone": "Папки %s сейчас на этом компьютере нет, смотреть нечего.",
        "head_new": "Новое с телефона, %d:",
        "head_pending": "Ещё не разобрано, %d:",
        "head_all": "Всего в папке %d:",
        "in_folder": "(в папке %s)",
        "nothing_new": "С телефона ничего нового. (в папке %s)",
        "arriving": "пришло ещё не целиком - в следующий раз будет весь",
        "is_sorted": "разобрано",
        "shown_before": "Ещё %d показывал раньше, они так и не разобраны.",
        "pending_of_all": "Из них не разобрано: %d.",
        "marked": "Записал как разобранное: %s. Сам файл не тронут.",
        "moved": "%s теперь лежит в папке %s внутри той же папки. Ничего не удалено.",
        "moved_renamed": ("%s теперь лежит в папке %s внутри той же папки под именем %s: файл с первым именем "
                          "там уже был, и оба на месте."),
        "already_done": "%s уже лежал в папке %s; записал только пометку.",
        # refusals
        "need_folder": "Скажите, какую папку видят и телефон, и этот компьютер.",
        "no_folder_set": "Папка с телефона пока не названа.",
        "too_high": ("%s я не возьму: это домашняя папка или папка на самом верху, в ней лежит всё ваше. "
                     "Назовите одну папку в Google Диске или Dropbox, в которую вы кладёте с телефона, - "
                     "отдельную папку внутри них."),
        "crowded": ("В папке %s уже %d файлов и папок - среди них не разглядеть то, что только что пришло с "
                    "улицы. Если это не та папка, в которую вы кладёте с телефона, назовите ту. А если та "
                    "самая - разобранное можно убирать в папку разобрано внутри неё, я переношу туда после "
                    "вашего «да», или разложите файлы по своим папкам руками и назовите её снова."),
        "not_a_folder": "%s - это файл, а не папка.",
        "need_name": "Скажите, какой файл.",
        "no_such_file": "Файла с именем %s в папке с телефона нет.",
        "outside": ("%s лежит не в папке с телефона. Я трогаю только эту одну папку, поэтому переносить не буду."),
        "bad_into": "Разобранное уходит в %s и больше никуда.",
        "move_failed": "%s перенести не удалось: %s. Ничего не потеряно, файл там же, где был.",
    },
}


def words(lang="en"):
    return WORDS.get(lang if lang in WORDS else "en", WORDS["en"])


def say(lang, key, *args):
    text = words(lang)[key]
    return text % args if args else text


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS seen_files (
           path          TEXT PRIMARY KEY,
           name          TEXT    NOT NULL,
           kind          TEXT    NOT NULL DEFAULT 'other',
           size          INTEGER NOT NULL DEFAULT 0,
           modified_at   TEXT    NOT NULL DEFAULT '',
           first_seen_at TEXT    NOT NULL DEFAULT '',
           done          INTEGER NOT NULL DEFAULT 0,
           done_at       TEXT    NOT NULL DEFAULT '',
           note          TEXT    NOT NULL DEFAULT ''
       )""",
    """CREATE TABLE IF NOT EXISTS inbox_settings (
           key        TEXT PRIMARY KEY,
           value      TEXT NOT NULL DEFAULT '',
           updated_at TEXT NOT NULL DEFAULT ''
       )""",
    "CREATE INDEX IF NOT EXISTS idx_seen_files_name ON seen_files(name, done)",
)
TABLES = ("seen_files", "inbox_settings")


def migrate(conn, lang="en"):
    """Make our two tables exist, whatever version of Chasecall made this database.

    The background routine and a live session share one file, so another process may hold the write lock for
    longer than our patience (sqlite's busy timeout, set in `tracker.connect`). Swallowing that and handing back
    a database without tables only moves the crash one line further on, where it reaches a person as a Python
    traceback. So: try, and then *check* - `CREATE TABLE IF NOT EXISTS seen_files` does nothing at all and says
    nothing at all on a database where `seen_files` is somebody's view - and say it in words if they are missing.
    """
    try:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()
        have = tracker.tables_of(conn, TABLES)
    except sqlite3.DatabaseError as exc:           # locked, read-only, or not a database at all
        raise tracker.db_trouble(exc, tracker.db_path(), lang)
    if not set(TABLES) <= have:                    # the statements ran and the tables are still not there
        raise tracker.db_trouble(sqlite3.DatabaseError("seen_files is not a table"), tracker.db_path(), lang)
    return conn


def connect(path=None, lang="en"):
    return migrate(tracker.connect(path, lang), lang)


# ---------------------------------------------------------------- settings


def get_setting(conn, key):
    row = conn.execute("SELECT value FROM inbox_settings WHERE key = ?", (key,)).fetchone()
    return (row["value"] if row else "") or ""


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO inbox_settings (key, value, updated_at) VALUES (?, ?, ?)",
                 (key, value, tracker.iso(tracker.now_utc())))
    conn.commit()
    return value


# ---------------------------------------------------------------- the folder we were told about


def resolve(path):
    """A path as we always mean it: `~` expanded, quotes from a phone name stripped, symbolic links followed.

    Resolving and arguing are two jobs. This one never raises, so two paths can be compared - is this the folder
    we were already told about? - without the comparison itself refusing anything.
    """
    raw = os.path.expanduser(str(path or "").strip().strip("'\""))
    return os.path.realpath(os.path.abspath(raw)) if raw else ""


def check_path(path, lang="en"):
    """The one folder we are allowed to point at, resolved and argued with.

    A folder we accept here is one the session will later list, and offer to move files inside. Pointed at `/`,
    at the home folder or at `~/Documents`, that is an offer to shuffle somebody's own files around under the
    name "what came from your phone". So: no root, no home folder, no folder that holds the home folder, and at
    least one level of nesting below either - a folder of its own, made for this.
    """
    real = resolve(path)
    if not real:
        raise InboxError(say(lang, "need_folder"))
    home = os.path.realpath(os.path.expanduser("~"))
    root = os.path.abspath(os.sep)
    if os.path.exists(real) and not os.path.isdir(real):
        raise InboxError(say(lang, "not_a_folder", real))
    if real in (root, home) or home.startswith(real.rstrip(os.sep) + os.sep):
        raise InboxError(say(lang, "too_high", real))
    base = home if real.startswith(home + os.sep) else root
    if len([part for part in os.path.relpath(real, base).split(os.sep) if part not in ("", ".")]) < 2:
        raise InboxError(say(lang, "too_high", real))
    return real


def how_crowded(path, stop_at=CROWDED_FOLDER):
    """How many things are in the folder, counted no further than we need to know."""
    seen = 0
    try:
        with os.scandir(path) as scan:
            for _ in scan:
                seen += 1
                if seen > stop_at:
                    break
    except OSError:
        return 0
    return seen


def check_folder(path, lang="en"):
    """Both arguments about a folder somebody is *naming*: what it is, and how full it already is.

    How full it is used to be asked only of a folder being remembered (`--set`), and `--folder` walked straight
    past it: `list --folder ~/Documents` handed the person 250 of their own papers as "what came from your
    phone", and `file-done --folder` then offered to move them. The flag is documented in the skill, so it is not
    a back door somebody had to find - it was the front one. A folder that is not on this computer yet is fine
    (the cloud client may not have synced it); a folder that is the person's whole life is not.

    This is for the moment of naming only - see `_folder_for` for why the folder already named is never refused
    for being full.
    """
    real = check_path(path, lang)
    if os.path.isdir(real):
        crowd = how_crowded(real)
        if crowd > CROWDED_FOLDER:
            raise InboxError(say(lang, "crowded", real, crowd))
    return real


def get_folder(conn):
    value = get_setting(conn, FOLDER_KEY)
    return os.path.expanduser(value) if value else None


def set_folder(conn, path, lang="en"):
    """Remember it - after both arguments, because naming it is the moment they are worth having."""
    real = check_folder(path, lang)
    set_setting(conn, FOLDER_KEY, real)
    return {"ok": True, "folder": real, "exists": os.path.isdir(real)}


def folder(conn, set_=None, lang="en"):
    """`--set` remembers it; `--get`, or nothing, tells what is remembered."""
    if set_:
        return set_folder(conn, set_, lang)
    known = get_folder(conn)
    return {"ok": True, "folder": known, "exists": bool(known) and os.path.isdir(known)}


def _folder_for(conn, path, lang="en"):
    """The folder a command works in: the one named on the line, else the remembered one.

    **What kind of path it is** - `/`, the home folder, a folder holding the home folder, a file rather than a
    folder - is argued with here every single time, for both, because that never stops being true.

    **How full it is** is a different question, and it belongs only where a folder is being *named*: `--set`, and
    a `--folder` pointing somewhere we have not been told about. That is where "you have named your Documents"
    is caught, and there the refusal has a way out - name another folder.

    On the folder already named it had no way out and became a wall. A real phone folder fills up from ordinary
    use, and the day it passed two hundred things *every* command was refused - including `file-done`, the one
    command that makes the pile smaller, and `list`, which only reads names. The person was told to "make a
    folder inside it for the phone and name that one" about the very folder their phone was sending to. A check
    whose only outcome is that nobody can use their own folder is not protecting them from anything: they named
    it, they fill it, and nothing here deletes or overwrites a thing in it.
    """
    known = get_folder(conn)
    if path:
        if known and resolve(path) == resolve(known):
            return check_path(path, lang)          # the folder already named, pointed at again by its own name
        return check_folder(path, lang)            # a folder being named now: ask how full it is, once
    return check_path(known, lang) if known else None


# ---------------------------------------------------------------- what is in the folder (names only)


def kind_of(name):
    lower = name.lower()
    for kind, suffixes in KINDS:
        if lower.endswith(suffixes):
            return kind
    return "other"


def is_junk(name):
    lower = name.lower()
    return (lower.startswith(".") or lower in JUNK_NAMES or lower in OURS
            or lower.endswith(JUNK_SUFFIXES))


def human_size(size, lang="en"):
    size = int(size or 0)
    names = words(lang)["sizes"]
    if size < 1024:
        return "%d %s" % (size, names[0])
    if size < 1024 * 1024:
        return "%.0f %s" % (size / 1024.0, names[1])
    if size < 1024 * 1024 * 1024:
        return "%.1f %s" % (size / (1024.0 * 1024.0), names[2])
    return "%.1f %s" % (size / (1024.0 * 1024.0 * 1024.0), names[3])


def _entry(path, stat):
    name = os.path.basename(path)
    return {"name": name, "path": path, "kind": kind_of(name), "size": int(stat.st_size),
            "modified_at": tracker.iso(datetime.fromtimestamp(stat.st_mtime, timezone.utc)),
            "arriving": int(stat.st_size) == 0}


def read_folder(path):
    """Top level only, files only, no contents. A folder we cannot open is an empty one, not a crash."""
    entries = []
    try:
        with os.scandir(path) as scan:
            for item in scan:
                try:
                    if not item.is_file(follow_symlinks=False) or is_junk(item.name):
                        continue
                    entries.append(_entry(os.path.join(path, item.name), item.stat(follow_symlinks=False)))
                except OSError:
                    continue                       # a file that vanished mid-sync: it will be here next time
    except (OSError, ValueError):
        return []
    entries.sort(key=lambda item: (item["modified_at"], item["name"]))
    return entries


def _known(conn):
    return {row["path"]: row for row in conn.execute("SELECT * FROM seen_files").fetchall()}


def scan(conn, path=None, scope="new", now=None, lang="en"):
    """Everything the two commands need, as plain data, so `--json` and the screen read the same numbers.

    `scope`: `new` - never shown before; `pending` - in the folder and not sorted yet; `all` - everything there.
    """
    now = now or tracker.now_utc()
    chosen = _folder_for(conn, path, lang)
    result = {"ok": True, "folder": chosen, "exists": False, "scope": scope, "count": 0, "files": [],
              "counts": {"new": 0, "pending": 0, "done": 0, "total": 0}, "reason": ""}
    if not chosen:
        result["reason"] = "no folder is set yet"
        return result
    if not os.path.isdir(chosen):
        result["reason"] = "the folder is not on this computer right now"
        return result

    result["exists"] = True
    known = _known(conn)
    fresh, files = [], []
    for entry in read_folder(chosen):
        row = known.get(entry["path"])
        entry["state"] = "new" if row is None else ("done" if int(row["done"] or 0) else "seen")
        entry["note"] = (row["note"] if row is not None else "") or ""
        if row is None and not entry["arriving"]:
            fresh.append(entry)                    # shown now, so not shown again tomorrow
        files.append(entry)

    if fresh:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_files (path, name, kind, size, modified_at, first_seen_at, done) "
            "VALUES (?, ?, ?, ?, ?, ?, 0)",
            [(e["path"], e["name"], e["kind"], e["size"], e["modified_at"], tracker.iso(now)) for e in fresh])
        conn.commit()

    result["counts"] = {
        "new": sum(1 for e in files if e["state"] == "new"),
        "pending": sum(1 for e in files if e["state"] != "done"),
        "done": sum(1 for e in files if e["state"] == "done"),
        "total": len(files)}
    if scope == "all":
        chosen_files = files
    elif scope == "pending":
        chosen_files = [e for e in files if e["state"] != "done"]
    else:
        chosen_files = [e for e in files if e["state"] == "new"]
    result["files"] = chosen_files
    result["count"] = len(chosen_files)
    return result


def list_files(conn, path=None, scope="new", now=None, lang="en"):
    return scan(conn, path=path, scope=scope, now=now, lang=lang)


# ---------------------------------------------------------------- marking one thing as sorted


def _find_row(conn, wanted, folder_path, lang="en"):
    """A file may be named by its full path, by its name, or by where it now lies (`done/photo.jpg`)."""
    raw = (wanted or "").strip().strip("'\"")
    if not raw:
        raise InboxError(say(lang, "need_name"))
    candidates = [os.path.abspath(os.path.expanduser(raw))]
    if folder_path:
        candidates.append(os.path.abspath(os.path.join(folder_path, raw)))
        for sub in DONE_DIRS:
            candidates.append(os.path.abspath(os.path.join(folder_path, sub, os.path.basename(raw))))
    for candidate in candidates:
        row = conn.execute("SELECT * FROM seen_files WHERE path = ?", (candidate,)).fetchone()
        if row is not None:
            return row, candidate
    name = os.path.basename(raw)
    row = conn.execute("SELECT * FROM seen_files WHERE name = ? ORDER BY done, first_seen_at DESC LIMIT 1",
                       (name,)).fetchone()
    if row is not None:
        return row, row["path"]
    for candidate in candidates:                   # never listed (a file sorted the minute it arrived)
        if os.path.isfile(candidate):
            return None, candidate
    raise InboxError(say(lang, "no_such_file", os.path.basename(raw) or raw))


def _remember_done(conn, target, note, stamp, size=0, modified_at=""):
    conn.execute("INSERT OR REPLACE INTO seen_files "
                 "(path, name, kind, size, modified_at, first_seen_at, done, done_at, note) "
                 "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                 (target, os.path.basename(target), kind_of(target), int(size), modified_at, stamp, stamp,
                  note or ""))


def mark(conn, wanted, note="", path=None, now=None, lang="en"):
    """Sorted, and the file left exactly where it is. Moving it is `file_done`, and only after a yes."""
    now = now or tracker.now_utc()
    chosen = _folder_for(conn, path, lang)
    row, target = _find_row(conn, wanted, chosen, lang)
    stamp = tracker.iso(now)
    if row is None:
        # A file we have never listed. Writing it down is harmless in itself, but `mark "/somewhere/else.pdf"`
        # would put a row about somebody's own paper into our table and call it sorted post from their phone.
        if not chosen:
            raise InboxError(say(lang, "no_folder_set"))
        if not _inside(chosen, target):
            raise InboxError(say(lang, "outside", os.path.basename(target) or target))
        size, modified_at = 0, ""
        try:
            stat = os.stat(target)
            size = int(stat.st_size)
            modified_at = tracker.iso(datetime.fromtimestamp(stat.st_mtime, timezone.utc))
        except OSError:
            pass
        _remember_done(conn, target, note, stamp, size, modified_at)
    else:
        conn.execute("UPDATE seen_files SET done = 1, done_at = ?, note = ? WHERE path = ?",
                     (stamp, note or (row["note"] or ""), row["path"]))
        target = row["path"]
    conn.commit()
    return {"ok": True, "file": os.path.basename(target), "path": target, "done": 1, "note": note or "",
            "moved": False}


# ---------------------------------------------------------------- moving a sorted file into done/


def _inside(folder_path, target):
    base = os.path.realpath(folder_path).rstrip(os.sep)
    real = os.path.realpath(target)
    return real != base and real.startswith(base + os.sep)


def free_name(folder_path, name):
    """A name in this folder that nobody is using. Two phones both send `IMG_0001.HEIC`, and a note gets sent
    twice; neither may quietly replace the other, so the second one gets `IMG_0001 (2).HEIC`."""
    target = os.path.join(folder_path, name)
    if not os.path.lexists(target):
        return target
    stem, ext = os.path.splitext(name)
    number = 2
    while True:
        target = os.path.join(folder_path, "%s (%d)%s" % (stem, number, ext))
        if not os.path.lexists(target):
            return target
        number += 1


def file_done(conn, wanted, note="", into=DONE_DIRS[0], path=None, now=None, lang="en"):
    """Move one sorted file into `done/` inside the same folder, and write down that it is sorted.

    The move happens here and never in a shell command: the name came from a phone or from a folder somebody
    else can write into, and `mv "<folder>/<name>"` would hand a name like `note" ; rm -rf ~ ; "x.txt` to the
    shell. Nothing is overwritten (`free_name`), nothing leaves the folder (`_inside`), nothing is deleted.
    """
    now = now or tracker.now_utc()
    chosen = _folder_for(conn, path, lang)
    if not chosen:
        raise InboxError(say(lang, "no_folder_set"))
    if into not in DONE_DIRS:
        raise InboxError(say(lang, "bad_into", " / ".join(DONE_DIRS)))
    raw = (wanted or "").strip().strip("'\"")
    if not raw:
        raise InboxError(say(lang, "need_name"))
    named = raw if os.path.isabs(os.path.expanduser(raw)) else os.path.join(chosen, raw)
    source = os.path.realpath(os.path.expanduser(named))
    if not _inside(chosen, source):
        raise InboxError(say(lang, "outside", os.path.basename(raw) or raw))
    stamp = tracker.iso(now)

    already = os.path.dirname(source) != os.path.realpath(chosen)
    if already and os.path.isfile(source):         # somebody moved it by hand already: only write it down
        result = mark(conn, source, note, chosen, now, lang)
        result.update({"into": os.path.basename(os.path.dirname(source)), "moved": False, "renamed": False})
        return result
    if not os.path.isfile(source):
        raise InboxError(say(lang, "no_such_file", os.path.basename(raw) or raw))

    # Where it is going is checked exactly like where it came from. `into` is already one of `DONE_DIRS`, and
    # that tuple is two words we wrote ourselves - but "it is one of ours" is a promise about a constant, and
    # `_inside` is a fact about a path. Add `".."` to that tuple, one line, and every test still passed while
    # `file-done --into ..` carried the file out of the folder: the source was checked and the target was not.
    done_dir = os.path.join(chosen, into)
    if not _inside(chosen, done_dir):
        raise InboxError(say(lang, "bad_into", " / ".join(DONE_DIRS)))
    try:
        os.makedirs(done_dir, exist_ok=True)
        target = free_name(done_dir, os.path.basename(source))
        os.replace(source, target)
    except OSError as exc:
        raise InboxError(say(lang, "move_failed", os.path.basename(source), exc))

    size, modified_at = 0, ""
    try:
        stat = os.stat(target)
        size = int(stat.st_size)
        modified_at = tracker.iso(datetime.fromtimestamp(stat.st_mtime, timezone.utc))
    except OSError:
        pass
    row = conn.execute("SELECT * FROM seen_files WHERE path = ?", (source,)).fetchone()
    conn.execute("DELETE FROM seen_files WHERE path IN (?, ?)", (source, target))
    _remember_done(conn, target, note or (row["note"] if row is not None else ""), stamp, size, modified_at)
    conn.commit()
    return {"ok": True, "file": os.path.basename(source), "path": target, "folder": chosen, "into": into,
            "done": 1, "note": note or "", "moved": True,
            "renamed": os.path.basename(target) != os.path.basename(source),
            "new_name": os.path.basename(target)}


# ---------------------------------------------------------------- human-readable output


def render_list(result, lang="en"):
    text = words(lang)
    if not result["folder"]:
        return text["no_folder_yet"]
    if not result["exists"]:
        return text["folder_gone"] % result["folder"]
    lines = []
    if result["count"]:
        head = {"new": text["head_new"], "pending": text["head_pending"], "all": text["head_all"]}
        lines.append((head.get(result["scope"], text["head_all"]) % result["count"])
                     + "  " + text["in_folder"] % result["folder"])
        for entry in result["files"]:
            line = "  %s - %s, %s, %s" % (text["kinds"].get(entry["kind"], entry["kind"]), entry["name"],
                                          tracker.fmt_local(entry["modified_at"]),
                                          human_size(entry["size"], lang))
            if entry["arriving"]:
                line += " (" + text["arriving"] + ")"
            elif result["scope"] != "new" and entry["state"] == "done":
                line += " (" + text["is_sorted"] + ")"
            lines.append(line)
    else:
        lines.append(text["nothing_new"] % result["folder"])
    if result["scope"] == "new" and result["counts"]["pending"] > result["count"]:
        lines.append(text["shown_before"] % (result["counts"]["pending"] - result["count"]))
    elif result["scope"] == "all" and result["counts"]["pending"]:
        lines.append(text["pending_of_all"] % result["counts"]["pending"])
    return "\n".join(lines)


def render(command, result, lang="en"):
    text = words(lang)
    if command == "list":
        return render_list(result, lang)
    if command == "folder":
        if not result["folder"]:
            return text["no_folder_yet"]
        return (text["folder_is"] % result["folder"]) + ("" if result["exists"] else text["folder_not_here"])
    if command == "mark":
        return text["marked"] % result["file"]
    if command == "file-done":
        if not result.get("moved"):
            return text["already_done"] % (result["file"], result.get("into") or DONE_DIRS[0])
        if result.get("renamed"):
            return text["moved_renamed"] % (result["file"], result["into"], result["new_name"])
        return text["moved"] % (result["file"], result["into"])
    return ""


# ---------------------------------------------------------------- CLI


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print JSON instead of text")
    common.add_argument("--lang", choices=list(LANGS), default=argparse.SUPPRESS,
                        help="the language the person reads")
    parser = argparse.ArgumentParser(
        prog="inbox.py", description="chasecall: what came from the phone (names only, nothing is read)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--lang", choices=list(LANGS), default=os.environ.get("CHASECALL_LANG", "en"),
                        help="the language the person reads")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", parents=[common], help="what is new in the phone folder")
    p_list.add_argument("--folder", default=None, help="the folder, if it is not the remembered one")
    scope = p_list.add_mutually_exclusive_group()
    scope.add_argument("--pending", action="store_true", help="everything not sorted yet, new or not")
    scope.add_argument("--all", action="store_true", help="everything in the folder, sorted or not")

    p_mark = sub.add_parser("mark", parents=[common], help="this one is sorted; the file is not touched")
    p_mark.add_argument("file", help="the name, or the path, of the file")
    p_mark.add_argument("--note", default="", help="one line: what was made of it (e.g. 'task #7')")
    p_mark.add_argument("--folder", default=None, help="the folder, if it is not the remembered one")

    p_done = sub.add_parser("file-done", parents=[common],
                            help="move a sorted file into done/ inside the same folder, and mark it")
    p_done.add_argument("file", help="the name of the file, exactly as it is in the folder")
    p_done.add_argument("--note", default="", help="one line: what was made of it (e.g. 'task #7')")
    p_done.add_argument("--into", default=DONE_DIRS[0], choices=list(DONE_DIRS),
                        help="the subfolder for sorted files")
    p_done.add_argument("--folder", default=None, help="the folder, if it is not the remembered one")

    p_folder = sub.add_parser("folder", parents=[common], help="remember (or tell) the shared folder")
    which = p_folder.add_mutually_exclusive_group()
    which.add_argument("--set", dest="set_", default=None, help="the path both the phone and this computer see")
    which.add_argument("--get", action="store_true", help="say which folder is remembered")
    return parser


def run(args):
    lang = getattr(args, "lang", "en")
    conn = connect(lang=lang)
    try:
        if args.command == "list":
            scope = "pending" if args.pending else ("all" if args.all else "new")
            return list_files(conn, args.folder, scope, lang=lang)
        if args.command == "mark":
            return mark(conn, args.file, args.note, args.folder, lang=lang)
        if args.command == "file-done":
            return file_done(conn, args.file, args.note, args.into, args.folder, lang=lang)
        if args.command == "folder":
            if args.get:                       # the flag the skill actually uses, read here and not by accident
                return folder(conn, lang=lang)
            if args.set_:
                return set_folder(conn, args.set_, lang)
            return folder(conn, lang=lang)     # neither flag: the same answer as `--get`
        raise InboxError("unknown command %r" % args.command)
    finally:
        conn.close()


def main(argv=None):
    args = build_parser().parse_args(argv)
    lang = getattr(args, "lang", "en")
    try:
        result = run(args)
    except InboxError as exc:
        payload = {"ok": False, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if getattr(args, "json", False)
              else ("chasecall: %s" % exc),
              file=sys.stdout if getattr(args, "json", False) else sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        text = render(args.command, result, lang)
        if text:
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Coming back to a task by itself - honestly, with what the machine actually has.

Product rule this file defends: we promise the person only what will really happen. On macOS we do NOT install a
launchd agent: a background job started that way is stopped by TCC the moment it touches Desktop or Documents
("Operation not permitted"), and the person is left believing their tasks are being chased when they are not.
Claude Code already has a background of its own - Code tab -> Routines -> New routine -> Local (Hourly / Daily /
Weekdays / Weekly), or simply saying in the chat "check my tasks every morning at nine". It runs while the app is
open and the machine is awake, and one missed run is caught up. So this script does not install anything on a Mac:
it hands the person the exact prompt to paste, and says out loud what it cannot do.

- `routine.py status`  - can we do a background at all: is `claude` in PATH, where the database is, when the tasks
                         were last swept, and how to switch the Routine on (`--lang ru|en`).
- `routine.py prompt`  - the ready prompt for the Routine, with the real path of the tracker in it.
- `routine.py windows` - Windows only: shows the `schtasks` command; installs it only with `--yes` (no TCC there).

There is deliberately no scheduled-line command here. The README sells the absence of one - "No cron, nothing
hidden" - and such a line sitting in the code is the very thing we promise not to have, one copy-and-paste
away. Nothing called it from any skill either.

`--json` gives the same answers as data, for when something needs a fact (is `claude` there, when was the
last sweep, what would the Windows command be) rather than the screen a person reads.

Standard library only, no network. Runs as a CLI and imports cleanly from the tests.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import tracker  # noqa: E402

TRACKER = os.path.join(HERE, "tracker.py")
TASK_NAME = "chasecall"
DEFAULT_INTERVAL_HOURS = 6
LANGS = ("en", "ru")

# A background run looks and prepares; it never acts. This is the same job the `watch` skill describes, word for
# word, and the two must not drift: if the routine were told to `log ... sent` and `wait`, the attempt counter
# would burn down in three quiet mornings without a single letter having left the house, and on the fourth the
# person would be told their three attempts are used up.
WATCH_PROMPT = (
    "Chasecall routine run: look and prepare, never act. "
    "1) `python3 {tracker} due --json`. "
    "2) If nothing is due, or it is night (22:00-08:00 local time), write nothing and end - no \"nothing to "
    "report\" message. "
    "3) For every task that is due, draft the next step - the letter, the new angle, what to check - and save it "
    "as a note: `python3 {tracker} log <id> note \"draft ready: <one line>\"`, so the morning brief shows it. "
    "4) If the attempts are used up, or the task needs the person - a call, a payment, a signature - run "
    "`python3 {tracker} human <id> \"<what the person must do>\"`. "
    "Never send, call, pay, cancel or delete anything, and never run `wait` or `log <id> sent`: the attempt "
    "counter belongs to letters that really went out, and nothing goes out without the person's yes in a session "
    "they are in. Close nothing without proof. "
    "Finish with one short line per task, for the person to read in the morning."
)
ALLOWED_TOOLS = "Bash(python3 {tracker}*)"

HOW_TO = {
    "en": ("Background is already in Claude Code, and it is the one that works:\n"
           "  1. Open the Claude app -> the Code tab.\n"
           "  2. Routines -> New routine -> Local.\n"
           "  3. Pick how often: Hourly / Daily / Weekdays / Weekly.\n"
           "  4. Paste the prompt from `routine.py prompt` and save.\n"
           "It runs while the app is open and the computer is awake; one missed run is caught up afterwards.\n"
           "You can also just say in the chat: \"check my tasks every morning at nine\"."),
    "ru": ("Фон уже есть в самом Claude Code - и работает именно он:\n"
           "  1. Откройте приложение Claude -> вкладка Code.\n"
           "  2. Routines -> New routine -> Local.\n"
           "  3. Выберите, как часто: Hourly / Daily / Weekdays / Weekly.\n"
           "  4. Вставьте промпт из `routine.py prompt` и сохраните.\n"
           "Работает, пока приложение открыто и компьютер не спит; один пропущенный запуск догоняется потом.\n"
           "Можно и просто сказать в чате: «проверяй мои дела каждое утро в девять»."),
}
NO_CLAUDE = {
    "en": ("I do not see `claude` in PATH, so I will not set up a background run - your tasks will come back to "
           "life in your next session, and nothing is lost."),
    "ru": ("Не вижу `claude` в PATH - фон не поставлю: дела оживут в следующей сессии, ничего не потеряется."),
}
MAC_NO_INSTALL = {
    "en": ("On macOS I install nothing by myself: a background job put in with launchd is cut off by the system's "
           "privacy protection the moment it touches your files, and you would think you were being helped when "
           "you were not. Use the Routine above - it really runs."),
    "ru": ("На macOS я сам ничего не ставлю: фоновую задачу через launchd система блокирует, как только она "
           "трогает ваши файлы, и вы будете думать, что дела ведутся, а они стоят. Включите Routine выше - "
           "он работает по-настоящему."),
}


# The four lines of the status screen. They were English whatever `--lang` said, so a Russian reader got the
# Russian four steps underneath an English table of contents - and the labels are the half of it that says
# whether anything is wrong.
LABELS = {
    "en": {"head": "chasecall background - %s", "claude": "claude in PATH: ", "db": "database:       ",
           "alive": "tasks alive:    ", "sweep": "last sweep:     ", "no": "no", "never": "never",
           "not_yet": " (not created yet)", "ago": "%s ago", "windows": "Windows task: "},
    "ru": {"head": "chasecall, фоновая работа - %s", "claude": "claude в PATH:   ", "db": "файл с делами:   ",
           "alive": "дел в работе:    ", "sweep": "последний обход: ", "no": "нет", "never": "ни разу",
           "not_yet": " (ещё не создан)", "ago": "%s назад", "windows": "Задача для Windows: "},
}

NOT_WINDOWS = {
    "en": "this is for Windows; on %s the Routine in the Code tab is the one that works",
    "ru": "это для Windows; на %s работает Routine во вкладке Code",
}


def in_words(mapping, lang):
    return mapping.get(lang if lang in mapping else "en", mapping["en"])


AUTO = object()   # "look it up yourself"; None means "there is none", which is a thing the tests need to say


def claude_bin(explicit=AUTO):
    """Where the `claude` executable is, or None. `CHASECALL_CLAUDE_BIN` wins, then PATH."""
    if explicit is not AUTO:
        return explicit or None
    from_env = os.environ.get("CHASECALL_CLAUDE_BIN")
    if from_env:
        return from_env
    return shutil.which("claude")


def prompt_text():
    return WATCH_PROMPT.format(tracker=TRACKER)


def allowed_tools():
    return ALLOWED_TOOLS.format(tracker=TRACKER)


def claude_argv(binary):
    return [binary or "claude", "-p", prompt_text(), "--allowedTools", allowed_tools()]


def windows_argv(binary, hours=DEFAULT_INTERVAL_HOURS):
    inner = subprocess.list2cmdline(claude_argv(binary))
    return ["schtasks", "/create", "/tn", TASK_NAME, "/tr", inner, "/sc", "hourly", "/mo", str(int(hours)), "/f"]


def last_sweep(now=None):
    """When the tasks were last touched at all - the honest answer to 'is anything happening?'."""
    path = tracker.db_path()
    if not os.path.exists(path):
        return None, None
    now = now or tracker.now_utc()
    try:
        conn = tracker.connect(path)
    except Exception:                             # noqa: BLE001
        return None, None
    try:
        row = conn.execute("SELECT MAX(ts) FROM events").fetchone()
    except Exception:                             # noqa: BLE001
        return None, None
    finally:
        conn.close()
    stamp = row[0] if row else None
    if not stamp:
        return None, None
    try:
        return stamp, tracker.humanize((now - tracker.parse_iso(stamp)).total_seconds())
    except tracker.TrackerError:
        return stamp, None


def open_tasks():
    path = tracker.db_path()
    if not os.path.exists(path):
        return 0
    try:
        conn = tracker.connect(path)
    except Exception:                             # noqa: BLE001
        return 0
    try:
        return int(conn.execute("SELECT COUNT(*) FROM tasks WHERE state IN ('open', 'waiting', 'blocked')"
                                ).fetchone()[0])
    except Exception:                             # noqa: BLE001
        return 0
    finally:
        conn.close()


def platform_of(explicit=None):
    name = (explicit or sys.platform).lower()
    if name.startswith("darwin") or name == "mac":
        return "darwin"
    if name.startswith("win"):
        return "win32"
    return "linux"


def status(lang="en", platform=None, binary=AUTO, hours=DEFAULT_INTERVAL_HOURS):
    where = platform_of(platform)
    found = claude_bin(binary)
    stamp, ago = last_sweep()
    data = {"ok": True, "platform": where, "claude": found, "claude_found": bool(found),
            "db": tracker.db_path(), "db_exists": os.path.exists(tracker.db_path()),
            "open_tasks": open_tasks(), "last_sweep": stamp, "last_sweep_ago": ago,
            "installs_anything": where == "win32", "how_to": HOW_TO.get(lang, HOW_TO["en"]),
            "prompt": prompt_text(), "allowed_tools": allowed_tools()}
    if not found:
        data["warning"] = NO_CLAUDE.get(lang, NO_CLAUDE["en"])
    if where == "darwin":
        data["note"] = MAC_NO_INSTALL.get(lang, MAC_NO_INSTALL["en"])
    elif where == "win32":
        data["windows_command"] = subprocess.list2cmdline(windows_argv(found, hours))
    return data


def windows(yes=False, platform=None, binary=AUTO, hours=DEFAULT_INTERVAL_HOURS, lang="en"):
    """Windows has no TCC, so a scheduled task there is honest. Still only on an explicit yes."""
    where = platform_of(platform)
    found = claude_bin(binary)
    argv = windows_argv(found, hours)
    data = {"ok": True, "platform": where, "claude": found, "claude_found": bool(found),
            "command": subprocess.list2cmdline(argv), "argv": argv, "installed": False,
            "interval_hours": int(hours)}
    if where != "win32":
        data["reason"] = in_words(NOT_WINDOWS, lang) % where
        data["how_to"] = HOW_TO.get(lang, HOW_TO["en"])
        return data
    if not found:
        data["ok"] = False
        data["reason"] = NO_CLAUDE.get(lang, NO_CLAUDE["en"])
        return data
    if not yes:
        data["reason"] = "shown only; nothing is scheduled without --yes"
        return data
    if not sys.platform.startswith("win"):        # a rendered plan is not a reason to run schtasks here
        data["reason"] = "not running schtasks on %s" % sys.platform
        return data
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        data["ok"] = False
        data["reason"] = "schtasks did not run: %s" % exc
        return data
    data["installed"] = done.returncode == 0
    data["ok"] = done.returncode == 0
    data["reason"] = (done.stdout or done.stderr or "").strip()
    return data


def render_status(data, lang="en"):
    said = LABELS.get(lang, LABELS["en"])
    lines = [said["head"] % data["platform"],
             "  " + said["claude"] + (data["claude"] or said["no"]),
             "  " + said["db"] + data["db"] + ("" if data["db_exists"] else said["not_yet"]),
             "  " + said["alive"] + "%d" % data["open_tasks"],
             "  " + said["sweep"] + (("%s (%s)" % (tracker.fmt_local(data["last_sweep"]),
                                                   said["ago"] % data["last_sweep_ago"]))
                                     if data["last_sweep"] else said["never"])]
    if data.get("warning"):
        lines += ["", data["warning"]]
    lines += ["", data["how_to"]]
    if data.get("note"):
        lines += ["", data["note"]]
    if data.get("windows_command"):
        lines += ["", said["windows"] + data["windows_command"]]
    return "\n".join(lines)


def build_parser():
    # The shared flags work on both sides of the command: `routine.py --lang ru status` and `routine.py status
    # --lang ru` are the same thing.
    # The subcommands get their own copies with no defaults of their own, so a flag given before the command
    # survives (argparse would otherwise let the command's default overwrite it).
    # `platform` and the interval stay named arguments of the functions - the tests need to ask "and what would
    # you say on Windows?" - but they are not on the command line: nothing a person types should be able to make
    # this script describe a machine they are not sitting at.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--lang", choices=list(LANGS), default=argparse.SUPPRESS)
    parser = argparse.ArgumentParser(prog="routine.py",
                                     description="chasecall background: honest about what runs")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--lang", choices=list(LANGS), default=os.environ.get("CHASECALL_LANG", "en"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", parents=[common], help="what we can promise about the background")
    sub.add_parser("prompt", parents=[common], help="the prompt to paste into a Routine")
    p_win = sub.add_parser("windows", parents=[common], help="Windows scheduled task (only with --yes)")
    p_win.add_argument("--yes", action="store_true", help="really create the task")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "status":
        data = status(args.lang)
        text = render_status(data, args.lang)
    elif args.command == "prompt":
        data = {"ok": True, "prompt": prompt_text(), "allowed_tools": allowed_tools(), "tracker": TRACKER}
        text = prompt_text()
    else:
        data = windows(args.yes, lang=args.lang)
        if data["platform"] == "win32":
            text = "\n".join([data["command"], "", data.get("reason", ""),
                              "installed: yes" if data["installed"] else "installed: no"])
        else:
            # A `schtasks /create ...` line on a Mac is an instruction the person cannot follow, in front of
            # somebody who does not know that. They get the reason and the Routine steps, and nothing to copy.
            text = "\n".join([data.get("reason", ""), "", data.get("how_to", "")])
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else text)
    return 0 if data.get("ok", True) else 3


if __name__ == "__main__":
    sys.exit(main())

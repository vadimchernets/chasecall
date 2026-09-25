#!/usr/bin/env python3
"""One screen the person can read in ten seconds: done, waiting, your move, mine today.

Product rule this file defends: the person must never have to ask "what is happening with my thing?" and must
never discover a task only when it is too late. Everything a chased task can be is on this one screen, and the
line that matters most - what we cannot do without them - is always there, even when it is empty.

The repository speaks English; this screen speaks to the person, so it is bilingual: `--lang ru|en`.
Standard library only, no network. Runs as a CLI and imports cleanly from the tests.
"""
import argparse
import json
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import tracker  # noqa: E402

LANGS = ("en", "ru")

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


def build_parser():
    parser = argparse.ArgumentParser(prog="brief.py", description="chasecall one-screen brief")
    parser.add_argument("--lang", default=os.environ.get("CHASECALL_LANG", "en"), choices=list(LANGS))
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    conn = tracker.connect()
    try:
        data = collect(conn)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render(data, args.lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())

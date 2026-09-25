#!/usr/bin/env python3
"""The PreToolUse gate: nothing irreversible happens without a yes from the person, in this session, minutes ago.

Product rule this file defends - rule 2, the one the whole plugin stands on: sending a letter, paying, cancelling a
booking and deleting things are done by the person's word, not by our judgement. A promise in a prompt is a wish;
this is a hook, so it holds even when the model is sure it knows better.

How the yes is given: the session asks, the person says it, and the session writes it down -
    python3 scripts/tracker.py log <id> approved "the person said yes to sending the letter"
For the next 15 minutes that task may act. Nothing else changes; reading is never blocked.

Reads a PreToolUse event as JSON on stdin (`tool_name`, `tool_input`), prints `{"decision": "approve"}` or
`{"decision": "block", "reason": ...}`. It fails open: what it cannot read, it does not block - a gate that jams
shut on a stray byte would teach the person to switch it off.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import tracker  # noqa: E402

APPROVAL_WINDOW_S = 15 * 60
COMMAND_TOOLS = ("bash", "shell", "run_command")

# A first word that only ever reads. Everything here is skipped before we look for anything dangerous, so that
# `grep -r mail ~/notes` or `git log` never trips the gate.
READ_ONLY_BINS = {
    "cat", "bat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "ag", "ls", "tree", "wc",
    "pwd", "whoami", "id", "date", "uname", "hostname", "which", "type", "file", "stat", "du", "df", "sort",
    "uniq", "cut", "tr", "column", "diff", "jq", "echo", "printf", "basename", "dirname", "realpath",
    "readlink", "env", "printenv", "ps", "sw_vers", "true", "test", "man", "history", "sleep", "open",
}
GIT_READS = {"status", "log", "diff", "show", "branch", "remote", "ls-files", "blame", "describe", "rev-parse"}
# Our own scripts touch nothing but our own database, and the session runs them all day long. They are safe even
# when their arguments are full of dangerous-looking words - an evidence line often says "the money is back on
# the card", and that must not read as a payment.
OUR_TOOLS = re.compile(r"\b(?:tracker|brief|guard|routine)\.py\b", re.IGNORECASE)
NOT_READ_ONLY_FLAGS = re.compile(r"(?:^|\s)-(?:-in-?place\b|i\b)|(?:^|\s)-(?:delete|exec|execdir|ok)\b")
PREFIXES = {"sudo", "doas", "time", "nohup", "command", "builtin", "exec", "nice", "xargs", "caffeinate"}
# Command substitution is split out too, so that a dangerous command cannot hide inside a harmless one.
SPLIT_RE = re.compile(r"\|\||&&|[;\n|&]|\$\(|`")
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Four families of irreversible. Each entry: (regex, what we say it looks like).
SEND_MAIL = [
    (re.compile(r"\bsendmail\b", re.I), "sending mail with sendmail"),
    (re.compile(r"\bmailx?\b\s+(?:-\S|\S+@\S+)", re.I), "sending mail with the mail command"),
    (re.compile(r"\b(?:msmtp|mutt|neomutt|swaks|s-nail)\b", re.I), "sending mail"),
    (re.compile(r"\bsmtplib\b|\bsmtp\.\w", re.I), "sending mail over SMTP"),
    (re.compile(r"\bosascript\b[\s\S]*\bmail\b", re.I), "sending mail through Mail.app"),
    (re.compile(r"\bcurl\b[\s\S]*\bapi[\w.\-]*[\s\S]*mail", re.I), "sending mail through a mail API"),
    (re.compile(r"\bcurl\b[\s\S]*mail[\s\S]*(?:-X\s*POST|--data|\s-d\s)", re.I), "posting to a mail service"),
    (re.compile(r"\b(?:mailgun|sendgrid|postmark|mailchimp)\b", re.I), "sending mail through a mail service"),
]
MONEY = [
    (re.compile(r"\bstripe\b", re.I), "a payment through Stripe"),
    (re.compile(r"\bpay(?:ment|ments|pal)?\b", re.I), "a payment"),
    (re.compile(r"\bcheckout\b", re.I), "a checkout"),
    (re.compile(r"\bcard\b", re.I), "something with a card"),
    (re.compile(r"\b(?:billing|invoice|charge)\b", re.I), "money"),
]
DELETE = [
    (re.compile(r"\brm\b\s+(?:-\S+\s+)*-\S*[rf]", re.I), "deleting files (rm -rf)"),
    (re.compile(r"\bdelete\s+from\b", re.I), "deleting rows from a database"),
    (re.compile(r"\bdrop\s+(?:table|database)\b", re.I), "dropping a table"),
]
DELETE_BINS = {"rm", "rmdir", "unlink", "shred", "srm"}
# Scratch files are the machine's own; the person's files are not. Deleting one of theirs needs their yes, with or
# without -rf, because "rm one photo" is exactly as final as "rm -rf the folder".
TEMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/tmp/", "/var/folders/", "/private/var/folders/", "/dev/")
CANCEL = [
    (re.compile(r"\bcancel\b", re.I), "cancelling something"),
    (re.compile(r"\bunsubscribe\b", re.I), "unsubscribing"),
]
NETWORK_WRITE = re.compile(r"-X\s*(?:POST|PUT|PATCH|DELETE)|--data\b|--data-\w+|\s-d\s|--form\b|\s-F\s|"
                           r"\bwget\b[\s\S]*--post", re.I)


def segments(command):
    """A command line as the separate commands it really is, so a read never covers for a write behind a pipe."""
    return [part.strip() for part in SPLIT_RE.split(command) if part.strip()]


def first_token(segment):
    tokens = [t for t in re.split(r"\s+", segment.strip()) if t]
    while tokens and (ASSIGNMENT_RE.match(tokens[0]) or os.path.basename(tokens[0]) in PREFIXES):
        tokens.pop(0)
    if not tokens:
        return "", []
    return os.path.basename(tokens[0].strip("()`\"'")), tokens[1:]


def is_read_only(segment):
    name, rest = first_token(segment)
    if not name:
        return True
    if OUR_TOOLS.search(segment):
        return True
    if name == "git":
        sub = next((t for t in rest if not t.startswith("-")), "")
        return sub in GIT_READS
    if name in ("sed", "awk", "find", "perl"):
        return not NOT_READ_ONLY_FLAGS.search(segment)
    return name in READ_ONLY_BINS


def deletes_the_persons_files(segment):
    """True when this segment removes something that is not a scratch file."""
    name, rest = first_token(segment)
    if name not in DELETE_BINS:
        return False
    targets = [token.strip("'\"") for token in rest if not token.startswith("-")]
    if not targets:
        return True
    return not all(target.startswith(TEMP_PREFIXES) for target in targets)


def dangerous(command):
    """-> (family, what it looks like) for the first irreversible thing found, else None."""
    for segment in segments(command):
        if is_read_only(segment):
            continue
        name, _ = first_token(segment)
        if name in DELETE_BINS:
            if deletes_the_persons_files(segment):
                return "delete", "deleting your files"
            continue                              # a scratch file in /tmp is the machine's own business
        for family, rules in (("mail", SEND_MAIL), ("money", MONEY), ("delete", DELETE)):
            for pattern, what in rules:
                if family == "money" and name == "git":
                    continue                      # `git checkout` is not a checkout
                if pattern.search(segment):
                    return family, what
        if NETWORK_WRITE.search(segment) or name in ("curl", "wget", "http", "httpie"):
            for pattern, what in CANCEL:
                if pattern.search(segment):
                    return "cancel", what
    return None


def command_of(data):
    """The command line out of a PreToolUse event, or None when this is not a command at all."""
    if not isinstance(data, dict):
        return None
    name = data.get("tool_name") or data.get("toolName") or data.get("tool") or ""
    short = str(name).split("__")[-1].strip().lower()
    if short not in COMMAND_TOOLS:
        return None                               # reading files, searching, thinking: not ours to gate
    tool_input = data.get("tool_input") or data.get("toolInput") or data.get("input") or {}
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if isinstance(command, list):
        command = " ".join(str(part) for part in command)
    return command if isinstance(command, str) and command.strip() else None


def recent_approval(now=None, window_s=APPROVAL_WINDOW_S, path=None):
    """The person's yes: an `approved` event, minutes old, on a task that is still alive."""
    path = path or tracker.db_path()
    if not os.path.exists(path):
        return None
    now = now or tracker.now_utc()
    try:
        conn = tracker.connect(path)
    except Exception:                             # noqa: BLE001 - a broken database must not break the session
        return None
    try:
        rows = conn.execute(
            """SELECT e.task_id, e.ts, e.text, t.title, t.state FROM events e JOIN tasks t ON t.id = e.task_id
               WHERE e.kind = 'approved' AND t.state NOT IN ('done', 'dropped')
               ORDER BY e.ts DESC LIMIT 20""").fetchall()
    except Exception:                             # noqa: BLE001
        return None
    finally:
        conn.close()
    for row in rows:
        try:
            age = (now - tracker.parse_iso(row["ts"])).total_seconds()
        except tracker.TrackerError:
            continue
        if 0 <= age <= window_s:
            return {"task_id": row["task_id"], "title": row["title"], "text": row["text"],
                    "age_s": int(age), "ts": row["ts"]}
    return None


def reason_text(what, command):
    return ("chasecall: this looks like %s, and nothing irreversible happens without the person's yes. "
            "Ask them in plain words, and when they say yes write it down: "
            'python3 %s log <id> approved "<what they agreed to>" - then run the command again (the yes holds for '
            "%d minutes). If it is their move - a call, a payment, a signature - "
            'use: python3 %s human <id> "<what they must do>". Command: %s'
            % (what, os.path.join(HERE, "tracker.py"), APPROVAL_WINDOW_S // 60,
               os.path.join(HERE, "tracker.py"), command.strip()[:200]))


def decide(raw, now=None, path=None):
    """-> {'decision': 'approve'} | {'decision': 'block', 'reason': ...}. Never raises."""
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (ValueError, TypeError):
        return {"decision": "approve"}            # unreadable input is not evidence of danger
    try:
        command = command_of(data)
        if not command:
            return {"decision": "approve"}
        found = dangerous(command)
        if not found:
            return {"decision": "approve"}
        family, what = found
        approval = recent_approval(now=now, path=path)
        if approval:
            return {"decision": "approve", "reason": "the person said yes %d minutes ago on task #%s"
                    % (approval["age_s"] // 60, approval["task_id"])}
        return {"decision": "block", "reason": reason_text(what, command), "family": family}
    except Exception:                             # noqa: BLE001 - a gate that jams shut gets switched off
        return {"decision": "approve"}


def main(argv=None):
    try:
        raw = sys.stdin.read()
    except Exception:                             # noqa: BLE001
        raw = ""
    print(json.dumps(decide(raw), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The PreToolUse gate: nothing irreversible happens without a yes from the person, for this action, minutes ago.

Product rule this file defends - rule 2, the one the whole plugin stands on: sending a letter, paying, cancelling
a booking and deleting the person's files are done on their word, not on our judgement. A promise in a prompt is a
wish; this is a hook, so it holds even when the model is sure it knows better.

How it answers, and why it matters: on anything it does not recognise as irreversible it prints NOTHING and exits
0. That means "I have no opinion" - Claude Code then asks the person for permission exactly as it always would.
It never prints an approval, because in a PreToolUse hook an approval is not "carry on", it is "skip the
permission system", and a plugin that quietly switched permissions off for every command in every project would
be a lockpick sold as a shield. To block, it writes the reason on stderr and exits 2.

How the yes is given: the session asks in plain words, the person answers, and the session writes down what they
agreed to -
    python3 scripts/tracker.py log <id> approved "yes, send the letter to the shop"
For the next 15 minutes that yes opens that one family of actions - a yes about a letter does not open a
deletion. Reading is never blocked.

WHAT THIS GATE DOES NOT CATCH - it is a guard against an accident, not against a determined attempt. Anyone who
wants past it can walk past it: a command hidden in base64 or in a script file, a value the shell resolves at run
time beyond a plain `VAR=value` on the same line, an alias or a function, a POST from a language runtime instead
of curl, a mail client or a browser driven through its own interface, a file overwritten by an editor rather than
by a shell redirection. It also cannot see anything done outside this session. Treat it as the seat belt, not as
the lock on the door.
"""
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import tracker  # noqa: E402

APPROVAL_WINDOW_S = 15 * 60
COMMAND_TOOLS = ("bash", "shell", "run_command")

# A first word that only ever reads. Checked as the first word of a segment - never as a substring, or
# `rm -rf ~/Documents/old # tracker.py` would talk its way through.
READ_ONLY_BINS = {
    "cat", "bat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "ag", "ls", "tree", "wc",
    "pwd", "whoami", "id", "date", "uname", "hostname", "which", "type", "file", "stat", "du", "df", "sort",
    "uniq", "cut", "tr", "column", "diff", "jq", "echo", "printf", "basename", "dirname", "realpath",
    "readlink", "printenv", "ps", "sw_vers", "true", "test", "man", "history", "sleep", "pbcopy", "pbpaste",
}
GIT_READS = {"status", "log", "diff", "show", "branch", "remote", "ls-files", "blame", "describe", "rev-parse"}
# Our own scripts touch nothing but our own database, so their arguments are safe even when they are full of
# frightening words: an evidence line often says "the money is back on the card", and that is not a payment.
OUR_SCRIPTS = ("tracker.py", "brief.py", "guard.py", "routine.py", "inbox.py")
INTERPRETERS = {"python", "python3", "py"}
# `env` belongs here, not among the readers: `env sendmail them@example.com` still sends the letter.
PREFIXES = {"sudo", "doas", "time", "nohup", "command", "builtin", "exec", "nice", "xargs", "caffeinate", "env"}
NOT_READ_ONLY_FLAGS = re.compile(r"(?:^|\s)-(?:-in-?place\b|i\b)|(?:^|\s)-(?:delete|exec|execdir|ok)\b")
# Command substitution is split out too, so a dangerous command cannot ride inside a harmless one. The one `|`
# that is not a pipe is the one in `>|` ("overwrite it even if the shell was told not to"): cut there, and what
# is left of the line is `echo x >` with nothing after it, and the file being emptied has become a segment of
# its own that nothing recognises.
SPLIT_RE = re.compile(r"\|\||&&|[;\n&]|(?<!>)\||\$\(|`")
# The same operators as whole words, for the one place where the line has already been read with its quotes.
SHELL_OPERATORS = {";", "&&", "||", "|", "&", ">", ">>", "<", "<<", "2>", "2>>", "&>"}
ASSIGN_RE = re.compile(r"(?:^|[;&|]\s*)([A-Za-z_][A-Za-z0-9_]*)=([^\s;&|]*)")
ASSIGNMENT_HEAD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

DELETE_BINS = {"rm", "rmdir", "unlink", "shred", "srm"}
MAIL_BINS = {"sendmail", "mailx", "mail", "msmtp", "mutt", "neomutt", "swaks", "s-nail", "postfix"}
MONEY_BINS = {"stripe", "pay", "paypal", "braintree"}
NET_BINS = {"curl", "wget", "http", "httpie"}
# Scratch files are the machine's own; the person's files are not.
TEMP_PREFIXES = ("/tmp/", "/private/tmp/", "/var/tmp/", "/var/folders/", "/private/var/folders/", "/dev/")

MAIL_SERVICES = re.compile(r"\b(?:mailgun|sendgrid|postmark|mailchimp|sparkpost|mandrill)\b", re.I)
MAIL_URL = re.compile(r"https?://\S*(?:mail|smtp|messages?/send)", re.I)
MAIL_IN_CODE = re.compile(r"\bsmtplib\b|\bsmtp\.\w|\bSMTP\s*\(", re.I)
OSASCRIPT_MAIL = re.compile(r"\bosascript\b[\s\S]*\bmail\b", re.I)
MONEY_URL = re.compile(r"https?://\S*(?:checkout|payment|/pay\b|billing|invoice|charge|stripe|card)", re.I)
CANCEL_WORD = re.compile(r"\b(?:cancel|unsubscribe)\b", re.I)
CANCEL_URL = re.compile(r"https?://\S*(?:cancel|unsubscribe)", re.I)
NETWORK_WRITE = re.compile(r"-X\s*(?:POST|PUT|PATCH|DELETE)|--data\b|--data-\w+|\s-d\s|--form\b|\s-F\s|"
                           r"\bwget\b[\s\S]*--post", re.I)
SQL_DELETE = re.compile(r"\bdelete\s+from\b|\bdrop\s+(?:table|database)\b", re.I)
PIPE_TO_SHELL = re.compile(r"\|\s*(?:sudo\s+)?(?:sh|bash|zsh|ksh|dash|python3?|perl|ruby|node)\b", re.I)
# A redirection that empties one of the person's files, in the forms a shell really accepts: `>`, `>>`, a file
# number in front of it (`2>`, `2>>`) and the "yes, clobber it" form (`>|`). The old pattern refused to look at
# anything preceded by a digit, so `2> ~/Documents/report.docx` emptied the file in silence, and `>|` fell
# between the `|` the line is split on and a character class that excludes it. `&>` arrives here already split
# on its `&`, as a segment beginning with `>`. Nothing is matched after a digit that we have not counted as the
# file number ourselves, so `2>&1` still finds no target of the person's.
REDIRECT_RE = re.compile(r"\d*>>?\|?\s*(\"[^\"]+\"|'[^']+'|[^\s;|&<>]+)")
LONG_DIGITS = re.compile(r"\b\d{14,19}\b")

# The words that make a written-down yes count for a family. Both languages: the person says it in Russian, the
# session writes it down in whatever it was thinking in.
FAMILY_WORDS = {
    "mail": ("send", "sent", "mail", "email", "letter", "write", "reply", "отправ", "письм", "почт", "напис"),
    "money": ("pay", "payment", "card", "checkout", "invoice", "charge", "bill", "оплат", "плат", "карт",
              "счёт", "счет", "деньг"),
    "delete": ("delete", "remove", "erase", "wipe", "overwrite", "rm ", "удал", "снос", "очист", "стере",
               "перезапис"),
    "cancel": ("cancel", "unsubscribe", "отмен", "отпис", "аннул"),
}
FAMILY_NAMES = {"mail": "sending mail", "money": "money", "delete": "deleting or overwriting files",
                "cancel": "cancelling"}


# ---------------------------------------------------------------- reading the command


def expand_simple_variables(command):
    """`C=sendmail; $C a@b.c` is still sendmail. Only plain assignments on the same line - the shell can do far
    more, and the header says so."""
    values = dict(ASSIGN_RE.findall(command))
    if not values:
        return command
    for name, value in values.items():
        if value:
            command = re.sub(r"\$\{%s\}|\$%s\b" % (re.escape(name), re.escape(name)), value.strip("'\""), command)
    return command


def segments(command):
    """A command line as the separate commands it really is, so a read never covers for a write behind a pipe."""
    return [part.strip() for part in SPLIT_RE.split(command) if part.strip()]


def one_command_of_ours(command):
    """One command, quotes and all, that runs one of our own scripts - and nothing else on the line.

    `segments()` cuts on `;` and `|` without looking at the quotes, which is right when the danger is hidden
    behind an operator and wrong when the *argument* is a file name from somebody's phone:
    `inbox.py file-done 'note" ; rm -rf ~ ; "x.txt'` is one command moving one badly named file, and cutting it
    up turns it into an `rm -rf ~` that never existed. `shlex` reads the quotes the way the shell does: if what
    comes out is a single command of ours, with no operator of its own, there is nothing here to judge.
    """
    if any(mark in command for mark in ("`", "$(", "\n", "\r")):
        return False                               # a substitution or a second line: more than one command here
    try:
        # `punctuation_chars` is what makes this safe: `list; rm -rf ~` has no space before the `;`, and a
        # plain split would hand back `list;` as a word and call the whole line one command.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:                             # unbalanced quotes: we do not know what this is
        return False
    if not tokens or any(token in SHELL_OPERATORS or token[0] in ";<>|&" for token in tokens):
        return False
    while tokens and (ASSIGNMENT_HEAD.match(tokens[0]) or os.path.basename(tokens[0]) in PREFIXES):
        tokens.pop(0)
    if not tokens:
        return False
    return is_ours(os.path.basename(tokens[0].strip("()`\"'")), tokens[1:])


def first_token(segment):
    tokens = [t for t in re.split(r"\s+", segment.strip()) if t]
    while tokens and (ASSIGNMENT_HEAD.match(tokens[0]) or os.path.basename(tokens[0]) in PREFIXES):
        tokens.pop(0)
    if not tokens:
        return "", []
    return os.path.basename(tokens[0].strip("()`\"'")), tokens[1:]


def arguments(rest):
    return [token.strip("'\"") for token in rest if not token.startswith("-")]


def is_ours(name, rest):
    """One of our own scripts, run directly or through python - recognised by the first words, not by a mention."""
    if name in OUR_SCRIPTS:
        return True
    if name in INTERPRETERS:
        for token in rest:
            if os.path.basename(token.strip("'\"")) in OUR_SCRIPTS:
                return True
            if not token.startswith("-"):
                return False
    return False


def is_read_only(segment):
    name, rest = first_token(segment)
    if not name:
        return True
    if is_ours(name, rest):
        return True
    if name == "git":
        sub = next((t for t in rest if not t.startswith("-")), "")
        return sub in GIT_READS
    if name in ("sed", "awk", "find", "perl"):
        return not NOT_READ_ONLY_FLAGS.search(segment)
    return name in READ_ONLY_BINS


# ---------------------------------------------------------------- whose file is this


def theirs(target):
    """True when this path is one of the person's own files: not scratch, not inside the folder we work in.

    `rm build/tmp.o` in a project is ordinary work; `rm ~/Documents/report.docx` is not, with or without -rf.
    """
    raw = str(target).strip().strip("'\"")
    if not raw or raw.startswith(("-", "&")):
        return False
    path = os.path.expanduser(raw)
    cwd = os.path.normpath(os.getcwd())
    home = os.path.normpath(os.path.expanduser("~"))
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(cwd, path))
    else:
        path = os.path.normpath(path)
    if path.startswith(TEMP_PREFIXES) or path == "/dev/null":
        return False
    if cwd == home:                               # working from the home folder: everything in it is theirs
        return True
    return not (path == cwd or path.startswith(cwd + os.sep))


def luhn_card(text):
    """A long run of digits that passes the card checksum - `touch card.txt` is not a payment, 4242... is."""
    for run in LONG_DIGITS.findall(text):
        digits = [int(char) for char in reversed(run)]
        total = 0
        for index, digit in enumerate(digits):
            if index % 2:
                digit *= 2
                digit -= 9 if digit > 9 else 0
            total += digit
        if total % 10 == 0:
            return True
    return False


# ---------------------------------------------------------------- what is irreversible here


def deletes_something(segment, name, rest):
    if name in DELETE_BINS:
        targets = arguments(rest)
        if not targets:
            return "deleting files"
        if any(theirs(target) for target in targets):
            return "deleting your files"
        return None
    if name == "find" and NOT_READ_ONLY_FLAGS.search(segment):
        roots = arguments(rest) or ["."]
        if any(theirs(root) for root in roots):
            return "deleting files that a search finds"
        return None
    if name in ("mv", "cp", "dd") and "/dev/null" in segment:
        if any(theirs(target) for target in arguments(rest) if target != "/dev/null"):
            return "throwing a file away into /dev/null"
        return None
    if SQL_DELETE.search(segment):
        return "deleting rows from a database"
    return None


def sends_mail(segment, name, rest):
    if name in MAIL_BINS:
        if name in ("mail", "mailx") and not rest:
            return None                           # bare `mail` opens the mailbox to read it
        return "sending mail"
    if OSASCRIPT_MAIL.search(segment):
        return "sending mail through Mail.app"
    if MAIL_SERVICES.search(segment) or (name in NET_BINS and MAIL_URL.search(segment)):
        return "sending mail through a mail service"
    if MAIL_IN_CODE.search(segment):
        return "sending mail over SMTP"
    return None


def spends_money(segment, name, rest):
    if name in MONEY_BINS:
        return "a payment"
    if name in NET_BINS and MONEY_URL.search(segment):
        return "a payment"
    if luhn_card(segment):
        return "something with a card number"
    return None


def cancels(segment, name, rest):
    if name in NET_BINS and (CANCEL_URL.search(segment) or (CANCEL_WORD.search(segment)
                                                            and NETWORK_WRITE.search(segment))):
        return "cancelling or unsubscribing"
    return None


def dangerous(command):
    """-> (family, what it looks like) for the first irreversible thing found, else None."""
    command = expand_simple_variables(command)
    if PIPE_TO_SHELL.search(command):
        return "delete", "running a script straight off the network"
    if one_command_of_ours(command):
        return None                               # our own script, with a file name from a phone in its hands
    for segment in segments(command):
        for target in REDIRECT_RE.findall(segment):
            if theirs(target):                    # `echo > ~/Documents/report.docx` empties it
                return "delete", "overwriting one of your files"
        if is_read_only(segment):
            continue
        name, rest = first_token(segment)
        for family, look in (("delete", deletes_something), ("mail", sends_mail),
                             ("money", spends_money), ("cancel", cancels)):
            what = look(segment, name, rest)
            if what:
                return family, what
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


# ---------------------------------------------------------------- the person's yes


def hints_of(command):
    """The words a yes could name this command by: the binaries it runs."""
    found = []
    for segment in segments(expand_simple_variables(command)):
        name, _ = first_token(segment)
        if name and len(name) > 2:
            found.append(name.lower())
    return found


def approval_covers(text, family, hints):
    """A yes counts only if it is about this: the family in words, or the command named outright."""
    said = " " + str(text or "").lower() + " "
    if any(word in said for word in FAMILY_WORDS.get(family, ())):
        return True
    return any(hint in said for hint in hints)


def approvals(now=None, window_s=APPROVAL_WINDOW_S, path=None):
    """Every yes written down in the window, on a task that is still alive."""
    path = path or tracker.db_path()
    if not os.path.exists(path):
        return []
    now = now or tracker.now_utc()
    try:
        conn = tracker.connect(path)
    except Exception:                             # noqa: BLE001 - a broken database must not break the session
        return []
    try:
        rows = conn.execute(
            """SELECT e.task_id, e.ts, e.text, t.title FROM events e JOIN tasks t ON t.id = e.task_id
               WHERE e.kind = 'approved' AND t.state NOT IN ('done', 'dropped')
               ORDER BY e.ts DESC LIMIT 20""").fetchall()
    except Exception:                             # noqa: BLE001
        return []
    finally:
        conn.close()
    fresh = []
    for row in rows:
        try:
            age = (now - tracker.parse_iso(row["ts"])).total_seconds()
        except tracker.TrackerError:
            continue
        if 0 <= age <= window_s:
            fresh.append({"task_id": row["task_id"], "text": row["text"], "age_s": int(age),
                          "title": row["title"]})
    return fresh


def reason_text(family, what, command, near_miss=None):
    tracker_py = os.path.join(HERE, "tracker.py")
    lines = ["chasecall: this looks like %s, and nothing irreversible happens without the person's yes." % what]
    if near_miss:
        lines.append("The yes on task #%s was about something else (\"%s\"), so it does not cover this."
                     % (near_miss["task_id"], (near_miss["text"] or "")[:80]))
    lines.append("Ask them in plain words, and when they say yes write down what they agreed to: "
                 "python3 %s log <id> approved \"<what exactly is allowed - say %s>\". It holds for %d minutes, "
                 "for that kind of action only." % (tracker_py, FAMILY_NAMES.get(family, family),
                                                    APPROVAL_WINDOW_S // 60))
    lines.append("If it is their move - a call, a payment, a signature - use: "
                 "python3 %s human <id> \"<what they must do>\"." % tracker_py)
    lines.append("Command: " + command.strip()[:200])
    return " ".join(lines)


def decide(raw, now=None, path=None):
    """-> (allow: bool, reason: str). Allowing means "no opinion", not "skip the permission system". Never raises."""
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (ValueError, TypeError):
        return True, ""                           # unreadable input is not evidence of danger
    try:
        command = command_of(data)
        if not command:
            return True, ""
        found = dangerous(command)
        if not found:
            return True, ""
        family, what = found
        hints = hints_of(command)
        near_miss = None
        for approval in approvals(now=now, path=path):
            if approval_covers(approval["text"], family, hints):
                return True, ""
            near_miss = near_miss or approval
        return False, reason_text(family, what, command, near_miss)
    except Exception:                             # noqa: BLE001 - a gate that jams shut gets switched off
        return True, ""


def main(argv=None):
    try:
        raw = sys.stdin.read()
    except Exception:                             # noqa: BLE001
        raw = ""
    allow, reason = decide(raw)
    if allow:
        return 0                                  # silence: Claude Code asks the person as it always would
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())

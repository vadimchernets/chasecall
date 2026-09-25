# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Open a private security advisory on GitHub instead:
go to https://github.com/vadimchernets/chasecall/security/advisories/new, describe what you found, how to
reproduce it, and what it lets someone do. You will get an answer as soon as possible.

Useful things to include: your operating system, your Claude Code version, and, if the safety hook is involved,
the exact command it allowed or blocked (remove any personal data first).

The most interesting report is a command that sends, pays, cancels or deletes something and that `scripts/guard.py`
lets through without an approval in the tracker.

## Scope

Chasecall's own code: the scripts in `scripts/`, the hooks in `hooks/`, and the skills in `skills/`. Problems in
Claude Code itself, or in the mail, banking or booking services a task involves, should go to their makers.

## What Chasecall holds

One SQLite file, `~/.claude/chasecall/chasecall.db` (or wherever `CHASECALL_DB` points): your tasks, who you are
chasing, what was written and when. It is not encrypted and it is as private as your home folder. The scripts use
the Python standard library only and never open a network connection. Chasecall has no account, no key and no
password of yours to lose.

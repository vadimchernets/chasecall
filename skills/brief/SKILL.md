---
name: brief
description: One screen of where every chased task stands - done in the last day, waiting for an answer with the date of the next step, needs the user, and what Chasecall will push today. Use when the user asks "what is waiting on me", "how are my tasks", "brief me", "что сегодня от меня нужно", "как там мои дела".
argument-hint: "[ru|en]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/brief.py *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/inbox.py *)
---

# Chasecall: the brief

The user said: $ARGUMENTS

## 1. Print it

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/brief.py --lang ru
```

Use `--lang ru` when the user writes in Russian, `--lang en` otherwise, or whatever `$ARGUMENTS` names. The script
prints four blocks: **done in the last day · waiting for an answer (with the date of the next step) · needs you ·
I will take these today**.

Show it as it comes. Do not reformat it into your own table, do not add encouragement, do not repeat it in your own
words afterwards.

Empty database: the script says so. Answer in one line - "Nothing is being chased right now." - and offer the
first task in the same line.

## 1a. The brief in the phone folder - only after they have said yes, out loud

If a phone folder is set (`inbox.py folder --get`), the same brief can be left there as a file, so they can read
it in the street:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/brief.py --lang ru --to "<folder>"
```

**The first time, the script writes nothing and hands you a question instead.** That is deliberate. The brief
carries the titles of their tasks, who they are dealing with, phone numbers and the notes - and that folder is
synced to Google Drive or Dropbox, so the file leaves this computer. "Nothing leaves your computer that you did
not send yourself" is the promise on the front page; it stays true only if this one is asked.

Put the script's question to them in their own words, once, and wait for a real answer:

> "Я могу класть эту сводку в ту папку файлом, чтобы вы читали её с телефона. В ней названия ваших дел, с кем вы
> их ведёте, телефоны и заметки. Эта папка уходит в ваше облако - значит, и файл уедет туда. Класть?"

- **Yes** → run the same command again with `--agreed`. The answer is remembered for that folder; you never ask
  a second time.
- **No** → run it with `--declined`. That is remembered too, so nobody is pestered about it again.
- **Anything unclear** → treat it as a no for now and move on. Silence is not a yes.

After that, say nothing about it at all - unless the script says it could not write. **The screen is the same
either way, so read the exit status: 0 means the file is in their folder, 3 means it is not** and the line on
stderr says why (nobody has said yes yet, they said no, the folder has not synced, or the name is taken).

One case it will report: there is already a `brief.txt` or `сводка.txt` in that folder that is **not ours** -
not ours meaning it does not carry our own mark inside it, whatever we may have written at that path before.
The person deletes our brief and leaves their own note under the same name; that note is theirs. Never work
around it. Say what it found, ask whose file that is, and leave it exactly where it is.

## 2. One line at the end

Under the brief, add exactly one line: the single most useful thing the user could do right now.

> Needs you: one call to the clinic (#7). Everything else is waiting or on me.

If nothing needs them: "Nothing needs you today." That line is the point of the whole brief; do not bury it.

## 3. Then wait

Offer at most one next step, and only when there is a real one:

- something is overdue → "Want me to push the three overdue ones?" (the `push` skill)
- something needs a call or a payment → "Want the script for that call?" (the `handoff` skill)
- the standing weekly task ("Посмотреть, что нового" / "Look at what is new") is due → "Shall I have a look at
  what is new this week?" (the `scout` skill). It is a reminder, not a chase: never write to anyone about it.
- nothing at all → say so and stop

Do not push, do not re-run the brief in the same turn, and do not start writing letters because the brief showed
them. The user asked to see, not to act.

## Never

- Never send an e-mail, a message or a form without the user's explicit yes in this session.
- Never speak on the phone in the user's name, and never place a call.
- Never pay for anything, and never ask for or store a card number, password or code.
- Never write to anyone between 22:00 and 08:00 local time.
- Never more than three pushes on one channel; after that ask the user to step in.
- Never touch the user's files. The only file Chasecall writes is its own database - and, after an explicit yes
  to that folder, its own brief in the phone folder, which it replaces only when the file lying there carries
  our own mark inside it.
- Never put the brief in a folder that syncs to a cloud without that yes, and never quietly replace a file of
  the same name that somebody else put there.
- Never report a task as done in the brief if the tracker has no evidence for it; the script does not, and neither
  do you.

---
name: brief
description: One screen of where every chased task stands - done in the last day, waiting for an answer with the date of the next step, needs the user, and what Chasecall will push today. Use when the user asks "what is waiting on me", "how are my tasks", "brief me", "что сегодня от меня нужно", "как там мои дела".
argument-hint: "[ru|en]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/brief.py *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py *)
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

## 2. One line at the end

Under the brief, add exactly one line: the single most useful thing the user could do right now.

> Needs you: one call to the clinic (#7). Everything else is waiting or on me.

If nothing needs them: "Nothing needs you today." That line is the point of the whole brief; do not bury it.

## 3. Then wait

Offer at most one next step, and only when there is a real one:

- something is overdue → "Want me to push the three overdue ones?" (the `push` skill)
- something needs a call or a payment → "Want the script for that call?" (the `handoff` skill)
- the standing task "Look at what is new" is due → "Shall I have a look at what is new this week?" (the `scout`
  skill). It is a reminder, not a chase: never write to anyone about it.
- nothing at all → say so and stop

Do not push, do not re-run the brief in the same turn, and do not start writing letters because the brief showed
them. The user asked to see, not to act.

## Never

- Never send an e-mail, a message or a form without the user's explicit yes in this session.
- Never speak on the phone in the user's name, and never place a call.
- Never pay for anything, and never ask for or store a card number, password or code.
- Never write to anyone between 22:00 and 08:00 local time.
- Never more than three pushes on one channel; after that ask the user to step in.
- Never touch the user's files. The only file Chasecall reads and writes is its own database.
- Never report a task as done in the brief if the tracker has no evidence for it; the script does not, and neither
  do you.

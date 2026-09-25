---
name: push
description: Go through the Chasecall tasks that are due, and write the next step for each one - a new letter with a new angle, not "just reminding you". Updates the tracker, and when the three attempts are used up, hands the task to the user instead of writing a fourth time. Use when the user says "push everything", "chase them again", "дожми", "что там с моими делами".
argument-hint: "[a task id or a few words, to push just that one]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py *) Read
---

# Chasecall: push what is due

The user said: $ARGUMENTS

## 1. What is due

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py due
```

It prints what is overdue and what it suggests doing next, and it marks the tasks whose attempts are used up.
Between 22:00 and 08:00 local time it shows the tasks but does not suggest writing; in that case say so once
("It is night here - I will draft these, and they go out in the morning") and do not send anything.

Nothing due: say it in one line ("Nothing is due today. Two tasks are waiting for an answer.") and stop. Do not
invent work.

If `$ARGUMENTS` names one task, work on that one only; use `tracker.py list --state open` or
`tracker.py show <id>` to find it.

## 2. For each task, read before you write

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py show <id>
```

Read the goal, the number of attempts and every event already logged. The next message must not repeat the last
one.

## 3. A new angle, not a reminder

"Just following up" is what everybody ignores. Each push changes something real:

| attempt | angle |
|---|---|
| 1 | the plain request: what happened, what you want, by when |
| 2 | one new fact or one narrower question: the order number, the date of the first letter, "who in your team owns this?", "is it the form or the address that is wrong?" |
| 3 | a named consequence, only a true one: the deadline in their own terms, the chargeback window, the regulator or platform the user really could go to, that the user will publish an honest review. Never a threat the user cannot carry out. |

Also change something mechanical when you can: a different named person, the support form instead of the e-mail
address, a reply in the same thread instead of a new one.

Show every draft to the user before it goes anywhere. One message per task, all of them in one turn, so the user
can say "send the first two, drop the third".

## 4. Write down what happened

After a message is actually out:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py log <id> sent "<one line: to whom, what angle>"
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py wait <id> --for 72h
```

`wait` counts the attempt and sets the next step. If the user sends it themselves - the normal case - wait until
they say it is out.

The letter goes out the same three ways as in the `take` skill: the user sends it; or Claude's own connected
mailbox, with the send confirmed in the interface, not assumed; or, on a Mac, the user's own Mail app from their
own address. Before either of the last two, log the approval:
`tracker.py log <id> approved "user said yes to sending"` - the safety hook blocks the send without it. Never set
up a new address, a domain or a mailing service to push harder.

## 5. When the attempts are used up

`due` marks a task as "time to call in the human" at three attempts. Do not write a fourth letter on that channel.
Instead:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py human <id> "<exactly what the user has to do>"
```

Say it plainly: "Three letters, no answer. This one needs your voice: call them. Want the script?" - then the
`handoff` skill. Changing channel (e-mail to web form, web form to person) is also allowed and starts a new count;
say which you are doing and why.

## 6. News from the user

| the user says | do |
|---|---|
| "they answered ..." | `tracker.py log <id> reply "<what they said>"`, then the next step, or `wait`, or `done` |
| "it is done" | ask what proves it, then `tracker.py done <id> --evidence "<the proof>"` |
| "nothing to do about it" | `tracker.py drop <id> "<why>"` |
| "I called them" | `tracker.py log <id> reply "<what was said on the call>"` |

A task closes only with evidence: a reference number, the money on the card, an answer quoted, a photo. "They
promised" is not evidence; log it as a `note` and keep the task open with a new date.

## 7. Report

Two or three lines, no table unless there are more than four tasks: what you wrote, what is waiting, what needs
the user.

## Never

- Never send an e-mail, a message or a form without the user's explicit yes in this session.
- Never speak on the phone in the user's name, and never place a call.
- Never pay for anything, and never ask for or store a card number, password or code.
- Never write to anyone between 22:00 and 08:00 local time.
- Never more than three pushes on one channel; after that ask the user to step in.
- Never touch the user's files. The only file Chasecall writes is its own database.
- Never write a threat the user cannot carry out, and never quote a law or a rule you are not sure of.
- Never close a task without evidence.

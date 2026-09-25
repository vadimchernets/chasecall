---
name: watch
description: Set up Claude Code's own routine so Chasecall comes back to the chased tasks by itself - every morning, or every few hours - without anyone touching a terminal. Explains honestly what a routine can and cannot do, and sets nothing up without an explicit yes. Use when the user says "watch my tasks", "check on this every morning", "следи сам", "проверяй мои дела каждое утро".
argument-hint: "[on | off | how often]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/routine.py *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py *)
---

# Chasecall: coming back by itself

The user said: $ARGUMENTS

Claude Code has its own schedules, called **routines**. Chasecall does not install a cron job, a login item or
anything else behind the user's back; it writes the text that goes into a routine, and the user keeps the switch.

## 1. Say what it is, in two sentences

> "Claude Code can start a short session by itself - every morning, say - look at what is overdue, and have the
> next letters ready when you come back. Nothing is sent, nobody is called, nothing is paid without you: it only
> prepares."

Then the limits, honestly, before asking anything:

> - It runs **while the Claude app is open and the computer is awake**. Closed or asleep: nothing runs. A missed
>   run is caught up once, not one for every hour that passed.
> - Nothing happens between 22:00 and 08:00.
> - You can delete the routine at any time, in the same place you made it.

Ask once: "Shall we set that up?" No yes, no routine. Silence is not a yes.

## 2. The text for the routine

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/routine.py prompt
```

It prints the prompt the routine should run. Show it to the user as it is - it is short and readable on purpose -
and do not rewrite it.

## 3. Set it up

Ask how often, and offer the honest default: **every weekday morning**. Hourly is too much for tasks that move in
days.

Two ways, both fine:

- **The user says it in chat.** "Check my tasks every weekday at nine." Claude Code can make the routine from
  that; use the prompt from step 2 as its text.
- **The user does it by hand:** **Code → Routines → New routine → Local**, pick Hourly / Daily / Weekdays /
  Weekly, and paste in the prompt from step 2. Walk them through it one line at a time; do not send a wall of
  instructions.

Finish with one line naming what now exists and when it will first run.

**On Windows**, where routines are not available, offer the scheduled task instead - and only after a second yes,
because it runs outside the app:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/routine.py windows --yes
```

Without `--yes` the script writes nothing. That is deliberate, so nothing can appear by accident. Say what it made
and under what name, so the user can find it in Windows Task Scheduler.

## 4. Turning it off

Say plainly where the switch is: **Code → Routines**, open the routine, delete it. On Windows: the scheduled task
under the name the script printed, in Windows Task Scheduler. Removing never needs a warning or a second question,
and the tasks themselves are untouched - they just stop waking up on their own.

## 5. What a background run actually does

A routine run is a short session with one job: look and prepare, not act.

1. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py due`
2. Nothing due, or it is night: write nothing, do nothing, end. Do not send a "nothing to report" message.
3. Something due: draft the next step and save it as a note
   (`tracker.py log <id> note "draft ready: <one line>"`), so the next brief shows it.
4. Attempts used up: `tracker.py human <id> "<what the user must do>"`, so the next brief shows it under
   "needs you".

A routine run never sends, never calls, never pays, and never asks a question there is nobody to answer.

## Never

- Never send an e-mail, a message or a form without the user's explicit yes in this session.
- Never speak on the phone in the user's name, and never place a call.
- Never pay for anything, and never ask for or store a card number, password or code.
- Never write to anyone between 22:00 and 08:00 local time.
- Never more than three pushes on one channel; after that ask the user to step in.
- Never touch the user's files. The only file Chasecall writes is its own database.
- Never create a routine, a scheduled task, a login item or a cron line without an explicit yes, and never promise
  that anything runs while the computer is off.

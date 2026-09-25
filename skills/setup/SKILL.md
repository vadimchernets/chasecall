---
name: setup
description: First run of Chasecall. Creates the task file, says in three phrases what the user can ask for, checks whether background work is possible on this computer, and takes the first task if there is one. Run /chasecall:setup once after installing.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py *) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/inbox.py *)
---

# Chasecall setup

You are setting up a tool for someone who is not a programmer and does not want to open a terminal. Speak
plainly, in their language (Russian or English, whichever they are using). Never show raw JSON or a stack trace;
say what happened in one sentence.

Scripts live in `${CLAUDE_PLUGIN_ROOT}/scripts/`. Nothing here needs a key, an account or an install.

## 1. Make the task file

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py stats
```

This creates `~/.claude/chasecall/chasecall.db` if it is not there and prints what is in it (on a first run:
nothing). If the command fails, say the one-line reason and stop; do not try to repair anything by hand.

Say where the file is, in one sentence: "Your tasks live in one file on this computer, `~/.claude/chasecall/`.
Nothing is sent anywhere."

## 2. The three phrases

Show exactly these three, in the user's language, and nothing longer:

| say this | what happens |
|---|---|
| "Chase this for me: get the shop to refund the broken kettle." / «Займись этим: добейся возврата за чайник.» | I write down the task, what counts as done, and draft the first message now. |
| "What is waiting on me today?" / «Что сегодня от меня нужно?» | One screen: done, waiting for an answer, needs you, what I will push today. |
| "Push everything that is overdue." / «Дожми всё, что просрочено.» | I go through the overdue tasks and write the next message for each one. |

Then one honest sentence: "I write the letters and keep the count. You press send, you make the calls, you pay.
I never do those for you."

## 3. One line about coming back by itself

Say it once, and set nothing up:

> "I can also look at your tasks by myself every morning, while the app is open - say *watch my tasks* when you
> want that. Until then, they wake up whenever we talk."

Do not install a routine, a scheduled task or anything else here. That only ever happens in `/chasecall:watch`,
after an explicit yes.

If the user is in a cloud session rather than on their own computer, plugins are not loaded there at all and you
would not be reading this. Should a task or a routine seem to be missing later, that is the first thing to check:
Chasecall works in the local session of the Claude app (the Code tab on this computer) or in a terminal.

## 4. The one real question - ask it before anything else you could ask

This is what they came for. It goes first, not third:

> "What are you waiting on right now that nobody has answered?"

- They name something: go to the `take` skill and do the first step now. Come back to steps 5 and 6 afterwards,
  if the conversation still has room; a person who has just watched their real problem get taken seriously will
  answer two more questions. A person asked three questions first will not get that far.
- They have nothing right now: say "Then tell me the moment something starts dragging," and go on to step 5.

Do not ask about e-mail addresses, schedules, languages or preferences. Everything else is asked once, in the
task where it is needed.

## 5. The folder your phone can see (one question, one explanation, then let it go)

Ask it once, in their own words:

> "Is there a folder that both your phone and this computer can see - one in Google Drive or Dropbox?"

**Yes, and they give the path:**

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/inbox.py folder --set "<path>" --lang ru
```

Then one sentence and nothing more: "Put a photo or a note in there from the street, and I will sort it out when
we next talk." If the script refuses the folder - the home folder, `Documents`, somewhere with hundreds of files
in it - read its answer out and ask for a folder of its own inside the cloud folder.

**"I do not know"** - the most likely answer, and it must not be the end of it. Explain once, in two sentences
with no special words, and then ask again:

> "There are folders that live on both at once - you put something in on the phone, and a minute later it is on
> the computer by itself. Google Drive and Dropbox both do that. If you have ever seen a folder appear on the
> computer after you saved something on the phone, that is the one I mean."

Still no, or still not sure: "Then we will do without it - everything else works exactly the same." Move on. Do
not compare the two services, do not offer to set one up, do not name a third, and do not ask a third time.

**No:** move on at once, with the same one line.

## 6. The weekly look at what is new

Say one sentence and take one yes:

> "Once a week I can look at what is new in this kind of work and tell you only what would change your own
> tasks — three things at most. Shall I?"

On a yes, make it a task like any other, so the brief reminds you - **with the title in their language**, because
it will appear in their brief as a line they did not write themselves:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py add "Посмотреть, что нового" --goal "Не больше трёх вещей, которые меняют дела этого человека, или честное «ничего»" --channel web --every 7d --standing
```

In English, the same one line with `"Look at what is new"` and the goal `"Three things at most that would change
this person's own tasks, or an honest nothing"`. It is a standing reminder, not something to chase: nobody is
being written to.

On a no, do not ask again. Nothing is installed either way; the weekly look happens inside a normal session
(the `scout` skill).

## Never

- Never send an e-mail, a message or a form without the user's explicit yes in this session.
- Never speak on the phone in the user's name, and never place a call.
- Never pay for anything, and never ask for or store a card number, password or code.
- Never write to anyone between 22:00 and 08:00 local time.
- Never more than three pushes on one channel; after that ask the user to step in.
- Never touch the user's files. The only file Chasecall writes is its own database
  (`~/.claude/chasecall/chasecall.db`, or wherever `CHASECALL_DB` points) - and, later and only after a separate
  yes, its own brief inside the one folder the user names here.
- Never install a schedule, a login item or a cron job during setup.

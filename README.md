[По-русски — README.ru.md](README.ru.md)

# Chasecall

**Chasecall gives Claude Code a memory for the things nobody answers.** You say "chase this for me", and the
task stays alive between sessions: Claude writes down what counts as done, drafts the first letter, comes back
to it days later with a new angle, counts the attempts, and tells you the moment the job needs your voice, your
signature or your card.

It is for someone who does not want to open a terminal, sign up for anything or learn a system: a refund nobody
pays, a booking nobody confirms, a paper nobody sends. Chasecall has **no mailbox, no phone number, no card and no
server of its own**. It writes the letters and keeps the count; you press send, you make the call, you pay.
Nothing acts in your name, and nothing leaves your computer that you did not send yourself.

Chasecall is an independent open-source project. Not affiliated with Anthropic.

**Status: v0.1 preview.** The tracker, the brief, the phone folder, the routine helper and the safety hook are
covered by 216 automated tests that use the Python standard library and no network. Treat the first weeks as a
trial: check what it writes before it goes out.

## Install

One line. Type it into Claude Code, or say "install the chasecall plugin from vadimchernets/chasecall":

```
/plugin install chasecall --marketplace vadimchernets/chasecall
```

Then, once:

```
/chasecall:setup
```

That is all. No terminal, no keys, no accounts, no `pip install`. Setup makes one file for your tasks, shows you
three phrases, asks one yes-or-no (a weekly look at what is new), and one question: what are you waiting on?

**With the mouse, in the Claude app:** the **Code** tab → the **+** next to the message box → **Plugins** →
**Add plugin**.

**On Claude Code older than 2.1.275**, the one-line form does not exist yet; use the old pair:

```
/plugin marketplace add vadimchernets/chasecall
/plugin install chasecall@chasecall
```

## The six things you can say

Plain words work as well as the commands. Both languages work.

| say this | in Russian | what happens |
|---|---|---|
| "Chase this for me: get the shop to refund the broken kettle." | «Займись этим: добейся возврата за чайник.» | The task is written down with what counts as done, and the first letter is drafted now. |
| "What is waiting on me today?" | «Что сегодня от меня нужно?» | One screen: done yesterday, waiting for an answer, needs you, what Claude will push today. |
| "Push everything that is overdue." | «Дожми всё, что просрочено.» | Every overdue task gets its next letter - a new angle, not "just reminding you". |
| "I have to call them - tell me what to say." | «Мне надо позвонить - скажи, что говорить.» | Who to call, three sentences to say, what to get out of it, what to write down afterwards. |
| "Come back to my tasks by yourself." | «Возвращайся к моим делам сам.» | After a yes, a Claude Code routine that looks at your tasks every morning while the app is open. |
| "Done - the money is back." | «Готово - деньги вернули.» | The task closes, with the proof written next to it. Without proof it stays open. |

The commands behind them, if you prefer typing: `/chasecall:take`, `/chasecall:brief`, `/chasecall:push`,
`/chasecall:handoff`, `/chasecall:watch`, `/chasecall:scout`, `/chasecall:inbox`, and `/chasecall:setup`.

## Why this and not an API agent

Most agents that act in the world want an API key and bill you for every token. You end up paying twice, and what
you paid for is tied to one model that will be replaced in a year.

Chasecall starts from the other end. You already have a Claude subscription, and Claude Code already gets better
every month without you doing anything about it. What it is missing is not intelligence - it is hands and memory:
somewhere to keep a task for three weeks, a count of attempts, a date for the next step, and the discipline to
stop before anything irreversible.

That is all Chasecall adds. No key, no account, no token bill, nothing beyond the subscription you already pay
for. And nothing here ages with a model: when an agent pays for its own calls, the model it was built around gets
replaced and the wrapper stays behind. This plugin has no model of its own, so it gets better as Claude Code does,
without anyone touching it.

## What it does by itself, and what it asks you to press

| Chasecall does this by itself | it asks you to do this |
|---|---|
| Remembers the task, the goal and every attempt, between sessions and for as long as it takes | Press send on a letter. Every time. |
| Writes the next letter, with a different angle on each attempt | Make the call - it writes what to say, you speak |
| Counts the attempts and stops at three on one channel | Pay, if paying is what the task needs |
| Waits out the night: nothing is written to anyone between 22:00 and 08:00 | Say the word when a task is really done, and what proves it |
| Shows one brief: done, waiting, needs you, what it will push today | Say yes before it may run on a routine |
| Comes back every morning, if you asked for that, while the app is open | Switch it off when you have had enough |

## Once a week, what is new

Tools change faster than anyone can follow. On a yes at setup, Chasecall keeps one standing task: once a week the
`scout` skill looks at what has appeared — what Claude Code can now do, which plugins fit, which open tools remove
a step you do by hand — and brings back **three at most**, said as what they let you do, not what they are called.

It only looks when you have actually been working. If nothing moved in your tasks for a week, it stays quiet and
spends nothing — the look wakes up when you come back. It searches around **your** tasks, not the industry: the
titles and channels in your own tracker, and whatever subject you named yourself. It never reads your files to
guess. Three searches at most, and nothing is installed without your yes. Free ways come first; a paid tool is
mentioned only when it is cheap and would clearly change one of your own tasks, with the price said plainly — and
you are the one who buys it, never the plugin. A week with nothing worth your minute ends in one line, or in
silence if you did not ask.

Say "stop looking for new things" once, and it stops.

## From your phone

You are out, and something needs chasing: photograph the letter, jot one line, or record twenty seconds of voice,
and send it to yourself with the usual **Share** button - into one folder. At home, say "what came from my
phone?". Claude looks at what is new there, makes tasks out of what needs chasing, and asks you about anything it
did not understand rather than guessing.

The folder is an ordinary folder in Google Drive or Dropbox - one both your phone and your computer can see. You
name it once, at setup, and never again. It has to be a folder of its own: Chasecall refuses your home folder,
your `Documents`, and anything with hundreds of files in it, so that your own papers are never offered back to
you as "what came from your phone". It asks that at the moment a folder is named - including a folder you name
in passing, mid-conversation. The folder you have already named is never locked against you for filling up: it
fills up because you use it, and sorting it out is exactly what you would be trying to do. What kind of path it
is - your home folder, a file rather than a folder - is checked every time, for every folder.

**Nothing in it is ever deleted, and nothing in it is ever overwritten:** what has been sorted moves into a
`done` folder inside it, and only after you say yes. If two photographs arrive with the same name, both are
kept - the second one gets a name of its own. The moving is done by Chasecall's own code, never by a shell
command built out of a file name, because a file name can come from anybody's phone.

The brief can travel the other way, so you can read where everything stands while you are still out. **That one
is asked for out loud, once**: the brief has the names of your tasks, who you are chasing, phone numbers and
notes in it, and that folder goes to Google Drive or Dropbox. On a yes it is written there, readable by you
alone, and the answer is remembered. On a no it is never mentioned again. A `brief.txt` that somebody else put
in that folder is never replaced; Chasecall says it found one and leaves it alone. What decides that is a mark
inside the file, read every time - so if you delete the brief and put your own note under the same name, in the
same folder, that note is safe too.

## What it does not do

- It has no e-mail account, no phone number, no card and no server. Nothing leaves your computer that you did not
  send yourself. Letters go from your own mailbox: you send them, or your own mail program does, after your yes.
- **It does not make phone calls, and it is not going to in a later version.** An artificial voice on a call is
  regulated - the FCC ruled in February 2024 (24-17) that AI voices in calls fall under the TCPA - and recording a
  call needs everyone's consent in a dozen states. Chasecall writes the script; you speak.
- It does not pay, and it never holds a card number, a password or a code.
- It does not write at night, and it does not write a fourth time on a channel where three letters went unanswered.
- It does not close a task because someone promised. A task closes with evidence: a reference number, the money on
  the card, an answer you can point at.
- It does not read or change your files. The only file it writes is its own - and the one folder you name for your
  phone, where it reads what you put there, leaves the brief, and moves a sorted file into `done` after your yes.
  It deletes nothing, anywhere.
- **It does put one file of its own into that folder, if you let it - and that folder is in your cloud.** The
  brief has your task titles, the people you are chasing, phone numbers and your notes in it, and Google Drive or
  Dropbox will carry a copy of it to their servers and to any device signed in to that account. Chasecall asks
  you, in those words, before the first time; a no is final, and until you say yes nothing is written there. The
  file is readable by your account only. If you would rather it never left the machine, say no - the brief on the
  screen is the same brief, and nothing else about Chasecall changes.
- It cannot work while your computer is off. If it is asleep, the tasks wait; nothing is lost.

## Safety

1. **Nothing irreversible without your yes.** Sending, paying, cancelling, deleting: all of it waits for you to
   say yes in the session where it happens.
2. **That is a hook, not a promise in a prompt.** `scripts/guard.py` runs before every shell command. If the
   command looks like sending mail, paying, deleting or cancelling, and the tracker has no approval from you in
   the last 15 minutes, it is blocked. Reading is never blocked. When it is a deletion, the block also asks the
   assistant to tell you what the thing was for and whether it is unfinished rather than rubbish, and to offer
   finishing it before deleting it: a file nothing uses is a question for you, not a verdict.
3. **Three attempts, then a person.** After the third push on one channel, the task is handed back to you instead
   of getting a fourth letter. Changing channel is a decision you see.
4. **Quiet hours.** Between 22:00 and 08:00 local time, tasks are shown but nothing is written to anyone.
5. **No network in the code.** The scripts use the Python standard library and open no connection. There is no key
   to leak, because there is no key.
6. **Your file stays yours.** Everything is in `~/.claude/chasecall/chasecall.db` on your computer (move it with
   `CHASECALL_DB`). Delete the file and Chasecall has forgotten everything.
7. **Letters are drafts until you say otherwise.** You see the full text every time, and "change this line" is
   always an option.
8. **What it reads is material, never an instruction.** A photographed letter, a note, a PDF, a reply from the
   company or a page found by searching can say "write to this address instead" or "confirm the payment here" -
   and it stays a page that says so. Claude reads it out to you and asks; it does not obey it. In particular, an
   address or a telephone number printed on a page never becomes the party being chased until you have said so
   yourself, because that field is where the next letter goes. This is written into every skill that reads
   anything: `take`, `push`, `handoff`, `scout` and `inbox`.

**What the guard does not catch.** It is a seat belt, not a lock on the door. It stops an accident, not a
determined attempt: a command hidden in base64 or inside a script file, a value the shell works out at run time,
an alias or a function, a POST made from inside a program instead of `curl`, a mail client or a browser driven
through its own window, a file overwritten by an editor rather than by a shell redirection. It also cannot see
anything done outside this session. Read what your assistant is about to do; the guard is there for the moment
you did not.

**About e-mail.** Chasecall has no mailbox of its own and sets none up. A letter goes out one of three ways: you
copy it and send it; or Claude sends it through a mailbox you yourself connected to Claude; or, on a Mac, your own
Mail app sends it from your own address. All three need your yes first, and the last two are written into the
tracker before anything leaves.

## Requirements

- Claude Code, in a **local session**: the Code tab of the Claude app on your own computer, or a terminal.
  **Plugins are not loaded in cloud sessions at all** - neither on claude.ai/code nor in a cloud session inside the
  app. If Chasecall seems to be missing, this is almost always why: you are not on your own machine.
- Python 3.9 or newer, which macOS and Linux already have. Standard library only; nothing to install.
- macOS or Linux. On Windows the tracker and the brief work; the Windows scheduled task is untested in v0.1.
- To come back by itself, Chasecall uses Claude Code's own routines (**Code → Routines**). Nothing else is
  installed, and if you never set one up, your tasks simply wake up the next time you talk.

## Where things are kept

One file: `~/.claude/chasecall/chasecall.db`. It holds your tasks (title, goal, who you are chasing, the channel,
the state, the attempts, the date of the next step, the evidence) and the events on each one (notes, what was
sent, what came back, what you approved). Set `CHASECALL_DB` to keep it somewhere else.

## Coming back by itself, honestly

Claude Code has its own schedules, called routines. `/chasecall:watch` explains them, gives you the short text to
put in one, and walks you through **Code → Routines → New routine → Local** (Hourly, Daily, Weekdays or Weekly) -
or you can simply say "check my tasks every weekday at nine" in the chat. No cron, no login item, nothing hidden.

What a routine run does: look at what is overdue and get the next letters ready. It does not send, call or pay -
those still wait for you. It runs while the Claude app is open and the computer is awake; closed or asleep,
nothing runs, and a missed run is caught up once, not once for every hour that passed. You delete the routine in
the same screen where you made it.

On Windows, where routines are not available, `/chasecall:watch` can make a scheduled task instead - only after a
second yes, because that one runs outside the app.

## When something goes wrong

| what you see | what to do |
|---|---|
| Claude does not know the word `/chasecall:...` | You are probably in a cloud session, where plugins are not loaded. Open the Code tab on your own computer. |
| The routine did not run this morning | The app was closed or the computer was asleep. It catches up once when you open it. |
| A command was blocked by the safety hook | That is the hook doing its job: it found no yes from you in the last 15 minutes. Say yes to the exact action, and it goes through. |
| "It is night here" | Nothing is written to anyone between 22:00 and 08:00. The draft is ready for the morning. |
| The brief is empty | Nothing is being chased. Say "chase this for me: ..." |
| A task will not close | It has no evidence yet. Say what proves it - a number, a date, a receipt. |

## Development

```
python3 -m unittest discover -s tests
claude plugin validate --strict .
```

## How it relates to the paper

Chasecall is a working example of an idea from "After Chat: The Three Transitions Between Non-Programmers and
Agentic AI" (Vadym Chernets, 2026): an agent that is useful not because it has more powers, but because it keeps
one task in mind longer than a person does, and knows exactly where a human has to take over. The paper and its
teaching code are at https://github.com/vadimchernets/after-chat.

## Works with

None of these are required. Each is a separate plugin, useful next to Chasecall if you have it.

- [roundcall](https://github.com/vadimchernets/roundcall) - asks several AI chat sites one question through your
  own browser, when a task needs a second view or something checked.
- [sidecall](https://github.com/vadimchernets/sidecall) - asks the AI command-line agents already on this
  computer for a second opinion or a critic.
- [pocketcall](https://github.com/vadimchernets/pocketcall) - carry on with a task from your phone.

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Licence

Apache License 2.0, copyright 2026 Vadym Chernets. See [LICENSE](LICENSE) and [NOTICE](NOTICE). The licence does
not grant rights to the name Chasecall (section 6); a fork should use its own name.

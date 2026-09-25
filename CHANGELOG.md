# Changelog

## 0.1.0 — 2026-09-25 (preview)

First public version.

- Eight skills: `setup`, `take`, `push`, `brief`, `watch`, `handoff`, `scout`, `inbox`.
- A task tracker that survives between sessions: goal, channel, counterpart, attempts, the date of the next step,
  evidence, and the note of what the person has to do themselves.
- A brief in English or Russian: done in the last day, waiting for an answer, needs you, what will be pushed today.
- Coming back by itself through Claude Code's own routines; a Windows scheduled task only on a second yes. No cron,
  no login items, no launch agents. `routine.py status` speaks the person's language on every line of it, and a
  `schtasks` command is shown only to somebody who is actually on Windows.
- A `PreToolUse` guard that stops sending, paying, deleting and cancelling unless the person approved it -
  including a file of theirs emptied by a redirection, in every form a shell accepts it: `>`, `>>`, `&>`, a
  file number in front of it (`2>`, `2>>`) and the "overwrite it anyway" form (`>|`).
- The `SessionStart` hook (`tracker.py due --brief`) makes nothing. It used to open the database, so the task
  file appeared the first time a session started - before `/chasecall:setup`, whose first step is the one that
  says it makes it, and before the person had agreed to anything. With no file there is nothing to show, so it
  says nothing and creates nothing; every other command creates it as before.
- Quiet hours 22:00–08:00, three attempts on one channel, a task closes only with evidence.
- The weekly look at what is new runs only in a week where something actually moved, searches around the person's
  own tasks, and never installs or buys anything by itself.
- A bridge from the phone: one folder in Google Drive or Dropbox that both devices see, named once at setup. What
  is shared into it from the street - a photo, a note, a voice memo - becomes tasks at home (`inbox`); what has
  been shown is not shown again; nothing is ever deleted and nothing is ever overwritten, and a sorted file is
  moved into `done/` only after a yes.
  - The move is `inbox.py file-done`, inside the named folder and never a shell command: file names come from a
    phone and from a folder other people can write into, so they are names and nothing else. The skill is
    granted no `mv` and no `mkdir` - and it says plainly what that grant is and is not, because `allowed-tools`
    pre-approves and never restricts; `disallowed-tools` takes `Write` and `Edit` away for the turn the skill is
    called in, and `guard.py` knows `inbox.py` for one of ours, so a file name full of shell characters is not
    read as a second command.
  - A file of the same name already in `done/` is kept: the new one gets a free name next to it, and where it
    lands is checked to be inside the named folder exactly as where it came from is.
  - What kind of path a folder is - not `/`, not the home folder, not a folder holding the home folder, not a
    file - is argued with every time something is listed, marked or moved. **How full it is** is asked where a
    folder is being named: `folder --set`, and a `--folder` pointing somewhere new, which is where
    `list --folder ~/Documents` used to hand back 250 of the person's own papers as "new from the phone". The
    folder already named is never refused for having filled up - that turned an ordinary phone folder into a
    wall the day it passed 200 things, `file-done` included, with no way out through the product.
  - `mark` writes down only what is inside that one folder: a file named by an absolute path from somewhere else
    is refused instead of being recorded as post from the street.
  - `inbox.py` speaks the person's language (`--lang ru|en`), in lines rather than a table, and names no
    commands at them.
- The brief can go back the same way as a file (`brief.py --to`), to be read on the phone - **after the person
  has been asked, once, in plain words**, because that folder syncs to a cloud and the brief carries task
  titles, counterparts, phone numbers and notes. The answer is remembered per folder (`--agreed` / `--declined`),
  the file is written 0600 like the database, and a `brief.txt` that is not ours is never replaced.
  - **Ours means the mark inside the file, read every time** - the beginning and the end of it, because the mark
    is in the last line and a brief of 120 tasks is bigger than one read. A note of our own that we once wrote
    at that path is a hint for the refusal and never a permission: delete the brief, leave your own note under
    the same name, and the note is left alone and named out loud.
  - Exit 3 when the brief is on the screen and the file was not left in the folder; 0 when it was.
- Nothing a skill reads is ever an instruction to it - a photographed letter, a reply, an invoice, a page found
  by searching. It is quoted, never obeyed, and an address printed on a page never becomes the party being
  chased until the person has said so themselves. In every skill that reads anything (`take`, `push`, `handoff`,
  `scout`, `inbox`) and in both READMEs.
- Standard library only: no API key, no account, no paid service, no network in the scripts.
- The shared database waits for the other process (sqlite's busy timeout) instead of failing at once, and what
  it says is the right one of three sentences, in the person's own language: busy (try in a moment), cannot be
  written to (the permissions, which will not pass by themselves), or not a Chasecall task file at all. Never a
  traceback - including for a `CHASECALL_DB` that is a text file or a database with a `tasks` of somebody else's.
- `--json` on `tracker.py`, `brief.py`, `inbox.py` and `routine.py` is part of the interface: the screens are
  written for a person in one of two languages, and anything that needs a number reads the JSON instead.
- `README.ru.md`: the whole thing in Russian, linked from the first line of `README.md`, with the one command
  that has to be typed (`/chasecall:setup`) and the rest of the commands named as in the English one.
- 213 automated tests (`python3 -m unittest discover -s tests`). Every guard in this list has one that goes red
  when the guard is taken out, checked by taking each one out.

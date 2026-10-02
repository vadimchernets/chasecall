# Changelog

## 0.1.5 — 2026-10-02

- Skills run their scripts through the step-0 launcher, on every system: the Bash tool runs
  `sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" chasecall say scripts/<name>.py ...`, the PowerShell tool (Windows without
  Git Bash) the same line starting with the bare path `${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1`. No skill calls `python3`
  any more (on Windows it is often missing or the Microsoft Store stub). The launcher takes a Python only once `-c`
  proves 3.8+, tries `python`, `py -3`, `python3` on Windows, never starts the Store or Apple stub, and with no Python
  says one step-0 line. Scripts are passed relative to the plugin root; text piped in PowerShell reaches the script as
  UTF-8 with no BOM (Windows PowerShell 5.1 wrote one). `allowed-tools` grant both forms, quoted as the command is -
  the old unquoted `Bash(python3 ${CLAUDE_PLUGIN_ROOT}/...)` never matched the quoted commands and always prompted.
  Checked on GitHub Actions on windows-latest, macos-latest and ubuntu-latest, including a real `claude -p` that opens a
  skill and runs its command with no prompt, through Bash and through PowerShell.
- Guard in PowerShell also reads `[IO.File]::Delete`, `[IO.Directory]::Delete`, `WriteAllText`/`WriteAllBytes`/
  `WriteAllLines`/`AppendAllText` onto the person's existing files, `cmd /c del|erase|rd|rmdir`, `Remove-Item -Recurse`
  through `rm`, `ri`, `rmdir`, `erase`, `del`, `rd`, `Invoke-WebRequest`/`iwr` with `-Method Post` to mail, payment
  or cancel addresses, `irm ... | iex`. It recognises the step-0 launcher as running its own scripts.
- A block is now the documented PreToolUse `deny` on stdout (exit 0), not exit 2: Claude Code shows the reason
  alone instead of the whole two-line hook command in front of it.

## 0.1.4 — 2026-10-02

- Hooks on Windows without Git Bash. There Claude Code runs hook commands in PowerShell, where `sh` does not
  exist, so the hooks failed. Each command in `hooks/hooks.json` is now two lines: sh and Git Bash run the first
  (`exec sh hooks/python.sh ...`, which never comes back); PowerShell finds no `exec`, goes on to the second (whose
  hoisted `trap { continue }` keeps it quiet about that) and
  loads `hooks/python.ps1` - the same step 0 guard (a real Python 3.8+ or one line and exit 0), as a script block
  so no execution policy stops it, with UTF-8 both ways. Checked on GitHub Actions on windows-latest (PowerShell 7,
  Windows PowerShell 5.1, Git Bash; with Python and without), macos-latest and ubuntu-latest, by a real
  `claude -p` session and by every hook command run the way Claude Code spawns it.
- `hooks/python.sh` exports `PYTHONUTF8=1`, so on Windows a hook reads non-English file names right.
- The guard now also stands in front of Claude Code's `PowerShell` tool (Windows without Git Bash): matcher
  `Bash|PowerShell`, and PowerShell's own verbs - `Remove-Item`, `del`, `Send-MailMessage`, `Invoke-RestMethod
  -Method Post` - and `$HOME`, `$env:USERPROFILE` as the home folder.
- README: install from Poly A1's catalogue by its raw link (`/plugin marketplace add https://raw.githubusercontent.com/vadimchernets/poly-a1-plugins/main/.claude-plugin/marketplace.json`,
  then `/plugin install chasecall@poly-a1`) - no git needed; the Poly A1 folder is the way without internet,
  and `marketplace remove` is never the way to switch. The old
  `chasecall@chasecall` / `--marketplace vadimchernets/chasecall` lines are gone.

## 0.1.3 — 2026-10-02

- Step 0 guard: every hook now runs through `hooks/python.sh`, which starts the hook only with a
  real Python 3.8+. On a Mac without Command Line Tools it never runs the `/usr/bin/python3` stub (the
  one that pops Apple's install window mid-lesson); on Windows it skips the Microsoft Store stub and
  finds python.org's `python` or `py`. With no Python the session start says so in one line and the
  session goes on; nothing errors. Tests: `tests/test_step0.py`.
- Every release now carries `chasecall-0.1.3.zip` (one top folder `chasecall-0.1.3/`), built by the new
  `scripts/release-zip.sh` and attached by `.github/workflows/release.yml` on each `v*` tag. The Poly A1
  catalogue installs it as an `archive` source with its `sha256`, so installing needs no git: a
  beginner's Linux has none, and on a Mac without Apple's Command Line Tools `git` is the stub that
  opens Apple's install window.

## 0.1.2 — 2026-10-02

- Every per-language word table (brief, inbox, routine, tracker, the guard's yes-phrase stems) moved out of
  the scripts and into `lang/<code>.json`, loaded once at import time from `Path(__file__).resolve().parent.parent
  / "lang"`. The scripts carry no per-language text of their own any more; adding or changing a language is
  an edit to `lang/`, not to a script.
- Spanish, Portuguese and Ukrainian added as full equals to English and Russian: `--lang en|ru|es|pt|uk`
  everywhere a language is chosen, a `lang/<code>.json` table for each, and guard stems for each so a yes said
  in any of the five is recognised.
- A `check_language.py` check (and its own test) now runs over the whole repository: every file git knows
  about is read for Cyrillic outside a language place - a path under `ru/` or `uk/`, a `README.ru.md`-shaped
  name, `lang/ru.json`/`lang/uk.json`, or the self-names "Русский"/"Українська" in a language list.
- Guard stems written `^stem` in `lang/<code>.json` match only at the start of a word, so one language's
  stem cannot open the gate on another language's word (`pagar` inside Portuguese `apagar`, `pag` inside `page`).

## 0.1.1 — 2026-10-02

- Project language is English: comments, skill instructions, docs and default messages translated; Russian kept only as a localization (README.ru.md, per-language word tables, ru test fixtures).

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
  - When what is blocked is a deletion, the refusal also asks for the two things a task already cannot be closed
    without: what the thing was for, and whether it is unfinished rather than rubbish - a thing nothing uses is a
    question for the person, not a verdict, and finishing it is offered before deleting it. Wording only: nothing
    is blocked that was not blocked before, and a yes that opened a deletion still opens it.
  - **Two refusals that were not true, and are gone.** `echo hi > ~/Desktop/note.md` where there is no such file
    yet was refused as "overwriting one of your files": it writes a new one, and "save me a note on the desktop"
    was hitting a wall built on a false statement. The redirection is now read against the disk, so a file that
    is really there is still protected in every form (`>`, `>>`, `2>`, `>|`) and a file that is not there is
    simply written. And `mv ~/Desktop/notes.txt ~/Documents/ 2>/dev/null` was refused as "throwing a file away
    into /dev/null" - that `/dev/null` is the shell hiding an error message, not a destination. Redirections are
    taken off a command's arguments before `mv` and `cp` are judged by where they are really putting the file.
  - **The person's yes is read in the words people use.** Conjugated Russian verb forms for "rewrite" and "wipe"
    matched nothing, because the stems recognized were a different grammatical form; and ordinary words for
    changing a file - edit, fix, save, and their Russian equivalents - were in no family at all, so a phrase like
    "yes, fix my shopping list" left the block
    standing in front of the very thing that had just been asked for. Changing a file is now its own family,
    narrower than deleting: those words open the change and do not open `rm -rf ~/Documents` or `DELETE FROM`.
    A yes that names the file (`report.docx`) counts on the name alone, with no word from any list.
  - **The refusal asks for the name of the file, not the name of the family.** It used to print
    `approved "<what exactly is allowed - say deleting or overwriting files>"` - our own instruction asking for
    the widest yes there is, which opens every deletion on the computer for fifteen minutes. It now prints the
    file it is looking at: `approved "edit report.docx"`.
  - The test project is built outside the system temporary folder. It used to be made by
    `tempfile.TemporaryDirectory()`, which is `/var/folders/...` on a Mac - a path the guard already waves
    through as scratch - so every "inside the project this is ordinary work" test was passing on the wrong rule,
    and the working-folder rule could be deleted from `theirs()` with the whole suite still green. It cannot now.
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
- **The call card, for a hard call in a language the person barely has** (`handoff`). Before the card, the thing
  that helps most and that almost nobody is told: in a clinic, a bank or a government office an interpreter is
  often theirs by right and free, and the first sentence of the call can simply be the request for one. Then one
  screen: whether a participant may record the call where they are — the first line, because it is the first
  thing they ask, with Portugal (article 199), the eleven US states and New South Wales named, the places where
  a participant may record named as well, and "do not record" wherever there is doubt; what they want in one sentence
  somebody else could check; five things to say in the other side's language, written so they can be read aloud;
  five questions they will be asked with the answers already next to them; three rescue phrases, one of them
  asking for an interpreter; and "please send me this in writing", which is the evidence the task closes on.
  - **A live conversation is not translated by us, and no way of doing it is advised** — no recording for us to
    listen to afterwards, no transcript, no second phone left on the table. That is in `## Never`, next to the
    voice and the card number, and not only in the prose. The person's own phone is a different matter: a Samsung
    or a Pixel translates a call on the device, an iPhone 15 Pro or newer does Spanish and Portuguese and nothing
    else — there is no Russian and no Ukrainian in Apple's call translation — and where it works the phone tells
    the other side by itself. Named in one line, never set up by us.
  - Written because the promise had already gone out to people in the coach they are given: rule 18 sends them to
    `/chasecall:handoff` for exactly this card. The tests for it are written from that promise rather than from
    the page, so the page cannot be trimmed to fit them.
- Standard library only: no API key, no account, no paid service, no network in the scripts.
- The shared database waits for the other process (sqlite's busy timeout) instead of failing at once, and what
  it says is the right one of three sentences, in the person's own language: busy (try in a moment), cannot be
  written to (the permissions, which will not pass by themselves), or not a Chasecall task file at all. Never a
  traceback - including for a `CHASECALL_DB` that is a text file or a database with a `tasks` of somebody else's.
- `--json` on `tracker.py`, `brief.py`, `inbox.py` and `routine.py` is part of the interface: the screens are
  written for a person in one of two languages, and anything that needs a number reads the JSON instead.
- `README.ru.md`: the whole thing in Russian, linked from the first line of `README.md`, with the one command
  that has to be typed (`/chasecall:setup`) and the rest of the commands named as in the English one.
- 246 automated tests (`python3 -m unittest discover -s tests`). Every guard in this list has one that goes red
  when the guard is taken out, checked by taking each one out.

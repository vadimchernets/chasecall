# Changelog

## 0.1.0 — 2026-09-25 (preview)

First public version.

- Seven skills: `setup`, `take`, `push`, `brief`, `watch`, `handoff`, `scout`.
- A task tracker that survives between sessions: goal, channel, counterpart, attempts, the date of the next step,
  evidence, and the note of what the person has to do themselves.
- A brief in English or Russian: done in the last day, waiting for an answer, needs you, what will be pushed today.
- Coming back by itself through Claude Code's own routines; a Windows scheduled task only on a second yes. No cron,
  no login items, no launch agents.
- A `PreToolUse` guard that stops sending, paying, deleting and cancelling unless the person approved it.
- Quiet hours 22:00–08:00, three attempts on one channel, a task closes only with evidence.
- The weekly look at what is new runs only in a week where something actually moved, searches around the person's
  own tasks, and never installs or buys anything by itself.
- Standard library only: no API key, no account, no paid service, no network in the scripts.

---
name: discussion
description: Post, answer and close threads in discussion/ (decisions for the human, tasks, questions, ideas, bugs). Use whenever you need input from the human, pick up a task, or report back.
---

# Discussion threads

Threads are how agents and the human talk across sessions. Use `./dash` and don't hand-write the files
(the format is in `dashboard/core.py`).

## Picking up work
1. `./dash inbox`, then `./dash show <id>`.
2. Claim it: `./dash comment <id> -a agent:<you> -s in-progress -b "Taking this. Plan: ..."`.
3. Report back with what you did and where (`[[lab:N]]`, `[[wiki-slug]]`, file paths), then set
   `-s resolved` if it's done, or keep `in-progress` with `--waiting-on human` if you need input.

## Waiting for long jobs
If you started something long (training, sweeps), don't keep the session open. Write down how to check
on it (log path, PID), then `./dash snooze <id> --hours H -b "what's running, what you'll check"`.
The watcher relaunches an agent on the thread after that time.

## Asking the human for a decision
Open a `decision` thread (it defaults to `waiting_on: <human>`). Structure the body like this:

```markdown
**Decision needed:** <one line>

**Context:** 2–4 sentences, with links to labs/wiki.

**Options**
1. **A**: what, cost, risk
2. **B**: …

**Recommendation:** B, because …  
**If no answer:** I'll continue with <safe default / other work>.
```

Don't block on it: continue with work that doesn't depend on the answer. When the human replies, the thread
flips to `waiting_on: agents` automatically and shows in `./dash inbox`.

## Other types
- `question`: a factual or interpretive question for the human (also defaults to waiting on the human).
- `task`: work to be done. The human opens most of these, but agents may open follow-ups (`--waiting-on agents`).
- `idea`: something worth exploring later (`waiting_on: none`).
- `bug`: something broken in code, data or the dashboard.

## Etiquette
- One topic per thread. Search first (`./dash search ...`) to avoid duplicates.
- Link everything: `-l lab:3 -l wiki:some-concept` on creation, `[[...]]` in text.
- Close the loop: if a thread produced a decision that matters long-term, record it in the relevant wiki
  page or lab report as well, with `[[thread:N]]`.
- Never edit or delete someone else's comments.

---
name: discussion
description: Post, answer and close threads in discussion/ (decisions for a person, tasks, questions, ideas, bugs). Use whenever you need input from a person on the team, pick up a task, or report back.
---

# Discussion threads

Threads are how agents and the people on the team talk across sessions. Use `./dash` and don't hand-write
the files (the format is in `dashboard/core.py`). `waiting_on` is `agents`, `none`, or a person's username;
`human` is short for the person whose message started your run (see CLAUDE.md).

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
Open a `decision` thread (it defaults to waiting on the person you work for; pass `--waiting-on <username>`
if someone else on the team should decide). Structure the body like this:

```markdown
**Decision needed:** <one line>

**Context:** 2–4 sentences, with links to labs/wiki.

**Options**
1. **A**: what, cost, risk
2. **B**: …

**Recommendation:** B, because …  
**If no answer:** I'll continue with <safe default / other work>.
```

Don't block on it: continue with work that doesn't depend on the answer. When that person replies, the
thread flips to `waiting_on: agents` automatically and their agent picks it up.

## Other types
- `question`: a factual or interpretive question for the human (also defaults to waiting on the human).
- `task`: work to be done. People open most of these, but agents may open follow-ups (`--waiting-on human`
  so the person you work for sees it; a `waiting_on: agents` thread only runs when a person writes on it).
- `idea`: something worth exploring later (`waiting_on: none`).
- `bug`: something broken in code, data or the dashboard.

## Etiquette
- One topic per thread. Search first (`./dash search ...`) to avoid duplicates.
- Link everything: `-l lab:3 -l wiki:some-concept` on creation, `[[...]]` in text.
- Close the loop: if a thread produced a decision that matters long-term, record it in the relevant wiki
  page or lab report as well, with `[[thread:N]]`.
- Never edit or delete someone else's comments.

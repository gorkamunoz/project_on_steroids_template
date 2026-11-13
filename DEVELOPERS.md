# How it works (for developers)

Users only need the [README](README.md). Agents follow [CLAUDE.md](CLAUDE.md) and `skills/`. This page is
for changing the template itself.

## Pieces

| File | Role |
|---|---|
| `dashboard/core.py` | All file formats (threads, labs, wiki, refs), config, identity, team, `./dash check` |
| `dashboard/server.py` + `templates/` | The web dashboard (FastAPI, 127.0.0.1 only) and a small JSON API |
| `dashboard/cli.py` | `./dash` |
| `dashboard/watcher.py` | `./run_agents.sh`: starts headless `claude -p` runs; prompt in `agent_prompt.md` |
| `dashboard/sync.py` | Git sync, held messages, renumbering, the Changes page |
| `dashboard/merge_thread.py` | Git merge driver for `discussion/*.md` (see `.gitattributes`) |
| `dashboard/notes.py` | LaTeX notes build and versioned releases |
| `dashboard/tests/` | `python -m pytest dashboard/tests -q`; `test_sync.py` uses two clones of a local bare repo |

Files on disk are the only state. Per-clone state lives in git-ignored `.dash/` (team cache, sync status),
`.agents/` (run logs) and `local.yaml`.

## Config

- `project.yaml` (shared): `name`, default `port` / `conda_env`, `agent_models` (first = default; aliases
  like `opus` track the newest model), `template_repo`, `example_team`.
- `local.yaml` (per clone): `me` (GitHub username, written by `setup.sh` from `gh api user`), optional
  `port` / `conda_env`. `DASH_ME` overrides `me`.
- Team = the repo's GitHub collaborators (`gh api repos/{owner}/{repo}/collaborators`), cached in
  `.dash/team.json`, refreshed hourly during sync; plus `me` and `example_team`. Without the cache: people
  seen in threads.

## Who runs what

- A thread's `waiting_on` is `agents`, `none` or a username. `human` (CLI) resolves to `DASH_REQUESTER`,
  which the watcher sets to the person whose message started the run, else to `me`.
- Each person's watcher only takes threads waiting on agents where **they** wrote last, or whose snooze
  expired and `run_by` is them (`core.pending_threads`). Comments by others on a thread someone else's agent
  snoozed don't trigger anyone; that agent reads them when it wakes.
- Per run the watcher: sets `run_by: me`, commits the thread, syncs (the thread id may change), launches
  `claude --model <thread model>`, then commits the thread and syncs again. Runs are sequential.

## Sync (`sync.sync`)

Under a file lock: `fetch` → if behind, renumber my new threads/labs whose numbers were pushed by someone
else first (all my new items of that kind move above every existing number, keeping order; links,
`links:`, `parents:`, `threads:` and the lab report heading are rewritten in lines I added) → `rebase
--autostash origin/<branch>` → `push --follow-tags`, retrying if rejected. A conflict the merge driver can't
solve aborts the rebase and shows a banner. With `pull=False` (an agent is working in the folder) it only
pushes when no pull is needed.

The merge driver keeps comments from both sides in date order; for each front-matter field it takes the
side that changed it, or the side updated last if both did.

Triggers: each dashboard action (background), each watcher run, every `AGENT_SYNC_S` (120 s) in the watcher,
`./dash lab-new` (reserves the number), `./dash notes release` (before numbering, then pushes the tag), the
⟳ button, `./dash sync`. Without an `origin` remote nothing is committed or pushed automatically.

## What gets committed

| Change | Committed by |
|---|---|
| Dashboard action (new thread, comment) | the dashboard, that thread file only |
| Message for my own agent | nobody until my watcher starts on it ("held"; `sync.held_threads`) |
| Agent work | the agent (its own files), then the watcher (the thread) |
| Anything else | the person, via the Changes page (`sync.commit_all`: all files except held ones; refuses > 5 MB) |

## The template repo

Example content is everything named `example` plus `example_team` in `project.yaml`. When `setup.sh`
runs in a repo whose `origin` (as `owner/repo`) isn't `template_repo`, it turns the copy into a new project
once: `name` and `conda_env` become the repo name (before the env is created), `./dash examples --remove`
deletes the examples, and the `template_repo` lines are dropped so it never runs again. In the template repo
itself (or with no remote) nothing is removed. Keep new examples named `*example*` so this keeps working.

Watcher knobs (env): `AGENT_POLL_S`, `AGENT_SYNC_S`, `AGENT_TIMEOUT_H`, `AGENT_BUDGET_USD`,
`AGENT_PERMISSION_MODE`, `AGENT_ALLOW_MCP`, `CLAUDE_BIN`.

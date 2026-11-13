# CLAUDE.md — how to work in this project

## The project

<!-- Replace this section with your project: research question, scope, what counts as done. -->
**Research question:** TODO: one or two sentences.
**Scope:** TODO: what is in and out of scope (theory, experiments, datasets, compute limits).

## How the team works

The project has a team of people (the GitHub collaborators of the repo, by username; `./dash team`) and no lead.
Each person has their own clone, dashboard and agents. **The human** below means the person you are working
for: the one whose message started your run (the watcher tells you who). On the command line `human` stands
for that person, e.g. `--waiting-on human`; to ask someone else, give their username (`--waiting-on bob`).
You are one of several agents working on the project, often in parallel and without
shared memory. Everything you know about the state of the project must come from the files, and everything
the next agent needs must be written back to them.

Each person follows the project through their own dashboard at http://localhost:<port> (`./run_server.sh`;
port in `project.yaml` or `local.yaml`). It only *reads*
the folders below, so anything you write in the right format shows up there automatically.

## Session protocol

1. **Start:** `./dash inbox` to see threads waiting on agents (tasks from the human, answered decisions).
   `./dash show <id>` to read one. Skim `./dash labs` and `wiki/index.md` for context on the topic at hand.
2. **Claim** a task before working on it: `./dash comment <id> -a agent:<you> -s in-progress -b "Taking this: <plan>"`.
3. **Work**, following the matching skill in `skills/` (lab, wiki, refs, discussion, review).
4. **Need a decision?** Don't guess on anything that changes the research direction, costs a lot of compute,
   or is hard to undo. Open a `decision` thread (see `skills/discussion`) and continue with something else.
5. **End:** comment on the threads you touched (what was done, where), set status, run `./dash check`
   and fix what it reports.

Pick an author name `agent:<role>` (e.g. `agent:lab-runner`, `agent:wiki-writer`) and use it consistently;
you can `export DASH_AUTHOR=agent:<role>` instead of passing `-a` each time.

## Autonomous runs

Most sessions are started by the **agent watcher** (`./run_agents.sh`). Each person runs their own, and it
only serves that person: it launches you headless for one thread when that thread is waiting on agents and
its person wrote the latest message, or when a snooze set by their agent has expired (`run_by:` in the thread
says whose machine handles it). Its instructions are in `dashboard/agent_prompt.md`. Consequences:
- Always reply on the thread before you finish. If you don't, the watcher hands the thread back to the human.
- For long jobs, start them in the background and `./dash snooze <id> --hours H`. You'll be relaunched to check on them.
- Commit your own work (only the files you touched). Never push: the watcher syncs with the team (pull, then
  push) after you finish. Thread and lab numbers can change during a sync if someone else pushed the same
  number first; links in what you wrote are updated, and `./dash lab-new` reserves its number right away.
- The model of each run is set per thread by the human (a `model:` field in the thread, chosen from the dropdown;
  the list and the default are `agent_models` in `project.yaml`). Don't change it yourself. If you know of a
  Claude model family that is missing from `agent_models`, open an `idea` thread suggesting to add it (search first,
  so there is only one such thread).

## Folder map

| Folder | What lives there | Rules |
|---|---|---|
| `refs/` | External sources: `refs/<key>/ref.yaml` + files (PDF, …) | **Immutable.** Add, never edit/delete. Key = `firstauthorYEARword`. |
| `wiki/` | One concept per `.md` page, cited, cross-linked. `wiki/index.md` is the map. | Update existing pages rather than duplicating. Cite `refs/` in `sources:`. |
| `labs/` | One experiment per folder `labs/NNN-slug/` (`lab.yaml`, `report.md`, `figures/`, code) | Self-contained. Never edit a finished lab's results; make a child lab instead. |
| `notes/` | LaTeX working notes: all derivations in one document; `versions/vNNN/` = released PDFs | Follow `skills/notes`. Release only when asked. `versions/` is immutable. |
| `src/` | Reusable code promoted out of labs | Only code used by ≥2 labs or clearly general. Tested. No one-off scripts. |
| `skills/` | Agent workflows (`skills/<name>/SKILL.md`) | Improve them when you learn something. See `skills/skill-authoring`. |
| `discussion/` | Threads: questions, decisions, tasks (`NNNN-slug.md`) | Use `./dash`, don't hand-edit others' comments. |
| `dashboard/` | The web UI + API + `dash` CLI + watcher + git sync (`core.py` holds all formats; overview in `DEVELOPERS.md`) | Change only when asked; run its tests after. |

## Formats (summary; details in each skill)

**Cross-links** work in any markdown (wiki, reports, threads): `[[slug]]` or `[[slug|text]]` → wiki page,
`[[lab:3]]`, `[[thread:12]]`, `[[ref:smith2020example]]`, `[[skill:lab]]`, `[[file:src/models/model.py]]`.
Math: `$...$` inline, `$$...$$` display (KaTeX). Broken links show red in the dashboard and fail `./dash check`.

**Thread** (`discussion/0007-slug.md`): YAML front matter (`id, title, type, status, author, waiting_on,
labels, links, created, updated`), body, then comments appended by `./dash comment`.
Types: `decision | task | question | idea | bug`. Status: `open | in-progress | resolved | closed`.
`waiting_on: <username> | agents | none` drives each person's "Waiting on you" list. Be precise with it.
Optional `model:` (set by a person from the dashboard) is the model the agent watcher runs on that thread;
`run_by:` (set by the watcher) is whose agent handles it.

**Lab** (`labs/012-beta-sweep/lab.yaml`): `title, status, parents, created, author, outputs_on, hypothesis,
conclusion, tags, metrics, wiki, threads`. `outputs_on` = whose machine holds its `outputs/` (set by `lab-new`). Status: `planned | running | done | failed | abandoned`.
`parents` = ids of labs this one builds on (their results motivated it or it reuses their code/checkpoints).
This field draws the lineage graph, so fill it carefully. Create with `./dash lab-new`.

**Wiki page**: front matter `title, tags, sources (ref keys), status (draft|stable), updated`, then markdown.

## `./dash` cheat sheet

```bash
./dash inbox                                   # what's waiting on agents
./dash show 7                                  # read a thread
./dash new -t decision --title "..." -a agent:x -l lab:3 -b - <<'EOF'
...markdown body...
EOF
./dash comment 7 -a agent:x -s resolved -b "Done in [[lab:4]]."
./dash lab-new --title "learning-rate sweep" -p 1,3 -a agent:x
./dash wiki-new some-concept --title "Some concept" -a agent:x
./dash snooze 7 --hours 3 -b "training L012 (pid 4242), will check MIG"
./dash pending                                 # what the watcher will launch next
./dash notes build                             # compile the working notes (draft)
./dash notes release -m "..." -c "..." --thread 7   # frozen, tagged PDF version (only when asked)
./dash search keyword
./dash check                                   # run before finishing
python -m pytest dashboard/tests -q            # after changing dashboard/ (in the project's conda env)
```

The same operations are available over HTTP (`GET/POST /api/threads`, `POST /api/threads/{id}/comments`,
`GET /api/labs`, `/api/labs/graph`, `/api/wiki`, `/api/check`) when the server runs.

## Environment, git and big files

- Conda env named in `project.yaml` (`conda_env`, Python 3.11): `conda activate <conda_env>`. If you install a package, add it to
  `environment.yml` in the same change, because `./setup.sh` rebuilds the env from that file on other machines.
- The project is a git repo shared on GitHub; each person has a clone. Commit only when asked or when a thread
  says to (autonomous runs: always, see above). Small, descriptive commits. Never push, never rewrite history.
- **Never commit large artifacts.** Checkpoints, datasets, raw arrays and logs go in `labs/NNN-*/outputs/`
  (git-ignored) or a top-level `data/` (git-ignored). Commit configs, code, small result summaries
  (`results.json`/`.csv` < 1 MB) and figures. `./dash check` flags files > 5 MB that git would pick up.
- Every lab must be reproducible from what *is* committed: config, seed, code (or the `src/` commit hash it used).
- Outputs live only on the machine that made them (`outputs_on`). If you need outputs from someone else's
  machine, don't silently redo the work: say so on the thread and ask (or propose re-running).

## Writing style for anything the human reads

Lead with the conclusion or the question. Be short and concrete, with numbers and links to labs and figures.
State uncertainty plainly. Distinguish *proved*, *observed in experiments*, and *conjectured*.

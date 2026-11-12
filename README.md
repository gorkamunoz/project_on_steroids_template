# Research project template

A folder layout, a local dashboard and conventions for running a research project with AI agents
(Claude Code) and one human lead. Everything lives in plain files (markdown, YAML, LaTeX), and agents and
the human talk through threads, much like GitHub issues.

```
project.yaml      settings: project name, your handle, dashboard port, conda env name   <- edit first
CLAUDE.md         instructions every agent reads (fill in "The project" section)
refs/             immutable archive of external sources (refs/<key>/ref.yaml + files)
wiki/             compiled knowledge, one concept per page; wiki/index.md is the map
labs/             one experiment per folder (lab.yaml, report.md, figures/, code); parent/child lineage
notes/            LaTeX working notes with frozen, git-tagged PDF versions (created by ./dash notes init)
src/              reusable code promoted out of labs
skills/           agent workflows (discussion, lab, wiki, refs, review, notes, skill-authoring)
discussion/       threads: tasks, questions, decisions between the human and agents
dashboard/        local web UI + JSON API + the dash CLI + agent watcher + tests
setup.sh          one-time setup per machine
run_server.sh     dashboard on http://localhost:<port>
run_agents.sh     agent watcher: starts a headless Claude Code agent for each thread waiting on agents
dash              command-line tool used by agents (./dash -h)
```

## Start a new project

1. Copy this folder and rename it.
2. Edit `project.yaml`: `name`, and the default `port` and `conda_env`. Who you are goes in the git-ignored
   `local.yaml` (`me: <your GitHub username>`), which `./setup.sh` writes.
3. Fill in the **The project** section at the top of `CLAUDE.md` (research question, scope).
4. `./setup.sh`: creates the conda env, checks the tools, runs the tests, and runs `git init`.
5. Delete the examples (everything named `example`):
   ```bash
   rm -r labs/00*-example-* wiki/example-* discussion/0001-example-* refs/smith2020example
   ```
   Then remove the example line from `wiki/index.md`.
6. Make your first commit. Optionally add a private remote (`git remote add origin ...`) and push.

## Daily use

```bash
./run_server.sh          # dashboard: http://localhost:<port>
./run_agents.sh          # agents in the foreground (or: ./run_agents.sh install  -> always-on service)
```
Open a thread in the dashboard (Discussion → New thread, type `task`, waiting on `agents`). Within about
30 seconds the watcher starts an agent, which replies on the thread and commits its work (it never pushes).
Pick the agent's model in the same form (and change it later from the reply form); the choices and the
default come from `agent_models` in `project.yaml`. Follow it in the Agents tab. Remote machine: `ssh -N -L 4200:localhost:<port> you@host`, then open
http://localhost:4200.

## Requirements

- Linux, conda (Miniforge/Miniconda), git.
- Claude Code CLI, logged in (`claude -p "say ok"` must work). Needed for the agents.
- LaTeX, for the notes PDFs only:
  `sudo apt install latexmk latexdiff poppler-utils lmodern texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-science texlive-pictures`

The dashboard serves only on 127.0.0.1. Its frontend libraries (KaTeX, Cytoscape) are bundled, so it works offline.

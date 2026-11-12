# Research project template

A folder layout, a local dashboard and conventions for running a research project with AI agents
(Claude Code) and a team of people. Everything lives in plain files (markdown, YAML, LaTeX) in one GitHub
repo. People and agents talk through threads, much like GitHub issues. Each person works in their own clone,
with their own dashboard, agents and Claude account, and changes sync through git automatically.

```
project.yaml      shared settings: project name, default port / conda env, agent models   <- edit first
local.yaml        this clone only (git-ignored): `me` = your GitHub username; port / env overrides
CLAUDE.md         instructions every agent reads (fill in "The project" section)
refs/             immutable archive of external sources (refs/<key>/ref.yaml + files)
wiki/             compiled knowledge, one concept per page; wiki/index.md is the map
labs/             one experiment per folder (lab.yaml, report.md, figures/, code); parent/child lineage
notes/            LaTeX working notes with frozen, git-tagged PDF versions (created by ./dash notes init)
src/              reusable code promoted out of labs
skills/           agent workflows (discussion, lab, wiki, refs, review, notes, skill-authoring)
discussion/       threads: tasks, questions, decisions between people and agents
dashboard/        local web UI + JSON API + the dash CLI + agent watcher + git sync + tests
setup.sh          one-time setup per machine (and per person)
run_server.sh     your dashboard on http://localhost:<port>
run_agents.sh     your agent watcher: starts a headless Claude Code agent for your requests
dash              command-line tool used by agents (./dash -h)
```

## Start a new project

1. On GitHub, open the template repo and click **Use this template** → create a **private** repo.
2. Clone it and edit `project.yaml` (`name`, default `port` and `conda_env`). Fill in **The project** at the top
   of `CLAUDE.md` (research question, scope).
3. `./setup.sh`: creates the conda env (it includes the GitHub CLI `gh`), asks you to `gh auth login` if
   needed, writes `local.yaml` with your GitHub username, registers the thread merge rule, offers to remove the
   template's example content, and runs the tests.
4. Commit and push. Add your teammates as collaborators on GitHub (Settings → Collaborators): **the team is
   whoever has access to the repo** (`./dash team`).

Each teammate then clones the repo and runs `./setup.sh` once.

## Daily use

```bash
./run_server.sh          # your dashboard: http://localhost:<port>
./run_agents.sh          # your agents (or: ./run_agents.sh install  -> always-on service)
```
- **Ask your agents:** Discussion → New thread, waiting on `agents`. Your watcher starts an agent within ~30 s;
  it replies on the thread and commits its work. Pick the agent's model in the same form (and change it later
  from the reply form); the choices and the default are `agent_models` in `project.yaml`. Runs use your Claude
  account. Follow them in the Agents tab.
- **Ask a person:** set "waiting on" to their username. It shows in their "Waiting on you" after the next sync.
- **Your agents serve only you.** A message for agents stays on your machine ("not sent yet") until your own
  agent starts on it, then it is pushed. Others' requests are run by their agents.
- **Sync** happens automatically: after each of your dashboard actions, after each agent run, and every ~2 min
  while the watcher runs. There is also the ⟳ button in the header and `./dash sync`. If two people created
  thread or lab #8 at the same time, the later one is renumbered (with a note); comments made on the same
  thread at the same time are merged in date order.
- **Big files** (checkpoints, data) never go to git; they stay on the machine that made them (`outputs_on:`
  in `lab.yaml`). Use shared storage (e.g. a cluster folder) if others need them.

Remote machine: `ssh -N -L 4200:localhost:<port> you@host`, then open http://localhost:4200.

## The template repo itself

The example content (everything named `example`, plus the demo team `example_team: [bob, carla]` in
`project.yaml`) shows the formats. `./setup.sh` offers to delete it in any repo other than `template_repo`;
`./dash examples --remove` does it by hand.

## Requirements

- Linux, conda (Miniforge/Miniconda), git, a GitHub account with access to the repo.
- Claude Code CLI, logged in (`claude -p "say ok"` must work). Needed for the agents.
- LaTeX, for the notes PDFs only:
  `sudo apt install latexmk latexdiff poppler-utils lmodern texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-science texlive-pictures`

The dashboard serves only on 127.0.0.1. Its frontend libraries (KaTeX, Cytoscape) are bundled, so it works offline.

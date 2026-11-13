# Research project template

Run a research project with AI agents (Claude Code), alone or with a team. Everything is plain files in a
git repo. In a team, each person works in their own copy with their own dashboard and agents, and the copies
stay in sync through GitHub automatically.

## Requirements

- Linux, conda (Miniforge/Miniconda), git. For a team: a GitHub account with access to the repo.
- Claude Code, logged in (`claude -p "say ok"` must work).
- LaTeX, only for the notes PDFs:
  `sudo apt install latexmk latexdiff poppler-utils lmodern texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-science texlive-pictures`

## Start a project (once)

`./setup.sh` first asks whether you work **with a team on GitHub** (yes) or **alone on this computer** (no;
nothing is ever pushed). It then installs everything, names the project and removes the template's examples.

**With a team**
1. On GitHub, open this template and click **Use this template** → create a **private** repo. Clone it.
2. Run `./setup.sh` and answer **yes**.
3. In `CLAUDE.md`, fill in **The project** (research question, scope).
4. Commit and push. Add your teammates on GitHub (Settings → Collaborators) so they can clone it.

To join a team project: clone it, run `./setup.sh`, answer **yes**.

**Alone**
1. Clone this template into a folder named after your project.
2. Run `./setup.sh` and answer **no**.
3. In `CLAUDE.md`, fill in **The project**.

## Daily use

```bash
./run_server.sh     # your dashboard, at the address it prints
./run_agents.sh     # your agents (keep it running; or ./run_agents.sh install to run it always)
```

- **Ask the agents:** Discussion → New thread, *waiting on* `agents`. Your agent replies on the thread.
  Choose the model in the same form. Agents use your Claude account.
- **Ask a teammate:** set *waiting on* to their name. It appears in their *Waiting on you*.
- **Your own changes** (code, papers, data you add by hand): when the header shows **● N to commit**, click it,
  write one line about what you changed, and press **Commit & sync** (just **Commit** when alone).
- **In a team, everything else syncs by itself.** The ⟳ in the header shows the last sync; click it to sync now.

Good to know:
- A message for the agents shows **Not sent yet** until your agent picks it up, so keep `./run_agents.sh` running.
- Big files (checkpoints, datasets) don't go to GitHub: keep them in a lab's `outputs/` folder. They stay on your machine.
- Port already in use? Put `port: 8011` (any free port) in `local.yaml`.
- On a remote machine: `ssh -N -L 4200:localhost:<port> you@host`, then open http://localhost:4200.

## What's in the repo

| Folder | What |
|---|---|
| `discussion/` | threads between people and agents |
| `labs/` | experiments, one per folder |
| `wiki/` | what the project knows, one concept per page |
| `refs/` | papers and other sources |
| `notes/` | LaTeX working notes, with released PDF versions |
| `src/` | shared code |
| `skills/` | how agents do things (they follow these) |

How it works inside: [DEVELOPERS.md](DEVELOPERS.md).

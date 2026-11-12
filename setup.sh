#!/usr/bin/env bash
# One-time setup on a new machine (safe to re-run: it updates instead of recreating).
#   ./setup.sh
# 1. creates/updates the conda env named in project.yaml (conda_env) from environment.yml
# 2. checks the external tools: git, LaTeX (for notes/), Claude Code (for agents)
# 3. runs the dashboard tests and ./dash check
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
SETUP_ONLY=1 source "$DIR/dashboard/env.sh"   # -> ENV_NAME, PORT
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
miss() { printf '  \033[31m✗\033[0m %s\n' "$*"; MISSING=1; }
MISSING=0

echo "== 1. conda environment '$ENV_NAME'"
CONDA=""
for c in conda "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/miniforge3/bin/conda" \
         "$HOME/mambaforge/bin/conda" /opt/conda/bin/conda; do
  command -v "$c" >/dev/null 2>&1 && { CONDA="$(command -v "$c")"; break; }
done
if [ -z "$CONDA" ]; then
  miss "conda not found. Install Miniforge first:"
  echo "      curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
  echo "      bash Miniforge3-Linux-x86_64.sh    # then open a new terminal and re-run ./setup.sh"
  exit 1
fi
ok "conda: $CONDA"
if "$CONDA" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "  env exists, updating from environment.yml ..."
  "$CONDA" env update -n "$ENV_NAME" -f environment.yml || { miss "conda env update failed"; exit 1; }
else
  echo "  creating env from environment.yml (a few minutes) ..."
  "$CONDA" env create -n "$ENV_NAME" -f environment.yml || { miss "conda env create failed"; exit 1; }
fi
unset SETUP_ONLY; source "$DIR/dashboard/env.sh"
ok "python: $PY ($("$PY" --version 2>&1))"

echo "== 2. external tools"
command -v git >/dev/null && ok "git" || miss "git (sudo apt install git)"
for t in latexmk pdflatex latexdiff pdfinfo pdftotext; do
  command -v "$t" >/dev/null && ok "$t" || miss "$t  (notes PDFs need it)"
done
if [ "$MISSING" = 1 ] && ! command -v latexmk >/dev/null; then
  echo "      LaTeX for the working notes: sudo apt install latexmk texlive-latex-extra texlive-science \\"
  echo "                                   texlive-fonts-recommended latexdiff poppler-utils"
fi
CLAUDE="$(command -v claude || echo "$HOME/.local/bin/claude")"
if [ -x "$CLAUDE" ]; then
  ok "claude: $CLAUDE ($("$CLAUDE" --version 2>/dev/null | head -1))"
  echo "      (agents use this machine's Claude login; check it with: claude -p \"say ok\")"
else
  miss "Claude Code CLI (needed only for ./run_agents.sh). Install it, then run 'claude' once to log in."
fi

if [ ! -d .git ]; then
  git init -q -b main && ok "initialised a git repository (make your first commit when ready)"
fi

echo "== 3. self-test"
"$PY" -m pytest dashboard/tests -q -p no:warnings 2>&1 | tail -1
./dash check | tail -1

echo
[ "$MISSING" = 1 ] && echo "Some optional tools are missing (see ✗ above)."
echo "Next: ./run_server.sh   (dashboard on http://localhost:$PORT)"
echo "      ./run_agents.sh   (agents; or './run_agents.sh install' for the always-on service)"

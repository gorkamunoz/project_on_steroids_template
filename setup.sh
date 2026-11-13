#!/usr/bin/env bash
# One-time setup on a new machine (safe to re-run: it updates instead of recreating).
#   ./setup.sh
# 1. creates/updates the conda env named in project.yaml (conda_env) from environment.yml
# 2. checks the external tools: git, LaTeX (for notes/), Claude Code (for agents)
# 3. you and the team: GitHub login (gh), local.yaml (`me`), the git remote, the thread merge rule,
#    and (in a new project made from the template) removing the example content
# 4. runs the dashboard tests and ./dash check
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

echo "== 3. you and the team (GitHub)"
GH="$(dirname "$PY")/gh"; [ -x "$GH" ] || GH="$(command -v gh || true)"
if [ -n "$GH" ] && ! "$GH" auth status >/dev/null 2>&1 && [ -t 0 ]; then
  echo "  Log in to GitHub (choose HTTPS; this also lets git push to the repo):"
  "$GH" auth login && "$GH" auth setup-git
fi
if [ -n "$GH" ] && "$GH" auth status >/dev/null 2>&1; then
  ok "gh: logged in to GitHub"
else
  miss "gh is not logged in to GitHub. Run:  $GH auth login   (then re-run ./setup.sh)"
fi
if grep -q "^me:" local.yaml 2>/dev/null; then
  ok "local.yaml: $(grep '^me:' local.yaml)"
else
  ME=""
  [ -n "$GH" ] && ME="$("$GH" api user --jq .login 2>/dev/null || true)"
  if [ -z "$ME" ] && [ -t 0 ]; then read -rp "  Your GitHub username: " ME; fi
  if [ -n "$ME" ]; then
    { [ -f local.yaml ] || echo "# This clone only (git-ignored). me = your GitHub username; port / conda_env override project.yaml."
      echo "me: $ME"; } >> local.yaml
    ok "local.yaml: me: $ME"
  else
    miss "who are you? Put 'me: <your GitHub username>' in local.yaml"
  fi
fi
ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
if [ -n "$ORIGIN" ]; then
  ok "git remote: $ORIGIN (changes sync with the team automatically)"
else
  miss "no git remote: working locally only. To share: git remote add origin https://github.com/<owner>/<repo>.git"
fi
PYTHONPATH="$DIR" "$PY" -c "from dashboard import sync; sync.ensure_config()" && ok "thread merge rule registered (git config merge.dash-thread)"
TEMPLATE="$(cfg template_repo '')"
if ls -d labs/*-example-* >/dev/null 2>&1 && [ -n "$TEMPLATE" ] && [ -n "$ORIGIN" ] && [[ "$ORIGIN" != *"$TEMPLATE"* ]] && [ -t 0 ]; then
  read -rp "  This looks like a new project made from the template. Remove the example content? [Y/n] " A
  if [[ ! "$A" =~ ^[Nn] ]]; then ./dash examples --remove && ok "example content removed (commit it when ready)"; fi
fi

echo "== 4. self-test"
"$PY" -m pytest dashboard/tests -q -p no:warnings 2>&1 | tail -1
./dash check | tail -1

echo
[ "$MISSING" = 1 ] && echo "Some optional tools are missing (see ✗ above)."
echo "Next: ./run_server.sh   (dashboard on http://localhost:$PORT)"
echo "      ./run_agents.sh   (agents; or './run_agents.sh install' for the always-on service)"

#!/usr/bin/env bash
# One-time setup on a new machine (safe to re-run: it updates instead of recreating).
#   ./setup.sh
# 0. asks once: team (share through a GitHub repo) or local (only you, nothing pushed); kept in local.yaml.
#    In a new project made from the template: names the project and its conda env after the repo (team) or
#    the folder (local), and (in step 3) deletes the template's example content. Happens once.
# 1. creates/updates the conda env named in project.yaml (conda_env) from environment.yml
# 2. checks the external tools: git, LaTeX (for notes/), Claude Code (for agents)
# 3. you and the team: local.yaml (`me` = your GitHub username), the git remote, the thread merge rule,
#    and (in a new project) removing the example content
# 4. runs the dashboard tests and ./dash check
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
SETUP_ONLY=1 source "$DIR/dashboard/env.sh"   # -> ENV_NAME, PORT
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
miss() { printf '  \033[31m✗\033[0m %s\n' "$*"; MISSING=1; }
MISSING=0

# owner/repo of a GitHub URL (https://github.com/o/r.git or git@github.com:o/r.git)
repo_slug() { echo "${1%.git}" | sed -E 's#.*[:/]([^/:]+/[^/]+)$#\1#'; }
[ -d .git ] || { git init -q -b main && ok "initialised a git repository"; }
ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
TEMPLATE="$(cfg template_repo '')"

# Team or local? Asked once; the answer is kept in local.yaml (mode: team | local).
MODE="$(_cfg1 "$DIR/local.yaml" mode)"
if [ -z "$MODE" ]; then
  if [ -t 0 ]; then
    echo "Will you work on this project with others, through a GitHub repo?"
    read -rp "  [Y] yes, with a team on GitHub   [n] no, only me on this computer (nothing is pushed): " A
    [[ "$A" =~ ^[Nn] ]] && MODE=local || MODE=team
  else
    MODE="$([ -n "$ORIGIN" ] && echo team || echo local)"
  fi
  { [ -f local.yaml ] || echo "# This clone only (git-ignored): mode, me = your GitHub username, optional port / conda_env."
    echo "mode: $MODE            # team = share through the GitHub repo; local = only you, nothing pushed"; } >> local.yaml
fi
if [ "$MODE" = team ] && [ -z "$ORIGIN" ] && [ -t 0 ]; then
  read -rp "  GitHub repo of this project (e.g. https://github.com/you/my-project.git): " URL
  if [ -n "$URL" ]; then git remote add origin "$URL" && ORIGIN="$URL"; fi
fi

NEW_PROJECT=0
SLUG="$([ -n "$ORIGIN" ] && repo_slug "$ORIGIN")"
if [ -n "$TEMPLATE" ] && [ "$MODE" = team ] && [ -n "$ORIGIN" ] && [ "$SLUG" != "$TEMPLATE" ]; then
  NEW_PROJECT=1; REPO="$(basename "$SLUG")"            # your own repo, made with "Use this template"
elif [ -n "$TEMPLATE" ] && [ "$MODE" = local ] && [ "$SLUG" = "$TEMPLATE" ]; then
  NEW_PROJECT=1; REPO="$(basename "$DIR")"             # the template cloned to use alone
  git remote rename origin template && ORIGIN="" && ok "remote 'origin' renamed to 'template': nothing will be pushed to it"
fi
if [ "$NEW_PROJECT" = 1 ]; then
  NEW_ENV="$(echo "$REPO" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9_\n-' '_')"
  echo "== 0. new project '$REPO' (made from the template $TEMPLATE, $MODE mode)"
  sed -E -i "s/^(name:[[:space:]]*)[^#]*[^#[:space:]]/\1$REPO/; s/^(conda_env:[[:space:]]*)[^#]*[^#[:space:]]/\1$NEW_ENV/" project.yaml
  ok "project.yaml: name: $REPO, conda_env: $NEW_ENV (edit them if you like)"
  SETUP_ONLY=1 source "$DIR/dashboard/env.sh"   # re-read: ENV_NAME
fi

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

echo "== 3. you and the team"
GH="$(dirname "$PY")/gh"; [ -x "$GH" ] || GH="$(command -v gh || true)"  # optional; used only if already logged in
if grep -q "^me:" local.yaml 2>/dev/null; then
  ok "local.yaml: $(grep '^me:' local.yaml)"
else
  ME=""
  [ -n "$GH" ] && ME="$("$GH" api user --jq .login 2>/dev/null || true)"
  [ -z "$ME" ] && [ "$MODE" = local ] && ME="$(whoami)"
  if [ -z "$ME" ] && [ -t 0 ]; then read -rp "  Your GitHub username: " ME; fi
  if [ -n "$ME" ]; then
    { [ -f local.yaml ] || echo "# This clone only (git-ignored). me = your GitHub username; port / conda_env override project.yaml."
      echo "me: $ME"; } >> local.yaml
    ok "local.yaml: me: $ME"
  else
    miss "who are you? Put 'me: <your GitHub username>' in local.yaml"
  fi
fi
if [ "$MODE" = local ]; then
  ok "local mode: only you, nothing is pushed (to share later: mode: team in local.yaml + a GitHub remote)"
elif [ -n "$ORIGIN" ]; then
  ok "git remote: $ORIGIN (changes sync with the team automatically)"
else
  miss "no git remote (this folder wasn't cloned from GitHub): working locally only. To share it: git remote add origin https://github.com/<owner>/<repo>.git"
fi
PYTHONPATH="$DIR" "$PY" -c "from dashboard import sync; sync.ensure_config()" && ok "thread merge rule registered (git config merge.dash-thread)"
if [ "$NEW_PROJECT" = 1 ]; then
  ./dash examples --remove >/dev/null && sed -i '/template_repo/d' project.yaml \
    && ok "removed the template's example content and demo team (commit$([ "$MODE" = team ] && echo " and push") when ready)"
fi

echo "== 4. self-test"
"$PY" -m pytest dashboard/tests -q -p no:warnings 2>&1 | tail -1
./dash check | tail -1

echo
[ "$MISSING" = 1 ] && echo "Some optional tools are missing (see ✗ above)."
echo "Next: ./run_server.sh   (dashboard on http://localhost:$PORT)"
echo "      ./run_agents.sh   (agents; or './run_agents.sh install' for the always-on service)"

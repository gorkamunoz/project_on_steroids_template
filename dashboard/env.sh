# Sourced by ./run_server.sh, ./run_agents.sh, ./dash, ./setup.sh.
# Reads project.yaml and sets: ENV_NAME (conda env), PORT, and PY (that env's python, unless SETUP_ONLY=1).
# PY lookup order: $PROJECT_PY, the active conda env, common conda install folders, `conda info --base`.
cfg() {  # cfg KEY DEFAULT -> value of "KEY: value" in project.yaml (comments and quotes stripped)
  local v
  v="$(sed -n "s/^$1:[[:space:]]*//p" "$DIR/project.yaml" 2>/dev/null | head -1 | sed 's/[[:space:]]*#.*$//; s/^["'\'']//; s/["'\'']$//; s/[[:space:]]*$//')"
  echo "${v:-$2}"
}
ENV_NAME="${PROJECT_ENV:-$(cfg conda_env research)}"
PORT="${PORT:-$(cfg port 8010)}"
_find_py() {
  [ -n "${PROJECT_PY:-}" ] && { echo "$PROJECT_PY"; return; }
  if [ "${CONDA_DEFAULT_ENV:-}" = "$ENV_NAME" ] && [ -x "${CONDA_PREFIX:-}/bin/python" ]; then
    echo "$CONDA_PREFIX/bin/python"; return
  fi
  local b
  for b in "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/micromamba" \
           "/opt/conda" "/opt/miniconda3" "/opt/anaconda3"; do
    [ -x "$b/envs/$ENV_NAME/bin/python" ] && { echo "$b/envs/$ENV_NAME/bin/python"; return; }
  done
  if command -v conda >/dev/null 2>&1; then  # slow fallback: ask conda where it lives
    b="$(conda info --base 2>/dev/null)"
    [ -n "$b" ] && [ -x "$b/envs/$ENV_NAME/bin/python" ] && echo "$b/envs/$ENV_NAME/bin/python"
  fi
}
if [ -z "${SETUP_ONLY:-}" ]; then
  PY="$(_find_py)"
  if [ -z "$PY" ] || [ ! -x "$PY" ]; then
    echo "error: conda environment '$ENV_NAME' (conda_env in project.yaml) not found on this machine." >&2
    echo "       Run ./setup.sh once (or set PROJECT_PY=/path/to/python)." >&2
    exit 1
  fi
fi

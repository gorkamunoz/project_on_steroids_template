# Sourced by ./run_server.sh, ./run_agents.sh, ./dash, ./setup.sh.
# Reads project.yaml (shared) and local.yaml (this clone, overrides it) and sets: ENV_NAME (conda env),
# PORT, and PY (that env's python, unless SETUP_ONLY=1).
# PY lookup order: $PROJECT_PY, the active conda env, common conda install folders, `conda info --base`.
_cfg1() {  # _cfg1 FILE KEY -> value of "KEY: value" in FILE (comments and quotes stripped)
  sed -n "s/^$2:[[:space:]]*//p" "$1" 2>/dev/null | head -1 | sed 's/[[:space:]]*#.*$//; s/^["'\'']//; s/["'\'']$//; s/[[:space:]]*$//'
}
cfg() {  # cfg KEY DEFAULT -> local.yaml value, else project.yaml value, else DEFAULT
  local v
  v="$(_cfg1 "$DIR/local.yaml" "$1")"
  [ -n "$v" ] || v="$(_cfg1 "$DIR/project.yaml" "$1")"
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

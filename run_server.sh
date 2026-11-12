#!/usr/bin/env bash
# Single launcher for the local research dashboard -> http://localhost:<port in project.yaml>
# Usage: ./run_server.sh                (PORT=8011 to override the port; NO_RELOAD=1 to disable auto-restart)
# Auto-restarts when dashboard/ code changes (agents may edit it).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/dashboard/env.sh"
cd "$DIR"
echo "Dashboard: http://localhost:$PORT"
RELOAD=(--reload --reload-dir "$DIR/dashboard")
[ -n "${NO_RELOAD:-}" ] && RELOAD=()
exec "$PY" -m uvicorn dashboard.server:app --host 127.0.0.1 --port "$PORT" "${RELOAD[@]}" "$@"

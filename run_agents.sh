#!/usr/bin/env bash
# Always-on agent watcher: launches a headless Claude Code agent for threads waiting on agents.
#   ./run_agents.sh              run in the foreground (Ctrl+C to stop)
#   ./run_agents.sh once         handle at most one pending thread, then exit
#   ./run_agents.sh install      install + start as a systemd user service (survives terminals/reboots*)
#   ./run_agents.sh uninstall    stop + remove the service
#   ./run_agents.sh status|logs  service status / follow its log
# Pause without stopping the service: Agents page in the dashboard, or ./dash agents --pause
# Model: chosen per thread in the dashboard (list + default: agent_models in project.yaml)
# Knobs (env): AGENT_BUDGET_USD (per run), AGENT_TIMEOUT_H (6), AGENT_POLL_S (30)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/dashboard/env.sh"
UNIT="$(echo "$ENV_NAME" | tr -c "a-zA-Z0-9_\n-" "-")-agents"
UNIT_FILE="$HOME/.config/systemd/user/$UNIT.service"

case "${1:-run}" in
  run)  cd "$DIR"; PYTHONPATH="$DIR" exec "$PY" -u -m dashboard.watcher ;;
  once) cd "$DIR"; PYTHONPATH="$DIR" exec "$PY" -u -m dashboard.watcher --once ;;
  install)
    mkdir -p "$(dirname "$UNIT_FILE")"
    cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=$ENV_NAME agent watcher ($DIR)

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/run_agents.sh run
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
UNIT
    systemctl --user daemon-reload
    systemctl --user enable --now "$UNIT"
    echo "Installed and started $UNIT. Logs: ./run_agents.sh logs"
    echo "*To keep it running while you are logged out: sudo loginctl enable-linger $USER" ;;
  uninstall)
    systemctl --user disable --now "$UNIT" || true
    rm -f "$UNIT_FILE"; systemctl --user daemon-reload; echo "Removed $UNIT" ;;
  status) systemctl --user status "$UNIT" --no-pager ;;
  logs)   journalctl --user -u "$UNIT" -f ;;
  *) sed -n '2,11p' "$0"; exit 1 ;;
esac

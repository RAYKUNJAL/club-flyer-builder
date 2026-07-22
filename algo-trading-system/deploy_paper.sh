#!/usr/bin/env bash
# Deploy the dashboard + 24/7 paper-trading loop on a plain Ubuntu/Debian VPS via systemd.
# Run AS ROOT on the VPS: sudo bash deploy_paper.sh
#
# Get the source onto the box first:
#   git clone -b claude/trading-bot-page-research-0ruvr4 \
#     https://github.com/RAYKUNJAL/club-flyer-builder.git /opt/club-flyer-builder
#   ln -s /opt/club-flyer-builder/algo-trading-system /opt/algotrader
#
# PAPER ONLY: nothing this script installs can touch real money. Alpaca keys are
# optional (paper keys only); without them the in-memory paper broker is used.

set -euo pipefail

APP_DIR="/opt/algotrader"
APP_USER="algotrader"
PORT="8000"

if [ ! -d "$APP_DIR/src/algotrader" ]; then
  echo "ERROR: $APP_DIR/src/algotrader not found. Clone the repo first (see top of this script)." >&2
  exit 1
fi

echo "==> Installing system dependencies"
apt-get update -qq && apt-get install -y -qq python3-venv python3-pip

id -u "$APP_USER" &>/dev/null || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"

echo "==> Creating venv and installing"
cd "$APP_DIR"
python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -e . fastapi uvicorn yfinance requests

mkdir -p /etc/algotrader
if [ ! -f /etc/algotrader/alpaca.env ]; then
  cat > /etc/algotrader/alpaca.env <<'EOF'
# OPTIONAL: Alpaca PAPER keys (from the paper-trading section of alpaca.markets).
# Leave commented out to use the in-memory paper broker instead. NEVER put live
# keys here -- the app refuses the live endpoint regardless (see GATES.md).
# APCA_API_KEY_ID=
# APCA_API_SECRET_KEY=
EOF
  chmod 600 /etc/algotrader/alpaca.env
fi

echo "==> Selecting the statistically-best strategy (highest OOS win-rate lower bound)"
sudo -u "$APP_USER" ./.venv/bin/python scripts/select_strategy.py || \
  ./.venv/bin/python scripts/select_strategy.py

chown -R "$APP_USER:$APP_USER" "$APP_DIR" /etc/algotrader

echo "==> Writing systemd units (dashboard + paper trader)"
cat > /etc/systemd/system/algotrader-web.service <<EOF
[Unit]
Description=algotrader dashboard
After=network.target
[Service]
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=-/etc/algotrader/alpaca.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn algotrader.webapp.main:app --host 0.0.0.0 --port ${PORT}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/algotrader-paper.service <<EOF
[Unit]
Description=algotrader 24/7 paper trading loop (PAPER ONLY)
After=network.target
[Service]
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=-/etc/algotrader/alpaca.env
ExecStart=${APP_DIR}/.venv/bin/python scripts/run_paper_trading.py
Restart=on-failure
RestartSec=30
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now algotrader-web algotrader-paper

sleep 2
echo "==> Health checks:"
curl -sS "http://127.0.0.1:${PORT}/api/health" && echo " (dashboard up)"
systemctl --no-pager -l status algotrader-paper | head -5

echo
echo "Done. Dashboard: http://<vps-ip>:${PORT}/  (paper validation card fills as trades close)"
echo "Logs:  journalctl -u algotrader-paper -f"
echo "Swap strategy:  sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/python ${APP_DIR}/scripts/select_strategy.py --best-score && systemctl restart algotrader-paper"

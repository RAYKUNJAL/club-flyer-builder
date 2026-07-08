#!/usr/bin/env bash
# =============================================================================
# One-command VPS setup for BuildMyMold.com + MakeMyMold.com
#
# Run as root on a fresh Ubuntu/Debian VPS (tested on Ubuntu 22.04/24.04):
#
#   apt-get update && apt-get install -y git
#   git clone -b claude/meshcast-competitor-analysis-wdpwes \
#       https://github.com/RAYKUNJAL/club-flyer-builder.git /opt/moldsites
#   bash /opt/moldsites/deploy/vps-setup.sh you@your-email.com
#
# What it does:
#   1. Installs Node.js 20, nginx, certbot
#   2. Installs Ollama and pulls the Qwen model for the support chatbot
#   3. Builds both branded sites (sites/buildmymold, sites/makemymold)
#   4. Creates systemd services  buildmymold (:8787)  makemymold (:8788)
#   5. Creates nginx vhosts for both domains and issues free SSL certificates
#
# Requirements: buildmymold.com and makemymold.com A records → this server.
# =============================================================================
set -euo pipefail

EMAIL="${1:-}"
REPO_DIR="/opt/moldsites"
QWEN_MODEL="${QWEN_MODEL:-qwen2.5:7b-instruct}"   # use qwen2.5:3b-instruct on small VPSes (<8 GB RAM)

if [[ $EUID -ne 0 ]]; then echo "Run as root (sudo bash $0 you@email.com)"; exit 1; fi
if [[ -z "$EMAIL" ]]; then echo "Usage: bash $0 your-email@example.com   (email is for the SSL certificates)"; exit 1; fi
if [[ ! -d "$REPO_DIR" ]]; then echo "Repo not found at $REPO_DIR — clone it there first (see header of this script)."; exit 1; fi

echo "==> [1/6] Installing Node.js 20, nginx, certbot…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
if ! command -v node >/dev/null || [[ "$(node -v | cut -c2-3)" -lt 18 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
apt-get install -y nginx certbot python3-certbot-nginx

echo "==> [2/6] Installing Ollama + pulling ${QWEN_MODEL} (this is the chatbot's brain)…"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable --now ollama
TOTAL_RAM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
if [[ "$TOTAL_RAM_GB" -lt 8 && "$QWEN_MODEL" == "qwen2.5:7b-instruct" ]]; then
  echo "    (only ${TOTAL_RAM_GB} GB RAM — switching to qwen2.5:3b-instruct)"
  QWEN_MODEL="qwen2.5:3b-instruct"
fi
ollama pull "$QWEN_MODEL"

echo "==> [3/6] Building both branded sites…"
cd "$REPO_DIR"
node build-brands.js

echo "==> [4/6] Creating systemd services…"
make_service() { # $1=slug $2=port
  cat > "/etc/systemd/system/$1.service" <<EOF
[Unit]
Description=$1 site + AI support bot
After=network.target ollama.service

[Service]
WorkingDirectory=${REPO_DIR}/sites/$1/support-bot
Environment=PORT=$2
Environment=LLM_BASE_URL=http://127.0.0.1:11434/v1
Environment=LLM_MODEL=${QWEN_MODEL}
# --- PayPal: fill these in when ready, then: systemctl restart $1 ---
#Environment=PAYPAL_ENV=live
#Environment=PAYPAL_CLIENT_ID=
#Environment=PAYPAL_CLIENT_SECRET=
#Environment=PAYPAL_PLAN_MAKER_M=
#Environment=PAYPAL_PLAN_MAKER_Y=
#Environment=PAYPAL_PLAN_PRO_M=
#Environment=PAYPAL_PLAN_PRO_Y=
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
}
make_service buildmymold 8787
make_service makemymold 8788
systemctl daemon-reload
systemctl enable --now buildmymold makemymold

echo "==> [5/6] Configuring nginx…"
make_vhost() { # $1=domain $2=port
  cat > "/etc/nginx/sites-available/$1" <<EOF
server {
    listen 80;
    server_name $1 www.$1;
    location / {
        proxy_pass http://127.0.0.1:$2;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 300s;
        client_max_body_size 5m;
    }
}
EOF
  ln -sf "/etc/nginx/sites-available/$1" "/etc/nginx/sites-enabled/$1"
}
make_vhost buildmymold.com 8787
make_vhost makemymold.com 8788
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> [6/6] Issuing SSL certificates…"
certbot --nginx --non-interactive --agree-tos -m "$EMAIL" --redirect \
  -d buildmymold.com -d www.buildmymold.com || echo "!! certbot failed for buildmymold.com — check DNS, then: certbot --nginx -d buildmymold.com -d www.buildmymold.com"
certbot --nginx --non-interactive --agree-tos -m "$EMAIL" --redirect \
  -d makemymold.com -d www.makemymold.com || echo "!! certbot failed for makemymold.com — check DNS, then: certbot --nginx -d makemymold.com -d www.makemymold.com"

echo
echo "============================================================"
echo "  DONE!"
echo "  🧱 https://buildmymold.com   (service: buildmymold, port 8787)"
echo "  🪄 https://makemymold.com    (service: makemymold,  port 8788)"
echo
echo "  Chatbot model: ${QWEN_MODEL} via Ollama"
echo "  Logs:    journalctl -u buildmymold -f"
echo "  Update:  cd ${REPO_DIR} && git pull && node build-brands.js \\"
echo "           && systemctl restart buildmymold makemymold"
echo "  PayPal:  edit /etc/systemd/system/<site>.service (see comments),"
echo "           run 'node sites/<site>/support-bot/setup-paypal.js' once,"
echo "           then: systemctl daemon-reload && systemctl restart <site>"
echo "============================================================"

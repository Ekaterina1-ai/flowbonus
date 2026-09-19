#!/usr/bin/env bash
# FlowBonus — установка на Ubuntu/Debian (Timeweb VPS)
# Запуск на сервере от root:
#   curl -fsSL https://raw.githubusercontent.com/Ekaterina1-ai/flowbonus/main/server/deploy.sh | bash
# или скопируйте файл на сервер и: bash deploy.sh

set -euo pipefail

APP_DIR=/opt/flowbonus
REPO=https://github.com/Ekaterina1-ai/flowbonus.git
DOMAIN_OR_IP="${1:-85.193.90.43}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git nginx

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  rm -rf "$APP_DIR"
  git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR/server"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn

cat >/etc/systemd/system/flowbonus.service <<EOF
[Unit]
Description=FlowBonus Flask app
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR/server
Environment=HOST=127.0.0.1
Environment=PORT=5500
Environment=FLASK_DEBUG=0
ExecStart=$APP_DIR/server/.venv/bin/gunicorn -b 127.0.0.1:5500 -w 2 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/nginx/sites-available/flowbonus <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name $DOMAIN_OR_IP _;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:5500;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sfn /etc/nginx/sites-available/flowbonus /etc/nginx/sites-enabled/flowbonus
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable --now flowbonus
systemctl restart flowbonus
systemctl restart nginx

if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH || true
  ufw allow 80/tcp || true
  ufw --force enable || true
fi

echo ""
echo "OK: http://$DOMAIN_OR_IP/"
systemctl --no-pager --full status flowbonus | head -20

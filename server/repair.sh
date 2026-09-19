#!/usr/bin/env bash
# Быстрый ремонт FlowBonus на VPS (вставить в консоль Timeweb от root)
set -euo pipefail

APP_DIR=/opt/flowbonus
cd "$APP_DIR"
git pull --ff-only || true

cd "$APP_DIR/server"
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt gunicorn

# Надёжный вариант для демо: gunicorn сразу на :80 (без зависаний nginx→upstream)
systemctl stop nginx 2>/dev/null || true
systemctl disable nginx 2>/dev/null || true

cat >/etc/systemd/system/flowbonus.service <<'EOF'
[Unit]
Description=FlowBonus
After=network.target

[Service]
User=root
WorkingDirectory=/opt/flowbonus/server
Environment=FLASK_DEBUG=0
ExecStart=/opt/flowbonus/server/.venv/bin/gunicorn -b 0.0.0.0:80 -w 2 --timeout 60 --access-logfile /var/log/flowbonus-access.log --error-logfile /var/log/flowbonus-error.log app:app
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable flowbonus
systemctl restart flowbonus
sleep 2

echo "=== status ==="
systemctl --no-pager --full status flowbonus | head -25
echo "=== local curl ==="
curl -sS -m 8 -o /tmp/fb.html -w "http_code=%{http_code}\n" http://127.0.0.1/ || true
head -c 200 /tmp/fb.html 2>/dev/null; echo
echo "=== listen ==="
ss -lntp | grep -E ':80|:5500' || true
echo
echo "Откройте: http://85.193.90.43/"

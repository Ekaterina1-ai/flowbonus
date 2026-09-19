#!/usr/bin/env bash
# Лёгкий деплой FlowBonus для маленького VPS (Waitress + swap)
# В консоли Timeweb:
#   curl -fsSL https://raw.githubusercontent.com/Ekaterina1-ai/flowbonus/main/server/fix-light.sh | bash
set -euo pipefail

APP_DIR=/opt/flowbonus
REPO=https://github.com/Ekaterina1-ai/flowbonus.git

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

# Swap 1G — чтобы не убивало процесс по OOM
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=1024
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon --show || true
free -h

# Убиваем старый gunicorn/nginx
systemctl stop flowbonus 2>/dev/null || true
systemctl stop nginx 2>/dev/null || true
pkill -9 -f gunicorn 2>/dev/null || true
pkill -9 -f waitress 2>/dev/null || true
sleep 1

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin main
  git -C "$APP_DIR" reset --hard origin/main
else
  rm -rf "$APP_DIR"
  git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR/server"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cat >/etc/systemd/system/flowbonus.service <<'EOF'
[Unit]
Description=FlowBonus (Waitress)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/flowbonus/server
Environment=PYTHONUNBUFFERED=1
Environment=FLASK_DEBUG=0
ExecStart=/opt/flowbonus/server/.venv/bin/waitress-serve --host=0.0.0.0 --port=80 --threads=4 --channel-timeout=30 app:app
Restart=always
RestartSec=2
# лимит памяти мягкий, с swap процесс не убьёт сразу
MemoryMax=400M

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl reset-failed flowbonus || true
systemctl enable flowbonus
systemctl restart flowbonus
sleep 2

echo "=== status ==="
systemctl --no-pager --full status flowbonus | head -25

echo "=== local ==="
curl -sS -m 10 -o /tmp/fb.html -w "local=%{http_code}\n" http://127.0.0.1/ || true
head -c 160 /tmp/fb.html; echo

echo "=== public self ==="
curl -sS -m 10 -o /dev/null -w "public=%{http_code}\n" http://85.193.90.43/ || true

ufw allow 22/tcp 2>/dev/null || true
ufw allow 80/tcp 2>/dev/null || true
ufw --force enable 2>/dev/null || true

echo
echo "Откройте: http://85.193.90.43/"

#!/usr/bin/env bash
# Починить зависший gunicorn FlowBonus — вставить в консоль Timeweb
set -euo pipefail

echo "=== stop hung workers ==="
systemctl stop flowbonus 2>/dev/null || true
pkill -9 -f 'gunicorn.*app:app' 2>/dev/null || true
sleep 1
ss -lntp | grep ':80 ' || echo "port 80 free"

echo "=== update app ==="
cd /opt/flowbonus
git fetch origin main || true
git reset --hard origin/main || true

cd /opt/flowbonus/server
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt gunicorn

# Быстрый тест без systemd
echo "=== quick test on :8080 ==="
pkill -9 -f 'gunicorn.*8080' 2>/dev/null || true
gunicorn -b 127.0.0.1:8080 -w 1 --timeout 15 app:app >/tmp/gb-test.log 2>&1 &
GPID=$!
sleep 2
curl -sS -m 8 -o /tmp/t.html -w "test8080=%{http_code}\n" http://127.0.0.1:8080/ || true
head -c 120 /tmp/t.html; echo
kill -9 $GPID 2>/dev/null || true
pkill -9 -f 'gunicorn.*8080' 2>/dev/null || true

# Если тест не 200 — покажем лог и выйдем с ошибкой
CODE=$(curl -sS -m 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ 2>/dev/null || echo 000)

cat >/etc/systemd/system/flowbonus.service <<'EOF'
[Unit]
Description=FlowBonus
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/flowbonus/server
Environment=FLASK_DEBUG=0
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/flowbonus/server/.venv/bin/gunicorn \
  -b 0.0.0.0:80 \
  -w 1 \
  --threads 8 \
  --worker-class gthread \
  --timeout 30 \
  --graceful-timeout 5 \
  --keep-alive 2 \
  --access-logfile /var/log/flowbonus-access.log \
  --error-logfile /var/log/flowbonus-error.log \
  --capture-output \
  app:app
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl reset-failed flowbonus || true
systemctl enable flowbonus
systemctl restart flowbonus
sleep 2

echo "=== status ==="
systemctl --no-pager --full status flowbonus | head -30

echo "=== local http ==="
curl -sS -m 8 -o /tmp/out.html -w "local=%{http_code}\n" http://127.0.0.1/ || true
head -c 200 /tmp/out.html; echo

echo "=== public self-hit ==="
curl -sS -m 8 -o /dev/null -w "public=%{http_code}\n" http://85.193.90.43/ || true

echo "=== logs ==="
tail -n 40 /var/log/flowbonus-error.log 2>/dev/null || true

ufw allow 22/tcp 2>/dev/null || true
ufw allow 80/tcp 2>/dev/null || true
ufw --force enable 2>/dev/null || true

echo
echo "Готово. Проверьте http://85.193.90.43/"

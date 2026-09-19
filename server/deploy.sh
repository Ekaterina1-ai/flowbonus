#!/usr/bin/env bash
# FlowBonus — первичная установка на облачный сервер Timeweb (Ubuntu 22.04/24.04).
#
# Запуск на сервере от root:
#   curl -fsSL https://raw.githubusercontent.com/Ekaterina1-ai/flowbonus/main/server/deploy.sh -o deploy.sh
#   bash deploy.sh
#
# Скрипт идемпотентный: повторный запуск ничего не ломает и НЕ трогает базу данных.
# Для обычного обновления кода используйте update.sh.

set -euo pipefail

APP_DIR=/opt/flowbonus
DATA_DIR=/var/lib/flowbonus
ENV_FILE=/etc/flowbonus.env
REPO="${FLOWBONUS_REPO:-https://github.com/Ekaterina1-ai/flowbonus.git}"
BRANCH="${FLOWBONUS_BRANCH:-main}"
APP_USER=flowbonus

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите скрипт от root." >&2
  exit 1
fi

echo "=== 1/8 пакеты ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git nginx curl sqlite3

echo "=== 2/8 swap (защита от OOM на тарифах с 1 ГБ RAM) ==="
if ! swapon --show | grep -q '/swapfile'; then
  if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=1024
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi
free -h

echo "=== 3/8 пользователь и каталоги данных ==="
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$DATA_DIR/uploads" "$DATA_DIR/backups"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR"

echo "=== 4/8 код приложения ==="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" remote set-url origin "$REPO"
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" "$REPO" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "=== 5/8 переменные окружения ==="
if [ ! -f "$ENV_FILE" ]; then
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat >"$ENV_FILE" <<EOF
SECRET_KEY=$SECRET
FLOWBONUS_DB_PATH=$DATA_DIR/flowbonus.db
FLOWBONUS_UPLOAD_DIR=$DATA_DIR/uploads
MAX_UPLOAD_MB=20
TRUST_PROXY=1
SESSION_COOKIE_SECURE=0
EOF
  echo "создан $ENV_FILE"
else
  echo "$ENV_FILE уже существует — оставляем как есть (SECRET_KEY не меняем)"
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

echo "=== 6/8 виртуальное окружение ==="
cd "$APP_DIR/server"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt
chown -R "$APP_USER:$APP_USER" "$APP_DIR/server/.venv"

echo "=== 7/8 инициализация базы ==="
# init_db() создаёт таблицы и индексы, существующие данные не затрагивает.
sudo -u "$APP_USER" FLOWBONUS_DB_PATH="$DATA_DIR/flowbonus.db" \
  .venv/bin/python -c "import db; db.init_db(); print('DB OK:', db.DB_PATH)"

echo "=== 8/8 systemd + nginx ==="
install -m 644 "$APP_DIR/server/flowbonus.service" /etc/systemd/system/flowbonus.service
install -m 644 "$APP_DIR/server/nginx-flowbonus.conf" /etc/nginx/sites-available/flowbonus
ln -sfn /etc/nginx/sites-available/flowbonus /etc/nginx/sites-enabled/flowbonus
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/html

nginx -t
systemctl daemon-reload
systemctl reset-failed flowbonus 2>/dev/null || true
systemctl enable flowbonus
systemctl restart flowbonus
systemctl enable nginx
systemctl restart nginx

# Ежедневный бэкап базы в 04:00.
install -m 755 "$APP_DIR/server/backup.sh" /usr/local/bin/flowbonus-backup
cat >/etc/cron.d/flowbonus-backup <<'EOF'
0 4 * * * root /usr/local/bin/flowbonus-backup >/var/log/flowbonus-backup.log 2>&1
EOF

if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH || true
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  ufw --force enable || true
fi

sleep 2
echo
echo "=== status ==="
systemctl --no-pager --full status flowbonus | head -15
echo
echo "=== проверка ==="
curl -sS -m 10 -o /dev/null -w "app  (127.0.0.1:5500) = %{http_code}\n" http://127.0.0.1:5500/api/health || true
curl -sS -m 10 -o /dev/null -w "nginx(80)             = %{http_code}\n" http://127.0.0.1/ || true
echo
IP="$(curl -sS -m 5 https://api.ipify.org || echo '<IP сервера>')"
echo "Готово. Откройте: http://$IP/"
echo
echo "Дальше:"
echo "  • тестовые данные:  bash $APP_DIR/server/seed.sh"
echo "  • обновить код:     bash $APP_DIR/server/update.sh"
echo "  • логи:             journalctl -u flowbonus -f"

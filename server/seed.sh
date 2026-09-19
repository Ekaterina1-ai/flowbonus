#!/usr/bin/env bash
# FlowBonus — залить тестовые данные в базу на сервере.
# Запуск от root:  bash /opt/flowbonus/server/seed.sh
# Пароль спросим интерактивно, чтобы он не попал ни в репозиторий, ни в историю команд.

set -euo pipefail

APP_DIR=/opt/flowbonus
DATA_DIR=/var/lib/flowbonus
APP_USER=flowbonus

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите скрипт от root." >&2
  exit 1
fi

read -rsp "Пароль для тестового партнёра «Норма Тела» (+7 917 840-90-90): " PARTNER_PW
echo
read -rsp "Пароль для тестового клиента (+7 900 111-22-33, Enter — пропустить): " CLIENT_PW
echo

cd "$APP_DIR/server"
sudo -u "$APP_USER" env \
  FLOWBONUS_DB_PATH="$DATA_DIR/flowbonus.db" \
  FLOWBONUS_UPLOAD_DIR="$DATA_DIR/uploads" \
  DEMO_PARTNER_PASSWORD="$PARTNER_PW" \
  DEMO_CLIENT_PASSWORD="$CLIENT_PW" \
  .venv/bin/python seed_demo.py

echo "Готово."

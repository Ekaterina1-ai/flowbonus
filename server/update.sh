#!/usr/bin/env bash
# FlowBonus — обновление кода на сервере без потери данных.
# Запуск от root:  bash /opt/flowbonus/server/update.sh

set -euo pipefail

APP_DIR=/opt/flowbonus
DATA_DIR=/var/lib/flowbonus
BRANCH="${FLOWBONUS_BRANCH:-main}"
APP_USER=flowbonus

# Тело обёрнуто в функцию: git reset перезаписывает этот же файл, а bash читает
# скрипт по частям — без функции обновление сломалось бы на середине.
main() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Запустите скрипт от root." >&2
    exit 1
  fi

  # База и фотографии лежат в $DATA_DIR, поэтому git reset их не затрагивает.
  echo "=== бэкап базы перед обновлением ==="
  bash "$APP_DIR/server/backup.sh" || echo "предупреждение: бэкап не сделан"

  echo "=== git ==="
  # см. комментарий в deploy.sh: каталог принадлежит flowbonus, git запускает root
  git config --global --get-all safe.directory 2>/dev/null | grep -qx "$APP_DIR" ||
    git config --global --add safe.directory "$APP_DIR"
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"

  echo "=== зависимости ==="
  cd "$APP_DIR/server"
  .venv/bin/pip install --upgrade pip wheel >/dev/null
  .venv/bin/pip install -r requirements.txt
  chown -R "$APP_USER:$APP_USER" "$APP_DIR/server/.venv"

  echo "=== миграции схемы ==="
  sudo -u "$APP_USER" env FLOWBONUS_DB_PATH="$DATA_DIR/flowbonus.db" \
    .venv/bin/python -c "import db; db.init_db(); print('DB OK:', db.DB_PATH)"

  echo "=== перезапуск ==="
  install -m 644 "$APP_DIR/server/flowbonus.service" /etc/systemd/system/flowbonus.service
  install -m 755 "$APP_DIR/server/backup.sh" /usr/local/bin/flowbonus-backup
  # nginx-конфиг не перезаписываем: в нём могут быть домены и сертификаты,
  # добавленные certbot. Обновляйте вручную при необходимости.
  systemctl daemon-reload
  systemctl restart flowbonus
  nginx -t && systemctl reload nginx

  sleep 2
  systemctl --no-pager --full status flowbonus | head -12
  echo
  curl -sS -m 10 -o /dev/null -w "app   = %{http_code}\n" http://127.0.0.1:5500/api/health || true
  curl -sS -m 10 -o /dev/null -w "nginx = %{http_code}\n" http://127.0.0.1/ || true
  echo "Готово."
}

main "$@"

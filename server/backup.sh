#!/usr/bin/env bash
# FlowBonus — резервная копия базы. Ставится в /usr/local/bin/flowbonus-backup
# и запускается по cron ежедневно (см. deploy.sh).
#
# Используется sqlite3 .backup — это единственный корректный способ копировать
# базу в режиме WAL, пока приложение работает. Обычный cp может дать битый файл.

set -euo pipefail

DATA_DIR=/var/lib/flowbonus
DB_PATH="${FLOWBONUS_DB_PATH:-$DATA_DIR/flowbonus.db}"
BACKUP_DIR="${FLOWBONUS_BACKUP_DIR:-$DATA_DIR/backups}"
KEEP_DAYS="${FLOWBONUS_BACKUP_KEEP_DAYS:-14}"

if [ ! -f "$DB_PATH" ]; then
  echo "База $DB_PATH не найдена — нечего копировать."
  exit 0
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/flowbonus-$STAMP.db"

sqlite3 "$DB_PATH" ".backup '$DEST'"
gzip -f "$DEST"
chmod 600 "$DEST.gz"

# Чистим копии старше KEEP_DAYS дней.
find "$BACKUP_DIR" -name 'flowbonus-*.db.gz' -mtime "+$KEEP_DAYS" -delete

echo "Бэкап готов: $DEST.gz"
ls -lh "$BACKUP_DIR" | tail -5

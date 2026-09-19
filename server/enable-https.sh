#!/usr/bin/env bash
# FlowBonus — подключение домена и бесплатного HTTPS (Let's Encrypt).
# Запускать ПОСЛЕ покупки домена и настройки A-записи на IP сервера.
#
#   bash /opt/flowbonus/server/enable-https.sh flowbonus.ru www.flowbonus.ru
#
# Для .рф домена укажите punycode-имя (xn--...), certbot не понимает кириллицу:
#   bash enable-https.sh xn--80aafgcqfdbaebrl0b.xn--p1ai
# Punycode можно получить так:
#   python3 -c "print('потокбонусов.рф'.encode('idna').decode())"

set -euo pipefail

NGINX_CONF=/etc/nginx/sites-available/flowbonus
ENV_FILE=/etc/flowbonus.env

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите скрипт от root." >&2
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo "Использование: bash enable-https.sh <домен> [ещё домены...]" >&2
  exit 1
fi

DOMAINS=("$@")
EMAIL="${LETSENCRYPT_EMAIL:-}"

echo "=== проверка DNS ==="
SERVER_IP="$(curl -sS -m 5 https://api.ipify.org)"
echo "IP сервера: $SERVER_IP"
for d in "${DOMAINS[@]}"; do
  RESOLVED="$(getent ahostsv4 "$d" | awk '{print $1; exit}' || true)"
  echo "  $d -> ${RESOLVED:-не резолвится}"
  if [ "$RESOLVED" != "$SERVER_IP" ]; then
    echo "  ВНИМАНИЕ: A-запись не указывает на этот сервер. Дождитесь обновления DNS." >&2
  fi
done

echo "=== прописываем домены в nginx ==="
SERVER_NAMES="${DOMAINS[*]}"
sed -i "s/^\( *\)server_name .*/\1server_name $SERVER_NAMES;/" "$NGINX_CONF"
# default_server оставляем, чтобы сайт продолжал отвечать и по IP.
nginx -t
systemctl reload nginx

echo "=== certbot ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y certbot python3-certbot-nginx

CERTBOT_ARGS=(--nginx --redirect --agree-tos --non-interactive)
if [ -n "$EMAIL" ]; then
  CERTBOT_ARGS+=(-m "$EMAIL")
else
  CERTBOT_ARGS+=(--register-unsafely-without-email)
fi
for d in "${DOMAINS[@]}"; do
  CERTBOT_ARGS+=(-d "$d")
done

certbot "${CERTBOT_ARGS[@]}"

echo "=== включаем Secure-флаг для cookie ==="
if grep -q '^SESSION_COOKIE_SECURE=' "$ENV_FILE"; then
  sed -i 's/^SESSION_COOKIE_SECURE=.*/SESSION_COOKIE_SECURE=1/' "$ENV_FILE"
else
  echo 'SESSION_COOKIE_SECURE=1' >>"$ENV_FILE"
fi
systemctl restart flowbonus

echo "=== автообновление сертификата ==="
systemctl list-timers --no-pager | grep -i certbot || true
certbot renew --dry-run

sleep 2
curl -sS -m 15 -o /dev/null -w "https = %{http_code}\n" "https://${DOMAINS[0]}/" || true
echo
echo "Готово: https://${DOMAINS[0]}/"

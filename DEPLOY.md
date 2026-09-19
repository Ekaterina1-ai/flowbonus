# Деплой FlowBonus на Timeweb Cloud

Схема: **облачный сервер (VPS) → nginx на 80 порту → waitress на 127.0.0.1:5500 → SQLite**.

Главное правило: **код живёт в `/opt/flowbonus`, данные — в `/var/lib/flowbonus`.**
Обновление кода перезаписывает первый каталог и никогда не трогает второй,
поэтому база и фотографии партнёров не теряются при деплое.

| Что | Где |
|---|---|
| Код | `/opt/flowbonus` (git-клон) |
| База SQLite | `/var/lib/flowbonus/flowbonus.db` |
| Фото партнёров | `/var/lib/flowbonus/uploads` |
| Бэкапы базы | `/var/lib/flowbonus/backups` (14 дней) |
| Переменные окружения | `/etc/flowbonus.env` |
| Сервис | `systemctl status flowbonus` |
| Логи приложения | `journalctl -u flowbonus -f` |
| Логи nginx | `/var/log/nginx/flowbonus-*.log` |

---

## 1. Создать сервер

В панели [timeweb.cloud](https://timeweb.cloud/) → **Облачные серверы** → **Создать**:

- ОС: **Ubuntu 24.04**
- Тариф: минимальный (1 CPU / 1 ГБ RAM) достаточно — скрипт сам добавит 1 ГБ swap
- Регион: любой российский
- Доступ: SSH-ключ (надёжнее пароля)

Запишите публичный IP-адрес сервера.

## 2. Выложить код на GitHub

Перед деплоем отправьте изменения в репозиторий, из которого сервер будет забирать код:

```bash
git add -A
git commit -m "Prepare deploy: persistent DB path, env config, deploy scripts"
git push origin main
```

> Репозиторий `Ekaterina1-ai/flowbonus` публичный. Убедитесь, что в нём больше
> нет базы, личных заметок и паролей — см. раздел «Что было убрано из git».

## 3. Установка

Подключитесь по SSH (или откройте веб-консоль в панели Timeweb) и выполните от root:

```bash
curl -fsSL https://raw.githubusercontent.com/Ekaterina1-ai/flowbonus/main/server/deploy.sh -o deploy.sh
bash deploy.sh
```

Скрипт сам: поставит пакеты, создаст swap, отдельного системного пользователя
`flowbonus`, каталоги данных, `/etc/flowbonus.env` со **случайным SECRET_KEY**,
виртуальное окружение, таблицы и индексы в базе, юнит systemd, конфиг nginx,
ежедневный бэкап в 04:00 и правила фаервола.

В конце он сам проверит, что приложение и nginx отвечают `200`, и напечатает адрес.

Скрипт идемпотентный — можно запускать повторно, база и `SECRET_KEY` не пострадают.

## 4. Тестовые данные

```bash
bash /opt/flowbonus/server/seed.sh
```

Скрипт интерактивно спросит пароли и создаст:

- партнёра «Норма Тела», Волгоград — вход по `+7 917 840-90-90`
- (необязательно) тестового клиента — вход по `+7 900 111-22-33`

Пароли нигде не сохраняются: ни в репозитории, ни в истории команд.

### Либо перенести свою локальную базу

Если хотите поднять на сервере ровно те данные, что были на компьютере:

```powershell
# на своём компьютере, из каталога проекта
scp server\flowbonus.db root@IP_СЕРВЕРА:/tmp/flowbonus.db
scp -r assets\partners\p2 root@IP_СЕРВЕРА:/tmp/p2
```

```bash
# на сервере
systemctl stop flowbonus
mv /tmp/flowbonus.db /var/lib/flowbonus/flowbonus.db
mv /tmp/p2 /var/lib/flowbonus/uploads/p2
chown -R flowbonus:flowbonus /var/lib/flowbonus
systemctl start flowbonus
```

## 5. Проверить

Откройте `http://IP_СЕРВЕРА/` и пройдите по сценариям:

- главная, «Клиентам», «Партнёрам» открываются, мобильная вёрстка на телефоне
- регистрация клиента → кабинет → выбор города
- промокод `FLOWBONUS` (+1 монета) и `START2` (+2 монеты)
- покупка монет тестовой картой (демо-оплата, деньги не списываются)
- кабинет клиента → QR на списание
- вход партнёра → сканирование QR телефоном → списание монет
- загрузка фото в кабинете партнёра → фото видно в списке партнёров

Полезные команды:

```bash
systemctl status flowbonus         # состояние сервиса
journalctl -u flowbonus -n 100     # последние логи
curl -s localhost:5500/api/health  # приложение живо?
sqlite3 /var/lib/flowbonus/flowbonus.db "select id,business_name,city from partners;"
```

## 6. Обновление кода

```bash
bash /opt/flowbonus/server/update.sh
```

Сделает бэкап базы, подтянет `main`, обновит зависимости, применит миграции схемы
и перезапустит сервис. Конфиг nginx не перезаписывает, чтобы не потерять домены
и сертификаты.

## 7. Домены и HTTPS (когда купите домены)

1. В панели Timeweb → **Домены** купите `flowbonus.ru` и `потокбонусов.рф`.
2. В DNS каждого домена создайте **A-запись** `@` → IP сервера и `www` → IP сервера.
3. Подождите обновления DNS (обычно 15 минут – 2 часа), затем на сервере:

```bash
# латинский домен
bash /opt/flowbonus/server/enable-https.sh flowbonus.ru www.flowbonus.ru
```

Для `.рф` нужен punycode — certbot не понимает кириллицу:

```bash
python3 -c "print('потокбонусов.рф'.encode('idna').decode())"
# -> xn--80aafgcqfdbaebrl0b.xn--p1ai
bash /opt/flowbonus/server/enable-https.sh flowbonus.ru www.flowbonus.ru xn--80aafgcqfdbaebrl0b.xn--p1ai
```

Скрипт проверит DNS, впишет домены в nginx, получит сертификат Let's Encrypt,
включит редирект с HTTP на HTTPS, выставит `SESSION_COOKIE_SECURE=1` и проверит
автопродление сертификата.

> `SESSION_COOKIE_SECURE=1` до подключения HTTPS ставить нельзя — браузер перестанет
> отправлять cookie и вход сломается. Скрипт включает его только после получения
> сертификата.

## 8. Бэкапы

Ежедневно в 04:00 через cron (`/etc/cron.d/flowbonus-backup`), хранятся 14 дней.
Вручную: `flowbonus-backup`.

Восстановление:

```bash
systemctl stop flowbonus
gunzip -c /var/lib/flowbonus/backups/flowbonus-20260919-040000.db.gz > /var/lib/flowbonus/flowbonus.db
chown flowbonus:flowbonus /var/lib/flowbonus/flowbonus.db
systemctl start flowbonus
```

Копии лежат на том же диске, поэтому раз в неделю скачивайте их к себе:

```powershell
scp root@IP_СЕРВЕРА:/var/lib/flowbonus/backups/*.gz .
```

---

## Переменные окружения

Все живут в `/etc/flowbonus.env`, полный список с пояснениями — в
[`server/.env.example`](server/.env.example). После правки нужен
`systemctl restart flowbonus`.

| Переменная | Назначение |
|---|---|
| `SECRET_KEY` | Подпись cookie-сессий. Случайный, генерируется при установке. Смена = разлогин всех. |
| `FLOWBONUS_DB_PATH` | Файл базы SQLite |
| `FLOWBONUS_UPLOAD_DIR` | Каталог фотографий партнёров |
| `MAX_UPLOAD_MB` | Лимит размера файла; держите равным `client_max_body_size` в nginx |
| `TRUST_PROXY` | `1` за nginx — иначе ссылка в QR уедет на `127.0.0.1` |
| `SESSION_COOKIE_SECURE` | `1` только после подключения HTTPS |

## Что было убрано из git

Эти файлы остались на компьютере, но больше не попадают в публичный репозиторий:

| Файл | Почему |
|---|---|
| `server/flowbonus.db` | Рабочая база с персональными данными; к тому же деплой затирал ею данные сервера |
| `назв и дом.txt` | Пароль в открытом виде |
| `Норма тела.png` | Исходник, не нужен приложению |
| `assets/partners/p2/` | Фотографии партнёра — пользовательский контент, место которому на сервере |

> Важно: они убраны из текущего коммита, но **остаются в истории git** и в уже
> опубликованных коммитах на GitHub. Пароль из `назв и дом.txt` (`Norma12`)
> считайте раскрытым — смените его в кабинете партнёра после деплоя.

## Почему SQLite, а не PostgreSQL

Нагрузка — единицы запросов в секунду, запись редкая. SQLite в режиме WAL с
`busy_timeout=30s` это спокойно выдерживает, а бэкап — это один файл. Managed
PostgreSQL от Timeweb понадобится, если появится второй сервер приложения или
записи станут тысячами в минуту. Тогда меняется только `server/db.py`.

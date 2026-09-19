# FlowBonus

Веб-сервис бонусной платформы: лендинг, личный кабинет клиента и кабинет партнёра.

## Быстрый старт локально

```bash
cd server
python -m venv .venv
.venv\Scripts\activate        # Windows; на Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Откройте `http://127.0.0.1:5500`. База создастся сама в `server/flowbonus.db`.

Тестовые данные (пароли задаёте сами, в репозитории их нет):

```bash
DEMO_PARTNER_PASSWORD=Norma12 DEMO_CLIENT_PASSWORD=Test123 python seed_demo.py
```

На Windows в PowerShell:

```powershell
$env:DEMO_PARTNER_PASSWORD="Norma12"; $env:DEMO_CLIENT_PASSWORD="Test123"; python seed_demo.py
```

Создаст партнёра «Норма Тела» (вход `+7 917 840-90-90`) и клиента `+7 900 111-22-33`.

## Что внутри

- `index.html`, `clients.html`, `partners.html` — публичные страницы
- `cabinet/` — личный кабинет клиента
- `partner-cabinet/` — кабинет партнёра
- `css/mobile.css`, `cabinet/css/mobile.css` — отдельная мобильная вёрстка
- `server/` — Flask API + SQLite

### Файлы сервера

| Файл | Назначение |
|---|---|
| `app.py` | Маршруты: страницы, статика, API клиента и партнёра |
| `db.py` | Схема SQLite, миграции, вся работа с данными |
| `wsgi.py` | Точка входа для waitress в продакшене |
| `seed_demo.py` | Тестовые данные (пароли — из переменных окружения) |
| `.env.example` | Все переменные окружения с пояснениями |
| `deploy.sh` | Первичная установка на сервер Timeweb |
| `update.sh` | Обновление кода на сервере без потери данных |
| `backup.sh` | Бэкап базы (корректный для режима WAL) |
| `seed.sh` | Тестовые данные на сервере, пароли спрашивает интерактивно |
| `enable-https.sh` | Домены и сертификат Let's Encrypt |
| `flowbonus.service` | Юнит systemd |
| `nginx-flowbonus.conf` | Конфиг nginx (reverse proxy) |

## Настройка

Приложение читает только переменные окружения, см. `server/.env.example`.
Без них работает в режиме локальной разработки: база и загрузки — внутри проекта,
`SECRET_KEY` генерируется в `server/.secret_key`.

В продакшене база и фотографии обязательно лежат **вне** каталога с кодом
(`FLOWBONUS_DB_PATH`, `FLOWBONUS_UPLOAD_DIR`), иначе обновление кода затрёт данные.

## Деплой

Разворачивается на облачном сервере Timeweb Cloud: nginx → waitress → SQLite.
Пошаговая инструкция — в [DEPLOY.md](DEPLOY.md).

## Данные, которых нет в репозитории

База, фотографии партнёров и личные заметки намеренно не версионируются
(см. `.gitignore`). База с рабочими данными живёт только на сервере, в
`/var/lib/flowbonus/`, и бэкапится по cron.

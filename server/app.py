"""FlowBonus server: лендинг + API + кабинет клиента."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

from db import (
    add_coins,
    add_partner_image,
    admin_add_client_coins,
    admin_count,
    admin_public,
    admin_reset_client_password,
    admin_reset_partner_password,
    admin_set_client_blocked,
    admin_set_partner_blocked,
    admin_stats,
    bootstrap_or_verify_admin,
    client_is_blocked,
    client_public,
    create_client,
    create_partner,
    create_promo_admin,
    create_spend_token,
    delete_partner_image,
    get_admin_by_id,
    get_client_admin_detail,
    get_client_by_id,
    get_connection,
    get_partner_admin_detail,
    get_partner_by_id,
    init_db,
    list_admin_audit,
    list_clients_admin,
    list_partners_admin,
    list_partners_public,
    list_promos_admin,
    lookup_spend_token,
    partner_is_blocked,
    partner_public,
    partner_stats,
    redeem_promo,
    redeem_spend_token,
    set_promo_active,
    update_partner_profile,
    update_selected_city,
    verify_login,
    verify_partner_login,
)

ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = Path(__file__).resolve().parent
DATA_DIR = SERVER_DIR / "data"
COIN_PRICE_RUB = 100

# Фотографии партнёров хранятся вне git-каталога на сервере, см. .env.example.
BUNDLED_PARTNER_ASSETS = ROOT / "assets" / "partners"
UPLOAD_DIR = Path(os.environ.get("FLOWBONUS_UPLOAD_DIR") or BUNDLED_PARTNER_ASSETS).expanduser()
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024

PASSWORD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]{6,}$")
PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{10,20}$")
ADMIN_LOGIN_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,64}$")


def _load_secret_key() -> str:
    """SECRET_KEY из окружения; иначе — постоянный файл, чтобы сессии жили между рестартами."""
    from_env = os.environ.get("SECRET_KEY", "").strip()
    if from_env:
        return from_env

    key_file = Path(os.environ.get("FLOWBONUS_SECRET_FILE") or (SERVER_DIR / ".secret_key"))
    if key_file.is_file():
        stored = key_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    generated = secrets.token_urlsafe(48)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(generated, encoding="utf-8")
    os.chmod(key_file, 0o600)
    return generated


app = Flask(
    __name__,
    static_folder=None,
)
app.secret_key = _load_secret_key()
app.config.update(
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    JSON_SORT_KEYS=False,
)

# За nginx-прокси: без этого request.host_url в QR-ссылке уедет на http/127.0.0.1.
if os.environ.get("TRUST_PROXY", "1") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
init_db()


def load_cities() -> list[str]:
    path = DATA_DIR / "cities_ru.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_partners() -> list[dict]:
    path = DATA_DIR / "partners.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def current_client():
    client_id = session.get("client_id")
    if not client_id:
        return None
    client = get_client_by_id(client_id)
    if client and client_is_blocked(client):
        session.clear()
        return None
    return client


def current_partner():
    partner_id = session.get("partner_id")
    if not partner_id:
        return None
    partner = get_partner_by_id(partner_id)
    if partner and partner_is_blocked(partner):
        session.clear()
        return None
    return partner


def current_admin():
    admin_id = session.get("admin_id")
    if not admin_id:
        return None
    return get_admin_by_id(admin_id)


def require_admin():
    admin = current_admin()
    if not admin:
        return None, (jsonify({"error": "unauthorized"}), 401)
    return admin, None


# ---------- static landing & assets ----------

@app.get("/")
def home():
    return send_from_directory(ROOT, "index.html")


@app.get("/index.html")
def index_html():
    return send_from_directory(ROOT, "index.html")


@app.get("/clients.html")
def clients_html():
    return send_from_directory(ROOT, "clients.html")


@app.get("/partners.html")
def partners_html():
    return send_from_directory(ROOT, "partners.html")


@app.get("/css/<path:filename>")
def css_files(filename: str):
    return send_from_directory(ROOT / "css", filename)


@app.get("/js/<path:filename>")
def js_files(filename: str):
    return send_from_directory(ROOT / "js", filename)


@app.get("/assets/<path:filename>")
def assets_files(filename: str):
    return send_from_directory(ROOT / "assets", filename)


@app.get("/assets/partners/<path:filename>")
def partner_assets_files(filename: str):
    """Сначала ищем в каталоге загрузок, затем среди картинок из репозитория."""
    if UPLOAD_DIR != BUNDLED_PARTNER_ASSETS and (UPLOAD_DIR / filename).is_file():
        return send_from_directory(UPLOAD_DIR, filename)
    return send_from_directory(BUNDLED_PARTNER_ASSETS, filename)


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(ROOT / "assets", "favicon.ico")


@app.get("/robots.txt")
def robots_txt():
    return send_from_directory(ROOT, "robots.txt")


@app.get("/flowbonus-hero.png")
def hero_png():
    return send_from_directory(ROOT, "flowbonus-hero.png")


@app.get("/cabinet")
@app.get("/cabinet/")
def cabinet_page():
    if not current_client():
        return redirect("/?login=1")
    return send_from_directory(ROOT / "cabinet", "index.html")


@app.get("/cabinet/css/<path:filename>")
def cabinet_css(filename: str):
    return send_from_directory(ROOT / "cabinet" / "css", filename)


@app.get("/cabinet/js/<path:filename>")
def cabinet_js(filename: str):
    return send_from_directory(ROOT / "cabinet" / "js", filename)


@app.get("/partner-cabinet")
@app.get("/partner-cabinet/")
def partner_cabinet_page():
    if not current_partner():
        return redirect("/partners.html?login=partner")
    return send_from_directory(ROOT / "partner-cabinet", "index.html")


@app.get("/partner-cabinet/css/<path:filename>")
def partner_cabinet_css(filename: str):
    return send_from_directory(ROOT / "partner-cabinet" / "css", filename)


@app.get("/partner-cabinet/js/<path:filename>")
def partner_cabinet_js(filename: str):
    return send_from_directory(ROOT / "partner-cabinet" / "js", filename)


@app.get("/partner/scan")
def partner_scan_redirect():
    token = (request.args.get("token") or "").strip()
    if not current_partner():
        return redirect(f"/partners.html?login=partner&token={token}")
    return redirect(f"/partner-cabinet/?scan={token}")


@app.get("/admin/login")
@app.get("/admin/login/")
def admin_login_page():
    if current_admin():
        return redirect("/admin/")
    return send_from_directory(ROOT / "admin", "login.html")


@app.get("/admin")
@app.get("/admin/")
def admin_cabinet_page():
    if not current_admin():
        return redirect("/admin/login")
    return send_from_directory(ROOT / "admin", "index.html")


@app.get("/admin/css/<path:filename>")
def admin_css(filename: str):
    return send_from_directory(ROOT / "admin" / "css", filename)


@app.get("/admin/js/<path:filename>")
def admin_js(filename: str):
    return send_from_directory(ROOT / "admin" / "js", filename)


# ---------- API ----------

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "coin_price_rub": COIN_PRICE_RUB})


@app.get("/api/cities")
def api_cities():
    return jsonify({"cities": load_cities()})


@app.get("/api/partners")
def api_partners():
    city = (request.args.get("city") or "").strip() or None
    partners = list_partners_public(city)
    return jsonify({"partners": partners})


@app.get("/api/me")
def api_me():
    client = current_client()
    if not client:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"client": client_public(client), "coin_price_rub": COIN_PRICE_RUB})


@app.post("/api/register")
def api_register():
    data = request.get_json(silent=True) or {}
    fio = (data.get("fio") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    city = (data.get("city") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password2") or ""

    if not all([fio, phone, email, city, password, password2]):
        return jsonify({"error": "Заполните все поля."}), 400
    if not PHONE_RE.match(phone):
        return jsonify({"error": "Некорректный номер телефона."}), 400
    if "@" not in email or "." not in email:
        return jsonify({"error": "Некорректный email."}), 400
    if not PASSWORD_RE.match(password):
        return jsonify(
            {"error": "Пароль: минимум 6 символов, только буквы или цифры."}
        ), 400
    if password != password2:
        return jsonify({"error": "Пароли не совпадают."}), 400

    try:
        client = create_client(
            fio=fio,
            phone=phone,
            email=email,
            city=city,
            password=password,
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "unique" in msg or "unique constraint" in msg:
            return jsonify({"error": "Такой телефон или email уже зарегистрирован."}), 409
        return jsonify({"error": "Не удалось создать профиль."}), 500

    session.clear()
    session["client_id"] = client["id"]
    return jsonify({"ok": True, "client": client_public(client), "redirect": "/cabinet/"})


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    if not phone or not password:
        return jsonify({"error": "Введите телефон и пароль."}), 400

    client = verify_login(phone, password)
    if not client:
        return jsonify({"error": "Неверный телефон или пароль."}), 401
    if client_is_blocked(client):
        return jsonify({"error": "Доступ к кабинету заблокирован."}), 403

    session.clear()
    session["client_id"] = client["id"]
    return jsonify({"ok": True, "client": client_public(client), "redirect": "/cabinet/"})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/city")
def api_set_city():
    client = current_client()
    if not client:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    city = (data.get("city") or "").strip()
    if not city:
        return jsonify({"error": "Выберите город."}), 400
    cities = load_cities()
    if city not in cities:
        return jsonify({"error": "Город не найден в списке."}), 400
    update_selected_city(client["id"], city)
    refreshed = get_client_by_id(client["id"])
    return jsonify({"ok": True, "client": client_public(refreshed)})


@app.post("/api/buy-coins")
def api_buy_coins():
    """Демо-оплата: карту не сохраняем, только last4 для истории."""
    client = current_client()
    if not client:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    try:
        coins = int(data.get("coins") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Укажите количество монет."}), 400

    card_number = re.sub(r"\D", "", str(data.get("card_number") or ""))
    card_exp = (data.get("card_exp") or "").strip()
    card_cvc = re.sub(r"\D", "", str(data.get("card_cvc") or ""))

    if coins < 1 or coins > 100:
        return jsonify({"error": "Можно купить от 1 до 100 монет за раз."}), 400
    if len(card_number) < 16:
        return jsonify({"error": "Проверьте номер карты."}), 400
    if not re.match(r"^\d{2}/\d{2}$", card_exp):
        return jsonify({"error": "Срок карты в формате ММ/ГГ."}), 400
    if len(card_cvc) < 3:
        return jsonify({"error": "Проверьте CVC-код."}), 400

    amount = coins * COIN_PRICE_RUB
    new_balance = add_coins(client["id"], coins, amount, card_number[-4:])
    return jsonify(
        {
            "ok": True,
            "coins": new_balance,
            "added": coins,
            "amount_rub": amount,
            "message": f"Зачислено {coins} монет на сумму {amount} ₽.",
        }
    )


@app.post("/api/promo")
def api_promo():
    client = current_client()
    if not client:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    code = data.get("code") or ""
    try:
        result = redeem_promo(client["id"], code)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(
        {
            "ok": True,
            "coins": result["balance"],
            "added": result["coins_added"],
            "message": f"Промокод {result['code']} активирован. +{result['coins_added']} монет.",
        }
    )


@app.post("/api/spend-qr")
def api_spend_qr():
    """Создаёт одноразовый QR-токен для списания монет партнёром."""
    client = current_client()
    if not client:
        return jsonify({"error": "unauthorized"}), 401

    token_data = create_spend_token(client["id"], ttl_minutes=10)
    payload = {
        "type": "flowbonus_spend",
        "token": token_data["token"],
        "client_id": client["id"],
        "phone": client["phone"],
        "fio": client["fio"],
        "coins": client["coins"],
        "expires_at": token_data["expires_at"],
    }
    # URL, который позже откроет кабинет партнёра при сканировании
    scan_url = f"{request.host_url.rstrip('/')}/partner/scan?token={token_data['token']}"
    return jsonify(
        {
            "ok": True,
            "token": token_data["token"],
            "ttl_minutes": token_data["ttl_minutes"],
            "expires_at": token_data["expires_at"],
            "qr_payload": scan_url,
            "payload": payload,
            "balance": client["coins"],
        }
    )


# ---------- Partner API ----------

@app.get("/api/partner/me")
def api_partner_me():
    partner = current_partner()
    if not partner:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"partner": partner_public(partner), "stats": partner_stats(partner["id"])})


@app.post("/api/partner/register")
def api_partner_register():
    data = request.get_json(silent=True) or {}
    business = (data.get("business") or "").strip()
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    city = (data.get("city") or "").strip()
    address = (data.get("address") or "").strip()
    comment = (data.get("comment") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password2") or ""

    if not all([business, category, name, phone, password, password2]):
        return jsonify({"error": "Заполните обязательные поля."}), 400
    if not PHONE_RE.match(phone):
        return jsonify({"error": "Некорректный номер телефона."}), 400
    if not PASSWORD_RE.match(password):
        return jsonify({"error": "Пароль: минимум 6 символов, только буквы или цифры."}), 400
    if password != password2:
        return jsonify({"error": "Пароли не совпадают."}), 400

    try:
        partner = create_partner(
            business_name=business,
            category=category,
            contact_name=name,
            phone=phone,
            password=password,
            city=city,
            address=address,
            comment=comment,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "unique" in msg:
            return jsonify({"error": "Этот телефон уже зарегистрирован как партнёр."}), 409
        return jsonify({"error": "Не удалось создать кабинет партнёра."}), 500

    session.clear()
    session["partner_id"] = partner["id"]
    return jsonify({"ok": True, "partner": partner_public(partner), "redirect": "/partner-cabinet/"})


@app.post("/api/partner/login")
def api_partner_login():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    if not phone or not password:
        return jsonify({"error": "Введите телефон и пароль."}), 400

    partner = verify_partner_login(phone, password)
    if not partner:
        return jsonify({"error": "Неверный телефон или пароль."}), 401
    if partner_is_blocked(partner):
        return jsonify({"error": "Доступ к кабинету заблокирован."}), 403

    session.clear()
    session["partner_id"] = partner["id"]
    return jsonify({"ok": True, "partner": partner_public(partner), "redirect": "/partner-cabinet/"})


@app.post("/api/partner/logout")
def api_partner_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/partner/profile")
def api_partner_profile():
    partner = current_partner()
    if not partner:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    updated = update_partner_profile(
        partner["id"],
        city=data.get("city", partner["city"]),
        address=data.get("address", partner["address"]),
        spend_coins=data.get("spend_coins", partner["spend_coins"]),
        comment=data.get("comment", partner["comment"]),
        website=data.get("website", _safe_get(partner, "website", "")),
        description=data.get("description", _safe_get(partner, "description", "")),
        hours=data.get("hours", _safe_get(partner, "hours", "")),
        category=data.get("category", partner["category"]),
        business_name=data.get("business_name", partner["business_name"]),
    )
    return jsonify({"ok": True, "partner": partner_public(updated)})


def _safe_get(row, key, default=""):
    try:
        return row[key] if row[key] is not None else default
    except (KeyError, IndexError):
        return default


@app.post("/api/partner/images")
def api_partner_upload_image():
    partner = current_partner()
    if not partner:
        return jsonify({"error": "unauthorized"}), 401
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "Выберите изображение."}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return jsonify({"error": "Допустимы JPG, PNG, WEBP, GIF."}), 400

    import uuid

    folder = UPLOAD_DIR / f"p{partner['id']}"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = folder / filename
    file.save(dest)
    rel = f"/assets/partners/p{partner['id']}/{filename}"
    image = add_partner_image(partner["id"], rel)
    return jsonify({"ok": True, "image": image, "partner": partner_public(get_partner_by_id(partner["id"]))})


@app.delete("/api/partner/images/<int:image_id>")
def api_partner_delete_image(image_id: int):
    partner = current_partner()
    if not partner:
        return jsonify({"error": "unauthorized"}), 401
    path = delete_partner_image(partner["id"], image_id)
    if not path:
        return jsonify({"error": "Изображение не найдено."}), 404
    # удаляем файл, если он лежит в папке загрузок именно этого партнёра
    try:
        folder = UPLOAD_DIR / f"p{partner['id']}"
        local = folder / Path(path).name
        if local.is_file() and local.parent == folder:
            local.unlink(missing_ok=True)
    except OSError:
        pass
    return jsonify({"ok": True, "partner": partner_public(get_partner_by_id(partner["id"]))})


@app.post("/api/partner/lookup-token")
def api_partner_lookup_token():
    partner = current_partner()
    if not partner:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    if "token=" in token:
        token = token.split("token=")[-1].split("&")[0].strip()
    try:
        info = lookup_spend_token(token)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "spend": info, "suggested_coins": partner["spend_coins"]})


@app.post("/api/partner/redeem")
def api_partner_redeem():
    partner = current_partner()
    if not partner:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    if "token=" in token:
        token = token.split("token=")[-1].split("&")[0].strip()
    try:
        coins = int(data.get("coins") or partner["spend_coins"])
        result = redeem_spend_token(partner_id=partner["id"], token=token, coins=coins)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Некорректное количество монет."}), 400
    return jsonify({**result, "stats": partner_stats(partner["id"])})


# ---------- Admin API ----------

@app.get("/api/admin/bootstrap-status")
def api_admin_bootstrap_status():
    return jsonify({"needs_bootstrap": admin_count() == 0})


@app.post("/api/admin/login")
def api_admin_login():
    data = request.get_json(silent=True) or {}
    login = (data.get("login") or "").strip()
    password = data.get("password") or ""
    if not login or not password:
        return jsonify({"error": "Введите логин и пароль."}), 400
    if admin_count() == 0 and not ADMIN_LOGIN_RE.match(login):
        return jsonify(
            {"error": "Логин: 3–64 символа, латиница, цифры, . _ -"}
        ), 400
    if not PASSWORD_RE.match(password):
        return jsonify(
            {"error": "Пароль: минимум 6 символов, только буквы или цифры."}
        ), 400
    try:
        admin = bootstrap_or_verify_admin(login, password)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 401
    session.clear()
    session["admin_id"] = admin["id"]
    session.permanent = True
    return jsonify(
        {
            "ok": True,
            "admin": admin_public(admin),
            "bootstrap": False,
            "redirect": "/admin/",
        }
    )


@app.post("/api/admin/logout")
def api_admin_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/admin/me")
def api_admin_me():
    admin, err = require_admin()
    if err:
        return err
    return jsonify({"admin": admin_public(admin)})


@app.get("/api/admin/stats")
def api_admin_stats():
    admin, err = require_admin()
    if err:
        return err
    date_from = request.args.get("from") or None
    date_to = request.args.get("to") or None
    try:
        stats = admin_stats(date_from, date_to)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "stats": stats})


@app.get("/api/admin/audit")
def api_admin_audit():
    admin, err = require_admin()
    if err:
        return err
    return jsonify({"ok": True, "items": list_admin_audit(80)})


@app.get("/api/admin/clients")
def api_admin_clients():
    admin, err = require_admin()
    if err:
        return err
    return jsonify({"ok": True, "clients": list_clients_admin()})


@app.get("/api/admin/clients/<int:client_id>")
def api_admin_client_detail(client_id: int):
    admin, err = require_admin()
    if err:
        return err
    detail = get_client_admin_detail(client_id)
    if not detail:
        return jsonify({"error": "Клиент не найден."}), 404
    return jsonify({"ok": True, "client": detail})


@app.post("/api/admin/clients/<int:client_id>/coins")
def api_admin_client_coins(client_id: int):
    admin, err = require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        coins = int(data.get("coins") or 0)
        balance = admin_add_client_coins(
            admin_id=admin["id"],
            client_id=client_id,
            coins=coins,
            note=str(data.get("note") or ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "coins": balance, "client": get_client_admin_detail(client_id)})


@app.post("/api/admin/clients/<int:client_id>/password")
def api_admin_client_password(client_id: int):
    admin, err = require_admin()
    if err:
        return err
    try:
        password = admin_reset_client_password(admin["id"], client_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "password": password})


@app.post("/api/admin/clients/<int:client_id>/block")
def api_admin_client_block(client_id: int):
    admin, err = require_admin()
    if err:
        return err
    try:
        admin_set_client_blocked(admin["id"], client_id, True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "is_blocked": True})


@app.post("/api/admin/clients/<int:client_id>/unblock")
def api_admin_client_unblock(client_id: int):
    admin, err = require_admin()
    if err:
        return err
    try:
        admin_set_client_blocked(admin["id"], client_id, False)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "is_blocked": False})


@app.get("/api/admin/partners")
def api_admin_partners():
    admin, err = require_admin()
    if err:
        return err
    return jsonify({"ok": True, "partners": list_partners_admin()})


@app.get("/api/admin/partners/<int:partner_id>")
def api_admin_partner_detail(partner_id: int):
    admin, err = require_admin()
    if err:
        return err
    detail = get_partner_admin_detail(partner_id)
    if not detail:
        return jsonify({"error": "Партнёр не найден."}), 404
    return jsonify({"ok": True, "partner": detail})


@app.post("/api/admin/partners/<int:partner_id>/password")
def api_admin_partner_password(partner_id: int):
    admin, err = require_admin()
    if err:
        return err
    try:
        password = admin_reset_partner_password(admin["id"], partner_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "password": password})


@app.post("/api/admin/partners/<int:partner_id>/block")
def api_admin_partner_block(partner_id: int):
    admin, err = require_admin()
    if err:
        return err
    try:
        admin_set_partner_blocked(admin["id"], partner_id, True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "is_blocked": True})


@app.post("/api/admin/partners/<int:partner_id>/unblock")
def api_admin_partner_unblock(partner_id: int):
    admin, err = require_admin()
    if err:
        return err
    try:
        admin_set_partner_blocked(admin["id"], partner_id, False)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "is_blocked": False})


@app.get("/api/admin/promos")
def api_admin_promos():
    admin, err = require_admin()
    if err:
        return err
    return jsonify({"ok": True, "promos": list_promos_admin()})


@app.post("/api/admin/promos")
def api_admin_create_promo():
    admin, err = require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    max_uses = data.get("max_uses")
    if max_uses in ("", None):
        max_uses = None
    try:
        promo = create_promo_admin(
            admin_id=admin["id"],
            code=str(data.get("code") or ""),
            coins=int(data.get("coins") or 0),
            comment=str(data.get("comment") or ""),
            max_uses=max_uses,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Некорректные данные промокода."}), 400
    return jsonify({"ok": True, "promo": promo})


@app.post("/api/admin/promos/<path:code>/close")
def api_admin_close_promo(code: str):
    admin, err = require_admin()
    if err:
        return err
    try:
        promo = set_promo_active(admin["id"], code, False)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "promo": promo})


@app.post("/api/admin/promos/<path:code>/open")
def api_admin_open_promo(code: str):
    admin, err = require_admin()
    if err:
        return err
    try:
        promo = set_promo_active(admin["id"], code, True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "promo": promo})


# ---------- error handlers ----------

@app.errorhandler(413)
def too_large(_exc):
    limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
    return jsonify({"error": f"Файл слишком большой. Максимум {limit_mb} МБ."}), 413


@app.errorhandler(404)
def not_found(exc):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Метод не найден."}), 404
    return exc


@app.errorhandler(500)
def server_error(_exc):
    app.logger.exception("unhandled error on %s", request.path)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Внутренняя ошибка сервера."}), 500
    return "Внутренняя ошибка сервера. Попробуйте позже.", 500


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5500"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"FlowBonus: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)

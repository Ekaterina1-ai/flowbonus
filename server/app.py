"""FlowBonus server: лендинг + API + кабинет клиента."""
from __future__ import annotations

import json
import re
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory, session

from db import (
    add_coins,
    add_partner_image,
    client_public,
    create_client,
    create_partner,
    create_spend_token,
    delete_partner_image,
    get_client_by_id,
    get_connection,
    get_partner_by_id,
    init_db,
    list_partners_public,
    lookup_spend_token,
    partner_public,
    partner_stats,
    redeem_promo,
    redeem_spend_token,
    update_partner_profile,
    update_selected_city,
    verify_login,
    verify_partner_login,
)

ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = Path(__file__).resolve().parent
DATA_DIR = SERVER_DIR / "data"
COIN_PRICE_RUB = 100

PASSWORD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]{6,}$")
PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{10,20}$")

app = Flask(
    __name__,
    static_folder=None,
)
app.secret_key = "flowbonus-dev-secret-change-in-production"


def load_cities() -> list[str]:
    path = DATA_DIR / "cities_ru.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_partners() -> list[dict]:
    path = DATA_DIR / "partners.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@app.before_request
def ensure_db() -> None:
    if not getattr(app, "_db_ready", False):
        init_db()
        app._db_ready = True


def current_client():
    client_id = session.get("client_id")
    if not client_id:
        return None
    return get_client_by_id(client_id)


def current_partner():
    partner_id = session.get("partner_id")
    if not partner_id:
        return None
    return get_partner_by_id(partner_id)


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


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(ROOT / "assets", "favicon.ico")


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

    folder = ROOT / "assets" / "partners" / f"p{partner['id']}"
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
    # удаляем файл, если он внутри нашей папки партнёра
    try:
        local = ROOT / path.lstrip("/").replace("/", "\\") if False else ROOT.joinpath(*path.strip("/").split("/"))
        if local.exists() and str(partner["id"]) in str(local):
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


if __name__ == "__main__":
    init_db()
    print("FlowBonus: http://127.0.0.1:5500")
    app.run(host="127.0.0.1", port=5500, debug=True)

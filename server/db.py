"""FlowBonus — инициализация SQLite и работа с пользователями."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).resolve().parent / "flowbonus.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                city TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                coins INTEGER NOT NULL DEFAULT 0,
                selected_city TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS coin_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                coins_added INTEGER NOT NULL,
                card_last4 TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS spend_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                client_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                coins INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                max_uses INTEGER,
                used_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS promo_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                coins INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(client_id, code),
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (code) REFERENCES promo_codes(code)
            );

            CREATE TABLE IF NOT EXISTS partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT NOT NULL,
                category TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                city TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                comment TEXT NOT NULL DEFAULT '',
                spend_coins INTEGER NOT NULL DEFAULT 2,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS partner_spend_ops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                coins INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (partner_id) REFERENCES partners(id),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS partner_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (partner_id) REFERENCES partners(id)
            );
            """
        )
        # миграция колонок профиля партнёра
        partner_cols = {row[1] for row in conn.execute("PRAGMA table_info(partners)").fetchall()}
        for col, ddl in (
            ("website", "TEXT NOT NULL DEFAULT ''"),
            ("description", "TEXT NOT NULL DEFAULT ''"),
            ("hours", "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in partner_cols:
                conn.execute(f"ALTER TABLE partners ADD COLUMN {col} {ddl}")
        # демо-промокоды
        conn.execute(
            """
            INSERT OR IGNORE INTO promo_codes (code, coins, active, max_uses, used_count)
            VALUES
              ('FLOWBONUS', 1, 1, NULL, 0),
              ('START2', 2, 1, NULL, 0)
            """
        )
        conn.commit()


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def create_client(
    *,
    fio: str,
    phone: str,
    email: str,
    city: str,
    password: str,
) -> sqlite3.Row:
    phone_norm = normalize_phone(phone)
    password_hash = generate_password_hash(password)
    with get_connection() as conn:
        exists_partner = conn.execute(
            "SELECT id FROM partners WHERE phone = ?", (phone_norm,)
        ).fetchone()
        if exists_partner:
            raise ValueError("Этот телефон уже зарегистрирован как партнёр.")

        cur = conn.execute(
            """
            INSERT INTO clients (fio, phone, email, city, password_hash, selected_city)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (fio.strip(), phone_norm, email.strip().lower(), city.strip(), password_hash, city.strip()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row


def get_client_by_phone(phone: str) -> sqlite3.Row | None:
    phone_norm = normalize_phone(phone)
    with get_connection() as conn:
        return conn.execute("SELECT * FROM clients WHERE phone = ?", (phone_norm,)).fetchone()


def get_client_by_id(client_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()


def verify_login(phone: str, password: str) -> sqlite3.Row | None:
    client = get_client_by_phone(phone)
    if not client:
        return None
    if not check_password_hash(client["password_hash"], password):
        return None
    return client


def update_selected_city(client_id: int, city: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE clients SET selected_city = ? WHERE id = ?",
            (city.strip(), client_id),
        )
        conn.commit()


def add_coins(client_id: int, coins: int, amount_rub: int, card_last4: str) -> int:
    with get_connection() as conn:
        conn.execute(
            "UPDATE clients SET coins = coins + ? WHERE id = ?",
            (coins, client_id),
        )
        conn.execute(
            """
            INSERT INTO coin_orders (client_id, amount, coins_added, card_last4)
            VALUES (?, ?, ?, ?)
            """,
            (client_id, amount_rub, coins, card_last4),
        )
        conn.commit()
        row = conn.execute("SELECT coins FROM clients WHERE id = ?", (client_id,)).fetchone()
        return int(row["coins"])


def client_public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "fio": row["fio"],
        "phone": row["phone"],
        "email": row["email"],
        "city": row["city"],
        "selected_city": row["selected_city"] or row["city"],
        "coins": row["coins"],
    }


def redeem_promo(client_id: int, code: str) -> dict:
    code_norm = code.strip().upper()
    if not code_norm:
        raise ValueError("Введите промокод.")

    with get_connection() as conn:
        promo = conn.execute(
            "SELECT * FROM promo_codes WHERE code = ?",
            (code_norm,),
        ).fetchone()
        if not promo or not promo["active"]:
            raise ValueError("Промокод не найден или неактивен.")

        already = conn.execute(
            "SELECT id FROM promo_redemptions WHERE client_id = ? AND code = ?",
            (client_id, code_norm),
        ).fetchone()
        if already:
            raise ValueError("Вы уже активировали этот промокод.")

        if promo["max_uses"] is not None and promo["used_count"] >= promo["max_uses"]:
            raise ValueError("Лимит активаций промокода исчерпан.")

        coins = int(promo["coins"])
        conn.execute(
            "UPDATE clients SET coins = coins + ? WHERE id = ?",
            (coins, client_id),
        )
        conn.execute(
            "UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?",
            (code_norm,),
        )
        conn.execute(
            """
            INSERT INTO promo_redemptions (client_id, code, coins)
            VALUES (?, ?, ?)
            """,
            (client_id, code_norm, coins),
        )
        conn.commit()
        balance = conn.execute(
            "SELECT coins FROM clients WHERE id = ?",
            (client_id,),
        ).fetchone()["coins"]

    return {"coins_added": coins, "balance": int(balance), "code": code_norm}


def create_spend_token(client_id: int, ttl_minutes: int = 10) -> dict:
    import secrets
    from datetime import datetime, timedelta, timezone

    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ttl_minutes)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO spend_tokens (token, client_id, created_at, expires_at, used)
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                token,
                client_id,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                expires.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
    return {
        "token": token,
        "expires_at": expires.isoformat(),
        "ttl_minutes": ttl_minutes,
    }


def partner_public(row: sqlite3.Row) -> dict:
    images = list_partner_images(row["id"])
    return {
        "id": row["id"],
        "business_name": row["business_name"],
        "category": row["category"],
        "contact_name": row["contact_name"],
        "phone": row["phone"],
        "city": row["city"] or "",
        "address": row["address"] or "",
        "comment": row["comment"] or "",
        "website": _row_get(row, "website", ""),
        "description": _row_get(row, "description", ""),
        "hours": _row_get(row, "hours", ""),
        "spend_coins": int(row["spend_coins"] or 2),
        "images": images,
        "image": images[0]["path"] if images else "/assets/partners/norma-tela.png",
    }


def _row_get(row: sqlite3.Row, key: str, default=""):
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError):
        return default


def list_partner_images(partner_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, path, sort_order
            FROM partner_images
            WHERE partner_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (partner_id,),
        ).fetchall()
    return [{"id": r["id"], "path": r["path"], "sort_order": r["sort_order"]} for r in rows]


def add_partner_image(partner_id: int, path: str) -> dict:
    with get_connection() as conn:
        order_row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM partner_images WHERE partner_id = ?",
            (partner_id,),
        ).fetchone()
        next_order = int(order_row["next_order"])
        cur = conn.execute(
            """
            INSERT INTO partner_images (partner_id, path, sort_order)
            VALUES (?, ?, ?)
            """,
            (partner_id, path, next_order),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, path, sort_order FROM partner_images WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return {"id": row["id"], "path": row["path"], "sort_order": row["sort_order"]}


def delete_partner_image(partner_id: int, image_id: int) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT path FROM partner_images WHERE id = ? AND partner_id = ?",
            (image_id, partner_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "DELETE FROM partner_images WHERE id = ? AND partner_id = ?",
            (image_id, partner_id),
        )
        conn.commit()
        return row["path"]


def list_partners_public(city: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if city:
            rows = conn.execute(
                "SELECT * FROM partners WHERE city = ? ORDER BY id ASC",
                (city,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM partners ORDER BY id ASC").fetchall()
    result = []
    for row in rows:
        images = list_partner_images(row["id"])
        paths = [img["path"] for img in images]
        result.append(
            {
                "id": f"db-{row['id']}",
                "partner_id": row["id"],
                "name": row["business_name"],
                "city": row["city"] or "",
                "category": row["category"],
                "address": row["address"] or "",
                "phone": row["phone"],
                "hours": _row_get(row, "hours", ""),
                "website": _row_get(row, "website", ""),
                "description": _row_get(row, "description", "") or (row["comment"] or ""),
                "spend_coins": int(row["spend_coins"] or 2),
                "images": paths,
                "image": paths[0] if paths else "/assets/partners/norma-tela.png",
            }
        )
    return result


def create_partner(
    *,
    business_name: str,
    category: str,
    contact_name: str,
    phone: str,
    password: str,
    city: str = "",
    address: str = "",
    comment: str = "",
) -> sqlite3.Row:
    phone_norm = normalize_phone(phone)
    password_hash = generate_password_hash(password)
    with get_connection() as conn:
        # телефон не должен совпадать с клиентским логином в той же роли-путанице —
        # разрешаем разные таблицы, но один номер = один тип аккаунта для простоты
        exists_client = conn.execute(
            "SELECT id FROM clients WHERE phone = ?", (phone_norm,)
        ).fetchone()
        if exists_client:
            raise ValueError("Этот телефон уже зарегистрирован как клиент.")

        cur = conn.execute(
            """
            INSERT INTO partners (
                business_name, category, contact_name, phone, password_hash,
                city, address, comment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                business_name.strip(),
                category.strip(),
                contact_name.strip(),
                phone_norm,
                password_hash,
                city.strip(),
                address.strip(),
                comment.strip(),
            ),
        )
        conn.commit()
        return conn.execute("SELECT * FROM partners WHERE id = ?", (cur.lastrowid,)).fetchone()


def get_partner_by_phone(phone: str) -> sqlite3.Row | None:
    phone_norm = normalize_phone(phone)
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM partners WHERE phone = ?", (phone_norm,)
        ).fetchone()


def get_partner_by_id(partner_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM partners WHERE id = ?", (partner_id,)
        ).fetchone()


def verify_partner_login(phone: str, password: str) -> sqlite3.Row | None:
    partner = get_partner_by_phone(phone)
    if not partner:
        return None
    if not check_password_hash(partner["password_hash"], password):
        return None
    return partner


def update_partner_profile(partner_id: int, **fields) -> sqlite3.Row:
    allowed = {
        "city",
        "address",
        "spend_coins",
        "comment",
        "business_name",
        "website",
        "description",
        "hours",
        "category",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_partner_by_id(partner_id)

    if "spend_coins" in updates:
        updates["spend_coins"] = max(1, min(50, int(updates["spend_coins"])))

    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [partner_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE partners SET {cols} WHERE id = ?", values)
        conn.commit()
        return conn.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()


def partner_stats(partner_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS ops_count,
              COALESCE(SUM(coins), 0) AS coins_total
            FROM partner_spend_ops
            WHERE partner_id = ?
            """,
            (partner_id,),
        ).fetchone()
        recent = conn.execute(
            """
            SELECT o.coins, o.created_at, c.fio, c.phone
            FROM partner_spend_ops o
            JOIN clients c ON c.id = o.client_id
            WHERE o.partner_id = ?
            ORDER BY o.id DESC
            LIMIT 10
            """,
            (partner_id,),
        ).fetchall()
    return {
        "ops_count": int(row["ops_count"] or 0),
        "coins_total": int(row["coins_total"] or 0),
        "recent": [
            {
                "coins": r["coins"],
                "created_at": r["created_at"],
                "client_fio": r["fio"],
                "client_phone": r["phone"],
            }
            for r in recent
        ],
    }


def lookup_spend_token(token: str) -> dict:
    from datetime import datetime, timezone

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT t.*, c.fio, c.phone, c.coins AS client_coins
            FROM spend_tokens t
            JOIN clients c ON c.id = t.client_id
            WHERE t.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        raise ValueError("QR не найден или уже недействителен.")
    if row["used"]:
        raise ValueError("Этот QR уже был использован.")

    # expires_at stored as UTC string without timezone sometimes
    try:
        exp = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            raise ValueError("Срок действия QR истёк.")
    except ValueError as exc:
        if "истёк" in str(exc) or "использован" in str(exc) or "недействителен" in str(exc):
            raise
        # if parse fails, continue

    return {
        "token": row["token"],
        "client_id": row["client_id"],
        "client_fio": row["fio"],
        "client_phone": row["phone"],
        "client_coins": int(row["client_coins"] or 0),
        "expires_at": row["expires_at"],
    }


def redeem_spend_token(*, partner_id: int, token: str, coins: int) -> dict:
    info = lookup_spend_token(token)
    coins = int(coins)
    if coins < 1:
        raise ValueError("Укажите количество монет для списания.")
    if coins > info["client_coins"]:
        raise ValueError("У клиента недостаточно монет на счёте.")

    with get_connection() as conn:
        # повторная проверка used
        row = conn.execute(
            "SELECT used FROM spend_tokens WHERE token = ?", (token,)
        ).fetchone()
        if not row or row["used"]:
            raise ValueError("Этот QR уже был использован.")

        conn.execute(
            "UPDATE clients SET coins = coins - ? WHERE id = ? AND coins >= ?",
            (coins, info["client_id"], coins),
        )
        changed = conn.execute("SELECT changes()").fetchone()[0]
        if not changed:
            raise ValueError("Не удалось списать монеты.")

        conn.execute(
            "UPDATE spend_tokens SET used = 1 WHERE token = ?",
            (token,),
        )
        conn.execute(
            """
            INSERT INTO partner_spend_ops (partner_id, client_id, token, coins)
            VALUES (?, ?, ?, ?)
            """,
            (partner_id, info["client_id"], token, coins),
        )
        conn.commit()
        balance = conn.execute(
            "SELECT coins FROM clients WHERE id = ?",
            (info["client_id"],),
        ).fetchone()["coins"]

    return {
        "ok": True,
        "coins_spent": coins,
        "client_balance": int(balance),
        "client_fio": info["client_fio"],
    }

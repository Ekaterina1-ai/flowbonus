"""FlowBonus — инициализация SQLite и работа с пользователями."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

# На сервере база лежит вне каталога приложения (см. FLOWBONUS_DB_PATH в .env),
# иначе обновление кода через git затрёт рабочие данные.
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "flowbonus.db"
DB_PATH = Path(os.environ.get("FLOWBONUS_DB_PATH") or DEFAULT_DB_PATH).expanduser()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
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
                used_count INTEGER NOT NULL DEFAULT 0,
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
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

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS coin_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                source TEXT NOT NULL,
                admin_id INTEGER,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (admin_id) REFERENCES admins(id)
            );

            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT '',
                target_id TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (admin_id) REFERENCES admins(id)
            );

            CREATE INDEX IF NOT EXISTS idx_coin_orders_client ON coin_orders(client_id);
            CREATE INDEX IF NOT EXISTS idx_spend_tokens_client ON spend_tokens(client_id);
            CREATE INDEX IF NOT EXISTS idx_spend_tokens_expires ON spend_tokens(expires_at);
            CREATE INDEX IF NOT EXISTS idx_promo_redemptions_client ON promo_redemptions(client_id);
            CREATE INDEX IF NOT EXISTS idx_partners_city ON partners(city);
            CREATE INDEX IF NOT EXISTS idx_partner_spend_ops_partner ON partner_spend_ops(partner_id);
            CREATE INDEX IF NOT EXISTS idx_partner_spend_ops_client ON partner_spend_ops(client_id);
            CREATE INDEX IF NOT EXISTS idx_partner_images_partner ON partner_images(partner_id, sort_order);
            CREATE INDEX IF NOT EXISTS idx_coin_ledger_client ON coin_ledger(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_coin_orders_created ON coin_orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_partner_spend_ops_created ON partner_spend_ops(created_at);
            """
        )
        # миграция колонок профиля партнёра
        partner_cols = {row[1] for row in conn.execute("PRAGMA table_info(partners)").fetchall()}
        for col, ddl in (
            ("website", "TEXT NOT NULL DEFAULT ''"),
            ("description", "TEXT NOT NULL DEFAULT ''"),
            ("hours", "TEXT NOT NULL DEFAULT ''"),
            ("is_blocked", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col not in partner_cols:
                conn.execute(f"ALTER TABLE partners ADD COLUMN {col} {ddl}")

        client_cols = {row[1] for row in conn.execute("PRAGMA table_info(clients)").fetchall()}
        if "is_blocked" not in client_cols:
            conn.execute(
                "ALTER TABLE clients ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0"
            )

        promo_cols = {row[1] for row in conn.execute("PRAGMA table_info(promo_codes)").fetchall()}
        if "comment" not in promo_cols:
            conn.execute(
                "ALTER TABLE promo_codes ADD COLUMN comment TEXT NOT NULL DEFAULT ''"
            )
        if "created_at" not in promo_cols:
            # SQLite не позволяет non-constant default в ALTER TABLE
            conn.execute("ALTER TABLE promo_codes ADD COLUMN created_at TEXT")
            conn.execute(
                "UPDATE promo_codes SET created_at = datetime('now') WHERE created_at IS NULL"
            )

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
        conn.execute(
            """
            INSERT INTO coin_ledger (client_id, delta, source, note)
            VALUES (?, ?, 'purchase', ?)
            """,
            (client_id, coins, f"Покупка на {amount_rub} ₽"),
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
        "is_blocked": bool(_row_get(row, "is_blocked", 0)),
    }


def client_is_blocked(row: sqlite3.Row | None) -> bool:
    if not row:
        return False
    return bool(_row_get(row, "is_blocked", 0))


def partner_is_blocked(row: sqlite3.Row | None) -> bool:
    if not row:
        return False
    return bool(_row_get(row, "is_blocked", 0))


def redeem_promo(client_id: int, code: str) -> dict:
    code_norm = code.strip().upper()
    if not code_norm:
        raise ValueError("Введите промокод.")

    with get_connection() as conn:
        promo = conn.execute(
            "SELECT * FROM promo_codes WHERE code = ?",
            (code_norm,),
        ).fetchone()
        if not promo:
            raise ValueError("Промокод недействителен.")
        if not promo["active"]:
            raise ValueError("Промокод уже не действует.")

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
        conn.execute(
            """
            INSERT INTO coin_ledger (client_id, delta, source, note)
            VALUES (?, ?, 'promo', ?)
            """,
            (client_id, coins, f"Промокод {code_norm}"),
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
        conn.execute(
            """
            INSERT INTO coin_ledger (client_id, delta, source, note)
            VALUES (?, ?, 'spend', ?)
            """,
            (info["client_id"], -coins, f"Списание у партнёра #{partner_id}"),
        )
        conn.commit()
        balance = conn.execute(
            "SELECT coins FROM clients WHERE id = ?",
            (info["client_id"],)
        ).fetchone()["coins"]

    return {
        "ok": True,
        "coins_spent": coins,
        "client_balance": int(balance),
        "client_fio": info["client_fio"],
    }


# ---------- Admin ----------

def admin_count() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM admins").fetchone()
    return int(row["c"] or 0)


def get_admin_by_id(admin_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM admins WHERE id = ?", (admin_id,)).fetchone()


def get_admin_by_login(login: str) -> sqlite3.Row | None:
    login_norm = login.strip().lower()
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM admins WHERE lower(login) = ?",
            (login_norm,),
        ).fetchone()


def bootstrap_or_verify_admin(login: str, password: str) -> sqlite3.Row:
    """Первый вход создаёт единственного админа; далее — только проверка."""
    login_clean = login.strip()
    if not login_clean or len(login_clean) < 3:
        raise ValueError("Логин: минимум 3 символа.")
    if not password or len(password) < 6:
        raise ValueError("Пароль: минимум 6 символов.")

    with get_connection() as conn:
        count = int(conn.execute("SELECT COUNT(*) AS c FROM admins").fetchone()["c"] or 0)
        if count == 0:
            password_hash = generate_password_hash(password)
            cur = conn.execute(
                """
                INSERT INTO admins (login, password_hash)
                VALUES (?, ?)
                """,
                (login_clean, password_hash),
            )
            conn.commit()
            return conn.execute(
                "SELECT * FROM admins WHERE id = ?", (cur.lastrowid,)
            ).fetchone()

        admin = conn.execute(
            "SELECT * FROM admins WHERE lower(login) = ?",
            (login_clean.lower(),),
        ).fetchone()
        if not admin or not check_password_hash(admin["password_hash"], password):
            raise ValueError("Неверный логин или пароль.")
        return admin


def admin_public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "login": row["login"],
        "created_at": row["created_at"],
    }


def _insert_admin_audit(
    conn: sqlite3.Connection,
    admin_id: int,
    action: str,
    *,
    target_type: str = "",
    target_id: str = "",
    detail: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO admin_audit_log
          (admin_id, action, target_type, target_id, detail, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """,
        (admin_id, action, target_type, str(target_id), detail),
    )


def write_admin_audit(
    admin_id: int,
    action: str,
    *,
    target_type: str = "",
    target_id: str = "",
    detail: str = "",
) -> None:
    with get_connection() as conn:
        _insert_admin_audit(
            conn,
            admin_id,
            action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
        conn.commit()


AUDIT_ACTION_LABELS = {
    "block": "Блокировка",
    "unblock": "Разблокировка",
    "reset_password": "Сброс пароля",
    "add_coins": "Начисление монет",
    "create_promo": "Создание промокода",
    "close_promo": "Закрытие промокода",
    "open_promo": "Открытие промокода",
}


def _audit_target_label(
    conn: sqlite3.Connection, target_type: str, target_id: str
) -> str:
    tid = (target_id or "").strip()
    ttype = (target_type or "").strip().lower()
    if ttype == "client" and tid.isdigit():
        row = conn.execute(
            "SELECT fio FROM clients WHERE id = ?", (int(tid),)
        ).fetchone()
        if row:
            return f"Клиент: {row['fio']}"
        return f"Клиент #{tid}"
    if ttype == "partner" and tid.isdigit():
        row = conn.execute(
            "SELECT business_name FROM partners WHERE id = ?", (int(tid),)
        ).fetchone()
        if row:
            return f"Партнёр: {row['business_name']}"
        return f"Партнёр #{tid}"
    if ttype == "promo" and tid:
        return f"Промокод: {tid}"
    if ttype and tid:
        return f"{ttype} {tid}"
    return tid or "—"


def list_admin_audit(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.*, ad.login AS admin_login
            FROM admin_audit_log a
            JOIN admins ad ON ad.id = a.admin_id
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (max(1, min(200, int(limit))),),
        ).fetchall()
        items = []
        for r in rows:
            items.append(
                {
                    "id": r["id"],
                    "admin_id": r["admin_id"],
                    "admin_login": r["admin_login"],
                    "action": r["action"],
                    "action_label": AUDIT_ACTION_LABELS.get(r["action"], r["action"]),
                    "target_type": r["target_type"],
                    "target_id": r["target_id"],
                    "target_label": _audit_target_label(
                        conn, r["target_type"], r["target_id"]
                    ),
                    "detail": r["detail"],
                    "created_at": r["created_at"],
                }
            )
    return items


def list_clients_admin() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, fio, phone, email, city, selected_city, coins,
                   COALESCE(is_blocked, 0) AS is_blocked, created_at
            FROM clients
            ORDER BY id DESC
            """
        ).fetchall()
    return [
        {
            "id": r["id"],
            "fio": r["fio"],
            "phone": r["phone"],
            "email": r["email"],
            "city": r["city"],
            "selected_city": r["selected_city"] or r["city"],
            "coins": int(r["coins"] or 0),
            "is_blocked": bool(r["is_blocked"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_client_admin_detail(client_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, fio, phone, email, city, selected_city, coins,
                   COALESCE(is_blocked, 0) AS is_blocked, created_at
            FROM clients WHERE id = ?
            """,
            (client_id,),
        ).fetchone()
        if not row:
            return None
        ledger = conn.execute(
            """
            SELECT id, delta, source, note, created_at, admin_id
            FROM coin_ledger
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT 100
            """,
            (client_id,),
        ).fetchall()
        purchases = conn.execute(
            """
            SELECT id, amount, coins_added, created_at
            FROM coin_orders
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (client_id,),
        ).fetchall()
        promos = conn.execute(
            """
            SELECT code, coins, created_at
            FROM promo_redemptions
            WHERE client_id = ?
            ORDER BY id DESC
            """,
            (client_id,),
        ).fetchall()
    return {
        "id": row["id"],
        "fio": row["fio"],
        "phone": row["phone"],
        "email": row["email"],
        "city": row["city"],
        "selected_city": row["selected_city"] or row["city"],
        "coins": int(row["coins"] or 0),
        "is_blocked": bool(row["is_blocked"]),
        "created_at": row["created_at"],
        "ledger": [
            {
                "id": r["id"],
                "delta": int(r["delta"]),
                "source": r["source"],
                "note": r["note"] or "",
                "created_at": r["created_at"],
                "admin_id": r["admin_id"],
            }
            for r in ledger
        ],
        "purchases": [
            {
                "id": r["id"],
                "amount": int(r["amount"]),
                "coins_added": int(r["coins_added"]),
                "created_at": r["created_at"],
            }
            for r in purchases
        ],
        "promos": [
            {
                "code": r["code"],
                "coins": int(r["coins"]),
                "created_at": r["created_at"],
            }
            for r in promos
        ],
    }


def admin_add_client_coins(
    *,
    admin_id: int,
    client_id: int,
    coins: int,
    note: str = "",
) -> int:
    coins = int(coins)
    if coins < 1 or coins > 10000:
        raise ValueError("Можно начислить от 1 до 10000 монет.")
    note_clean = (note or "").strip()
    if len(note_clean) < 3:
        raise ValueError("Укажите причину начисления на русском языке (минимум 3 символа).")
    with get_connection() as conn:
        client = conn.execute(
            "SELECT id, coins FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        if not client:
            raise ValueError("Клиент не найден.")
        conn.execute(
            "UPDATE clients SET coins = coins + ? WHERE id = ?",
            (coins, client_id),
        )
        conn.execute(
            """
            INSERT INTO coin_ledger (client_id, delta, source, admin_id, note)
            VALUES (?, ?, 'admin', ?, ?)
            """,
            (client_id, coins, admin_id, note_clean),
        )
        _insert_admin_audit(
            conn,
            admin_id,
            "add_coins",
            target_type="client",
            target_id=str(client_id),
            detail=f"+{coins} монет. {note_clean}",
        )
        conn.commit()
        return int(
            conn.execute(
                "SELECT coins FROM clients WHERE id = ?", (client_id,)
            ).fetchone()["coins"]
        )


def generate_user_password(length: int = 8) -> str:
    """Пароль из букв и цифр — подходит под правила входа клиента/партнёра."""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(6, length)))


def admin_reset_client_password(admin_id: int, client_id: int) -> str:
    """Генерирует новый пароль, сохраняет хеш, возвращает пароль для передачи клиенту."""
    password = generate_user_password()
    password_hash = generate_password_hash(password)
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE clients SET password_hash = ? WHERE id = ?",
            (password_hash, client_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Клиент не найден.")
        _insert_admin_audit(
            conn,
            admin_id,
            "reset_password",
            target_type="client",
            target_id=str(client_id),
            detail="Пароль сброшен (сгенерирован системой)",
        )
        conn.commit()
    return password


def admin_set_client_blocked(admin_id: int, client_id: int, blocked: bool) -> None:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE clients SET is_blocked = ? WHERE id = ?",
            (1 if blocked else 0, client_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Клиент не найден.")
        action = "block" if blocked else "unblock"
        _insert_admin_audit(
            conn,
            admin_id,
            action,
            target_type="client",
            target_id=str(client_id),
            detail="Доступ заблокирован" if blocked else "Доступ восстановлен",
        )
        conn.commit()


def list_partners_admin() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, business_name, category, contact_name, phone, city, address,
                   comment, spend_coins, COALESCE(is_blocked, 0) AS is_blocked, created_at,
                   website, description, hours
            FROM partners
            ORDER BY id DESC
            """
        ).fetchall()
    return [
        {
            "id": r["id"],
            "business_name": r["business_name"],
            "category": r["category"],
            "contact_name": r["contact_name"],
            "phone": r["phone"],
            "city": r["city"] or "",
            "address": r["address"] or "",
            "comment": r["comment"] or "",
            "website": _row_get(r, "website", ""),
            "description": _row_get(r, "description", ""),
            "hours": _row_get(r, "hours", ""),
            "spend_coins": int(r["spend_coins"] or 2),
            "is_blocked": bool(r["is_blocked"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_partner_admin_detail(partner_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if not row:
            return None
        stats = partner_stats(partner_id)
    return {
        **{
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
            "is_blocked": bool(_row_get(row, "is_blocked", 0)),
            "created_at": row["created_at"],
        },
        "stats": stats,
    }


def admin_reset_partner_password(admin_id: int, partner_id: int) -> str:
    """Генерирует новый пароль, сохраняет хеш, возвращает пароль для передачи партнёру."""
    password = generate_user_password()
    password_hash = generate_password_hash(password)
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE partners SET password_hash = ? WHERE id = ?",
            (password_hash, partner_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Партнёр не найден.")
        _insert_admin_audit(
            conn,
            admin_id,
            "reset_password",
            target_type="partner",
            target_id=str(partner_id),
            detail="Пароль сброшен (сгенерирован системой)",
        )
        conn.commit()
    return password


def admin_set_partner_blocked(admin_id: int, partner_id: int, blocked: bool) -> None:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE partners SET is_blocked = ? WHERE id = ?",
            (1 if blocked else 0, partner_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Партнёр не найден.")
        action = "block" if blocked else "unblock"
        _insert_admin_audit(
            conn,
            admin_id,
            action,
            target_type="partner",
            target_id=str(partner_id),
            detail="Доступ заблокирован" if blocked else "Доступ восстановлен",
        )
        conn.commit()


def list_promos_admin() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.code, p.coins, p.active, p.max_uses, p.used_count,
                   COALESCE(p.comment, '') AS comment,
                   p.created_at,
                   (SELECT COUNT(*) FROM promo_redemptions r WHERE r.code = p.code) AS clients_used
            FROM promo_codes p
            ORDER BY p.created_at DESC, p.code ASC
            """
        ).fetchall()
    return [
        {
            "code": r["code"],
            "coins": int(r["coins"]),
            "active": bool(r["active"]),
            "max_uses": r["max_uses"],
            "used_count": int(r["used_count"] or 0),
            "clients_used": int(r["clients_used"] or 0),
            "comment": r["comment"] or "",
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def create_promo_admin(
    *,
    admin_id: int,
    code: str,
    coins: int,
    comment: str = "",
    max_uses: int | None = None,
) -> dict:
    code_norm = code.strip().upper()
    if not code_norm or len(code_norm) < 3:
        raise ValueError("Промокод: минимум 3 символа.")
    coins = int(coins)
    if coins < 1 or coins > 1000:
        raise ValueError("Монет по промокоду: от 1 до 1000.")
    if max_uses is not None:
        max_uses = int(max_uses)
        if max_uses < 1:
            raise ValueError("Лимит использований должен быть больше 0.")

    with get_connection() as conn:
        exists = conn.execute(
            "SELECT code FROM promo_codes WHERE code = ?", (code_norm,)
        ).fetchone()
        if exists:
            raise ValueError("Такой промокод уже существует.")
        conn.execute(
            """
            INSERT INTO promo_codes (code, coins, active, max_uses, used_count, comment, created_at)
            VALUES (?, ?, 1, ?, 0, ?, datetime('now', 'localtime'))
            """,
            (code_norm, coins, max_uses, (comment or "").strip()),
        )
        _insert_admin_audit(
            conn,
            admin_id,
            "create_promo",
            target_type="promo",
            target_id=code_norm,
            detail=f"+{coins} монет. {(comment or '').strip()}".strip(),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM promo_codes WHERE code = ?", (code_norm,)
        ).fetchone()
    return {
        "code": row["code"],
        "coins": int(row["coins"]),
        "active": bool(row["active"]),
        "max_uses": row["max_uses"],
        "used_count": int(row["used_count"] or 0),
        "clients_used": 0,
        "comment": _row_get(row, "comment", ""),
        "created_at": _row_get(row, "created_at", ""),
    }


def set_promo_active(admin_id: int, code: str, active: bool) -> dict:
    code_norm = code.strip().upper()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE promo_codes SET active = ? WHERE code = ?",
            (1 if active else 0, code_norm),
        )
        if cur.rowcount == 0:
            raise ValueError("Промокод не найден.")
        action = "open_promo" if active else "close_promo"
        _insert_admin_audit(
            conn,
            admin_id,
            action,
            target_type="promo",
            target_id=code_norm,
            detail="Промокод открыт" if active else "Промокод закрыт",
        )
        conn.commit()
    promos = {p["code"]: p for p in list_promos_admin()}
    return promos[code_norm]


def _period_bounds(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    """Нормализует границы периода (даты сервера, локальное время)."""
    from datetime import datetime

    today = datetime.now().date()
    if date_from:
        start = date_from.strip()[:10]
    else:
        start = today.isoformat()
    if date_to:
        end_day = date_to.strip()[:10]
    else:
        end_day = today.isoformat()
    # inclusive end of day
    end = f"{end_day} 23:59:59"
    start_ts = f"{start} 00:00:00"
    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end_day, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Некорректный формат даты. Используйте ГГГГ-ММ-ДД.") from exc
    if start > end_day:
        raise ValueError("Дата «с» не может быть позже даты «по».")
    return start_ts, end


def admin_stats(date_from: str | None = None, date_to: str | None = None) -> dict:
    start_ts, end_ts = _period_bounds(date_from, date_to)
    with get_connection() as conn:
        purchases = conn.execute(
            """
            SELECT
              COALESCE(SUM(coins_added), 0) AS coins_bought,
              COALESCE(SUM(amount), 0) AS cash_rub,
              COUNT(*) AS purchase_count
            FROM coin_orders
            WHERE created_at >= ? AND created_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        spends = conn.execute(
            """
            SELECT
              COALESCE(SUM(coins), 0) AS coins_spent,
              COUNT(*) AS spend_count
            FROM partner_spend_ops
            WHERE created_at >= ? AND created_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        registrations = conn.execute(
            """
            SELECT COUNT(*) AS c FROM clients
            WHERE created_at >= ? AND created_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        partner_regs = conn.execute(
            """
            SELECT COUNT(*) AS c FROM partners
            WHERE created_at >= ? AND created_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        promo_uses = conn.execute(
            """
            SELECT COUNT(*) AS c FROM promo_redemptions
            WHERE created_at >= ? AND created_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        top_partners = conn.execute(
            """
            SELECT
              p.id,
              p.business_name,
              p.city,
              COUNT(o.id) AS ops_count,
              COALESCE(SUM(o.coins), 0) AS coins_total
            FROM partner_spend_ops o
            JOIN partners p ON p.id = o.partner_id
            WHERE o.created_at >= ? AND o.created_at <= ?
            GROUP BY p.id
            ORDER BY coins_total DESC, ops_count DESC
            LIMIT 20
            """,
            (start_ts, end_ts),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM clients) AS clients_total,
              (SELECT COUNT(*) FROM partners) AS partners_total,
              (SELECT COALESCE(SUM(coins), 0) FROM clients) AS coins_in_wallets
            """
        ).fetchone()

    return {
        "period": {"from": start_ts[:10], "to": end_ts[:10]},
        "coins_bought": int(purchases["coins_bought"] or 0),
        "cash_rub": int(purchases["cash_rub"] or 0),
        "purchase_count": int(purchases["purchase_count"] or 0),
        "coins_spent": int(spends["coins_spent"] or 0),
        "spend_count": int(spends["spend_count"] or 0),
        "client_registrations": int(registrations["c"] or 0),
        "partner_registrations": int(partner_regs["c"] or 0),
        "promo_redemptions": int(promo_uses["c"] or 0),
        "clients_total": int(totals["clients_total"] or 0),
        "partners_total": int(totals["partners_total"] or 0),
        "coins_in_wallets": int(totals["coins_in_wallets"] or 0),
        "top_partners": [
            {
                "id": r["id"],
                "business_name": r["business_name"],
                "city": r["city"] or "",
                "ops_count": int(r["ops_count"] or 0),
                "coins_total": int(r["coins_total"] or 0),
            }
            for r in top_partners
        ],
    }


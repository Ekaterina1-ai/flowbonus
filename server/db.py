"""FlowBonus — инициализация SQLite и работа с пользователями."""
from __future__ import annotations

import calendar
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

# На сервере база лежит вне каталога приложения (см. FLOWBONUS_DB_PATH в .env),
# иначе обновление кода через git затрёт рабочие данные.
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "flowbonus.db"
DB_PATH = Path(os.environ.get("FLOWBONUS_DB_PATH") or DEFAULT_DB_PATH).expanduser()

# Версия комплекта юридических документов. Меняется при публикации новой редакции:
# по этому значению видно, какую именно редакцию принял пользователь.
LEGAL_DOCS_VERSION = "2026-09-28-r3"

# Тарифы клубной карты. Привилегии отдельно от карты не продаются, поэтому
# цена есть только у тарифа целиком.
CARD_PLANS = (
    {"code": "m1", "title": "1 месяц", "months": 1, "privileges": 3, "price_rub": 300},
    {"code": "m3", "title": "3 месяца", "months": 3, "privileges": 10, "price_rub": 900},
    {"code": "m6", "title": "6 месяцев", "months": 6, "privileges": 25, "price_rub": 2000},
)
CARD_PLANS_BY_CODE = {plan["code"]: plan for plan in CARD_PLANS}

PROMO_TRIAL_DAYS_DEFAULT = 14
REFERRAL_BONUS_PRIVILEGES = 1
REFERRAL_TRIAL_DAYS = 30
# Бонусные привилегии (промокоды и приглашения) — не больше 40 в календарный год.
BONUS_PRIVILEGES_YEAR_CAP = 40
EXPIRY_REMINDER_DAYS = 7


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
                spend_coins INTEGER NOT NULL DEFAULT 1,
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

            CREATE TABLE IF NOT EXISTS consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_type TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                granted INTEGER NOT NULL,
                docs_version TEXT NOT NULL DEFAULT '',
                ip TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
            CREATE INDEX IF NOT EXISTS idx_consents_subject ON consents(subject_type, subject_id, kind);
            CREATE INDEX IF NOT EXISTS idx_coin_orders_created ON coin_orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_partner_spend_ops_created ON partner_spend_ops(created_at);

            CREATE TABLE IF NOT EXISTS card_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                months INTEGER NOT NULL,
                privileges INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                valid_until TEXT NOT NULL,
                payment_ref TEXT NOT NULL DEFAULT '',
                refunded_amount INTEGER NOT NULL DEFAULT 0,
                refunded_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            -- Пакет привилегий: оплаченный (из тарифа) или бонусный.
            -- Действует, пока активна клубная карта клиента.
            CREATE TABLE IF NOT EXISTS privilege_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                order_id INTEGER,
                total INTEGER NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                price_rub INTEGER NOT NULL DEFAULT 0,
                closed_at TEXT,
                close_reason TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (order_id) REFERENCES card_orders(id)
            );

            CREATE TABLE IF NOT EXISTS privilege_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL,
                partner_id INTEGER,
                admin_id INTEGER,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_card_orders_client ON card_orders(client_id);
            CREATE INDEX IF NOT EXISTS idx_card_orders_created ON card_orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_privilege_lots_client ON privilege_lots(client_id, closed_at);
            CREATE INDEX IF NOT EXISTS idx_privilege_ledger_client ON privilege_ledger(client_id, created_at);
            """
        )
        # миграция колонок профиля партнёра
        partner_cols = {row[1] for row in conn.execute("PRAGMA table_info(partners)").fetchall()}
        for col, ddl in (
            ("website", "TEXT NOT NULL DEFAULT ''"),
            ("description", "TEXT NOT NULL DEFAULT ''"),
            ("hours", "TEXT NOT NULL DEFAULT ''"),
            ("is_blocked", "INTEGER NOT NULL DEFAULT 0"),
            ("privilege_text", "TEXT NOT NULL DEFAULT ''"),
            ("offer_active", "INTEGER NOT NULL DEFAULT 1"),
        ):
            if col not in partner_cols:
                conn.execute(f"ALTER TABLE partners ADD COLUMN {col} {ddl}")

        client_cols = {row[1] for row in conn.execute("PRAGMA table_info(clients)").fetchall()}
        for col, ddl in (
            ("is_blocked", "INTEGER NOT NULL DEFAULT 0"),
            ("card_expires_at", "TEXT"),
            ("ref_code", "TEXT"),
            ("referred_by", "INTEGER"),
            ("referral_rewarded", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col not in client_cols:
                conn.execute(f"ALTER TABLE clients ADD COLUMN {col} {ddl}")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_ref_code ON clients(ref_code)"
        )
        for row in conn.execute("SELECT id FROM clients WHERE ref_code IS NULL").fetchall():
            conn.execute(
                "UPDATE clients SET ref_code = ? WHERE id = ?",
                (_new_ref_code(conn), row["id"]),
            )

        promo_cols = {row[1] for row in conn.execute("PRAGMA table_info(promo_codes)").fetchall()}
        if "trial_days" not in promo_cols:
            conn.execute(
                "ALTER TABLE promo_codes ADD COLUMN trial_days INTEGER NOT NULL "
                f"DEFAULT {PROMO_TRIAL_DAYS_DEFAULT}"
            )
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
        _migrate_coin_balances(conn)
        conn.commit()


def _migrate_coin_balances(conn: sqlite3.Connection) -> None:
    """Однократно переносит остатки прежней версии сервиса в бонусные привилегии."""
    done = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'coins_to_privileges'"
    ).fetchone()
    if done:
        return
    now = _utcnow()
    expires = _fmt(now + timedelta(days=REFERRAL_TRIAL_DAYS))
    note = "Перенос остатка из прежней версии сервиса"
    for row in conn.execute("SELECT id, coins FROM clients WHERE coins > 0").fetchall():
        count = int(row["coins"])
        conn.execute(
            "UPDATE clients SET coins = 0, card_expires_at = ? WHERE id = ?",
            (expires, row["id"]),
        )
        conn.execute(
            """
            INSERT INTO privilege_lots (client_id, kind, source, total, note)
            VALUES (?, 'bonus', 'migration', ?, ?)
            """,
            (row["id"], count, note),
        )
        conn.execute(
            """
            INSERT INTO privilege_ledger (client_id, delta, kind, source, note)
            VALUES (?, ?, 'bonus', 'migration', ?)
            """,
            (row["id"], count, note),
        )
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('coins_to_privileges', ?)",
        (_fmt(now),),
    )


# ---------- Время и клубная карта ----------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("T", " ").replace("Z", ""))
    except ValueError:
        return None


def _iso_utc(value: str | None) -> str | None:
    """Время из БД (UTC) в ISO с суффиксом Z — браузер покажет его в местном поясе."""
    dt = _parse(value)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _add_months(dt: datetime, months: int) -> datetime:
    index = dt.month - 1 + months
    year = dt.year + index // 12
    month = index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _new_ref_code(conn: sqlite3.Connection) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not conn.execute("SELECT 1 FROM clients WHERE ref_code = ?", (code,)).fetchone():
            return code


def card_plans_public() -> list[dict]:
    return [dict(plan) for plan in CARD_PLANS]


def _ledger(
    conn: sqlite3.Connection,
    client_id: int,
    delta: int,
    source: str,
    note: str,
    *,
    kind: str = "",
    partner_id: int | None = None,
    admin_id: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO privilege_ledger (client_id, delta, kind, source, partner_id, admin_id, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (client_id, delta, kind, source, partner_id, admin_id, note),
    )


def _close_expired_card(conn: sqlite3.Connection, client_id: int, now: datetime) -> None:
    """Если срок карты истёк — аннулирует неиспользованные привилегии (ленивая проверка)."""
    row = conn.execute(
        "SELECT card_expires_at FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    expires = _parse(row["card_expires_at"]) if row else None
    if expires is None or expires > now:
        return
    lots = conn.execute(
        """
        SELECT total - used AS left_count FROM privilege_lots
        WHERE client_id = ? AND closed_at IS NULL
        """,
        (client_id,),
    ).fetchall()
    if not lots:
        return
    left = sum(int(lot["left_count"]) for lot in lots)
    conn.execute(
        """
        UPDATE privilege_lots SET closed_at = ?, close_reason = 'expired'
        WHERE client_id = ? AND closed_at IS NULL
        """,
        (_fmt(expires), client_id),
    )
    if left > 0:
        _ledger(
            conn,
            client_id,
            -left,
            "expire",
            "Срок клубной карты истёк, неиспользованные привилегии аннулированы",
        )


def _refund_amount(price_rub: int, total: int, left: int) -> int:
    """Возврат за лот: цена × неиспользованные / всего, с округлением в пользу клиента."""
    if total <= 0 or left <= 0:
        return 0
    return -(-int(price_rub) * int(left) // int(total))


def _card_state(conn: sqlite3.Connection, client_id: int, now: datetime | None = None) -> dict:
    now = now or _utcnow()
    _close_expired_card(conn, client_id, now)
    row = conn.execute(
        "SELECT card_expires_at FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    expires = _parse(row["card_expires_at"]) if row else None
    active = expires is not None and expires > now
    paid = bonus = refund = 0
    if active:
        for lot in conn.execute(
            """
            SELECT kind, total, used, price_rub FROM privilege_lots
            WHERE client_id = ? AND closed_at IS NULL
            """,
            (client_id,),
        ).fetchall():
            left = int(lot["total"]) - int(lot["used"])
            if lot["kind"] == "paid":
                paid += left
                refund += _refund_amount(lot["price_rub"], lot["total"], left)
            else:
                bonus += left
    days_left = 0
    if active:
        days_left = max(1, -(-int((expires - now).total_seconds()) // 86400))
    privileges = paid + bonus
    return {
        "active": active,
        "expires_at": _iso_utc(row["card_expires_at"]) if active else None,
        "days_left": days_left,
        "privileges": privileges,
        "paid_privileges": paid,
        "bonus_privileges": bonus,
        "refund_rub": refund,
        "reminder": active and days_left <= EXPIRY_REMINDER_DAYS and privileges > 0,
    }


def client_card(client_id: int) -> dict:
    with get_connection() as conn:
        state = _card_state(conn, client_id)
        conn.commit()
    return state


def _bonus_granted_this_year(conn: sqlite3.Connection, client_id: int, now: datetime) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(total), 0) AS s FROM privilege_lots
        WHERE client_id = ? AND kind = 'bonus' AND source IN ('promo', 'referral')
          AND strftime('%Y', created_at) = ?
        """,
        (client_id, str(now.year)),
    ).fetchone()
    return int(row["s"] or 0)


def _grant_bonus(
    conn: sqlite3.Connection,
    client_id: int,
    count: int,
    *,
    source: str,
    note: str,
    trial_days: int,
    now: datetime,
) -> tuple[int, bool]:
    """Начисляет бонусные привилегии. Без активной карты открывает пробную.

    Возвращает (начислено, открыта_пробная_карта). Годовой лимит соблюдается.
    """
    room = BONUS_PRIVILEGES_YEAR_CAP - _bonus_granted_this_year(conn, client_id, now)
    count = min(int(count), max(0, room))
    if count <= 0:
        return 0, False
    _close_expired_card(conn, client_id, now)
    row = conn.execute(
        "SELECT card_expires_at FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    expires = _parse(row["card_expires_at"])
    opened_trial = False
    if expires is None or expires <= now:
        conn.execute(
            "UPDATE clients SET card_expires_at = ? WHERE id = ?",
            (_fmt(now + timedelta(days=max(1, int(trial_days)))), client_id),
        )
        opened_trial = True
    conn.execute(
        """
        INSERT INTO privilege_lots (client_id, kind, source, total, note)
        VALUES (?, 'bonus', ?, ?, ?)
        """,
        (client_id, source, count, note),
    )
    _ledger(conn, client_id, count, source, note, kind="bonus")
    return count, opened_trial


def _reward_referral(conn: sqlite3.Connection, client_id: int, now: datetime) -> None:
    """После первой оплаты приглашённого друга — бонус обоим."""
    row = conn.execute(
        "SELECT referred_by, referral_rewarded FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    if not row or not row["referred_by"] or row["referral_rewarded"]:
        return
    conn.execute("UPDATE clients SET referral_rewarded = 1 WHERE id = ?", (client_id,))
    _grant_bonus(
        conn,
        client_id,
        REFERRAL_BONUS_PRIVILEGES,
        source="referral",
        note="Бонус за регистрацию по приглашению друга",
        trial_days=REFERRAL_TRIAL_DAYS,
        now=now,
    )
    inviter = conn.execute(
        "SELECT id, COALESCE(is_blocked, 0) AS is_blocked FROM clients WHERE id = ?",
        (row["referred_by"],),
    ).fetchone()
    if inviter and not inviter["is_blocked"]:
        _grant_bonus(
            conn,
            inviter["id"],
            REFERRAL_BONUS_PRIVILEGES,
            source="referral",
            note="Бонус за приглашённого друга",
            trial_days=REFERRAL_TRIAL_DAYS,
            now=now,
        )


def purchase_card(client_id: int, plan_code: str, payment_ref: str = "") -> dict:
    """Оформляет клубную карту. При действующей карте срок продлевается от даты
    её окончания, а привилегии нового тарифа доступны сразу."""
    plan = CARD_PLANS_BY_CODE.get((plan_code or "").strip())
    if not plan:
        raise ValueError("Выберите тариф клубной карты.")
    now = _utcnow()
    with get_connection() as conn:
        _close_expired_card(conn, client_id, now)
        row = conn.execute(
            "SELECT card_expires_at FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        if not row:
            raise ValueError("Клиент не найден.")
        current = _parse(row["card_expires_at"])
        extended = current is not None and current > now
        new_expires = _add_months(current if extended else now, plan["months"])
        cur = conn.execute(
            """
            INSERT INTO card_orders
                (client_id, plan_code, months, privileges, amount, valid_until, payment_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                plan["code"],
                plan["months"],
                plan["privileges"],
                plan["price_rub"],
                _fmt(new_expires),
                payment_ref,
            ),
        )
        note = f"Клубная карта «{plan['title']}», {plan['price_rub']} ₽"
        conn.execute(
            """
            INSERT INTO privilege_lots
                (client_id, kind, source, order_id, total, price_rub, note)
            VALUES (?, 'paid', 'purchase', ?, ?, ?, ?)
            """,
            (client_id, cur.lastrowid, plan["privileges"], plan["price_rub"], note),
        )
        conn.execute(
            "UPDATE clients SET card_expires_at = ? WHERE id = ?",
            (_fmt(new_expires), client_id),
        )
        _ledger(conn, client_id, plan["privileges"], "purchase", note, kind="paid")
        _reward_referral(conn, client_id, now)
        conn.commit()
    return {
        "plan": dict(plan),
        "extended": extended,
        "valid_until": _iso_utc(_fmt(new_expires)),
        "card": client_card(client_id),
    }


def client_history(client_id: int, limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT delta, kind, source, note, created_at FROM privilege_ledger
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (client_id, max(1, min(200, int(limit)))),
        ).fetchall()
    return [
        {
            "delta": int(r["delta"]),
            "kind": r["kind"],
            "source": r["source"],
            "note": r["note"] or "",
            "created_at": _iso_utc(r["created_at"]),
        }
        for r in rows
    ]


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


CONSENT_KINDS = ("terms", "pd", "marketing")


def record_consents(
    *,
    subject_type: str,
    subject_id: int,
    consents: dict[str, bool],
    ip: str = "",
    user_agent: str = "",
    docs_version: str = LEGAL_DOCS_VERSION,
) -> None:
    """Пишет в журнал факт предоставления или отзыва согласий.

    Журнал только пополняется: отзыв согласия — это новая запись с granted=0,
    поэтому история остаётся доказуемой.
    """
    rows = [
        (
            subject_type,
            int(subject_id),
            kind,
            1 if consents.get(kind) else 0,
            docs_version,
            (ip or "")[:64],
            (user_agent or "")[:512],
        )
        for kind in CONSENT_KINDS
        if kind in consents
    ]
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO consents
                (subject_type, subject_id, kind, granted, docs_version, ip, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def latest_consent(subject_type: str, subject_id: int, kind: str) -> bool:
    """Актуальное состояние согласия — последняя запись в журнале."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT granted FROM consents
            WHERE subject_type = ? AND subject_id = ? AND kind = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (subject_type, int(subject_id), kind),
        ).fetchone()
    return bool(row and row["granted"])


def create_client(
    *,
    fio: str,
    phone: str,
    email: str,
    city: str,
    password: str,
    ref_code: str = "",
) -> sqlite3.Row:
    phone_norm = normalize_phone(phone)
    password_hash = generate_password_hash(password)
    with get_connection() as conn:
        exists_partner = conn.execute(
            "SELECT id FROM partners WHERE phone = ?", (phone_norm,)
        ).fetchone()
        if exists_partner:
            raise ValueError("Этот телефон уже зарегистрирован как партнёр.")

        referred_by = None
        ref_norm = (ref_code or "").strip().upper()
        if ref_norm:
            inviter = conn.execute(
                "SELECT id FROM clients WHERE ref_code = ?", (ref_norm,)
            ).fetchone()
            referred_by = inviter["id"] if inviter else None

        cur = conn.execute(
            """
            INSERT INTO clients
                (fio, phone, email, city, password_hash, selected_city, ref_code, referred_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fio.strip(),
                phone_norm,
                email.strip().lower(),
                city.strip(),
                password_hash,
                city.strip(),
                _new_ref_code(conn),
                referred_by,
            ),
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


def client_public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "fio": row["fio"],
        "phone": row["phone"],
        "email": row["email"],
        "city": row["city"],
        "selected_city": row["selected_city"] or row["city"],
        "ref_code": _row_get(row, "ref_code", ""),
        "card": client_card(row["id"]),
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

        granted, opened_trial = _grant_bonus(
            conn,
            client_id,
            int(promo["coins"]),
            source="promo",
            note=f"Промокод {code_norm}",
            trial_days=int(_row_get(promo, "trial_days", PROMO_TRIAL_DAYS_DEFAULT)),
            now=_utcnow(),
        )
        if not granted:
            raise ValueError(
                "Достигнут годовой лимит бонусных привилегий "
                f"({BONUS_PRIVILEGES_YEAR_CAP} в календарный год)."
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
            (client_id, code_norm, granted),
        )
        conn.commit()

    return {
        "granted": granted,
        "trial_opened": opened_trial,
        "code": code_norm,
        "card": client_card(client_id),
    }


def create_spend_token(client_id: int, ttl_minutes: int = 10) -> dict:
    card = client_card(client_id)
    if not card["active"]:
        raise ValueError("Клубная карта не активна. Оформите карту, чтобы пользоваться привилегиями.")
    if card["privileges"] < 1:
        raise ValueError("На карте не осталось привилегий. Оформите новую карту — привилегии добавятся сразу.")

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
        "card": card,
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
        "privilege_text": _row_get(row, "privilege_text", ""),
        "offer_active": bool(_row_get(row, "offer_active", 1)),
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
                """
                SELECT * FROM partners
                WHERE city = ? AND COALESCE(is_blocked, 0) = 0
                  AND COALESCE(offer_active, 1) = 1
                ORDER BY id ASC
                """,
                (city,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM partners
                WHERE COALESCE(is_blocked, 0) = 0 AND COALESCE(offer_active, 1) = 1
                ORDER BY id ASC
                """
            ).fetchall()
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
                "privilege_text": _row_get(row, "privilege_text", ""),
                "images": paths,
                "image": paths[0] if paths else "/assets/partners/norma-tela.png",
            }
        )
    return result


def public_landing_snapshot() -> dict:
    """Данные для блока «Уже с нами» на лендинге — из живой базы."""
    partners = list_partners_public()
    with get_connection() as conn:
        clients_count = int(
            conn.execute("SELECT COUNT(*) AS c FROM clients").fetchone()["c"] or 0
        )
    return {
        "clients_count": clients_count,
        "partners_count": len(partners),
        "partners": partners,
    }


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
        "comment",
        "business_name",
        "website",
        "description",
        "hours",
        "category",
        "privilege_text",
        "offer_active",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_partner_by_id(partner_id)

    if "privilege_text" in updates:
        updates["privilege_text"] = str(updates["privilege_text"] or "").strip()[:300]
    if "offer_active" in updates:
        updates["offer_active"] = 1 if updates["offer_active"] else 0

    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [partner_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE partners SET {cols} WHERE id = ?", values)
        conn.commit()
        return conn.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()


def partner_stats(partner_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS ops_count FROM partner_spend_ops WHERE partner_id = ?",
            (partner_id,),
        ).fetchone()
        recent = conn.execute(
            """
            SELECT o.created_at, c.fio, c.phone
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
        "recent": [
            {
                "created_at": _iso_utc(r["created_at"]),
                "client_fio": r["fio"],
                "client_phone": r["phone"],
            }
            for r in recent
        ],
    }


def lookup_spend_token(token: str) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT t.*, c.fio, c.phone
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
        expires = _parse(row["expires_at"])
        if expires is not None and _utcnow() > expires:
            raise ValueError("Срок действия QR истёк. Попросите клиента открыть новый QR.")
        card = _card_state(conn, row["client_id"])
        conn.commit()

    if not card["active"]:
        raise ValueError("У клиента нет активной клубной карты.")
    if card["privileges"] < 1:
        raise ValueError("У клиента не осталось привилегий на карте.")

    return {
        "token": row["token"],
        "client_id": row["client_id"],
        "client_fio": row["fio"],
        "client_phone": row["phone"],
        "card_expires_at": card["expires_at"],
        "privileges": card["privileges"],
        "expires_at": row["expires_at"],
    }


def redeem_spend_token(*, partner_id: int, token: str) -> dict:
    """Подтверждение привилегии: расходуется ровно одна привилегия.

    Сначала бонусные, затем оплаченные — в порядке оформления.
    """
    info = lookup_spend_token(token)
    client_id = info["client_id"]

    with get_connection() as conn:
        row = conn.execute(
            "SELECT used FROM spend_tokens WHERE token = ?", (token,)
        ).fetchone()
        if not row or row["used"]:
            raise ValueError("Этот QR уже был использован.")

        partner = conn.execute(
            "SELECT business_name FROM partners WHERE id = ?", (partner_id,)
        ).fetchone()
        lot = conn.execute(
            """
            SELECT id, kind FROM privilege_lots
            WHERE client_id = ? AND closed_at IS NULL AND used < total
            ORDER BY CASE kind WHEN 'bonus' THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (client_id,),
        ).fetchone()
        if not lot:
            raise ValueError("У клиента не осталось привилегий на карте.")

        cur = conn.execute(
            "UPDATE privilege_lots SET used = used + 1 WHERE id = ? AND used < total",
            (lot["id"],),
        )
        if not cur.rowcount:
            raise ValueError("Не удалось подтвердить привилегию. Повторите сканирование.")

        conn.execute("UPDATE spend_tokens SET used = 1 WHERE token = ?", (token,))
        conn.execute(
            """
            INSERT INTO partner_spend_ops (partner_id, client_id, token, coins)
            VALUES (?, ?, ?, 1)
            """,
            (partner_id, client_id, token),
        )
        name = partner["business_name"] if partner else f"#{partner_id}"
        _ledger(
            conn,
            client_id,
            -1,
            "spend",
            f"Привилегия у партнёра «{name}»",
            kind=lot["kind"],
            partner_id=partner_id,
        )
        conn.commit()

    return {
        "ok": True,
        "client_fio": info["client_fio"],
        "privileges_left": client_card(client_id)["privileges"],
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
    "add_coins": "Начисление (прежняя версия сервиса)",
    "add_privileges": "Начисление привилегий",
    "refund_card": "Возврат за клубную карту",
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
            SELECT c.id, c.fio, c.phone, c.email, c.city, c.selected_city,
                   c.card_expires_at,
                   CASE WHEN c.card_expires_at > datetime('now') THEN (
                       SELECT COALESCE(SUM(l.total - l.used), 0) FROM privilege_lots l
                       WHERE l.client_id = c.id AND l.closed_at IS NULL
                   ) ELSE 0 END AS privileges,
                   COALESCE(c.is_blocked, 0) AS is_blocked, c.created_at
            FROM clients c
            ORDER BY c.id DESC
            """
        ).fetchall()
    now = _utcnow()
    result = []
    for r in rows:
        expires = _parse(r["card_expires_at"])
        active = expires is not None and expires > now
        result.append(
            {
                "id": r["id"],
                "fio": r["fio"],
                "phone": r["phone"],
                "email": r["email"],
                "city": r["city"],
                "selected_city": r["selected_city"] or r["city"],
                "card_active": active,
                "card_expires_at": _iso_utc(r["card_expires_at"]) if active else None,
                "privileges": int(r["privileges"] or 0),
                "is_blocked": bool(r["is_blocked"]),
                "created_at": r["created_at"],
            }
        )
    return result


def get_client_admin_detail(client_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, fio, phone, email, city, selected_city, referred_by,
                   COALESCE(is_blocked, 0) AS is_blocked, created_at
            FROM clients WHERE id = ?
            """,
            (client_id,),
        ).fetchone()
        if not row:
            return None
        card = _card_state(conn, client_id)
        conn.commit()
        ledger = conn.execute(
            """
            SELECT id, delta, kind, source, note, created_at, admin_id
            FROM privilege_ledger
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT 100
            """,
            (client_id,),
        ).fetchall()
        orders = conn.execute(
            """
            SELECT id, plan_code, months, privileges, amount, valid_until,
                   refunded_amount, refunded_at, created_at
            FROM card_orders
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
        invited = conn.execute(
            "SELECT COUNT(*) AS c FROM clients WHERE referred_by = ?", (client_id,)
        ).fetchone()
    return {
        "id": row["id"],
        "fio": row["fio"],
        "phone": row["phone"],
        "email": row["email"],
        "city": row["city"],
        "selected_city": row["selected_city"] or row["city"],
        "is_blocked": bool(row["is_blocked"]),
        "created_at": row["created_at"],
        "referred_by": row["referred_by"],
        "invited_count": int(invited["c"] or 0),
        "card": card,
        "ledger": [
            {
                "id": r["id"],
                "delta": int(r["delta"]),
                "kind": r["kind"],
                "source": r["source"],
                "note": r["note"] or "",
                "created_at": r["created_at"],
                "admin_id": r["admin_id"],
            }
            for r in ledger
        ],
        "orders": [
            {
                "id": r["id"],
                "plan_title": CARD_PLANS_BY_CODE.get(r["plan_code"], {}).get("title", r["plan_code"]),
                "privileges": int(r["privileges"]),
                "amount": int(r["amount"]),
                "valid_until": r["valid_until"],
                "refunded_amount": int(r["refunded_amount"] or 0),
                "refunded_at": r["refunded_at"],
                "created_at": r["created_at"],
            }
            for r in orders
        ],
        "promos": [
            {
                "code": r["code"],
                "privileges": int(r["coins"]),
                "created_at": r["created_at"],
            }
            for r in promos
        ],
    }


def admin_add_client_privileges(
    *,
    admin_id: int,
    client_id: int,
    privileges: int,
    days: int = 0,
    note: str = "",
) -> dict:
    """Компенсация по обращению: бонусные привилегии и (или) продление карты."""
    privileges = int(privileges or 0)
    days = int(days or 0)
    if privileges < 0 or privileges > 100:
        raise ValueError("Привилегий: от 0 до 100.")
    if days < 0 or days > 365:
        raise ValueError("Продление: от 0 до 365 дней.")
    if not privileges and not days:
        raise ValueError("Укажите число привилегий или дней продления.")
    note_clean = (note or "").strip()
    if len(note_clean) < 3:
        raise ValueError("Укажите причину начисления на русском языке (минимум 3 символа).")
    now = _utcnow()
    with get_connection() as conn:
        client = conn.execute(
            "SELECT id, card_expires_at FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        if not client:
            raise ValueError("Клиент не найден.")
        _close_expired_card(conn, client_id, now)
        expires = _parse(client["card_expires_at"])
        active = expires is not None and expires > now
        if days:
            new_expires = (expires if active else now) + timedelta(days=days)
            conn.execute(
                "UPDATE clients SET card_expires_at = ? WHERE id = ?",
                (_fmt(new_expires), client_id),
            )
            active = True
        if privileges:
            if not active:
                raise ValueError(
                    "Клубная карта не активна — укажите, на сколько дней её открыть."
                )
            conn.execute(
                """
                INSERT INTO privilege_lots (client_id, kind, source, total, note)
                VALUES (?, 'bonus', 'admin', ?, ?)
                """,
                (client_id, privileges, note_clean),
            )
        _ledger(
            conn,
            client_id,
            privileges,
            "admin",
            note_clean + (f" (карта продлена на {days} дн.)" if days else ""),
            kind="bonus" if privileges else "",
            admin_id=admin_id,
        )
        parts = []
        if privileges:
            parts.append(f"+{privileges} привилегий")
        if days:
            parts.append(f"+{days} дн. к карте")
        _insert_admin_audit(
            conn,
            admin_id,
            "add_privileges",
            target_type="client",
            target_id=str(client_id),
            detail=f"{', '.join(parts)}. {note_clean}",
        )
        conn.commit()
    return client_card(client_id)


def admin_refund_client_card(*, admin_id: int, client_id: int, note: str = "") -> dict:
    """Отказ клиента от клубной карты: возврат за неиспользованные оплаченные привилегии."""
    now = _utcnow()
    with get_connection() as conn:
        if not conn.execute("SELECT id FROM clients WHERE id = ?", (client_id,)).fetchone():
            raise ValueError("Клиент не найден.")
        card = _card_state(conn, client_id, now)
        if not card["active"]:
            raise ValueError("У клиента нет действующей клубной карты.")
        lots = conn.execute(
            """
            SELECT id, kind, order_id, total, used, price_rub FROM privilege_lots
            WHERE client_id = ? AND closed_at IS NULL
            """,
            (client_id,),
        ).fetchall()
        refund_total = 0
        left_total = 0
        for lot in lots:
            left = int(lot["total"]) - int(lot["used"])
            left_total += left
            if lot["kind"] != "paid":
                continue
            amount = _refund_amount(lot["price_rub"], lot["total"], left)
            refund_total += amount
            if lot["order_id"] and amount:
                conn.execute(
                    """
                    UPDATE card_orders
                    SET refunded_amount = refunded_amount + ?, refunded_at = ?
                    WHERE id = ?
                    """,
                    (amount, _fmt(now), lot["order_id"]),
                )
        conn.execute(
            """
            UPDATE privilege_lots SET closed_at = ?, close_reason = 'refund'
            WHERE client_id = ? AND closed_at IS NULL
            """,
            (_fmt(now), client_id),
        )
        conn.execute(
            "UPDATE clients SET card_expires_at = ? WHERE id = ?", (_fmt(now), client_id)
        )
        note_clean = (note or "").strip()
        _ledger(
            conn,
            client_id,
            -left_total,
            "refund",
            f"Отказ от клубной карты, возврат {refund_total} ₽"
            + (f". {note_clean}" if note_clean else ""),
            admin_id=admin_id,
        )
        _insert_admin_audit(
            conn,
            admin_id,
            "refund_card",
            target_type="client",
            target_id=str(client_id),
            detail=f"Возврат {refund_total} ₽, закрыто привилегий: {left_total}. {note_clean}".strip(),
        )
        conn.commit()
    return {"refund_rub": refund_total, "privileges_closed": left_total}


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
                   comment, COALESCE(is_blocked, 0) AS is_blocked, created_at,
                   website, description, hours, privilege_text,
                   COALESCE(offer_active, 1) AS offer_active
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
            "privilege_text": _row_get(r, "privilege_text", ""),
            "offer_active": bool(r["offer_active"]),
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
            "privilege_text": _row_get(row, "privilege_text", ""),
            "offer_active": bool(_row_get(row, "offer_active", 1)),
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
            SELECT p.code, p.coins, p.trial_days, p.active, p.max_uses, p.used_count,
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
            "privileges": int(r["coins"]),
            "trial_days": int(r["trial_days"] or PROMO_TRIAL_DAYS_DEFAULT),
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
    privileges: int,
    trial_days: int = PROMO_TRIAL_DAYS_DEFAULT,
    comment: str = "",
    max_uses: int | None = None,
) -> dict:
    code_norm = code.strip().upper()
    if not code_norm or len(code_norm) < 3:
        raise ValueError("Промокод: минимум 3 символа.")
    privileges = int(privileges)
    if privileges < 1 or privileges > BONUS_PRIVILEGES_YEAR_CAP:
        raise ValueError(f"Привилегий по промокоду: от 1 до {BONUS_PRIVILEGES_YEAR_CAP}.")
    trial_days = int(trial_days or PROMO_TRIAL_DAYS_DEFAULT)
    if trial_days < 1 or trial_days > 90:
        raise ValueError("Срок пробной карты: от 1 до 90 дней.")
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
            INSERT INTO promo_codes
                (code, coins, trial_days, active, max_uses, used_count, comment, created_at)
            VALUES (?, ?, ?, 1, ?, 0, ?, datetime('now', 'localtime'))
            """,
            (code_norm, privileges, trial_days, max_uses, (comment or "").strip()),
        )
        _insert_admin_audit(
            conn,
            admin_id,
            "create_promo",
            target_type="promo",
            target_id=code_norm,
            detail=(
                f"+{privileges} привилегий, пробная карта {trial_days} дн. "
                f"{(comment or '').strip()}"
            ).strip(),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM promo_codes WHERE code = ?", (code_norm,)
        ).fetchone()
    return {
        "code": row["code"],
        "privileges": int(row["coins"]),
        "trial_days": int(row["trial_days"]),
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
              COALESCE(SUM(privileges), 0) AS privileges_sold,
              COALESCE(SUM(amount), 0) AS cash_rub,
              COUNT(*) AS cards_sold
            FROM card_orders
            WHERE created_at >= ? AND created_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        refunds = conn.execute(
            """
            SELECT COALESCE(SUM(refunded_amount), 0) AS refunded_rub
            FROM card_orders
            WHERE refunded_at >= ? AND refunded_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        bonus = conn.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS bonus_granted
            FROM privilege_lots
            WHERE kind = 'bonus' AND created_at >= ? AND created_at <= ?
            """,
            (start_ts, end_ts),
        ).fetchone()
        spends = conn.execute(
            """
            SELECT COUNT(*) AS privileges_used
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
              COUNT(o.id) AS ops_count
            FROM partner_spend_ops o
            JOIN partners p ON p.id = o.partner_id
            WHERE o.created_at >= ? AND o.created_at <= ?
            GROUP BY p.id
            ORDER BY ops_count DESC
            LIMIT 20
            """,
            (start_ts, end_ts),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM clients) AS clients_total,
              (SELECT COUNT(*) FROM partners) AS partners_total,
              (SELECT COUNT(*) FROM clients WHERE card_expires_at > datetime('now')) AS active_cards,
              (SELECT COALESCE(SUM(l.total - l.used), 0)
                 FROM privilege_lots l JOIN clients c ON c.id = l.client_id
                 WHERE l.closed_at IS NULL AND c.card_expires_at > datetime('now')
              ) AS privileges_available
            """
        ).fetchone()

    return {
        "period": {"from": start_ts[:10], "to": end_ts[:10]},
        "cards_sold": int(purchases["cards_sold"] or 0),
        "cash_rub": int(purchases["cash_rub"] or 0),
        "refunded_rub": int(refunds["refunded_rub"] or 0),
        "privileges_sold": int(purchases["privileges_sold"] or 0),
        "bonus_granted": int(bonus["bonus_granted"] or 0),
        "privileges_used": int(spends["privileges_used"] or 0),
        "client_registrations": int(registrations["c"] or 0),
        "partner_registrations": int(partner_regs["c"] or 0),
        "promo_redemptions": int(promo_uses["c"] or 0),
        "clients_total": int(totals["clients_total"] or 0),
        "partners_total": int(totals["partners_total"] or 0),
        "active_cards": int(totals["active_cards"] or 0),
        "privileges_available": int(totals["privileges_available"] or 0),
        "top_partners": [
            {
                "id": r["id"],
                "business_name": r["business_name"],
                "city": r["city"] or "",
                "ops_count": int(r["ops_count"] or 0),
            }
            for r in top_partners
        ],
    }


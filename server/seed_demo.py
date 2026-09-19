"""FlowBonus — тестовые данные для свежей базы.

Идемпотентно: повторный запуск обновляет профиль, а не создаёт дубли.
Пароль берётся только из окружения, в репозитории его нет.

    DEMO_PARTNER_PASSWORD=... python seed_demo.py

Необязательно, чтобы завести и тестового клиента:

    DEMO_PARTNER_PASSWORD=... DEMO_CLIENT_PASSWORD=... python seed_demo.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from db import (
    add_partner_image,
    create_client,
    create_partner,
    get_client_by_phone,
    get_partner_by_phone,
    init_db,
    list_partner_images,
    partner_public,
    update_partner_profile,
)

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.environ.get("FLOWBONUS_UPLOAD_DIR") or (ROOT / "assets" / "partners")).expanduser()

PARTNER_PHONE = "+79178409090"
CLIENT_PHONE = "+79001112233"

PARTNER_PROFILE = {
    "business_name": "Норма Тела",
    "category": "Салон красоты",
    "city": "Волгоград",
    "address": "бульвар 30-летия Победы, 19В, район Семь Ветров",
    "hours": "Пн–Вс: 10:00–21:00",
    "website": "https://норма-тела.рф/",
    "description": (
        "Салон красоты в Волгограде. Услуги для лица и тела, "
        "комфортная атмосфера и удобный график работы."
    ),
    "comment": "",
    "spend_coins": 2,
}


def seed_partner(password: str) -> None:
    partner = get_partner_by_phone(PARTNER_PHONE)
    if partner is None:
        partner = create_partner(
            business_name=PARTNER_PROFILE["business_name"],
            category=PARTNER_PROFILE["category"],
            contact_name="Екатерина",
            phone=PARTNER_PHONE,
            password=password,
            city=PARTNER_PROFILE["city"],
            address=PARTNER_PROFILE["address"],
        )
        print(f"создан партнёр id={partner['id']}")
    else:
        print(f"партнёр уже есть, id={partner['id']} — обновляем профиль")

    update_partner_profile(partner["id"], **PARTNER_PROFILE)

    if not list_partner_images(partner["id"]):
        src = ROOT / "assets" / "partners" / "norma-tela.png"
        if src.is_file():
            dest_dir = UPLOAD_DIR / f"p{partner['id']}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest_dir / "cover.png")
            add_partner_image(partner["id"], f"/assets/partners/p{partner['id']}/cover.png")
            print("добавлена обложка")
        else:
            print(f"пропускаем обложку: нет файла {src}")

    print(partner_public(get_partner_by_phone(PARTNER_PHONE)))


def seed_client(password: str) -> None:
    if get_client_by_phone(CLIENT_PHONE):
        print("тестовый клиент уже есть")
        return
    client = create_client(
        fio="Тест Клиент",
        phone=CLIENT_PHONE,
        email="test@flowbonus.ru",
        city="Волгоград",
        password=password,
    )
    print(f"создан клиент id={client['id']}")


def main() -> int:
    partner_password = os.environ.get("DEMO_PARTNER_PASSWORD", "")
    if not partner_password:
        print(
            "Задайте DEMO_PARTNER_PASSWORD (минимум 6 символов, буквы или цифры).",
            file=sys.stderr,
        )
        return 1

    init_db()
    seed_partner(partner_password)

    client_password = os.environ.get("DEMO_CLIENT_PASSWORD", "")
    if client_password:
        seed_client(client_password)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

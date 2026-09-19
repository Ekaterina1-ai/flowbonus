from pathlib import Path
import shutil
from db import (
    init_db,
    get_connection,
    get_partner_by_phone,
    add_partner_image,
    list_partner_images,
    update_partner_profile,
    partner_public,
)

init_db()
ROOT = Path(__file__).resolve().parent.parent

with get_connection() as conn:
    conn.execute(
        "DELETE FROM partner_images WHERE partner_id IN (SELECT id FROM partners WHERE phone = ?)",
        ("79002223344",),
    )
    conn.execute(
        "DELETE FROM partner_spend_ops WHERE partner_id IN (SELECT id FROM partners WHERE phone = ?)",
        ("79002223344",),
    )
    conn.execute("DELETE FROM partners WHERE phone = ?", ("79002223344",))
    conn.commit()

p = get_partner_by_phone("+79178409090")
print("partner id", p["id"])
update_partner_profile(
    p["id"],
    business_name="Норма Тела",
    category="Салон красоты",
    city="Волгоград",
    address="бульвар 30-летия Победы, 19В, район Семь Ветров",
    hours="Пн–Вс: 10:00–21:00",
    website="https://норма-тела.рф/",
    description="Салон красоты в Волгограде. Услуги для лица и тела, комфортная атмосфера и удобный график работы.",
    comment="",
    spend_coins=2,
)

if not list_partner_images(p["id"]):
    src = ROOT / "assets" / "partners" / "norma-tela.png"
    dest_dir = ROOT / "assets" / "partners" / f"p{p['id']}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "cover.png"
    shutil.copyfile(src, dest)
    add_partner_image(p["id"], f"/assets/partners/p{p['id']}/cover.png")

print(partner_public(get_partner_by_phone("+79178409090")))

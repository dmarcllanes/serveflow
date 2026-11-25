"""Create (or reset) a store from a seed JSON file.

    uv run python seed_client.py seeds/demo-resto.json            # create
    uv run python seed_client.py seeds/demo-resto.json --reset    # delete & recreate (DESTROYS orders)
    uv run python seed_client.py seeds/demo-resto.json --password 's3cret-pass'

Prices in the JSON are in pesos. The admin password comes from --password, then the
seed's "admin_password", then ADMIN_PASSWORD env, else a random one is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys

import db


def cents(v) -> int:
    return int(round(float(v or 0) * 100))


def seed(path: str, reset: bool = False, password: str | None = None) -> None:
    data = json.load(open(path, encoding="utf-8"))
    store = data["store"]
    if not db.STORE_RE.match(store):
        sys.exit(f"Invalid store slug {store!r}: use lowercase letters, digits and dashes.")
    p = db.db_path(store)
    if p.exists():
        if not reset:
            sys.exit(f"{p} already exists. Use --reset to delete and recreate it (destroys orders).")
        db.close_store(store)
        for suffix in ("", "-wal", "-shm"):
            fp = p.with_name(p.name + suffix)
            if fp.exists():
                fp.unlink()
    con = db.get_db(store, create=True)

    settings = {k: v for k, v in data.get("settings", {}).items() if k != "admin_pw"}
    db.set_settings(con, settings)
    populate(con, data)

    pw = password or data.get("admin_password") or os.environ.get("ADMIN_PASSWORD")
    generated = not pw
    pw = pw or secrets.token_urlsafe(10)
    db.set_admin_password(con, pw)

    n_items = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"✓ Seeded {store!r} → {p} ({n_items} items)")
    print(f"  Storefront: http://{store}.localhost:5001   Admin: http://{store}.localhost:5001/admin")
    if generated:
        print(f"  Admin password (save it now): {pw}")


def populate(con, data: dict) -> None:
    """Load categories/items (prices in pesos) and delivery zones from seed-shaped data."""
    for ci, cat in enumerate(data.get("categories", [])):
        cid = db.upsert_category(con, cat["name"], sort=ci)
        for ii, it in enumerate(cat.get("items", [])):
            db.save_item(con, {
                "category_id": cid, "name": it["name"], "description": it.get("description", ""),
                "price_cents": cents(it["price"]), "tags": it.get("tags", []), "allergens": it.get("allergens", []),
                "daily_portions": it.get("daily_portions"), "active": it.get("active", True), "sort": ii,
                "variants": [{"name": v["name"], "price_delta_cents": cents(v.get("add", 0))}
                             for v in it.get("variants", [])],
                "groups": [{"name": g["name"], "min_select": g.get("min", 0), "max_select": g.get("max", 1),
                            "options": [{"name": o["name"], "price_delta_cents": cents(o.get("add", 0))}
                                        for o in g["options"]]} for g in it.get("modifier_groups", [])],
            })
    for z in data.get("delivery_zones", []):
        db.save_zone(con, z["name"], cents(z["fee"]), cents(z.get("min_order", 0)), int(z.get("eta_minutes", 45)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seed_file")
    ap.add_argument("--reset", action="store_true", help="delete the existing store DB first")
    ap.add_argument("--password", help="admin password (min 8 chars)")
    a = ap.parse_args()
    seed(a.seed_file, a.reset, a.password)

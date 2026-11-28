"""Schema, migrations, reads and ALL writes for a ServeFlow store.

One SQLite file per store (data/<store>.db). Connections are autocommit
(isolation_level=None); every write that must be consistent runs inside
`tx(con)` which issues BEGIN IMMEDIATE.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
TZ = ZoneInfo(os.environ.get("STORE_TZ", "Asia/Manila"))
STORE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
# Subdomains a self-serve signup may never claim.
RESERVED_STORES = frozenset("""
www admin api app apps mail smtp imap pop ftp static assets cdn media img images help support status blog docs
dashboard signup login logout register account accounts billing pay payment payments biteflow serveflow demo test staging dev
root ns ns1 ns2 mx email secure store stores shop owner kitchen order orders _tls_check healthz posts
""".split())

MODES = ("dine_in", "pickup", "delivery", "cod")
MODE_LABEL = {"dine_in": "Dine-in", "pickup": "Pickup", "delivery": "Delivery", "cod": "Cash on Delivery"}
PAYMENTS = ("gcash", "bank", "counter", "cod")
PAY_LABEL = {"gcash": "GCash", "bank": "Bank transfer", "counter": "Pay at counter", "cod": "Cash on delivery"}
STATUSES = ("pending_payment", "preparing", "ready", "out_for_delivery", "completed", "cancelled")
STATUS_LABEL = {
    "pending_payment": "Awaiting payment",
    "preparing": "Preparing",
    "ready": "Ready",
    "out_for_delivery": "Out for delivery",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
DELIVERY_MODES = ("delivery", "cod")
MAX_QTY = 50


class OrderError(ValueError):
    """User-facing validation error (safe to show)."""


# ---------------------------------------------------------------- connections

def now() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def db_path(store: str) -> Path:
    return DATA_DIR / f"{store}.db"


def upload_dir(store: str, kind: str) -> Path:
    p = DATA_DIR / "uploads" / store / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def store_exists(store: str | None) -> bool:
    return bool(store) and bool(STORE_RE.match(store)) and db_path(store).exists()


def store_name_problem(store: str) -> str | None:
    """Why `store` can't be claimed by a new signup, or None if it's free."""
    if not 3 <= len(store or "") <= 30 or not STORE_RE.match(store):
        return "Use 3–30 lowercase letters, numbers or dashes."
    if store in RESERVED_STORES:
        return "That name is reserved."
    if db_path(store).exists():
        return "That link is already taken."
    return None


def claim_store(store: str) -> sqlite3.Connection:
    """Atomically create a brand-new store DB. Raises FileExistsError if the name was taken
    (O_EXCL makes two simultaneous signups for the same name safe)."""
    if not STORE_RE.match(store or ""):
        raise LookupError(store)
    p = db_path(store)
    p.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640))
    return get_db(store, create=True)


def delete_store_files(store: str) -> None:
    """Remove a store's DB files (used to roll back a failed signup)."""
    close_store(store)
    p = db_path(store)
    for suffix in ("", "-wal", "-shm"):
        fp = p.with_name(p.name + suffix)
        if fp.exists():
            fp.unlink()


_local = threading.local()


def get_db(store: str, create: bool = False) -> sqlite3.Connection:
    """Thread-local cached autocommit connection for a store."""
    if not STORE_RE.match(store or ""):
        raise LookupError(store)
    cache = getattr(_local, "cons", None)
    if cache is None:
        cache = _local.cons = {}
    con = cache.get(store)
    if con is None:
        p = db_path(store)
        if not create and not p.exists():
            raise LookupError(store)
        p.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(p, isolation_level=None, timeout=10, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("PRAGMA synchronous=NORMAL")
        migrate(con)
        cache[store] = con
    return con


def close_store(store: str) -> None:
    cache = getattr(_local, "cons", None) or {}
    con = cache.pop(store, None)
    if con:
        con.close()


@contextmanager
def tx(con: sqlite3.Connection):
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


# ---------------------------------------------------------------- migrations

MIGRATIONS = [
    """
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE categories(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL,
        sort INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE items(
        id INTEGER PRIMARY KEY,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
        image TEXT, tags TEXT NOT NULL DEFAULT '[]', allergens TEXT NOT NULL DEFAULT '[]',
        sold_out INTEGER NOT NULL DEFAULT 0,
        daily_portions INTEGER CHECK(daily_portions IS NULL OR daily_portions >= 0),
        remaining INTEGER CHECK(remaining IS NULL OR remaining >= 0),
        active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX items_cat ON items(category_id, sort);
    CREATE TABLE variants(
        id INTEGER PRIMARY KEY,
        item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        name TEXT NOT NULL, price_delta_cents INTEGER NOT NULL DEFAULT 0,
        sort INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE modifier_groups(
        id INTEGER PRIMARY KEY,
        item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        min_select INTEGER NOT NULL DEFAULT 0 CHECK(min_select >= 0),
        max_select INTEGER NOT NULL DEFAULT 1 CHECK(max_select >= 1),
        sort INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE modifiers(
        id INTEGER PRIMARY KEY,
        group_id INTEGER NOT NULL REFERENCES modifier_groups(id) ON DELETE CASCADE,
        name TEXT NOT NULL, price_delta_cents INTEGER NOT NULL DEFAULT 0,
        sort INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE delivery_zones(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL,
        fee_cents INTEGER NOT NULL DEFAULT 0 CHECK(fee_cents >= 0),
        min_order_cents INTEGER NOT NULL DEFAULT 0, eta_minutes INTEGER NOT NULL DEFAULT 45,
        active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE customers(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE,
        address TEXT NOT NULL DEFAULT '', orders_count INTEGER NOT NULL DEFAULT 0,
        total_spent_cents INTEGER NOT NULL DEFAULT 0,
        first_order_at TEXT, last_order_at TEXT);
    CREATE TABLE orders(
        id INTEGER PRIMARY KEY, token TEXT NOT NULL UNIQUE, code TEXT NOT NULL DEFAULT '',
        customer_id INTEGER REFERENCES customers(id),
        customer_name TEXT NOT NULL, phone TEXT NOT NULL,
        mode TEXT NOT NULL CHECK(mode IN ('dine_in','pickup','delivery','cod')),
        table_no TEXT, address TEXT, zone_id INTEGER, zone_name TEXT,
        delivery_fee_cents INTEGER NOT NULL DEFAULT 0,
        subtotal_cents INTEGER NOT NULL, total_cents INTEGER NOT NULL,
        payment_method TEXT NOT NULL CHECK(payment_method IN ('gcash','bank','counter','cod')),
        payment_status TEXT NOT NULL CHECK(payment_status IN ('unpaid','submitted','verified','rejected','collect')),
        payment_ref TEXT, proof_path TEXT, payment_note TEXT,
        status TEXT NOT NULL CHECK(status IN
            ('pending_payment','preparing','ready','out_for_delivery','completed','cancelled')),
        scheduled_for TEXT, notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX orders_status ON orders(status, created_at);
    CREATE INDEX orders_created ON orders(created_at);
    CREATE TABLE order_items(
        id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        item_id INTEGER, name TEXT NOT NULL, variant_name TEXT,
        modifiers TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '',
        qty INTEGER NOT NULL CHECK(qty > 0),
        unit_price_cents INTEGER NOT NULL, line_total_cents INTEGER NOT NULL);
    CREATE TABLE order_events(
        id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        from_status TEXT, to_status TEXT, note TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
    CREATE TABLE ai_proposals(
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
        summary TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','confirmed','dismissed','failed')),
        result TEXT, created_at TEXT NOT NULL, decided_at TEXT);
    CREATE TABLE chat_threads(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, messages TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL);
    """,
    # 2: portions_held = 1 when the order took its portions out of items.remaining (every order
    # until now). Orders for a later day are 0 until reset_daily_portions on that day takes them.
    """
    ALTER TABLE orders ADD COLUMN portions_held INTEGER NOT NULL DEFAULT 1;
    CREATE INDEX orders_sched ON orders(scheduled_for);
    """,
]


def migrate(con: sqlite3.Connection) -> None:
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    for i, script in enumerate(MIGRATIONS[ver:], start=ver + 1):
        con.execute("BEGIN IMMEDIATE")
        try:
            # re-check inside the lock (another process may have migrated)
            if con.execute("PRAGMA user_version").fetchone()[0] >= i:
                con.execute("COMMIT")
                continue
            for stmt in [s for s in script.split(";") if s.strip()]:
                con.execute(stmt)
            con.execute(f"PRAGMA user_version={i}")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise


# ---------------------------------------------------------------- settings

DEFAULT_SETTINGS = {
    "name": "My Kitchen",
    "tagline": "Order online — 0% commission",
    "brand_color": "#c2410c",
    "accent_color": "#fef3c7",
    "logo": "",
    "announcement": "",
    "address": "",
    "contact_phone": "",
    "modes": ["dine_in", "pickup", "delivery", "cod"],
    "payments": ["gcash", "bank", "counter"],
    "gcash_name": "",
    "gcash_number": "",
    "bank_details": "",
    "prep_minutes": 20,
    "slot_minutes": 30,
    # weekday (0=Mon) -> ["HH:MM", "HH:MM"] or null when closed
    "hours": {str(d): ["08:00", "20:00"] for d in range(7)},
    "accepting_orders": True,
    # GCash / bank orders with no payment proof are cancelled (portions released) after this long
    "payment_window_minutes": 30,
}


def get_settings(con) -> dict:
    s = dict(DEFAULT_SETTINGS)
    for r in con.execute("SELECT key, value FROM settings"):
        if r["key"] == "admin_pw" or r["key"].startswith("_"):  # secrets & private owner data
            continue
        try:
            s[r["key"]] = json.loads(r["value"])
        except ValueError:
            s[r["key"]] = r["value"]
    return s


def set_settings(con, values: dict) -> None:
    with tx(con):
        for k, v in values.items():
            con.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, json.dumps(v)),
            )


def _hash_pw(pw: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()


def session_version(con) -> int:
    """Bumped on every password change. An admin session is only valid while its saved version
    matches, so changing the password logs out every other device."""
    return int(get_private(con, "session_ver") or 0)


def set_admin_password(con, pw: str) -> int:
    """Set the owner password and log out all existing sessions. Returns the new session version."""
    if not 8 <= len(pw or "") <= 128:
        raise OrderError("Password must be 8–128 characters.")
    salt = secrets.token_bytes(16)
    with tx(con):
        con.execute(
            "INSERT INTO settings(key, value) VALUES('admin_pw', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(salt.hex() + "$" + _hash_pw(pw, salt)),),
        )
        r = con.execute("SELECT value FROM settings WHERE key='_session_ver'").fetchone()
        ver = int(json.loads(r["value"]) if r else 0) + 1
        con.execute("INSERT INTO settings(key, value) VALUES('_session_ver', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(ver),))
    return ver


def change_admin_password(con, current: str, new: str, confirm: str) -> int:
    """Owner-initiated change from the admin. Raises OrderError with a message to show."""
    if not check_admin_password(con, current or ""):
        raise OrderError("Your current password is wrong.")
    if new != confirm:
        raise OrderError("The two new passwords don't match.")
    if new == current:
        raise OrderError("Choose a password different from the current one.")
    return set_admin_password(con, new)


def check_admin_password(con, pw: str) -> bool:
    r = con.execute("SELECT value FROM settings WHERE key='admin_pw'").fetchone()
    if not r:
        return False
    salt_hex, digest = json.loads(r["value"]).split("$", 1)
    return hmac.compare_digest(_hash_pw(pw, bytes.fromhex(salt_hex)), digest)


def is_live(settings: dict) -> bool:
    """Self-serve stores start un-activated (customers see "coming soon") until the platform
    owner activates them. Stores without the flag (seeded/legacy) are live."""
    return settings.get("activated", True) is not False


def get_private(con, key: str):
    r = con.execute("SELECT value FROM settings WHERE key=?", ("_" + key,)).fetchone()
    return json.loads(r["value"]) if r else None


def set_private(con, key: str, value) -> None:
    set_settings(con, {"_" + key: value})


LOGIN_TOKEN_TTL = 600  # seconds


def issue_login_token(con) -> str:
    """Single-use token that logs the owner in on their store's subdomain right after signup."""
    tok = secrets.token_urlsafe(32)
    exp = (now() + timedelta(seconds=LOGIN_TOKEN_TTL)).timestamp()
    set_private(con, "login_token", {"h": hashlib.sha256(tok.encode()).hexdigest(), "exp": exp})
    return tok


def consume_login_token(con, tok: str) -> bool:
    if not tok:
        return False
    with tx(con):
        r = con.execute("SELECT value FROM settings WHERE key='_login_token'").fetchone()
        if not r:
            return False
        con.execute("DELETE FROM settings WHERE key='_login_token'")
    d = json.loads(r["value"])
    return (d.get("exp", 0) > now().timestamp()
            and hmac.compare_digest(d.get("h", ""), hashlib.sha256(tok.encode()).hexdigest()))


# ---------------------------------------------------------------- kitchen hours

def _hm(s: str, day: datetime) -> datetime:
    h, m = (int(x) for x in s.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def hours_on(settings: dict, day: datetime) -> tuple[datetime, datetime] | None:
    span = (settings.get("hours") or {}).get(str(day.weekday()))
    if not span:
        return None
    opens, closes = _hm(span[0], day), _hm(span[1], day)
    if closes <= opens:  # past midnight
        closes += timedelta(days=1)
    return opens, closes


def kitchen_status(settings: dict, at: datetime | None = None) -> dict:
    at = at or now()
    accepting = bool(settings.get("accepting_orders", True))
    for back in (1, 0):  # yesterday's late shift may still be running
        span = hours_on(settings, at - timedelta(days=back))
        if span and span[0] <= at < span[1]:
            return {"open": accepting, "accepting": accepting, "closes": span[1]}
    nxt = None
    for d in range(0, 8):
        span = hours_on(settings, at + timedelta(days=d))
        if span and span[0] > at:
            nxt = span[0]
            break
    return {"open": False, "accepting": accepting, "opens": nxt}


def time_slots(settings: dict, at: datetime | None = None, days: int = 2) -> list[datetime]:
    """Schedulable pickup/delivery times from now + prep time, within kitchen hours."""
    at = at or now()
    prep = int(settings.get("prep_minutes") or 20)
    step = max(10, int(settings.get("slot_minutes") or 30))
    earliest = at + timedelta(minutes=prep)
    out: list[datetime] = []
    for d in range(-1, days):
        span = hours_on(settings, at + timedelta(days=d))
        if not span:
            continue
        t = span[0] + timedelta(minutes=prep)
        while t <= span[1]:
            if t >= earliest and t not in out:
                out.append(t)
            t += timedelta(minutes=step)
    return sorted(out)[:60]


def ampm(hhmm: str) -> str:
    """'08:00' → '8 AM', '20:30' → '8:30 PM'."""
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{h % 12 or 12}{f':{m:02d}' if m else ''} {'AM' if h % 24 < 12 else 'PM'}"


def fmt_hours(settings: dict, friendly: bool = False) -> list[tuple[str, str]]:
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out = []
    for d in range(7):
        span = (settings.get("hours") or {}).get(str(d))
        if not span:
            out.append((names[d], "Closed"))
        else:
            out.append((names[d], f"{ampm(span[0])} – {ampm(span[1])}" if friendly else f"{span[0]}–{span[1]}"))
    return out


# ---------------------------------------------------------------- menu reads

def _item_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["tags"] = json.loads(d["tags"] or "[]")
    d["allergens"] = json.loads(d["allergens"] or "[]")
    d["available"] = bool(d["active"]) and not d["sold_out"] and (d["remaining"] is None or d["remaining"] > 0)
    return d


def categories(con, include_inactive=False) -> list[dict]:
    q = "SELECT * FROM categories" + ("" if include_inactive else " WHERE active=1") + " ORDER BY sort, id"
    return [dict(r) for r in con.execute(q)]


def items(con, include_inactive=False) -> list[dict]:
    q = (
        "SELECT i.* FROM items i JOIN categories c ON c.id=i.category_id"
        + ("" if include_inactive else " WHERE i.active=1 AND c.active=1")
        + " ORDER BY c.sort, c.id, i.sort, i.id"
    )
    return [_item_dict(r) for r in con.execute(q)]


def get_item(con, item_id: int, with_options=True) -> dict | None:
    r = con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not r:
        return None
    d = _item_dict(r)
    if with_options:
        d["variants"] = [dict(v) for v in con.execute(
            "SELECT * FROM variants WHERE item_id=? ORDER BY sort, id", (item_id,))]
        groups = []
        for g in con.execute("SELECT * FROM modifier_groups WHERE item_id=? ORDER BY sort, id", (item_id,)):
            g = dict(g)
            g["options"] = [dict(m) for m in con.execute(
                "SELECT * FROM modifiers WHERE group_id=? ORDER BY sort, id", (g["id"],))]
            groups.append(g)
        d["groups"] = groups
    return d


def full_menu(con) -> list[dict]:
    """Categories with items (and options) — used by AI tools."""
    cats = {c["id"]: {**c, "items": []} for c in categories(con)}
    for it in items(con):
        if it["category_id"] in cats:
            cats[it["category_id"]]["items"].append(get_item(con, it["id"]))
    return [c for c in cats.values() if c["items"]]


def delivery_zones(con, include_inactive=False) -> list[dict]:
    q = "SELECT * FROM delivery_zones" + ("" if include_inactive else " WHERE active=1") + " ORDER BY name"
    return [dict(r) for r in con.execute(q)]


# ---------------------------------------------------------------- pricing

def price_line(con, item_id: int, variant_id: int | None, modifier_ids: list[int], qty: int,
               note: str = "", future: bool = False) -> dict:
    """Validate a cart line against live DB rows and price it. Raises OrderError.
    future=True (an order for a later day) skips today's 86 flag and portions left."""
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise OrderError("Invalid quantity.")
    if not 1 <= qty <= MAX_QTY:
        raise OrderError(f"Quantity must be 1–{MAX_QTY}.")
    it = get_item(con, int(item_id))
    if not it or not it["active"]:
        raise OrderError("That item is no longer on the menu.")
    if not future and (it["sold_out"] or (it["remaining"] is not None and it["remaining"] <= 0)):
        raise OrderError(f"{it['name']} is sold out.")
    unit = it["price_cents"]
    variant = None
    if it["variants"]:
        variant = next((v for v in it["variants"] if v["id"] == (int(variant_id) if variant_id else None)), None)
        if not variant:
            raise OrderError(f"Choose an option for {it['name']}.")
        unit += variant["price_delta_cents"]
    mod_ids = {int(m) for m in modifier_ids or []}
    chosen = []
    known = set()
    for g in it["groups"]:
        picked = [m for m in g["options"] if m["id"] in mod_ids]
        known |= {m["id"] for m in g["options"]}
        if len(picked) < g["min_select"]:
            raise OrderError(f"{it['name']}: choose at least {g['min_select']} in “{g['name']}”.")
        if len(picked) > g["max_select"]:
            raise OrderError(f"{it['name']}: choose at most {g['max_select']} in “{g['name']}”.")
        for m in picked:
            unit += m["price_delta_cents"]
            chosen.append({"id": m["id"], "group": g["name"], "name": m["name"], "price_delta_cents": m["price_delta_cents"]})
    if mod_ids - known:
        raise OrderError(f"{it['name']}: invalid add-on selected.")
    return {
        "item_id": it["id"], "name": it["name"], "variant_id": variant["id"] if variant else None,
        "variant_name": variant["name"] if variant else None, "modifiers": chosen,
        "modifier_ids": sorted(mod_ids), "qty": qty, "note": (note or "").strip()[:140],
        "unit_price_cents": unit, "line_total_cents": unit * qty,
        "remaining": it["remaining"], "image": it["image"],
    }


def price_cart(con, cart: list[dict], future: bool = False) -> tuple[list[dict], list[str]]:
    """Price every cart line; returns (valid_lines, error_messages)."""
    lines, errors = [], []
    for raw in cart:
        try:
            lines.append(price_line(con, raw["item_id"], raw.get("variant_id"), raw.get("modifier_ids", []),
                                    raw.get("qty", 1), raw.get("note", ""), future))
        except (OrderError, KeyError, TypeError, ValueError) as e:
            errors.append(str(e) if isinstance(e, OrderError) else "An item in your cart is no longer valid.")
    return lines, errors


# ---------------------------------------------------------------- orders

TRANSITIONS = {
    "pending_payment": {"preparing", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"out_for_delivery", "completed", "cancelled"},
    "out_for_delivery": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def allowed_next(order: dict) -> list[str]:
    nxt = set(TRANSITIONS[order["status"]])
    if order["mode"] in DELIVERY_MODES:
        if order["status"] == "ready":
            nxt.discard("completed")
    else:
        nxt.discard("out_for_delivery")
    if order["status"] == "pending_payment" and order["payment_status"] != "verified":
        nxt.discard("preparing")  # must go through verify_payment
    return [s for s in STATUSES if s in nxt]


def _event(con, order_id, frm, to, note=""):
    con.execute("INSERT INTO order_events(order_id, from_status, to_status, note, at) VALUES(?,?,?,?,?)",
                (order_id, frm, to, note, iso()))


def place_order(con, cart: list[dict], form: dict) -> dict:
    """Validate, decrement portions and create the order atomically. Raises OrderError."""
    settings = get_settings(con)
    name = (form.get("name") or "").strip()[:80]
    phone = re.sub(r"[^\d+]", "", form.get("phone") or "")[:16]
    mode = form.get("mode")
    payment = form.get("payment")
    if not name:
        raise OrderError("Please enter your name.")
    if len(re.sub(r"\D", "", phone)) < 10:
        raise OrderError("Please enter a valid mobile number.")
    if mode not in settings["modes"] or mode not in MODES:
        raise OrderError("Choose how you'd like to get your order.")
    if mode == "cod":
        payment = "cod"
    elif payment not in settings["payments"] or payment == "cod":
        raise OrderError("Choose a payment method.")
    if payment == "counter" and mode not in ("dine_in", "pickup"):
        raise OrderError("Pay at counter is only for dine-in or pickup.")
    if not cart:
        raise OrderError("Your cart is empty.")

    status = kitchen_status(settings)
    when = (form.get("when") or "asap").strip()
    scheduled = None
    if when != "asap":
        slots = {s.isoformat(timespec="minutes"): s for s in time_slots(settings)}
        if when not in slots:
            raise OrderError("That time slot is no longer available. Please pick another.")
        scheduled = slots[when].isoformat(timespec="minutes")
    elif not status["open"]:
        raise OrderError("The kitchen is closed right now — please schedule a time.")
    if not settings.get("accepting_orders", True):
        raise OrderError("We're not accepting online orders at the moment.")

    table_no = address = zone = None
    if mode == "dine_in":
        table_no = (form.get("table_no") or "").strip()[:12] or None
    if mode in DELIVERY_MODES:
        address = (form.get("address") or "").strip()[:300]
        if len(address) < 8:
            raise OrderError("Please enter your full delivery address.")
        try:
            zid = int(form.get("zone_id") or 0)
        except ValueError:
            zid = 0
        zone = con.execute("SELECT * FROM delivery_zones WHERE id=? AND active=1", (zid,)).fetchone()
        if not zone:
            raise OrderError("Choose your delivery area.")

    # An order for a later day doesn't touch today's portions: it's checked against that day's
    # daily_portions here, and reset_daily_portions takes it out on the day.
    day = datetime.fromisoformat(scheduled).date() if scheduled else None
    future = day is not None and day > now().date()

    with tx(con):
        lines, errors = price_cart(con, cart, future)
        if errors:
            raise OrderError(errors[0])
        need: dict[int, int] = {}
        for ln in lines:
            need[ln["item_id"]] = need.get(ln["item_id"], 0) + ln["qty"]
        for item_id, q in need.items():
            r = con.execute("SELECT name, remaining, daily_portions FROM items WHERE id=?", (item_id,)).fetchone()
            if future:
                if r["daily_portions"] is not None:
                    left = r["daily_portions"] - _prebooked(con, day, item_id)
                    if left < q:
                        raise OrderError(f"Only {max(left, 0)} {r['name']} left for {day:%a %b %-d}."
                                         if left > 0 else f"{r['name']} is fully booked for {day:%a %b %-d}.")
            elif r["remaining"] is not None:
                if r["remaining"] < q:
                    left = r["remaining"]
                    raise OrderError(f"Only {left} {r['name']} left." if left else f"{r['name']} just sold out.")
                con.execute("UPDATE items SET remaining=remaining-? WHERE id=?", (q, item_id))
        subtotal = sum(ln["line_total_cents"] for ln in lines)
        fee = zone["fee_cents"] if zone else 0
        if zone and subtotal < zone["min_order_cents"]:
            raise OrderError(f"Minimum order for {zone['name']} is ₱{zone['min_order_cents'] / 100:,.0f}.")
        ts = iso()
        cust = con.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
        if cust:
            cid = cust["id"]
            con.execute("UPDATE customers SET name=?, address=COALESCE(?, address) WHERE id=?", (name, address, cid))
        else:
            cid = con.execute(
                "INSERT INTO customers(name, phone, address, first_order_at) VALUES(?,?,?,?)",
                (name, phone, address or "", ts)).lastrowid
        online = payment in ("gcash", "bank")
        order_status = "pending_payment" if online else "preparing"
        token = secrets.token_urlsafe(16)
        oid = con.execute(
            """INSERT INTO orders(token, customer_id, customer_name, phone, mode, table_no, address,
                   zone_id, zone_name, delivery_fee_cents, subtotal_cents, total_cents, payment_method,
                   payment_status, status, scheduled_for, notes, created_at, updated_at, portions_held)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (token, cid, name, phone, mode, table_no, address, zone["id"] if zone else None,
             zone["name"] if zone else None, fee, subtotal, subtotal + fee, payment,
             "unpaid" if online else "collect", order_status, scheduled,
             (form.get("notes") or "").strip()[:300], ts, ts, 0 if future else 1)).lastrowid
        con.execute("UPDATE orders SET code=? WHERE id=?", (f"#{oid:04d}", oid))
        for ln in lines:
            con.execute(
                """INSERT INTO order_items(order_id, item_id, name, variant_name, modifiers, note, qty,
                       unit_price_cents, line_total_cents) VALUES(?,?,?,?,?,?,?,?,?)""",
                (oid, ln["item_id"], ln["name"], ln["variant_name"],
                 json.dumps([{"group": m["group"], "name": m["name"]} for m in ln["modifiers"]]),
                 ln["note"], ln["qty"], ln["unit_price_cents"], ln["line_total_cents"]))
        con.execute(
            "UPDATE customers SET orders_count=orders_count+1, total_spent_cents=total_spent_cents+?, "
            "last_order_at=? WHERE id=?", (subtotal + fee, ts, cid))
        _event(con, oid, None, order_status, "Order placed")
    return get_order(con, oid)


def get_order(con, order_id: int | None = None, token: str | None = None) -> dict | None:
    if token is not None:
        r = con.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
    else:
        r = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not r:
        return None
    o = dict(r)
    o["items"] = []
    for li in con.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id", (o["id"],)):
        li = dict(li)
        li["modifiers"] = json.loads(li["modifiers"])
        o["items"].append(li)
    o["events"] = [dict(e) for e in con.execute(
        "SELECT * FROM order_events WHERE order_id=? ORDER BY id", (o["id"],))]
    return o


def list_orders(con, status: str | None = None, limit: int = 100, since: str | None = None) -> list[dict]:
    q, args = "SELECT id FROM orders WHERE 1=1", []
    if status:
        q += " AND status=?"
        args.append(status)
    if since:
        q += " AND created_at>=?"
        args.append(since)
    order = "ASC" if status in ("pending_payment", "preparing", "ready", "out_for_delivery") else "DESC"
    q += f" ORDER BY COALESCE(scheduled_for, created_at) {order}, id {order} LIMIT ?"
    args.append(limit)
    return [get_order(con, r["id"]) for r in con.execute(q, args)]


def status_counts(con) -> dict:
    out = {s: 0 for s in STATUSES}
    since = iso(now().replace(hour=0, minute=0, second=0, microsecond=0))
    for r in con.execute(
            "SELECT status, COUNT(*) n FROM orders WHERE status NOT IN ('completed','cancelled') "
            "OR created_at>=? GROUP BY status", (since,)):
        out[r["status"]] = r["n"]
    return out


def _prebooked(con, day, item_id: int | None = None) -> int:
    """Portions taken by live orders placed for `day` that haven't been taken out of `remaining`
    yet (portions_held=0), for one item or all items."""
    q = ("SELECT COALESCE(SUM(oi.qty), 0) FROM order_items oi JOIN orders o ON o.id=oi.order_id "
         "WHERE o.portions_held=0 AND o.status!='cancelled' AND substr(o.scheduled_for,1,10)=?")
    args: list = [day.isoformat()]
    if item_id is not None:
        q += " AND oi.item_id=?"
        args.append(item_id)
    return con.execute(q, args).fetchone()[0]


def _restore_portions(con, order_id: int) -> None:
    if not con.execute("SELECT portions_held FROM orders WHERE id=?", (order_id,)).fetchone()[0]:
        return  # a later-day order that never took today's portions
    for li in con.execute("SELECT item_id, qty FROM order_items WHERE order_id=?", (order_id,)).fetchall():
        if li["item_id"]:
            con.execute(
                "UPDATE items SET remaining = CASE WHEN daily_portions IS NOT NULL "
                "THEN MIN(remaining + ?, MAX(daily_portions, remaining)) ELSE remaining + ? END "
                "WHERE id=? AND remaining IS NOT NULL", (li["qty"], li["qty"], li["item_id"]))


def advance_order(con, order_id: int, to: str, note: str = "") -> dict:
    with tx(con):
        o = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not o:
            raise OrderError("Order not found.")
        if to not in allowed_next(dict(o)):
            raise OrderError(f"Can't move {o['code']} from {STATUS_LABEL[o['status']]} to {STATUS_LABEL.get(to, to)}.")
        if to == "cancelled":
            _cancel(con, o, note)
        else:
            con.execute("UPDATE orders SET status=?, updated_at=? WHERE id=?", (to, iso(), order_id))
            _event(con, order_id, o["status"], to, note)
    return get_order(con, order_id)


def _cancel(con, o, note: str) -> None:
    """Cancel inside an open transaction: release portions and undo the customer's totals."""
    _restore_portions(con, o["id"])
    con.execute("UPDATE customers SET orders_count=MAX(orders_count-1,0), "
                "total_spent_cents=MAX(total_spent_cents-?,0) WHERE id=?", (o["total_cents"], o["customer_id"]))
    con.execute("UPDATE orders SET status='cancelled', updated_at=? WHERE id=?", (iso(), o["id"]))
    _event(con, o["id"], o["status"], "cancelled", note)


EXPIRED_NOTE = "Payment not received in time"


def payment_window(settings: dict) -> int:
    try:
        return max(5, min(24 * 60, int(settings.get("payment_window_minutes") or 30)))
    except (TypeError, ValueError):
        return 30


def payment_deadline(o: dict, settings: dict) -> datetime | None:
    """When an unpaid GCash/bank order is cancelled automatically (None if it isn't waiting on the
    customer). The clock starts when the order is placed, and again when a proof is rejected."""
    if o["status"] != "pending_payment" or o["payment_status"] not in ("unpaid", "rejected"):
        return None
    return datetime.fromisoformat(o["updated_at"]) + timedelta(minutes=payment_window(settings))


def expire_unpaid(con, settings: dict | None = None) -> int:
    """Cancel GCash/bank orders still unpaid after the payment window, releasing their portions.
    Orders with a proof waiting for the owner are never touched. Returns how many were cancelled."""
    settings = settings or get_settings(con)
    cutoff = iso(now() - timedelta(minutes=payment_window(settings)))
    stale = ("SELECT * FROM orders WHERE status='pending_payment' "
             "AND payment_status IN ('unpaid','rejected') AND updated_at<?")
    if not con.execute(stale, (cutoff,)).fetchone():  # common case: no write lock needed
        return 0
    n = 0
    with tx(con):
        for o in con.execute(stale, (cutoff,)).fetchall():  # re-read inside the lock
            _cancel(con, o, EXPIRED_NOTE)
            n += 1
    return n


_swept: dict[str, float] = {}


def housekeep(con, store: str, every: float = 60) -> None:
    """Cheap periodic upkeep, run from request handlers (there's no background worker):
    at most once a minute per store per process."""
    t = time.monotonic()
    if t - _swept.get(store, -every) < every:
        return
    _swept[store] = t
    try:
        expire_unpaid(con)
    except sqlite3.OperationalError:  # busy: try again on a later request
        _swept.pop(store, None)


def submit_payment_proof(con, token: str, proof_path: str, ref: str) -> dict:
    with tx(con):
        o = con.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
        if not o:
            raise OrderError("Order not found.")
        if o["status"] == "cancelled":
            raise OrderError("This order was cancelled, so no payment is needed. Please place a new order.")
        if o["status"] != "pending_payment" or o["payment_status"] not in ("unpaid", "rejected"):
            raise OrderError("This order no longer needs a payment proof.")
        con.execute("UPDATE orders SET proof_path=?, payment_ref=?, payment_status='submitted', updated_at=? "
                    "WHERE id=?", (proof_path, (ref or "").strip()[:40], iso(), o["id"]))
        _event(con, o["id"], o["status"], o["status"], "Payment proof submitted")
    return get_order(con, o["id"])


def verify_payment(con, order_id: int) -> dict:
    with tx(con):
        o = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not o or o["status"] != "pending_payment":
            raise OrderError("This order isn't awaiting payment.")
        con.execute("UPDATE orders SET payment_status='verified', status='preparing', updated_at=? WHERE id=?",
                    (iso(), order_id))
        _event(con, order_id, "pending_payment", "preparing", "Payment verified")
    return get_order(con, order_id)


def reject_payment(con, order_id: int, reason: str) -> dict:
    with tx(con):
        o = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not o or o["status"] != "pending_payment":
            raise OrderError("This order isn't awaiting payment.")
        con.execute("UPDATE orders SET payment_status='rejected', payment_note=?, updated_at=? WHERE id=?",
                    ((reason or "Payment could not be verified.").strip()[:200], iso(), order_id))
        _event(con, order_id, "pending_payment", "pending_payment", f"Payment rejected: {reason}")
    return get_order(con, order_id)


# ---------------------------------------------------------------- menu writes

def set_sold_out(con, item_id: int, sold_out: bool) -> dict:
    with tx(con):
        if not con.execute("UPDATE items SET sold_out=? WHERE id=?", (int(bool(sold_out)), item_id)).rowcount:
            raise OrderError("Item not found.")
    return get_item(con, item_id, with_options=False)


def set_remaining(con, item_id: int, remaining: int | None) -> dict:
    if remaining is not None and (remaining < 0 or remaining > 100_000):
        raise OrderError("Portions must be 0 or more.")
    with tx(con):
        if not con.execute("UPDATE items SET remaining=? WHERE id=?", (remaining, item_id)).rowcount:
            raise OrderError("Item not found.")
    return get_item(con, item_id, with_options=False)


def set_price(con, item_id: int, price_cents: int) -> dict:
    if price_cents < 0 or price_cents > 10_000_000:
        raise OrderError("Invalid price.")
    with tx(con):
        if not con.execute("UPDATE items SET price_cents=? WHERE id=?", (price_cents, item_id)).rowcount:
            raise OrderError("Item not found.")
    return get_item(con, item_id, with_options=False)


def reset_daily_portions(con, clear_sold_out: bool = True) -> int:
    """Start a new day: refill every tracked item, minus what customers already booked for today
    in earlier days (those orders then count as holding their portions)."""
    today = now().date()
    with tx(con):
        n = con.execute("UPDATE items SET remaining=daily_portions WHERE daily_portions IS NOT NULL").rowcount
        for r in con.execute(
                "SELECT oi.item_id, SUM(oi.qty) q FROM order_items oi JOIN orders o ON o.id=oi.order_id "
                "WHERE o.status!='cancelled' AND substr(o.scheduled_for,1,10)=? "
                "AND (o.portions_held=0 OR substr(o.created_at,1,10)<?) AND oi.item_id IS NOT NULL "
                "GROUP BY oi.item_id", (today.isoformat(), today.isoformat())).fetchall():
            con.execute("UPDATE items SET remaining=MAX(remaining-?, 0) WHERE id=? AND remaining IS NOT NULL",
                        (r["q"], r["item_id"]))
        con.execute("UPDATE orders SET portions_held=1 WHERE portions_held=0 AND status!='cancelled' "
                    "AND substr(scheduled_for,1,10)=?", (today.isoformat(),))
        if clear_sold_out:
            con.execute("UPDATE items SET sold_out=0")
        con.execute("INSERT INTO settings(key, value) VALUES('last_portion_reset', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(iso()),))
    return n


def upsert_category(con, name: str, cat_id: int | None = None, sort: int = 0, active: bool = True) -> int:
    name = name.strip()[:60]
    if not name:
        raise OrderError("Category name is required.")
    with tx(con):
        if cat_id:
            con.execute("UPDATE categories SET name=?, sort=?, active=? WHERE id=?", (name, sort, int(active), cat_id))
            return cat_id
        return con.execute("INSERT INTO categories(name, sort, active) VALUES(?,?,?)",
                           (name, sort, int(active))).lastrowid


def update_category(con, cat_id: int, name: str | None = None, active: bool | None = None) -> None:
    with tx(con):
        if name is not None:
            name = name.strip()[:60]
            if not name:
                raise OrderError("Category name is required.")
            con.execute("UPDATE categories SET name=? WHERE id=?", (name, cat_id))
        if active is not None:
            con.execute("UPDATE categories SET active=? WHERE id=?", (int(active), cat_id))


def delete_category(con, cat_id: int) -> None:
    """Only empty categories can be deleted (items keep order history)."""
    with tx(con):
        n = con.execute("SELECT COUNT(*) FROM items WHERE category_id=?", (cat_id,)).fetchone()[0]
        if n:
            raise OrderError(f"This category still has {n} item{'s' if n != 1 else ''}. Move them to another "
                             "category first (Edit → Category), or hide the category instead.")
        con.execute("DELETE FROM categories WHERE id=?", (cat_id,))


def reorder_categories(con, ids: list[int]) -> None:
    with tx(con):
        for i, cid in enumerate(ids):
            con.execute("UPDATE categories SET sort=? WHERE id=?", (i, cid))


def reorder_items(con, category_id: int, ids: list[int]) -> None:
    with tx(con):
        for i, iid in enumerate(ids):
            con.execute("UPDATE items SET sort=? WHERE id=? AND category_id=?", (i, iid, category_id))


def save_item(con, data: dict, item_id: int | None = None) -> int:
    """Create/update an item. `data` keys: category_id, name, description, price_cents, tags,
    allergens, daily_portions, active, sort, image (optional), variants, groups (optional)."""
    name = (data.get("name") or "").strip()[:80]
    if not name:
        raise OrderError("Item name is required.")
    if int(data.get("price_cents", -1)) < 0:
        raise OrderError("Price must be 0 or more.")
    daily = data.get("daily_portions")
    daily = None if daily in (None, "") else int(daily)
    if daily is not None and daily < 0:
        raise OrderError("Daily portions must be 0 or more.")
    with tx(con):
        if not con.execute("SELECT 1 FROM categories WHERE id=?", (int(data["category_id"]),)).fetchone():
            raise OrderError("Choose a category.")
        vals = (int(data["category_id"]), name, (data.get("description") or "").strip()[:400],
                int(data["price_cents"]), json.dumps(list(data.get("tags") or [])),
                json.dumps(list(data.get("allergens") or [])), daily, int(bool(data.get("active", True))),
                int(data.get("sort") or 0))
        if item_id:
            old = con.execute("SELECT daily_portions, remaining FROM items WHERE id=?", (item_id,)).fetchone()
            if not old:
                raise OrderError("Item not found.")
            con.execute("UPDATE items SET category_id=?, name=?, description=?, price_cents=?, tags=?, "
                        "allergens=?, daily_portions=?, active=?, sort=? WHERE id=?", (*vals, item_id))
            if daily is None:
                con.execute("UPDATE items SET remaining=NULL WHERE id=?", (item_id,))
            elif old["daily_portions"] is None:
                con.execute("UPDATE items SET remaining=? WHERE id=?", (daily, item_id))
        else:
            item_id = con.execute(
                "INSERT INTO items(category_id, name, description, price_cents, tags, allergens, "
                "daily_portions, active, sort, remaining) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (*vals, daily)).lastrowid
        if data.get("image") is not None:
            con.execute("UPDATE items SET image=? WHERE id=?", (data["image"] or None, item_id))
        if "variants" in data:
            con.execute("DELETE FROM variants WHERE item_id=?", (item_id,))
            for i, v in enumerate(data["variants"]):
                con.execute("INSERT INTO variants(item_id, name, price_delta_cents, sort) VALUES(?,?,?,?)",
                            (item_id, v["name"][:60], int(v.get("price_delta_cents", 0)), i))
        if "groups" in data:
            con.execute("DELETE FROM modifier_groups WHERE item_id=?", (item_id,))
            for i, g in enumerate(data["groups"]):
                mn, mx = int(g.get("min_select", 0)), int(g.get("max_select", 1))
                if mx < 1 or mn > mx or mn > len(g["options"]):
                    raise OrderError(f"Check the min/max for “{g['name']}”.")
                gid = con.execute(
                    "INSERT INTO modifier_groups(item_id, name, min_select, max_select, sort) VALUES(?,?,?,?,?)",
                    (item_id, g["name"][:60], mn, mx, i)).lastrowid
                for j, m in enumerate(g["options"]):
                    con.execute("INSERT INTO modifiers(group_id, name, price_delta_cents, sort) VALUES(?,?,?,?)",
                                (gid, m["name"][:60], int(m.get("price_delta_cents", 0)), j))
    return item_id


def delete_item(con, item_id: int) -> None:
    # keep history intact: order_items store name/price snapshots; just hide it
    with tx(con):
        con.execute("UPDATE items SET active=0 WHERE id=?", (item_id,))


def save_zone(con, name: str, fee_cents: int, min_order_cents: int = 0, eta: int = 45,
              zone_id: int | None = None) -> None:
    name = name.strip()[:60]
    if not name or fee_cents < 0 or min_order_cents < 0:
        raise OrderError("Zone needs a name and a fee of 0 or more.")
    with tx(con):
        if zone_id:
            con.execute("UPDATE delivery_zones SET name=?, fee_cents=?, min_order_cents=?, eta_minutes=? "
                        "WHERE id=?", (name, fee_cents, min_order_cents, eta, zone_id))
        else:
            con.execute("INSERT INTO delivery_zones(name, fee_cents, min_order_cents, eta_minutes) "
                        "VALUES(?,?,?,?)", (name, fee_cents, min_order_cents, eta))


def delete_zone(con, zone_id: int) -> None:
    with tx(con):
        con.execute("UPDATE delivery_zones SET active=0 WHERE id=?", (zone_id,))


# ---------------------------------------------------------------- media

IMAGE_MAGIC = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png", b"RIFF": ".webp", b"GIF8": ".gif"}
MAX_UPLOAD = 6 * 1024 * 1024


def save_image(store: str, kind: str, data: bytes) -> str:
    """Validate by magic bytes and store under data/uploads/<store>/<kind>/. Returns filename."""
    if not data:
        raise OrderError("Please choose an image.")
    if len(data) > MAX_UPLOAD:
        raise OrderError("Image is too large (max 6 MB).")
    ext = next((e for magic, e in IMAGE_MAGIC.items() if data.startswith(magic)), None)
    if ext == ".webp" and data[8:12] != b"WEBP":
        ext = None
    if not ext:
        raise OrderError("Please upload a JPG, PNG, WEBP or GIF image.")
    name = secrets.token_hex(12) + ext
    (upload_dir(store, kind) / name).write_bytes(data)
    return name


def media_file(store: str, kind: str, name: str) -> Path | None:
    if not re.fullmatch(r"[0-9a-f]{24}\.(jpg|png|webp|gif)", name or ""):
        return None
    p = DATA_DIR / "uploads" / store / kind / name
    return p if p.is_file() else None


# ---------------------------------------------------------------- customers & insights

def list_customers(con, limit=200) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT * FROM customers ORDER BY last_order_at DESC LIMIT ?", (limit,))]


def sales_summary(con, days: int = 7) -> dict:
    start = now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    since = iso(start)
    ok = "status NOT IN ('cancelled','pending_payment')"
    tot = con.execute(f"SELECT COUNT(*) n, COALESCE(SUM(total_cents),0) s FROM orders "
                      f"WHERE {ok} AND created_at>=?", (since,)).fetchone()
    by_day = {(start + timedelta(days=i)).date().isoformat(): 0 for i in range(days)}
    for r in con.execute(f"SELECT substr(created_at,1,10) d, SUM(total_cents) s FROM orders "
                         f"WHERE {ok} AND created_at>=? GROUP BY d", (since,)):
        if r["d"] in by_day:
            by_day[r["d"]] = r["s"]
    top = [dict(r) for r in con.execute(
        f"SELECT oi.name, SUM(oi.qty) qty, SUM(oi.line_total_cents) revenue FROM order_items oi "
        "JOIN orders o ON o.id=oi.order_id WHERE o.status NOT IN ('cancelled','pending_payment') "
        "AND o.created_at>=? GROUP BY oi.name ORDER BY qty DESC LIMIT 8", (since,))]
    modes = {r["mode"]: r["n"] for r in con.execute(
        f"SELECT mode, COUNT(*) n FROM orders WHERE {ok} AND created_at>=? GROUP BY mode", (since,))}
    hours = {r["h"]: r["n"] for r in con.execute(
        f"SELECT CAST(substr(created_at,12,2) AS INTEGER) h, COUNT(*) n FROM orders "
        f"WHERE {ok} AND created_at>=? GROUP BY h", (since,))}
    cancelled = con.execute("SELECT COUNT(*) FROM orders WHERE status='cancelled' AND created_at>=?",
                            (since,)).fetchone()[0]
    return {
        "days": days, "orders": tot["n"], "revenue_cents": tot["s"],
        "aov_cents": (tot["s"] // tot["n"]) if tot["n"] else 0, "by_day": by_day,
        "top_items": top, "by_mode": modes, "by_hour": hours, "cancelled": cancelled,
    }


# ---------------------------------------------------------------- AI persistence

def get_thread(con, thread_id: str) -> list[dict]:
    r = con.execute("SELECT messages FROM chat_threads WHERE id=?", (thread_id,)).fetchone()
    return json.loads(r["messages"]) if r else []


def save_thread(con, thread_id: str, kind: str, messages: list[dict]) -> None:
    with tx(con):
        con.execute("INSERT INTO chat_threads(id, kind, messages, updated_at) VALUES(?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET messages=excluded.messages, updated_at=excluded.updated_at",
                    (thread_id, kind, json.dumps(messages[-40:]), iso()))


def create_proposal(con, kind: str, payload: dict, summary: str) -> int:
    with tx(con):
        return con.execute("INSERT INTO ai_proposals(kind, payload, summary, created_at) VALUES(?,?,?,?)",
                           (kind, json.dumps(payload), summary[:300], iso())).lastrowid


def get_proposal(con, pid: int) -> dict | None:
    r = con.execute("SELECT * FROM ai_proposals WHERE id=?", (pid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["payload"] = json.loads(d["payload"])
    return d


def pending_proposals(con) -> list[dict]:
    return [get_proposal(con, r["id"]) for r in con.execute(
        "SELECT id FROM ai_proposals WHERE status='pending' ORDER BY id DESC LIMIT 20")]


def settle_proposal(con, pid: int, status: str, result: str) -> None:
    """Record the outcome of a proposal already claimed with decide_proposal(..., 'confirmed')."""
    with tx(con):
        con.execute("UPDATE ai_proposals SET status=?, result=? WHERE id=?", (status, result[:300], pid))


def decide_proposal(con, pid: int, status: str, result: str = "") -> bool:
    """Atomically move a pending proposal to a final state. False if it was already decided."""
    with tx(con):
        return bool(con.execute(
            "UPDATE ai_proposals SET status=?, result=?, decided_at=? WHERE id=? AND status='pending'",
            (status, result[:300], iso(), pid)).rowcount)

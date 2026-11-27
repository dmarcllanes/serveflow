import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Scratch DATA_DIR for the whole run, set BEFORE importing app modules. Never touches real data/.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="serveflow-test-")
for k in ("LLM_BASE_URL", "LLM_API_KEY", "DEFAULT_STORE", "CONTACT_URL", "HTTPS_ONLY"):
    os.environ[k] = ""  # blank (not unset) so main.py's .env loader can't refill them from a real .env
os.environ["BASE_DOMAIN"] = "localhost"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["STORE_TZ"] = "Asia/Manila"

import db  # noqa: E402
import seed_client  # noqa: E402

SEED = json.loads((Path(__file__).parent.parent / "seeds" / "demo-resto.json").read_text(encoding="utf-8"))
PW = "test-pass-123"
ALL_DAY = {str(d): ["00:00", "00:00"] for d in range(7)}  # open 24 hours, so tests never hit closing time
_n = 0


class Clock:
    """Controls db.now() so tests can jump ahead (payment windows, the next day)."""

    def __init__(self):
        self.t = datetime(2026, 12, 2, 10, 0, tzinfo=db.TZ)  # a Wednesday, 10 AM

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(db, "now", c)
    return c


def make_store() -> str:
    global _n
    _n += 1
    slug = f"t{_n}-{os.getpid()}"
    con = db.claim_store(slug)
    db.set_settings(con, {**SEED["settings"], "hours": ALL_DAY, "accepting_orders": True})
    seed_client.populate(con, SEED)
    db.set_admin_password(con, PW)
    db._swept.pop(slug, None)
    return slug


@pytest.fixture
def slug():
    return make_store()


@pytest.fixture
def con(slug):
    return db.get_db(slug)


@pytest.fixture
def app():
    import main
    return main.app


def http(app, slug):
    from starlette.testclient import TestClient
    return TestClient(app, base_url=f"http://{slug}.localhost")


@pytest.fixture
def client(app, slug):
    return http(app, slug)


def login(c):
    r = c.post("/admin/login", data={"password": PW}, headers={"hx-request": "1"})
    assert r.headers.get("hx-redirect") == "/admin/queue", r.text
    return c


@pytest.fixture
def owner(client):
    return login(client)


def item_id(con, name: str) -> int:
    return con.execute("SELECT id FROM items WHERE name=?", (name,)).fetchone()[0]


def remaining(con, name: str):
    return con.execute("SELECT remaining FROM items WHERE name=?", (name,)).fetchone()[0]


def order(con, name="Classic Ensaymada", qty=1, payment="gcash", when="asap", phone="09171234567", **form):
    return db.place_order(con, [{"item_id": item_id(con, name), "qty": qty}],
                          {"name": "Ana Cruz", "phone": phone, "mode": "pickup", "payment": payment,
                           "when": when, **form})


def slot_on(con, day) -> str:
    """A schedulable time on `day`, in the format the checkout form sends."""
    s = db.get_settings(con)
    return next(t.isoformat(timespec="minutes") for t in db.time_slots(s) if t.date() == day and t.hour >= 9)

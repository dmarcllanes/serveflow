"""Pages and admin flows through the real app (FastHTML + sessions)."""

from datetime import timedelta

import ai
import db
from conftest import PW, http, login, order


def test_pages_load_and_say_serveflow(client, slug):
    for path in ("/", "/menu", "/cart", "/admin/login"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "BiteFlow" not in r.text
    assert "ServeFlow" in client.get("/menu").text


def test_admin_needs_login(client):
    r = client.get("/admin/queue", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_order_page_shows_payment_deadline_then_expired_message(client, con, clock):
    o = order(con)
    page = client.get(f"/order/{o['token']}").text
    assert "Please pay by" in page and f"{clock.t + timedelta(minutes=30):%-I:%M %p}" in page

    clock.advance(minutes=31)
    db._swept.clear()
    page = client.get(f"/order/{o['token']}").text  # visiting the store runs the expiry sweep
    assert "didn&#x27;t receive your payment in time" in page or "didn't receive your payment in time" in page
    assert db.get_order(con, o["id"])["status"] == "cancelled"


def test_kitchen_card_shows_auto_cancel_time(owner, con, clock):
    order(con)
    html = owner.get("/admin/queue/list?tab=pending_payment").text
    assert "Cancels automatically at" in html


def test_payment_window_setting_is_saved_and_clamped(owner, con):
    page = owner.get("/admin/website").text
    assert 'name="payment_window_minutes"' in page
    form = {"name": "Demo", "payment_window_minutes": "2", "modes": "pickup", "payments": "gcash"}
    owner.post("/admin/website", data=form, follow_redirects=False)
    assert db.get_settings(con)["payment_window_minutes"] == 5


def test_password_change_logs_out_other_devices(app, slug, con):
    phone, tablet = login(http(app, slug)), login(http(app, slug))

    r = phone.post("/admin/password", data={"current": "nope-nope", "password": "new-pass-456",
                                            "confirm": "new-pass-456"}, follow_redirects=False)
    assert "pw=current" in r.headers["location"]
    assert "current password is wrong" in phone.get(r.headers["location"]).text
    r = phone.post("/admin/password", data={"current": PW, "password": "new-pass-456",
                                            "confirm": "different-1"}, follow_redirects=False)
    assert "pw=match" in r.headers["location"]
    assert db.check_admin_password(con, PW)

    r = phone.post("/admin/password", data={"current": PW, "password": "new-pass-456",
                                            "confirm": "new-pass-456"}, follow_redirects=False)
    assert "saved=4" in r.headers["location"]
    assert phone.get("/admin/queue", follow_redirects=False).status_code == 200  # this device stays in
    r = tablet.get("/admin/queue", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"  # the other one is out
    assert db.check_admin_password(con, "new-pass-456")


def test_copilot_proposal_runs_once(con):
    tid = con.execute("SELECT id FROM items WHERE name='Tapsilog'").fetchone()[0]
    pid = db.create_proposal(con, "set_price", {"item_id": tid, "price_cents": 18900}, "Tapsilog → ₱189")
    assert "189" in ai.execute_proposal(con, pid)
    try:
        ai.execute_proposal(con, pid)
        raise AssertionError("second confirm should fail")
    except db.OrderError as e:
        assert "already handled" in str(e)
    p = db.get_proposal(con, pid)
    assert p["status"] == "confirmed" and "189" in p["result"]


def test_copilot_proposal_that_fails_is_marked_failed(con):
    pid = db.create_proposal(con, "set_price", {"item_id": 99999, "price_cents": 100}, "Missing item")
    try:
        ai.execute_proposal(con, pid)
    except db.OrderError:
        pass
    p = db.get_proposal(con, pid)
    assert p["status"] == "failed" and "not found" in p["result"].lower()

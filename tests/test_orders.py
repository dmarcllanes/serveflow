"""Order rules in db.py: unpaid-order expiry, portions for later-day orders, cancelling."""

from datetime import timedelta

import pytest

import db
from conftest import item_id, order, remaining, slot_on


# ---------------------------------------------------------------- unpaid orders expire

def test_unpaid_order_expires_and_releases_portions(con, clock):
    o = order(con, qty=3)
    assert o["status"] == "pending_payment" and remaining(con, "Classic Ensaymada") == 21

    clock.advance(minutes=29)
    assert db.expire_unpaid(con) == 0

    clock.advance(minutes=2)
    assert db.expire_unpaid(con) == 1
    o = db.get_order(con, o["id"])
    assert o["status"] == "cancelled"
    assert o["events"][-1]["note"] == db.EXPIRED_NOTE
    assert remaining(con, "Classic Ensaymada") == 24
    cust = con.execute("SELECT orders_count, total_spent_cents FROM customers").fetchone()
    assert tuple(cust) == (0, 0)


def test_expiry_leaves_proofs_and_pay_later_orders_alone(con, clock):
    with_proof = order(con, phone="09170000001")
    db.submit_payment_proof(con, with_proof["token"], "a" * 24 + ".png", "")
    counter = order(con, payment="counter", phone="09170000002")
    clock.advance(hours=3)
    assert db.expire_unpaid(con) == 0
    assert db.get_order(con, with_proof["id"])["status"] == "pending_payment"
    assert db.get_order(con, counter["id"])["status"] == "preparing"


def test_rejected_proof_restarts_the_window(con, clock):
    o = order(con)
    clock.advance(minutes=20)
    db.submit_payment_proof(con, o["token"], "b" * 24 + ".png", "")
    clock.advance(minutes=5)
    db.reject_payment(con, o["id"], "Blurry screenshot")  # the 30 minutes start again here

    clock.advance(minutes=20)  # 45 min after placing, 20 after the rejection
    assert db.expire_unpaid(con) == 0
    clock.advance(minutes=11)
    assert db.expire_unpaid(con) == 1


def test_payment_window_is_a_setting(con, clock):
    db.set_settings(con, {"payment_window_minutes": 10})
    o = order(con)
    s = db.get_settings(con)
    assert db.payment_deadline(o, s) == clock.t + timedelta(minutes=10)
    clock.advance(minutes=11)
    assert db.expire_unpaid(con) == 1


def test_proof_after_expiry_explains_the_cancellation(con, clock):
    o = order(con)
    clock.advance(minutes=31)
    db.expire_unpaid(con)
    with pytest.raises(db.OrderError, match="cancelled"):
        db.submit_payment_proof(con, o["token"], "c" * 24 + ".png", "")


def test_housekeep_runs_at_most_once_a_minute(con, slug, clock):
    o = order(con)
    clock.advance(minutes=31)
    db.housekeep(con, slug, every=60)
    assert db.get_order(con, o["id"])["status"] == "cancelled"
    o2 = order(con, phone="09170000003")
    clock.advance(minutes=31)
    db.housekeep(con, slug, every=3600)  # throttled: same process ran it moments ago
    assert db.get_order(con, o2["id"])["status"] == "pending_payment"


# ---------------------------------------------------------------- orders for a later day

def test_order_for_tomorrow_keeps_todays_portions(con, clock):
    tomorrow = clock.t.date() + timedelta(days=1)
    o = order(con, qty=5, payment="counter", when=slot_on(con, tomorrow))
    assert remaining(con, "Classic Ensaymada") == 24
    assert con.execute("SELECT portions_held FROM orders WHERE id=?", (o["id"],)).fetchone()[0] == 0


def test_tomorrow_is_limited_by_its_own_daily_portions(con, clock):
    when = slot_on(con, clock.t.date() + timedelta(days=1))
    order(con, qty=22, payment="counter", when=when)
    with pytest.raises(db.OrderError, match="Only 2 Classic Ensaymada left"):
        order(con, qty=3, payment="counter", when=when, phone="09170000004")
    order(con, qty=2, payment="counter", when=when, phone="09170000005")
    with pytest.raises(db.OrderError, match="fully booked"):
        order(con, qty=1, payment="counter", when=when, phone="09170000006")


def test_sold_out_today_can_still_be_ordered_for_tomorrow(con, clock):
    db.set_remaining(con, item_id(con, "Classic Ensaymada"), 0)
    with pytest.raises(db.OrderError, match="sold out"):
        order(con, payment="counter")
    order(con, payment="counter", when=slot_on(con, clock.t.date() + timedelta(days=1)))


def test_reset_on_the_day_takes_prebooked_portions(con, clock):
    o = order(con, qty=5, payment="counter", when=slot_on(con, clock.t.date() + timedelta(days=1)))
    clock.advance(days=1)
    clock.t = clock.t.replace(hour=7)
    db.reset_daily_portions(con)
    assert remaining(con, "Classic Ensaymada") == 19
    db.reset_daily_portions(con)  # pressing reset twice gives the same answer
    assert remaining(con, "Classic Ensaymada") == 19

    db.advance_order(con, o["id"], "cancelled")
    assert remaining(con, "Classic Ensaymada") == 24


def test_cancelling_a_later_day_order_leaves_today_alone(con, clock):
    order(con, qty=2, payment="counter", phone="09170000007")
    assert remaining(con, "Classic Ensaymada") == 22
    later = order(con, qty=5, payment="counter", when=slot_on(con, clock.t.date() + timedelta(days=1)))
    db.advance_order(con, later["id"], "cancelled")
    assert remaining(con, "Classic Ensaymada") == 22


def test_cancel_restores_portions_and_customer_totals(con, clock):
    o = order(con, qty=4, payment="counter")
    db.advance_order(con, o["id"], "cancelled")
    assert remaining(con, "Classic Ensaymada") == 24
    assert con.execute("SELECT orders_count FROM customers").fetchone()[0] == 0
    with pytest.raises(db.OrderError):
        db.advance_order(con, o["id"], "cancelled")  # already final


# ---------------------------------------------------------------- passwords

def test_password_change_bumps_session_version(con):
    v = db.session_version(con)
    with pytest.raises(db.OrderError, match="current password"):
        db.change_admin_password(con, "wrong-pass", "new-pass-456", "new-pass-456")
    with pytest.raises(db.OrderError, match="match"):
        db.change_admin_password(con, "test-pass-123", "new-pass-456", "new-pass-789")
    with pytest.raises(db.OrderError, match="8–128"):
        db.change_admin_password(con, "test-pass-123", "short", "short")
    assert db.session_version(con) == v
    assert db.change_admin_password(con, "test-pass-123", "new-pass-456", "new-pass-456") == v + 1
    assert db.check_admin_password(con, "new-pass-456")

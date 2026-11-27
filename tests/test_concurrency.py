"""Many devices at once, against a real uvicorn server (threads, like production).

Regression: requests used to share one SQLite connection across threads, so simultaneous
kitchen taps failed with "cannot start a transaction within a transaction".
"""

import socket
import threading
import time

import httpx
import pytest
import uvicorn

import ai
import db
from conftest import PW, item_id, make_store


@pytest.fixture(scope="module")
def server():
    import main
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)


def run_all(fns):
    """Start every call at the same moment; return their results."""
    out, bar = [None] * len(fns), threading.Barrier(len(fns))

    def go(i):
        bar.wait()
        out[i] = fns[i]()
    ts = [threading.Thread(target=go, args=(i,)) for i in range(len(fns))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return out


def browser(base, slug):
    return httpx.Client(base_url=base, headers={"host": f"{slug}.localhost"}, timeout=30)


def test_simultaneous_kitchen_taps_all_succeed(server):
    slug = make_store()
    con = db.get_db(slug)
    tap = item_id(con, "Classic Ensaymada")
    ids = [db.place_order(con, [{"item_id": tap, "qty": 1}], {
        "name": f"T{i}", "phone": f"0917{i:07d}", "mode": "pickup", "payment": "counter", "when": "asap"})["id"]
        for i in range(24)]
    devices = []
    for _ in ids:
        c = browser(server, slug)
        assert c.post("/admin/login", data={"password": PW}, headers={"hx-request": "1"}).headers.get("hx-redirect")
        devices.append(c)

    def work(i):
        def f():
            a = devices[i].post(f"/admin/orders/{ids[i]}/advance", data={"to": "ready"}, headers={"hx-request": "1"})
            b = devices[i].post(f"/admin/items/{(i % 10) + 1}/remaining", data={"remaining": "20"},
                                headers={"hx-request": "1"})
            return a.status_code, b.status_code
        return f

    results = run_all([work(i) for i in range(len(ids))])
    assert results == [(200, 200)] * len(ids)
    assert con.execute("SELECT COUNT(*) FROM orders WHERE status='ready'").fetchone()[0] == len(ids)


def test_simultaneous_checkouts_never_oversell(server):
    slug = make_store()
    con = db.get_db(slug)
    tap = item_id(con, "Classic Ensaymada")  # 24 portions
    shoppers = []
    for _ in range(25):
        c = browser(server, slug)
        c.post(f"/cart/quick/{tap}", headers={"hx-request": "1"})
        c.post("/cart/qty/0?d=1", headers={"hx-request": "1"})  # 2 each → only 12 can succeed
        shoppers.append(c)

    def checkout(i):
        return lambda: shoppers[i].post("/checkout", headers={"hx-request": "1"}, data={
            "name": f"S{i}", "phone": f"0918{i:07d}", "mode": "pickup", "payment": "counter", "when": "asap"})

    results = run_all([checkout(i) for i in range(len(shoppers))])
    placed = [r for r in results if r.headers.get("hx-redirect", "").startswith("/order/")]
    assert all(r.status_code == 200 for r in results)
    assert len(placed) == 12
    assert con.execute("SELECT remaining FROM items WHERE id=?", (tap,)).fetchone()[0] == 0


def test_double_confirm_from_two_devices_runs_once():
    slug = make_store()
    con = db.get_db(slug)
    pid = db.create_proposal(con, "reset_portions", {}, "Reset all daily portions")

    def confirm():
        try:
            ai.execute_proposal(db.get_db(slug), pid)  # each thread has its own connection
            return "ran"
        except db.OrderError:
            return "refused"

    assert sorted(run_all([confirm] * 6)) == ["ran"] + ["refused"] * 5

"""Owner & Kitchen admin: queue tabs, payment verification, menu/86 editor, customers,
insights, website editor and Kitchen Co-pilot. All routes under /admin are session-protected
by main.before (except /admin/login)."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime

from fasthtml.common import (
    A, APIRouter, Button, Div, Form, H2, H3, Img, Input, Label, Nav, Option, P, Response, Script, Select, Span,
    Table, Tbody, Td, Th, Thead, Tr, HtmxResponseHeaders,
)
from starlette.responses import FileResponse, RedirectResponse

import ai
import db
import ui
from ui import peso

ar = APIRouter(prefix="/admin")

QUEUE_TABS = ["pending_payment", "preparing", "ready", "out_for_delivery", "completed", "cancelled"]
TAG_CHOICES = ["best_seller", "spicy", "new", "vegetarian"]
_login_fail: dict[str, list[float]] = {}


def ctx(req):
    # get_db is per-thread: call it here, on the handler's thread (see main.before)
    store = req.scope["store"]
    con = db.get_db(store)
    db.housekeep(con, store)
    return store, con


def log_in(sess, store: str, con) -> None:
    sess["admin"] = store
    sess["admin_ver"] = db.session_version(con)
    sess["copilot_id"] = "k_" + secrets.token_hex(8)


def toast(msg: str):
    return HtmxResponseHeaders(trigger=json.dumps({"toast": msg}))


def toast_only(msg: str):
    return Response("", headers={"HX-Trigger": json.dumps({"toast": msg})})


def shell(req, title: str, active: str, *content):
    _, con = ctx(req)
    s = db.get_settings(con)
    counts = db.status_counts(con)
    live = db.is_live(s)
    links = ([] if live else [("start", "★ Setup", 0)]) + [
             ("queue", "Kitchen", counts["pending_payment"] + counts["preparing"] + counts["ready"]),
             ("menu", "Menu & 86", 0), ("copilot", "Co-pilot", 0), ("insights", "Insights", 0),
             ("customers", "Customers", 0), ("qr", "QR codes", 0), ("website", "Website", 0)]
    nav = Nav(*[A(label, Span(str(n), cls="ml-1 rounded-full bg-brand text-white text-[10px] px-1.5") if n else None,
                  href=f"/admin/{key}",
                  cls=f"shrink-0 rounded-full px-3 py-1.5 text-sm font-semibold "
                      f"{'bg-stone-900 text-white' if key == active else 'bg-white border border-stone-300'}")
                for key, label, n in links],
              cls="flex gap-2 overflow-x-auto no-scrollbar")
    top = Div(Div(A(s["name"], href="/", target="_blank", cls="font-extrabold"),
                  Span(" · Admin", cls="text-stone-500"), cls="text-lg"),
              Form(Button("Log out", cls="text-sm text-stone-500"), method="post", action="/admin/logout"),
              cls="flex justify-between items-center")
    banner = None if live else Div(
        Span("Not live yet.", cls="font-bold"),
        Span(" Customers see a “coming soon” page. Build your menu and settings, then we'll switch it on. "),
        A("Setup checklist →", href="/admin/start", cls="font-semibold underline"),
        cls="mt-3 rounded-xl bg-amber-100 px-3 py-2 text-sm text-amber-900")
    return ui.page(f"{title} · {s['name']} admin", s,
                   Div(top, banner, Div(nav, cls="mt-3"), cls="sticky top-0 z-20 bg-[#faf7f2]/95 backdrop-blur px-4 py-3"),
                   Div(*content, cls="px-4 pt-2"), cls="max-w-5xl")


# ---------------------------------------------------------------- auth

@ar("/login", methods=["get"])
def login_page(req, sess):
    _, con = ctx(req)
    s = db.get_settings(con)
    if sess.get("admin") == req.scope["store"]:
        return RedirectResponse("/admin/queue", status_code=303)
    return ui.page("Admin login", s, Div(ui.card(
        ui.heading(s["name"], "Owner & kitchen login"),
        Form(ui.field("Password", "password", type="password", required=True, autofocus=True,
                      autocomplete="current-password"),
             ui.error_box(None), ui.btn("Log in", type="submit", cls="w-full"),
             hx_post="/admin/login", hx_target="#form-error", hx_swap="outerHTML", cls="grid gap-3"),
        cls="p-6"), cls="max-w-sm mx-auto pt-20 px-4"))


@ar("/login", methods=["post"])
def login(req, sess, password: str = ""):
    import time
    store, con = ctx(req)
    key = f"{store}:{req.client.host if req.client else '?'}"
    recent = [t for t in _login_fail.get(key, []) if time.time() - t < 900]
    if len(recent) >= 8:
        return ui.error_box("Too many attempts. Try again in 15 minutes.")
    if not db.check_admin_password(con, password):
        _login_fail[key] = recent + [time.time()]
        return ui.error_box("Wrong password.")
    _login_fail.pop(key, None)
    log_in(sess, store, con)
    return Response("", headers={"HX-Redirect": "/admin/queue"})


@ar("/welcome", methods=["get"])
def welcome(req, sess, t: str = ""):
    """Single-use hand-off from signup on the bare domain (see signup.py)."""
    store, con = ctx(req)
    if not db.consume_login_token(con, t):
        return RedirectResponse("/admin/login", status_code=303)
    log_in(sess, store, con)
    return RedirectResponse("/admin/start?new=1", status_code=303)


@ar("/start", methods=["get"])
def start(req, new: int = 0):
    import os
    _, con = ctx(req)
    s = db.get_settings(con)
    n_items = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    pays = set(s.get("payments") or [])
    has_pay = ("gcash" in pays and s.get("gcash_number")) or ("bank" in pays and s.get("bank_details"))
    steps = [
        ("Make the menu yours", f"{n_items} sample items are loaded. Edit prices, add photos, or delete what you don't sell.",
         "/admin/menu", "Edit menu", n_items > 0 and bool(s.get("menu_edited"))),
        ("Add your logo, address & hours", "So customers know who you are and when you're open.",
         "/admin/website", "Edit storefront", bool(s.get("logo") and s.get("address"))),
        ("Set up GCash or bank transfer", "Customers pay you directly. Pay-at-counter is on until you add one.",
         "/admin/website", "Add payment details", bool(has_pay)),
        ("Preview your store", "Only you can see it while you're logged in. Place a test order to try the kitchen queue.",
         "/", "Open preview", False),
    ]
    contact = os.environ.get("CONTACT_URL", "").strip()
    live = db.is_live(s)
    rows = [Div(Span("✓" if done else str(i + 1),
                     cls=f"grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold "
                         f"{'bg-emerald-600 text-white' if done else 'bg-stone-900 text-white'}"),
                Div(P(t, cls="font-semibold"), P(d, cls="text-sm text-stone-600"), cls="flex-1"),
                A(lbl, href=href, target="_blank" if href == "/" else None,
                  cls="shrink-0 rounded-full border border-stone-300 bg-white px-3 py-1.5 text-sm font-semibold"),
                cls="flex items-center gap-3 py-3 border-b border-stone-100")
            for i, (t, d, href, lbl, done) in enumerate(steps)]
    golive = ui.card(
        H3("Go live" if not live else "You're live 🎉", cls="font-bold"),
        P("Your store opens to customers once the one-time setup fee is settled. We'll switch it on and your "
          "link starts taking orders. No monthly fees, 0% commission." if not live
          else "Customers can order at your link now.", cls="mt-1 text-sm text-stone-600"),
        A("Message us to go live", href=contact, target="_blank", rel="noopener",
          cls="mt-3 inline-block rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white")
        if contact and not live else None,
        cls="p-4")
    return shell(req, "Setup", "start",
                 Div(H2("Welcome to your store! 👋" if new else "Setup checklist", cls="text-xl font-extrabold"),
                     P(Span("Your link: ", cls="text-stone-500"),
                       A(req.url.hostname, href="/", target="_blank", cls="font-semibold underline")),
                     cls="mb-3"),
                 Div(ui.card(*rows, cls="px-4"), golive, cls="grid md:grid-cols-[2fr_1fr] gap-3 items-start"))


@ar("/logout", methods=["post"])
def logout(sess):
    sess.pop("admin", None)
    sess.pop("admin_ver", None)
    return RedirectResponse("/admin/login", status_code=303)


@ar("/", methods=["get"])
def admin_home():
    return RedirectResponse("/admin/queue", status_code=303)


# ---------------------------------------------------------------- kitchen queue

def fmt_time(ts: str | None) -> str:
    return f"{datetime.fromisoformat(ts):%b %-d · %-I:%M %p}" if ts else ""


NEXT_LABEL = {"preparing": "Start preparing", "ready": "Mark ready", "out_for_delivery": "Out for delivery",
              "completed": "Complete", "cancelled": "Cancel"}


def order_card(o: dict, settings: dict | None = None):
    items = [Div(Span(f"{li['qty']}×", cls="font-extrabold w-8 shrink-0"),
                 Div(P(li["name"], cls="font-semibold"),
                     P(" · ".join(([li["variant_name"]] if li["variant_name"] else []) +
                                  [m["name"] for m in li["modifiers"]]), cls="text-xs text-stone-600"),
                     P(f"“{li['note']}”", cls="text-xs italic text-amber-800") if li["note"] else None),
                 cls="flex gap-1 py-1") for li in o["items"]]
    where = {"dine_in": f"Dine-in{' · T' + o['table_no'] if o['table_no'] else ''}", "pickup": "Pickup",
             "delivery": f"Delivery · {o['zone_name']}", "cod": f"COD · {o['zone_name']}"}[o["mode"]]
    actions = []
    if o["status"] == "pending_payment":
        if o["proof_path"]:
            actions.append(A(Img(src=f"/admin/proof/{o['id']}", cls="w-full max-h-72 object-contain rounded-xl "
                                                                    "border bg-stone-50"),
                             href=f"/admin/proof/{o['id']}", target="_blank"))
        actions.append(P(f"{db.PAY_LABEL[o['payment_method']]} · {o['payment_status']}"
                         + (f" · ref {o['payment_ref']}" if o["payment_ref"] else ""),
                         cls="text-xs text-stone-600"))
        if (due := db.payment_deadline(o, settings or {})):
            actions.append(P(f"⏳ Cancels automatically at {due:%-I:%M %p} if no payment proof arrives",
                             cls="text-xs font-semibold text-amber-800"))
        row = []
        if o["payment_status"] == "submitted":
            row.append(ui.btn("✓ Verify payment", kind="success", hx_post=f"/admin/orders/{o['id']}/verify",
                              hx_target=f"#order-{o['id']}", hx_swap="outerHTML"))
            row.append(ui.btn("Reject", kind="danger", hx_post=f"/admin/orders/{o['id']}/reject",
                              hx_prompt="Reason for rejecting (shown to customer):",
                              hx_target=f"#order-{o['id']}", hx_swap="outerHTML"))
        row.append(ui.btn("Cancel order", kind="ghost", hx_post=f"/admin/orders/{o['id']}/advance?to=cancelled",
                          hx_confirm=f"Cancel {o['code']}? Portions will be restored.",
                          hx_target=f"#order-{o['id']}", hx_swap="outerHTML"))
        actions.append(Div(*row, cls="flex flex-wrap gap-2"))
    else:
        nxt = db.allowed_next(o)
        row = [ui.btn(NEXT_LABEL[t], kind="danger" if t == "cancelled" else "primary",
                      hx_post=f"/admin/orders/{o['id']}/advance?to={t}", hx_target=f"#order-{o['id']}",
                      hx_swap="outerHTML",
                      hx_confirm=f"Cancel {o['code']}? Portions will be restored." if t == "cancelled" else None,
                      cls="flex-1" if t != "cancelled" else "")
               for t in nxt]
        if row:
            actions.append(Div(*row, cls="flex gap-2"))
    pay = ("Paid" if o["payment_status"] == "verified" else
           "Collect " + peso(o["total_cents"]) if o["payment_status"] == "collect" else o["payment_status"])
    return ui.card(
        Div(Div(Span(o["code"], cls="font-mono font-extrabold text-lg"), Span(where, cls="text-sm font-semibold"),
                cls="flex items-baseline gap-2"),
            ui.status_badge(o["status"], db.STATUS_LABEL[o["status"]]), cls="flex justify-between items-center"),
        P(f"{o['customer_name']} · {o['phone']} · placed {fmt_time(o['created_at'])}", cls="text-xs text-stone-500"),
        P(f"⏰ Scheduled {fmt_time(o['scheduled_for'])}", cls="text-sm font-bold text-violet-700")
        if o["scheduled_for"] else None,
        P(f"📍 {o['address']}", cls="text-xs text-stone-600") if o["address"] else None,
        Div(*items, cls="my-2 border-y border-stone-100 py-1"),
        P(f"Note: {o['notes']}", cls="text-xs bg-amber-50 rounded-lg px-2 py-1 mb-2") if o["notes"] else None,
        Div(Span(peso(o["total_cents"]), cls="font-extrabold"), Span(pay, cls="text-xs text-stone-500"),
            cls="flex justify-between items-center mb-2"),
        *actions, cls="p-4", id=f"order-{o['id']}")


def queue_list(con, tab: str):
    orders = db.list_orders(con, tab, limit=60)
    s = db.get_settings(con)
    return Div(*(order_card(o, s) for o in orders) if orders else [ui.empty("Nothing here right now.")],
               id="queue-list", cls="grid sm:grid-cols-2 gap-3 mt-3",
               hx_get=f"/admin/queue/list?tab={tab}", hx_trigger="every 10s", hx_swap="outerHTML")


@ar("/queue", methods=["get"])
def queue(req, tab: str = "preparing"):
    _, con = ctx(req)
    tab = tab if tab in QUEUE_TABS else "preparing"
    counts = db.status_counts(con)
    s = db.get_settings(con)
    tabs = Div(*[A(db.STATUS_LABEL[t] if t != "pending_payment" else "Payments",
                   Span(f" {counts[t]}", cls="font-mono") if counts[t] else None,
                   href=f"/admin/queue?tab={t}",
                   cls=f"shrink-0 px-3 py-2 text-sm font-semibold border-b-2 "
                       f"{'border-brand text-stone-900' if t == tab else 'border-transparent text-stone-500'}")
                 for t in QUEUE_TABS], cls="flex overflow-x-auto no-scrollbar border-b border-stone-200")
    accepting = s.get("accepting_orders", True)
    pause = Button("⏸ Pause online orders" if accepting else "▶ Resume online orders",
                   hx_post="/admin/accepting", hx_swap="outerHTML",
                   cls=f"text-xs font-semibold rounded-full px-3 py-1 "
                       f"{'bg-stone-200' if accepting else 'bg-red-600 text-white'}")
    return shell(req, "Kitchen", "queue",
                 Div(H2("Kitchen queue", cls="text-xl font-extrabold"), pause, cls="flex justify-between items-center"),
                 tabs, queue_list(con, tab))


@ar("/accepting", methods=["post"])
def toggle_accepting(req):
    _, con = ctx(req)
    s = db.get_settings(con)
    db.set_settings(con, {"accepting_orders": not s.get("accepting_orders", True)})
    return RedirectResponse("/admin/queue", status_code=303) if not req.headers.get("hx-request") else \
        Response("", headers={"HX-Refresh": "true"})


@ar("/queue/list", methods=["get"])
def queue_list_route(req, tab: str = "preparing"):
    _, con = ctx(req)
    return queue_list(con, tab if tab in QUEUE_TABS else "preparing")


def _order_action(req, fn, order_id: int, *args):
    _, con = ctx(req)
    try:
        o = fn(con, order_id, *args)
    except db.OrderError as e:
        o = db.get_order(con, order_id)
        return (order_card(o, db.get_settings(con)) if o else Div()), toast(str(e))
    return order_card(o, db.get_settings(con)), toast(f"{o['code']} → {db.STATUS_LABEL[o['status']]}")


@ar("/orders/{order_id}/advance", methods=["post"])
def advance(req, order_id: int, to: str):
    return _order_action(req, db.advance_order, order_id, to)


@ar("/orders/{order_id}/verify", methods=["post"])
def verify(req, order_id: int):
    return _order_action(req, db.verify_payment, order_id)


@ar("/orders/{order_id}/reject", methods=["post"])
def reject(req, order_id: int):
    reason = req.headers.get("hx-prompt") or "Payment could not be verified."
    return _order_action(req, db.reject_payment, order_id, reason)


@ar("/proof/{order_id}", methods=["get"])
def proof(req, order_id: int):
    store, con = ctx(req)
    o = db.get_order(con, order_id)
    p = db.media_file(store, "proofs", o["proof_path"]) if o and o["proof_path"] else None
    if not p:
        return Response("Not found", status_code=404)
    return FileResponse(p, headers={"Cache-Control": "private, no-store"})


# ---------------------------------------------------------------- menu & 86

DRAG = Span("⠿", cls="drag cursor-grab touch-none select-none px-1 text-lg leading-none text-stone-400 "
                    "hover:text-stone-700 active:cursor-grabbing", title="Drag to reorder", aria_hidden="true")


def item_row(it: dict):
    out = bool(it["sold_out"])
    return Div(
        DRAG,
        Div(P(it["name"], cls="font-semibold" + ("" if it["active"] else " line-through text-stone-400")),
            P(peso(it["price_cents"]), " · ",
              A("Edit", href=f"/admin/menu/{it['id']}", cls="underline"), cls="text-xs text-stone-500"),
            cls="flex-1 min-w-0"),
        Form(Input(name="remaining", type="number", min="0", value="" if it["remaining"] is None else it["remaining"],
                   placeholder="∞", cls="w-16 rounded-lg border border-stone-300 px-2 py-1 text-sm text-center"),
             Span(f"/{it['daily_portions']}" if it["daily_portions"] is not None else "", cls="text-xs text-stone-500"),
             hx_post=f"/admin/items/{it['id']}/remaining", hx_trigger="change", hx_target=f"#row-{it['id']}",
             hx_swap="outerHTML", cls="flex items-center gap-1", title="Portions left today (blank = untracked)"),
        Button("86'd" if out else "86", hx_post=f"/admin/items/{it['id']}/86", hx_target=f"#row-{it['id']}",
               hx_swap="outerHTML",
               cls=f"w-16 rounded-xl py-2 text-sm font-extrabold "
                   f"{'bg-stone-900 text-white' if out else 'bg-white border-2 border-stone-900'}",
               title="Tap to toggle Sold Out"),
        id=f"row-{it['id']}", data_id=str(it["id"]), cls=f"flex items-center gap-2.5 py-2.5 border-b border-stone-100 "
                                  f"{'bg-stone-100 -mx-2 px-2 rounded-lg' if out else ''}")


SORTABLE = Script(src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js")
SORT_JS = """
document.querySelectorAll('[data-sort]').forEach(el => new Sortable(el, {
  handle: '.drag', animation: 160, ghostClass: 'opacity-40', delay: 120, delayOnTouchOnly: true,
  onEnd: () => htmx.ajax('POST', el.dataset.sort, {values: {ids: [...el.children].map(c => c.dataset.id)
    .filter(Boolean).join(',')}, swap: 'none'})
}));
"""


def category_card(c: dict, its: list[dict]):
    hidden = not c["active"]
    cid = c["id"]
    head = Div(
        DRAG,
        Form(Input(name="name", value=c["name"], maxlength="60", required=True, aria_label="Category name",
                   title="Click to rename",
                   cls="w-full min-w-0 rounded-lg border border-transparent bg-transparent px-1.5 py-1 font-bold "
                       "hover:border-stone-200 focus:border-stone-300 focus:bg-white focus:outline-none"),
             hx_post=f"/admin/categories/{cid}/rename", hx_trigger="change", hx_swap="none", cls="min-w-0 flex-1"),
        Span(f"{len(its)}", cls="rounded-full bg-stone-100 px-2 py-0.5 text-xs font-semibold text-stone-500",
             title="Items"),
        Button("Hidden" if hidden else "Visible", hx_post=f"/admin/categories/{cid}/toggle", hx_swap="none",
               title="Show or hide this whole category on your store",
               cls=f"rounded-full px-2.5 py-1 text-xs font-bold "
                   f"{'bg-stone-900 text-white' if hidden else 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'}"),
        Button("🗑", hx_post=f"/admin/categories/{cid}/delete", hx_swap="none", aria_label="Delete category",
               hx_confirm=f"Delete the category “{c['name']}”?", title="Delete (only when empty)",
               cls="rounded-full px-2 py-1 text-sm hover:bg-red-50"),
        cls="flex items-center gap-1.5")
    rows = Div(*[item_row(i) for i in its], data_sort=f"/admin/categories/{cid}/items/order", cls="mt-1")
    empty = P("No items yet. ", A("+ Add one", href=f"/admin/menu/new?category={cid}", cls="underline"),
              cls="py-3 text-sm text-stone-500") if not its else None
    return Div(ui.card(head, rows, empty, cls=f"p-4 {'opacity-60' if hidden else ''}"), data_id=str(cid))


@ar("/menu", methods=["get"])
def menu(req):
    _, con = ctx(req)
    s = db.get_settings(con)
    cats = db.categories(con, include_inactive=True)
    its = db.items(con, include_inactive=True)
    last = s.get("last_portion_reset")
    groups = [category_card(c, [i for i in its if i["category_id"] == c["id"]]) for c in cats]
    return shell(req, "Menu", "menu",
                 Div(H2("Menu & 86 board", cls="text-xl font-extrabold"),
                     Div(ui.link_btn("+ Item", href="/admin/menu/new", kind="dark"),
                         ui.btn("Reset daily portions", kind="ghost", hx_post="/admin/menu/reset",
                                hx_confirm="Reset every item to its daily portions and clear all 86 flags?"),
                         cls="flex gap-2"),
                     cls="flex flex-wrap justify-between items-center gap-2"),
                 P("Tap 86 to mark sold out. Edit the number to set portions left today (blank = unlimited).",
                   f" Last reset: {fmt_time(last)}." if last else "", cls="text-xs text-stone-500 mt-1"),
                 P("⠿ Drag categories and items to change their order on your store. Click a category name to "
                   "rename it.", cls="text-xs text-stone-500"),
                 Div(*groups, data_sort="/admin/categories/order", cls="grid gap-3 mt-3 md:grid-cols-2"),
                 ui.card(Form(ui.field("New category", "name", required=True, maxlength="60"),
                              ui.btn("Add category", kind="ghost"), method="post", action="/admin/categories",
                              cls="flex gap-2 items-end"), cls="p-4 mt-3"),
                 SORTABLE, Script(SORT_JS))


def _ids(raw: str) -> list[int]:
    return [int(x) for x in (raw or "").split(",") if x.strip().isdigit()][:500]


@ar("/categories/order", methods=["post"])
def order_categories(req, ids: str = ""):
    _, con = ctx(req)
    db.reorder_categories(con, _ids(ids))
    return toast_only("Category order saved")


@ar("/categories/{cat_id}/items/order", methods=["post"])
def order_items(req, cat_id: int, ids: str = ""):
    _, con = ctx(req)
    db.reorder_items(con, cat_id, _ids(ids))
    return toast_only("Item order saved")


@ar("/categories/{cat_id}/rename", methods=["post"])
def rename_category(req, cat_id: int, name: str = ""):
    _, con = ctx(req)
    try:
        db.update_category(con, cat_id, name=name)
    except db.OrderError as e:
        return toast_only(str(e))
    return toast_only(f"Renamed to “{name.strip()[:60]}”")


@ar("/categories/{cat_id}/toggle", methods=["post"])
def toggle_category(req, cat_id: int):
    _, con = ctx(req)
    c = next((c for c in db.categories(con, True) if c["id"] == cat_id), None)
    if c:
        db.update_category(con, cat_id, active=not c["active"])
    return Response("", headers={"HX-Refresh": "true"})


@ar("/categories/{cat_id}/delete", methods=["post"])
def remove_category(req, cat_id: int):
    _, con = ctx(req)
    try:
        db.delete_category(con, cat_id)
    except db.OrderError as e:
        return toast_only(str(e))
    return Response("", headers={"HX-Refresh": "true"})


@ar("/items/{item_id}/86", methods=["post"])
def toggle_86(req, item_id: int):
    _, con = ctx(req)
    it = db.get_item(con, item_id, with_options=False)
    if not it:
        return Response("", status_code=404)
    it = db.set_sold_out(con, item_id, not it["sold_out"])
    return item_row(it), toast(f"{it['name']}: {'86 / Sold out' if it['sold_out'] else 'back on'}")


@ar("/items/{item_id}/remaining", methods=["post"])
def set_remaining(req, item_id: int, remaining: str = ""):
    _, con = ctx(req)
    try:
        val = None if remaining.strip() == "" else int(remaining)
        it = db.set_remaining(con, item_id, val)
    except (ValueError, db.OrderError) as e:
        return item_row(db.get_item(con, item_id, False)), toast(str(e) if isinstance(e, db.OrderError) else "Invalid")
    return item_row(it), toast(f"{it['name']}: {'unlimited' if val is None else val} left")


@ar("/menu/reset", methods=["post"])
def reset(req):
    _, con = ctx(req)
    n = db.reset_daily_portions(con)
    return Response("", headers={"HX-Refresh": "true", "HX-Trigger": json.dumps({"toast": f"Reset {n} items"})})


@ar("/categories", methods=["post"])
def add_category(req, name: str = ""):
    _, con = ctx(req)
    try:
        db.upsert_category(con, name, sort=len(db.categories(con, True)))
    except db.OrderError:
        pass
    return RedirectResponse("/admin/menu", status_code=303)


# ---- item editor (variants / modifier groups as simple text lines)

def variants_text(it):
    return "\n".join(f"{v['name']} | {v['price_delta_cents'] / 100:g}" for v in it.get("variants", []))


def groups_text(it):
    lines = []
    for g in it.get("groups", []):
        opts = ", ".join(f"{m['name']} +{m['price_delta_cents'] / 100:g}" for m in g["options"])
        lines.append(f"{g['name']} ({g['min_select']}-{g['max_select']}): {opts}")
    return "\n".join(lines)


def _money(s: str) -> int:
    s = (s or "").replace("₱", "").replace(",", "").strip()
    return int(round(float(s or 0) * 100))


def parse_variants(text: str) -> list[dict]:
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        name, _, price = line.partition("|")
        out.append({"name": name.strip(), "price_delta_cents": _money(price)})
    return out


GROUP_RE = re.compile(r"^(?P<name>[^(:]+?)\s*(?:\((?P<min>\d+)\s*-\s*(?P<max>\d+)\))?\s*:\s*(?P<opts>.+)$")
OPT_RE = re.compile(r"^(?P<name>.+?)(?:\s*\+\s*₱?(?P<price>-?[\d.,]+))?$")


def parse_groups(text: str) -> list[dict]:
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        m = GROUP_RE.match(line.strip())
        if not m:
            raise db.OrderError(f"Can't read add-on line: “{line.strip()}”. Use  Name (min-max): Opt +10, Opt2")
        opts = []
        for o in m["opts"].split(","):
            om = OPT_RE.match(o.strip())
            if om and om["name"].strip():
                opts.append({"name": om["name"].strip(), "price_delta_cents": _money(om["price"] or "0")})
        out.append({"name": m["name"].strip(), "min_select": int(m["min"] or 0), "max_select": int(m["max"] or 1),
                    "options": opts})
    return out


NEW_ITEM = {"id": None, "category_id": None, "name": "", "description": "", "price_cents": 0, "tags": [],
            "allergens": [], "daily_portions": None, "active": 1, "sort": 0, "image": None,
            "variants": [], "groups": []}


def item_form(con, it: dict | None, err: str | None = None, raw: dict | None = None):
    it = it or NEW_ITEM
    raw = raw or {}
    cats = db.categories(con, include_inactive=True)
    action = f"/admin/menu/{it['id']}" if it.get("id") else "/admin/menu/new"
    return Form(
        ui.error_box(err),
        Div(ui.field("Name", "name", it["name"], required=True, maxlength="80"),
            ui.select("Category", "category_id", [(c["id"], c["name"]) for c in cats], it["category_id"]),
            ui.field("Base price (₱)", "price", f"{it['price_cents'] / 100:g}", type="number", step="0.01", min="0",
                     required=True),
            ui.field("Daily portions", "daily_portions",
                     "" if it["daily_portions"] is None else it["daily_portions"], type="number", min="0",
                     hint="Blank = unlimited. Reset each morning from the Menu tab."),
            cls="grid sm:grid-cols-2 gap-3"),
        ui.field("Description", "description", it["description"], type="textarea", maxlength="400"),
        Div(Span("Badges", cls="block text-sm font-medium mb-1"),
            Div(*[Label(Input(type="checkbox", name="tags", value=t, checked=t in it["tags"]), ui.TAG_LABEL[t],
                        cls="flex items-center gap-1.5 text-sm") for t in TAG_CHOICES], cls="flex flex-wrap gap-4")),
        ui.field("Allergens (comma separated)", "allergens", ", ".join(it["allergens"]),
                 placeholder="milk, egg, peanuts, shellfish, gluten"),
        ui.field("Variants / sizes", "variants", raw.get("variants", variants_text(it)), type="textarea",
                 hint="One per line:  Regular | 0   ·   Large | 20   (price added to base). Blank = none."),
        ui.field("Add-on groups", "groups", raw.get("groups", groups_text(it)), type="textarea",
                 hint="One group per line:  Sinkers (0-3): Pearls +15, Nata +15   ·   "
                      "Sugar level (1-1): 25%, 50%, 100%   (min-max picks)"),
        Div(Label(Span("Photo", cls="block text-sm font-medium mb-1"),
                  Input(type="file", name="image", accept="image/*", cls="text-sm")),
            Img(src=f"/media/{it['image']}", cls="w-20 h-20 rounded-xl object-cover") if it.get("image") else None,
            cls="flex items-end gap-4"),
        Div(Label(Input(type="checkbox", name="active", value="1", checked=bool(it["active"])), "Show on menu",
                  cls="flex items-center gap-1.5 text-sm"),
            P("Drag ⠿ on the Menu page to change the order.", cls="text-xs text-stone-500"),
            cls="grid grid-cols-2 gap-3 items-end"),
        ui.btn("Save item", type="submit", cls="w-full"),
        method="post", action=action, enctype="multipart/form-data", cls="grid gap-4")


@ar("/menu/new", methods=["get"])
def new_item(req, category: int = 0):
    _, con = ctx(req)
    if not db.categories(con, True):
        return RedirectResponse("/admin/menu", status_code=303)
    return shell(req, "New item", "menu", A("← Menu", href="/admin/menu", cls="text-sm"),
                 ui.heading("New item"),
                 ui.card(item_form(con, {**NEW_ITEM, "category_id": category or None}), cls="p-4 max-w-2xl"))


@ar("/menu/{item_id}", methods=["get"])
def edit_item(req, item_id: int):
    _, con = ctx(req)
    it = db.get_item(con, item_id)
    if not it:
        return RedirectResponse("/admin/menu", status_code=303)
    return shell(req, it["name"], "menu", A("← Menu", href="/admin/menu", cls="text-sm"),
                 ui.heading(f"Edit {it['name']}"), ui.card(item_form(con, it), cls="p-4 max-w-2xl"))


async def _save_item(req, item_id: int | None):
    store, con = ctx(req)
    form = await req.form()
    data = {
        "name": form.get("name", ""), "category_id": int(form.get("category_id") or 0),
        "description": form.get("description", ""), "tags": [t for t in form.getlist("tags") if t in TAG_CHOICES],
        "allergens": [a.strip().lower()[:30] for a in (form.get("allergens") or "").split(",") if a.strip()][:12],
        "daily_portions": form.get("daily_portions") or None, "active": form.get("active") == "1",
    }
    old = db.get_item(con, item_id, with_options=False) if item_id else None
    if old and old["category_id"] == data["category_id"]:
        data["sort"] = old["sort"]
    else:  # new item, or moved to another category → goes to the end of that category
        data["sort"] = 1 + (con.execute("SELECT COALESCE(MAX(sort), -1) FROM items WHERE category_id=?",
                                        (data["category_id"],)).fetchone()[0])
    try:
        data["price_cents"] = _money(form.get("price"))
        data["variants"] = parse_variants(form.get("variants"))
        data["groups"] = parse_groups(form.get("groups"))
        up = form.get("image")
        if up is not None and hasattr(up, "read"):
            raw = await up.read()
            if raw:
                data["image"] = db.save_image(store, "media", raw)
        new_id = db.save_item(con, data, item_id)
    except (db.OrderError, ValueError) as e:
        base = (db.get_item(con, item_id) if item_id else None) or NEW_ITEM
        it = {**base, **{k: v for k, v in data.items() if k not in ("variants", "groups", "image")}}
        msg = str(e) if isinstance(e, db.OrderError) else "Check the numbers you entered."
        raw_text = {"variants": form.get("variants", ""), "groups": form.get("groups", "")}
        return shell(req, "Edit item", "menu", A("← Menu", href="/admin/menu", cls="text-sm"),
                     ui.heading(it["name"] or "New item"), ui.card(item_form(con, it, msg, raw_text), cls="p-4 max-w-2xl"))
    if not db.get_settings(con).get("menu_edited"):
        db.set_settings(con, {"menu_edited": True})  # setup checklist step 1
    return RedirectResponse(f"/admin/menu#row-{new_id}", status_code=303)


@ar("/menu/new", methods=["post"])
async def create_item(req):
    return await _save_item(req, None)


@ar("/menu/{item_id}", methods=["post"])
async def update_item(req, item_id: int):
    return await _save_item(req, item_id)


# ---------------------------------------------------------------- customers

@ar("/customers", methods=["get"])
def customers(req):
    _, con = ctx(req)
    rows = db.list_customers(con)
    table = Table(
        Thead(Tr(*[Th(h, cls="text-left px-3 py-2 text-xs uppercase text-stone-500") for h in
                   ("Name", "Mobile", "Orders", "Spent", "Last order")])),
        Tbody(*[Tr(Td(c["name"], cls="px-3 py-2 font-medium"), Td(c["phone"], cls="px-3 py-2 font-mono text-sm"),
                   Td(c["orders_count"], cls="px-3 py-2"), Td(peso(c["total_spent_cents"]), cls="px-3 py-2"),
                   Td(fmt_time(c["last_order_at"]), cls="px-3 py-2 text-sm text-stone-500"),
                   cls="border-t border-stone-100") for c in rows]),
        cls="w-full")
    return shell(req, "Customers", "customers", H2("Customers", cls="text-xl font-extrabold mb-3"),
                 ui.card(Div(table, cls="overflow-x-auto") if rows else ui.empty("No customers yet."), cls="p-2"))


# ---------------------------------------------------------------- insights

def bar_rows(pairs: list[tuple[str, int]], fmt=str):
    top = max([v for _, v in pairs] or [0]) or 1
    return Div(*[Div(Span(k, cls="w-24 shrink-0 text-xs text-stone-600 truncate"),
                     Div(Div(cls="h-full rounded bg-brand", style=f"width:{max(2, v * 100 // top)}%"),
                         cls="flex-1 h-4 bg-stone-100 rounded"),
                     Span(fmt(v), cls="w-20 text-right text-xs font-semibold"), cls="flex items-center gap-2")
                 for k, v in pairs], cls="grid gap-1.5")


@ar("/insights", methods=["get"])
def insights(req, days: int = 7):
    _, con = ctx(req)
    days = days if days in (1, 7, 30) else 7
    r = db.sales_summary(con, days)
    stat = lambda label, val: ui.card(P(label, cls="text-xs text-stone-500"), P(val, cls="text-2xl font-extrabold"),
                                      cls="p-4")
    picker = Div(*[A({1: "Today", 7: "7 days", 30: "30 days"}[d], href=f"/admin/insights?days={d}",
                     cls=f"px-3 py-1 rounded-full text-sm {'bg-stone-900 text-white' if d == days else 'bg-white border'}")
                   for d in (1, 7, 30)], cls="flex gap-2")
    by_day = [(datetime.fromisoformat(d).strftime("%a %-d"), v) for d, v in r["by_day"].items()]
    return shell(req, "Insights", "insights",
                 Div(H2("Sales insights", cls="text-xl font-extrabold"), picker,
                     cls="flex flex-wrap justify-between items-center gap-2 mb-3"),
                 Div(stat("Revenue", peso(r["revenue_cents"])), stat("Orders", str(r["orders"])),
                     stat("Avg order", peso(r["aov_cents"])), stat("Cancelled", str(r["cancelled"])),
                     cls="grid grid-cols-2 md:grid-cols-4 gap-3"),
                 Div(ui.card(H3("Revenue by day", cls="font-bold mb-2"), bar_rows(by_day, peso), cls="p-4")
                     if days > 1 else None,
                     ui.card(H3("Top items", cls="font-bold mb-2"),
                             bar_rows([(t["name"], t["qty"]) for t in r["top_items"]], lambda v: f"{v} sold")
                             if r["top_items"] else P("No sales yet.", cls="text-sm text-stone-500"), cls="p-4"),
                     ui.card(H3("By order type", cls="font-bold mb-2"),
                             bar_rows([(db.MODE_LABEL[m], n) for m, n in r["by_mode"].items()], lambda v: f"{v}")
                             if r["by_mode"] else P("—", cls="text-sm text-stone-500"), cls="p-4"),
                     ui.card(H3("Busy hours", cls="font-bold mb-2"),
                             bar_rows([(f"{h % 12 or 12}{'am' if h < 12 else 'pm'}", n)
                                       for h, n in sorted(r["by_hour"].items())], lambda v: f"{v}")
                             if r["by_hour"] else P("—", cls="text-sm text-stone-500"), cls="p-4"),
                     cls="grid md:grid-cols-2 gap-3 mt-3"))


# ---------------------------------------------------------------- website editor

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@ar("/website", methods=["get"])
def website(req, saved: int = 0, pw: str = ""):
    _, con = ctx(req)
    s = db.get_settings(con)
    hours = s.get("hours") or {}
    zones = db.delivery_zones(con)
    hours_rows = [Div(Span(DAYS[d], cls="w-10 text-sm font-medium"),
                      Input(type="time", name=f"open_{d}", value=(hours.get(str(d)) or ["", ""])[0], cls=ui.INPUT_CLS),
                      Input(type="time", name=f"close_{d}", value=(hours.get(str(d)) or ["", ""])[1], cls=ui.INPUT_CLS),
                      cls="flex items-center gap-2") for d in range(7)]
    store_form = Form(
        P("✓ Saved", cls="text-emerald-700 font-semibold") if saved == 1 else None,
        H3("Storefront", cls="font-bold"),
        Div(ui.field("Store name", "name", s["name"], required=True, maxlength="60"),
            ui.field("Tagline", "tagline", s.get("tagline", ""), maxlength="120"),
            ui.field("Brand color", "brand_color", s["brand_color"], type="color"),
            ui.field("Accent color", "accent_color", s["accent_color"], type="color"),
            ui.field("Address", "address", s.get("address", ""), maxlength="200"),
            ui.field("Contact phone", "contact_phone", s.get("contact_phone", ""), maxlength="30"),
            cls="grid sm:grid-cols-2 gap-3"),
        ui.field("Announcement banner", "announcement", s.get("announcement", ""), maxlength="200",
                 hint="e.g. Free delivery within Poblacion this week!"),
        Label(Span("Logo", cls="block text-sm font-medium mb-1"), Input(type="file", name="logo", accept="image/*",
                                                                         cls="text-sm")),
        H3("Homepage", cls="font-bold mt-2"),
        P("Your link opens on a homepage that shows off your best sellers and menu, with Order buttons. ",
          A("View it ↗", href="/", target="_blank", cls="underline"), cls="text-xs text-stone-500"),
        ui.field("Headline", "hero_title", s.get("hero_title", ""), maxlength="90",
                 placeholder=s["name"], hint="The big line at the top, e.g. “Ceremonial matcha & bread from our oven.”"),
        ui.field("About us", "about", s.get("about", ""), type="textarea", maxlength="1200",
                 hint="Your story in a few lines. Leave blank to hide the section."),
        Label(Span("Cover photo", cls="block text-sm font-medium mb-1"),
              Input(type="file", name="cover", accept="image/*", cls="text-sm"),
              P("Optional. Without one, your best sellers are shown instead.", cls="text-xs text-stone-500 mt-1"),
              cls="block"),
        Label(Input(type="checkbox", name="remove_cover", value="1"), "Remove cover photo",
              cls="flex items-center gap-1.5 text-sm") if s.get("cover") else None,
        Div(ui.field("Facebook page URL", "facebook", s.get("facebook", ""), type="url", maxlength="200",
                     placeholder="https://facebook.com/…"),
            ui.field("Instagram URL", "instagram", s.get("instagram", ""), type="url", maxlength="200",
                     placeholder="https://instagram.com/…"),
            cls="grid sm:grid-cols-2 gap-3"),
        H3("Order types & payment", cls="font-bold mt-2"),
        Div(*[Label(Input(type="checkbox", name="modes", value=m, checked=m in s["modes"]), db.MODE_LABEL[m],
                    cls="flex items-center gap-1.5 text-sm") for m in db.MODES], cls="flex flex-wrap gap-4"),
        Div(*[Label(Input(type="checkbox", name="payments", value=p, checked=p in s["payments"]), db.PAY_LABEL[p],
                    cls="flex items-center gap-1.5 text-sm") for p in ("gcash", "bank", "counter")],
            cls="flex flex-wrap gap-4"),
        Div(ui.field("GCash account name", "gcash_name", s.get("gcash_name", ""), maxlength="60"),
            ui.field("GCash number", "gcash_number", s.get("gcash_number", ""), maxlength="20"),
            cls="grid sm:grid-cols-2 gap-3"),
        ui.field("Bank transfer details", "bank_details", s.get("bank_details", ""), type="textarea", maxlength="300"),
        H3("Kitchen hours", cls="font-bold mt-2"),
        P("Leave both blank for closed days.", cls="text-xs text-stone-500"),
        Div(*hours_rows, cls="grid gap-2"),
        Div(ui.field("Prep time (min)", "prep_minutes", s.get("prep_minutes", 20), type="number", min="0", max="240"),
            ui.field("Slot interval (min)", "slot_minutes", s.get("slot_minutes", 30), type="number", min="10",
                     max="120"), cls="grid grid-cols-2 gap-3"),
        ui.field("Time to pay for GCash / bank orders (min)", "payment_window_minutes", db.payment_window(s),
                 type="number", min="5", max="1440",
                 hint="Unpaid orders are cancelled after this, so their portions go back on the menu."),
        ui.btn("Save storefront", type="submit"),
        method="post", action="/admin/website", enctype="multipart/form-data", cls="grid gap-3")
    zone_list = [Div(Span(f"{z['name']} · {peso(z['fee_cents'])} · min {peso(z['min_order_cents'])} · "
                          f"~{z['eta_minutes']} min", cls="text-sm"),
                     Form(Button("Remove", cls="text-xs text-red-700"), method="post",
                          action=f"/admin/zones/{z['id']}/delete"),
                     cls="flex justify-between py-2 border-b border-stone-100") for z in zones]
    zone_form = Form(Div(ui.field("Area", "name", required=True, maxlength="60"),
                         ui.field("Fee ₱", "fee", type="number", min="0", step="1", required=True),
                         ui.field("Min order ₱", "min_order", "0", type="number", min="0"),
                         ui.field("ETA min", "eta", "45", type="number", min="5"),
                         cls="grid grid-cols-2 sm:grid-cols-4 gap-2"),
                     ui.btn("Add zone", kind="ghost"), method="post", action="/admin/zones", cls="grid gap-2 mt-3")
    pw_form = Form(
        P("✓ Password changed. Every other device has been logged out.", cls="text-sm font-semibold text-emerald-700")
        if saved == 4 else None,
        ui.error_box(PW_ERRORS.get(pw), "pw-error"),
        ui.field("Current password", "current", type="password", required=True, autocomplete="current-password"),
        ui.field("New password", "password", type="password", minlength="8", maxlength="128", required=True,
                 autocomplete="new-password", hint="At least 8 characters."),
        ui.field("Repeat new password", "confirm", type="password", minlength="8", maxlength="128", required=True,
                 autocomplete="new-password"),
        P("Changing it logs out every other phone or tablet, e.g. when a staff member leaves.",
          cls="text-xs text-stone-500"),
        ui.btn("Change password", kind="ghost"), method="post", action="/admin/password", cls="grid gap-3")
    return shell(req, "Website", "website", H2("Website editor", cls="text-xl font-extrabold mb-3"),
                 Div(ui.card(store_form, cls="p-4"),
                     Div(ui.card(home_form(s, saved == 2), cls="p-4"),
                         ui.card(chat_settings_form(s, saved == 3), cls="p-4"),
                         ui.card(H3("Delivery zones", cls="font-bold"), *zone_list, zone_form, cls="p-4"),
                         ui.card(H3("Security", cls="font-bold mb-2"), pw_form, cls="p-4", id="security"), cls="grid gap-3 content-start"),
                     cls="grid md:grid-cols-2 gap-3"))


def home_form(s: dict, saved: bool):
    import storehome
    cur = s.get("home") if isinstance(s.get("home"), dict) else {}
    blocks = []
    for key, label, toggle, texts in storehome.HOME_SECTIONS:
        on = bool(cur.get(f"show_{key}", True))
        head = (Label(Input(type="checkbox", name=f"show_{key}", value="1", checked=on, cls="size-4"),
                      Span(label, cls="font-semibold"), cls="flex items-center gap-2 text-sm")
                if toggle else P(label, cls="text-sm font-semibold"))
        fields = [ui.field(tlabel, tkey, cur.get(tkey, ""), maxlength="120",
                           placeholder=default.replace("{name}", s["name"])) for tkey, tlabel, default in texts]
        blocks.append(Div(head, Div(*fields, cls="mt-2 grid gap-2 sm:grid-cols-2") if fields else None,
                          cls="rounded-2xl border border-stone-200 p-3"))
    return Form(
        Div(H3("Homepage sections", cls="font-bold"),
            A("View ↗", href="/", target="_blank", cls="text-xs underline"), cls="flex items-baseline justify-between"),
        P("Turn sections on or off and change their text. Leave a box empty to use the text shown in grey. "
          "Type {name} for your store name.", cls="text-xs text-stone-500"),
        P("✓ Saved", cls="font-semibold text-emerald-700") if saved else None,
        *blocks,
        ui.btn("Save homepage", type="submit"),
        method="post", action="/admin/website/home", id="home-settings", cls="grid scroll-mt-20 gap-3")


def chat_settings_form(s: dict, saved: bool):
    sugg = ai.parse_suggestions(s.get("chat_suggestions"))
    default_lines = "\n".join(f"{lbl} | {q}" for lbl, q in ai.default_suggestions(s))
    return Form(
        H3("Chat assistant", cls="font-bold"),
        P("What customers see when they tap “💬 Ask us”.", cls="text-xs text-stone-500"),
        P("✓ Saved", cls="font-semibold text-emerald-700") if saved else None,
        ui.field("Greeting", "chat_greeting", s.get("chat_greeting", ""), type="textarea", maxlength="400",
                 placeholder=ai.default_greeting(s["name"])),
        ui.field("Suggestion buttons", "chat_suggestions", "\n".join(f"{lbl} | {q}" for lbl, q in sugg),
                 type="textarea", maxlength="1200", placeholder=default_lines, rows="7",
                 hint="One per line: Button text | Question it sends. Up to 8. Leave empty for the defaults."),
        ui.btn("Save chat", type="submit"),
        method="post", action="/admin/website/chat", id="chat-settings", cls="grid scroll-mt-20 gap-3")


@ar("/website/home", methods=["post"])
async def save_home(req):
    import storehome
    _, con = ctx(req)
    form = await req.form()
    home = {}
    for key, _, toggle, texts in storehome.HOME_SECTIONS:
        if toggle:
            home[f"show_{key}"] = form.get(f"show_{key}") == "1"
        for tkey, _, _ in texts:
            if (v := " ".join((form.get(tkey) or "").split())[:120]):
                home[tkey] = v
    db.set_settings(con, {"home": home})
    return RedirectResponse("/admin/website?saved=2#home-settings", status_code=303)


@ar("/website/chat", methods=["post"])
async def save_chat(req):
    _, con = ctx(req)
    form = await req.form()
    db.set_settings(con, {"chat_greeting": (form.get("chat_greeting") or "").strip()[:400],
                          "chat_suggestions": [list(x) for x in ai.parse_suggestions(form.get("chat_suggestions") or "")]})
    return RedirectResponse("/admin/website?saved=3#chat-settings", status_code=303)


@ar("/website", methods=["post"])
async def save_website(req):
    store, con = ctx(req)
    form = await req.form()
    hours = {}
    for d in range(7):
        o, c = form.get(f"open_{d}") or "", form.get(f"close_{d}") or ""
        hours[str(d)] = [o, c] if re.fullmatch(r"\d\d:\d\d", o) and re.fullmatch(r"\d\d:\d\d", c) else None
    clamp = lambda v, lo, hi, dflt: max(lo, min(hi, int(v))) if str(v or "").isdigit() else dflt
    vals = {
        "name": (form.get("name") or "My Kitchen").strip()[:60],
        "tagline": (form.get("tagline") or "").strip()[:120],
        "brand_color": form.get("brand_color") if ui.HEX.match(form.get("brand_color") or "") else "#c2410c",
        "accent_color": form.get("accent_color") if ui.HEX.match(form.get("accent_color") or "") else "#fef3c7",
        "address": (form.get("address") or "").strip()[:200],
        "contact_phone": (form.get("contact_phone") or "").strip()[:30],
        "announcement": (form.get("announcement") or "").strip()[:200],
        "hero_title": (form.get("hero_title") or "").strip()[:90],
        "about": (form.get("about") or "").strip()[:1200],
        "facebook": u if (u := (form.get("facebook") or "").strip()[:200]).startswith("https://") else "",
        "instagram": u if (u := (form.get("instagram") or "").strip()[:200]).startswith("https://") else "",
        "modes": [m for m in form.getlist("modes") if m in db.MODES] or ["pickup"],
        "payments": [p for p in form.getlist("payments") if p in ("gcash", "bank", "counter")] or ["counter"],
        "gcash_name": (form.get("gcash_name") or "").strip()[:60],
        "gcash_number": (form.get("gcash_number") or "").strip()[:20],
        "bank_details": (form.get("bank_details") or "").strip()[:300],
        "hours": hours,
        "prep_minutes": clamp(form.get("prep_minutes"), 0, 240, 20),
        "slot_minutes": clamp(form.get("slot_minutes"), 10, 120, 30),
        "payment_window_minutes": clamp(form.get("payment_window_minutes"), 5, 1440, 30),
    }
    for key in ("logo", "cover"):
        up = form.get(key)
        if up is not None and hasattr(up, "read"):
            raw = await up.read()
            if raw:
                try:
                    vals[key] = db.save_image(store, "media", raw)
                except db.OrderError:
                    pass
    if form.get("remove_cover") and "cover" not in vals:
        vals["cover"] = ""
    db.set_settings(con, vals)
    return RedirectResponse("/admin/website?saved=1", status_code=303)


@ar("/zones", methods=["post"])
def add_zone(req, name: str = "", fee: str = "0", min_order: str = "0", eta: str = "45"):
    _, con = ctx(req)
    try:
        db.save_zone(con, name, _money(fee), _money(min_order), int(eta or 45))
    except (db.OrderError, ValueError):
        pass
    return RedirectResponse("/admin/website", status_code=303)


@ar("/zones/{zone_id}/delete", methods=["post"])
def remove_zone(req, zone_id: int):
    _, con = ctx(req)
    db.delete_zone(con, zone_id)
    return RedirectResponse("/admin/website", status_code=303)


PW_ERRORS = {"current": "Your current password is wrong.", "match": "The two new passwords don't match.",
             "same": "Choose a password different from the current one.",
             "length": "The new password must be 8–128 characters."}


@ar("/password", methods=["post"])
def change_password(req, sess, current: str = "", password: str = "", confirm: str = ""):
    import time
    store, con = ctx(req)
    key = f"pw:{store}:{req.client.host if req.client else '?'}"
    recent = [t for t in _login_fail.get(key, []) if time.time() - t < 900]
    if len(recent) >= 8:
        return RedirectResponse("/admin/website?pw=current#security", status_code=303)
    try:
        sess["admin_ver"] = db.change_admin_password(con, current, password, confirm)
    except db.OrderError as e:
        msg = str(e)
        if msg == PW_ERRORS["current"]:
            _login_fail[key] = recent + [time.time()]
        code = next((k for k, v in PW_ERRORS.items() if v == msg), "length")
        return RedirectResponse(f"/admin/website?pw={code}#security", status_code=303)
    return RedirectResponse("/admin/website?saved=4#security", status_code=303)


# ---------------------------------------------------------------- QR codes (tables, posters, social)

def _store_link(req, table: str = "") -> str:
    base = f"{req.url.scheme}://{req.url.netloc}/"
    return base + (f"?table={table}" if table else "")


def _qr_svg(data: str, scale: int = 5) -> str:
    import segno
    return segno.make(data, error="m").svg_inline(scale=scale, border=2, dark="#1c1917", omitsize=True)


QR_PRINT_CSS = """
@media print {
  .no-print, .sticky { display: none !important; }
  body { background: #fff !important; }
  .qr-sheet { gap: 0 !important; }
  .qr-card { break-inside: avoid; box-shadow: none !important; border: 1px dashed #d6d3d1 !important; border-radius: 0 !important; }
}
.qr-card svg { width: 100%; height: auto; }
"""


@ar("/qr", methods=["get"])
def qr_page(req, tables: str = ""):
    from fasthtml.common import NotStr, Style
    _, con = ctx(req)
    s = db.get_settings(con)
    n = int(tables) if tables.isdigit() else int(s.get("table_count") or 10)
    n = max(1, min(n, 100))
    if tables.isdigit() and n != s.get("table_count"):
        db.set_settings(con, {"table_count": n})
    link = _store_link(req)
    poster = ui.card(
        Div(Div(NotStr(_qr_svg(link, 8)), cls="qr-card w-48 shrink-0"),
            Div(H3("Store QR & link", cls="font-bold"),
                P("For the counter, posters, flyers and delivery bags. Share the link on Facebook, Instagram and "
                  "Messenger, and customers order the same way.", cls="mt-1 text-sm text-stone-600"),
                Div(Input(value=link, readonly=True, onclick="this.select()", cls=ui.INPUT_CLS + " text-sm"),
                    Button("Copy", type="button", cls="rounded-xl bg-stone-900 px-3 text-sm font-semibold text-white",
                           onclick=f"navigator.clipboard.writeText({json.dumps(link)});this.textContent='Copied ✓'"),
                    cls="mt-3 flex gap-2"),
                A("Download QR (SVG)", href="/admin/qr/download", cls="mt-2 inline-block text-sm font-semibold underline"),
                cls="min-w-0 flex-1"),
            cls="flex flex-col sm:flex-row gap-5 items-start"),
        cls="p-4 no-print")
    cards = [Div(P(s["name"], cls="font-extrabold text-center truncate"),
                 Div(NotStr(_qr_svg(_store_link(req, str(t)), 5)), cls="mt-2"),
                 P("Scan to order", cls="text-center text-sm font-semibold"),
                 P(f"Table {t}", cls="mt-1 text-center text-2xl font-extrabold text-brand"),
                 cls="qr-card rounded-2xl border border-stone-200 bg-white p-4 shadow-sm")
             for t in range(1, n + 1)]
    controls = Form(ui.field("Number of tables", "tables", str(n), type="number", min="1", max="100"),
                    ui.btn("Update", kind="ghost", type="submit"),
                    ui.btn("🖨 Print table cards", type="button", onclick="window.print()"),
                    method="get", action="/admin/qr", cls="no-print flex flex-wrap items-end gap-2")
    return shell(req, "QR codes", "qr", Style(QR_PRINT_CSS),
                 H2("QR codes", cls="no-print text-xl font-extrabold mb-1"),
                 P("Customers scan, see your menu and order from their phone. Table QR codes fill in the table "
                   "number automatically, so dine-in orders show up in your kitchen queue with the table.",
                   cls="no-print text-sm text-stone-600 mb-3"),
                 poster,
                 Div(H3("Table cards", cls="font-bold"), controls, cls="no-print mt-5 mb-3 grid gap-3"),
                 Div(*cards, cls="qr-sheet grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 pb-10"))


@ar("/qr/download", methods=["get"])
def qr_download(req, table: str = ""):
    import segno, io
    _, con = ctx(req)
    buf = io.BytesIO()
    segno.make(_store_link(req, table), error="m").save(buf, kind="svg", scale=12, border=2)
    name = re.sub(r"[^a-z0-9-]", "", req.scope["store"]) + (f"-table-{table}" if table else "") + "-qr.svg"
    return Response(buf.getvalue(), media_type="image/svg+xml",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- kitchen co-pilot

@ar("/copilot", methods=["get"])
def copilot_page(req, sess):
    _, con = ctx(req)
    pending = db.pending_proposals(con)
    intro = ("Ask me things like “What's still preparing?”, “Top sellers this week?”, "
             "“86 the sisig” or “Set ensaymada to 10 left”. I'll propose changes — you tap Confirm."
             if ai.enabled() else "AI isn't set up. Add LLM_API_KEY to enable the Kitchen Co-pilot.")
    return shell(req, "Co-pilot", "copilot",
                 H2("Kitchen Co-pilot", cls="text-xl font-extrabold mb-3"),
                 Div(ui.card(Div(ai.bubble(intro, False), id="chat-log", cls="h-[55vh] overflow-y-auto p-3 space-y-2"),
                             ai.chat_form("/admin/copilot", "Ask about orders, sales, stock…"), cls="flex flex-col"),
                     Div(H3("Pending proposals", cls="font-bold mb-2"),
                         Div(*[ai.proposal_card(p) for p in pending] if pending
                             else [P("None.", cls="text-sm text-stone-500")], cls="grid gap-2"),
                         cls="content-start"),
                     cls="grid md:grid-cols-[2fr_1fr] gap-3"))


@ar("/copilot", methods=["post"])
def copilot_chat(req, sess, message: str = ""):
    store, con = ctx(req)
    if not sess.get("copilot_id"):
        sess["copilot_id"] = "k_" + secrets.token_hex(8)
    reply, proposals = ai.copilot(con, store, sess["copilot_id"], message)
    return ai.bubbles(message, reply, proposals=proposals)


@ar("/copilot/proposal/{pid}/confirm", methods=["post"])
def confirm_proposal(req, pid: int):
    _, con = ctx(req)
    try:
        msg = ai.execute_proposal(con, pid)
    except db.OrderError as e:
        msg = str(e)
    p = db.get_proposal(con, pid)
    return (ai.proposal_card(p) if p else Div()), toast(msg)


@ar("/copilot/proposal/{pid}/dismiss", methods=["post"])
def dismiss_proposal(req, pid: int):
    _, con = ctx(req)
    db.decide_proposal(con, pid, "dismissed", "Dismissed")
    p = db.get_proposal(con, pid)
    return ai.proposal_card(p) if p else Div()

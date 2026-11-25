"""Public storefront: menu, item customizer, cart, checkout, payment proof, /order/<token>, concierge chat."""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlparse

from fasthtml.common import (
    A, APIRouter, Aside, Button, Details, Div, Form, H2, H3, Header, Input, Label, Li, Nav, Ol, P, Response,
    Script, Section, Span, Summary, Textarea, HtmxResponseHeaders,
)
from starlette.responses import FileResponse, RedirectResponse

import ai
import db
import ui
from ui import peso, delta

ar = APIRouter()
MAX_CART_LINES = 25


def ctx(req):
    return req.scope["store"], req.scope["con"]


def img_url(name: str | None) -> str | None:
    return f"/media/{name}" if name else None


# ---------------------------------------------------------------- cart (session)

def get_cart(sess) -> list[dict]:
    cart = sess.get("cart")
    return cart if isinstance(cart, list) else []


def cart_summary(con, sess):
    lines, errors = db.price_cart(con, get_cart(sess))
    return lines, errors, sum(ln["line_total_cents"] for ln in lines), sum(ln["qty"] for ln in lines)


def cart_counts(sess) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in get_cart(sess):
        k = str(c.get("item_id"))
        out[k] = out.get(k, 0) + int(c.get("qty") or 0)
    return out


def cart_events(sess, msg: str | None = None, error: bool = False):
    """HX-Trigger: refresh the "2 in cart" pills on every card, bounce the cart bar, show a toast."""
    ev: dict = {"cart": {"counts": cart_counts(sess)}}
    if msg:
        ev["toast"] = {"message": msg, "error": error}
    return HtmxResponseHeaders(trigger=json.dumps(ev))


def items_with_options(con) -> set[int]:
    """Items that need the options sheet (sizes / add-ons); everything else is one-tap add."""
    return {r[0] for r in con.execute("SELECT item_id FROM variants UNION SELECT item_id FROM modifier_groups")}


def cart_bar(con, sess, oob: bool = False, empty: tuple[str, str] | None = None, panel: bool = False):
    """Floating bottom cart bar. panel=True (menu page): hidden on desktop, where the side cart panel shows instead."""
    _, _, total, count = cart_summary(con, sess)
    inner = None
    if count:
        inner = A(
            Span(Span(str(count), cls="grid h-9 min-w-9 place-items-center rounded-full bg-white px-2 text-sm "
                                      "font-extrabold text-stone-900"),
                 Span(Span("View cart", cls="block font-bold leading-tight"),
                      Span(f"{count} item{'s' if count != 1 else ''} · review & checkout", cls="block text-xs opacity-80")),
                 cls="flex items-center gap-3"),
            Span(Span(peso(total), cls="font-extrabold"), Span("→", cls="text-lg"), cls="flex items-center gap-2"),
            href="/cart",
            cls="press mx-auto flex w-full max-w-xl items-center justify-between rounded-full bg-brand py-2 pl-2 pr-5 "
                "text-white shadow-2xl shadow-stone-900/30")
    elif empty:
        inner = A(Span(empty[0], cls="font-bold"), Span("→", cls="text-lg"), href=empty[1],
                  cls="press mx-auto flex w-full max-w-xl items-center justify-between rounded-full bg-brand px-5 "
                      "py-3.5 text-white shadow-2xl shadow-stone-900/30 md:hidden")
    return Div(inner, id="cartbar", cls="fixed inset-x-3 bottom-[max(.75rem,env(safe-area-inset-bottom))] z-30"
               + (" lg:hidden" if panel else ""), hx_swap_oob="true" if oob else None)


def cart_panel(con, sess, oob: bool = False):
    """Desktop (lg+) cart on the right side of the menu: live lines, +/−, total, checkout."""
    lines, _, total, count = cart_summary(con, sess)
    head = Div(H2("🧺 Your order", cls="text-lg font-extrabold"),
               Span(f"{count} item{'s' if count != 1 else ''}", cls="text-xs font-semibold text-stone-500") if count else None,
               cls="flex items-baseline justify-between border-b border-stone-100 px-5 py-4")
    if not lines:
        body = Div(P("🛒", cls="text-5xl"), P("Your cart is empty", cls="mt-3 font-bold"),
                   P("Tap + on anything you like and it'll show up here.", cls="mt-1 text-sm text-stone-500"),
                   cls="px-6 py-12 text-center")
        foot = None
    else:
        images = {r[0]: r[1] for r in con.execute("SELECT id, image FROM items")}

        def step_btn(i, d, label, aria):
            return Button(label, hx_post=f"/cart/qty/{i}?d={d}&panel=1", hx_target="#cart-panel", hx_swap="outerHTML",
                          aria_label=aria, cls="press grid size-7 place-items-center rounded-full bg-white text-sm shadow-sm")
        rows = [Div(ui.img(img_url(images.get(ln["item_id"])), ln["name"], "size-12 shrink-0 rounded-xl text-2xl"),
                    Div(P(ln["name"], cls="text-sm font-semibold leading-snug"),
                        P(line_desc(ln), cls="truncate text-xs text-stone-500") if line_desc(ln) else None,
                        P(f"“{ln['note']}”", cls="truncate text-xs italic text-stone-500") if ln["note"] else None,
                        Div(Span(peso(ln["line_total_cents"]), cls="text-sm font-extrabold"),
                            Div(step_btn(i, -1, "🗑" if ln["qty"] <= 1 else "−", "Remove" if ln["qty"] <= 1 else "Less"),
                                Span(str(ln["qty"]), cls="w-6 text-center text-sm font-extrabold"),
                                step_btn(i, 1, "+", "More"),
                                cls="flex items-center rounded-full bg-stone-100 p-0.5"),
                            cls="mt-1.5 flex items-center justify-between"),
                        cls="min-w-0 flex-1"),
                    cls="flex gap-3 py-3")
                for i, ln in enumerate(lines)]
        body = Div(*rows, cls="min-h-0 flex-1 divide-y divide-stone-100 overflow-y-auto px-5")
        foot = Div(Div(Span("Subtotal"), Span(peso(total), cls="text-lg font-extrabold"),
                       cls="flex items-baseline justify-between"),
                   P("Delivery fee (if any) is added at checkout.", cls="mt-0.5 text-xs text-stone-500"),
                   A(Span("Checkout", cls="font-bold"), Span(peso(total), " →", cls="font-extrabold"), href="/checkout",
                     cls="press mt-3 flex items-center justify-between rounded-full bg-brand px-5 py-3.5 text-white shadow-lg"),
                   A("View full cart", href="/cart", cls="mt-2 block text-center text-xs font-semibold text-stone-500 underline"),
                   cls="border-t border-stone-100 px-5 py-4")
    return Aside(head, body, foot, id="cart-panel", aria_label="Your order", hx_swap_oob="true" if oob else None,
                 cls="sticky top-4 hidden max-h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-3xl bg-white "
                     "ring-1 ring-stone-900/[.06] shadow-sm lg:flex")


def on_menu_page(req) -> bool:
    return urlparse(req.headers.get("hx-current-url", "")).path == "/menu"


def cart_oob(req, con, sess) -> tuple:
    """Out-of-band cart refresh for whatever page the request came from."""
    if on_menu_page(req):
        return cart_bar(con, sess, oob=True, panel=True), cart_panel(con, sess, oob=True)
    return (cart_bar(con, sess, oob=True),)


# ---------------------------------------------------------------- menu

def status_info(status: dict) -> tuple[str, str]:
    """(dot color class, text) for the open/closed pill."""
    if status["open"]:
        return "bg-emerald-500", "Open now" + (f" · until {status['closes']:%-I:%M %p}" if status.get("closes") else "")
    if not status["accepting"]:
        return "bg-red-500", "Not taking orders right now"
    return "bg-amber-500", ("Closed" + (f" · opens {status['opens']:%a %-I:%M %p}" if status.get("opens") else "")
                            + " · you can order ahead")


def store_header(s: dict, status: dict):
    dot, txt = status_info(status)
    return Header(
        A("← Home", href="/", cls="inline-flex rounded-full bg-white px-3 py-1.5 text-xs font-semibold ring-1 "
                                  "ring-stone-900/10 hover:ring-stone-900/25"),
        Div(ui.img(img_url(s.get("logo")), s["name"], "size-16 shrink-0 rounded-2xl text-3xl ring-1 ring-stone-900/5"),
            Div(H2(s["name"], cls="text-2xl font-extrabold leading-tight tracking-tight"),
                P(s.get("tagline", ""), cls="text-sm text-stone-600") if s.get("tagline") else None,
                Span(Span(cls=f"size-2 rounded-full {dot}"), txt,
                     cls="mt-1.5 inline-flex items-center gap-1.5 text-xs font-semibold text-stone-700"),
                cls="min-w-0"),
            cls="mt-4 flex items-center gap-4"),
        Div(Span("📣"), Span(s["announcement"]), cls="mt-4 flex gap-2 rounded-2xl bg-accent px-3.5 py-2.5 text-sm")
        if s.get("announcement") else None,
        cls="px-4 pt-5 pb-2")


def open_attrs(it: dict) -> dict:
    """Make a card open the item sheet (click or Enter)."""
    if not it["available"]:
        return {}
    return {"hx_get": f"/item/{it['id']}", "hx_target": "#modal", "role": "button", "tabindex": "0",
            "hx_trigger": "click, keyup[key=='Enter']"}


def add_button(it: dict, has_opts: bool, cls: str = ""):
    """Round + button: one-tap add for simple items, opens the options sheet otherwise."""
    if not it["available"]:
        return None
    act = ({"hx_get": f"/item/{it['id']}", "hx_target": "#modal"} if has_opts
           else {"hx_post": f"/cart/quick/{it['id']}", "hx_swap": "none"})
    return Button("+", type="button", aria_label=f"Add {it['name']}", title="Choose options" if has_opts else "Add to cart",
                  onclick="event.stopPropagation()",
                  cls=f"press grid size-10 place-items-center rounded-full bg-brand pb-0.5 text-2xl font-light leading-none "
                      f"text-white shadow-lg ring-4 ring-white hover:brightness-110 {cls}", **act)


def incart_pill(it: dict, n: int, cls: str = ""):
    return Span(f"{n} in cart" if n else "", data_incart=str(it["id"]),
                cls=f"incart inline-flex rounded-full px-2 py-0.5 text-[11px] font-bold {cls}")


def sold_veil(it: dict):
    return None if it["available"] else Div(
        Span("Sold out today", cls="rounded-full bg-stone-900 px-2.5 py-1 text-[11px] font-bold text-white"),
        cls="absolute inset-0 grid place-items-center rounded-[inherit] bg-white/55")


def item_card(it: dict, has_opts: bool = False, incart: int = 0, cat: str = ""):
    desc = it["description"] or ""
    pic = Div(ui.img(img_url(it["image"]), it["name"], "size-28 rounded-2xl text-5xl"), sold_veil(it),
              add_button(it, has_opts, "absolute -bottom-2 -right-2"), cls="relative shrink-0 rounded-2xl")
    body = Div(
        incart_pill(it, incart, "mb-1"),
        H3(it["name"], cls="font-bold leading-snug"),
        P(desc, cls="mt-0.5 line-clamp-2 text-sm text-stone-500") if desc else None,
        Div(Span(peso(it["price_cents"]), cls="font-extrabold"),
            Span("· options", cls="text-xs text-stone-400") if has_opts and it["available"] else None,
            cls="mt-2 flex items-baseline gap-1.5"),
        Div(ui.item_badges(it), cls="mt-1.5"),
        cls="min-w-0 flex-1 py-0.5")
    return Div(body, pic, id=f"item-{it['id']}",
               data_search=f"{it['name']} {desc} {cat} {' '.join(it['tags']).replace('_', ' ')}".lower(),
               cls="item-card press flex gap-4 rounded-3xl bg-white p-3.5 ring-1 ring-stone-900/[.06] transition "
                   + ("cursor-pointer hover:shadow-lg hover:shadow-stone-900/5 hover:ring-stone-900/15" if it["available"]
                      else "opacity-60"),
               **open_attrs(it))


def mini_card(it: dict, has_opts: bool = False, incart: int = 0):
    """Square card for the "Popular" carousel."""
    return Div(
        Div(ui.img(img_url(it["image"]), it["name"], "aspect-square w-full rounded-2xl text-6xl"), sold_veil(it),
            add_button(it, has_opts, "absolute -bottom-2 -right-2"),
            Div(incart_pill(it, incart, "shadow"), cls="absolute left-2 top-2"),
            cls="relative rounded-2xl"),
        P(it["name"], cls="mt-3 line-clamp-2 text-sm font-semibold leading-snug"),
        P(peso(it["price_cents"]), cls="text-sm font-extrabold text-deep"),
        cls="press w-40 shrink-0 cursor-pointer snap-start", **open_attrs(it))


MENU_JS = """
(() => {
const q = document.getElementById('menu-search'), cards = [...document.querySelectorAll('.item-card')];
const secs = [...document.querySelectorAll('[data-sec]')], none = document.getElementById('no-match');
const pop = document.getElementById('popular'), clr = document.getElementById('search-clear');
const run = () => {
  const v = q.value.trim().toLowerCase();
  cards.forEach(c => c.hidden = !!v && !c.dataset.search.includes(v));
  secs.forEach(s => s.hidden = !s.querySelector('.item-card:not([hidden])'));
  if (pop) pop.hidden = !!v; clr.hidden = !v;
  none.hidden = !v || secs.some(s => !s.hidden);
};
if (q) { q.addEventListener('input', run); clr.addEventListener('click', () => { q.value = ''; run(); q.focus(); }); }
const chips = [...document.querySelectorAll('[data-chip]')];
const setActive = id => chips.forEach(c => { const on = c.dataset.chip === id; c.classList.toggle('chip-on', on);
  if (on) c.parentElement.scrollTo({left: c.offsetLeft - 16, behavior: 'smooth'}); });
const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && setActive(e.target.id)),
  {rootMargin: '-35% 0px -60% 0px'});
secs.forEach(s => io.observe(s));
})();
"""


TABLE_TTL = 4 * 3600  # a scanned table "sticks" for one meal, not forever


def clean_table(v: str) -> str:
    return "".join(ch for ch in (v or "") if ch.isalnum() or ch in " -")[:12].strip()


def current_table(sess) -> str:
    """Table number from a scanned table QR (/?table=5), if still fresh."""
    import time
    t = sess.get("table") or {}
    return t.get("no", "") if isinstance(t, dict) and time.time() - t.get("at", 0) < TABLE_TTL else ""


@ar("/menu", methods=["get"])
def menu(req, sess, table: str = "", open: int = 0):
    store, con = ctx(req)
    s = db.get_settings(con)
    if table:
        import time
        no = "" if table == "none" else clean_table(table)
        sess["table"] = {"no": no, "at": time.time()} if no else {}
        return RedirectResponse("/menu", status_code=303)  # clean URL; a reload/share won't re-pin the table
    status = db.kitchen_status(s)
    cats = db.categories(con)
    its = db.items(con)
    opts = items_with_options(con)
    counts = cart_counts(sess)
    by_cat = {c["id"]: [] for c in cats}
    for it in its:
        by_cat.setdefault(it["category_id"], []).append(it)
    cats = [c for c in cats if by_cat.get(c["id"])]

    def card(it, cat=""):
        return item_card(it, it["id"] in opts, counts.get(str(it["id"]), 0), cat)

    popular = [it for it in its if "best_seller" in it["tags"] and it["available"]]
    pop_row = Section(
        Div(H2("🔥 Popular right now", cls="text-lg font-extrabold"),
            Span("Swipe →", cls="text-xs text-stone-400 sm:hidden"), cls="flex items-baseline justify-between px-4"),
        Div(*[mini_card(it, it["id"] in opts, counts.get(str(it["id"]), 0)) for it in popular],
            cls="no-scrollbar mt-3 flex snap-x scroll-px-4 gap-3 overflow-x-auto px-4 pb-3"),
        id="popular", cls="mt-4") if len(popular) >= 2 else None
    search = Div(
        Span("🔍", cls="pointer-events-none absolute left-8 top-1/2 -translate-y-1/2 text-sm"),
        Input(type="search", id="menu-search", placeholder="Search the menu…", autocomplete="off",
              aria_label="Search the menu",
              cls="w-full rounded-full border-0 bg-white py-3 pl-11 pr-11 text-[15px] ring-1 ring-stone-900/10 "
                  "focus:outline-none focus:ring-2 focus:ring-[color:var(--brand)]"),
        Button("✕", type="button", id="search-clear", hidden=True, aria_label="Clear search",
               cls="absolute right-6 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full bg-stone-100 text-xs"),
        cls="relative px-4 mt-2") if its else None
    chips = Nav(*[A(c["name"], Span(str(len(by_cat[c["id"]])), cls="ml-1.5 text-xs opacity-60"),
                    href=f"#cat-{c['id']}", data_chip=f"cat-{c['id']}",
                    cls="shrink-0 rounded-full border border-stone-200 bg-white px-4 py-2 text-sm font-semibold transition")
                  for c in cats],
                cls="no-scrollbar sticky top-0 z-20 mt-3 flex gap-2 overflow-x-auto bg-[#faf7f2]/90 px-4 py-3 "
                    "backdrop-blur-md") if len(cats) > 1 else None
    sections = [Section(Div(H2(c["name"], cls="text-xl font-extrabold"),
                            Span(f"{len(by_cat[c['id']])} items", cls="text-xs text-stone-400"),
                            cls="mb-3 flex items-baseline justify-between"),
                        Div(*[card(it, c["name"]) for it in by_cat[c["id"]]], cls="grid gap-3"),
                        id=f"cat-{c['id']}", data_sec="1", cls="mt-6 scroll-mt-20 px-4") for c in cats]
    no_match = Div(P("🤔", cls="text-4xl"), P("No matches", cls="mt-2 font-bold"),
                   P("Try another word, or ask the menu assistant 💬", cls="text-sm text-stone-500"),
                   id="no-match", hidden=True, cls="py-14 text-center")
    footer = Div(
        P(s.get("address", ""), cls="text-sm font-medium"),
        Div(*[Div(Span(d, cls="inline-block w-10 font-semibold"), h) for d, h in db.fmt_hours(s, friendly=True)],
            cls="mt-2 grid grid-cols-2 gap-x-4 text-xs text-stone-500"),
        P("Powered by BiteFlow · 0% commission", cls="mt-4 text-[11px] text-stone-400"),
        cls="mx-4 mt-12 border-t border-stone-900/10 pt-6")
    preview = Div(Span("Preview", cls="font-bold"), " · only you can see this until your store goes live. ",
                  A("Back to admin", href="/admin/start", cls="font-semibold underline"),
                  cls="bg-amber-100 px-4 py-2 text-center text-sm text-amber-900") if req.scope.get("preview") else None
    tno = current_table(sess) if "dine_in" in s["modes"] else ""
    table_bar = Div(
        Span("🍽", cls="text-2xl"),
        Div(P(f"Table {tno} · Dine-in", cls="font-bold"),
            P("Order here and we'll bring it to your table.", cls="text-xs opacity-85"), cls="flex-1"),
        A("Not at a table?", href="/menu?table=none", cls="shrink-0 text-xs underline opacity-85"),
        cls="mx-4 mt-3 flex items-center gap-3 rounded-2xl bg-brand px-4 py-3 text-white") if tno else None
    left = Div(store_header(s, status), table_bar, search, pop_row, chips,
               *(sections or [ui.empty("Menu coming soon", "Check back later!")]), no_match, footer, cls="min-w-0")
    return ui.page(s["name"], s, preview,
                   Div(left, Div(cart_panel(con, sess), cls="hidden pt-5 lg:block"),
                       cls="lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-8 lg:px-6"),
                   cart_bar(con, sess, panel=True), ai.chat_widget("concierge", s), Script(MENU_JS),
                   Script("document.addEventListener('DOMContentLoaded', () => setTimeout(() => "
                          f"document.getElementById('item-{int(open)}')?.click(), 0))") if open else None,
                   cls="max-w-2xl lg:max-w-6xl")


# ---------------------------------------------------------------- item customizer

CUSTOMIZER_JS = """
function bfPrice(f){
  let u = +f.dataset.base;
  f.querySelectorAll('input:checked[data-d]').forEach(i => u += +i.dataset.d);
  const q = Math.max(1, +f.qty.value || 1);
  let missing = null;
  f.querySelectorAll('.grp').forEach(g => {
    const min = +g.dataset.min, max = +g.dataset.max, ins = [...g.querySelectorAll('input')];
    const n = ins.filter(i => i.checked).length;
    if (max > 1) ins.forEach(b => b.disabled = !b.checked && n >= max);
    if (min > 0) {
      const ok = n >= min; g.classList.toggle('need', !ok); g.classList.toggle('done', ok);
      g.querySelector('.grp-state').textContent = ok ? '✓ Done' : 'Required';
      if (!ok && !missing) missing = g;
    }
  });
  const b = f.querySelector('.bf-add');
  b.querySelector('.lbl').textContent = missing ? 'Choose ' + missing.dataset.name : (q > 1 ? 'Add ' + q + ' to cart' : 'Add to cart');
  b.querySelector('.bf-total').textContent = missing ? '↑' : '₱' + (u*q/100).toLocaleString('en-PH', {maximumFractionDigits: 2});
  b.classList.toggle('opacity-80', !!missing);
  f.querySelector('.bf-minus').disabled = q <= 1;
}
function bfQty(btn, d){ const f = btn.form; f.qty.value = Math.min(50, Math.max(1, (+f.qty.value||1) + d)); bfPrice(f); }
function bfGo(e, f){
  const g = f.querySelector('.grp.need'); if (!g) return;
  e.preventDefault(); g.scrollIntoView({behavior: 'smooth', block: 'center'});
  g.classList.remove('shake'); void g.offsetWidth; g.classList.add('shake');
}
"""


def stock_line(it: dict):
    if it["remaining"] is None:
        return Span(id=f"stock-{it['id']}")
    txt = "Sold out" if it["remaining"] <= 0 else f"🔥 {it['remaining']} left today"
    return Span(txt, id=f"stock-{it['id']}", cls="rounded-full bg-orange-50 px-2 py-0.5 text-xs font-semibold text-orange-700",
                hx_get=f"/item/{it['id']}/stock", hx_trigger="every 15s", hx_swap="outerHTML")


@ar("/item/{item_id}/stock", methods=["get"])
def item_stock(req, item_id: int):
    _, con = ctx(req)
    it = db.get_item(con, item_id, with_options=False)
    return stock_line(it) if it else Span()


def option_row(inp, name: str, d: int, multi: bool):
    return Label(
        inp,
        Span(Span("✓", cls="tick text-[11px] font-bold text-white"),
             cls=f"ind grid size-5 shrink-0 place-items-center border-2 border-stone-300 transition "
                 f"{'rounded-md' if multi else 'rounded-full'}"),
        Span(name, cls="flex-1 font-medium"),
        Span(delta(d), cls="text-sm font-semibold text-stone-500") if d else Span("Free", cls="text-xs text-stone-400")
        if multi else None,
        cls="opt press flex cursor-pointer items-center gap-3 rounded-2xl border border-stone-200 px-4 py-3 transition")


def option_group(title: str, rows: list, min_sel: int, max_sel: int):
    if min_sel and max_sel == 1:
        sub = "Pick 1"
    elif max_sel == 1:
        sub = "Pick 1 if you like"
    else:
        sub = f"Pick up to {max_sel}" if not min_sel else f"Pick {min_sel}–{max_sel}"
    return Div(
        Div(Div(H3(title, cls="font-bold"), P(sub, cls="text-xs text-stone-500")),
            Span("Required" if min_sel else "Optional",
                 cls="grp-state shrink-0 rounded-full bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-600"),
            cls="flex items-start justify-between gap-3"),
        Div(*rows, cls="mt-2.5 grid gap-2"),
        data_min=str(min_sel), data_max=str(max_sel), data_name=title.lower(), cls="grp mt-6")


@ar("/item/{item_id}", methods=["get"])
def item_modal(req, item_id: int):
    _, con = ctx(req)
    it = db.get_item(con, item_id)
    if not it or not it["active"]:
        return ui.modal(ui.empty("Item not found"), title="")
    if not it["available"]:
        return ui.modal(ui.empty(f"{it['name']} is sold out", "Please check back later."), title=it["name"])
    parts = []
    if it["variants"]:
        parts.append(option_group("Size / type", [
            option_row(Input(type="radio", name="variant_id", value=str(v["id"]), required=True, checked=i == 0,
                             data_d=str(v["price_delta_cents"]), cls="sr-only"),
                       v["name"], v["price_delta_cents"], False)
            for i, v in enumerate(it["variants"])], 1, 1))
    for g in it["groups"]:
        single = g["max_select"] == 1
        parts.append(option_group(g["name"], [
            option_row(Input(type="radio" if single else "checkbox", name=f"g{g['id']}" if single else "mod",
                             value=str(m["id"]), data_d=str(m["price_delta_cents"]),
                             required=single and g["min_select"] > 0, cls="sr-only"),
                       m["name"], m["price_delta_cents"], not single)
            for m in g["options"]], g["min_select"], g["max_select"]))
    f = Form(
        Input(type="hidden", name="item_id", value=str(it["id"])),
        *parts,
        Details(Summary("✏️ Add a note for the kitchen", cls="cursor-pointer select-none text-sm font-semibold text-deep"),
                Input(name="note", maxlength="140", placeholder="e.g. less ice, extra hot, no onions",
                      cls=ui.INPUT_CLS + " mt-2"),
                cls="mt-6 rounded-2xl bg-stone-50 px-4 py-3"),
        ui.error_box(None, "item-error"),
        Div(
            Div(Button("−", type="button", onclick="bfQty(this,-1)", aria_label="Less",
                       cls="bf-minus press grid size-10 place-items-center rounded-full bg-white text-xl shadow-sm disabled:opacity-40"),
                Input(name="qty", value="1", type="number", min="1", max="50", readonly=True, aria_label="Quantity",
                      cls="w-8 bg-transparent text-center font-extrabold"),
                Button("+", type="button", onclick="bfQty(this,1)", aria_label="More",
                       cls="press grid size-10 place-items-center rounded-full bg-white text-xl shadow-sm"),
                cls="flex items-center rounded-full bg-stone-100 p-1"),
            Button(Span("Add to cart", cls="lbl"), Span(peso(it["price_cents"]), cls="bf-total font-extrabold"),
                   type="submit", onclick="bfGo(event, this.form)",
                   cls="bf-add press flex flex-1 items-center justify-between gap-2 rounded-full bg-brand px-5 py-3.5 "
                       "font-semibold text-white shadow-lg transition"),
            cls="sticky -bottom-5 z-10 -mx-5 -mb-5 mt-6 flex items-center gap-3 border-t border-stone-100 bg-white px-5 "
                "pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]"),
        data_base=str(it["price_cents"]), onchange="bfPrice(this)", novalidate=True,
        hx_post="/cart/add", hx_target="#item-error", hx_swap="outerHTML")
    return ui.modal(
        H2(it["name"], cls="text-2xl font-extrabold leading-tight tracking-tight"),
        Div(Span(peso(it["price_cents"]), cls="text-lg font-extrabold text-deep"), stock_line(it),
            cls="mt-1 flex flex-wrap items-center gap-2"),
        P(it["description"], cls="mt-2 text-stone-600") if it["description"] else None,
        Div(ui.item_badges(it), cls="mt-3") if ui.item_badges(it) else None,
        P("⚠️ Contains: " + ", ".join(it["allergens"]), cls="mt-3 text-xs text-stone-500") if it["allergens"] else None,
        f, Script(CUSTOMIZER_JS + "bfPrice(document.querySelector('#modal form'));"),
        title=it["name"],
        hero=ui.img(img_url(it["image"]), it["name"], "h-56 w-full rounded-t-[1.75rem] text-8xl sm:h-64"))


async def _mods_from_form(req) -> tuple[dict, list[int]]:
    form = await req.form()
    mods = [int(v) for k, v in form.multi_items() if (k == "mod" or (k.startswith("g") and k[1:].isdigit()))
            and str(v).isdigit()]
    return form, mods


@ar("/cart/add", methods=["post"])
async def cart_add(req, sess):
    _, con = ctx(req)
    form, mods = await _mods_from_form(req)
    try:
        variant = form.get("variant_id")
        ln = db.price_line(con, int(form.get("item_id") or 0), int(variant) if variant else None, mods,
                           int(form.get("qty") or 1), form.get("note", ""))
    except (db.OrderError, ValueError) as e:
        return ui.error_box(str(e) if isinstance(e, db.OrderError) else "Invalid selection.", "item-error")
    cart = get_cart(sess)
    if len(cart) >= MAX_CART_LINES:
        return ui.error_box("Your cart is full.", "item-error")
    _merge_into_cart(cart, ln)
    sess["cart"] = cart
    return (ui.error_box(None, "item-error"), *cart_oob(req, con, sess), Div(id="modal", hx_swap_oob="true"),
            cart_events(sess, f"Added {ln['qty']}× {ln['name']}"))


@ar("/cart/quick/{item_id}", methods=["post"])
def cart_quick(req, sess, item_id: int):
    """The round + on a card: add one straight away (items with options open their sheet instead)."""
    _, con = ctx(req)
    if item_id in items_with_options(con):
        return item_modal(req, item_id), HtmxResponseHeaders(retarget="#modal", reswap="innerHTML")
    try:
        ln = db.price_line(con, item_id, None, [], 1)
    except db.OrderError as e:
        return Div(), cart_events(sess, str(e), error=True)
    cart = get_cart(sess)
    if len(cart) >= MAX_CART_LINES:
        return Div(), cart_events(sess, "Your cart is full.", error=True)
    _merge_into_cart(cart, ln)
    sess["cart"] = cart
    return *cart_oob(req, con, sess), cart_events(sess, f"Added {ln['name']}")


def _merge_into_cart(cart: list[dict], ln: dict) -> None:
    key = (ln["item_id"], ln["variant_id"], tuple(ln["modifier_ids"]), ln["note"])
    for c in cart:
        if (c["item_id"], c.get("variant_id"), tuple(sorted(c.get("modifier_ids", []))), c.get("note", "")) == key:
            c["qty"] = min(db.MAX_QTY, c["qty"] + ln["qty"])
            return
    cart.append({"item_id": ln["item_id"], "variant_id": ln["variant_id"], "modifier_ids": ln["modifier_ids"],
                 "qty": ln["qty"], "note": ln["note"]})


# ---------------------------------------------------------------- cart page

def line_desc(ln: dict) -> str:
    bits = ([ln["variant_name"]] if ln.get("variant_name") else []) + [m["name"] for m in ln.get("modifiers", [])]
    return " · ".join(bits)


def cart_body(con, sess):
    lines, errors, total, count = cart_summary(con, sess)
    if errors:  # drop invalid lines so the cart heals itself
        cart = get_cart(sess)
        keep = []
        for raw in cart:
            try:
                db.price_line(con, raw["item_id"], raw.get("variant_id"), raw.get("modifier_ids", []), raw["qty"])
                keep.append(raw)
            except Exception:
                pass
        sess["cart"] = keep
    if not lines:
        return Div(Div(P("🛒", cls="text-6xl"), P("Your cart is empty", cls="mt-3 text-lg font-bold"),
                       P("Add something delicious from the menu.", cls="text-sm text-stone-500"),
                       A("Browse the menu →", href="/menu",
                         cls="press mt-6 inline-flex rounded-full bg-brand px-6 py-3 font-semibold text-white"),
                       cls="py-16 text-center"),
                   *[ui.error_box(e, f"err-{i}") for i, e in enumerate(errors)], id="cart-body")
    images = {r[0]: r[1] for r in con.execute("SELECT id, image FROM items")}
    rows = []
    for i, ln in enumerate(lines):
        one = ln["qty"] <= 1
        rows.append(Div(
            ui.img(img_url(images.get(ln["item_id"])), ln["name"], "size-16 shrink-0 rounded-2xl text-3xl"),
            Div(P(ln["name"], cls="font-semibold leading-snug"),
                P(line_desc(ln), cls="text-xs text-stone-500") if line_desc(ln) else None,
                P(f"“{ln['note']}”", cls="text-xs italic text-stone-500") if ln["note"] else None,
                P(peso(ln["line_total_cents"]), cls="mt-1 text-sm font-extrabold"), cls="min-w-0 flex-1"),
            Div(Button("🗑" if one else "−", hx_post=f"/cart/qty/{i}?d=-1", hx_target="#cart-body", hx_swap="outerHTML",
                       aria_label="Remove" if one else "Less",
                       cls=f"press grid size-9 place-items-center rounded-full bg-white shadow-sm {'text-sm' if one else 'text-lg'}"),
                Span(str(ln["qty"]), cls="w-7 text-center font-extrabold"),
                Button("+", hx_post=f"/cart/qty/{i}?d=1", hx_target="#cart-body", hx_swap="outerHTML", aria_label="More",
                       cls="press grid size-9 place-items-center rounded-full bg-white text-lg shadow-sm"),
                cls="flex shrink-0 items-center rounded-full bg-stone-100 p-1"),
            cls="flex items-center gap-3 py-3.5"))
    return Div(
        *[ui.error_box(e + " (removed from cart)", f"err-{i}") for i, e in enumerate(errors)],
        Div(*rows, cls="divide-y divide-stone-100 rounded-3xl bg-white px-4 ring-1 ring-stone-900/[.06]"),
        A("＋ Add more items", href="/menu",
          cls="mt-3 flex items-center justify-center rounded-2xl border-2 border-dashed border-stone-300 py-3 text-sm "
              "font-semibold text-stone-600 hover:border-stone-400"),
        Div(Div(Span(f"Subtotal · {count} item{'s' if count != 1 else ''}"), Span(peso(total), cls="font-bold"),
                cls="flex justify-between"),
            P("Delivery fee (if any) is added at checkout.", cls="mt-1 text-xs text-stone-500"),
            cls="mt-4 rounded-3xl bg-white p-4 ring-1 ring-stone-900/[.06]"),
        Div(A(Span("Go to checkout", cls="font-bold"), Span(peso(total), " →", cls="font-extrabold"), href="/checkout",
              cls="press flex w-full items-center justify-between rounded-full bg-brand px-6 py-4 text-white shadow-2xl "
                  "shadow-stone-900/30"),
            cls="sticky bottom-[max(.75rem,env(safe-area-inset-bottom))] mt-5"),
        id="cart-body")


@ar("/cart", methods=["get"])
def cart_page(req, sess):
    _, con = ctx(req)
    s = db.get_settings(con)
    return ui.page(f"Cart · {s['name']}", s,
                   Div(A("← Keep ordering", href="/menu", cls="text-sm font-semibold text-stone-600"),
                       ui.heading("Your cart", "Check your order, then continue to checkout."),
                       cart_body(con, sess), cls="px-4 pt-5"))


@ar("/cart/qty/{idx}", methods=["post"])
def cart_qty(req, sess, idx: int, d: int, panel: int = 0):
    _, con = ctx(req)
    cart = get_cart(sess)
    if 0 <= idx < len(cart):
        cart[idx]["qty"] = min(db.MAX_QTY, cart[idx]["qty"] + (1 if d > 0 else -1))
        if cart[idx]["qty"] <= 0:
            cart.pop(idx)
        sess["cart"] = cart
    if panel:  # desktop side panel on the menu page
        return cart_panel(con, sess), cart_bar(con, sess, oob=True, panel=True), cart_events(sess)
    return cart_body(con, sess)


# ---------------------------------------------------------------- checkout

CHECKOUT_JS = """
function bfMode(f){
  const m = (f.querySelector('input[name=mode]:checked')||{}).value;
  f.querySelectorAll('[data-modes]').forEach(el => {
    const on = el.dataset.modes.split(' ').includes(m);
    el.classList.toggle('hidden', !on);
    el.querySelectorAll('input,select,textarea').forEach(i => i.disabled = !on);
  });
  const pays = [...f.querySelectorAll('input[name=payment]:not(:disabled)')];
  if (pays.length && !pays.some(p => p.checked)) pays[0].checked = true;
}
"""


MODE_ICON = {"dine_in": "🍽", "pickup": "🛍", "delivery": "🛵", "cod": "💵"}
PAY_ICON = {"gcash": "📱", "bank": "🏦", "counter": "🧾"}


def radio_card(name, value, title, sub="", checked=False, icon="", **kw):
    return Label(
        Input(type="radio", name=name, value=value, checked=checked, cls="sr-only", **kw),
        Span(icon, cls="text-2xl") if icon else None,
        Div(P(title, cls="font-semibold leading-tight"), P(sub, cls="text-xs text-stone-500") if sub else None,
            cls="min-w-0 flex-1"),
        Span(Span("✓", cls="tick text-[11px] font-bold text-white"),
             cls="ind grid size-5 shrink-0 place-items-center rounded-full border-2 border-stone-300 transition"),
        cls="opt press flex cursor-pointer items-center gap-3 rounded-2xl border border-stone-200 bg-white px-3.5 py-3 transition")


def step(n: int, title: str, *content, sub: str | None = None):
    return Section(
        Div(Span(str(n), cls="grid size-7 shrink-0 place-items-center rounded-full bg-stone-900 text-xs font-bold text-white"),
            Div(H3(title, cls="text-lg font-bold leading-tight"), P(sub, cls="text-xs text-stone-500") if sub else None),
            cls="flex items-center gap-3"),
        Div(*content, cls="mt-4"),
        cls="rounded-3xl bg-white p-4 ring-1 ring-stone-900/[.06] sm:p-5")


def _totals(con, sess, mode=None, zone_id=None):
    _, _, subtotal, _ = cart_summary(con, sess)
    fee, note = 0, None
    if mode in db.DELIVERY_MODES and zone_id:
        z = con.execute("SELECT * FROM delivery_zones WHERE id=? AND active=1", (zone_id,)).fetchone()
        if z:
            fee = z["fee_cents"]
            if subtotal < z["min_order_cents"]:
                note = f"Minimum order for {z['name']} is {peso(z['min_order_cents'])}."
    return subtotal, fee, note


def totals_box(con, sess, mode=None, zone_id=None):
    subtotal, fee, note = _totals(con, sess, mode, zone_id)
    return Div(
        Div(Span("Subtotal"), Span(peso(subtotal)), cls="flex justify-between"),
        Div(Span("Delivery fee"), Span(peso(fee)), cls="flex justify-between") if mode in db.DELIVERY_MODES else None,
        Div(Span("Total", cls="font-bold"), Span(peso(subtotal + fee), cls="text-xl font-extrabold"),
            cls="mt-2 flex items-baseline justify-between border-t border-stone-100 pt-3"),
        P("⚠️ " + note, cls="mt-2 rounded-xl bg-red-50 px-3 py-2 text-xs font-medium text-red-700") if note else None,
        id="totals", cls="space-y-1 text-sm")


@ar("/checkout/totals", methods=["post"])
def checkout_totals(req, sess, mode: str = "", zone_id: int = 0):
    _, con = ctx(req)
    subtotal, fee, _ = _totals(con, sess, mode, zone_id)
    return totals_box(con, sess, mode, zone_id), Span(peso(subtotal + fee), id="place-total", hx_swap_oob="true")


@ar("/checkout", methods=["get"])
def checkout(req, sess):
    _, con = ctx(req)
    s = db.get_settings(con)
    lines, _, subtotal, count = cart_summary(con, sess)
    if not count:
        return RedirectResponse("/cart", status_code=303)
    status = db.kitchen_status(s)
    slots = db.time_slots(s)
    modes = [m for m in db.MODES if m in s["modes"]]
    zones = db.delivery_zones(con)
    if not zones:
        modes = [m for m in modes if m not in db.DELIVERY_MODES]
    pays = [p for p in s["payments"] if p in ("gcash", "bank", "counter")]
    mode_sub = {"dine_in": "Eat here", "pickup": "Grab & go", "delivery": "Pay online",
                "cod": "Pay cash on arrival"}
    pay_sub = {"gcash": "Send, then upload a screenshot", "bank": "Transfer, then upload a screenshot",
               "counter": "Pay when you get your order"}
    pay_modes = {"gcash": "dine_in pickup delivery", "bank": "dine_in pickup delivery", "counter": "dine_in pickup"}
    first_pay_for = {m: next((p for p in pays if m in pay_modes[p].split()), None) for m in modes}
    prep = int(s.get("prep_minutes") or 0)
    when_opts = ([("asap", f"As soon as possible{f' (~{prep} min)' if prep else ''}")] if status["open"] else []) + \
        [(t.isoformat(timespec="minutes"), f"{t:%a %b %-d · %-I:%M %p}") for t in slots]
    if not modes or not when_opts:
        return ui.page("Checkout", s, Div(ui.heading("Checkout"),
                                          ui.empty("Online ordering is unavailable right now.",
                                                   "Please check our hours and try again later."),
                                          cls="px-4 pt-5"))
    remembered = sess.get("customer") or {}
    tno = current_table(sess) if "dine_in" in modes else ""
    if tno:
        modes = ["dine_in"] + [m for m in modes if m != "dine_in"]
    summary = Details(
        Summary(Span("🧺", cls="text-xl"),
                Span(Span(f"{count} item{'s' if count != 1 else ''} in your order", cls="block font-semibold"),
                     Span("Tap to see them", cls="block text-xs text-stone-500"), cls="flex-1"),
                Span(peso(subtotal), cls="font-extrabold"),
                cls="flex cursor-pointer select-none list-none items-center gap-3"),
        Div(*[Div(Span(f"{ln['qty']}×", cls="w-7 font-bold text-stone-500"),
                  Div(P(ln["name"], cls="font-medium"), P(line_desc(ln), cls="text-xs text-stone-500") if line_desc(ln) else None,
                      cls="flex-1"),
                  Span(peso(ln["line_total_cents"])), cls="flex gap-2 py-2 text-sm") for ln in lines],
            A("Edit cart", href="/cart", cls="mt-1 inline-block text-sm font-semibold text-deep underline"),
            cls="mt-3 divide-y divide-stone-100 border-t border-stone-100 pt-1"),
        cls="rounded-3xl bg-white p-4 ring-1 ring-stone-900/[.06]")
    total0 = subtotal
    f = Form(
        summary,
        step(1, "Your details",
             Div(ui.field("Name", "name", remembered.get("name", ""), required=True, maxlength="80",
                          autocomplete="name", placeholder="Juan Dela Cruz"),
                 ui.field("Mobile number", "phone", remembered.get("phone", ""), type="tel", required=True,
                          placeholder="0917 123 4567", autocomplete="tel", inputmode="tel",
                          hint="Only used for updates about this order."),
                 cls="grid gap-3"),
             sub="So we know who the order is for"),
        step(2, "How do you want it?",
             Div(*[radio_card("mode", m, db.MODE_LABEL[m], mode_sub[m], checked=i == 0, icon=MODE_ICON[m])
                   for i, m in enumerate(modes)], cls="grid gap-2 sm:grid-cols-2"),
             Div(ui.field("Table number" + ("" if tno else " (optional)"), "table_no", tno, maxlength="12",
                          inputmode="numeric", hint="✓ From the QR code on your table." if tno else ""),
                 data_modes="dine_in", cls="mt-4"),
             Div(ui.select("Delivery area", "zone_id",
                           [(z["id"], f"{z['name']} · {peso(z['fee_cents'])} · ~{z['eta_minutes']} min")
                            for z in zones], hx_post="/checkout/totals", hx_target="#totals",
                           hx_swap="outerHTML", hx_include="closest form") if zones else None,
                 ui.field("Full address & landmark", "address", remembered.get("address", ""),
                          type="textarea", maxlength="300", required=True,
                          placeholder="House no., street, barangay, landmark"),
                 data_modes="delivery cod", cls="mt-4 grid gap-3")),
        step(3, "When?",
             ui.select("Time", "when", when_opts),
             P("🕒 We're closed right now, so pick a time and we'll have it ready.",
               cls="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800")
             if not status["open"] else None),
        step(4, "Payment",
             Div(*[Div(radio_card("payment", p, db.PAY_LABEL[p], pay_sub[p], icon=PAY_ICON[p],
                                  checked=p == first_pay_for.get(modes[0])),
                       data_modes=pay_modes[p]) for p in pays],
                 Div(Div(Span("💵", cls="text-2xl"), P("You'll pay cash to the rider when your order arrives.",
                                                       cls="text-sm text-stone-600"),
                         cls="flex items-center gap-3 rounded-2xl bg-stone-50 px-3.5 py-3"), data_modes="cod"),
                 cls="grid gap-2")),
        Details(Summary("✏️ Add notes for the kitchen (optional)",
                        cls="cursor-pointer select-none text-sm font-semibold text-deep"),
                Textarea(name="notes", maxlength="300", placeholder="Allergies, special requests…",
                         cls=ui.INPUT_CLS + " mt-3 min-h-[80px]"),
                cls="rounded-3xl bg-white p-4 ring-1 ring-stone-900/[.06]"),
        Div(totals_box(con, sess, modes[0], zones[0]["id"] if zones else None),
            cls="rounded-3xl bg-white p-4 ring-1 ring-stone-900/[.06]"),
        ui.error_box(None),
        Div(Button(Span("Place order", cls="font-bold"), Span(peso(total0), id="place-total", cls="font-extrabold"),
                   type="submit", hx_disabled_elt="this",
                   cls="press flex w-full items-center justify-between rounded-full bg-brand px-6 py-4 text-white "
                       "shadow-2xl shadow-stone-900/30 disabled:opacity-60"),
            P("You can track your order live right after.", cls="mt-2 text-center text-xs text-stone-500"),
            cls="sticky bottom-[max(.75rem,env(safe-area-inset-bottom))]"),
        hx_post="/checkout", hx_target="#form-error", hx_swap="outerHTML",
        onchange="bfMode(this)", cls="grid gap-3",
    )
    return ui.page(f"Checkout · {s['name']}", s,
                   Div(A("← Back to cart", href="/cart", cls="text-sm font-semibold text-stone-600"),
                       ui.heading("Checkout", "4 quick steps and you're done."), f,
                       Script(CHECKOUT_JS + """
const _f = document.querySelector('form[hx-post="/checkout"]'); bfMode(_f);
_f.querySelectorAll('input[name=mode]').forEach(r => r.addEventListener('change', () =>
  htmx.ajax('POST', '/checkout/totals', {source: _f, target: '#totals', swap: 'outerHTML', values: {
    mode: r.value, zone_id: (_f.zone_id||{}).value || 0}})));
document.body.addEventListener('htmx:afterSwap', e => { if (e.detail.target.id === 'form-error' && e.detail.target.textContent.trim())
  e.detail.target.scrollIntoView({behavior: 'smooth', block: 'center'}); });"""),
                       cls="px-4 pt-5"))


@ar("/checkout", methods=["post"])
async def place(req, sess):
    _, con = ctx(req)
    form = dict((await req.form()).items())
    try:
        order = db.place_order(con, get_cart(sess), form)
    except db.OrderError as e:
        return ui.error_box(str(e))
    sess["cart"] = []
    sess["customer"] = {"name": order["customer_name"], "phone": order["phone"], "address": order["address"] or ""}
    mine = [t for t in (sess.get("orders") or []) if isinstance(t, str)][-9:]
    sess["orders"] = mine + [order["token"]]
    return Response("", headers={"HX-Redirect": f"/order/{order['token']}"})


# ---------------------------------------------------------------- order tracking

def progress(o: dict):
    if o["status"] == "cancelled":
        return None
    steps = ["pending_payment", "preparing", "ready"]
    if o["mode"] in db.DELIVERY_MODES:
        steps.append("out_for_delivery")
    steps.append("completed")
    if o["payment_method"] not in ("gcash", "bank"):
        steps.remove("pending_payment")
    cur = steps.index(o["status"]) if o["status"] in steps else 0
    short = {"pending_payment": "Payment", "preparing": "Preparing", "ready": "Ready",
             "out_for_delivery": "On the way", "completed": "Done"}
    done_all = o["status"] == "completed"
    out = []
    for i, st in enumerate(steps):
        past, now_ = i < cur or done_all, i == cur and not done_all
        circle = ("bg-brand text-white" if past else "bg-brand text-white ring-now" if now_
                  else "bg-stone-100 text-stone-400")
        out.append(Li(
            Div(cls=f"absolute left-1/2 top-4 h-1 w-full {'bg-brand' if i < cur or done_all else 'bg-stone-100'}")
            if i < len(steps) - 1 else None,
            Span("✓" if past else str(i + 1),
                 cls=f"relative z-10 grid size-8 place-items-center rounded-full text-sm font-bold transition {circle}"),
            Span(short[st], cls=f"text-[11px] leading-tight {'font-bold text-stone-900' if now_ else 'text-stone-500'}"),
            cls="relative flex flex-1 flex-col items-center gap-1.5 text-center"))
    return Ol(*out, cls="flex")


def payment_panel(con, o: dict, s: dict, err: str | None = None):
    if o["status"] != "pending_payment":
        return Div(id="payment")
    if o["payment_status"] == "submitted":
        return Div(Div(Span("📨", cls="text-3xl"),
                       Div(P("Payment proof received", cls="font-bold"),
                           P("We're checking it now. This page updates by itself.", cls="text-sm text-stone-600")),
                       cls="flex items-center gap-4 rounded-3xl bg-emerald-50 p-4 ring-1 ring-emerald-200"), id="payment")
    gcash = o["payment_method"] == "gcash"
    acct = (s.get("gcash_number") or "") if gcash else (s.get("bank_details") or "")
    rejected = P(f"⚠️ Your last screenshot was rejected: {o['payment_note']}. Please upload a new one.",
                 cls="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700") if o["payment_status"] == "rejected" else None

    def num(n):
        return Span(str(n), cls="grid size-7 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-white")

    copy_btn = Button("Copy", type="button", data_copy=acct.replace(" ", "") if gcash else acct,
                      onclick="navigator.clipboard.writeText(this.dataset.copy);this.textContent='Copied ✓'",
                      cls="press shrink-0 rounded-full bg-white px-3 py-1.5 text-xs font-bold ring-1 ring-stone-900/10") if acct else None
    return Div(Div(
        H3("Complete your payment", cls="text-lg font-bold"),
        P("We'll start preparing as soon as it's confirmed.", cls="text-sm text-stone-500"),
        rejected,
        Div(num(1), Div(P("Send ", Span(peso(o["total_cents"]), cls="font-extrabold"),
                          " via GCash" if gcash else " by bank transfer", cls="font-semibold"),
                        Div(Div(P(s.get("gcash_name") or "", cls="text-sm font-semibold") if gcash else None,
                                P(acct or "—", cls="font-mono text-lg font-bold" if gcash else "whitespace-pre-line text-sm font-medium"),
                                cls="min-w-0"),
                            copy_btn, cls="mt-2 flex items-center justify-between gap-3 rounded-2xl bg-stone-50 px-4 py-3"),
                        P(f"Put {o['code']} in the message.", cls="mt-1 text-xs text-stone-500"),
                        cls="min-w-0 flex-1"),
            cls="mt-4 flex gap-3"),
        Div(num(2), Form(
            P("Upload your screenshot", cls="font-semibold"),
            Label(Input(type="file", name="proof", accept="image/*", required=True, cls="sr-only",
                        onchange="this.nextElementSibling.textContent = this.files[0] ? '🖼 ' + this.files[0].name : 'Tap to choose a screenshot'"),
                  Span("Tap to choose a screenshot", cls="block truncate"),
                  cls="mt-2 block cursor-pointer rounded-2xl border-2 border-dashed border-stone-300 px-4 py-5 text-center "
                      "text-sm font-semibold text-stone-600 hover:border-stone-400"),
            Details(Summary("Add reference no. (optional)", cls="cursor-pointer text-xs font-semibold text-stone-500"),
                    Input(name="ref", maxlength="40", placeholder="e.g. 1029 384 756", cls=ui.INPUT_CLS + " mt-2"),
                    cls="mt-2"),
            ui.error_box(err, "proof-error"),
            Button("Send payment proof", type="submit", hx_disabled_elt="this",
                   cls="press mt-3 w-full rounded-full bg-brand py-3.5 font-bold text-white disabled:opacity-60"),
            hx_post=f"/order/{o['token']}/proof", hx_encoding="multipart/form-data",
            hx_target="#payment", hx_swap="outerHTML", cls="min-w-0 flex-1"),
            cls="mt-5 flex gap-3"),
        cls="rounded-3xl bg-white p-5 ring-1 ring-stone-900/[.06]"), id="payment")


def order_status_card(o: dict):
    final = o["status"] in ("completed", "cancelled")
    pickup = o["mode"] == "pickup"
    hero = {
        "pending_payment": ("💳", "Waiting for your payment", "Follow the steps below. It only takes a minute."),
        "preparing": ("👩‍🍳", "We're preparing your order", "Sit tight, the kitchen is on it."),
        "ready": ("✅", "Ready for pickup!" if pickup else "Your order is ready!",
                  "Show your order number at the counter." if pickup else "It'll be with you shortly."),
        "out_for_delivery": ("🛵", "On the way!", "Your rider is heading to you."),
        "completed": ("🎉", "Enjoy your meal!", "Salamat po! We hope to see you again."),
        "cancelled": ("✖️", "Order cancelled", "Contact the store if you have questions."),
    }[o["status"]]
    sched = None
    if o["scheduled_for"]:
        from datetime import datetime
        sched = P(f"🕒 Scheduled for {datetime.fromisoformat(o['scheduled_for']):%a %b %-d · %-I:%M %p}",
                  cls="mt-2 text-sm font-medium text-stone-600")
    return Div(
        Div(Div(Span(o["code"], cls="font-mono text-sm font-bold"),
                Span(Span(cls="size-2 animate-pulse rounded-full bg-emerald-500"), "Live",
                     cls="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-500") if not final else None,
                cls="flex items-center justify-between"),
            Div(Span(hero[0], cls="text-5xl" + (" animate-bounce" if o["status"] == "ready" else "")),
                Div(P(hero[1], cls="text-xl font-extrabold leading-tight"), P(hero[2], cls="text-sm text-stone-600")),
                cls="mt-3 flex items-center gap-4"),
            sched,
            Div(progress(o), cls="mt-6") if o["status"] != "cancelled" else None,
            cls="rounded-3xl bg-white p-5 ring-1 ring-stone-900/[.06]"),
        id="order-status",
        hx_get=None if final else f"/order/{o['token']}/status", hx_trigger=None if final else "every 10s",
        hx_swap="outerHTML")


@ar("/order/{token}", methods=["get"])
def order_page(req, token: str):
    _, con = ctx(req)
    s = db.get_settings(con)
    o = db.get_order(con, token=token)
    if not o:
        return Response("Order not found", status_code=404)
    items = [Div(Span(f"{li['qty']}×", cls="w-7 font-bold text-stone-500"),
                 Div(P(li["name"], cls="font-medium"),
                     P(" · ".join(([li["variant_name"]] if li["variant_name"] else []) +
                                  [m["name"] for m in li["modifiers"]]), cls="text-xs text-stone-500"),
                     P(f"“{li['note']}”", cls="text-xs italic text-stone-500") if li["note"] else None, cls="flex-1"),
                 Span(peso(li["line_total_cents"])), cls="flex gap-2 py-2.5 text-sm")
             for li in o["items"]]
    where = {"dine_in": f"Dine-in{' · Table ' + o['table_no'] if o['table_no'] else ''}",
             "pickup": "Pickup at " + (s.get("address") or s["name"]),
             "delivery": f"Delivery to {o['address']} ({o['zone_name']})",
             "cod": f"Cash on delivery to {o['address']} ({o['zone_name']})"}[o["mode"]]

    def info(icon, text):
        return Div(Span(icon, cls="w-6 text-center"), Span(text, cls="flex-1"), cls="flex gap-2 text-sm text-stone-700")

    return ui.page(f"Order {o['code']} · {s['name']}", s, Div(
        A(f"← {s['name']}", href="/", cls="text-sm font-semibold text-stone-600"),
        ui.heading("Your order"),
        Div(order_status_card(o), payment_panel(con, o, s), cls="grid gap-3"),
        Div(H3("Order details", cls="font-bold"),
            Div(info(MODE_ICON.get(o["mode"], "📍"), where),
                info(PAY_ICON.get(o["payment_method"], "💵"), db.PAY_LABEL[o["payment_method"]]),
                info("👤", f"{o['customer_name']} · {o['phone']}"), cls="mt-3 grid gap-2"),
            Div(*items, cls="mt-3 divide-y divide-stone-100 border-t border-stone-100"),
            Div(Span("Delivery fee"), Span(peso(o["delivery_fee_cents"])), cls="flex justify-between pt-2 text-sm")
            if o["delivery_fee_cents"] else None,
            Div(Span("Total", cls="font-bold"), Span(peso(o["total_cents"]), cls="text-lg font-extrabold"),
                cls="mt-2 flex items-baseline justify-between border-t border-stone-100 pt-3"),
            cls="mt-3 rounded-3xl bg-white p-5 ring-1 ring-stone-900/[.06]"),
        Div(Button("🔗 Copy tracking link", type="button",
                   onclick="navigator.clipboard.writeText(location.href);this.textContent='Link copied ✓'",
                   cls="press rounded-full bg-white px-4 py-3 text-sm font-semibold ring-1 ring-stone-900/10"),
            A("Order more", href="/menu", cls="press rounded-full bg-stone-900 px-4 py-3 text-center text-sm font-semibold text-white"),
            cls="mt-4 grid grid-cols-2 gap-2"),
        P("Keep this page to follow your order. ",
          A(f"Call {s['contact_phone']}", href=f"tel:{s['contact_phone'].replace(' ', '')}", cls="font-semibold underline")
          if s.get("contact_phone") else None, cls="mt-4 text-center text-xs text-stone-500"),
        cls="px-4 pt-5"))


@ar("/order/{token}/status", methods=["get"])
def order_status(req, token: str):
    _, con = ctx(req)
    o = db.get_order(con, token=token)
    if not o:
        return Response("", status_code=404)
    out = [order_status_card(o)]
    if o["status"] != "pending_payment":
        out.append(Div(id="payment", hx_swap_oob="true"))
    return tuple(out)


@ar("/order/{token}/proof", methods=["post"])
async def upload_proof(req, token: str):
    store, con = ctx(req)
    s = db.get_settings(con)
    o = db.get_order(con, token=token)
    if not o:
        return Response("", status_code=404)
    form = await req.form()
    up = form.get("proof")
    try:
        data = await up.read() if up is not None and hasattr(up, "read") else b""
        name = db.save_image(store, "proofs", data)
        o = db.submit_payment_proof(con, token, name, form.get("ref", ""))
    except db.OrderError as e:
        return payment_panel(con, o, s, str(e))
    return payment_panel(con, o, s), cart_events({}, "Payment proof sent")


# ---------------------------------------------------------------- media

@ar("/media/{name}", methods=["get"])
def media(req, name: str):
    store, _ = ctx(req)
    p = db.media_file(store, "media", name)
    if not p:
        return Response("Not found", status_code=404)
    return FileResponse(p, headers={"Cache-Control": "public, max-age=604800, immutable"})


# ---------------------------------------------------------------- AI concierge

@ar("/chat", methods=["post"])
def chat(req, sess, message: str = ""):
    _, con = ctx(req)
    if not sess.get("chat_id"):
        sess["chat_id"] = "c_" + secrets.token_hex(8)
    client_ip = req.client.host if req.client else "?"
    reply, cart, show = ai.concierge(con, req.scope["store"], sess["chat_id"], message, client_ip)
    if cart:
        sess["ai_cart"] = cart
    return (*ai.bubbles("", reply, cart_lines=cart, apply_url="/chat/apply" if cart else None),
            chat_items(con, sess, show))


def chat_items(con, sess, ids: list[int]):
    """Tappable item cards under a chat reply: tap to open options, + to add."""
    by_id = {i["id"]: i for i in db.items(con)}
    its = [by_id[i] for i in ids if i in by_id]
    if not its:
        return None
    opts, counts = items_with_options(con), cart_counts(sess)
    return Div(*[Div(Div(ui.img(img_url(it["image"]), it["name"], "aspect-square w-full rounded-xl text-4xl"),
                         sold_veil(it),
                         add_button(it, it["id"] in opts, "absolute -bottom-1.5 -right-1.5 !size-8 !text-xl"),
                         cls="relative rounded-xl"),
                     P(it["name"], cls="mt-2 line-clamp-2 text-xs font-semibold leading-snug"),
                     P(peso(it["price_cents"]), cls="text-xs font-extrabold text-deep"),
                     incart_pill(it, counts.get(str(it["id"]), 0), "mt-1"),
                     cls="press w-28 shrink-0 cursor-pointer", **open_attrs(it))
                 for it in its],
               cls="chat-in no-scrollbar -mx-4 flex gap-2.5 overflow-x-auto pb-1 pl-[3.25rem] pr-4")


@ar("/chat/apply", methods=["post"])
def chat_apply(req, sess):
    _, con = ctx(req)
    proposed = sess.get("ai_cart") or []
    cart, added, problems = get_cart(sess), 0, []
    for raw in proposed:
        try:
            ln = db.price_line(con, raw["item_id"], raw.get("variant_id"), raw.get("modifier_ids", []),
                               raw.get("qty", 1), raw.get("note", ""))
        except (db.OrderError, KeyError, TypeError, ValueError) as e:
            problems.append(str(e))
            continue
        if len(cart) < MAX_CART_LINES:
            _merge_into_cart(cart, ln)
            added += ln["qty"]
    sess["cart"] = cart
    sess.pop("ai_cart", None)
    msg = f"Added {added} item(s) to your cart." + (" " + " ".join(problems) if problems else "")
    return (Div(P("✓ " + msg, cls="text-xs font-semibold text-emerald-700"), cls="ml-9 py-1"),
            *cart_oob(req, con, sess), cart_events(sess, msg))

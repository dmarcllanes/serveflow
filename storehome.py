"""A store's public homepage (`<store>.yourdomain.com/`): a branded landing page built from the
store's own settings and live menu: hero, best sellers, menu by category, about, how to order,
hours & location. Every "Order" button leads into the ordering flow at /menu (storefront.py),
and orders land in the owner's kitchen queue as usual.

Owner-editable in Admin → Website: hero_title, about, cover (photo), facebook, instagram.
"""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote, quote_plus

from fasthtml.common import (
    A, APIRouter, Button, Div, Footer, H1, H2, H3, Header, Img, Link, Nav, NotStr, P, Script, Section,
    Span, Style, Title,
)
from starlette.responses import RedirectResponse

import ai
import db
import storefront
import ui
from ui import peso

ar = APIRouter()

FONT = Link(rel="stylesheet",
            href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800&display=swap")

CSS = """
html{scroll-behavior:smooth}
.font-display{font-family:'Bricolage Grotesque',Inter,system-ui,sans-serif;letter-spacing:-.025em}
.bg-soft{background:color-mix(in srgb,var(--brand) 9%,#fff)}
.bg-soft2{background:color-mix(in srgb,var(--brand) 16%,#fff)}
.text-deep{color:color-mix(in srgb,var(--brand) 75%,#000)}
.ring-soft{--tw-ring-color:color-mix(in srgb,var(--brand) 22%,transparent)}
.hero-glow{background:radial-gradient(60% 60% at 15% 10%,color-mix(in srgb,var(--brand) 22%,transparent),transparent 70%),
  radial-gradient(50% 50% at 90% 20%,color-mix(in srgb,var(--accent) 90%,transparent),transparent 70%),
  radial-gradient(40% 50% at 60% 100%,color-mix(in srgb,var(--brand) 12%,transparent),transparent 70%)}
.grain{background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
.tile{background:linear-gradient(140deg,color-mix(in srgb,var(--accent) 85%,#fff),color-mix(in srgb,var(--brand) 18%,#fff))}
.floaty{animation:floaty 6s ease-in-out infinite}@keyframes floaty{50%{transform:translateY(-10px)}}
.js .reveal{opacity:0;transform:translateY(24px);transition:opacity .7s cubic-bezier(.2,.7,.2,1),transform .7s cubic-bezier(.2,.7,.2,1);transition-delay:var(--d,0ms)}
.js .reveal.in{opacity:1;transform:none}
[data-catpanel][hidden]{display:none!important}
.cat-tab[aria-selected=true]{background:var(--brand);color:#fff;--tw-ring-color:transparent}
.marquee{animation:marquee 35s linear infinite}@keyframes marquee{to{transform:translateX(-50%)}}
.card-lift{transition:transform .25s cubic-bezier(.2,.8,.2,1),box-shadow .25s}
.card-lift:hover{transform:translateY(-4px);box-shadow:0 24px 40px -24px rgba(28,25,23,.35)}
#store-nav.scrolled .nav-inner{background:rgba(255,255,255,.8);backdrop-filter:blur(14px);box-shadow:0 0 0 1px rgba(28,25,23,.07),0 12px 30px -12px rgba(28,25,23,.2)}
.nav-inner{transition:background .3s,box-shadow .3s}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.js .reveal{opacity:1;transform:none}}
"""

JS = """
(() => {
const $$ = s => [...document.querySelectorAll(s)];
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), {threshold: .12});
$$('.reveal').forEach(el => io.observe(el));
const nav = document.getElementById('store-nav'); const sc = () => nav.classList.toggle('scrolled', scrollY > 12);
addEventListener('scroll', sc, {passive: true}); sc();
$$('[data-cat]').forEach(t => t.addEventListener('click', () => {
  $$('[data-cat]').forEach(x => x.setAttribute('aria-selected', x === t));
  $$('[data-catpanel]').forEach(p => p.hidden = p.dataset.catpanel !== t.dataset.cat);
}));
})();
"""


# Owner-editable homepage text & section switches (Admin → Website → Homepage sections).
# Stored in the `home` setting as {"show_<key>": bool, "<text key>": str}; "{name}" = store name.
HOME_SECTIONS = [
    ("hero", "Top section", False, [("order_label", "Order button", "Order now"),
                                     ("hero_second", "Second button", "See best sellers")]),
    ("marquee", "Scrolling category strip", True, []),
    ("best", "Best sellers", True, [("best_label", "Small label", "Customer favorites"),
                                    ("best_title", "Title", "Best sellers"),
                                    ("best_sub", "Subtitle", "Tap a card to see options, or hit + to add it.")]),
    ("menu", "Menu preview", True, [("menu_label", "Small label", "The menu"),
                                    ("menu_title", "Title", "Something for every craving")]),
    ("about", "About us", True, [("about_label", "Small label", "Our story"),
                                 ("about_title", "Title", "About {name}")]),
    ("how", "How ordering works", True, [("how_title", "Title", "Ordering takes a minute")]),
    ("visit", "Hours & location", True, [("visit_label", "Small label", "Visit us"),
                                         ("visit_title", "Title", "Hours & location")]),
    ("final", "Closing banner", True, [("final_title", "Title", "Hungry? Your order is a minute away."),
                                       ("final_sub", "Subtitle", "Order straight from {name}.")]),
]


def home_cfg(s: dict) -> dict:
    saved = s.get("home") if isinstance(s.get("home"), dict) else {}
    h: dict = {}
    for key, _, toggle, texts in HOME_SECTIONS:
        if toggle:
            h[f"show_{key}"] = bool(saved.get(f"show_{key}", True))
        for tkey, _, default in texts:
            h[tkey] = (str(saved.get(tkey) or "").strip() or default).replace("{name}", s["name"])
    return h


def _media(name: str | None) -> str | None:
    return f"/media/{name}" if name else None


def _thumb(it: dict, cls: str):
    if it.get("image"):
        return Img(src=_media(it["image"]), alt=it["name"], loading="lazy", cls=f"object-cover {cls}")
    return Div(NotStr(ui.food_emoji(it["name"])), cls=f"tile grid place-items-center {cls}")


def _order_btn(text, href="/menu", cls="", light=False):
    style = "bg-white text-stone-950 hover:bg-white/90" if light else "bg-brand text-white hover:brightness-110"
    return A(Span(text), Span("→", cls="transition-transform group-hover:translate-x-1"), href=href,
             cls=f"group inline-flex items-center justify-center gap-2 rounded-full px-6 py-3.5 font-semibold "
                 f"shadow-lg shadow-stone-900/10 transition hover:-translate-y-0.5 {style} {cls}")


def _stock_note(it: dict):
    if not it["available"]:
        return Span("Sold out today", cls="rounded-full bg-stone-900 px-2 py-0.5 text-[11px] font-bold text-white")
    if it["remaining"] is not None and it["remaining"] <= 5:
        return Span(f"Only {it['remaining']} left", cls="rounded-full bg-orange-100 px-2 py-0.5 text-[11px] font-bold text-orange-800")
    return None


def _status_pill(status: dict):
    if status["open"]:
        txt = "Open now" + (f" · until {status['closes']:%-I:%M %p}" if status.get("closes") else "")
        dot = "bg-green-500"
    elif not status["accepting"]:
        txt, dot = "Not taking online orders right now", "bg-red-500"
    else:
        txt = "Closed" + (f" · opens {status['opens']:%a %-I:%M %p}" if status.get("opens") else "") + " · order ahead"
        dot = "bg-amber-500"
    return Span(Span(cls=f"size-2 rounded-full {dot}"), txt,
                cls="inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-xs font-semibold "
                    "ring-1 ring-stone-900/10 backdrop-blur")


# ---------------------------------------------------------------- sections

def _nav(s: dict, h: dict, has_best: bool, has_about: bool):
    initial = (s["name"] or "?")[:1].upper()
    logo = (Img(src=_media(s["logo"]), alt="", cls="size-9 rounded-full object-cover") if s.get("logo")
            else Span(initial, cls="grid size-9 place-items-center rounded-full bg-brand font-display font-bold text-white"))
    links = ([("Best sellers", "#best")] if has_best else []) + ([("Menu", "#menu")] if h["show_menu"] else []) + \
        ([("About", "#about")] if has_about else []) + ([("Visit", "#visit")] if h["show_visit"] else [])
    return Header(
        Nav(A(logo, Span(s["name"], cls="font-display text-lg font-bold truncate max-w-[45vw]"), href="#top",
              cls="flex min-w-0 items-center gap-2.5"),
            Div(*[A(t, href=h, cls="rounded-full px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-900/5")
                  for t, h in links], cls="hidden md:flex"),
            A(h["order_label"], href="/menu", cls="shrink-0 rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white"),
            cls="nav-inner mx-auto flex max-w-6xl items-center justify-between gap-3 rounded-full px-3 py-2 pl-3"),
        id="store-nav", cls="fixed inset-x-0 top-3 z-40 px-3")


def _hero(s: dict, status: dict, featured: list[dict], modes: list[str], ox: dict, h: dict, has_best: bool):
    title = s.get("hero_title") or s["name"]
    sub = s.get("tagline") or ""
    if s.get("cover"):
        visual = Div(Img(src=_media(s["cover"]), alt=s["name"], cls="h-full w-full object-cover"),
                     cls="reveal aspect-[4/5] w-full max-w-md overflow-hidden rounded-[2.5rem] shadow-2xl shadow-stone-900/20 [--d:150ms]")
    else:  # collage of real menu items
        cards = []
        pos = ["left-0 top-6 -rotate-6", "right-0 top-0 rotate-3", "left-10 bottom-0 rotate-2", "right-6 bottom-10 -rotate-3"]
        for k, it in enumerate(featured[:4]):
            cards.append(Div(
                Div(_thumb(it, "h-32 w-full rounded-2xl text-6xl"),
                    storefront.add_button(it, it["id"] in ox["opts"], "absolute -bottom-2 -right-2 !size-9"),
                    cls="relative"),
                P(it["name"], cls="mt-2 truncate pr-6 text-sm font-semibold"),
                P(peso(it["price_cents"]), cls="text-sm font-bold text-deep"),
                cls=f"floaty absolute w-44 cursor-pointer rounded-3xl bg-white p-2.5 shadow-xl shadow-stone-900/10 "
                    f"ring-1 ring-stone-900/5 transition hover:shadow-2xl {pos[k]}",
                style=f"animation-delay:-{k * 1.5}s", **storefront.open_attrs(it)))
        visual = Div(*cards, cls="reveal relative h-[420px] w-full max-w-md [--d:150ms]")
    chips = [Span(db.MODE_LABEL[m], cls="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold ring-1 ring-stone-900/10")
             for m in modes]
    return Section(
        Div(cls="hero-glow pointer-events-none absolute inset-0"),
        Div(cls="grain pointer-events-none absolute inset-0 opacity-[.25] mix-blend-multiply"),
        Div(Div(Div(_status_pill(status), cls="reveal"),
                H1(title, cls="reveal font-display mt-6 text-5xl sm:text-6xl lg:text-7xl font-bold leading-[1] text-balance [--d:80ms]"),
                P(sub, cls="reveal mt-5 max-w-lg text-lg text-stone-600 text-pretty [--d:160ms]") if sub else None,
                Div(_order_btn(h["order_label"]),
                    A(h["hero_second"], href="#best" if has_best else "/menu",
                      cls="inline-flex items-center rounded-full bg-white/70 px-6 py-3.5 font-semibold ring-1 ring-stone-900/10 hover:ring-stone-900/25"),
                    cls="reveal mt-8 flex flex-wrap gap-3 [--d:240ms]"),
                Div(*chips, cls="reveal mt-6 flex flex-wrap gap-2 [--d:320ms]") if chips else None,
                cls="relative z-10 flex-1"),
            Div(visual, cls="relative z-10 flex w-full flex-1 justify-center"),
            cls="relative mx-auto flex max-w-6xl flex-col items-center gap-12 px-5 pb-20 pt-32 sm:pt-36 lg:flex-row"),
        id="top", cls="relative overflow-hidden")


def _cat_marquee(cats: list[dict], by_cat: dict):
    if len(cats) < 2:
        return None
    row = [A(Span(ui.food_emoji(by_cat[c["id"]][0]["name"] if by_cat.get(c["id"]) else c["name"]), cls="text-2xl"),
             Span(c["name"], cls="font-display text-2xl font-bold"), Span("✦", cls="ml-6 text-brand"),
             href=f"/menu#cat-{c['id']}", cls="flex shrink-0 items-center gap-3 pr-6")
           for c in cats]
    reps = max(2, 8 // len(row))
    return Section(Div(Div(*(row * reps * 2), cls="marquee flex w-max"), cls="overflow-hidden"),
                   cls="border-y border-stone-900/10 bg-white/70 py-5 [mask-image:linear-gradient(90deg,transparent,#000_8%,#000_92%,transparent)]")


def _best(featured: list[dict], ox: dict, h: dict):
    def card(k, it):
        has_opts = it["id"] in ox["opts"]
        return Div(
            Div(_thumb(it, "aspect-[4/3] w-full text-7xl transition duration-500 group-hover:scale-105"),
                Div(_stock_note(it), cls="absolute left-3 top-3"),
                Div(storefront.incart_pill(it, ox["counts"].get(str(it["id"]), 0), "shadow"), cls="absolute right-3 top-3"),
                storefront.sold_veil(it),
                cls="relative overflow-hidden rounded-[1.5rem]"),
            Div(Div(H3(it["name"], cls="font-display text-lg font-bold leading-tight"),
                    Span(peso(it["price_cents"]), cls="shrink-0 font-bold text-deep"),
                    cls="flex items-start justify-between gap-3"),
                P(it["description"], cls="mt-1 line-clamp-2 text-sm text-stone-500") if it["description"] else None,
                Div(ui.item_badges(it), cls="mt-2"),
                cls="flex-1 px-1 pt-3"),
            Div(Span("Choose size & add-ons" if has_opts else "Ready to add" if it["available"] else "Back tomorrow",
                     cls="text-sm font-medium text-stone-500"),
                storefront.add_button(it, has_opts),
                cls="mt-4 flex items-center justify-between rounded-full bg-soft py-1.5 pl-4 pr-1.5"),
            cls=f"group card-lift reveal flex flex-col rounded-[2rem] bg-white p-3 ring-1 ring-stone-900/[.06] "
                f"{'cursor-pointer' if it['available'] else 'opacity-70'}",
            style=f"--d:{(k % 3) * 90}ms", **storefront.open_attrs(it))
    return Section(
        Div(Div(P(h["best_label"], cls="text-xs font-bold uppercase tracking-[.18em] text-brand"),
                H2(h["best_title"], cls="font-display mt-3 text-4xl sm:text-5xl font-bold text-balance"),
                P(h["best_sub"], cls="mt-3 text-stone-500"),
                cls="reveal flex flex-col"),
            Div(*[card(k, it) for k, it in enumerate(featured)], cls="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"),
            cls="mx-auto max-w-6xl px-5 py-24"),
        id="best")


def _menu(cats: list[dict], by_cat: dict, ox: dict, h: dict):
    cats = [c for c in cats if by_cat.get(c["id"])]
    if not cats:
        return None
    tabs = Div(*[Button(c["name"], type="button", role="tab", data_cat=str(c["id"]),
                        aria_selected="true" if i == 0 else "false",
                        cls="cat-tab shrink-0 rounded-full bg-white px-4 py-2 text-sm font-semibold ring-1 ring-stone-200 transition")
                 for i, c in enumerate(cats)], role="tablist", cls="no-scrollbar mt-8 flex gap-2 overflow-x-auto pb-1")
    panels = [Div(*[Div(_thumb(it, "size-16 shrink-0 rounded-2xl text-3xl"),
                        Div(Div(P(it["name"], cls="truncate font-semibold"), _stock_note(it), cls="flex items-center gap-2"),
                            P(it["description"], cls="truncate text-sm text-stone-500") if it["description"] else None,
                            Div(Span(peso(it["price_cents"]), cls="font-bold"),
                                storefront.incart_pill(it, ox["counts"].get(str(it["id"]), 0)),
                                cls="mt-0.5 flex items-center gap-2"),
                            cls="min-w-0 flex-1"),
                        storefront.add_button(it, it["id"] in ox["opts"], "shrink-0 !ring-0"),
                        cls=f"press flex items-center gap-4 rounded-2xl bg-white p-3 ring-1 ring-stone-900/[.06] transition "
                            f"hover:shadow-md hover:ring-stone-900/20 {'cursor-pointer' if it['available'] else 'opacity-60'}",
                        **storefront.open_attrs(it))
                    for it in by_cat[c["id"]]],
                  data_catpanel=str(c["id"]), hidden=i != 0, cls="mt-5 grid gap-2 md:grid-cols-2")
              for i, c in enumerate(cats)]
    return Section(
        Div(Div(P(h["menu_label"], cls="text-xs font-bold uppercase tracking-[.18em] text-brand"),
                H2(h["menu_title"], cls="font-display mt-3 text-4xl sm:text-5xl font-bold text-balance"),
                cls="reveal"),
            tabs, *panels,
            Div(_order_btn("See the full menu"), cls="mt-8"),
            cls="mx-auto max-w-6xl px-5 py-24"),
        id="menu", cls="bg-soft")


def _about(s: dict, h: dict):
    about = (s.get("about") or "").strip()
    if not about:
        return None
    paras = [P(p.strip(), cls="mt-4 text-lg leading-relaxed text-stone-700") for p in about.split("\n") if p.strip()]
    return Section(
        Div(Div(P(h["about_label"], cls="text-xs font-bold uppercase tracking-[.18em] text-brand"),
                H2(h["about_title"], cls="font-display mt-3 text-4xl sm:text-5xl font-bold text-balance"),
                cls="reveal lg:w-2/5"),
            Div(*paras, cls="reveal lg:w-3/5 [--d:120ms]"),
            cls="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-24 lg:flex-row lg:gap-16"),
        id="about")


def _how(s: dict, modes: list[str], h: dict):
    say = {"gcash": "GCash", "bank": "bank transfer", "counter": "at the counter"}
    pays = [say[p] for p in s.get("payments", []) if p in say]
    if "cod" in modes:
        pays.append("cash on delivery")
    pays_txt = ", ".join(pays[:-1]) + (" or " if len(pays) > 1 else "") + pays[-1] if pays else ""
    steps = [("Pick your favorites", "Browse the menu and customize: sizes, add-ons and notes for the kitchen."),
             ("Choose how", " · ".join(db.MODE_LABEL[m] for m in modes) + ". Order now or schedule a time."),
             ("Pay & track", (f"Pay with {pays_txt}. " if pays else "") + "Follow your order live, no need to message us.")]
    return Section(
        Div(H2(h["how_title"], cls="reveal font-display text-center text-4xl sm:text-5xl font-bold"),
            Div(*[Div(Span(str(i + 1), cls="font-display grid size-12 place-items-center rounded-full bg-brand text-lg font-bold text-white"),
                      H3(t, cls="font-display mt-4 text-xl font-bold"), P(d, cls="mt-2 text-stone-600"),
                      cls="reveal rounded-[2rem] bg-white p-6 ring-1 ring-stone-900/[.06]", style=f"--d:{i * 100}ms")
                  for i, (t, d) in enumerate(steps)],
                cls="mt-10 grid gap-4 md:grid-cols-3"),
            cls="mx-auto max-w-6xl px-5 py-24"))


def _visit(s: dict, h: dict):
    today = db.now().weekday()
    def ampm(t: str) -> str:
        h, m = (int(x) for x in t.split(":"))
        return f"{h % 12 or 12}{':%02d' % m if m else ''} {'AM' if h < 12 or h == 24 else 'PM'}"
    hours = [(d, " – ".join(ampm(t) for t in span) if span else "Closed")
             for d, span in zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                                [(s.get("hours") or {}).get(str(i)) for i in range(7)])]
    addr = (s.get("address") or "").strip()
    phone = (s.get("contact_phone") or "").strip()
    socials = [(lbl, s.get(k)) for k, lbl in (("facebook", "Facebook"), ("instagram", "Instagram"))
               if str(s.get(k) or "").startswith("https://")]
    return Section(
        Div(Div(P(h["visit_label"], cls="text-xs font-bold uppercase tracking-[.18em] text-brand"),
                H2(h["visit_title"], cls="font-display mt-3 text-4xl sm:text-5xl font-bold"),
                P(addr, cls="mt-6 text-lg") if addr else None,
                A("Open in Google Maps ↗", href=f"https://www.google.com/maps/search/?api=1&query={quote_plus(addr)}",
                  target="_blank", rel="noopener", cls="mt-2 inline-block font-semibold text-deep underline") if addr else None,
                P(A(f"📞 {phone}", href=f"tel:{phone.replace(' ', '')}", cls="font-semibold"), cls="mt-5") if phone else None,
                Div(*[A(lbl, href=url, target="_blank", rel="noopener",
                        cls="rounded-full bg-white px-4 py-2 text-sm font-semibold ring-1 ring-stone-900/10 hover:ring-stone-900/30")
                      for lbl, url in socials], cls="mt-5 flex gap-2") if socials else None,
                cls="reveal flex-1"),
            Div(*[Div(Span(d, cls="font-semibold"), Span(h, cls="tabular-nums"),
                      cls=f"flex justify-between rounded-xl px-4 py-2.5 {'bg-brand text-white' if i == today else ''}")
                  for i, (d, h) in enumerate(hours)],
                cls="reveal flex-1 rounded-[2rem] bg-white p-3 ring-1 ring-stone-900/[.06] [--d:120ms]"),
            cls="mx-auto flex max-w-6xl flex-col gap-10 px-5 py-24 lg:flex-row"),
        id="visit")


def _final(s: dict, h: dict):
    return Section(
        Div(Div(cls="grain pointer-events-none absolute inset-0 opacity-[.15]"),
            Div(H2(h["final_title"], cls="font-display text-4xl sm:text-5xl font-bold text-balance"),
                P(h["final_sub"], cls="mt-3 text-white/80") if h["final_sub"] else None,
                Div(_order_btn(h["order_label"], light=True), cls="mt-8"),
                cls="relative z-10"),
            cls="reveal relative mx-auto max-w-5xl overflow-hidden rounded-[2.5rem] bg-brand px-6 py-16 text-center text-white sm:py-20"),
        cls="px-4 pb-16")


# ---------------------------------------------------------------- route

@ar("/", methods=["get"])
def home(req, sess, table: str = ""):
    if table:  # a table QR → straight to the menu with the table remembered
        return RedirectResponse(f"/menu?table={quote(table)}", status_code=303)
    con = db.get_db(req.scope["store"])
    db.housekeep(con, req.scope["store"])
    s = db.get_settings(con)
    status = db.kitchen_status(s)
    cats = db.categories(con)
    its = db.items(con)
    by_cat: dict = {}
    for it in its:
        by_cat.setdefault(it["category_id"], []).append(it)
    featured = [it for it in its if "best_seller" in it["tags"]]
    featured = (featured + [it for it in its if it not in featured])[:6]
    modes = [m for m in db.MODES if m in s["modes"]]
    ox = {"opts": storefront.items_with_options(con), "counts": storefront.cart_counts(sess)}
    h = home_cfg(s)
    has_best = bool(featured) and h["show_best"]
    has_about = bool((s.get("about") or "").strip()) and h["show_about"]
    preview = Div(Span("Preview", cls="font-bold"), " · only you can see this until your store goes live. ",
                  A("Back to admin", href="/admin/start", cls="font-semibold underline"),
                  cls="relative z-50 bg-amber-100 px-4 py-2 text-center text-sm text-amber-900") if req.scope.get("preview") else None
    desc = s.get("tagline") or f"Order online from {s['name']}"
    from fasthtml.common import Meta
    return (Title(f"{s['name']} · Order online"),
            Meta(name="description", content=desc), Meta(property="og:title", content=s["name"]),
            Meta(property="og:description", content=desc),
            ui.theme(s), FONT, Style(CSS), Script("document.documentElement.classList.add('js')"),
            preview, _nav(s, h, has_best, has_about),
            Div(_hero(s, status, featured, modes, ox, h, has_best),
                _cat_marquee(cats, by_cat) if h["show_marquee"] else None,
                _best(featured, ox, h) if has_best else None,
                _menu(cats, by_cat, ox, h) if h["show_menu"] else None,
                _about(s, h) if has_about else None,
                _how(s, modes, h) if h["show_how"] else None,
                _visit(s, h) if h["show_visit"] else None,
                _final(s, h) if h["show_final"] else None, cls="overflow-x-clip bg-[#faf7f2]"),
            Footer(Div(P(f"© {datetime.now().year} {s['name']}", cls="font-semibold"),
                       P("Online ordering by ServeFlow · 0% commission", cls="text-stone-500"),
                       cls="mx-auto flex max-w-6xl flex-col justify-between gap-1 px-5 py-8 pb-24 text-sm sm:flex-row md:pb-8"),
                   cls="border-t border-stone-900/10 bg-[#faf7f2]"),
            storefront.cart_bar(con, sess, empty=(h["order_label"], "/menu")), ai.chat_widget("concierge", s), Script(JS),
            Div(id="modal"), Div(id="toast", cls="fixed bottom-24 inset-x-0 z-50 flex flex-col gap-2 pointer-events-none"),
            ui.TOAST_JS)

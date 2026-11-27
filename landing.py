"""Marketing page served on the bare domain (no store subdomain).

Config (all optional):
  CONTACT_URL  "Talk to us" button + the "message us to go live" link in a new store's admin
               (e.g. https://m.me/yourpage or mailto:)

The "Create your store" form posts to /signup (signup.py), which creates the store and logs the
owner straight into <store>/admin.

Everything interactive here is a client-side illustration (vanilla JS, no requests); it never
touches a store DB.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fasthtml.common import (
    A, Body, Button, Details, Div, Footer, Form, H1, H2, H3, Head, Header, Html, Input, Label, Li, Link,
    Meta, Nav, P, Script, Section, Span, Style, Summary, Title, Ul, to_xml,
)
from starlette.responses import Response

import db
import ui

ORANGE = "#c2410c"


# ---------------------------------------------------------------- urls

def _store_url(store: str, base: str) -> str:
    if base == "localhost":
        return f"http://{store}.localhost:{os.environ.get('PORT', '5001')}/"
    return f"https://{store}.{base}/"


# ---------------------------------------------------------------- small pieces

def _btn(*text, href, kind="primary", cls=""):
    styles = {
        "primary": "bg-stone-950 text-white hover:bg-orange-700 shadow-lg shadow-stone-900/10",
        "brand": "bg-orange-600 text-white hover:bg-orange-700 shadow-lg shadow-orange-700/25",
        "ghost": "bg-white/70 text-stone-900 ring-1 ring-stone-900/10 hover:ring-stone-900/25 backdrop-blur",
        "light": "bg-white text-stone-950 hover:bg-orange-50",
        "outline-light": "text-white ring-1 ring-white/30 hover:ring-white/70",
    }
    ext = {"target": "_blank", "rel": "noopener"} if href.startswith("http") else {}
    return A(*text, href=href, **ext,
             cls=f"mag group inline-flex items-center justify-center gap-2 rounded-full px-6 py-3.5 text-[15px] "
                 f"font-semibold {styles[kind]} {cls}")


def _arrow():
    return Span("→", cls="transition-transform group-hover:translate-x-1")


def _eyebrow(text, dark=False):
    return P(Span(cls="inline-block size-1.5 rounded-full bg-orange-500 mr-2 align-middle"), text,
             cls=f"text-xs font-bold uppercase tracking-[.18em] {'text-orange-300' if dark else 'text-orange-700'}")


def _head(eyebrow, title, sub=None, dark=False, center=False):
    return Div(_eyebrow(eyebrow, dark),
               H2(title, cls="font-display mt-4 text-4xl sm:text-5xl font-bold leading-[1.02] text-balance"),
               P(sub, cls=f"mt-4 text-lg text-pretty {'text-stone-400' if dark else 'text-stone-600'}") if sub else None,
               cls=f"reveal max-w-2xl {'mx-auto text-center' if center else ''}")


def _ctas(contact, demo=None, dark=False, center=False, secondary=None):
    out = [_btn(Span("Create your store"), _arrow(), href="#start", kind="light" if dark else "brand")]
    if contact:
        out.append(_btn(Span("Talk to us"), href=contact, kind="outline-light" if dark else "ghost"))
    elif secondary:
        out.append(_btn(Span(secondary[0]), href=secondary[1], kind="outline-light" if dark else "ghost"))
    return Div(*out, cls=f"flex flex-wrap gap-3 {'justify-center' if center else ''}")


def _card(*c, cls="", dark=False):
    base = ("bg-white/[.04] ring-1 ring-white/10" if dark
            else "bg-white ring-1 ring-stone-900/[.07] shadow-[0_1px_0_rgba(0,0,0,.03),0_20px_40px_-24px_rgba(28,25,23,.18)]")
    return Div(*c, cls=f"spot relative overflow-hidden rounded-[1.75rem] {base} {cls}")


def _pill(text, cls=""):
    return Span(text, cls=f"inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold {cls}")


# ---------------------------------------------------------------- hero phone (interactive)

MENU = {
    "Coffee": [("Ube Spanish Latte", "Espresso, condensed milk, ube halaya", 145, "best"),
               ("Iced Americano", "Double shot, 16oz", 110, None),
               ("Salted Caramel Macchiato", "House caramel, sea salt foam", 165, "new")],
    "Rice Meals": [("Chicken Adobo Bowl", "Garlic rice, soft egg, atchara", 185, "best"),
                   ("Sisig Rice", "Sizzling pork sisig, calamansi", 195, "spicy"),
                   ("Tapsilog", "Beef tapa, sinangag, itlog", 180, None)],
    "Pastries": [("Ensaymada", "Baked this morning", 75, "out"),
                 ("Ube Cheese Pandesal", "Soft, warm · 6 left", 25, "low"),
                 ("Banana Bread", "Thick slice, walnuts", 95, None)],
    "Milk Tea": [("Brown Sugar Boba", "Tiger stripes, fresh milk", 130, "best"),
                 ("Wintermelon", "Classic, 50% sugar", 115, None),
                 ("Taro Milk Tea", "Real taro, pearls", 125, None)],
}
BADGE = {"best": ("★ Best Seller", "bg-amber-100 text-amber-800"), "spicy": ("🌶 Spicy", "bg-red-50 text-red-700"),
         "new": ("New", "bg-sky-50 text-sky-700"), "low": ("6 left", "bg-orange-50 text-orange-700")}


def _menu_row(name, desc, price, tag):
    out = tag == "out"
    b = BADGE.get(tag)
    return Div(
        Div(cls="size-12 shrink-0 rounded-xl bg-gradient-to-br from-amber-100 via-orange-100 to-rose-100"),
        Div(Div(P(name, cls="truncate font-semibold text-[13px] leading-tight"), _pill(b[0], b[1] + " shrink-0") if b else None,
                cls="flex min-w-0 items-center gap-1.5"),
            P(desc, cls="truncate text-[11px] text-stone-500 mt-0.5"),
            Div(Span(f"₱{price}", cls="text-[13px] font-bold"),
                _pill("Sold out", "bg-stone-900 text-white") if out else
                Button("+", type="button", data_add=name, data_price=str(price), aria_label=f"Add {name}",
                       cls="grid place-items-center size-7 rounded-full bg-orange-600 text-white font-bold "
                           "hover:bg-orange-700 active:scale-90 transition"),
                cls="mt-1 flex items-center justify-between"),
            cls="flex-1 min-w-0"),
        cls=f"flex gap-3 rounded-2xl bg-white p-2.5 ring-1 ring-stone-200/80 {'opacity-50 grayscale' if out else ''}")


def _phone():
    cats = list(MENU)
    return Div(
        Div(cls="absolute left-1/2 top-2.5 z-10 h-5 w-24 -translate-x-1/2 rounded-full bg-stone-950"),
        Div(
            Div(Div(P("Your Café", cls="font-display font-bold text-lg leading-none"),
                    P(Span(cls="inline-block size-1.5 rounded-full bg-green-500 mr-1.5 align-middle"),
                      "Open · until 9 PM", cls="mt-1 text-[11px] text-stone-500")),
                Div("YC", cls="grid size-9 place-items-center rounded-full bg-orange-600 text-white text-xs font-bold"),
                cls="flex items-center justify-between px-1 pt-5"),
            Div(*[Button(c, type="button", role="tab", data_tab=c, aria_selected="true" if i == 0 else "false",
                         cls="tab shrink-0 rounded-full bg-white px-3 py-1 text-[11px] font-semibold ring-1 ring-stone-200 transition")
                  for i, c in enumerate(cats)],
                role="tablist", cls="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto"),
            Div(*[Div(*[_menu_row(*r) for r in MENU[c]], data_panel=c, hidden=i != 0, cls="space-y-2")
                  for i, c in enumerate(cats)],
                cls="no-scrollbar mt-3 h-[282px] overflow-y-auto"),
            Div(P("Added", id="phone-toast", cls="phone-toast pointer-events-none absolute inset-x-6 bottom-[70px] "
                                                  "rounded-full bg-stone-950 px-3 py-1.5 text-center text-[11px] font-semibold text-white"),
                Div(Span("Tap + to add", id="cart-count", cls="font-semibold"),
                    Span("₱0", id="cart-total", cls="font-bold tabular-nums"),
                    id="cart-bar",
                    cls="flex items-center justify-between rounded-full bg-orange-600 px-4 py-2.5 text-[13px] text-white"),
                cls="mt-3"),
            cls="relative rounded-[2rem] bg-[#faf7f2] p-3.5 pb-4"),
        id="phone",
        cls="relative w-[300px] rounded-[2.6rem] bg-stone-950 p-2.5 shadow-[0_50px_100px_-30px_rgba(124,45,18,.45)] "
            "ring-1 ring-white/10")


def _float_chip(dot, title, sub, cls):
    return Div(Span(cls=f"size-2 rounded-full {dot}"),
               Div(P(title, cls="text-xs font-bold leading-tight"), P(sub, cls="text-[10px] text-stone-500")),
               cls=f"floaty pointer-events-none absolute z-20 hidden md:flex items-center gap-2.5 rounded-2xl bg-white/90 px-3.5 py-2.5 "
                   f"shadow-xl shadow-stone-900/10 ring-1 ring-stone-900/5 backdrop-blur {cls}")


# ---------------------------------------------------------------- sections

def _nav(contact, demo):
    return Header(
        Nav(A(Span(cls="size-2.5 rounded-full bg-gradient-to-br from-orange-500 to-rose-500"),
              Span("ServeFlow", cls="font-display text-lg font-bold"), href="#top", cls="flex items-center gap-2"),
            Div(*[A(t, href=h, cls="rounded-full px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-900/5 hover:text-stone-950 transition")
                  for t, h in (("Features", "#features"), ("A day", "#day"), ("AI", "#ai"), ("Kitchen", "#kitchen"),
                               ("Pricing", "#pricing"), ("FAQ", "#faq"))],
                cls="hidden md:flex items-center"),
            Div(A("Log in", href="/login", cls="rounded-full px-3 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-900/5"),
                A("Create your store", href="#start",
                  cls="rounded-full bg-stone-950 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-700 transition"),
                cls="flex items-center gap-1"),
            cls="nav-inner mx-auto flex max-w-5xl items-center justify-between gap-4 rounded-full px-3 py-2 pl-5"),
        id="nav", cls="fixed inset-x-0 top-3 z-50 px-3")


def _hero(contact, demo):
    words = ["café.", "milk tea shop.", "carinderia.", "bakery.", "cloud kitchen.", "restaurant."]
    return Section(
        Div(Div(cls="blob left-[-10%] top-[-10%] size-[520px] bg-orange-300"),
            Div(cls="blob right-[-8%] top-[10%] size-[460px] bg-rose-300 [animation-delay:-6s]"),
            Div(cls="blob left-[30%] bottom-[-20%] size-[420px] bg-amber-200 [animation-delay:-12s]"),
            Div(cls="grid-bg absolute inset-0"),
            Div(cls="grain absolute inset-0 opacity-[.35] mix-blend-multiply"),
            cls="pointer-events-none absolute inset-0 overflow-hidden"),
        Div(
            Div(Div(Span(_pill("NEW", "bg-orange-600 text-white mr-2"), "AI Menu Concierge is live",
                         cls="inline-flex items-center rounded-full bg-white/70 py-1 pl-1 pr-3 text-xs font-semibold "
                             "ring-1 ring-stone-900/10 backdrop-blur"),
                    cls="reveal"),
                H1(Span("Online orders for", cls="block"), Span("your ", cls=""),
                   Span(words[0], id="rot", data_words=json.dumps(words), cls="grad-text"),
                   Span("Zero commission.", cls="block whitespace-nowrap text-stone-400"),
                   cls="reveal font-display mt-6 text-[2.6rem] sm:text-6xl lg:text-[4.1rem] font-bold leading-[1] [--d:80ms]"),
                P("A branded ordering link for your Facebook, Instagram and Messenger. Customers order and pay "
                  "with GCash, you run the kitchen from your phone, and you keep every peso of every sale.",
                  cls="reveal mt-6 max-w-lg text-lg text-stone-600 text-pretty [--d:160ms]"),
                Div(_ctas(contact, secondary=("See how it works", "#day")), cls="reveal mt-8 [--d:240ms]"),
                Div(*[Div(P(n, cls="font-display text-2xl font-bold"), P(l, cls="text-xs text-stone-500"))
                      for n, l in (("0%", "commission"), ("No app", "for customers"), ("Pay once", "no monthly fees"))],
                    cls="reveal mt-10 flex gap-8 [--d:320ms]"),
                cls="relative z-10 flex-[1.3]"),
            Div(Div(_phone(), cls="reveal [--d:200ms]"),
                _float_chip("bg-green-500", "New order #1043", "Pickup · 12:30 PM · ₱330", "-left-16 top-20"),
                _float_chip("bg-sky-500", "GCash proof received", "Tap to verify", "-right-10 top-1/2 [animation-delay:-2s]"),
                _float_chip("bg-stone-900", "Ensaymada → Sold out", "86'd by kitchen", "-left-14 bottom-36 [animation-delay:-4s]"),
                id="hero-stage", cls="relative flex flex-1 justify-center [perspective:1200px] py-6"),
            cls="relative mx-auto flex max-w-6xl flex-col lg:flex-row items-center gap-16 px-5 pt-36 pb-24 sm:pt-40"),
        id="top", cls="relative")


def _marquee():
    kinds = ["Restaurants", "Cafés", "Milk tea shops", "Bakeries", "Food trays", "Cloud kitchens",
             "Carinderias", "Party orders", "Coffee carts", "Home bakers"]
    row = [Span(Span(k, cls="font-display text-2xl sm:text-3xl font-bold"),
                Span("✦", cls="mx-8 text-orange-500"), cls="flex shrink-0 items-center") for k in kinds]
    return Section(
        Div(Div(*row, *row, cls="marquee flex w-max"), cls="marquee-wrap overflow-hidden"),
        aria_label="Built for", cls="border-y border-stone-900/10 bg-white/60 py-6 [mask-image:linear-gradient(90deg,transparent,#000_10%,#000_90%,transparent)]")


def _calculator():
    presets = [("₱50k", 50000), ("₱150k", 150000), ("₱500k", 500000), ("₱1M", 1000000)]
    return Section(
        Div(
            Div(_head("Keep your margin", "How much is commission really costing you?",
                      "Marketplace apps take a cut of every order. On ServeFlow the whole order is yours. "
                      "Enter your own numbers below."),
                cls="flex-1"),
            _card(
                Label(Span("Monthly online sales", cls="text-sm font-semibold"),
                      Div(Span("₱", cls="font-display text-3xl font-bold text-stone-400"),
                          Input(id="calc-sales", type="number", min="0", step="1000", value="150000", inputmode="numeric",
                                aria_label="Monthly online sales in pesos",
                                cls="w-full bg-transparent font-display text-4xl font-bold outline-none tabular-nums"),
                          cls="mt-2 flex items-center gap-1 border-b-2 border-stone-200 pb-2 focus-within:border-orange-600 transition-colors"),
                      cls="block"),
                Div(*[Button(t, type="button", data_preset=str(v),
                             cls="preset rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-stone-200 hover:ring-stone-400 transition")
                      for t, v in presets], cls="mt-3 flex flex-wrap gap-1.5"),
                Label(Div(Span("Commission rate you pay today", cls="text-sm font-semibold"),
                          Span("25%", id="calc-rate-out", cls="font-display text-xl font-bold text-orange-600 tabular-nums"),
                          cls="flex items-end justify-between"),
                      Input(id="calc-rate", type="range", min="0", max="40", step="1", value="25",
                            cls="range mt-3 w-full"),
                      cls="mt-7 block"),
                Div(P("Where each month's sales go", cls="text-xs font-semibold text-stone-500"),
                    Div(P("Marketplace", cls="w-24 shrink-0 text-xs font-semibold"),
                        Div(Div(id="bar-keep", cls="h-full rounded-l-full bg-stone-800 transition-[width] duration-500", style="width:75%"),
                            Div(id="bar-fee", cls="h-full rounded-r-full bg-gradient-to-r from-orange-500 to-rose-500 transition-[width] duration-500", style="width:25%"),
                            cls="flex h-3 flex-1 overflow-hidden rounded-full"),
                        cls="mt-3 flex items-center gap-3"),
                    Div(P("ServeFlow", cls="w-24 shrink-0 text-xs font-semibold"),
                        Div(cls="h-3 flex-1 rounded-full bg-stone-800"),
                        cls="mt-2 flex items-center gap-3"),
                    Div(Span(Span(cls="inline-block size-2 rounded-full bg-stone-800 mr-1.5"), "You keep"),
                        Span(Span(cls="inline-block size-2 rounded-full bg-orange-500 mr-1.5"), "Commission"),
                        cls="mt-3 flex gap-4 text-[11px] text-stone-500"),
                    cls="mt-7"),
                Div(Div(P("Lost to commission per year", cls="text-xs font-semibold text-orange-200"),
                        P("₱450,000", id="calc-year", cls="font-display mt-1 text-4xl sm:text-5xl font-bold tabular-nums"),
                        P(Span("₱37,500", id="calc-month", cls="tabular-nums font-semibold text-white"), " every month",
                          cls="mt-1 text-sm text-orange-200")),
                    Div(P("On ServeFlow", cls="text-xs font-semibold text-orange-200"),
                        P("₱0", cls="font-display mt-1 text-4xl sm:text-5xl font-bold"), cls="text-right"),
                    cls="mt-7 flex items-end justify-between gap-4 rounded-2xl bg-gradient-to-br from-stone-900 to-stone-800 p-5 text-white"),
                cls="reveal flex-1 w-full p-6 sm:p-8"),
            cls="mx-auto flex max-w-6xl flex-col lg:flex-row items-center gap-14 px-5 py-28"))


def _features(base):
    brands = [("#c2410c", "Kapé at Kain", "kapeatkain"), ("#047857", "Matcha Lab", "matchalab"),
              ("#7c3aed", "Ube Haus", "ubehaus"), ("#0f172a", "Kusina 88", "kusina88"),
              ("#db2777", "Sweet Tray Co.", "sweettray")]
    hours = [8, 14, 22, 30, 52, 96, 88, 46, 30, 34, 58, 72, 64, 28]
    peak = hours.index(max(hours))

    eighty_six = _card(
        H3("1-tap “86” & daily portions", cls="font-display text-xl font-bold"),
        P("Set how many you prepped. The menu counts down live, and the item sells out by itself at zero.",
          cls="mt-2 text-sm text-stone-600"),
        Div(Div(Div(P("Ensaymada", cls="font-semibold"),
                    P("12 left today", id="p-status", cls="text-xs font-semibold text-green-700")),
                Button(Span(cls="knob"), type="button", role="switch", aria_checked="true", id="p-switch",
                       aria_label="Available", cls="switch"),
                cls="flex items-center justify-between"),
            Div(Button("−", type="button", id="p-dec", aria_label="One less portion",
                       cls="grid size-9 place-items-center rounded-full bg-stone-100 text-lg font-bold hover:bg-stone-200"),
                Span("12", id="p-count", cls="font-display text-3xl font-bold tabular-nums"),
                Button("+", type="button", id="p-inc", aria_label="One more portion",
                       cls="grid size-9 place-items-center rounded-full bg-stone-100 text-lg font-bold hover:bg-stone-200"),
                cls="mt-4 flex items-center justify-between rounded-xl bg-stone-50 p-2"),
            cls="relative z-10 mt-5 rounded-2xl bg-white p-4 ring-1 ring-stone-200"),
        P("What customers see", cls="relative z-10 mt-5 text-[11px] font-semibold uppercase tracking-wider text-stone-400"),
        Div(Div(cls="size-11 shrink-0 rounded-lg bg-gradient-to-br from-amber-100 to-orange-100"),
            Div(P("Ensaymada", cls="text-sm font-semibold"), P("₱75", cls="text-xs font-bold"), cls="flex-1"),
            Span("12 left", id="p-preview", cls="rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-bold text-orange-700"),
            id="p-row", cls="relative z-10 mt-2 flex items-center gap-3 rounded-2xl bg-white p-2.5 ring-1 ring-stone-200 transition"),
        cls="reveal p-7 [--d:80ms]")

    payments = _card(
        H3("GCash & bank payments", cls="font-display text-xl font-bold"),
        P("Customers pay you directly and upload a proof of payment. You check it and confirm with one tap.",
          cls="mt-2 text-sm text-stone-600"),
        Div(Div(Div("G", cls="grid size-10 place-items-center rounded-xl bg-sky-600 text-white font-bold"),
                Div(P("#1042 · ₱330", cls="text-sm font-bold"), P("GCash · proof.jpg", cls="text-xs text-stone-500"),
                    cls="flex-1"),
                Button("Verify", type="button", id="pay-btn",
                       cls="rounded-full bg-stone-950 px-3.5 py-1.5 text-xs font-semibold text-white transition"),
                cls="flex items-center gap-3"),
            cls="relative z-10 mt-5 rounded-2xl bg-white p-3.5 ring-1 ring-stone-200"),
        P("COD and pay-at-counter work too.", cls="relative z-10 mt-3 text-xs text-stone-500"),
        cls="reveal p-7")

    modes = _card(
        H3("Dine-in, pickup, delivery", cls="font-display text-xl font-bold"),
        P("Delivery zones with fees, prep times and kitchen hours. Customers order ASAP or pick a time slot.",
          cls="mt-2 text-sm text-stone-600"),
        Div(*[Button(m, type="button", data_mode=m, aria_pressed="true" if i == 2 else "false",
                     cls="seg rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ring-stone-200 transition")
              for i, m in enumerate(["Dine-in", "Pickup", "Delivery", "COD"])],
            cls="relative z-10 mt-5 flex flex-wrap gap-1.5"),
        Div(*[Button(m, type="button", data_slot=m, aria_pressed="true" if i == 0 else "false",
                     cls="seg rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ring-stone-200 transition")
              for i, m in enumerate(["ASAP · ~20 min", "12:30 PM", "1:00 PM"])],
            cls="relative z-10 mt-2 flex flex-wrap gap-1.5"),
        P("Delivery · Zone 1 · +₱49", id="mode-out", cls="relative z-10 mt-4 text-xs font-semibold text-orange-700"),
        cls="reveal p-7 [--d:80ms]")

    steps = ["Preparing", "Ready", "Out for delivery", "Completed"]
    tracking = _card(
        H3("Private order tracking", cls="font-display text-xl font-bold"),
        P("Every order gets its own tracking link, so customers stop messaging “ready na po?”",
          cls="mt-2 text-sm text-stone-600"),
        Div(Div(Div(id="trk-bar", cls="h-full w-1/4 rounded-full bg-gradient-to-r from-orange-500 to-rose-500 transition-[width] duration-700"),
                cls="h-2 rounded-full bg-stone-100"),
            Div(*[Span(s, data_trk=str(i), cls="trk text-[10px] font-semibold text-stone-400 transition-colors")
                  for i, s in enumerate(steps)], cls="mt-2 flex justify-between"),
            P("Order #1043 is ", Span("Preparing", id="trk-now", cls="font-bold text-stone-950"),
              cls="mt-4 text-sm text-stone-600"),
            cls="relative z-10 mt-5 rounded-2xl bg-white p-4 ring-1 ring-stone-200"),
        cls="reveal p-7 [--d:160ms]")

    insights = _card(
        Div(Div(H3("Customers & sales insights", cls="font-display text-2xl font-bold"),
                P("Your best sellers, your busiest hours and your repeat customers. The customer list belongs "
                  "to you, not to a platform.", cls="mt-2 max-w-sm text-stone-600")),
            _pill("Sample data", "bg-stone-100 text-stone-500 self-start"),
            cls="relative z-10 flex justify-between gap-4"),
        Div(Div(*[Div(Div(cls=f"bar-grow w-full rounded-t-md {'bg-gradient-to-t from-orange-600 to-rose-400' if i == peak else 'bg-stone-200'}",
                          style=f"height:{h}%; transition-delay:{i * 40}ms"),
                      Span(f"{(7 + i) % 12 or 12}", cls="mt-1.5 text-[10px] text-stone-400"),
                      cls="flex h-full flex-1 flex-col items-center justify-end")
                  for i, h in enumerate(hours)],
                cls="flex h-36 items-end gap-1.5"),
            P("Busiest hour: 12 NN · 7 AM to 8 PM", cls="mt-2 text-xs font-semibold text-stone-500"),
            cls="reveal relative z-10 mt-6"),
        cls="reveal p-7 lg:col-span-2")

    isolated = _card(
        Div(H3("Your data stays yours", cls="font-display text-xl font-bold"),
            P("Every store runs on its own separate database. Your orders and customers are never mixed with another shop's.",
              cls="mt-2 max-w-md text-sm text-stone-600"),
            cls="relative z-10"),
        Div(*[Div(Span(cls="size-2 rounded-full bg-green-500"), Span(f"{s}.db", cls="font-mono text-[11px]"),
                  cls="flex items-center gap-2 rounded-lg bg-stone-50 px-3 py-2 ring-1 ring-stone-200")
              for _, _, s in brands], cls="relative z-10 mt-5 flex flex-wrap gap-1.5 lg:mt-0 lg:max-w-md lg:justify-end"),
        cls="reveal p-7 lg:col-span-3 lg:flex lg:items-center lg:justify-between lg:gap-8")

    return Section(
        Div(_head("Everything you need", "Run online orders without the chaos",
                  "No more scrolling Messenger threads to find an order. Go ahead and tap the cards below."),
            Div(eighty_six, payments, modes, insights, tracking, isolated,
                cls="mt-14 grid gap-4 lg:grid-cols-3"),
            cls="mx-auto max-w-6xl px-5 py-28"),
        id="features")


CHAT = [
    {"q": "Something not spicy for 2, under ₱400?",
     "a": "Two Chicken Adobo Bowls come to ₱370 (₱185 each). There are 6 portions left today, and "
          "12:30 pickup is open. Want me to set that up?",
     "cart": ["2 × Chicken Adobo Bowl", "Pickup · 12:30 PM · ₱370"]},
    {"q": "May oat milk ba kayo?",
     "a": "Yes! Oat milk is +₱30 on any latte. An iced 16oz Ube Spanish Latte with oat milk "
          "comes to ₱195.",
     "cart": ["1 × Ube Spanish Latte", "Iced 16oz · Oat milk · ₱195"]},
    {"q": "Do you deliver to Poblacion?",
     "a": "Yes. Poblacion is in Zone 1: ₱49 delivery and about 35 minutes. The kitchen is open until 9 PM "
          "tonight. Your order can go out ASAP.",
     "cart": None},
    {"q": "Anything with peanuts?",
     "a": "None of today's items list peanuts as an allergen. The Banana Bread has walnuts, so skip that one "
          "if you avoid tree nuts.",
     "cart": None},
]


def _ai():
    return Section(
        Div(cls="pointer-events-none absolute left-1/2 top-0 h-[500px] w-[900px] -translate-x-1/2 rounded-full "
                "bg-orange-600/25 blur-[120px]"),
        Div(cls="grain pointer-events-none absolute inset-0 opacity-[.08]"),
        Div(
            Div(_head("AI that knows your kitchen", "A menu concierge that never makes things up",
                      "Customers ask in English or Taglish. The concierge answers only from your live menu: "
                      "prices, add-ons, portions left, allergens, delivery zones and hours.", dark=True),
                Ul(*[Li(Span("✓", cls="grid size-5 shrink-0 place-items-center rounded-full bg-orange-500 text-[11px] font-bold text-white"),
                        Span(t), cls="flex gap-3 text-stone-300")
                     for t in ("Recommends only items that are actually available",
                               "Builds the cart. The customer confirms before anything is added",
                               "Works without AI too: if it's switched off, the store runs normally")],
                   cls="reveal mt-8 space-y-3 [--d:120ms]"),
                cls="flex-1"),
            Div(
                Div(Div(Span("✦", cls="text-orange-400"), Span("Menu Concierge", cls="font-semibold"),
                        _pill("Example", "bg-white/10 text-stone-300 ml-auto"),
                        cls="flex items-center gap-2 text-sm"),
                    Div(id="chat-log", aria_live="polite", cls="no-scrollbar mt-4 h-[300px] space-y-3 overflow-y-auto"),
                    Div(P("Try asking:", cls="w-full text-[11px] font-semibold text-stone-500"),
                        *[Button(c["q"], type="button", data_q=str(i),
                                 cls="chip rounded-full bg-white/[.06] px-3 py-1.5 text-left text-xs font-medium text-stone-200 "
                                     "ring-1 ring-white/10 hover:bg-white/10 transition")
                          for i, c in enumerate(CHAT)],
                        cls="mt-4 flex flex-wrap gap-1.5 border-t border-white/10 pt-4"),
                    cls="rounded-[1.75rem] bg-stone-900/80 p-5 ring-1 ring-white/10 shadow-2xl backdrop-blur"),
                id="ai-panel", cls="reveal flex-1 w-full max-w-lg [--d:150ms]"),
            cls="relative mx-auto flex max-w-6xl flex-col lg:flex-row items-center gap-14 px-5 py-28"),
        id="ai", cls="dark-sec relative overflow-hidden bg-stone-950 text-white")


COPILOT = [
    {"cmd": "86 the sisig", "title": "Mark Sisig Rice as sold out",
     "detail": "Hides the “+” button on the storefront until you turn it back on.",
     "done": "Done. Sisig Rice is now sold out."},
    {"cmd": "Reset ensaymada to 24", "title": "Set Ensaymada portions to 24",
     "detail": "Today's count goes from 0 to 24 and the item is available again.",
     "done": "Done. Ensaymada is back with 24 portions."},
    {"cmd": "Close delivery for today", "title": "Turn off delivery until tomorrow",
     "detail": "Pickup and dine-in stay open. Delivery orders already placed are not affected.",
     "done": "Done. Delivery is off until 7 AM tomorrow."},
]


def _kitchen():
    cols = [("prep", "Preparing", "bg-amber-400"), ("ready", "Ready", "bg-green-500"), ("out", "Out for delivery", "bg-sky-500")]
    return Section(
        Div(_head("Owner & kitchen admin", "One screen for the whole lunch rush",
                  "Move tickets along, verify payments and 86 items from a phone or a tablet on the counter. "
                  "Click the arrows to move an order."),
            Div(
                _card(
                    Div(P("Kitchen queue", cls="font-semibold"),
                        P(Span("0", id="k-done", cls="font-bold text-stone-950 tabular-nums"), " completed",
                          cls="text-xs text-stone-500"),
                        cls="relative z-10 flex items-center justify-between"),
                    Div(*[Div(Div(Span(cls=f"size-2 rounded-full {dot}"), Span(t, cls="text-xs font-bold"),
                                  Span("0", data_count=k, cls="ml-auto rounded-full bg-white px-1.5 text-[10px] font-bold ring-1 ring-stone-200"),
                                  cls="flex items-center gap-1.5"),
                              Div(data_col=k, cls="mt-2 min-h-[220px] space-y-2"),
                              cls="min-w-0 flex-1 rounded-2xl bg-stone-100/80 p-2.5")
                          for k, t, dot in cols],
                        cls="relative z-10 mt-4 flex gap-2"),
                    cls="reveal p-4 sm:p-5 lg:col-span-3"),
                _card(
                    Div(Span("✦", cls="text-orange-600"), P("Kitchen Co-pilot", cls="font-semibold"),
                        cls="relative z-10 flex items-center gap-2"),
                    P("Tell it what you need. Nothing changes until you tap Confirm.",
                      cls="relative z-10 mt-1 text-xs text-stone-500"),
                    Div(*[Button(f"“{c['cmd']}”", type="button", data_cp=str(i),
                                 cls="chip-l rounded-full bg-stone-100 px-3 py-1.5 text-xs font-semibold hover:bg-stone-200 transition")
                          for i, c in enumerate(COPILOT)],
                        cls="relative z-10 mt-4 flex flex-wrap gap-1.5"),
                    Div(P("Pick a command above.", cls="text-sm text-stone-400"),
                        id="cp-out", aria_live="polite",
                        cls="relative z-10 mt-4 grid min-h-[150px] place-items-center rounded-2xl border border-dashed border-stone-300 p-4"),
                    cls="reveal p-5 lg:col-span-2 [--d:100ms]"),
                cls="mt-14 grid gap-4 lg:grid-cols-5"),
            cls="mx-auto max-w-6xl px-5 py-28"),
        id="kitchen")


def _steps():
    steps = [("Create your store", "Pick a name, what you sell and a color. Your store and your owner dashboard are ready in a minute."),
             ("Make it yours", "Edit the sample menu, add photos, GCash or bank details and kitchen hours from your dashboard."),
             ("Go live & share", "Settle the one-time setup fee and we switch your store on. Share the link on Facebook, Instagram and Messenger.")]
    return Section(
        Div(_head("Go live fast", "From sign-up to first order in three steps", center=True),
            Div(Div(cls="absolute left-[16%] right-[16%] top-7 hidden h-px border-t-2 border-dashed border-stone-300 md:block"),
                *[Div(Div(str(i + 1), cls="font-display relative z-10 mx-auto grid size-14 place-items-center rounded-full "
                                         "bg-gradient-to-br from-orange-500 to-rose-500 text-xl font-bold text-white "
                                         "shadow-lg shadow-orange-600/30 ring-8 ring-[#faf7f2]"),
                      H3(t, cls="font-display mt-5 text-xl font-bold"),
                      P(d, cls="mx-auto mt-2 max-w-xs text-stone-600"),
                      cls=f"reveal text-center [--d:{i * 120}ms]")
                  for i, (t, d) in enumerate(steps)],
                cls="relative mt-16 grid gap-12 md:grid-cols-3"),
            cls="mx-auto max-w-6xl px-5 py-28"))


def _pricing(contact, demo):
    inc = ["Your own store, link & owner dashboard", "Help setting up your menu & payments",
           "No monthly subscription", "Unlimited orders, 0% commission", "GCash, bank, COD & counter payments",
           "Kitchen queue, 86 toggles & daily portions", "AI Menu Concierge & Kitchen Co-pilot",
           "Customer list & sales insights"]
    return Section(
        Div(Div(_head("Simple pricing", "Pay once. Keep every sale after that.",
                      "Create your store and build it for free. When you're ready for customers, a one-time "
                      "setup fee switches it on. No monthly subscription and no cut of your orders after that."),
                cls="flex-1"),
            Div(Div(
                Div(P("ServeFlow Store", cls="font-semibold"), _pill("One-time setup", "bg-orange-100 text-orange-800"),
                    cls="flex items-center justify-between"),
                P("Pay once", cls="font-display mt-4 text-6xl font-bold"),
                P("₱0 monthly · 0% commission", cls="mt-2 font-semibold text-orange-700"),
                P("Build for free · one-time setup fee to go live", cls="mt-1 text-sm text-stone-500"),
                Ul(*[Li(Span("✓", cls="grid size-5 shrink-0 place-items-center rounded-full bg-orange-100 text-[11px] font-bold text-orange-700"),
                        Span(t), cls="flex items-center gap-3 text-[15px]") for t in inc],
                   cls="mt-7 space-y-3"),
                Div(_ctas(contact, demo), cls="mt-8"),
                cls="rounded-[calc(2rem-2px)] bg-white p-8"),
                cls="reveal glow flex-1 w-full max-w-md rounded-[2rem] bg-gradient-to-br from-orange-500 via-amber-400 to-rose-500 p-[2px] [--d:120ms]"),
            cls="mx-auto flex max-w-6xl flex-col lg:flex-row items-center gap-14 px-5 py-28"),
        id="pricing")


FAQ = [
    ("Can I set up my store before paying?",
     "Yes. Create your store and you'll land in your own owner dashboard with a sample menu for what you sell. "
     "Edit everything and preview it. Customers see a “coming soon” page until you settle the one-time setup "
     "fee and we switch it on."),
    ("Do my customers need to download an app?",
     "No. Your store is a website that opens in any phone browser, including inside Facebook and Messenger."),
    ("How do I get paid?",
     "Directly. Customers send GCash or bank transfers to your own accounts and upload a proof of payment, "
     "which you confirm in the admin. Cash on delivery and pay-at-counter also work. ServeFlow never holds your money."),
    ("Do you take a percentage of my sales?",
     "No. ServeFlow charges 0% commission and no monthly subscription. You pay a one-time setup fee, "
     "and every order after that is yours, however many you get."),
    ("Can I handle delivery myself?",
     "Yes. You set delivery zones and fees and use your own riders or a courier you book. Customers can also "
     "choose pickup or dine-in."),
    ("What if an item runs out mid-service?",
     "Tap “86” and it's marked sold out right away. You can also set daily prep portions, and the menu shows "
     "how many are left until they're gone."),
    ("Is the AI required?",
     "No. The store works fully without it. When it's on, it answers only from your live menu data and never "
     "places or changes anything without a confirmation tap."),
]


def _faq():
    return Section(
        Div(_head("FAQ", "Questions owners ask us", center=True),
            Div(*[Details(Summary(Span(q, cls="font-semibold text-lg"),
                                  Span("+", cls="faq-plus grid size-8 shrink-0 place-items-center rounded-full bg-stone-100 text-lg transition"),
                                  cls="flex cursor-pointer list-none items-center justify-between gap-4 p-5"),
                          P(a, cls="faq-body px-5 pb-5 -mt-1 text-stone-600 leading-relaxed"),
                          cls="reveal rounded-2xl bg-white ring-1 ring-stone-900/[.07] open:shadow-lg open:shadow-stone-900/5 transition-shadow")
                  for q, a in FAQ],
                cls="mt-12 space-y-2"),
            cls="mx-auto max-w-3xl px-5 py-28"),
        id="faq")


def _final_cta(contact, demo):
    return Section(
        Div(Div(cls="pointer-events-none absolute -left-20 -top-24 size-[420px] rounded-full bg-orange-600/50 blur-[100px]"),
            Div(cls="pointer-events-none absolute -bottom-32 -right-10 size-[420px] rounded-full bg-rose-600/40 blur-[100px]"),
            Div(cls="grain pointer-events-none absolute inset-0 opacity-[.1]"),
            Div(H2("Stop paying commission on your own customers.",
                   cls="font-display text-4xl sm:text-6xl font-bold leading-[1.02] text-balance"),
                P("Create your store in a minute. Go live this week.", cls="mt-5 text-lg text-stone-400"),
                Div(_ctas(contact, demo, dark=True, center=True), cls="mt-9"),
                cls="relative z-10"),
            cls="reveal relative mx-auto max-w-5xl overflow-hidden rounded-[2.5rem] bg-stone-950 px-6 py-20 text-center text-white sm:py-28"),
        cls="px-4 pb-16")


def _footer(local_stores, base):
    dev = None
    if local_stores:
        dev = Div(P("Local dev · stores in data/", cls="text-xs font-semibold text-stone-500"),
                  Div(*[A(f"{s}.localhost", href=_store_url(s, base), cls="text-sm font-semibold text-orange-700 underline")
                        for s in local_stores], cls="mt-1 flex flex-wrap gap-3"),
                  cls="mt-6 rounded-xl border border-dashed border-stone-300 p-3")
    return Footer(
        Div(Div(A(Span(cls="size-2.5 rounded-full bg-gradient-to-br from-orange-500 to-rose-500"),
                  Span("ServeFlow", cls="font-display text-lg font-bold"), href="#top", cls="flex items-center gap-2"),
                P("White-label online ordering for Philippine food businesses.", cls="text-sm text-stone-500"),
                cls="flex flex-col sm:flex-row sm:items-center justify-between gap-2"),
            dev,
            cls="mx-auto max-w-6xl px-5 py-10"),
        cls="border-t border-stone-900/10")


# ---------------------------------------------------------------- store preview builder

STARTERS = json.loads((Path(__file__).parent / "seeds" / "starters.json").read_text(encoding="utf-8"))
# what the signup preview shows = the first category of the starter menu the store will really get
TYPES = {k: {"tag": v["tagline"], "cat": v["categories"][0]["name"],
             "items": [[i["name"], i.get("description", ""), i["price"]] for i in v["categories"][0]["items"][:3]]}
         for k, v in STARTERS.items()}
COLORS = ["#c2410c", "#047857", "#7c3aed", "#0f172a", "#db2777", "#0369a1"]


def _field(label, *c, hint=None, cls=""):
    return Label(Span(label, cls="text-sm font-semibold"), *c,
                 P(hint, cls="mt-1 text-xs text-stone-500") if hint else None, cls=f"relative z-10 block {cls}")


INPUT = ("mt-2 w-full rounded-2xl bg-stone-50 px-4 py-3 text-[15px] ring-1 ring-stone-200 outline-none "
         "focus:bg-white focus:ring-2 focus:ring-orange-600 transition")


def _preview(base):
    dom = "yourdomain.com" if base == "localhost" else base
    first = next(iter(TYPES))
    form = Form(
        _field("Store name", Input(id="cfg-name", name="name", required=True, minlength="2", maxlength="60",
                                   autocomplete="organization", placeholder="e.g. Kapé at Kain",
                                   cls=INPUT.replace("text-[15px]", "font-display text-2xl font-bold"))),
        P("What do you sell?", cls="relative z-10 mt-5 text-sm font-semibold"),
        Div(*[Button(t, type="button", data_type=t, aria_pressed="true" if i == 0 else "false",
                     cls="seg rounded-full px-3.5 py-2 text-sm font-semibold ring-1 ring-stone-200 transition")
              for i, t in enumerate(TYPES)],
            cls="relative z-10 mt-2 flex flex-wrap gap-1.5"),
        P("We'll start you with a sample menu for this. You can edit or delete any of it.",
          cls="relative z-10 mt-1.5 text-xs text-stone-500"),
        P("Brand color", cls="relative z-10 mt-5 text-sm font-semibold"),
        Div(*[Button(type="button", data_color=c, aria_label=f"Color {c}", aria_pressed="true" if i == 0 else "false",
                     style=f"background:{c}",
                     cls="swatch size-9 rounded-full ring-2 ring-offset-2 ring-transparent transition hover:scale-110")
              for i, c in enumerate(COLORS)],
            cls="relative z-10 mt-2 flex flex-wrap gap-2.5"),
        _field("Your store link",
               Div(Input(id="cfg-slug", name="slug", required=True, minlength="3", maxlength="30", pattern="[a-z0-9-]+",
                         autocomplete="off", autocapitalize="none", spellcheck="false", placeholder="yourstore",
                         cls="min-w-0 flex-1 bg-transparent py-3 pl-4 text-[15px] font-semibold outline-none"),
                   Span(f".{dom}", cls="shrink-0 pr-4 text-sm text-stone-500"),
                   cls="mt-2 flex items-center rounded-2xl bg-stone-50 ring-1 ring-stone-200 focus-within:bg-white "
                       "focus-within:ring-2 focus-within:ring-orange-600 transition"),
               Span("", id="slug-status", aria_live="polite", cls="mt-1 block min-h-4 text-xs font-semibold"),
               cls="mt-5"),
        Div(_field("Mobile number", Input(name="mobile", type="tel", required=True, inputmode="tel", autocomplete="tel",
                                          placeholder="0917 123 4567", cls=INPUT),
                   hint="So we can help you go live."),
            _field("Owner password", Input(name="password", type="password", required=True, minlength="8",
                                           autocomplete="new-password", placeholder="At least 8 characters", cls=INPUT),
                   hint="For your owner dashboard."),
            cls="mt-3 grid gap-4 sm:grid-cols-2"),
        Input(type="hidden", name="kind", id="cfg-kind", value=first),
        Input(type="hidden", name="color", id="cfg-color", value=COLORS[0]),
        Div(Label("Company", Input(name="company", tabindex="-1", autocomplete="off")),
            aria_hidden="true", cls="absolute -left-[9999px] h-px w-px overflow-hidden"),
        Div(id="signup-error", cls="relative z-10 mt-5 empty:hidden"),
        Button(Span("Create my store", cls="btn-label"), Span("→", cls="btn-label"),
               Span("Creating your store…", cls="btn-busy hidden"),
               type="submit", id="signup-btn",
               cls="relative z-10 mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-orange-600 px-6 "
                   "py-4 text-base font-semibold text-white shadow-lg shadow-orange-700/25 transition hover:bg-orange-700 "
                   "disabled:opacity-70"),
        P("Free to set up. Customers see your store once it's live.",
          cls="relative z-10 mt-3 text-center text-xs text-stone-500"),
        id="signup-form", method="post", action="/signup", novalidate=False)
    return Section(
        Div(_head("Create your store", "Your store and owner dashboard in one minute",
                  "Fill this in and you'll land in your own dashboard with a sample menu, ready to make "
                  "it yours. The preview updates as you type.", center=True),
            Div(
                _card(form, cls="reveal p-6 sm:p-8"),
                Div(
                    Div(Div(
                        Div(Div(Div("YS", cls="pv-init pv-bg grid size-11 place-items-center rounded-full text-sm font-bold text-white ring-4 ring-white"),
                                cls="absolute -bottom-5 left-4"),
                            cls="pv-bg relative h-20 rounded-2xl transition-colors duration-500"),
                        P("Your Store", cls="pv-name font-display mt-7 truncate px-1 text-xl font-bold"),
                        P(TYPES[next(iter(TYPES))]["tag"], cls="pv-tag truncate px-1 text-[11px] text-stone-500"),
                        P(TYPES[next(iter(TYPES))]["cat"], cls="pv-cat mt-4 px-1 text-xs font-bold uppercase tracking-wider text-stone-400"),
                        Div(id="pv-items", cls="mt-2 space-y-2"),
                        Div(Span("Tap + to add", id="pv-count", cls="font-semibold"), Span("₱0", id="pv-total", cls="font-bold tabular-nums"),
                            id="pv-bar", cls="pv-bg mt-3 flex items-center justify-between rounded-full px-4 py-2.5 text-[13px] text-white transition-colors duration-500"),
                        cls="rounded-[2rem] bg-[#faf7f2] p-3.5"),
                        cls="w-[300px] shrink-0 rounded-[2.6rem] bg-stone-950 p-2.5 shadow-[0_40px_80px_-30px_rgba(28,25,23,.5)]"),
                    Div(P("When you share it on Messenger", cls="text-[11px] font-semibold uppercase tracking-wider text-stone-400"),
                        Div(Div(cls="pv-bg h-24 transition-colors duration-500",
                                style="background-image:radial-gradient(circle at 30% 20%,rgba(255,255,255,.35),transparent 50%)"),
                            Div(P(Span("yourstore", cls="pv-slug"), f".{dom}", cls="truncate text-[10px] uppercase text-stone-500"),
                                P(Span("Order online from ", cls=""), Span("Your Store", cls="pv-name"),
                                  cls="mt-0.5 truncate text-sm font-semibold"),
                                P("Pickup, delivery & dine-in · Pay with GCash", cls="truncate text-xs text-stone-500"),
                                cls="bg-stone-100 px-3 py-2.5"),
                            cls="mt-2 w-64 overflow-hidden rounded-2xl ring-1 ring-stone-200"),
                        Div(P("Hi! Pa-order po 🙂", cls="rounded-2xl rounded-br-md bg-[#0084ff] px-3 py-2 text-sm text-white"),
                            cls="mt-2 flex w-64 justify-end"),
                        cls="hidden xl:block"),
                    cls="reveal flex items-center justify-center gap-8 lg:sticky lg:top-28 [--d:120ms]"),
                cls="mt-14 grid items-start gap-10 lg:grid-cols-2"),
            cls="mx-auto max-w-6xl px-5 py-28"),
        id="start")


# ---------------------------------------------------------------- scroll-lit statement

MANIFESTO = ("Marketplace apps list you next to your competitors and take a cut of every order. "
             "ServeFlow gives you *your *own *link, *your *own *brand, *your *own *customers, "
             "and *every *peso *of *every *sale.")


def _manifesto():
    words = [Span(w.lstrip("*") + " ", cls="lw hl" if w.startswith("*") else "lw") for w in MANIFESTO.split()]
    return Section(
        Div(P(*words, id="manifesto",
              cls="font-display text-[2rem] sm:text-5xl lg:text-6xl font-bold leading-[1.1] text-balance"),
            cls="mx-auto max-w-5xl px-5 py-28"),
        aria_label="Why ServeFlow")


# ---------------------------------------------------------------- a day in the kitchen (scrollytelling)

STORY = [
    ("7:00 AM", "Set today's portions",
     "Enter how many you prepped. The menu shows what's left, and items sell out by themselves at zero."),
    ("11:48 AM", "The lunch rush hits",
     "Orders come in from your link: pickup, dine-in, delivery, ASAP or scheduled. No more digging through chat threads."),
    ("12:05 PM", "Verify GCash in one tap",
     "Customers upload their proof of payment. You check the amount and confirm it, and the order moves on."),
    ("1:30 PM", "Sold out? 86 it",
     "One tap hides an item from the menu right away. Customers never order something you don't have."),
    ("9:00 PM", "Close and see your day",
     "Orders, sales, best sellers and repeat customers, all yours. Commission paid: zero."),
]


def _story_panel(i):
    if i == 0:
        rows = [("Ensaymada", 24), ("Chicken Adobo Bowl", 30), ("Sisig Rice", 20), ("Ube Cheese Pandesal", 60)]
        body = Div(*[Div(Div(P(n, cls="text-sm font-semibold"), P(Span("0", data_to=str(v), cls="tick tabular-nums font-bold"),
                                                                  " portions", cls="text-xs text-stone-500"),
                             cls="flex items-center justify-between"),
                         Div(Div(cls="fill h-full rounded-full bg-gradient-to-r from-orange-500 to-amber-400",
                                 style=f"--w:{min(100, v * 2)}%; transition-delay:{k * 90}ms"),
                             cls="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-100"),
                         cls="pop rounded-xl bg-white p-3 ring-1 ring-stone-200", style=f"animation-delay:{k * 80}ms")
                     for k, (n, v) in enumerate(rows)], cls="space-y-2")
    elif i == 1:
        rows = [("#1051", "Pickup · 12:15 PM", "2 × Adobo Bowl", "₱370"), ("#1052", "Delivery · ASAP", "Brown Sugar Boba × 3", "₱390"),
                ("#1053", "Dine-in · Table 4", "Sisig Rice, Ube Latte", "₱340"), ("#1054", "Pickup · 12:30 PM", "6 × Ube Pandesal", "₱150")]
        body = Div(*[Div(Span(cls="size-2 shrink-0 rounded-full bg-green-500"),
                         Div(P(o, " ", Span(m, cls="font-normal text-stone-500"), cls="text-sm font-bold"),
                             P(it, cls="text-xs text-stone-500"), cls="min-w-0 flex-1"),
                         Div(P(amt, cls="text-sm font-bold"), _pill("NEW", "bg-orange-600 text-white"), cls="text-right"),
                         cls="pop flex items-center gap-3 rounded-xl bg-white p-3 ring-1 ring-stone-200",
                         style=f"animation-delay:{k * 260}ms")
                     for k, (o, m, it, amt) in enumerate(rows)], cls="space-y-2")
    elif i == 2:
        body = Div(
            Div(Div(P("GCash", cls="font-bold"), P("Sent", cls="text-xs opacity-80"), cls="flex items-center justify-between"),
                P("₱330.00", cls="font-display mt-6 text-4xl font-bold"),
                P("Ref No. 1029 384 1182", cls="mt-1 text-xs opacity-80"),
                cls="pop rounded-2xl bg-gradient-to-br from-sky-600 to-blue-700 p-5 text-white"),
            Div(Div(P("Order #1042 · ₱330", cls="text-sm font-bold"), P("Pickup · Juan D.", cls="text-xs text-stone-500")),
                Span("Verify", cls="verify rounded-full bg-stone-950 px-4 py-2 text-xs font-semibold text-white transition"),
                cls="pop mt-3 flex items-center justify-between rounded-xl bg-white p-3 ring-1 ring-stone-200",
                style="animation-delay:150ms"),
            cls="")
    elif i == 3:
        rows = [("Chicken Adobo Bowl", "18 left", True), ("Sisig Rice", "2 left", "auto"), ("Ensaymada", "Sold out", False)]
        body = Div(*[Div(Div(P(n, cls="text-sm font-semibold"),
                             P(st, cls=f"st text-xs font-semibold {'text-green-700' if on is True else 'text-orange-600' if on else 'text-stone-500'}")),
                         Span(Span(cls="knob"), role="presentation",
                              cls=f"switch {'auto-off' if on == 'auto' else ''}", aria_checked="true" if on else "false"),
                         cls=f"pop flex items-center justify-between rounded-xl bg-white p-3 ring-1 ring-stone-200 {'opacity-50' if on is False else ''}",
                         style=f"animation-delay:{k * 80}ms")
                     for k, (n, st, on) in enumerate(rows)], cls="space-y-2")
    else:
        stats = [("Orders", "64", None), ("Sales", "₱18,420", 18420), ("Avg. order", "₱288", None), ("Commission", "₱0", None)]
        body = Div(
            Div(*[Div(P(l, cls="text-xs text-stone-500"),
                      P(Span(v, data_peso=str(n) if n else None, cls="tabular-nums"),
                        cls=f"font-display mt-1 text-2xl font-bold {'text-green-700' if l == 'Commission' else ''}"),
                      cls="pop rounded-xl bg-white p-3 ring-1 ring-stone-200", style=f"animation-delay:{k * 80}ms")
                  for k, (l, v, n) in enumerate(stats)], cls="grid grid-cols-2 gap-2"),
            Div(P("Best seller today", cls="text-xs text-stone-500"), P("★ Ube Spanish Latte · 23 sold", cls="text-sm font-bold"),
                cls="pop mt-2 rounded-xl bg-amber-50 p-3 ring-1 ring-amber-200", style="animation-delay:320ms"),
            _pill("Sample day", "bg-stone-100 text-stone-500 mt-3"))
    return Div(body, data_story_panel=str(i), cls="story-panel")


def _device():
    return Div(
        Div(Div(Span(cls="size-2.5 rounded-full bg-orange-600"), P("Kapé at Kain · Admin", cls="text-sm font-semibold"),
                cls="flex items-center gap-2"),
            P(STORY[0][0], id="story-clock", cls="font-display text-sm font-bold tabular-nums"),
            cls="flex items-center justify-between border-b border-stone-200 px-5 py-3.5"),
        Div(*[_story_panel(i) for i in range(len(STORY))], cls="relative h-[360px] p-4"),
        cls="overflow-hidden rounded-[1.75rem] bg-[#faf7f2] ring-1 ring-stone-900/10 shadow-[0_40px_80px_-30px_rgba(28,25,23,.35)]")


def _day():
    return Section(
        Div(_head("A day with ServeFlow", "From the 7 AM prep to the 9 PM close",
                  "Scroll through a typical day in a busy café kitchen."),
            Div(
                Div(*[Div(Div(P(t, cls="story-time font-display text-5xl sm:text-6xl font-bold grad-text"),
                              H3(title, cls="font-display mt-3 text-2xl sm:text-3xl font-bold"),
                              P(body, cls="mt-3 max-w-md text-lg text-stone-600"),
                              Div(Div(_story_panel(i), cls="story-inline relative mt-6 rounded-[1.5rem] bg-[#faf7f2] p-4 ring-1 ring-stone-900/10"),
                                  cls="lg:hidden")),
                          data_story=str(i), data_time=t, id=f"day-{i + 1}",
                          cls="story-step py-10 lg:flex lg:min-h-[78vh] lg:items-center lg:py-0")
                      for i, (t, title, body) in enumerate(STORY)],
                    cls="flex-1"),
                Div(Div(_device(), Div(*[Span(data_dot=str(i), cls="sdot h-1.5 w-1.5 rounded-full bg-stone-300 transition-all")
                                         for i in range(len(STORY))], cls="mt-5 flex justify-center gap-1.5"),
                        cls="sticky top-[calc(50vh-210px)]"),
                    cls="hidden flex-1 lg:block"),
                cls="mt-6 flex gap-16"),
            cls="mx-auto max-w-6xl px-5 pt-28 pb-10"),
        id="day")


# ---------------------------------------------------------------- css + js

GRAIN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
         "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/>"
         "</filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")")

CSS = """
html{scroll-behavior:smooth} body{overflow-x:hidden}
.font-display{font-family:'Bricolage Grotesque',Inter,system-ui,sans-serif;letter-spacing:-.025em}
.grad-text{background:linear-gradient(100deg,#ea580c 0%,#f59e0b 45%,#e11d48 100%);-webkit-background-clip:text;background-clip:text;color:transparent;padding-bottom:.08em}
#rot{display:inline-block;transition:opacity .3s,transform .3s,filter .3s}
#rot.out{opacity:0;transform:translateY(-.3em);filter:blur(6px)}
.blob{position:absolute;border-radius:9999px;filter:blur(80px);opacity:.5;animation:drift 18s ease-in-out infinite alternate}
@keyframes drift{to{transform:translate(60px,-40px) scale(1.15)}}
.grid-bg{background-image:linear-gradient(rgba(28,25,23,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(28,25,23,.06) 1px,transparent 1px);background-size:56px 56px;mask-image:radial-gradient(ellipse 70% 60% at 50% 30%,#000 20%,transparent 75%)}
.grain{background-image:GRAIN}
.floaty{animation:floaty 6s ease-in-out infinite}
@keyframes floaty{50%{transform:translateY(-12px)}}
#phone{transition:transform .3s ease-out;transform-style:preserve-3d;will-change:transform}
.tab[aria-selected=true]{background:#ea580c;color:#fff;--tw-ring-color:transparent}
.bump{animation:bump .4s cubic-bezier(.3,1.6,.5,1)}
@keyframes bump{40%{transform:scale(1.05)}}
.phone-toast{opacity:0;transform:translateY(8px);transition:opacity .25s,transform .25s}
.phone-toast.show{opacity:1;transform:none}
#nav .nav-inner{transition:background .3s,box-shadow .3s,backdrop-filter .3s}
#nav.scrolled .nav-inner{background:rgba(255,255,255,.72);backdrop-filter:blur(14px) saturate(1.4);box-shadow:0 0 0 1px rgba(28,25,23,.07),0 12px 32px -12px rgba(28,25,23,.18)}
.marquee{animation:marquee 40s linear infinite}
.marquee-wrap:hover .marquee{animation-play-state:paused}
@keyframes marquee{to{transform:translateX(-50%)}}
.js .reveal{opacity:0;transform:translateY(28px);transition:opacity .8s cubic-bezier(.2,.7,.2,1),transform .8s cubic-bezier(.2,.7,.2,1);transition-delay:var(--d,0ms)}
.js .reveal.in{opacity:1;transform:none}
.spot::before{content:'';position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .3s;background:radial-gradient(500px circle at var(--x,50%) var(--y,50%),rgba(234,88,12,.09),transparent 40%)}
.spot:hover::before{opacity:1}
.dark-sec .spot::before{background:radial-gradient(500px circle at var(--x,50%) var(--y,50%),rgba(251,146,60,.12),transparent 40%)}
.preset[aria-pressed=true],.seg[aria-pressed=true]{background:#1c1917;color:#fff;--tw-ring-color:#1c1917}
.chip[aria-pressed=true]{background:#fff;color:#0c0a09}
.swatch[aria-pressed=true]{--tw-ring-color:#1c1917}
.range{-webkit-appearance:none;appearance:none;height:6px;border-radius:9999px;background:linear-gradient(90deg,#ea580c var(--p,62%),#e7e5e4 var(--p,62%))}
.range::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;border-radius:9999px;background:#fff;border:2px solid #ea580c;box-shadow:0 2px 8px rgba(0,0,0,.15);cursor:grab}
.range::-moz-range-thumb{width:20px;height:20px;border-radius:9999px;background:#fff;border:2px solid #ea580c;cursor:grab}
.switch{position:relative;width:46px;height:28px;border-radius:9999px;background:#d6d3d1;transition:background .25s;flex-shrink:0}
.switch .knob{position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:9999px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);transition:transform .25s cubic-bezier(.3,1.4,.5,1)}
.switch[aria-checked=true]{background:#16a34a}
.switch[aria-checked=true] .knob{transform:translateX(18px)}
.bar-grow{transform-origin:bottom;transform:scaleY(.04);transition:transform 1s cubic-bezier(.2,.7,.2,1)}
.reveal.in .bar-grow{transform:none}
.kcard{animation:kin .4s cubic-bezier(.2,.8,.2,1)}
@keyframes kin{from{opacity:0;transform:translateY(10px) scale(.96)}}
.kcard.leaving{opacity:0;transform:translateX(16px) scale(.96);transition:all .25s}
.dots span{display:inline-block;width:6px;height:6px;margin:0 2px;border-radius:9999px;background:#a8a29e;animation:blink 1.2s infinite}
.dots span:nth-child(2){animation-delay:.15s}.dots span:nth-child(3){animation-delay:.3s}
@keyframes blink{0%,80%,100%{opacity:.25;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}
.msg{animation:kin .35s ease-out}
.glow{box-shadow:0 30px 80px -30px rgba(234,88,12,.45)}
details[open] .faq-plus{transform:rotate(45deg);background:#1c1917;color:#fff}
details[open] .faq-body{animation:kin .3s ease-out}
summary::-webkit-details-marker{display:none}
#progress{transform-origin:0 50%;transform:scaleX(0)}
.lw{color:#d6d3d1;transition:color .3s}
.lw.on{color:#1c1917}.lw.hl.on{color:#ea580c}
.story-panel{position:absolute;inset:1rem;opacity:0;transform:translateY(18px) scale(.98);transition:opacity .45s,transform .45s;pointer-events:none}
.story-panel.active{opacity:1;transform:none}
.story-inline .story-panel{position:relative;inset:auto}
.story-panel .pop{opacity:0}
.story-panel.active .pop{animation:popin .5s cubic-bezier(.2,.8,.2,1) both}
@keyframes popin{from{opacity:0;transform:translateY(12px) scale(.97)}to{opacity:1;transform:none}}
.story-panel .fill{width:0;transition:width 1s cubic-bezier(.2,.7,.2,1)}
.story-panel.active .fill{width:var(--w)}
@media (min-width:1024px){.story-step{opacity:.22;transition:opacity .5s}.story-step.active{opacity:1}}
.sdot.on{width:1.5rem;background:#ea580c}
.verify.done{background:#16a34a}
.mag{transition:transform .25s cubic-bezier(.2,.8,.2,1),background-color .2s,box-shadow .2s}
@media (prefers-reduced-motion:reduce){.story-panel .pop{opacity:1}.story-panel .fill{width:var(--w)}.lw{color:#1c1917}.lw.hl{color:#ea580c}*,*::before{animation:none!important;transition:none!important;scroll-behavior:auto!important}.js .reveal{opacity:1;transform:none}.bar-grow{transform:none}}
""".replace("GRAIN", GRAIN)


JS = """
(() => {
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const peso = n => '\\u20b1' + Math.round(n).toLocaleString('en-PH');
const wait = ms => new Promise(r => setTimeout(r, reduce ? 0 : ms));
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const onView = (el, fn, threshold = .3) => { if (!el) return; const o = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { fn(); o.disconnect(); } }), {threshold}); o.observe(el); };

// nav
const nav = $('#nav'); const sc = () => nav.classList.toggle('scrolled', scrollY > 16);
addEventListener('scroll', sc, {passive: true}); sc();

// reveal on scroll
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), {threshold: .12, rootMargin: '0px 0px -40px 0px'});
$$('.reveal').forEach(el => io.observe(el));

// spotlight cards
$$('.spot').forEach(c => c.addEventListener('pointermove', e => { const r = c.getBoundingClientRect(); c.style.setProperty('--x', (e.clientX - r.left) + 'px'); c.style.setProperty('--y', (e.clientY - r.top) + 'px'); }));

// rotating word
const rot = $('#rot');
if (rot && !reduce) { const w = JSON.parse(rot.dataset.words); let i = 0;
  setInterval(() => { i = (i + 1) % w.length; rot.classList.add('out'); setTimeout(() => { rot.textContent = w[i]; rot.classList.remove('out'); }, 300); }, 2400); }

// phone tilt
const stage = $('#hero-stage'), phone = $('#phone');
if (stage && !reduce && matchMedia('(pointer: fine)').matches) {
  stage.addEventListener('pointermove', e => { const r = stage.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
    phone.style.transform = `rotateY(${x * 16}deg) rotateX(${-y * 12}deg)`; });
  stage.addEventListener('pointerleave', () => phone.style.transform = '');
}

// phone: tabs + cart
$$('[data-tab]').forEach(t => t.addEventListener('click', () => {
  $$('[data-tab]').forEach(x => x.setAttribute('aria-selected', x === t));
  $$('[data-panel]').forEach(p => p.hidden = p.dataset.panel !== t.dataset.tab);
}));
let cn = 0, ct = 0, tt;
$$('[data-add]').forEach(b => b.addEventListener('click', () => {
  cn++; ct += +b.dataset.price;
  $('#cart-count').textContent = cn + (cn === 1 ? ' item' : ' items') + ' \\u00b7 View cart';
  $('#cart-total').textContent = peso(ct);
  const bar = $('#cart-bar'); bar.classList.remove('bump'); void bar.offsetWidth; bar.classList.add('bump');
  const t = $('#phone-toast'); t.textContent = 'Added ' + b.dataset.add; t.classList.add('show');
  clearTimeout(tt); tt = setTimeout(() => t.classList.remove('show'), 1400);
}));

// calculator
function tween(el, to) { const from = +el.dataset.v || 0; el.dataset.v = to;
  if (reduce) { el.textContent = peso(to); return; }
  const t0 = performance.now(), step = t => { const k = Math.min(1, (t - t0) / 500), e = 1 - Math.pow(1 - k, 3);
    el.textContent = peso(from + (to - from) * e); if (k < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); }
const cs = $('#calc-sales'), cr = $('#calc-rate');
const calc = () => { const sales = Math.max(0, +cs.value || 0), rate = +cr.value, m = sales * rate / 100;
  $('#calc-rate-out').textContent = rate + '%'; cr.style.setProperty('--p', (rate / 40 * 100) + '%');
  $('#bar-fee').style.width = rate + '%'; $('#bar-keep').style.width = (100 - rate) + '%';
  tween($('#calc-month'), m); tween($('#calc-year'), m * 12);
  $$('[data-preset]').forEach(p => p.setAttribute('aria-pressed', +p.dataset.preset === sales)); };
cs.addEventListener('input', calc); cr.addEventListener('input', calc);
$$('[data-preset]').forEach(p => p.addEventListener('click', () => { cs.value = p.dataset.preset; calc(); }));
calc();


// portions + 86
let pc = 12; const pSw = $('#p-switch');
const pRender = () => { const on = pSw.getAttribute('aria-checked') === 'true' && pc > 0;
  pSw.setAttribute('aria-checked', on); pSw.setAttribute('aria-label', on ? 'Available' : 'Sold out');
  $('#p-count').textContent = pc;
  const st = $('#p-status'); st.textContent = on ? pc + ' left today' : 'Sold out \\u00b7 hidden from menu';
  st.className = 'text-xs font-semibold ' + (on ? (pc <= 3 ? 'text-orange-600' : 'text-green-700') : 'text-stone-500');
  const pv = $('#p-preview'); pv.textContent = on ? pc + ' left' : 'Sold out';
  pv.className = 'rounded-full px-2 py-0.5 text-[10px] font-bold ' + (on ? 'bg-orange-50 text-orange-700' : 'bg-stone-900 text-white');
  $('#p-row').classList.toggle('opacity-50', !on); $('#p-row').classList.toggle('grayscale', !on); };
pSw.addEventListener('click', () => { const on = pSw.getAttribute('aria-checked') === 'true'; if (!on && pc === 0) pc = 12; pSw.setAttribute('aria-checked', !on); pRender(); });
$('#p-dec').addEventListener('click', () => { pc = Math.max(0, pc - 1); pRender(); });
$('#p-inc').addEventListener('click', () => { pc++; pSw.setAttribute('aria-checked', 'true'); pRender(); });

// payment verify
const pay = $('#pay-btn');
pay.addEventListener('click', () => { if (pay.dataset.done) return; pay.dataset.done = 1; pay.textContent = 'Paid \\u2713'; pay.classList.replace('bg-stone-950', 'bg-green-600');
  setTimeout(() => { delete pay.dataset.done; pay.textContent = 'Verify'; pay.classList.replace('bg-green-600', 'bg-stone-950'); }, 2500); });

// modes
const modeFee = {'Dine-in': 'Dine-in \\u00b7 table number at checkout', 'Pickup': 'Pickup \\u00b7 no fee', 'Delivery': 'Delivery \\u00b7 Zone 1 \\u00b7 +\\u20b149', 'COD': 'Cash on delivery \\u00b7 Zone 1 \\u00b7 +\\u20b149'};
const segs = (attr, cb) => $$(`[data-${attr}]`).forEach(b => b.addEventListener('click', () => { $$(`[data-${attr}]`).forEach(x => x.setAttribute('aria-pressed', x === b)); cb && cb(b); }));
segs('mode', b => $('#mode-out').textContent = modeFee[b.dataset.mode]); segs('slot');

// tracking loop
const trk = $$('.trk'); let ti = 0;
const trkSet = i => { ti = i; $('#trk-bar').style.width = ((i + 1) / trk.length * 100) + '%'; $('#trk-now').textContent = trk[i].textContent;
  trk.forEach((t, j) => t.classList.toggle('text-stone-950', j <= i)); };
onView($('#trk-bar'), () => { trkSet(0); if (!reduce) setInterval(() => trkSet((ti + 1) % trk.length), 1800); });

// AI chat
const CHAT = __CHAT__;
const log = $('#chat-log'); let busy = false;
const bubble = (html, me) => { const d = document.createElement('div'); d.className = 'msg flex ' + (me ? 'justify-end' : 'justify-start');
  d.innerHTML = `<div class="max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${me ? 'bg-orange-600 text-white rounded-br-md' : 'bg-white/[.07] text-stone-100 ring-1 ring-white/10 rounded-bl-md'}">${html}</div>`;
  log.appendChild(d); log.scrollTop = log.scrollHeight; return d.firstElementChild; };
async function ask(i) {
  if (busy) return; busy = true; const c = CHAT[i];
  $$('[data-q]').forEach(b => b.setAttribute('aria-pressed', +b.dataset.q === i));
  log.innerHTML = ''; bubble(esc(c.q), true); await wait(350);
  const typing = bubble('<span class="dots"><span></span><span></span><span></span></span>'); await wait(900);
  typing.textContent = ''; const words = c.a.split(' ');
  for (let k = 0; k < words.length; k++) { typing.textContent += (k ? ' ' : '') + words[k]; log.scrollTop = log.scrollHeight; await wait(28); }
  if (c.cart) { await wait(250); const d = document.createElement('div'); d.className = 'msg';
    d.innerHTML = `<div class="max-w-[85%] rounded-2xl bg-orange-500/10 p-3.5 ring-1 ring-orange-400/30"><p class="text-[11px] font-semibold uppercase tracking-wider text-orange-300">Proposed cart</p><p class="mt-1 text-sm font-semibold">${esc(c.cart[0])}</p><p class="text-xs text-stone-400">${esc(c.cart[1])}</p><div class="mt-3 flex gap-2"><button type="button" class="cart-yes rounded-full bg-orange-500 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-orange-400">Add to cart</button><button type="button" class="cart-no rounded-full px-3.5 py-1.5 text-xs font-semibold ring-1 ring-white/20 hover:ring-white/40">Not now</button></div></div>`;
    log.appendChild(d); log.scrollTop = log.scrollHeight;
    d.querySelector('.cart-yes').onclick = e => { e.target.parentElement.innerHTML = '<p class="text-xs font-semibold text-green-400">\\u2713 Added. The customer confirmed it.</p>'; };
    d.querySelector('.cart-no').onclick = e => { e.target.parentElement.innerHTML = '<p class="text-xs text-stone-400">No problem. Nothing was added.</p>'; }; }
  busy = false;
}
$$('[data-q]').forEach(b => b.addEventListener('click', () => ask(+b.dataset.q)));
onView($('#ai-panel'), () => ask(0), .5);

// kitchen board
const ORDERS = [['#1044', 'Pickup', '2 \\u00d7 Adobo Bowl'], ['#1045', 'Dine-in', 'Ube Latte, Sisig Rice'], ['#1046', 'Delivery', 'Brown Sugar Boba \\u00d7 3'],
  ['#1047', 'Pickup', 'Tapsilog, Iced Americano'], ['#1048', 'Delivery', '6 \\u00d7 Ube Pandesal'], ['#1049', 'Dine-in', 'Salted Caramel Macchiato']];
const NEXT = {prep: 'ready', ready: 'out', out: null}, LBL = {prep: 'Mark ready', ready: 'Send out', out: 'Complete'};
let oi = 0, done = 0;
const counts = () => $$('[data-col]').forEach(c => { $(`[data-count="${c.dataset.col}"]`).textContent = c.children.length; });
function kcard(o, col) {
  const d = document.createElement('div'); d.className = 'kcard rounded-xl bg-white p-2.5 ring-1 ring-stone-200 shadow-sm';
  d.innerHTML = `<div class="flex items-center justify-between gap-1"><p class="text-xs font-bold">${o[0]}</p><span class="truncate rounded-full bg-stone-100 px-1.5 text-[9px] font-semibold text-stone-600">${o[1]}</span></div><p class="mt-0.5 truncate text-[11px] text-stone-500">${o[2]}</p><button type="button" class="adv mt-2 w-full rounded-lg bg-stone-950 py-1 text-[10px] font-semibold text-white hover:bg-orange-600 transition"></button>`;
  const btn = d.querySelector('.adv');
  const place = c => { col = c; btn.textContent = LBL[c] + (NEXT[c] ? ' \\u2192' : ' \\u2713'); $(`[data-col="${c}"]`).appendChild(d); d.classList.remove('kcard'); void d.offsetWidth; d.classList.add('kcard'); counts(); };
  btn.onclick = () => { d.classList.add('leaving'); setTimeout(() => { d.classList.remove('leaving');
    if (NEXT[col]) place(NEXT[col]); else { d.remove(); $('#k-done').textContent = ++done; counts(); setTimeout(arrive, 700); } }, 220); };
  place(col);
}
const arrive = () => { if ($('[data-col="prep"]').children.length < 3) kcard(ORDERS[oi++ % ORDERS.length], 'prep'); };
kcard(ORDERS[oi++], 'prep'); kcard(ORDERS[oi++], 'prep'); kcard(['#1043', 'Pickup', '3 \\u00d7 Ensaymada'], 'ready'); kcard(['#1042', 'Delivery', 'Poblacion \\u00b7 GCash \\u2713'], 'out');

// co-pilot
const CP = __COPILOT__, cpOut = $('#cp-out');
$$('[data-cp]').forEach(b => b.addEventListener('click', () => {
  const c = CP[+b.dataset.cp];
  cpOut.className = 'relative z-10 mt-4 min-h-[150px] rounded-2xl bg-orange-50 p-4 ring-1 ring-orange-200';
  cpOut.innerHTML = `<p class="text-[11px] font-semibold uppercase tracking-wider text-orange-700">Proposed action</p><p class="mt-1 font-semibold">${esc(c.title)}</p><p class="mt-1 text-xs text-stone-600">${esc(c.detail)}</p><div class="mt-4 flex gap-2"><button type="button" class="ok rounded-full bg-stone-950 px-4 py-1.5 text-xs font-semibold text-white hover:bg-orange-700">Confirm</button><button type="button" class="no rounded-full px-4 py-1.5 text-xs font-semibold ring-1 ring-stone-300">Cancel</button></div>`;
  cpOut.querySelector('.ok').onclick = () => { cpOut.className = 'relative z-10 mt-4 grid min-h-[150px] place-items-center rounded-2xl bg-green-50 p-4 ring-1 ring-green-200 text-center';
    cpOut.innerHTML = `<p class="msg text-sm font-semibold text-green-800">\\u2713 ${esc(c.done)}</p>`; };
  cpOut.querySelector('.no').onclick = () => { cpOut.className = 'relative z-10 mt-4 grid min-h-[150px] place-items-center rounded-2xl border border-dashed border-stone-300 p-4';
    cpOut.innerHTML = '<p class="msg text-sm text-stone-500">Cancelled. Nothing changed.</p>'; };
}));

// scroll progress
const prog = $('#progress');
const progUpd = () => { const h = document.documentElement.scrollHeight - innerHeight; prog.style.transform = `scaleX(${h > 0 ? scrollY / h : 0})`; };
addEventListener('scroll', progUpd, {passive: true}); progUpd();

// magnetic buttons
if (!reduce && matchMedia('(pointer: fine)').matches) $$('.mag').forEach(b => {
  b.addEventListener('pointermove', e => { const r = b.getBoundingClientRect(); b.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * .18}px, ${(e.clientY - r.top - r.height / 2) * .3}px)`; });
  b.addEventListener('pointerleave', () => b.style.transform = '');
});

// store preview builder
const TYPES = __TYPES__; const cfg = {name: '', type: Object.keys(TYPES)[0], color: '#c2410c'};
let pvN = 0, pvT = 0;
const slug = s => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 24) || 'yourstore';
const initials = s => (s.trim().split(/\\s+/).filter(w => /^[\\p{L}\\p{N}]/u.test(w) && !/^(at|and|ng|sa|the|of|&)$/i.test(w)).slice(0, 2).map(w => w[0]).join('') || 'YS').toUpperCase();
function pvCart() { $('#pv-count').textContent = pvN ? pvN + (pvN === 1 ? ' item' : ' items') + ' · View cart' : 'Tap + to add'; $('#pv-total').textContent = peso(pvT); }
function renderCfg(items) {
  const name = cfg.name.trim() || 'Your Store', t = TYPES[cfg.type];
  $$('.pv-name').forEach(e => e.textContent = name); $$('.pv-slug').forEach(e => e.textContent = $('#cfg-slug').value || slug(name));
  $$('.pv-init').forEach(e => e.textContent = initials(name)); $$('.pv-bg').forEach(e => e.style.backgroundColor = cfg.color);
  $$('.pv-tag').forEach(e => e.textContent = t.tag); $$('.pv-cat').forEach(e => e.textContent = t.cat);
  if (!items) return;
  pvN = 0; pvT = 0; pvCart();
  $('#pv-items').innerHTML = t.items.map(([n, d, p], k) => `<div class="msg flex items-center gap-3 rounded-2xl bg-white p-2.5 ring-1 ring-stone-200/80" style="animation-delay:${k * 60}ms"><div class="size-11 shrink-0 rounded-xl bg-gradient-to-br from-amber-100 via-orange-100 to-rose-100"></div><div class="min-w-0 flex-1"><p class="truncate text-[13px] font-semibold">${esc(n)}</p><p class="truncate text-[11px] text-stone-500">${esc(d)}</p><p class="text-[13px] font-bold">${peso(p)}</p></div><button type="button" data-pv="${p}" aria-label="Add ${esc(n)}" class="pv-bg grid size-7 shrink-0 place-items-center rounded-full font-bold text-white transition active:scale-90" style="background-color:${cfg.color}">+</button></div>`).join('');
  $$('[data-pv]').forEach(b => b.addEventListener('click', () => { pvN++; pvT += +b.dataset.pv; pvCart(); const bar = $('#pv-bar'); bar.classList.remove('bump'); void bar.offsetWidth; bar.classList.add('bump'); }));
}
const slugIn = $('#cfg-slug'); let slugTouched = false, slugTimer;
const checkSlug = () => { clearTimeout(slugTimer); const v = slugIn.value; const st = $('#slug-status');
  if (!v) { st.textContent = ''; return; }
  slugTimer = setTimeout(async () => { try { const r = await fetch('/signup/check?slug=' + encodeURIComponent(v), {headers: {'HX-Request': 'true'}});
    if (slugIn.value === v) st.outerHTML = await r.text(); } catch (e) {} }, 350); };
$('#cfg-name').addEventListener('input', e => { cfg.name = e.target.value;
  if (!slugTouched) { slugIn.value = e.target.value.trim() ? slug(e.target.value) : ''; checkSlug(); }
  renderCfg(false); });
slugIn.addEventListener('input', () => { slugTouched = true;
  slugIn.value = slugIn.value.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 30); renderCfg(false); checkSlug(); });
const sf = $('#signup-form'), sBtn = $('#signup-btn');
sf.addEventListener('submit', async e => {
  e.preventDefault(); if (!sf.reportValidity()) return;
  sBtn.disabled = true; $$('.btn-label', sBtn).forEach(x => x.classList.add('hidden')); $('.btn-busy', sBtn).classList.remove('hidden');
  const done = () => { sBtn.disabled = false; $$('.btn-label', sBtn).forEach(x => x.classList.remove('hidden')); $('.btn-busy', sBtn).classList.add('hidden'); };
  try {
    const r = await fetch('/signup', {method: 'POST', body: new FormData(sf), headers: {'HX-Request': 'true'}});
    const to = r.headers.get('HX-Redirect');
    if (to) { location.href = to; return; }
    $('#signup-error').outerHTML = await r.text(); $('#signup-error').scrollIntoView({block: 'center', behavior: 'smooth'});
  } catch (err) { $('#signup-error').textContent = 'Network error. Please try again.'; }
  done();
});
$$('[data-type]').forEach(b => b.addEventListener('click', () => { $$('[data-type]').forEach(x => x.setAttribute('aria-pressed', x === b)); cfg.type = b.dataset.type; $('#cfg-kind').value = cfg.type; renderCfg(true); }));
$$('[data-color]').forEach(b => b.addEventListener('click', () => { $$('[data-color]').forEach(x => x.setAttribute('aria-pressed', x === b)); cfg.color = b.dataset.color; $('#cfg-color').value = cfg.color; renderCfg(false); }));
renderCfg(true);

// scroll-lit manifesto
const lws = $$('#manifesto .lw');
if (!reduce && lws.length) { const man = $('#manifesto');
  const lit = () => { const r = man.getBoundingClientRect(), p = Math.min(1, Math.max(0, (innerHeight * .85 - r.top) / (r.height + innerHeight * .35)));
    const n = Math.round(p * lws.length); lws.forEach((w, k) => w.classList.toggle('on', k < n)); };
  addEventListener('scroll', lit, {passive: true}); lit(); }

// a day with ServeFlow
const hooks = {
  0: el => el.querySelectorAll('.tick').forEach(t => { t.dataset.v = 0; const to = +t.dataset.to; if (reduce) { t.textContent = to; return; }
       const t0 = performance.now(), f = n => { const k = Math.min(1, (n - t0) / 900); t.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(f); }; requestAnimationFrame(f); }),
  2: el => { const v = el.querySelector('.verify'); v.classList.remove('done'); v.textContent = 'Verify'; setTimeout(() => { v.classList.add('done'); v.textContent = 'Verified ✓'; }, reduce ? 0 : 1100); },
  3: el => { const s = el.querySelector('.auto-off'); if (!s) return; const row = s.parentElement, st = row.querySelector('.st');
       s.setAttribute('aria-checked', 'true'); row.classList.remove('opacity-50'); st.textContent = '2 left'; st.className = 'st text-xs font-semibold text-orange-600';
       setTimeout(() => { s.setAttribute('aria-checked', 'false'); row.classList.add('opacity-50'); st.textContent = 'Sold out'; st.className = 'st text-xs font-semibold text-stone-500'; }, reduce ? 0 : 1100); },
  4: el => el.querySelectorAll('[data-peso]').forEach(e => { e.dataset.v = 0; tween(e, +e.dataset.peso); }),
};
let storyAt = -1;
function story(i) { if (i === storyAt) return; storyAt = i;
  $$('[data-story]').forEach(s => s.classList.toggle('active', +s.dataset.story === i));
  $$('.sdot').forEach(d => d.classList.toggle('on', +d.dataset.dot === i));
  const step = $(`[data-story="${i}"]`); $('#story-clock').textContent = step.dataset.time;
  $$('.story-panel').forEach(p => { const on = +p.dataset.storyPanel === i; const was = p.classList.contains('active');
    if (on && !was) { p.classList.add('active'); hooks[i] && hooks[i](p); } else if (!on && !p.closest('.story-inline')) p.classList.remove('active'); });
}
const sio = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) story(+e.target.dataset.story); }), {rootMargin: '-45% 0px -45% 0px'});
$$('[data-story]').forEach(s => sio.observe(s));
story(0);
})();
"""


# ---------------------------------------------------------------- small standalone pages

FONT_DISPLAY = Link(rel="stylesheet",
                    href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800&display=swap")


def _simple_doc(title: str, *body, brand: str = ORANGE, noindex: bool = False) -> Response:
    html = Html(
        Head(Meta(charset="utf-8"), Title(title), Meta(name="theme-color", content=brand),
             Meta(name="robots", content="noindex") if noindex else None,
             *ui.HDRS, FONT_DISPLAY,
             Style(".font-display{font-family:'Bricolage Grotesque',Inter,system-ui,sans-serif;letter-spacing:-.025em}")),
        Body(*body, cls="antialiased"), lang="en")
    return Response("<!doctype html>\n" + to_xml(html), media_type="text/html")


def coming_soon(settings: dict) -> Response:
    """What customers see on a store that hasn't been activated yet."""
    brand = settings.get("brand_color") if ui.HEX.match(str(settings.get("brand_color", ""))) else ORANGE
    name = settings.get("name") or "This store"
    return _simple_doc(
        f"{name} · Opening soon",
        Div(Div(Div(name[:1].upper(), style=f"background:{brand}",
                    cls="mx-auto grid size-16 place-items-center rounded-full font-display text-2xl font-bold text-white"),
                H1(name, cls="font-display mt-6 text-4xl font-bold text-balance"),
                P(settings.get("tagline") or "", cls="mt-2 text-stone-600"),
                P("Online ordering opens soon", style=f"color:{brand}", cls="mt-8 text-lg font-semibold"),
                P("We're getting our menu ready. Check back shortly!", cls="mt-1 text-stone-500"),
                A("Owner login", href="/admin/login", cls="mt-12 inline-block text-xs text-stone-400 underline"),
                cls="mx-auto max-w-md px-6 text-center"),
            cls="grid min-h-screen place-items-center bg-[#faf7f2]"),
        brand=brand, noindex=True)


def login_page(base: str, store: str = "", not_found: bool = False) -> Response:
    dom = "yourdomain.com" if base == "localhost" else base
    return _simple_doc(
        "Log in to your store · ServeFlow",
        Div(Div(A(Span(cls="size-2.5 rounded-full bg-gradient-to-br from-orange-500 to-rose-500"),
                  Span("ServeFlow", cls="font-display text-lg font-bold"), href="/", cls="flex items-center justify-center gap-2"),
                H1("Log in to your store", cls="font-display mt-8 text-3xl font-bold"),
                P("Enter your store link and we'll take you to your owner dashboard.", cls="mt-2 text-stone-600"),
                Form(Div(Input(name="store", value=store, required=True, autofocus=True, autocapitalize="none",
                               spellcheck="false", placeholder="yourstore",
                               cls="min-w-0 flex-1 bg-transparent py-3.5 pl-4 font-semibold outline-none"),
                         Span(f".{dom}", cls="shrink-0 pr-4 text-sm text-stone-500"),
                         cls="flex items-center rounded-2xl bg-white ring-1 ring-stone-300 focus-within:ring-2 focus-within:ring-orange-600"),
                     P("We couldn't find that store. Check the spelling.", cls="mt-2 text-sm font-semibold text-red-700")
                     if not_found else None,
                     Button("Continue →", type="submit",
                            cls="mt-4 w-full rounded-full bg-stone-950 px-6 py-3.5 font-semibold text-white hover:bg-orange-700 transition"),
                     method="get", action="/login", cls="mt-8 text-left"),
                P("New here? ", A("Create your store", href="/#start", cls="font-semibold text-orange-700 underline"),
                  cls="mt-6 text-sm text-stone-600"),
                cls="mx-auto w-full max-w-sm px-6 text-center"),
            cls="grid min-h-screen place-items-center bg-[#faf7f2]"),
        noindex=True)


# ---------------------------------------------------------------- page

def page(base_domain: str) -> Response:
    contact = os.environ.get("CONTACT_URL", "").strip() or None
    demo = None
    local = (sorted(p.stem for p in db.DATA_DIR.glob("*.db") if db.STORE_RE.match(p.stem))
             if base_domain == "localhost" else [])
    title = "ServeFlow: 0% commission online ordering for Philippine restaurants & cafés"
    desc = ("Your own branded online ordering store with GCash payments, a kitchen queue and an AI menu "
            "concierge. One-time setup, no monthly fees, 0% commission.")
    js = JS.replace("__TYPES__", json.dumps(TYPES)).replace("__CHAT__", json.dumps(CHAT)).replace("__COPILOT__", json.dumps(COPILOT))
    html = Html(
        Head(Meta(charset="utf-8"), Title(title), Meta(name="description", content=desc),
             Meta(property="og:title", content=title), Meta(property="og:description", content=desc),
             Meta(property="og:type", content="website"), Meta(name="theme-color", content=ORANGE),
             Script("document.documentElement.classList.add('js')"),
             *ui.HDRS,
             Link(rel="stylesheet",
                  href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800&display=swap"),
             Style(CSS)),
        Body(Div(id="progress", cls="fixed inset-x-0 top-0 z-[60] h-[3px] bg-gradient-to-r from-orange-500 via-amber-400 to-rose-500"),
             _nav(contact, demo),
             Div(_hero(contact, demo), _marquee(), _preview(base_domain), _calculator(), _manifesto(), _features(base_domain),
                 _day(), _ai(), _kitchen(),
                 _steps(), _pricing(contact, demo), _faq(), _final_cta(contact, demo), cls="overflow-x-clip"),
             _footer(local, base_domain),
             Script(js),
             cls="antialiased selection:bg-orange-200"),
        lang="en")
    return Response("<!doctype html>\n" + to_xml(html), media_type="text/html")

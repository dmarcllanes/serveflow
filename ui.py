"""Shared FT components, design tokens, badges and page layout (Tailwind via CDN)."""

from __future__ import annotations

import re

from fasthtml.common import (
    A, Button, Div, Form, H1, Img, Input, Label, Link, Main, Meta, NotStr, Option, P, Script,
    Select, Span, Style, Textarea, Title,
)

TAILWIND = Script(src="https://cdn.tailwindcss.com")
TW_CONFIG = Script("""
tailwind.config = { theme: { extend: {
  colors: { brand: 'var(--brand)', accent: 'var(--accent)' },
  fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] } } } };
""")
FONT = Link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap")

BASE_CSS = Style("""
html { -webkit-tap-highlight-color: transparent; }
body { background: #faf7f2; color: #1c1917; }
.htmx-request .htmx-hide { display: none; }
.htmx-indicator { display: none; } .htmx-request .htmx-indicator, .htmx-request.htmx-indicator { display: inline-block; }
.no-scrollbar::-webkit-scrollbar { display: none; } .no-scrollbar { scrollbar-width: none; }
dialog::backdrop { background: rgba(28,25,23,.55); }
#toast > div { animation: toastin .25s cubic-bezier(.2,.8,.2,1); }
@keyframes toastin { from { transform: translateY(12px) scale(.96); opacity: 0 } to { transform: none; opacity: 1 } }
.sheet { animation: sheetin .32s cubic-bezier(.2,.8,.2,1); }
@keyframes sheetin { from { transform: translateY(40px); opacity: 0 } to { transform: none; opacity: 1 } }
@media (min-width: 640px) { @keyframes sheetin { from { transform: translate(-50%,-46%) scale(.97); opacity: 0 }
  to { transform: translate(-50%,-50%); opacity: 1 } } }
.fade { animation: fadein .25s ease-out; } @keyframes fadein { from { opacity: 0 } }
.bump { animation: bump .45s cubic-bezier(.3,1.6,.5,1); } @keyframes bump { 40% { transform: scale(1.06) } }
.press { transition: transform .15s; } .press:active { transform: scale(.96); }
.opt:has(input:checked) { border-color: var(--brand); background: color-mix(in srgb, var(--brand) 7%, #fff);
  box-shadow: 0 0 0 1px var(--brand); }
.opt:has(input:disabled:not(:checked)) { opacity: .45; }
.opt .tick { opacity: 0; transform: scale(.5); transition: .15s; } .opt:has(input:checked) .tick { opacity: 1; transform: none; }
.grp.need .grp-state { background: #fff7ed; color: #9a3412; }
.grp.done .grp-state { background: #ecfdf5; color: #047857; }
.grp.shake { animation: shake .4s; } @keyframes shake { 25%,75% { transform: translateX(-5px) } 50% { transform: translateX(5px) } }
[data-incart]:empty { display: none; }
[hidden] { display: none !important; }
summary.list-none::-webkit-details-marker { display: none; }
.incart { background: color-mix(in srgb, var(--brand) 12%, #fff); color: color-mix(in srgb, var(--brand) 80%, #000); }
.text-deep { color: color-mix(in srgb, var(--brand) 78%, #000); }
.bg-soft { background: color-mix(in srgb, var(--brand) 8%, #fff); }
.chip-on { background: var(--brand) !important; color: #fff !important; border-color: transparent !important; }
.opt:has(input:checked) .ind { background: var(--brand); border-color: var(--brand); }
.opt:has(input:focus-visible) { outline: 2px solid var(--brand); outline-offset: 2px; }
.ring-now { box-shadow: 0 0 0 5px color-mix(in srgb, var(--brand) 22%, transparent); }
body.modal-open { overflow: hidden; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
""")

TOAST_JS = Script("""
(() => {
const closeModal = () => { const m = document.getElementById('modal'); if (m) m.innerHTML = ''; };
window.bfCloseModal = closeModal;
document.body.addEventListener('toast', e => {
  const t = document.getElementById('toast'); if (!t) return;
  const d = document.createElement('div');
  d.className = 'mx-auto flex w-fit max-w-[90vw] items-center gap-2 rounded-full bg-stone-900 text-white text-sm font-medium pl-2 pr-4 py-2 shadow-xl';
  const bad = !!e.detail.error;
  const i = document.createElement('span'); i.textContent = bad ? '!' : '✓';
  i.className = 'grid size-6 place-items-center rounded-full text-xs font-bold ' + (bad ? 'bg-red-500' : 'bg-emerald-500');
  const s = document.createElement('span'); s.textContent = e.detail.value || e.detail.message || 'Done';
  d.append(i, s); t.appendChild(d); setTimeout(() => d.remove(), 2600);
});
// cart changed: refresh "2 in cart" pills on every card and give the cart bar a little bounce
document.body.addEventListener('cart', e => {
  const counts = (e.detail.value || e.detail || {}).counts || {};
  document.querySelectorAll('[data-incart]').forEach(el => {
    const n = counts[el.dataset.incart] || 0; el.textContent = n ? n + ' in cart' : '';
  });
  document.querySelectorAll('#cartbar > *, #cart-panel').forEach(bar => {
    bar.classList.remove('bump'); void bar.offsetWidth; bar.classList.add('bump'); });
});
document.body.addEventListener('closeModal', closeModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
const m = document.getElementById('modal');
if (m) new MutationObserver(() => document.body.classList.toggle('modal-open', !!m.children.length))
  .observe(m, {childList: true});
})();
""")

HDRS = (Meta(name="viewport", content="width=device-width, initial-scale=1, viewport-fit=cover"),
        FONT, TAILWIND, TW_CONFIG, BASE_CSS)

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def theme(settings: dict):
    brand = settings.get("brand_color") if HEX.match(str(settings.get("brand_color", ""))) else "#c2410c"
    accent = settings.get("accent_color") if HEX.match(str(settings.get("accent_color", ""))) else "#fef3c7"
    return Style(f":root {{ --brand: {brand}; --accent: {accent}; }}")


def page(title: str, settings: dict, *content, cls: str = "max-w-2xl"):
    return (
        Title(title),
        theme(settings),
        Main(*content, cls=f"{cls} mx-auto min-h-screen pb-28"),
        Div(id="modal"),
        Div(id="toast", cls="fixed bottom-24 inset-x-0 z-50 flex flex-col gap-2 pointer-events-none"),
        TOAST_JS,
    )


# ---------------------------------------------------------------- formatting

def peso(cents: int | None) -> str:
    cents = cents or 0
    s = f"₱{abs(cents) / 100:,.2f}".replace(".00", "")
    return ("-" if cents < 0 else "") + s


def delta(cents: int) -> str:
    return "" if not cents else (f"+{peso(cents)}" if cents > 0 else peso(cents))


# ---------------------------------------------------------------- primitives

def btn(*c, kind: str = "primary", cls: str = "", **kw):
    styles = {
        "primary": "bg-brand text-white hover:opacity-90",
        "dark": "bg-stone-900 text-white hover:bg-stone-800",
        "ghost": "bg-white border border-stone-300 text-stone-800 hover:bg-stone-50",
        "danger": "bg-white border border-red-300 text-red-700 hover:bg-red-50",
        "success": "bg-emerald-600 text-white hover:bg-emerald-700",
    }
    return Button(*c, cls=f"inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 font-semibold "
                         f"text-sm transition disabled:opacity-50 {styles[kind]} {cls}", **kw)


def link_btn(*c, href: str, kind: str = "primary", cls: str = "", **kw):
    styles = {"primary": "bg-brand text-white", "ghost": "bg-white border border-stone-300 text-stone-800",
              "dark": "bg-stone-900 text-white"}
    return A(*c, href=href, cls=f"inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 "
                                f"font-semibold text-sm {styles[kind]} {cls}", **kw)


def card(*c, cls: str = "", **kw):
    return Div(*c, cls=f"bg-white rounded-2xl border border-stone-200 shadow-sm {cls}", **kw)


INPUT_CLS = ("w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-[15px] "
             "focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand")


def field(label: str, name: str, value="", type: str = "text", hint: str = "", **kw):
    if type == "textarea":
        el = Textarea(value or "", name=name, cls=INPUT_CLS + " min-h-[88px]", **kw)
    elif type == "color":  # show a real swatch, not a thin line
        el = Input(name=name, value=value or "#000000", type=type,
                   cls="h-11 w-full cursor-pointer rounded-xl border border-stone-300 bg-white p-1", **kw)
    else:
        el = Input(name=name, value="" if value is None else value, type=type, cls=INPUT_CLS, **kw)
    return Label(Span(label, cls="block text-sm font-medium text-stone-700 mb-1"), el,
                 P(hint, cls="text-xs text-stone-500 mt-1") if hint else None, cls="block")


def select(label: str, name: str, options: list[tuple], value=None, **kw):
    return Label(Span(label, cls="block text-sm font-medium text-stone-700 mb-1"),
                 Select(*[Option(t, value=str(v), selected=str(v) == str(value)) for v, t in options],
                        name=name, cls=INPUT_CLS, **kw), cls="block")


def error_box(msg: str | None, id: str = "form-error"):
    return Div(P(msg, cls="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2")
               if msg else None, id=id)


# ---------------------------------------------------------------- badges

BADGE_STYLE = {
    "86": "bg-stone-900 text-white",
    "sold_out": "bg-stone-900 text-white",
    "spicy": "bg-red-100 text-red-700",
    "best_seller": "bg-amber-100 text-amber-800",
    "new": "bg-sky-100 text-sky-800",
    "vegetarian": "bg-emerald-100 text-emerald-800",
    "low": "bg-orange-100 text-orange-800",
}
TAG_LABEL = {"spicy": "🌶 Spicy", "best_seller": "★ Best Seller", "new": "New", "vegetarian": "🌱 Veggie"}


def badge(text: str, kind: str = "new", cls: str = ""):
    return Span(text, cls=f"inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold "
                          f"{BADGE_STYLE.get(kind, 'bg-stone-100 text-stone-700')} {cls}")


def item_badges(it: dict):
    out = []
    if it.get("sold_out") or (it.get("remaining") is not None and it["remaining"] <= 0):
        out.append(badge("86 · Sold Out", "86"))
    elif it.get("remaining") is not None and it["remaining"] <= 5:
        out.append(badge(f"Only {it['remaining']} left", "low"))
    for t in it.get("tags", []):
        if t in TAG_LABEL:
            out.append(badge(TAG_LABEL[t], t))
    return Div(*out, cls="flex flex-wrap gap-1") if out else None


STATUS_STYLE = {
    "pending_payment": "bg-amber-100 text-amber-800",
    "preparing": "bg-sky-100 text-sky-800",
    "ready": "bg-emerald-100 text-emerald-800",
    "out_for_delivery": "bg-violet-100 text-violet-800",
    "completed": "bg-stone-200 text-stone-700",
    "cancelled": "bg-red-100 text-red-700",
}


def status_badge(status: str, label: str):
    return Span(label, cls=f"inline-flex rounded-full px-2.5 py-1 text-xs font-semibold {STATUS_STYLE.get(status, '')}")


def modal(*content, title: str = "", hero=None):
    """Bottom-sheet modal swapped into #modal. `hero` is an optional full-bleed image/tile on top."""
    close = Button("✕", cls="grid size-9 place-items-center rounded-full bg-white/90 text-stone-700 shadow ring-1 "
                             "ring-stone-900/10 backdrop-blur hover:bg-white", type="button", aria_label="Close",
                   onclick="document.getElementById('modal').innerHTML=''")
    head = (Div(hero, Div(close, cls="absolute right-3 top-3"), cls="relative -mx-5 -mt-5 mb-4") if hero else
            Div(Span(title, cls="font-bold text-lg"), close, cls="flex items-center justify-between mb-3"))
    return Div(
        Div(cls="fade fixed inset-0 bg-stone-900/55 backdrop-blur-[2px] z-40",
            onclick="document.getElementById('modal').innerHTML=''"),
        Div(
            Div(cls="mx-auto -mt-2 mb-3 h-1.5 w-10 rounded-full bg-stone-300 sm:hidden") if not hero else None,
            head, *content,
            role="dialog", aria_modal="true", aria_label=title or None,
            cls="sheet fixed z-50 inset-x-0 bottom-0 sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 "
                "sm:-translate-y-1/2 w-full sm:max-w-lg max-h-[92vh] overflow-y-auto overscroll-contain bg-white "
                "rounded-t-[1.75rem] sm:rounded-[1.75rem] p-5 shadow-2xl"),
    )


FOOD_EMOJI = [  # first keyword match wins (food words before drink words); used when an item has no photo
    ("melonpan", "🍈"), ("croissant", "🥐"), ("ensaymada", "🥐"), ("pandesal", "🥖"), ("bun", "🥯"),
    ("sourdough", "🍞"), ("loaf", "🍞"), ("bread", "🍞"), ("toast", "🍞"), ("box", "🎁"), ("set", "🍱"),
    ("cookie", "🍪"), ("brownie", "🍫"), ("cake", "🍰"), ("roll", "🍥"), ("flan", "🍮"), ("leche", "🍮"),
    ("halo", "🍧"), ("ice cream", "🍨"), ("donut", "🍩"), ("pancit", "🍜"), ("noodle", "🍜"), ("ramen", "🍜"),
    ("lumpia", "🥟"), ("shanghai", "🥟"), ("siomai", "🥟"), ("dumpling", "🥟"), ("sisig", "🍳"),
    ("silog", "🍳"), ("adobo", "🍗"), ("chicken", "🍗"), ("kare", "🍲"), ("sinigang", "🍲"),
    ("soup", "🍲"), ("beef", "🥩"), ("pork", "🥓"), ("fish", "🐟"), ("shrimp", "🍤"), ("rice", "🍚"),
    ("burger", "🍔"), ("fries", "🍟"), ("pizza", "🍕"), ("pasta", "🍝"), ("salad", "🥗"), ("sandwich", "🥪"),
    ("matcha", "🍵"), ("usucha", "🍵"), ("tea", "🧋"), ("boba", "🧋"), ("taro", "🧋"), ("wintermelon", "🧋"),
    ("latte", "☕"), ("coffee", "☕"), ("americano", "☕"), ("espresso", "☕"), ("macchiato", "☕"),
    ("cappuccino", "☕"), ("mocha", "☕"), ("barako", "☕"), ("chocolate", "🍫"), ("juice", "🧃"),
    ("calamansi", "🍋"), ("lemon", "🍋"), ("mango", "🥭"), ("strawberry", "🍓"), ("shake", "🥤"),
    ("soda", "🥤"), ("egg", "🍳"),
]


def food_emoji(name: str, fallback: str = "🍽") -> str:
    n = (name or "").lower()
    return next((e for k, e in FOOD_EMOJI if k in n), fallback)


def img(src: str | None, alt: str, cls: str = ""):
    if not src:
        return Div(NotStr(food_emoji(alt)), cls=f"flex items-center justify-center bg-accent text-3xl {cls}")
    return Img(src=src, alt=alt, loading="lazy", cls=f"object-cover {cls}")


def empty(text: str, sub: str = ""):
    return Div(P(text, cls="font-semibold text-stone-700"), P(sub, cls="text-sm text-stone-500") if sub else None,
               cls="text-center py-12")


def heading(text: str, sub: str | None = None):
    return Div(H1(text, cls="text-2xl font-extrabold tracking-tight"),
               P(sub, cls="text-stone-500 text-sm") if sub else None, cls="mb-4")


def form(*c, **kw):
    return Form(*c, **kw)

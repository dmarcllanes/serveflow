"""Self-serve onboarding on the bare domain: create a store, then hand the owner off to their
own subdomain's admin with a single-use login token.

New stores start un-activated: the owner can build everything in /admin and preview the
storefront, but customers see "coming soon" until the platform owner runs
`uv run python stores.py activate <store>` (after the one-time setup fee is settled).

Routes (bare domain only; 404 on a store subdomain):
  GET  /signup/check?slug=   live availability for the "your link" field
  POST /signup               create the store → redirect to <store>/admin/welcome?t=…
  GET  /login?store=         "log in to your store" → redirect to <store>/admin/login
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

from fasthtml.common import APIRouter, Div, P, Span
from starlette.responses import RedirectResponse, Response

import db
import seed_client
import ui

ar = APIRouter()

STARTERS: dict = json.loads((Path(__file__).parent / "seeds" / "starters.json").read_text(encoding="utf-8"))
MOBILE_RE = re.compile(r"^(?:\+?63|0)9\d{9}$")

_lock = threading.Lock()
_recent: dict[str, list[float]] = {}  # ip -> signup timestamps
PER_IP_PER_HOUR = 3
GLOBAL_PER_HOUR = 40


def base_domain() -> str:
    return os.environ.get("BASE_DOMAIN", "localhost").lower().strip(".")


def store_url(store: str, path: str = "/") -> str:
    base = base_domain()
    if base == "localhost":
        return f"http://{store}.localhost:{os.environ.get('PORT', '5001')}{path}"
    return f"https://{store}.{base}{path}"


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)[:24]


def tint(hex_color: str, keep: float = 0.12) -> str:
    """Light accent from a brand color (mix with white)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    mix = lambda c: round(255 - (255 - c) * keep)
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


def _client_ip(req) -> str:
    # uvicorn runs with --proxy-headers behind Caddy, so req.client is already the real client IP
    return req.client.host if req.client else "?"


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _lock:
        for k in list(_recent):
            _recent[k] = [t for t in _recent[k] if now - t < 3600]
            if not _recent[k]:
                del _recent[k]
        total = sum(len(v) for v in _recent.values())
        return len(_recent.get(ip, [])) < PER_IP_PER_HOUR and total < GLOBAL_PER_HOUR


def _note_signup(ip: str) -> None:
    with _lock:
        _recent.setdefault(ip, []).append(time.time())


def _bare_only(req) -> Response | None:
    return Response("Not found", status_code=404) if req.scope.get("store") else None


def error(msg: str):
    return Div(Span("⚠", cls="mr-2"), msg, id="signup-error", role="alert",
               cls="relative z-10 mt-5 rounded-2xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-800 ring-1 ring-red-200")


# ---------------------------------------------------------------- routes

@ar("/signup/check", methods=["get"])
def check(req, slug: str = ""):
    if (r := _bare_only(req)):
        return r
    slug = slug.strip().lower()
    if not slug:
        return Span("", id="slug-status")
    problem = db.store_name_problem(slug)
    return Span(f"✕ {problem}" if problem else "✓ Available", id="slug-status",
                cls=f"text-xs font-semibold {'text-red-700' if problem else 'text-green-700'}")


@ar("/signup", methods=["post"])
async def signup(req):
    if (r := _bare_only(req)):
        return r
    form = await req.form()
    htmx = bool(req.headers.get("hx-request"))

    def fail(msg: str):
        return error(msg) if htmx else Response(f"{msg}\n\nGo back and try again.", status_code=400,
                                                 media_type="text/plain; charset=utf-8")

    if (form.get("company") or "").strip():  # honeypot: humans never see this field
        return fail("Something went wrong. Please try again.")
    name = " ".join((form.get("name") or "").split())[:60]
    slug = (form.get("slug") or "").strip().lower() or slugify(name)
    kind = form.get("kind") or ""
    color = form.get("color") or "#c2410c"
    mobile = re.sub(r"[\s\-()]", "", form.get("mobile") or "")
    password = form.get("password") or ""

    if len(name) < 2:
        return fail("Enter your store's name.")
    if kind not in STARTERS:
        return fail("Pick what you sell.")
    if not ui.HEX.match(color):
        color = "#c2410c"
    if (problem := db.store_name_problem(slug)):
        return fail(f"Store link: {problem}")
    if not MOBILE_RE.match(mobile):
        return fail("Enter a valid PH mobile number, e.g. 0917 123 4567.")
    if not 8 <= len(password) <= 128:
        return fail("Password must be at least 8 characters.")
    ip = _client_ip(req)
    if not _rate_ok(ip):
        return fail("Too many new stores from your connection. Please try again in an hour.")

    starter = STARTERS[kind]
    try:
        con = db.claim_store(slug)
    except FileExistsError:
        return fail("Store link: That link was just taken. Try another.")
    try:
        db.set_settings(con, {
            "name": name, "tagline": starter["tagline"], "brand_color": color, "accent_color": tint(color),
            "modes": ["pickup", "dine_in"], "payments": ["counter"],
            "accepting_orders": True, "activated": False,
        })
        seed_client.populate(con, starter)
        db.set_admin_password(con, password)
        db.set_private(con, "owner", {"mobile": mobile, "kind": kind, "created": db.iso(), "ip": ip})
        token = db.issue_login_token(con)
    except Exception:
        db.delete_store_files(slug)
        raise
    _note_signup(ip)
    with open(db.DATA_DIR / "signups.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"store": slug, "name": name, "kind": kind, "mobile": mobile,
                            "created": db.iso(), "ip": ip}, ensure_ascii=False) + "\n")

    dest = store_url(slug, f"/admin/welcome?t={token}")
    if htmx:
        return Response("", headers={"HX-Redirect": dest})
    return RedirectResponse(dest, status_code=303)


@ar("/login", methods=["get"])
def find_store(req, store: str = ""):
    if (r := _bare_only(req)):
        return r
    import landing
    store = store.strip().lower()
    # accept a pasted full link too: "kapeatkain.yourdomain.com" or "https://kapeatkain…"
    store = re.sub(r"^https?://", "", store).split(".")[0].split("/")[0]
    if store and db.store_exists(store):
        return RedirectResponse(store_url(store, "/admin/login"), status_code=303)
    return landing.login_page(base_domain(), store, not_found=bool(store))

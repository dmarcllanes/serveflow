"""ServeFlow app setup: tenancy (subdomain → store DB), auth, route mounting.

Run locally:  uv run python main.py   →  http://demo-resto.localhost:5001
With DEFAULT_STORE=<store> in .env, the bare address (http://localhost:5001) serves that store directly.
"""

from __future__ import annotations

import os

from fasthtml.common import Beforeware, Response, fast_app, serve


def _load_dotenv(path: str = ".env") -> None:
    """Read KEY=value lines from .env (if present) without overriding real environment variables."""
    try:
        lines = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), path), encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

import db  # noqa: E402
import ui  # noqa: E402

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost").lower().strip(".")
DEFAULT_STORE = os.environ.get("DEFAULT_STORE", "")
db.DATA_DIR.mkdir(parents=True, exist_ok=True)


def resolve_store(host: str) -> str | None:
    host = (host or "").split(":")[0].lower().strip(".")
    for base in {BASE_DOMAIN, "localhost"}:
        if host.endswith("." + base):
            sub = host[: -len(base) - 1]
            return None if sub == "www" else sub
    return DEFAULT_STORE or None


PUBLIC_NOSTORE = ("/healthz", "/_tls_check")
BARE_DOMAIN_ROUTES = ("/signup", "/signup/check", "/login")  # signup.py; landing page for everything else
ADMIN_PUBLIC = ("/admin/login", "/admin/welcome")


def before(req, sess):
    path = req.url.path
    if path in PUBLIC_NOSTORE:
        return None
    store = resolve_store(req.headers.get("host", ""))
    if not db.store_exists(store):
        if store is None:
            return None if path in BARE_DOMAIN_ROUTES else landing()
        return Response("Store not found", status_code=404)
    # Only the store name goes in the scope. Handlers open their DB connection with db.get_db()
    # on their own thread: FastHTML runs this beforeware and the handler on different threadpool
    # threads, so a connection fetched here would be shared by concurrent requests.
    req.scope["store"] = store
    con = db.get_db(store)  # this thread's connection; used only inside this function
    is_owner = sess.get("admin") == store
    if is_owner and sess.get("admin_ver", 0) != db.session_version(con):
        sess.pop("admin", None)  # the password was changed on another device
        is_owner = False
    if not path.startswith("/admin"):
        # Un-activated stores: customers get "coming soon"; the logged-in owner gets a preview.
        s = db.get_settings(con)
        if not db.is_live(s):
            if not is_owner:
                import landing as lp
                return lp.coming_soon(s)
            req.scope["preview"] = True
    if path.startswith("/admin") and path not in ADMIN_PUBLIC:
        if not is_owner:
            if req.headers.get("hx-request"):
                return Response("", headers={"HX-Redirect": "/admin/login"})
            from starlette.responses import RedirectResponse
            return RedirectResponse("/admin/login", status_code=303)


def landing():
    import landing as lp
    return lp.page(BASE_DOMAIN)


secret = os.environ.get("SESSION_SECRET")
app, rt = fast_app(
    hdrs=ui.HDRS,
    pico=False,
    before=Beforeware(before, skip=[r"/favicon\.ico"]),
    secret_key=secret,
    key_fname=str(db.DATA_DIR / ".sesskey"),
    sess_https_only=os.environ.get("HTTPS_ONLY", "0") == "1",
    max_age=60 * 60 * 24 * 30,
    title="ServeFlow",
    bodykw={"cls": "font-sans antialiased"},
)


@rt("/healthz")
def healthz():
    return "ok"


@rt("/admin")
def admin_root():
    from starlette.responses import RedirectResponse
    return RedirectResponse("/admin/queue", status_code=303)


@rt("/_tls_check")
def tls_check(domain: str = ""):
    """Caddy on-demand TLS gate: only issue certs for existing stores."""
    d = domain.lower().strip(".")
    ok = d in (BASE_DOMAIN, "www." + BASE_DOMAIN) or (
        d.endswith("." + BASE_DOMAIN) and db.store_exists(resolve_store(d)))
    return Response("ok" if ok else "no", status_code=200 if ok else 404)


import admin  # noqa: E402
import signup  # noqa: E402
import storefront  # noqa: E402
import storehome  # noqa: E402

signup.ar.to_app(app)
storehome.ar.to_app(app)
storefront.ar.to_app(app)
admin.ar.to_app(app)

if __name__ == "__main__":
    serve(port=int(os.environ.get("PORT", 5001)))

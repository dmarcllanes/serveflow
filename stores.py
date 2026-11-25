"""Platform-owner commands for stores.

    uv run python stores.py list                 # every store, live or waiting, with the owner's mobile
    uv run python stores.py activate <store>     # setup fee settled → customers can order
    uv run python stores.py deactivate <store>   # back to "coming soon"

On the server:  docker compose exec app .venv/bin/python stores.py list
"""

from __future__ import annotations

import argparse
import sys

import db


def _open(store: str):
    if not db.store_exists(store):
        sys.exit(f"No store named {store!r}.")
    return db.get_db(store)


def list_stores() -> None:
    rows = []
    for p in sorted(db.DATA_DIR.glob("*.db")):
        if not db.STORE_RE.match(p.stem):
            continue
        con = db.get_db(p.stem)
        s, owner = db.get_settings(con), db.get_private(con, "owner") or {}
        rows.append((p.stem, s["name"], "LIVE" if db.is_live(s) else "waiting",
                     owner.get("mobile", "-"), (owner.get("created") or "-")[:16].replace("T", " ")))
    if not rows:
        print("No stores yet.")
        return
    w = [max(len(str(r[i])) for r in rows + [("STORE", "NAME", "STATUS", "MOBILE", "SIGNED UP")]) for i in range(5)]
    for r in [("STORE", "NAME", "STATUS", "MOBILE", "SIGNED UP")] + rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))


def set_live(store: str, live: bool) -> None:
    con = _open(store)
    db.set_settings(con, {"activated": live})
    print(f"✓ {store} is now {'LIVE: customers can order' if live else 'waiting: customers see coming soon'}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for c in ("activate", "deactivate"):
        sub.add_parser(c).add_argument("store")
    a = ap.parse_args()
    if a.cmd == "list":
        list_stores()
    else:
        set_live(a.store, a.cmd == "activate")

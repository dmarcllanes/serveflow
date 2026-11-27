# ServeFlow

White-label, 0%-commission online ordering for small Philippine food businesses, with an AI menu
concierge and a kitchen co-pilot. One codebase, one SQLite file per store, `<store>.yourdomain.com`.
See `CLAUDE.md` for the architecture.

## Run locally

```bash
uv sync
uv run python seed_client.py seeds/demo-resto.json        # creates data/demo-resto.db
uv run python main.py
```

- Storefront: http://demo-resto.localhost:5001
- Admin: http://demo-resto.localhost:5001/admin (password `demo-owner-123` from the seed)

AI is optional: set `LLM_API_KEY` (and optionally `LLM_BASE_URL`, `LLM_MODEL`; defaults to Groq
`openai/gpt-oss-20b`). Without it, everything still works: the customer chat answers common questions (menu, prices, hours, delivery, payment, allergens) straight from the store's data.

## How customers order

1. **Scan or tap**: a table QR (`<store>…/?table=5`), the store QR on posters and flyers, or the link shared on
   Facebook, Instagram and Messenger. Owners print these from **Admin → QR codes**.
2. **Store homepage** (`<store>…/`): a branded landing page with the store's headline, best sellers,
   menu by category, about, and hours & location. Every **Order** button opens the ordering menu
   (`/menu`, or `/menu?open=<item>` straight to an item). Owners edit the headline, about text, cover photo
   and social links in **Admin → Website**. Table QRs skip the homepage and go straight to the menu.
   Try the sample: `uv run python seed_client.py seeds/matcha-bakery.json` → `http://matchacrumb.localhost:5001`
   (admin password `matcha-owner-123`).
3. **Menu → item options → cart → checkout**. A table QR preselects Dine-in and fills in the table
   number (it's remembered for 4 hours).
4. **Pay**: GCash or bank transfer with a screenshot upload, pay at the counter, or COD.
5. **Track** on the private `/order/<token>` page as the kitchen moves the order through
   Payments → Preparing → Ready → Completed in **Admin → Kitchen**.

## Tests

```bash
uv run pytest -q    # scratch DATA_DIR, never touches data/
```

GitHub Actions runs the tests before every deploy.

## Self-serve signup & going live

Owners create their own store from the "Create your store" form on the bare domain
(`http://localhost:5001` locally). Signup creates `data/<store>.db` with a starter menu for their
business type (`seeds/starters.json`) and logs them straight into `<store>…/admin` (single-use token).

New stores are **not live**: customers see "coming soon", while the logged-in owner can preview
the storefront and place test orders. Once the one-time setup fee is settled:

```bash
uv run python stores.py list                  # live/waiting stores + owner mobile numbers
uv run python stores.py activate <store>      # customers can now order
# on the server: docker compose exec app .venv/bin/python stores.py activate <store>
```

Signups are also appended to `data/signups.jsonl`. Limits: 3 signups per IP per hour, 40 per hour overall.

## New store (manual, from a seed file)

Copy `seeds/demo-resto.json`, change `store` (the subdomain), settings and menu, then
`uv run python seed_client.py seeds/<store>.json --password '<owner password>'`. Use `--reset` to
recreate a store (destroys its orders).

## Deploy (Lightsail/EC2 1 GB)

Step-by-step AWS EC2 guide (launch settings, Elastic IP, sslip.io, backups, troubleshooting): see [`DEPLOY.md`](DEPLOY.md).

1. Install Docker + compose plugin, clone the repo to `/opt/biteflow`, `cp .env.example .env` and fill it.
2. DNS: `A yourdomain.com` and `A *.yourdomain.com` → the instance IP.
3. `./deploy.sh` (Caddy issues certs on demand, only for existing stores).
4. Seed stores on the server: `docker compose exec app .venv/bin/python seed_client.py seeds/<store>.json`.

Auto-deploy: add a dedicated key to the server's `~/.ssh/authorized_keys` pinned to a forced command:

```
command="cd /opt/biteflow && git pull --ff-only && ./deploy.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... deploy@gha
```

and set GitHub secrets `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KNOWN_HOSTS`.
Pushing to `main`/`master` then deploys.

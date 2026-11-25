# CLAUDE.md — BiteFlow (White-Label Agentic Online Ordering for Restaurants & Cafés)

## Project Overview
BiteFlow is a single-codebase, multi-tenant web app that gives small Philippine food businesses
(restaurants, cafés, milk tea shops, bakeries, food trays, cloud kitchens) their own white-label
online ordering store with an AI food concierge. Each business lives at `<store>.yourdomain.com`
with its own SQLite DB and 0% commission.

1. **Public Menu & Storefront (`/`)**: mobile-first menu by category, item customizer (variants,
   required/optional modifier groups, live remaining portions), cart, checkout (`dine_in` /
   `pickup` / `delivery` / `cod`, ASAP or scheduled time slot), manual payment (GCash / bank) with
   proof-of-payment upload, and a private order-tracking page (`/order/<token>`).
2. **AI Menu Concierge (customer AI)**: answers only from live DB rows (menu, prices, add-ons,
   remaining portions, delivery zones, kitchen hours, allergens), recommends available items, and
   prepares carts the customer confirms.
3. **Owner & Kitchen Admin (`/admin`)**: session-protected dashboard to verify payments, run the
   kitchen queue (Preparing → Ready → Out for Delivery → Completed), toggle 1-tap "86 / Sold Out"
   status, reset daily prep portions, view customers and sales insights, edit the storefront, and
   work with the **Kitchen Co-pilot** (owner AI) whose actions always require a tap on Confirm.

## Tech Stack & Environment (`uv`)
- **Package & runtime manager**: `uv` (Python 3.12+). Always `uv run`, `uv add`, `uv sync`.
  Never use `pip`, `poetry`, or `conda`.
- **Web**: `python-fasthtml` + HTMX + Tailwind CSS via CDN (no Node/Vite build step).
- **Database**: built-in `sqlite3`, one file per restaurant, `PRAGMA journal_mode=WAL`,
  `PRAGMA foreign_keys=ON`, autocommit connections with explicit `BEGIN IMMEDIATE` for every write
  that must be consistent. No Postgres/RDS/DynamoDB.
- **LLM**: `openai` SDK against an OpenAI-compatible endpoint via env vars `LLM_BASE_URL`,
  `LLM_API_KEY`, `LLM_MODEL` (default Groq `openai/gpt-oss-20b`, must support tool calling).
  The site must work fully with these unset: the customer chat falls back to `ai.quick_answer`
  (keyword answers + item cards from live DB rows); the owner Co-pilot says AI isn't set up.
- **Deploy**: one AWS Lightsail/EC2 1 GB instance, Docker Compose + Caddy (on-demand TLS for
  `*.BASE_DOMAIN`). Keep total container RAM under 150 MB. GitHub Actions auto-deploys on push.

## Directory Structure
```text
.
├── pyproject.toml / uv.lock
├── Dockerfile, docker-compose.yml, Caddyfile
├── deploy.sh                    # server: rebuild, prune, wait for health check
├── .github/workflows/deploy.yml # push to main/master → SSH (restricted key) → git pull + deploy.sh
├── main.py                      # app setup, tenancy, auth, route mounting
├── ui.py                        # shared FT components, design tokens, badges (86/Spicy/Best Seller), layout
├── storehome.py                # store homepage at / (hero, best sellers, menu, about, hours) → Order buttons
├── storefront.py                # menu, item customizer, cart, checkout, payment, /order/<token>
├── admin.py                     # kitchen queue tabs, menu/86 editor, insights, website editor
├── db.py                        # schema, migrations, ALL writes: portions, orders, state machine, media
├── landing.py                   # marketing page + signup form on the bare domain, "coming soon" page
├── signup.py                    # self-serve signup → new store DB → one-time login hand-off to <store>/admin
├── stores.py                    # platform owner CLI: list / activate / deactivate stores
├── ai.py                        # AI Menu Concierge + Kitchen Co-pilot (tools, prompts, proposals)
├── seed_client.py               # `uv run python seed_client.py seeds/demo-resto.json`
├── seeds/demo-resto.json        # sample café/kitchen (~12–14 items, variants, modifier groups)
├── seeds/starters.json          # starter menus per business type for self-serve signups
└── data/                        # git-ignored: <store>.db files + uploads/<store>/*
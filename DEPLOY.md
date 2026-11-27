# Deploying ServeFlow on AWS EC2

One small EC2 instance runs everything: the app container (FastHTML/uvicorn, ~110 MB) and Caddy
(HTTPS with on-demand certificates for every `<store>.BASE_DOMAIN`). All data — one SQLite file per
store plus uploads — lives in `/opt/biteflow/data` on the instance disk.

## Current deployment (demo, Nov 2026)

| | |
|---|---|
| AWS account | **Free plan** (credits only; Lightsail is blocked on this plan — see below) |
| Region / AZ | Sydney `ap-southeast-2` / `ap-southeast-2a` (the only region the Free plan allows) |
| Instance | `serveflow`, **t3.micro** (1 GB), Ubuntu 24.04 x86, 20 GiB gp3, credit spec Standard |
| Elastic IP | `16.179.248.107` |
| Security group | `launch-wizard-1`: inbound 22, 80, 443 from anywhere |
| App path | `/opt/biteflow` (owner `ubuntu`), data in `/opt/biteflow/data` |
| `BASE_DOMAIN` | `16-179-248-107.sslip.io` (no domain bought yet) |
| Stores | `demo-resto` (café), `matchacrumb` (bakery) — seeded, live |
| Auto-deploy | ✅ push to `master` → GitHub Actions → restricted SSH key → `git pull && ./deploy.sh` |
| AI | not configured (`LLM_API_KEY` empty) — chat uses keyword answers, Co-pilot says AI isn't set up |

Public links:

- Marketing page + signup: https://16-179-248-107.sslip.io
- Café: https://demo-resto.16-179-248-107.sslip.io (admin: `/admin`)
- Bakery: https://matchacrumb.16-179-248-107.sslip.io (admin: `/admin`)

Admin passwords were reset on the server to random values (not the ones in `seeds/*.json`) and are
kept outside the repo.

> **Why EC2 and not Lightsail?** Free plan accounts can only create resources in one region and hit
> a vCPU quota error when creating a Lightsail instance. EC2 runs on the plan's credits instead. On a
> paid account, Lightsail ($7/mo, 1 GB) works with the same steps from section 3 onward.

---

## Costs

Standard on-demand prices in Sydney (`ap-southeast-2`):

| Item | Per month |
|---|---|
| EC2 t3.micro (on 24/7) | ~$9.60 |
| 20 GiB gp3 EBS volume | ~$1.90 |
| Public IPv4 / Elastic IP | ~$3.60 |
| Data transfer out | $0 (first 100 GB/month free) |
| sslip.io, Let's Encrypt certs, GitHub Actions (public repo) | $0 |
| **Total** | **~$15/month (≈ ₱850–900)** |

- **Out of pocket right now: $0.** The Free plan's credits ($100 at signup, up to $100 more for
  AWS's getting-started activities, valid 6 months) pay for it — roughly 6 months of runtime.
- When credits or the 6-month period run out, AWS **stops** the resources unless the account is
  upgraded; Free plan accounts are not charged automatically. After upgrading: ~$15/month.
- Check the real numbers in **Billing and Cost Management → Credits** (balance, expiry) and
  **→ Bills** (actual daily cost).
- Optional extras: daily EBS snapshots (a few cents/month for a mostly-unchanged 20 GB volume),
  a real domain (~$10/year for `.com`).
- An Elastic IP is billed while allocated, **attached or not** — release it if you delete the
  instance.

---

## 1. Launch the instance (EC2 console → Launch instance)

| Field | Value |
|---|---|
| Name | `serveflow` |
| AMI | **Ubuntu Server 24.04 LTS (64-bit x86)** |
| Instance type | **t3.micro** (2 vCPU burstable, 1 GB RAM) |
| Key pair | Create new, ED25519, `.pem` (optional — EC2 Instance Connect works without it) |
| Network | Allow SSH, ✅ Allow HTTPS, ✅ Allow HTTP |
| Storage | **20 GiB gp3** (8 GiB fills up with Docker images) |
| File systems | **None** (SQLite WAL must not live on EFS/S3/FSx) |
| Advanced → Credit specification | **Standard** (Unlimited can bill for CPU bursts) |
| Advanced → User data | optional — see note below |

Wait until the instance is **Running** with status checks passed.

> **Note:** a User data launch script was intended here but **did not run** on the current
> instance (Docker wasn't installed, repo not cloned). The setup in section 4 does everything by
> hand and is safe to re-run, so User data is not needed.

## 2. Give it a fixed IP (Elastic IP)

The default public IP changes on every stop/start, which would break the links.

1. EC2 → **Network & Security → Elastic IPs** → **Allocate Elastic IP address** → defaults
   (Amazon's pool, `ap-southeast-2`) → Allocate.
2. Select it → **Actions → Associate Elastic IP address** → Instance → `serveflow` → Associate.

Use this IP everywhere below (`<IP>`, currently `16.179.248.107`).

## 3. Domain

- **No domain yet (current setup, $0):** [sslip.io](https://sslip.io) resolves any
  `*.<ip-with-dashes>.sslip.io` name to that IP, so no DNS setup is needed:
  `BASE_DOMAIN=16-179-248-107.sslip.io` → stores at `https://<store>.16-179-248-107.sslip.io`.
- **Real domain (for paying customers):** at your DNS provider add
  ```
  A   @   <IP>
  A   *   <IP>
  ```
  then on the server set `BASE_DOMAIN=yourdomain.com` and a real `ACME_EMAIL` in `.env`, and run
  `sudo ./deploy.sh`. Store links change to `https://<store>.yourdomain.com`.

## 4. Install and start the app

Connect: EC2 → Instances → `serveflow` → **Connect → EC2 Instance Connect** → user `ubuntu` →
Connect (a terminal opens in the browser).

Paste this whole block (replace the IP in the `sed` line for a different instance). Every step
skips itself if already done:

```bash
[ -f /swapfile ] || { sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab; }
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo mkdir -p /opt/biteflow && sudo chown ubuntu:ubuntu /opt/biteflow
[ -d /opt/biteflow/.git ] || git clone https://github.com/dmarcllanes/serveflow.git /opt/biteflow
cd /opt/biteflow && mkdir -p data
[ -f .env ] || cp .env.example .env
sed -i "s|^BASE_DOMAIN=.*|BASE_DOMAIN=16-179-248-107.sslip.io|; s|^ACME_EMAIL=.*|ACME_EMAIL=admin@16-179-248-107.sslip.io|; s|^SESSION_SECRET=change-me.*|SESSION_SECRET=$(openssl rand -hex 32)|" .env
sudo ./deploy.sh
```

`deploy.sh` builds the image (~35 s on t3.micro), starts both containers, and ends with
`Waiting for app health ✓`.

- `mkdir -p data` as `ubuntu` matters: the container runs as uid 1000 (= `ubuntu`) and must be
  able to write there.
- `ACME_EMAIL` is a placeholder; Let's Encrypt accepted it. Use a real address with a real domain.
- Optional AI: `nano .env` → set `LLM_API_KEY=` (Groq), then `sudo ./deploy.sh`.

## 5. Stores

```bash
cd /opt/biteflow

# sample stores (refuses to touch an existing store unless --reset, which DESTROYS its orders)
sudo docker compose exec app .venv/bin/python seed_client.py seeds/demo-resto.json
sudo docker compose exec app .venv/bin/python seed_client.py seeds/matcha-bakery.json

# self-serve signups start as "coming soon" — go live after the setup fee
sudo docker compose exec app .venv/bin/python stores.py list
sudo docker compose exec app .venv/bin/python stores.py activate <store>
```

**Change admin passwords** without touching store data (prints new random passwords once — save
them; the seed passwords are public in this repo):

```bash
cd /opt/biteflow && sudo docker compose exec -T app .venv/bin/python - <<'PY'
import secrets, db
for store in ("demo-resto", "matchacrumb"):
    pw = "-".join(secrets.token_urlsafe(4) for _ in range(3))
    db.set_admin_password(db.get_db(store), pw)
    print(f"{store:12}  new admin password:  {pw}")
PY
```

Owners can also change their password in **Admin → Website**.

The first request to each new hostname takes a few seconds while Caddy obtains its certificate.

## 6. Auto-deploy from GitHub (done)

How it was set up — the private key was generated on a laptop, stored only in GitHub secrets, then
deleted locally; it never touched the server:

```bash
# on the laptop (gh logged in)
ssh-keygen -q -t ed25519 -N '' -C deploy@gha -f ./gha_deploy
ssh-keyscan 16.179.248.107 > ./known_hosts
gh secret set DEPLOY_SSH_KEY     -R dmarcllanes/serveflow < ./gha_deploy
gh secret set DEPLOY_KNOWN_HOSTS -R dmarcllanes/serveflow < ./known_hosts
gh secret set DEPLOY_HOST        -R dmarcllanes/serveflow -b 16.179.248.107
gh secret set DEPLOY_USER        -R dmarcllanes/serveflow -b ubuntu
cat ./gha_deploy.pub   # → goes into the server line below
rm ./gha_deploy ./gha_deploy.pub ./known_hosts
```

```bash
# on the server: allow that key to run ONLY the deploy command
echo 'command="cd /opt/biteflow && git pull --ff-only && ./deploy.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... deploy@gha' >> ~/.ssh/authorized_keys
```

Every push to `main`/`master` now runs `.github/workflows/deploy.yml`: import check → SSH →
`git pull` + `./deploy.sh` (~25 s). Run it manually from **Actions → Deploy → Run workflow**, or
`gh workflow run deploy.yml -R dmarcllanes/serveflow --ref master`.

If the new version fails to build, the old one keeps running; if it builds but never becomes
healthy, the site is down until a fix is pushed (the Actions log shows the app's last 80 log lines).

## 7. Operations

Runs 24/7: the instance stays on until stopped, both containers are `restart: unless-stopped`, and
Docker starts on boot, so the site comes back by itself after crashes or reboots. Certificates renew
automatically.

```bash
cd /opt/biteflow
sudo docker compose ps                       # both Up, app (healthy)
sudo docker compose logs -f --tail=100 app   # app logs (caddy: ... logs caddy)
sudo docker stats --no-stream                # RAM: app < 110 MB, caddy < 40 MB
free -h && df -h /                           # memory/swap and disk
git pull && sudo ./deploy.sh                 # manual deploy
```

Health check URL (e.g. for a free UptimeRobot monitor):
`https://demo-resto.16-179-248-107.sslip.io/healthz`

### Backups

Everything that matters is `/opt/biteflow/data` (store DBs, uploads, `signups.jsonl`) plus `.env`.
Two layers:

**1. Daily copies on the server** (set up, Nov 2026). `backup.sh` copies every store DB with
SQLite's online backup API (safe while orders come in), checks each copy with
`PRAGMA integrity_check`, adds `uploads.tar.gz` and `.env`, and keeps the newest 14 in
`/opt/serveflow-backups/<date>_<time>/` (owner-only permissions). Cron runs it at 3:15 AM Manila
(19:15 UTC) and logs to `/opt/serveflow-backups/backup.log`:

```bash
# installed with: crontab -e  (user ubuntu)
15 19 * * * /opt/biteflow/backup.sh >> /opt/serveflow-backups/backup.log 2>&1
```

```bash
/opt/biteflow/backup.sh                        # back up now (writes to /opt/serveflow-backups)
ls /opt/serveflow-backups                      # one folder per run; *_FAILED = that run failed
tail /opt/serveflow-backups/backup.log         # last runs
```

These protect against a bad command, a bad deploy or a corrupted file. They do **not** survive
losing the instance or its disk, which is what layer 2 is for.

**2. Daily EBS snapshots (off the instance).** EC2 → **Elastic Block Store → Lifecycle Manager →
Create lifecycle policy** → EBS snapshot policy, target the `serveflow` instance's volume, every
24 hours at 20:00 UTC (after the cron copy), retain 7. Snapshots are incremental, so a few GB
costs cents per month.

**Restore one store** (e.g. `demo-resto` from a backup folder):

```bash
cd /opt/biteflow
sudo docker compose stop app
cp data/demo-resto.db data/demo-resto.db.before-restore      # keep the current one, just in case
rm -f data/demo-resto.db-wal data/demo-resto.db-shm
cp /opt/serveflow-backups/<folder>/demo-resto.db data/
sudo docker compose start app
```

Uploads: `tar -xzf /opt/serveflow-backups/<folder>/uploads.tar.gz -C data`.

### Stopping and starting the instance (to save money)

You can **Stop** the instance when nobody needs the site and **Start** it later; the same links
work again with no setup:

- **Same address:** the Elastic IP stays attached through stop/start, so every
  `*.16-179-248-107.sslip.io` link keeps pointing at the instance. (Without an Elastic IP the
  public IP would change and break the links.)
- **Starts itself:** Docker starts on boot and both containers are `restart: unless-stopped`, so no
  SSH or `deploy.sh` is needed after Start.
- **Data kept:** `/opt/biteflow/data` (store DBs, uploads) lives on the EBS volume, which survives a
  stop. Only **Terminate** deletes it.

Things to know:

- While stopped, the site is unreachable (no orders, no admin). After Start, allow ~1–2 minutes,
  then check `https://demo-resto.16-179-248-107.sslip.io/healthz`.
- Stopped still costs ~$5.50/month (EBS ~$1.90 + Elastic IP ~$3.60); only the ~$9.60 compute
  charge stops.
- **Don't release the Elastic IP** — a new one means new links.
- A push to `master` while stopped fails the GitHub Actions deploy (SSH can't connect); re-run the
  job or push again after Start.
- **Never Terminate** unless you're done with it — that deletes the disk.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` / `/opt/biteflow` missing | run the section 4 block |
| `docker: permission denied` | use `sudo docker ...`, or reconnect so the `docker` group applies |
| `./deploy.sh` → "Missing .env" | `cp .env.example .env` and fill it |
| app never healthy | `sudo docker compose logs --tail=80 app` (usually a bad `.env` value) |
| Build killed / very slow | swap missing — `free -h`; re-run the swap line of section 4 |
| Browser certificate error | DNS not pointing at `<IP>`, port 443 not open, or the store doesn't exist (Caddy only issues certs for existing stores) |
| Site unreachable | instance stopped, or security group missing inbound TCP 80/443 from `0.0.0.0/0` |
| GitHub deploy fails at SSH | check the four secrets; `DEPLOY_KNOWN_HOSTS` must be for the Elastic IP; the `authorized_keys` line must be present |
| `seed_client.py` says the store already exists | intended — use the password snippet above, or `--reset` only if wiping orders is OK |

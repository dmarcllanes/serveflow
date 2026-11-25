# Deploying BiteFlow on AWS EC2

One small EC2 instance runs everything: the app container (FastHTML/uvicorn, ~110 MB) and Caddy
(HTTPS with on-demand certificates for every `<store>.BASE_DOMAIN`). All data — one SQLite file per
store plus uploads — lives in `/opt/biteflow/data` on the instance disk.

> Why EC2 and not Lightsail? AWS **Free plan** accounts can't create Lightsail instances (vCPU quota
> 0, single allowed region), but EC2 runs on the plan's credits at $0 out of pocket. On a paid account
> Lightsail ($7/mo, 1 GB) works with the exact same steps from section 3 onward.

---

## 1. Launch the instance (EC2 console → Launch instance)

| Field | Value |
|---|---|
| Name | `biteflow` |
| AMI | **Ubuntu Server 24.04 LTS (64-bit x86)** |
| Instance type | **t3.micro** (2 vCPU burstable, 1 GB RAM) |
| Key pair | Create new → `biteflow`, ED25519, `.pem` (keep the file safe) |
| Network | Allow SSH (Anywhere or My IP), ✅ Allow HTTPS, ✅ Allow HTTP |
| Storage | **20 GiB gp3** (8 GiB fills up with Docker images) |
| File systems | **None** (SQLite WAL must not live on EFS/S3/FSx) |
| Advanced → Credit specification | **Standard** (Unlimited can bill for CPU bursts) |
| Advanced → User data | launch script below |

Launch script (runs once as root on first boot):

```bash
#!/bin/bash
set -e
# 1 GB swap so docker builds don't run out of memory
fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
# Docker + compose plugin
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu
# App code
mkdir -p /opt/biteflow
git clone https://github.com/dmarcllanes/serveflow.git /opt/biteflow
chown -R ubuntu:ubuntu /opt/biteflow
```

Wait until the instance is **Running** with **2/2 status checks passed**.

## 2. Give it a fixed IP (Elastic IP)

The default public IP changes on every stop/start, which would break DNS.

1. EC2 → **Network & Security → Elastic IPs** → **Allocate Elastic IP address** → Allocate.
2. Select it → **Actions → Associate Elastic IP address** → instance `biteflow` → Associate.

Use this Elastic IP everywhere below (`<IP>`). An Elastic IP attached to a running instance costs
the same as the normal public IPv4 (~$3.60/mo, covered by credits); a **detached** one is billed
for nothing, so release it if you delete the instance.

## 3. Domain

Pick one:

- **Real domain** (for customers): at your DNS provider add
  ```
  A   @   <IP>
  A   *   <IP>
  ```
  and use `BASE_DOMAIN=yourdomain.com`.
- **No domain yet** (demos, $0): use [sslip.io](https://sslip.io), which resolves any
  `*.<ip-with-dashes>.sslip.io` name to that IP. No DNS setup:
  `BASE_DOMAIN=13-55-123-45.sslip.io` → stores at `https://demo-resto.13-55-123-45.sslip.io`.
  Let's Encrypt rate limits are shared per sslip.io name, fine for a handful of stores.

## 4. Configure and start the app

Connect: EC2 → instance → **Connect → EC2 Instance Connect** (browser), or from your Mac:

```bash
chmod 400 ~/Downloads/biteflow.pem
ssh -i ~/Downloads/biteflow.pem ubuntu@<IP>
```

Check the launch script finished (Docker installed, repo cloned):

```bash
docker --version && ls /opt/biteflow     # if missing: sudo tail -50 /var/log/cloud-init-output.log
```

If `docker` gives "permission denied", log out and back in (group change from the launch script).

```bash
cd /opt/biteflow
cp .env.example .env
sed -i "s|^SESSION_SECRET=.*|SESSION_SECRET=$(openssl rand -hex 32)|" .env
nano .env       # BASE_DOMAIN, ACME_EMAIL; optional LLM_API_KEY, CONTACT_URL, DEFAULT_STORE
./deploy.sh     # builds, starts, waits for "Waiting for app health ✓"
```

## 5. Create stores

```bash
# sample stores
docker compose exec app .venv/bin/python seed_client.py seeds/demo-resto.json
docker compose exec app .venv/bin/python seed_client.py seeds/matcha-bakery.json

# go live after the setup fee (self-serve signups start as "coming soon")
docker compose exec app .venv/bin/python stores.py list
docker compose exec app .venv/bin/python stores.py activate <store>
```

- Marketing page + signup: `https://<BASE_DOMAIN>`
- Store: `https://<store>.<BASE_DOMAIN>`, admin at `/admin`

The first request to each new hostname takes a few seconds while Caddy obtains its certificate.

## 6. Auto-deploy from GitHub

On the server, create a key that can **only** trigger a deploy:

```bash
ssh-keygen -t ed25519 -N '' -C deploy@gha -f ~/gha_deploy
echo "command=\"cd /opt/biteflow && git pull --ff-only && ./deploy.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat ~/gha_deploy.pub)" >> ~/.ssh/authorized_keys
cat ~/gha_deploy                                                  # → DEPLOY_SSH_KEY
ssh-keyscan localhost 2>/dev/null | sed "s/^localhost/<IP>/"      # → DEPLOY_KNOWN_HOSTS
rm ~/gha_deploy ~/gha_deploy.pub
```

GitHub → repo **Settings → Secrets and variables → Actions** → New repository secret:

| Secret | Value |
|---|---|
| `DEPLOY_SSH_KEY` | private key printed above (including the BEGIN/END lines) |
| `DEPLOY_HOST` | `<IP>` |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_KNOWN_HOSTS` | keyscan output with your IP |

Every push to `main`/`master` now runs `.github/workflows/deploy.yml`: import check → SSH →
`git pull` + `./deploy.sh`. Re-run manually from the Actions tab (`workflow_dispatch`).

## 7. Operations

```bash
cd /opt/biteflow
docker compose ps                       # both containers Up, app (healthy)
docker compose logs -f --tail=100 app   # app logs (caddy: ... logs caddy)
docker stats --no-stream                # RAM: app < 110 MB, caddy < 40 MB
free -h && df -h /                      # memory/swap and disk
```

**Backups** — everything that matters is `/opt/biteflow/data` (+ `.env`):

- EC2 → **Elastic Block Store → Lifecycle Manager** → create a daily EBS snapshot policy for the
  instance's volume (keep ~7), or
- copy it off the box: `scp -i biteflow.pem -r ubuntu@<IP>:/opt/biteflow/data ./backup-$(date +%F)`
  (SQLite in WAL mode: copy while idle, or use `sqlite3 <db> ".backup out.db"` for a hot copy).

**Costs on the Free plan** — t3.micro + 20 GB gp3 + public IPv4 ≈ $15/mo in Sydney, paid from the plan's
credits. Check **Billing → Credits** occasionally; when credits or the plan period run out, AWS asks
you to upgrade (Free plan accounts are not charged automatically).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` after boot | launch script failed — `sudo tail -100 /var/log/cloud-init-output.log`, run its commands manually with `sudo` |
| `./deploy.sh` → "Missing .env" | `cp .env.example .env` and fill it |
| app never healthy | `docker compose logs --tail=80 app` (usually a bad `.env` value) |
| Build killed / very slow | swap missing — `free -h`; re-run the swap lines of the launch script |
| Browser certificate error | DNS not pointing at `<IP>` yet, port 443 not open in the security group, or the store doesn't exist (Caddy only issues certs for existing stores) |
| Site unreachable | security group must allow inbound TCP 80 and 443 from `0.0.0.0/0` |
| GitHub deploy fails at SSH | check the four secrets; `DEPLOY_KNOWN_HOSTS` must contain the Elastic IP, not `localhost` |

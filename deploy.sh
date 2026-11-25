#!/usr/bin/env bash
# Server-side deploy: rebuild, restart, prune, wait for the health check.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "Missing .env (copy .env.example)"; exit 1; }
mkdir -p data

docker compose build app
docker compose up -d --remove-orphans
docker image prune -f >/dev/null

echo -n "Waiting for app health"
for _ in $(seq 1 40); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q app)" 2>/dev/null || echo starting)
  if [ "$status" = "healthy" ]; then echo " ✓"; docker compose ps; exit 0; fi
  echo -n "."; sleep 3
done
echo " ✗ app did not become healthy"
docker compose logs --tail=80 app
exit 1

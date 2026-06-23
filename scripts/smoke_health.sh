#!/usr/bin/env bash
set -euo pipefail
COMPOSE="deploy/docker-compose.yml"
echo "[smoke] starting stack..."
docker compose -f "$COMPOSE" up -d
echo "[smoke] waiting for healthchecks (single-4090: services come up serially)..."
deadline=$((SECONDS+600))
while [ $SECONDS -lt $deadline ]; do
  unhealthy=$(docker compose -f "$COMPOSE" ps --format '{{.Name}} {{.Health}}' | grep -E 'starting|unhealthy' || true)
  if [ -z "$unhealthy" ]; then echo "[smoke] all healthy"; exit 0; fi
  sleep 10
done
echo "[smoke] TIMEOUT — still unhealthy:"; docker compose -f "$COMPOSE" ps
exit 1

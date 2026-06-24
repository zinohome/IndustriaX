#!/usr/bin/env bash
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
# Images referenced directly in compose, plus the base images of every service we
# build locally (e.g. apache/age under Dockerfile.postgres, python under Dockerfile.mcp),
# so the offline bundle is self-contained even for built services.
COMPOSE_IMAGES=$(grep -E '^\s+image:' deploy/docker-compose.yml | awk '{print $2}')
BASE_IMAGES=$(grep -hE '^FROM ' deploy/Dockerfile.* | awk '{print $2}')
IMAGES=$(printf '%s\n%s\n' "$COMPOSE_IMAGES" "$BASE_IMAGES" | sort -u)
MODELS="qwen3.5:9b qwen3-embedding:8b bge-m3 bge-reranker-v2-m3"
echo "== images to bundle =="; echo "$IMAGES"
echo "== model weights to bundle =="; echo "$MODELS"
if [ "$DRY" = "1" ]; then exit 0; fi
mkdir -p dist/images
for img in $IMAGES; do docker pull "$img"; done
docker save $IMAGES -o dist/images/industriax-images.tar
echo "$IMAGES" > dist/manifest-images.txt
echo "$MODELS" > dist/manifest-models.txt
echo "[offline] bundle written to dist/"

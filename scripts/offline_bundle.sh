#!/usr/bin/env bash
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
IMAGES=$(grep -E '^\s+image:' deploy/docker-compose.yml | awk '{print $2}')
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

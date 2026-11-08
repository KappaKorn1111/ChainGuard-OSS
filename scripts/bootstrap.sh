#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Review and replace all change-this-* values before shared or production use."
fi

docker compose build
docker compose up -d postgres redis dtrack-postgres dependency-track-api
docker compose run --rm migrate
docker compose up -d
echo "ChainGuard OSS is starting. Run ./scripts/verify.sh when services are healthy."

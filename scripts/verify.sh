#!/usr/bin/env sh
set -eu

API_URL="${API_URL:-http://localhost:8000}"
UI_URL="${UI_URL:-http://localhost:3000}"
DTRACK_URL="${DTRACK_URL:-http://localhost:8082}"

docker compose config --quiet
curl --fail --silent --show-error "$API_URL/health/live" >/dev/null
curl --fail --silent --show-error "$API_URL/health/ready" >/dev/null
curl --fail --silent --show-error "$UI_URL/" >/dev/null
curl --fail --silent --show-error "$DTRACK_URL/health" >/dev/null

echo "Compose configuration and service health checks passed."

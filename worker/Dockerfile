FROM anchore/syft:v1.57.0 AS syft
FROM anchore/grype:v0.121.2 AS grype
FROM golang:1.25.4-bookworm AS protobom
RUN go install github.com/protobom/sbom-convert@v0.0.7

FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    GRYPE_DB_CACHE_DIR=/data/grype-db

RUN useradd --create-home --uid 10001 scanner
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
COPY --from=syft /syft /usr/local/bin/syft
COPY --from=grype /grype /usr/local/bin/grype
COPY --from=protobom /go/bin/sbom-convert /usr/local/bin/sbom-convert
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen --no-dev

COPY backend ./backend
COPY worker ./worker
RUN mkdir -p /data/uploads /data/grype-db \
    && chown -R scanner:scanner /app /data

USER scanner
CMD ["celery", "--app", "worker.tasks:app", "worker", "--loglevel=INFO", "--concurrency=2"]

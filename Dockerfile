FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
COPY harness.yaml ./
COPY --from=frontend /frontend/dist ./frontend/dist
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    HARNESS_HOST=0.0.0.0 \
    HARNESS_OPEN_BROWSER=false \
    HARNESS_CACHE_DIR=/data/cache

EXPOSE 8000
CMD ["harness"]

# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS frontend-build

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY index.html tsconfig.json vite.config.ts eslint.config.js prettier.config.js ./
COPY public ./public
COPY src ./src

ARG VITE_API_BASE_URL
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}

RUN npm run build


FROM caddy:2-alpine AS web

COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend-build /app/dist/client /srv


FROM python:3.11-slim-bookworm AS backend-build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

COPY backend/pyproject.toml backend/uv.lock backend/astrology-runtime.lock ./backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project backend --no-install-project

COPY backend/app ./backend/app
COPY scripts/setup-backend-runtime.py ./scripts/setup-backend-runtime.py
RUN --mount=type=cache,target=/root/.cache/pip \
    backend/.venv/bin/python scripts/setup-backend-runtime.py


FROM python:3.11-slim-bookworm AS backend

ARG VEDICSIGN_UID=10001
ARG VEDICSIGN_GID=10001

ENV HOME=/home/vedicsign \
    NODE_ENV=production \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    PATH=/app/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin

WORKDIR /app

RUN groupadd --gid "${VEDICSIGN_GID}" vedicsign \
    && useradd --uid "${VEDICSIGN_UID}" --gid "${VEDICSIGN_GID}" \
      --create-home --home-dir /home/vedicsign --shell /usr/sbin/nologin vedicsign

# Copy Node/npm from the official Node image so PDF rendering uses the same locked
# Playwright package as the application. Playwright installs the required Debian
# browser libraries in this runtime stage.
COPY --from=node:20-bookworm-slim /usr/local/ /usr/local/

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev \
    && npx playwright install --with-deps chromium \
    && npm cache clean --force

COPY --from=backend-build /app/backend/.venv ./backend/.venv
COPY . .

RUN mkdir -p /app/backend/data/sessions /home/vedicsign/.cache \
    && chown -R vedicsign:vedicsign /app/backend/data /home/vedicsign \
    && backend/.venv/bin/python scripts/setup-backend-runtime.py --check-only

USER vedicsign

EXPOSE 8787

ENTRYPOINT ["/app/scripts/production/container-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787", "--workers", "1", "--no-access-log"]

# ---------------------------------------------------------------
# LAMA — Legacy Application Modernisation AI Studio
# Single-image bundle (frontend + backend + MongoDB + Nginx).
#
# Public port: 8382 (configurable at runtime by remapping)
# Persisted state: /data/db   (mount a host volume for MongoDB)
# External services: Qdrant (HTTP)  — pass QDRANT_URL/QDRANT_API_KEY env-vars
# Push: docker push mishramesh/lama:latest
# ---------------------------------------------------------------

# ===============================================================
# Stage 1 — build React frontend
# ===============================================================
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /build
# Do NOT set NODE_ENV=production here — it would make yarn install skip
# devDependencies (craco, eslint, etc.) and yarn build would then fail with
# "craco: not found". craco/CRA set NODE_ENV=production internally at build time.
ENV DISABLE_ESLINT_PLUGIN=true \
    GENERATE_SOURCEMAP=false \
    CI=false \
    REACT_APP_BACKEND_URL=""

# Cache yarn install layer.
# Note: yarn.lock is optional — the wildcard makes the COPY succeed even
# if the lockfile isn't tracked in git. Commit yarn.lock for reproducible
# CI builds.
COPY frontend/package.json frontend/yarn.lock* ./
RUN corepack enable && \
    if [ -f yarn.lock ]; then \
        yarn install --frozen-lockfile --network-timeout 600000; \
    else \
        echo "[lama] yarn.lock not found — falling back to fresh resolve"; \
        yarn install --network-timeout 600000; \
    fi

# Build (craco internally sets NODE_ENV=production)
COPY frontend/ ./
RUN yarn build

# ===============================================================
# Stage 2 — runtime image (Python + Mongo + Nginx + supervisord)
# ===============================================================
FROM python:3.11-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC

# Install MongoDB 7, Nginx, supervisord, curl, gnupg
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release \
        nginx supervisor tzdata; \
    rm -rf /var/lib/apt/lists/*

# MongoDB 7 GA from official repo (Debian 12 / bookworm)
RUN set -eux; \
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] http://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main" \
        > /etc/apt/sources.list.d/mongodb-org-7.0.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends mongodb-org-server mongodb-mongosh; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /data/db /var/log/mongodb /var/log/supervisor; \
    id mongodb >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin mongodb; \
    chown -R mongodb:mongodb /data/db /var/log/mongodb

# ---------- Python backend ----------
WORKDIR /app/backend
COPY backend/requirements.txt ./

# Install CPU-only PyTorch first (saves ~700 MB vs the default CUDA build,
# and drops the triton GPU dep entirely). When pip later processes
# requirements.txt, the existing torch==2.12.0 install satisfies the pin and
# the CUDA wheel is NOT re-pulled.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.12.0 && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir 'uvicorn[standard]'

COPY backend/ /app/backend/

# Drop the dev .env (real values come from -e flags at runtime via entrypoint.sh)
RUN rm -f /app/backend/.env

# ---------- React build output served by nginx ----------
COPY --from=frontend-build /build/build/ /usr/share/nginx/html/

# ---------- Nginx + supervisord configs ----------
COPY docker/nginx.conf      /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/entrypoint.sh    /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf || true

# Persist MongoDB data on a host volume
VOLUME ["/data/db"]

# Public port: 8382 (the only port exposed by the image)
EXPOSE 8382

# Healthcheck — passes once Nginx is up and /api/health returns 200
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8382/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]

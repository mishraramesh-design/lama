#!/usr/bin/env bash
# Container entrypoint for LAMA single-image bundle.
# - Ensures /data/db exists (MongoDB needs it as a volume)
# - Writes a runtime backend .env from env-vars passed at `docker run -e ...`
# - Hands control to supervisord which runs mongo + backend + nginx

set -e

DATA_DIR="${MONGO_DATA_DIR:-/data/db}"
mkdir -p "$DATA_DIR" /var/log/supervisor
chown -R mongodb:mongodb "$DATA_DIR" || true

# ---- Runtime .env for the FastAPI backend ----
cat > /app/backend/.env <<EOF
MONGO_URL=${MONGO_URL:-mongodb://127.0.0.1:27017}
DB_NAME=${DB_NAME:-lama}
OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
OPENROUTER_BASE_URL=${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}
QDRANT_URL=${QDRANT_URL:-}
QDRANT_API_KEY=${QDRANT_API_KEY:-}
LAMA_DEFAULT_MODEL=${LAMA_DEFAULT_MODEL:-deepseek/deepseek-chat}
EOF

echo "[lama] starting bundle (mongo + backend + nginx) on port 8382"
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf

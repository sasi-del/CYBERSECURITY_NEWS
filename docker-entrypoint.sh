#!/usr/bin/env bash
set -e

# ── Forward env vars into the cron shell ──────────────────────────
printenv | grep -E '^(GEMINI_API_KEY|OPENROUTER_API_KEY|OPENROUTER_MODEL|AI_PROVIDER|COLLECT_CRON|BULLETIN_CRON|PORT|WORKERS|TZ)=' \
    > /etc/environment 2>/dev/null || true

# ── Defaults ──────────────────────────────────────────────────────
COLLECT_CRON="${COLLECT_CRON:-30 7 * * 1-5}"
BULLETIN_CRON="${BULLETIN_CRON:-45 7 * * 1-5}"
PORT="${PORT:-8080}"
WORKERS="${WORKERS:-4}"

# ── Write crontab ────────────────────────────────────────────────
cat > /etc/cron.d/bulletin <<EOF
SHELL=/bin/bash
BASH_ENV=/etc/environment

${COLLECT_CRON} root cd /app && python scripts/collect_news.py >> /app/logs/cron.log 2>&1
${BULLETIN_CRON} root cd /app && python scripts/generate_bulletin_data.py >> /app/logs/cron.log 2>&1
EOF

chmod 0644 /etc/cron.d/bulletin
crontab /etc/cron.d/bulletin

# ── Initial data fetch if data/news_latest.json is missing ───────
if [ ! -f /app/data/news_latest.json ]; then
    echo "[entrypoint] No feed data found — running initial collection..."
    python scripts/collect_news.py 2>&1 | tail -3
    python scripts/generate_bulletin_data.py 2>&1 | tail -3
fi

# ── Start cron daemon in background ──────────────────────────────
cron

echo "[entrypoint] Cron started | Gunicorn ${WORKERS}w on :${PORT}"

# ── Launch gunicorn (PID 1 via tini) ─────────────────────────────
exec gunicorn \
    --workers "${WORKERS}" \
    --bind "0.0.0.0:${PORT}" \
    --chdir scripts \
    --access-logfile /app/logs/access.log \
    --error-logfile  /app/logs/error.log \
    --timeout 120 \
    bulletin_server:app

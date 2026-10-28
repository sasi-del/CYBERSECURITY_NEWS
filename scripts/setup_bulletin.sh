#!/bin/bash
# ===========================================================================
# setup_bulletin.sh
# Run this ONCE on your Kali laptop to install dependencies and set up cron.
# Usage: bash setup_bulletin.sh
# ===========================================================================

set -euo pipefail

PROJECT="/home/test/awesome-cybersecurity-feeds"
PYTHON="python3"

echo "🛡️  Cyber Bulletin Setup"
echo "========================="

# 1. Install Python deps system-wide (Kali)
echo ""
echo "📦 Installing dependencies..."
pip3 install --break-system-packages -q flask google-genai
echo "✅ Dependencies installed."

# 2. Create logs dir
mkdir -p "$PROJECT/logs"

# 3. Copy new scripts into project
echo ""
echo "📂 Installing scripts into $PROJECT/scripts/ ..."
STAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$STAGING_DIR/bulletin_server.py"        "$PROJECT/scripts/bulletin_server.py"
cp "$STAGING_DIR/generate_bulletin_data.py" "$PROJECT/scripts/generate_bulletin_data.py"
echo "✅ Scripts installed."

# 4. Write cron jobs
echo ""
echo "⏰ Installing cron jobs..."
CRON_COLLECT="30 7 * * 1-5 cd $PROJECT && $PYTHON scripts/collect_news.py >> $PROJECT/logs/cron.log 2>&1"
CRON_PROCESS="45 7 * * 1-5 cd $PROJECT && $PYTHON scripts/generate_bulletin_data.py >> $PROJECT/logs/cron.log 2>&1"
CRON_SERVER="@reboot cd $PROJECT && $PYTHON scripts/bulletin_server.py >> $PROJECT/logs/server.log 2>&1 &"

( crontab -l 2>/dev/null | grep -v "bulletin_"; \
  echo "$CRON_COLLECT"; \
  echo "$CRON_PROCESS"; \
  echo "$CRON_SERVER" ) | crontab -

echo "✅ Cron jobs installed:"
echo "   07:30 AM Mon-Fri → collect_news.py"
echo "   07:45 AM Mon-Fri → generate_bulletin_data.py"
echo "   On reboot        → bulletin_server.py"

# 5. Start the dashboard now
echo ""
echo "🚀 Starting dashboard on http://localhost:5000 ..."
cd "$PROJECT"
nohup $PYTHON scripts/bulletin_server.py >> logs/server.log 2>&1 &
DASH_PID=$!
sleep 1
if kill -0 $DASH_PID 2>/dev/null; then
    echo "✅ Server running (PID $DASH_PID) — open http://localhost:5000"
else
    echo "⚠️  Server may have failed — check logs/server.log"
fi

echo ""
echo "🛡️  Done! Dashboard is live."

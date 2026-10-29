# 🛡️ CYBERSECURITY_NEWS

**Private Internal Cybersecurity Intelligence Dashboard**

> Every morning, your team starts the day informed. Automatically.

---

## What It Does

Aggregates **700+ articles daily** from BleepingComputer, CVEfeed, OSS-Security, The Hacker News, Seclists, and more — scores them by severity and organisational relevance, clusters related CVEs, and serves a live internal web dashboard.

```
http://your-internal-server:8080
```

---

## System Architecture

```
07:30 AM  collect_news.py          →  data/news_latest.json  (700+ raw articles)
07:45 AM  generate_bulletin_data.py →  data/bulletin_cache.json  (scored + AI summary)
08:00 AM  Intern reviews dashboard   →  reports/cyber_bulletin_YYYY-MM-DD.md
08:45 AM  Post to Slack/Teams        →  reports/cyber_bulletin_YYYY-MM-DD_slack.txt
          bulletin_server.py         →  http://server:8080  (always running)
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/sasi-del/CYBERSECURITY_NEWS.git
cd CYBERSECURITY_NEWS

# 2. Install dependencies
pip3 install --break-system-packages flask google-genai gunicorn

# 3. Fetch today's feeds
python3 scripts/collect_news.py

# 4. Generate bulletin + AI summary (optional: set GEMINI_API_KEY)
export GEMINI_API_KEY="your-key-here"
python3 scripts/generate_bulletin_data.py

# 5. Start the dashboard
python3 scripts/bulletin_server.py
# Open http://localhost:8080
```

---

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/collect_news.py` | Fetches all RSS/Atom feeds → `data/news_latest.json` |
| `scripts/bulletin_server.py` | Flask web dashboard with severity scoring, CVE clustering, search & filter |
| `scripts/generate_bulletin_data.py` | Scores articles + generates Gemini AI executive summary |
| `scripts/generate_internal_bulletin.py` | Generates Markdown + Slack bulletin files |
| `scripts/setup_bulletin.sh` | One-shot installer: deps + cron + server launch |
| `scripts/check_feeds.py` | Feed health checker |
| `scripts/validate_sources.py` | Source validator |
| `scripts/report_health.py` | Health report generator |

---

## Deploy on Internal Server (Production)

```bash
# Install gunicorn for multi-user production serving
pip3 install --break-system-packages gunicorn

# Run with 4 workers on port 8080
cd /opt/CYBERSECURITY_NEWS
gunicorn --workers 4 --bind 0.0.0.0:8080 \
         --chdir scripts bulletin_server:app \
         --daemon \
         --access-logfile logs/access.log \
         --error-logfile logs/error.log
```

### Systemd Service (auto-start on reboot)

```bash
cat > /etc/systemd/system/cyberbulletin.service << 'EOF'
[Unit]
Description=Cyber Intelligence Bulletin Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/CYBERSECURITY_NEWS
ExecStart=/usr/local/bin/gunicorn --workers 4 --bind 0.0.0.0:8080 --chdir scripts bulletin_server:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cyberbulletin
systemctl start cyberbulletin
```

### Cron Jobs

```cron
30 7 * * 1-5 cd /opt/CYBERSECURITY_NEWS && python3 scripts/collect_news.py >> logs/cron.log 2>&1
45 7 * * 1-5 cd /opt/CYBERSECURITY_NEWS && python3 scripts/generate_bulletin_data.py >> logs/cron.log 2>&1
```

---

## Dashboard Features

| Feature | Detail |
|---------|--------|
| 🔴🟠🟡🟢 Severity cards | Live count of Critical / High / Medium / Low |
| 🚨 Ranked threat feed | Top 25 threats, CVEs auto-clustered, source badges |
| 🔍 Search & filter | Filter by severity or keyword — real-time |
| ✨ AI Summary | Gemini AI executive summary for management |
| 📡 Source breakdown | Bar chart of all feed sources |
| 🕐 Latest timeline | 8 most recent advisories |
| `/api/data` | JSON API for downstream integrations |
| Auto-refresh | Page refreshes every 5 minutes |

*Built for internal use — sasi-del/CYBERSECURITY_NEWS*

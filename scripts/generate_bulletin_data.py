#!/usr/bin/env python3
"""
scripts/generate_bulletin_data.py
AI-powered feed processor: scores, clusters, and optionally generates
an executive summary via Gemini AI, saving to data/bulletin_cache.json.

Run AFTER collect_news.py:
    python3 scripts/generate_bulletin_data.py

Requires: GEMINI_API_KEY env var for AI summary (optional).
          pip install google-genai
"""

import json
import os
import re
import sys
from datetime import datetime
from collections import defaultdict

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

def proj(rel):
    return os.path.join(PROJECT_ROOT, rel)

# ---------------------------------------------------------------------------
# Same scoring logic as bulletin_server.py (keep in sync)
# ---------------------------------------------------------------------------
ORG_TECH_STACK = [
    "kafka", "jenkins", "kubernetes", "k8s", "docker", "aws", "azure", "gcp",
    "linux", "windows", "cisco", "fortinet", "palo alto", "session smart",
    "nginx", "apache", "postgres", "mysql", "redis", "python", "go", "android",
    "chrome", "firefox", "outlook", "exchange", "sharepoint", "active directory",
]
HIGH_SEVERITY_KEYWORDS = [
    "zero-day", "0-day", "rce", "remote code execution", "unauthenticated",
    "privilege escalation", "data breach", "ransomware", "active exploitation",
    "cisa", "kev", "critical", "bypass", "backdoor", "supply chain",
]
MEDIUM_SEVERITY_KEYWORDS = [
    "vulnerability", "cve", "patch", "update", "advisory", "denial of service",
    "dos", "memory", "overflow", "injection", "xss", "csrf",
]


def score_article(article):
    title  = (article.get("title") or "").lower()
    desc   = (article.get("description") or "").lower()
    text   = title + " " + desc
    score, tags, severity = 0, [], "low"

    for tech in ORG_TECH_STACK:
        if re.search(r'\b' + re.escape(tech) + r'\b', text):
            score += 15
            tags.append(tech.upper())

    for kw in HIGH_SEVERITY_KEYWORDS:
        if kw in text:
            score += 12
            tags.append(kw.upper())
            severity = "critical" if kw in {
                "zero-day", "0-day", "rce", "remote code execution",
                "active exploitation", "ransomware", "backdoor",
            } else "high"

    for kw in MEDIUM_SEVERITY_KEYWORDS:
        if kw in text:
            score += 4
            if severity == "low":
                severity = "medium"

    return score, list(dict.fromkeys(tags))[:6], severity


def cluster_articles(articles, top_n=10):
    scored, clusters = [], defaultdict(list)

    for art in articles:
        score, tags, severity = score_article(art)
        title = art.get("title") or ""
        m = re.search(r'CVE-\d{4}-\d+\s*-\s*([A-Za-z0-9\s\/]+?):', title)
        if m:
            clusters[m.group(1).strip()].append((score, art, tags, severity))
        else:
            scored.append({"score": score, "article": art, "tags": tags,
                           "severity": severity, "cluster": [], "count": 1})

    for product, items in clusters.items():
        items.sort(key=lambda x: x[0], reverse=True)
        best_score, primary, _, severity = items[0]
        all_tags = list(dict.fromkeys([t for x in items for t in x[2]]))[:6]
        scored.append({
            "score":    best_score + len(items) * 4,
            "article":  primary,
            "tags":     all_tags,
            "severity": severity,
            "cluster":  [x[1] for x in items[1:4]],
            "count":    len(items),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# AI Summary (optional) — supports Gemini and OpenRouter
# ---------------------------------------------------------------------------
SUMMARY_PROMPT = """You are a cybersecurity analyst writing a 5-line executive summary \
for non-technical management. Today's top security headlines are:

{headlines}

Write a concise, plain-English summary (5 sentences max) that:
1. Identifies the most critical risk today
2. Mentions if any risk directly affects common enterprise technologies
3. Recommends one immediate action for IT/security teams
4. Uses no jargon or CVE numbers

Keep it punchy — this is read at the morning standup."""


def _build_prompt(top_items):
    lines = []
    for i, item in enumerate(top_items, 1):
        title = item["article"].get("title", "")
        sev   = item["severity"].upper()
        count = item["count"]
        line  = f"{i}. [{sev}] {title}"
        if count > 1:
            line += f" (+ {count - 1} related advisories)"
        lines.append(line)
    return SUMMARY_PROMPT.format(headlines="\n".join(lines))


def _detect_provider():
    provider = os.environ.get("AI_PROVIDER", "").lower().strip()
    if provider == "openrouter":
        return "openrouter"
    if provider == "gemini":
        return "gemini"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return None


def _summary_via_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set.")
        return None
    try:
        from google import genai
    except ImportError:
        print("google-genai not installed — pip install -U google-genai")
        return None
    client = genai.Client(api_key=api_key)
    interaction = client.interactions.create(
        model="gemini-3.8-flash",
        input=prompt,
        store=False,
    )
    return interaction.output_text.strip()


def _summary_via_openrouter(prompt):
    import requests as _req

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set.")
        return None
    model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    resp = _req.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": 512,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        print(f"OpenRouter error: {data['error']}")
        return None
    choices = data.get("choices") or []
    if not choices:
        print(f"OpenRouter returned no choices. Response: {json.dumps(data, indent=2)[:500]}")
        return None
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        print(f"OpenRouter returned empty content. Response: {json.dumps(data, indent=2)[:500]}")
        return None
    return content.strip()


def generate_ai_summary(top_items):
    provider = _detect_provider()
    if provider is None:
        print("No AI provider configured — skipping AI summary.")
        print("  Set GEMINI_API_KEY or OPENROUTER_API_KEY in your environment.")
        return None

    prompt = _build_prompt(top_items)
    try:
        if provider == "openrouter":
            print(f"Using OpenRouter (model: {os.environ.get('OPENROUTER_MODEL', 'google/gemini-2.5-flash')})")
            return _summary_via_openrouter(prompt)
        else:
            print("Using Gemini")
            return _summary_via_gemini(prompt)
    except Exception as e:
        print(f"AI summary error ({provider}): {e}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    today     = datetime.now().strftime("%Y-%m-%d")
    news_path = proj("data/news_latest.json")

    if not os.path.exists(news_path):
        print(f"❌ {news_path} not found. Run collect_news.py first.")
        sys.exit(1)

    with open(news_path, encoding="utf-8") as f:
        data = json.load(f)

    articles  = data.get("articles", [])
    top_items = cluster_articles(articles, top_n=10)

    print(f"📊 Processed {len(articles)} articles → {len(top_items)} top items")

    # AI summary
    ai_summary = generate_ai_summary(top_items)
    if ai_summary:
        print("✅ AI summary generated.")

    # Serialise
    serialisable = [{
        "title":    i["article"].get("title"),
        "url":      i["article"].get("url"),
        "source":   i["article"].get("source"),
        "published":i["article"].get("published"),
        "severity": i["severity"],
        "tags":     i["tags"],
        "score":    i["score"],
        "count":    i["count"],
        "cluster":  [{"title": c.get("title"), "url": c.get("url")} for c in i["cluster"]],
    } for i in top_items]

    cache = {
        "generated":  datetime.now().isoformat(),
        "date":       today,
        "ai_summary": ai_summary,
        "top_items":  serialisable,
    }

    cache_path = proj("data/bulletin_cache.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved bulletin cache → {cache_path}")

    # Also write Slack / markdown reports
    os.makedirs(proj("reports"), exist_ok=True)
    slack_path = proj(f"reports/cyber_bulletin_{today}_slack.txt")
    with open(slack_path, "w", encoding="utf-8") as f:
        f.write(f"🌅 *DAILY CYBER BULLETIN | {today}* 🛡️\n\n")
        if ai_summary:
            f.write(f"*📌 Executive Summary:*\n{ai_summary}\n\n")
        f.write("*🚨 Top Advisories:*\n")
        for i, item in enumerate(serialisable[:5], 1):
            suffix = f" (+{item['count']-1} related)" if item["count"] > 1 else ""
            f.write(f"{i}. *{item['title']}*{suffix}\n")
            f.write(f"   👉 <{item['url']}|View Advisory>\n\n")
        f.write("📋 Full report: http://YOUR-SERVER:5000\n")

    print(f"✅ Slack snippet → {slack_path}")


if __name__ == "__main__":
    main()

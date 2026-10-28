#!/usr/bin/env python3
"""
scripts/generate_internal_bulletin.py
Filters raw feed items into an actionable daily internal cyber bulletin.
Works from any working directory.
"""

import json
import os
import re
from datetime import datetime
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

def resolve_path(rel_path):
    if os.path.exists(rel_path):
        return os.path.abspath(rel_path)
    return os.path.join(PROJECT_ROOT, rel_path)

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

def load_news(filepath="data/news_latest.json"):
    target_path = resolve_path(filepath)
    if not os.path.exists(target_path):
        raise FileNotFoundError(
            f"Missing '{filepath}' (checked at {target_path}).\n"
            f"Please run collect_news.py first."
        )
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)

def score_article(article):
    title = (article.get("title") or "").lower()
    desc  = (article.get("description") or "").lower()
    text  = title + " " + desc
    score, tags = 0, []

    for tech in ORG_TECH_STACK:
        if re.search(r'\b' + re.escape(tech) + r'\b', text):
            score += 15
            tags.append(tech.upper())

    for kw in HIGH_SEVERITY_KEYWORDS:
        if kw in text:
            score += 10
            tags.append(kw.upper())

    source = (article.get("source") or "").lower()
    if "bleepingcomputer" in source or "the hacker news" in source:
        score += 8
    elif "oss-security" in source or "cvefeed" in source:
        score += 5

    return score, list(dict.fromkeys(tags))[:6]

def group_and_filter(articles, top_n=8):
    scored, cve_clusters = [], defaultdict(list)

    for art in articles:
        score, tags = score_article(art)
        title = art.get("title") or ""
        m = re.search(r'CVE-\d{4}-\d+\s*-\s*([A-Za-z0-9\s\/]+?):', title)
        if m:
            cve_clusters[m.group(1).strip()].append((score, art, tags))
        else:
            scored.append((score, art, tags, False))

    for product, items in cve_clusters.items():
        items.sort(key=lambda x: x[0], reverse=True)
        combined_score = max(x[0] for x in items) + len(items) * 3
        all_tags = list(dict.fromkeys([t for x in items for t in x[2]]))[:6]
        scored.append((combined_score, items[0][1], all_tags, items))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]

def generate_markdown(top_items, today_str):
    out = [f"# 🛡️ Daily Cybersecurity Morning Bulletin - {today_str}\n"]
    out.append("> *Internal Threat Intelligence Briefing for Leadership & Tech Teams*\n")
    out.append("## 📌 30-Second Executive Summary\n")
    out.append("- [ ] **[Intern to complete]** Summary of top organisational risks for today.\n")
    out.append("## 🚨 Top Vulnerability & Incident Highlights\n")

    for i, (score, art, tags, cluster) in enumerate(top_items, 1):
        title  = art.get("title", "")
        source = art.get("source", "Unknown")
        url    = art.get("url", "#")
        tag_str = " ".join([f"`{t}`" for t in tags[:4]])

        out.append(f"### {i}. {title}")
        out.append(f"- **Source:** {source} | **Tags:** {tag_str}")
        out.append(f"- **Link:** [{url}]({url})")

        if cluster and len(cluster) > 1:
            out.append(f"- **Consolidated Advisories ({len(cluster)} issues):**")
            for _, sub_art, _ in cluster[1:4]:
                out.append(f"  - [{sub_art.get('title')}]({sub_art.get('url')})")

        out.append("- **🔍 Organisational Impact:** *[Interns: Check if deployed in our stack]*")
        out.append("- **⚡ Action Required:** *[e.g., DevOps review patch status]*\n")

    out.append("## 💡 Daily Security Awareness Tip\n")
    out.append("*Tip for general staff (e.g., verifying MFA requests).*\n")
    return "\n".join(out)

def generate_slack_summary(top_items, today_str):
    out = [f"🌅 *DAILY CYBER BULLETIN | {today_str}* 🛡️\n"]
    out.append("Good morning team! Here are today's top security updates:\n")
    for i, (score, art, tags, cluster) in enumerate(top_items[:5], 1):
        title  = (art.get("title") or "").strip()
        url    = art.get("url", "#")
        suffix = f" (+{len(cluster)-1} related CVEs)" if cluster and len(cluster) > 1 else ""
        out.append(f"*{i}. {title}*{suffix}")
        out.append(f"   👉 <{url}|View Advisory>\n")
    out.append("📋 *Full report:* http://YOUR-SERVER:8080")
    return "\n".join(out)

def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    data      = load_news("data/news_latest.json")
    articles  = data.get("articles", [])
    top_items = group_and_filter(articles, top_n=6)

    reports_dir = os.path.join(PROJECT_ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    with open(os.path.join(reports_dir, f"cyber_bulletin_{today_str}.md"), "w", encoding="utf-8") as f:
        f.write(generate_markdown(top_items, today_str))

    with open(os.path.join(reports_dir, f"cyber_bulletin_{today_str}_slack.txt"), "w", encoding="utf-8") as f:
        f.write(generate_slack_summary(top_items, today_str))

    print(f"✅ Generated reports/cyber_bulletin_{today_str}.md")
    print(f"✅ Generated reports/cyber_bulletin_{today_str}_slack.txt")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import concurrent.futures
import json
import re
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "security_feeds.yaml"
OUTPUT_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

# Include articles published within the last 48 hours.
LOOKBACK_HOURS = 48
MAX_WORKERS = 10
TIMEOUT = 12


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()


def normalize_url(url):
    """Remove fragments and tracking parameters for deduplication."""
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return url.strip()
        ignored = {
            "fbclid", "gclid", "mc_cid", "mc_eid",
            "ref", "source"
        }
        query = "&".join(
            item for item in parts.query.split("&")
            if item and item.split("=")[0].lower() not in ignored
            and not item.split("=")[0].lower().startswith("utm_")
        )
        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            query,
            ""
        ))
    except (ValueError, AttributeError):
        return url.strip()


def fetch_source(source):
    feed_info = source.get("feed") or {}
    url = feed_info.get("url")
    if not url:
        return [], f"{source.get('id', 'unknown')}: missing feed URL"

    try:
        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": "CyberBulletinCollector/1.0"}
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)

        if not parsed.entries:
            return [], (
                f"{source.get('id', 'unknown')}: no entries "
                "(possibly unsupported feed or empty response)"
            )

        articles = []
        for entry in parsed.entries:
            title = clean_text(entry.get("title", ""))
            link = entry.get("link", "").strip()

            if not title or not link:
                continue

            published_struct = (
                entry.get("published_parsed")
                or entry.get("updated_parsed")
            )
            published = None

            if published_struct:
                published = datetime.fromtimestamp(
                    time.mktime(published_struct), tz=timezone.utc
                )

            articles.append({
                "source_id": source.get("id", ""),
                "source": source.get("name") or source.get("id", "Unknown"),
                "title": title,
                "url": link,
                "summary": clean_text(
                    entry.get("summary") or entry.get("description", "")
                )[:1200],
                "published": published.isoformat() if published else None,
                "_published_dt": published,
            })

        return articles, None

    except (requests.RequestException, ValueError, TypeError) as exc:
        return [], f"{source.get('id', 'unknown')}: {exc}"
    except Exception as exc:
        return [], f"{source.get('id', 'unknown')}: {exc}"


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    with CONFIG.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    sources = config.get("entities", [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    print(f"Cyber Bulletin Collector")
    print(f"Sources configured: {len(sources)}")
    print(f"Looking back: {LOOKBACK_HOURS} hours")
    print("Fetching feeds...")

    all_articles = []
    errors = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:
        futures = {
            executor.submit(fetch_source, source): source
            for source in sources
        }
        for future in concurrent.futures.as_completed(futures):
            articles, error = future.result()
            all_articles.extend(articles)
            if error:
                errors.append(error)

    # Deduplicate by normalized URL, then by title.
    unique = {}
    for article in all_articles:
        published = article.pop("_published_dt")
        article["_sort_dt"] = published

        if published and published < cutoff:
            continue

        url_key = normalize_url(article["url"])
        title_key = article["title"].casefold()
        key = url_key or title_key

        if key not in unique:
            unique[key] = article
        elif published and (
            not unique[key]["_sort_dt"]
            or published > unique[key]["_sort_dt"]
        ):
            unique[key] = article

    articles = list(unique.values())
    articles.sort(
        key=lambda a: a["_sort_dt"] or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True
    )

    for article in articles:
        article.pop("_sort_dt", None)

    now = datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat(),
        "lookback_hours": LOOKBACK_HOURS,
        "sources_configured": len(sources),
        "articles_found_before_filtering": len(all_articles),
        "articles_selected": len(articles),
        "feed_errors": errors,
        "articles": articles,
    }

    json_path = OUTPUT_DIR / "news_latest.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    date_label = datetime.now().astimezone().strftime("%Y-%m-%d")
    report_path = REPORT_DIR / f"cyber_bulletin_{date_label}.md"

    lines = [
        "# Daily Cyber Bulletin",
        "",
        f"**Generated:** {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"**Coverage:** Previous {LOOKBACK_HOURS} hours",
        f"**Articles selected:** {len(articles)}",
        "",
        "> Review and verify every item before distributing this bulletin. "
        "Feed content is untrusted input; confirm claims using the original source.",
        "",
    ]

    if not articles:
        lines += [
            "No dated articles were found within the selected time window.",
            "Check feed connectivity and review the feed errors below.",
            "",
        ]

    for index, article in enumerate(articles, 1):
        lines += [
            f"## {index}. {article['title']}",
            "",
            f"- **Source:** {article['source']}",
            f"- **Published:** {article['published'] or 'Date unavailable'}",
            f"- **Link:** {article['url']}",
        ]
        if article["summary"]:
            lines += ["", article["summary"]]
        lines.append("")

    lines += [
        "---",
        "",
        "## Collection status",
        "",
        f"- Configured sources: {len(sources)}",
        f"- Feed errors or empty feeds: {len(errors)}",
        "",
    ]

    if errors:
        lines.append("### Feeds needing review")
        lines.append("")
        lines.extend(f"- {error}" for error in errors[:50])
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Articles selected: {len(articles)}")
    print(f"Feed errors/empty feeds: {len(errors)}")
    print(f"JSON data: {json_path.relative_to(ROOT)}")
    print(f"Bulletin: {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

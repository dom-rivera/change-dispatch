"""Check candidate feeds before adding them to config/sources.yaml.

Usage: python scripts/check_feeds.py URL [URL ...]
For each URL prints the HTTP status, whether it parses as a feed, the number
of entries, the newest date and the first few headlines. It reads only what
the site offers to feed readers; a site that refuses (401/403/429) is
reported as refusing and is not retried.
"""
import sys

import feedparser
import requests

sys.path.insert(0, "scripts")
from fetch import USER_AGENT  # noqa: E402


def check(url: str) -> None:
    print(f"\n=== {url}")
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as e:
        print(f"  ERROR {type(e).__name__}: {e}")
        return
    print(f"  HTTP {r.status_code}  type={r.headers.get('content-type', '?')}  final={r.url}")
    if r.status_code in (401, 403, 429):
        print("  REFUSED: this site blocks automated readers; do not add it.")
        return
    if r.status_code != 200:
        return
    feed = feedparser.parse(r.content)
    n = len(feed.entries)
    print(f"  feed title: {feed.feed.get('title', '-')!r}  entries={n}  bozo={bool(feed.bozo)}")
    dates = [e.get("published") or e.get("updated") or "" for e in feed.entries]
    if dates:
        print(f"  first date: {dates[0]}")
    for e in feed.entries[:8]:
        print(f"   - {e.get('title', '').strip()[:110]}")


if __name__ == "__main__":
    for u in sys.argv[1:] or sys.stdin.read().split():
        check(u)

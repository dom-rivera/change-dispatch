"""Write today's headlines into docs/index.html as plain HTML.

The page normally fills in its stories with JavaScript (app.js). Search
engines, link previews, AI reading tools and readers with JavaScript off
don't run it, so they would only see an empty page. This script puts the
newest stories between the static markers inside #stories; app.js replaces
them with the full interactive list as soon as it runs.

Everything inserted is escaped, and only plain web links become links.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "docs" / "index.html"
ITEMS = ROOT / "docs" / "data" / "items.json"
START, END = "<!-- static:start -->", "<!-- static:end -->"
UPD_RE = re.compile(r'(<span id="updated">)(.*?)(</span>)')
CLOCK_RE = re.compile(r'(<time id="clock"[^>]*>)(.*?)(</time>)')
DATE_RE = re.compile(r'(<span id="today-date">)(.*?)(</span>)')
MAX_ITEMS = 30
MANILA = timezone(timedelta(hours=8))
SAFE_URL = re.compile(r"^https?://[^\s\"'<>]+$", re.I)


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def fmt(d: datetime) -> str:
    d = d.astimezone(MANILA)
    return f"{d:%b} {d.day}, {d.year}"


def current(item: dict, now: datetime) -> bool:
    return now - parse(item["published"]) <= timedelta(days=item.get("window_days", 7))


def story(item: dict, names: dict) -> str:
    e = html.escape
    title = e(item["title"])
    url = item.get("url", "")
    head = (f'<a href="{e(url, quote=True)}" rel="noopener noreferrer" target="_blank">{title}</a>'
            if SAFE_URL.match(url) else title)
    topics = "".join(f'<a href="#topic/{e(t, quote=True)}">{e(names.get(t, t))}</a>'
                     for t in item.get("topics", []))
    return (
        '<article class="story">'
        f'<p class="kicker">{e(item.get("type", ""))}<span class="src"> · {e(item.get("source", ""))}</span></p>'
        f'<h3 class="headline">{head}</h3>'
        f'<div class="meta"><time datetime="{e(item["published"], quote=True)}">{fmt(parse(item["published"]))}</time>'
        f'<span class="badge free">{e(item.get("access") or "Free to read")}</span></div>'
        + (f'<div class="tags">{topics}</div>' if topics else "")
        + "</article>"
    )


def build(page: str, doc: dict, now: datetime) -> str:
    names = {t["id"]: t["name"] for t in doc.get("topics", [])}
    items = [i for i in doc.get("items", []) if current(i, now)]
    items.sort(key=lambda i: (i.get("first_seen", ""), i.get("published", "")), reverse=True)
    block = "\n".join(story(i, names) for i in items[:MAX_ITEMS])
    if START not in page or END not in page:
        raise SystemExit("static markers missing from docs/index.html")
    a, rest = page.split(START, 1)
    _, b = rest.split(END, 1)
    page = f"{a}{START}\n{block}\n{END}{b}"
    generated = doc.get("generated")
    if generated:
        d = parse(generated).astimezone(MANILA)
        stamp = f"Updated {fmt(d)}, {d:%I:%M %p}".replace(" 0", " ")
        page = UPD_RE.sub(lambda m: m.group(1) + html.escape(stamp) + m.group(3), page, count=1)
        # Text-only readers see the edition date; app.js replaces both with a live clock.
        page = CLOCK_RE.sub(lambda m: m.group(1) + html.escape(f"{d:%I:%M %p}".lstrip("0")) + m.group(3), page, count=1)
        page = DATE_RE.sub(lambda m: m.group(1) + html.escape(f"{d:%A}, {fmt(d)}") + m.group(3), page, count=1)
    return page


def main() -> None:
    doc = json.loads(ITEMS.read_text(encoding="utf-8"))
    page = INDEX.read_text(encoding="utf-8")
    new = build(page, doc, datetime.now(timezone.utc))
    if new != page:
        INDEX.write_text(new, encoding="utf-8")
    print("docs/index.html: static headlines updated")


if __name__ == "__main__":
    main()

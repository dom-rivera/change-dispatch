"""The Change Dispatch: build the RSS feed (docs/feed.xml).

The feed lists the newest Editor's Notes and the newest items added to the
site, so people can follow The Change Dispatch in any feed reader app.
It is a public file: nobody signs up and no reader information is collected.

Items are dated by when they were added to the site, so feed readers show
them as new on the day they appear; the original publication date is in
each item's description.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
OUT = ROOT / "docs" / "feed.xml"
SITE = "https://dom-rivera.github.io/change-dispatch/"
FEED_URL = SITE + "feed.xml"
MAX_ITEMS = 60
MAX_NOTES = 5


def parse(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    if len(value) == 10:  # a plain date (notes): 9:00 AM Manila
        value += "T01:00:00+00:00"
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def rfc822(value: str) -> str:
    return format_datetime(parse(value).astimezone(timezone.utc), usegmt=True)


def tag(name: str, text: str, **attrs) -> str:
    a = "".join(f' {k}="{escape(str(v), {chr(34): "&quot;"})}"' for k, v in attrs.items())
    return f"<{name}{a}>{escape(str(text))}</{name}>"


def human_date(value: str) -> str:
    d = parse(value)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def build(data_dir: Path = DATA) -> str:
    items_doc = json.loads((data_dir / "items.json").read_text(encoding="utf-8"))
    notes_path = data_dir / "notes.json"
    notes = json.loads(notes_path.read_text(encoding="utf-8")).get("notes", []) if notes_path.exists() else []
    topic_names = {t["id"]: t["name"] for t in items_doc.get("topics", [])}
    region_name = (items_doc.get("region") or {}).get("name", "Philippines & Southeast Asia")

    entries = []  # (sort date, xml)
    for n in notes[:MAX_NOTES]:
        url = f"{SITE}#note/{n['slug']}"
        entries.append((parse(n["date"]), "\n".join([
            "    <item>",
            "      " + tag("title", "Editor’s Note: " + n["title"]),
            "      " + tag("link", url),
            "      " + tag("guid", "note-" + n["slug"], isPermaLink="false"),
            "      " + tag("pubDate", rfc822(n["date"])),
            "      " + tag("dc:creator", n.get("author", "Dom Rivera")),
            "      " + tag("category", "Editor’s Note"),
            "      " + tag("description", n["summary"]),
            "    </item>",
        ])))

    items = sorted(items_doc.get("items", []),
                   key=lambda i: (i.get("first_seen", ""), i.get("published", "")), reverse=True)
    for i in items[:MAX_ITEMS]:
        topics = [topic_names.get(t, t) for t in i.get("topics", [])]
        if i.get("region"):
            topics.append(region_name)
        labels = " · ".join(i.get("labels", []))
        desc = (f"{i['type']} · {i['source']} · "
                f"{'Added' if i.get('date_estimated') else 'Published'} {human_date(i['published'])}"
                f" · {i.get('access', 'Free to read')}"
                + (f" · {labels}" if labels else "")
                + (f". Topics: {', '.join(topics)}." if topics else "."))
        authors = ", ".join((i.get("cite") or {}).get("authors", [])[:6])
        lines = [
            "    <item>",
            "      " + tag("title", i["title"]),
            "      " + tag("link", i["url"]),
            "      " + tag("guid", i["id"], isPermaLink="false"),
            "      " + tag("pubDate", rfc822(i.get("first_seen") or i["published"])),
            "      " + tag("description", desc),
            "      " + tag("category", i["type"]),
        ]
        lines += ["      " + tag("category", t) for t in topics]
        if authors:
            lines.append("      " + tag("dc:creator", authors))
        lines.append("    </item>")
        entries.append((parse(i.get("first_seen") or i["published"]), "\n".join(lines)))

    entries.sort(key=lambda e: e[0], reverse=True)
    built = items_doc.get("generated") or datetime.now(timezone.utc).isoformat()
    head = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">',
        "  <channel>",
        "    " + tag("title", "The Change Dispatch"),
        "    " + tag("link", SITE),
        f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
        "    " + tag("description", "Open, verified news and research on organizational change, AI, "
                                   "psychology and economics, with a section on the Philippines and "
                                   "Southeast Asia. Every item is free to read."),
        "    " + tag("language", "en"),
        "    " + tag("lastBuildDate", rfc822(built)),
        "    " + tag("ttl", "360"),
        "    <image>",
        "      " + tag("url", SITE + "og-image.png"),
        "      " + tag("title", "The Change Dispatch"),
        "      " + tag("link", SITE),
        "    </image>",
    ])
    return head + "\n" + "\n".join(e[1] for e in entries) + "\n  </channel>\n</rss>\n"


def main() -> int:
    if not (DATA / "items.json").exists():
        print("No items yet; feed not built.")
        return 0
    xml = build()
    OUT.write_text(xml, encoding="utf-8")
    print(f"Feed written: {xml.count('<item>')} entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

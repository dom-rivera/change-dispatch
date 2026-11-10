"""The Change Dispatch: build the Editor's Notes.

Reads every note in notes/ (one Markdown file per note) and writes
docs/data/notes.json for the website.

A note file looks like this:

    ---
    title: What a week of layoff news says about change readiness
    date: 2026-11-16
    summary: One sentence shown on the front page (optional).
    draft: false
    ---
    Your text in Markdown...

Rules:
- Files starting with "_" (like _template.md) and README.md are ignored.
- draft: true keeps a note off the site.
- A note dated in the future appears on that day (Manila time), at the
  next update.
- Raw HTML in a note is shown as text, and only web links (http/https)
  become clickable, so a note can never break or endanger the site.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
OUT = ROOT / "docs" / "data" / "notes.json"
MANILA = timezone(timedelta(hours=8))
AUTHOR = "Dom Rivera"

md = (MarkdownIt("commonmark", {"html": False, "typographer": True})
      .enable(["replacements", "smartquotes", "table", "strikethrough"]))


class NoteError(ValueError):
    pass


def split_front_matter(text: str, name: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.S)
    if not m:
        raise NoteError(f"{name}: the note must start with a '---' block (title, date).")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise NoteError(f"{name}: the '---' block could not be read ({exc}). "
                        "Tip: put the title in quotes if it contains a colon.") from exc
    return meta, m.group(2)


def plain_text(html: str) -> str:
    text = re.sub(r"</?(?:em|strong|a|code|s|del)(?:\s[^>]*)?>", "", html)  # inline tags
    text = re.sub(r"<[^>]+>", " ", text)                                    # block tags
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", text).strip()


def external_links(html: str) -> str:
    # open links in a new tab, without giving the other site control
    return re.sub(r'<a href="(https?://[^"]+)"',
                  r'<a href="\1" target="_blank" rel="noopener noreferrer"', html)


def build_note(path: Path, today: str) -> dict | None:
    meta, body = split_front_matter(path.read_text(encoding="utf-8"), path.name)
    if meta.get("draft"):
        return None
    title = str(meta.get("title") or "").strip()
    if not title:
        raise NoteError(f"{path.name}: add a title, e.g.  title: My first note")
    date = meta.get("date")
    date = date.isoformat() if hasattr(date, "isoformat") else str(date or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise NoteError(f"{path.name}: add a date as YYYY-MM-DD, e.g.  date: 2026-11-16")
    if date > today:
        return None  # scheduled for later
    if not body.strip():
        raise NoteError(f"{path.name}: the note has no text yet (or set  draft: true).")

    html = external_links(md.render(body))
    text = plain_text(html)
    words = len(text.split())
    summary = str(meta.get("summary") or "").strip()
    if not summary:
        first = re.search(r"<p>(.*?)</p>", html, flags=re.S)
        summary = plain_text(first.group(1)) if first else text
        if len(summary) > 280:
            summary = summary[:277].rsplit(" ", 1)[0] + "…"
    return {
        "slug": re.sub(r"[^a-z0-9-]+", "-", path.stem.lower()).strip("-"),
        "title": title,
        "date": date,
        "author": AUTHOR,
        "summary": summary,
        "minutes": max(1, round(words / 220)),
        "html": html,
    }


def build(notes_dir: Path = NOTES, today: str | None = None) -> list[dict]:
    today = today or datetime.now(MANILA).strftime("%Y-%m-%d")
    notes, errors = [], []
    for path in sorted(notes_dir.glob("*.md")):
        if path.name.startswith("_") or path.name.lower() == "readme.md":
            continue
        try:
            note = build_note(path, today)
            if note:
                notes.append(note)
        except NoteError as exc:
            errors.append(str(exc))
    if errors:
        raise NoteError("\n".join(errors))
    slugs = [n["slug"] for n in notes]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise NoteError(f"Two notes have the same file name: {', '.join(dupes)}")
    return sorted(notes, key=lambda n: (n["date"], n["slug"]), reverse=True)


def main() -> int:
    try:
        notes = build()
    except NoteError as exc:
        print("The Editor's Notes could not be published:\n" + str(exc))
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"notes": notes}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(notes)} note(s) published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

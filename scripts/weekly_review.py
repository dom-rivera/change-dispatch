"""Weekly review for the editor.

Opens a GitHub issue listing every item the site kept in the past 7 days,
grouped by type and source, so the editor can skim the headlines and
remove anything off-topic (config/removed.yaml). GitHub emails the
repository owner about new issues. The previous week's review issue is
closed when a new one opens.

Headlines come from outside sources, so they are escaped: no Markdown
formatting, no @mentions and no #issue links can be triggered by them.
Uses the GitHub CLI (gh), preinstalled on GitHub's runners.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "docs" / "data" / "items.json"
STATUS = ROOT / "docs" / "data" / "status.json"
TITLE_PREFIX = "Weekly review:"
DAYS = 7
MAX_BODY = 60000          # GitHub's limit is 65,536 characters
MANILA = timezone(timedelta(hours=8))


def safe_text(s: str) -> str:
    """Escape Markdown and break @mentions so a headline is shown as text."""
    s = re.sub(r"\s+", " ", s or "").strip()
    s = re.sub(r"([\\`*_{}\[\]<>()#+!|~>])", r"\\\1", s)
    return s.replace("@", "@​")


def safe_url(u: str) -> str | None:
    if not re.match(r"^https?://[^\s\"'<>]+$", u or ""):
        return None
    return u.replace("(", "%28").replace(")", "%29")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def line(item: dict, topic_names: dict) -> str:
    url = safe_url(item.get("url", ""))
    title = safe_text(item.get("title", ""))
    head = f"[{title}]({url})" if url else title
    topics = ", ".join(topic_names.get(t, t) for t in item.get("topics", []))
    extra = []
    if item.get("region"):
        extra.append("PH & SE Asia")
    tail = " · ".join(x for x in (topics, *extra) if x)
    return f"- {head}  \n  <sub>{safe_text(item.get('source', ''))}" + (f" · {safe_text(tail)}" if tail else "") + "</sub>"


def build(items_doc: dict, status_doc: dict | None, now: datetime, repo: str,
          brief_research: bool = False) -> tuple[str, str]:
    start = now - timedelta(days=DAYS)
    names = {t["id"]: t["name"] for t in items_doc.get("topics", [])}
    week = [i for i in items_doc.get("items", []) if parse(i["first_seen"]) >= start]
    week.sort(key=lambda i: (i.get("source", ""), i.get("title", "")))

    groups = [
        ("News and expert analysis", ("news", "analysis"), True),
        ("Institutional reports", ("institutional",), True),
        ("Research and preprints", ("research", "preprint"), False),
    ]
    a, b = start.astimezone(MANILA), now.astimezone(MANILA)
    title = f"{TITLE_PREFIX} {a:%b} {a.day} to {b:%b} {b.day}, {b.year}"

    edit = f"https://github.com/{repo}/edit/main/config/removed.yaml" if repo else "config/removed.yaml"
    out = [
        f"**{len(week)} items** were added to the site in the past {DAYS} days.",
        "",
        "Skim the headlines below. If something is off-topic, unreliable or shouldn't appear, "
        f"add its link and a short reason to [config/removed.yaml]({edit}); "
        "it disappears at the next update and stays out. "
        "If a whole source or phrase keeps letting in the wrong things, reply here and adjust "
        "`config/sources.yaml` or `config/topics.yaml`.",
        "",
        "Close this issue when you're done. Next week's review closes it automatically.",
    ]

    if status_doc:
        failed = [s["name"] for s in status_doc.get("sources", []) if not s.get("ok")]
        stale = [s["name"] for s in status_doc.get("sources", []) if s.get("ok") and s.get("stale")]
        if failed or stale:
            out += ["", "### Sources to look at"]
            out += [f"- Not working: {safe_text(n)}" for n in failed]
            out += [f"- Nothing new for weeks: {safe_text(n)}" for n in stale]

    for label, layers, open_ in groups:
        chosen = [i for i in week if i.get("layer") in layers]
        if not chosen:
            continue
        by_src: dict[str, list] = defaultdict(list)
        for i in chosen:
            by_src[i.get("source", "")].append(i)
        body = []
        for src in sorted(by_src):
            body += [f"**{safe_text(src)}** ({len(by_src[src])})", ""]
            body += [line(i, names) for i in by_src[src]]
            body.append("")
        if not open_ and brief_research:
            body = [f"- {safe_text(src)}: {len(by_src[src])}" for src in sorted(by_src)]
            out += ["", f"## {label} ({len(chosen)})", "",
                    "Too many to list here this week; counts per source below. "
                    "See the Research Desk on the site for the papers.", ""] + body
        elif open_:
            out += ["", f"## {label} ({len(chosen)})", ""] + body
        else:
            out += ["", f"## {label} ({len(chosen)})", "",
                    "<details><summary>Show all</summary>", ""] + body + ["</details>"]

    text = "\n".join(out)
    if len(text) > MAX_BODY and not brief_research:
        return build(items_doc, status_doc, now, repo, brief_research=True)
    if len(text) > MAX_BODY:
        text = text[:MAX_BODY].rsplit("\n", 1)[0] + "\n\n_(List shortened to fit GitHub's limit. See the Archive on the site for the rest.)_"
    return title, text


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    items_doc = json.loads(ITEMS.read_text(encoding="utf-8"))
    status_doc = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else None
    title, body = build(items_doc, status_doc, datetime.now(timezone.utc),
                        os.environ.get("GITHUB_REPOSITORY", ""))
    if "--print" in sys.argv:
        print(title + "\n\n" + body)
        return 0
    old = json.loads(gh("issue", "list", "--state", "open", "--search",
                        f'"{TITLE_PREFIX}" in:title', "--json", "number,title"))
    url = gh("issue", "create", "--title", title, "--body", body).strip()
    for issue in old:
        if issue["title"].startswith(TITLE_PREFIX):
            gh("issue", "close", str(issue["number"]), "--comment", f"Replaced by {url}")
    print(f"Opened {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

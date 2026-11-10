"""The Change Dispatch: link and deployment audit.

Run on demand (Actions → Audit links → Run workflow). It:
1. opens every item link on the site and reports any that are broken;
2. checks that the live website, data, feed and preview image match the
   repository (so what readers see is the latest version).

Some publishers refuse automated checks (HTTP 403/429) even though the
page works in a browser; those are listed separately, not as broken.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://dom-rivera.github.io/change-dispatch/"
UA = "ChangeDispatchBot/1.0 (+https://github.com/dom-rivera/change-dispatch; link check)"


def check(url: str) -> tuple[str, int | None, str]:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    try:
        r = s.head(url, allow_redirects=True, timeout=25)
        if r.status_code in (403, 405, 400, 404, 429, 500, 501, 503):
            r = s.get(url, allow_redirects=True, timeout=25, stream=True)
        return url, r.status_code, r.url
    except requests.RequestException as exc:
        return url, None, str(exc)[:120]


def main() -> int:
    items = json.loads((ROOT / "docs/data/items.json").read_text(encoding="utf-8"))["items"]
    urls = sorted({i["url"] for i in items})
    by_url = {i["url"]: i for i in items}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, urls))

    ok = [r for r in results if r[1] and r[1] < 400]
    blocked = [r for r in results if r[1] in (401, 403, 429, 999)]
    broken = [r for r in results if r not in ok and r not in blocked]

    lines = [f"## Link audit: {len(urls)} links",
             f"- Working: {len(ok)}",
             f"- Publisher refused the automated check (usually fine in a browser): {len(blocked)}",
             f"- Broken or unreachable: {len(broken)}", ""]
    if blocked:
        lines.append("### Refused automated check")
        lines += [f"- {by_url[u]['source']}: {code} {u}" for u, code, _ in blocked]
    if broken:
        lines.append("### Broken or unreachable")
        lines += [f"- {by_url[u]['source']}: {code or 'no response'} {u} ({info})" for u, code, info in broken]

    # Is the live site the same as the repository?
    lines += ["", "## Live site matches the repository"]
    live_ok = True
    for path in ["index.html", "app.js", "apa.js", "style.css", "feed.xml", "data/items.json",
                 "data/notes.json", "og-image.png", "fonts/libre-franklin-latin-400-normal.woff2"]:
        try:
            r = requests.get(SITE + path, timeout=25, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
            local = (ROOT / "docs" / path).read_bytes()
            same = r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == hashlib.sha256(local).hexdigest()
            lines.append(f"- {path}: HTTP {r.status_code}, {'identical' if same else 'DIFFERENT (may be a cache delay of a few minutes)'}")
            live_ok &= r.status_code == 200
        except requests.RequestException as exc:
            lines.append(f"- {path}: unreachable ({exc})")
            live_ok = False

    # How is each research paper free to read? (OpenAlex open-access status)
    key = os.environ.get("OPENALEX_API_KEY", "")
    research = [i for i in items if (i.get("cite") or {}).get("doi") and i["layer"] == "research"]
    if key and research:
        from collections import Counter
        status, closed = Counter(), []
        for i in research:
            doi = i["cite"]["doi"].replace("https://doi.org/", "")
            try:
                r = requests.get(f"https://api.openalex.org/works/doi:{doi}",
                                 params={"api_key": key, "select": "open_access"}, timeout=25)
                oa = (r.json().get("open_access") or {})
                st = oa.get("oa_status") or "unknown"
            except Exception:
                st = "unknown"
            status[st] += 1
            if st in ("closed", "unknown"):
                closed.append(f"- {i['source']}: {st} {i['url']}")
        lines += ["", f"## Free-to-read check ({len(research)} research papers, via OpenAlex)",
                  "- gold/diamond: published open access; hybrid: open article in a subscription journal;",
                  "  green: free author copy in a repository; bronze: free on the publisher's site without an open licence",
                  ""] + [f"- {k}: {v}" for k, v in status.most_common()]
        if closed:
            lines += ["", "### Not confirmed free"] + closed

    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).write_text(report, encoding="utf-8")
    (ROOT / "link-audit.json").write_text(json.dumps(
        {"ok": len(ok), "blocked": blocked, "broken": broken}, indent=1), encoding="utf-8")
    return 0 if live_ok else 1


if __name__ == "__main__":
    sys.exit(main())

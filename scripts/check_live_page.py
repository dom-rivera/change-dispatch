"""Open the live site in a real (headless) Chrome and confirm it renders.

Tools that read raw HTML without running JavaScript only see the page shell
("Loading…"), because stories are filled in by app.js. This check runs the
JavaScript like a reader's browser does and fails if no stories appear.
Usage: python scripts/check_live_page.py [URL]
"""
import re
import subprocess
import sys

URL = sys.argv[1] if len(sys.argv) > 1 else "https://dom-rivera.github.io/change-dispatch/"
PAGES = ["", "#front", "#research", "#region", "#notes", "#editions", "#about"]


def dom(url: str) -> str:
    return subprocess.run(
        ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
         "--virtual-time-budget=10000", "--dump-dom", url],
        capture_output=True, text=True, timeout=90).stdout


ok = True
for page in PAGES:
    html = dom(URL + page)
    stories = len(re.findall(r"<article\b", html))
    clock = re.search(r'id="clock"[^>]*>([^<]*)<', html)
    updated = re.search(r'id="updated"[^>]*>([^<]*)<', html)
    stuck = bool(clock and "Loading" in clock.group(1))
    print(f"{page or '(today)':10} stories={stories:3}  clock={clock.group(1) if clock else '?'!r}  "
          f"updated={updated.group(1).strip() if updated else '?'!r}")
    if page in ("", "#front", "#research") and (stories == 0 or stuck):
        ok = False
print("PASS: the live page renders stories" if ok else "FAIL: the live page did not render")
sys.exit(0 if ok else 1)

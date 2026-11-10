# The Change Dispatch

*Open, verified news and research on organizational change, AI, psychology and economics.*

The Change Dispatch is a free, open-source digest that updates itself every morning (Manila time). It collects new items from a public list of trusted sources, keeps only those that are **recent, free to read and on-topic**, labels each one, and publishes them as a newspaper-style website.

Edited by Dom Rivera. Site: https://dom-rivera.github.io/change-dispatch · RSS: https://dom-rivera.github.io/change-dispatch/feed.xml

It covers change readiness, self-efficacy, openness to change, organizational change and change management, plus leadership, well-being, psychological safety, the future of work, AI at work, labor economics and behavioral economics, with a dedicated section on the Philippines and Southeast Asia.

## Inclusion policy

**Firm rule: every item must be free to read, or it doesn't appear.** Research papers appear only when a free legal copy exists, and the link goes straight to that copy.

A source is included only if it:

1. is an established institution: a peer-reviewed journal, university, government agency, international organization or established news organization;
2. has editorial standards and corrections, or uses peer review or moderation;
3. gives every item a clear publication date and a named author or institution;
4. is not mainly marketing, advocacy or user-generated content.

Never included: social media, personal blogs, newsletters, company press releases, content farms or anonymous sources.

Every item is labeled by type (Peer-reviewed, Preprint, Institutional, Expert analysis, News). Preprints and working papers are labeled "Not yet peer-reviewed", opinion pieces are labeled "Opinion", and retracted papers are excluded. The site links to and labels the work of others; it never republishes full articles.

## How it works

```
config/sources.yaml      the approved sources (edit to add or remove one)
config/topics.yaml       the topics and the phrases used to match them
notes/                   the Editor's Notes (one Markdown file per note)
scripts/fetch.py         collects, filters, tags and saves the items
scripts/build_notes.py   turns notes/ into docs/data/notes.json
scripts/build_feed.py    writes the RSS feed (docs/feed.xml)
scripts/health_alert.py  opens/closes the "needs attention" issue
scripts/audit_links.py   on-demand link, free-access and deployment audit
docs/                    the website (served by GitHub Pages)
docs/data/               items, status, notes and daily editions
.github/workflows/       daily edition, notes publishing, link audit
```

Each morning (6:17 AM Manila, with backup runs at 7:47 AM, 10:17 AM and 5:47 PM because GitHub sometimes skips scheduled runs), GitHub Actions runs `scripts/fetch.py`, which:

- reads news feeds (RSS), journal papers through [OpenAlex](https://openalex.org) and PsyArXiv preprints through the OSF API;
- runs two targeted research searches (core constructs, and authors at Philippine institutions) limited to DOAJ-listed journals with an h-index of 30+, English, with the topic in the title;
- applies a **freshness window** per source (7 days for news, 30 for analysis and preprints, 60 for research and reports) using the real publication date;
- drops items with no date, paywalled papers, retracted papers and anything that doesn't match a topic;
- labels each item from its **headline**: a broad word (like "AI" or "readiness") counts only when the headline is also about work. If the headline names no topic, news, reports and the curated change journals may use a specific phrase from the summary instead; research searches and preprints may not. Each label's evidence (the phrase, and whether it came from the headline) is saved with the item;
- for news and analysis only, also counts change events (an overhaul, layoffs, a return-to-office rule, an AI rollout) when the story names workers, staff or jobs; sponsored posts and reader call-outs are skipped;
- removes duplicates, tags topics and the regional filter, and saves the result;
- records which sources worked in `docs/data/status.json`, shown on the site's "About & sources" page;
- saves the day's edition in `docs/data/editions/` so readers can browse past days under "Past Editions".

Items and editions stay available for a year. The same run then publishes any Editor's Notes scheduled for that day, rebuilds the RSS feed, and opens a GitHub issue ("Daily edition needs attention") if the run or three or more sources fail, closing it when runs are healthy again.

## Site features

- Today's Dispatch, Front Page (core topics), Research Desk, Philippines & SE Asia, a page per topic, Archive (a year, searchable)
- Topics menu with the number of current items per topic; a topic page with few current items also shows recent older ones under "Earlier in the archive"
- Past Editions: each day's reading list, with day-to-day navigation
- Editor's Notes: a monthly note by the editor
- Cite (APA 7) on every item, copied with italics for Word or Google Docs
- RSS feed for feed reader apps (no sign-up, no reader data collected)
- About & Sources: the editor, the inclusion policy, live source status, correction and source-suggestion forms
- A notice when data is more than 30 hours old; link previews for social media

## Editing without code

- **Add or remove a source:** edit `config/sources.yaml` on GitHub (pencil icon), copy an existing block, change it, and commit.
- **Remove one item:** add its link and a short reason to `config/removed.yaml`; it disappears at the next update and stays out.
- **Adjust a topic:** edit the phrases in `config/topics.yaml`.
- **Run an update now:** Actions tab → Daily edition → Run workflow.
- **Write an Editor's Note:** see `notes/README.md`; copy `notes/_template.md` into a new file and commit.
- **Check a suggested feed before adding it:** Actions tab → Check candidate feeds → Run workflow, paste the feed address. It reports whether the site allows automated readers and shows recent headlines and links.
- **Weekly review:** every Monday at 8:47 AM Manila a GitHub issue lists the week's new items (news first). Skim it, remove anything off-topic via `config/removed.yaml`, then close the issue. Run it anytime: Actions tab → Weekly review → Run workflow.
- **Check every link:** Actions tab → Audit links → Run workflow (also confirms each research paper's free-access status and that the live site matches this repository).

## Setup (one time)

1. Add a repository secret named `OPENALEX_API_KEY` with a free key from [openalex.org/settings/api](https://openalex.org/settings/api).
2. Settings → Pages → Build and deployment → Source: *Deploy from a branch*, Branch: `main`, folder: `/docs`.
3. Actions tab → Daily edition → Run workflow, to publish the first edition.

## Security notes

- The daily workflow's GitHub actions are pinned to exact commits, and every Python package is installed with `--require-hashes` against the checksums in `requirements.txt` (generated from `requirements.in`).
- Only http(s) links from sources reach the site, and the page has a strict Content Security Policy.
- The Libre Franklin font is served from `docs/fonts` (SIL Open Font License, `docs/fonts/OFL.txt`); the site loads nothing from other servers.

To update packages: edit `requirements.in`, then run `uv pip compile requirements.in --generate-hashes --python-version 3.12 -o requirements.txt`.

## Running it on your own computer

```
pip install --require-hashes -r requirements.txt
python -m pytest tests          # filtering rules, notes, feed, citations
node tests/apa.test.js          # APA 7 formatter
OPENALEX_API_KEY=your_key python scripts/fetch.py
```

Then open `docs/index.html` through a local web server, for example `python -m http.server -d docs`.

## License

Code: MIT (see `LICENSE`). The compiled item list in `docs/data` is released under CC0; titles and linked content belong to their original publishers.

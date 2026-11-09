# The Change Dispatch

*Open, verified news and research on organizational change, AI, psychology and economics.*

The Change Dispatch is a free, open-source digest that updates itself every morning (Manila time). It collects new items from a public list of trusted sources, keeps only those that are **recent, free to read and on-topic**, labels each one, and publishes them as a newspaper-style website.

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
config/sources.yaml   the approved sources (edit to add or remove one)
config/topics.yaml    the topics and the phrases used to match them
scripts/fetch.py      collects, filters, tags and saves the items
docs/                 the website (served by GitHub Pages)
docs/data/            items.json and status.json, rewritten each day
.github/workflows/    the daily schedule
```

Each morning, GitHub Actions runs `scripts/fetch.py`, which:

- reads news feeds (RSS), journal papers through [OpenAlex](https://openalex.org) and PsyArXiv preprints through the OSF API;
- applies a **freshness window** per source (7 days for news, 14 for analysis, 30 for preprints, 60 for research and reports) using the real publication date;
- drops items with no date, paywalled papers, retracted papers and anything that doesn't match a topic;
- removes duplicates, tags topics and the regional filter, and saves the result;
- records which sources worked in `docs/data/status.json`, shown on the site's "About & sources" page.

Items stay in the searchable archive for a year.

## Editing without code

- **Add or remove a source:** edit `config/sources.yaml` on GitHub (pencil icon), copy an existing block, change it, and commit.
- **Adjust a topic:** edit the phrases in `config/topics.yaml`.
- **Run an update now:** Actions tab → Daily edition → Run workflow.

## Setup (one time)

1. Add a repository secret named `OPENALEX_API_KEY` with a free key from [openalex.org/settings/api](https://openalex.org/settings/api).
2. Settings → Pages → Build and deployment → Source: *Deploy from a branch*, Branch: `main`, folder: `/docs`.
3. Actions tab → Daily edition → Run workflow, to publish the first edition.

## Running it on your own computer

```
pip install -r requirements.txt
python -m pytest tests          # check the filtering rules
OPENALEX_API_KEY=your_key python scripts/fetch.py
```

Then open `docs/index.html` through a local web server, for example `python -m http.server -d docs`.

## License

Code: MIT (see `LICENSE`). The compiled item list in `docs/data` is released under CC0; titles and linked content belong to their original publishers.

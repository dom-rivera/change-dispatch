"""The Change Dispatch: daily fetcher.

Reads config/sources.yaml and config/topics.yaml, collects new items from
every enabled source, keeps only items that are recent, free to read and
on-topic, and writes:

    docs/data/items.json   every item currently on the site (and archive)
    docs/data/status.json  how each source did on this run

Run it with:  python scripts/fetch.py
The OpenAlex key is read from the OPENALEX_API_KEY environment variable
(a GitHub secret in the daily workflow). Without it, journal sources are
skipped and reported as such.
"""

from __future__ import annotations

import calendar
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "docs" / "data"

ARCHIVE_DAYS = 365          # items older than this leave the site entirely
STALE_SOURCE_DAYS = 60      # a source with nothing newer than this is flagged
MAX_FUTURE_SKEW = timedelta(days=2)
USER_AGENT = (
    "ChangeDispatchBot/1.0 "
    "(+https://github.com/dom-rivera/change-dispatch; open-source news digest)"
)
OPENALEX = "https://api.openalex.org"
OSF = "https://api.osf.io/v2"

LAYER_LABELS = {
    "research": "Peer-reviewed",
    "preprint": "Preprint",
    "institutional": "Institutional",
    "analysis": "Expert analysis",
    "news": "News",
}

NOW = datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def load_yaml(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def clean_text(raw: str | None) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def item_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def date_ok(published: datetime | None, window_days: int) -> bool:
    """Freshness gate: the item must have a real date inside the window."""
    if published is None:
        return False  # rule: every item needs a clear publication date
    if published > NOW + MAX_FUTURE_SKEW:
        return False
    return published >= NOW - timedelta(days=window_days)


# --------------------------------------------------------------------------
# Topic matching
# --------------------------------------------------------------------------

def _compile(phrases: list[str]) -> list[re.Pattern]:
    return [
        re.compile(r"(?<!\w)" + re.escape(p.strip()) + r"(?!\w)", re.IGNORECASE)
        for p in phrases or []
        if p and p.strip()
    ]


class TopicMatcher:
    def __init__(self, cfg: dict):
        self.topics = []
        for group in ("core", "context"):
            for t in cfg.get(group, []):
                self.topics.append({
                    "id": t["id"],
                    "group": group,
                    "match": _compile(t.get("match")),
                    "weak": _compile(t.get("weak")),
                    "exclude": _compile(t.get("exclude")),
                    "news_weak": _compile(t.get("news_weak")),
                })
        self.work_context = _compile(cfg.get("work_context"))
        self.news_context = _compile(cfg.get("news_context"))
        region = cfg.get("region", {})
        self.region_match = _compile(region.get("match"))
        self.region_countries = {c.upper() for c in region.get("author_countries", [])}

    def has_work_context(self, text: str) -> bool:
        return any(p.search(text) for p in self.work_context)

    def has_news_context(self, text: str) -> bool:
        return any(p.search(text) for p in self.news_context)

    def explain(self, text: str, news: bool = False) -> dict[str, dict]:
        """Which topics apply, and why: the phrase that matched and whether
        it was a strong phrase, a weak one (needs a work word) or a
        news-only change event (needs a worker word).

        Strong phrases tag a topic on their own. Weak phrases (broad words
        like "automation") only count when the text is also about work or
        organizations. For news and analysis only, "news_weak" change-event
        phrases (like "overhaul") count when the story also names workers,
        staff or jobs (the stricter news_context list)."""
        def first(patterns):
            for p in patterns:
                m = p.search(text)
                if m:
                    return m.group(0).lower()
            return None

        found: dict[str, dict] = {}
        work = None
        staff = None
        for t in self.topics:
            if any(p.search(text) for p in t["exclude"]):
                continue
            phrase = first(t["match"])
            kind = "strong"
            if phrase is None and t["weak"]:
                phrase = first(t["weak"])
                if phrase is not None:
                    if work is None:
                        work = self.has_work_context(text)
                    phrase = phrase if work else None
                    kind = "weak"
            if phrase is None and news and t["news_weak"]:
                phrase = first(t["news_weak"])
                if phrase is not None:
                    if staff is None:
                        staff = self.has_news_context(text)
                    phrase = phrase if staff else None
                    kind = "news"
            if phrase is not None:
                found[t["id"]] = {"phrase": phrase, "kind": kind}
        return found

    def topics_for(self, text: str, news: bool = False) -> list[str]:
        return list(self.explain(text, news))

    def is_regional(self, text: str, countries: set[str] | None = None) -> bool:
        if countries and countries & self.region_countries:
            return True
        return any(p.search(text) for p in self.region_match)


# --------------------------------------------------------------------------
# Fetchers. Each returns (candidates, info) where a candidate is a dict with
# title, url, published (datetime), text (for matching only), and extras.
# --------------------------------------------------------------------------

def http_get(session: requests.Session, url: str, **kw) -> requests.Response:
    last_exc = None
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=40, **kw)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(3 * (attempt + 1))
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}")
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:  # network trouble: retry
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(key)
        if st:
            return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
    return None


OPINION_HINTS = ("/opinion", "/commentisfree", "/columnists/", "/editorial")


def parse_feed(content: bytes) -> list[dict]:
    feed = feedparser.parse(content)
    if not feed.entries:
        raise ValueError("no entries found (not a valid feed?)")
    out = []
    for e in feed.entries:
        # NBER-style titles end with " -- by Author, Author"; keep the title only
        raw_title = clean_text(e.get("title"))
        byline = re.search(r"\s+--\s+by\s+(.*)$", raw_title)
        title = re.sub(r"\s+--\s+by\s+.*$", "", raw_title)
        authors = ([a.strip() for a in re.split(r",\s*|\s+and\s+|\s*&\s*", byline.group(1)) if a.strip()]
                   if byline else feed_authors(e))
        link = re.sub(r"#fromrss$", "", e.get("link") or "")
        if not title or not link.startswith("http"):
            continue
        tags = " ".join(
            (t.get("term") or "") for t in e.get("tags", []) if isinstance(t, dict)
        ).lower()
        summary = clean_text(e.get("summary") or e.get("description"))
        out.append({
            "title": title,
            "url": link,
            "published": entry_datetime(e),
            "text": f"{title} {summary} {tags}",
            "opinion": any(h in link.lower() for h in OPINION_HINTS)
            or "opinion" in tags.split(),
            "countries": set(),
            "cite": {"kind": "web", "authors": authors},
        })
    return out


def fetch_rss(session, src) -> tuple[list[dict], dict]:
    """Read a source's feeds. Normally the first feed that works is used;
    with combine: true every listed feed is read (e.g. several topic
    sections of one outlet) and duplicates are dropped. Links matching an
    exclude_urls pattern (e.g. sponsored posts) and titles matching an
    exclude_titles pattern (e.g. reader call-outs) are skipped."""
    errors, used, cands, seen = [], [], [], set()
    skip = [re.compile(p) for p in src.get("exclude_urls", [])]
    skip_titles = [re.compile(p, re.I) for p in src.get("exclude_titles", [])]
    for url in src.get("feeds", []):
        try:
            resp = http_get(session, url)
        except Exception as exc:  # try the next candidate feed
            errors.append(f"{url}: {exc}")
            continue
        used.append(url)
        for c in parse_feed(resp.content):
            link = c.get("url") or ""
            if (link in seen or any(p.search(link) for p in skip)
                    or any(p.search(c.get("title") or "") for p in skip_titles)):
                continue
            seen.add(link)
            cands.append(c)
        if not src.get("combine"):
            break
    if not used:
        raise RuntimeError("; ".join(errors) or "no feeds listed")
    info = {"feed_used": used[0] if len(used) == 1 else used}
    if errors:
        info["feeds_failed"] = errors
    return cands, info


def openalex_params(api_key: str, **params) -> dict:
    params["api_key"] = api_key
    return params


def resolve_journal(session, api_key, src) -> tuple[str, str]:
    """Find the OpenAlex source ID for a journal (by ISSN, then by name)."""
    if src.get("openalex_id"):
        return src["openalex_id"], src["name"]
    if src.get("issn"):
        resp = http_get(session, f"{OPENALEX}/sources", params=openalex_params(
            api_key, filter="issn:" + "|".join(src["issn"]), per_page=5))
        results = resp.json().get("results", [])
        if results:
            return results[0]["id"], results[0].get("display_name", src["name"])
    names = src.get("journal", src["name"])
    names = names if isinstance(names, list) else [names]
    seen = []
    for name in names:
        wanted = norm_title(name).removeprefix("the ")
        resp = http_get(session, f"{OPENALEX}/sources", params=openalex_params(
            api_key, search=name, per_page=10))
        for r in resp.json().get("results", []):
            got = r.get("display_name", "")
            seen.append(got)
            if norm_title(got).removeprefix("the ") == wanted:
                return r["id"], got
    hint = "; closest names in OpenAlex: " + ", ".join(dict.fromkeys(seen[:6])) if seen else ""
    raise LookupError(f"not found in OpenAlex: {', '.join(names)}{hint}")


def abstract_text(inverted: dict | None) -> str:
    """Rebuild an abstract from OpenAlex's inverted index (used only for
    topic matching; abstracts are never shown on the site)."""
    if not inverted:
        return ""
    slots = {}
    for word, positions in inverted.items():
        for pos in positions:
            slots[pos] = word
    return " ".join(slots[i] for i in sorted(slots))


def fetch_openalex(session, src, api_key) -> tuple[list[dict], dict]:
    if not api_key:
        raise RuntimeError("OPENALEX_API_KEY is not set; journal skipped")
    source_id, display = resolve_journal(session, api_key, src)
    short_id = source_id.rsplit("/", 1)[-1]
    since = (NOW - timedelta(days=src["window_days"])).strftime("%Y-%m-%d")
    filt = ",".join([
        f"primary_location.source.id:{short_id}",
        f"from_publication_date:{since}",
        "is_retracted:false",  # never show retracted papers
        "type:" + src.get("types", "article|review"),
    ] + ([] if src.get("publisher_free") else ["is_oa:true"]))  # free-to-read rule
    out, cursor, pages = [], "*", 0
    while cursor and pages < 5:
        resp = http_get(session, f"{OPENALEX}/works", params=openalex_params(
            api_key, filter=filt, per_page=100, cursor=cursor,
            select="id,doi,display_name,publication_date,open_access,biblio,"
                   "primary_location,authorships,abstract_inverted_index,is_retracted"))
        body = resp.json()
        for w in body.get("results", []):
            oa_url = (w.get("open_access") or {}).get("oa_url")
            if not oa_url and src.get("publisher_free"):
                # Publisher makes everything free to read (e.g. OECD since
                # July 2024), even where OpenAlex has not caught up.
                oa_url = w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url")
            title = clean_text(w.get("display_name"))
            if not oa_url or not title or w.get("is_retracted"):
                continue
            countries = set()
            for a in w.get("authorships") or []:
                countries.update(c.upper() for c in a.get("countries") or [])
                for inst in a.get("institutions") or []:
                    if inst.get("country_code"):
                        countries.add(inst["country_code"].upper())
            out.append({
                "title": title,
                "url": oa_url,
                "doi": w.get("doi"),
                "published": parse_iso(w.get("publication_date") or ""),
                "text": f"{title} {abstract_text(w.get('abstract_inverted_index'))}",
                "opinion": False,
                "countries": countries,
                "cite": openalex_cite(w, display,
                                      "report" if src.get("layer") == "institutional" else "journal"),
            })
        cursor = (body.get("meta") or {}).get("next_cursor")
        pages += 1
    info = {"openalex_source": source_id, "journal_matched": display}
    if not out:
        # Explain empty results: how many recent works exist at all, and
        # how many are free to read, so the status page shows why.
        diag = {}
        for label, extra in (("recent_any_type", ""), ("recent_free", ",is_oa:true")):
            resp = http_get(session, f"{OPENALEX}/works", params=openalex_params(
                api_key, per_page=1, select="id",
                filter=f"primary_location.source.id:{short_id},"
                       f"from_publication_date:{since}{extra}"))
            diag[label] = (resp.json().get("meta") or {}).get("count")
        resp = http_get(session, f"{OPENALEX}/works", params=openalex_params(
            api_key, per_page=1, select="publication_date",
            filter=f"primary_location.source.id:{short_id}",
            sort="publication_date:desc"))
        latest = resp.json().get("results") or [{}]
        diag["latest_in_openalex"] = latest[0].get("publication_date")
        info["diagnostic"] = diag
    return out, info


def _openalex_work_to_cand(w: dict) -> dict | None:
    oa_url = (w.get("open_access") or {}).get("oa_url")
    title = clean_text(w.get("display_name"))
    if not oa_url or not title or w.get("is_retracted"):
        return None
    countries = set()
    for a in w.get("authorships") or []:
        countries.update(c.upper() for c in a.get("countries") or [])
        for inst in a.get("institutions") or []:
            if inst.get("country_code"):
                countries.add(inst["country_code"].upper())
    source = ((w.get("primary_location") or {}).get("source") or {})
    return {
        "title": title,
        "url": oa_url,
        "doi": w.get("doi"),
        "published": parse_iso(w.get("publication_date") or ""),
        "text": f"{title} {abstract_text(w.get('abstract_inverted_index'))}",
        "opinion": False,
        "countries": countries,
        "source_name": source.get("display_name"),
        "cite": openalex_cite(w, source.get("display_name")),
    }


def fetch_openalex_search(session, src, api_key) -> tuple[list[dict], dict]:
    """Targeted research search: find new open-access journal articles that
    mention a core construct in their title or abstract.

    Safeguards: journal articles only, free to read, not retracted, and the
    journal must be listed in the Directory of Open Access Journals (DOAJ),
    which screens journals for quality and transparent peer review.
    Journals named in "exclude_journals" are skipped.
    """
    if not api_key:
        raise RuntimeError("OPENALEX_API_KEY is not set; search skipped")
    since = (NOW - timedelta(days=src["window_days"])).strftime("%Y-%m-%d")
    excluded = {norm_title(j) for j in src.get("exclude_journals", [])}
    out, seen, per_query, errors = [], set(), {}, []
    for phrase in src["queries"]:
        phrase = phrase.replace('"', "").replace(",", " ").strip()
        filt = ",".join([
            f'title_and_abstract.search:"{phrase}"',
            f"from_publication_date:{since}",
            "is_oa:true",
            "is_retracted:false",
            "type:article|review",
            "primary_location.source.type:journal",
            "language:en",
        ] + (["primary_location.source.is_in_doaj:true"] if src.get("doaj_only", True) else [])
          + ([src["extra_filter"]] if src.get("extra_filter") else []))
        try:
            resp = http_get(session, f"{OPENALEX}/works", params=openalex_params(
                api_key, filter=filt, per_page=src.get("per_phrase", 25), sort="publication_date:desc",
                select="id,doi,display_name,publication_date,open_access,biblio,"
                       "primary_location,authorships,abstract_inverted_index,is_retracted"))
        except Exception as exc:  # keep going with the other phrases
            errors.append(f"{phrase}: {str(exc)[:120]}")
            continue
        results = resp.json().get("results", [])
        per_query[phrase] = len(results)
        for w in results:
            cand = _openalex_work_to_cand(w)
            if not cand or norm_title(cand.get("source_name") or "") in excluded:
                continue
            key = (cand.get("doi") or cand["url"]).lower()
            if key in seen:
                continue
            seen.add(key)
            cand["source_id"] = ((w.get("primary_location") or {}).get("source") or {}).get("id")
            out.append(cand)
    if errors and not per_query:
        raise RuntimeError("; ".join(errors))

    # Keep only established journals: h-index (how widely the journal's
    # papers are cited) at or above the minimum.
    min_h = src.get("min_h_index", 30)
    ids = sorted({c["source_id"].rsplit("/", 1)[-1] for c in out if c.get("source_id")})
    h_index = {}
    for sid in ids:  # single-record lookups are free under OpenAlex's pricing
        try:
            resp = http_get(session, f"{OPENALEX}/sources/{sid}", params=openalex_params(
                api_key, select="id,summary_stats"))
            h_index[sid] = (resp.json().get("summary_stats") or {}).get("h_index") or 0
        except Exception:
            h_index[sid] = 0  # unknown journal: treat as not established
    before = len(out)
    out = [c for c in out
           if h_index.get((c.get("source_id") or "").rsplit("/", 1)[-1], 0) >= min_h]
    info = {"results_per_phrase": per_query,
            "dropped_low_h_index": before - len(out), "min_h_index": min_h}
    if errors:
        info["phrase_errors"] = errors
    return out, info


def fetch_osf(session, src) -> tuple[list[dict], dict]:
    since = (NOW - timedelta(days=src["window_days"])).strftime("%Y-%m-%d")
    base = f"{OSF}/preprints/"
    params = {
        "filter[provider]": src.get("provider", "psyarxiv"),
        "filter[date_published][gte]": since,
        "page[size]": 100,
    }
    out, url, pages = [], base, 0
    while url and pages < src.get("max_pages", 30):
        resp = http_get(session, url, params=params if url == base else None)
        body = resp.json()
        for p in body.get("data", []):
            a = p.get("attributes", {})
            if a.get("date_withdrawn") or a.get("reviews_state") in ("rejected", "withdrawn"):
                continue
            title = clean_text(a.get("title"))
            link = (p.get("links") or {}).get("html")
            if not title or not link:
                continue
            doi = (p.get("links") or {}).get("preprint_doi") or a.get("doi")
            if doi and not doi.startswith("http"):
                doi = "https://doi.org/" + doi
            out.append({
                "title": title,
                "url": link,
                "doi": doi,
                "published": parse_iso(a.get("date_published") or ""),
                "text": f"{title} {clean_text(a.get('description'))}",
                "opinion": False,
                "countries": set(),
                "osf_id": p.get("id"),
                "cite": {"kind": "preprint", "authors": [], "container": "PsyArXiv", "doi": doi},
            })
        url = (body.get("links") or {}).get("next")
        pages += 1
    return out, {}


# --------------------------------------------------------------------------
# Citation details (used by the site's "Cite in APA 7" button)
# --------------------------------------------------------------------------

def openalex_cite(w: dict, container: str | None, kind: str = "journal") -> dict:
    biblio = w.get("biblio") or {}
    authors = [((a.get("author") or {}).get("display_name") or "").strip()
               for a in (w.get("authorships") or [])]
    return {
        "kind": kind,
        "authors": [a for a in authors if a][:40],
        "container": container,
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "first_page": biblio.get("first_page"),
        "last_page": biblio.get("last_page"),
        "doi": w.get("doi"),
    }


def feed_authors(entry) -> list[str]:
    names = [clean_text(a.get("name")) for a in entry.get("authors", []) if isinstance(a, dict)]
    names = [n for n in names if n]
    if not names and entry.get("author"):
        names = [clean_text(entry.get("author"))]
    # Bylines like "By Jane Cruz and Ana Reyes" or "Jane Cruz, Ana Reyes"
    out = []
    for n in names:
        n = re.sub(r"^by\s+", "", n, flags=re.I)
        for x in re.split(r",\s*|\s+and\s+|\s*&\s*", n):
            x = clean_byline(x)
            if x:
                out.append(x)
    return out[:20]


ROLE_WORDS = (r"editor|correspondent|reporter|writer|columnist|analyst|journalist|"
              r"contributor|staff|desk|producer|presenter")
ROLE_DESCRIPTORS = (r"business|technology|tech|global|economics|economic|senior|chief|deputy|"
                    r"political|social|affairs|policy|financial|finance|money|consumer|industry|"
                    r"employment|work|workplace|media|science|health|education|foreign|world|"
                    r"international|national|news|data|investigations|digital|labour|labor|"
                    r"special|associate|contributing|staff")


def clean_byline(name: str) -> str:
    """Drop job titles and places from bylines, e.g. 'Jane Doe Business
    editor' -> 'Jane Doe', 'Ana Cruz in Manila' -> 'Ana Cruz'. Returns ''
    for entries that are only a role ('Staff reporter')."""
    name = re.sub(r"\s+in\s+[A-Z][\w .'-]*$", "", name.strip())
    m = re.match(r"^(.*?)(?:\s+(?:(?:%s)\s+){0,3}(?:%s))$" % (ROLE_DESCRIPTORS, ROLE_WORDS), name, flags=re.I)
    if m:
        name = m.group(1).strip()
    if re.fullmatch(r"(?:[A-Za-z]+\s+){0,3}(?:%s)" % ROLE_WORDS, name, flags=re.I):
        return ""
    return name.strip(" ,;")


def osf_authors(session, preprint_id: str) -> list[str]:
    try:
        resp = http_get(session, f"{OSF}/preprints/{preprint_id}/contributors/",
                        params={"embed": "users", "page[size]": 50})
        names = []
        for c in resp.json().get("data", []):
            if not (c.get("attributes") or {}).get("bibliographic", True):
                continue
            user = (((c.get("embeds") or {}).get("users") or {}).get("data") or {})
            name = ((user.get("attributes") or {}).get("full_name") or "").strip()
            if name:
                names.append(name)
        return names
    except Exception:
        return []


# --------------------------------------------------------------------------
# Main pipeline
# --------------------------------------------------------------------------

def safe_url(url: str | None) -> bool:
    """Only plain web links may reach the site (no javascript:, data:, etc.)."""
    if not url or any(c in url for c in "\r\n\t \"'<>"):
        return False
    parts = urlparse(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def cite_for(cand: dict, src: dict) -> dict:
    cite = dict(cand.get("cite") or {})
    kind = cite.get("kind")
    if src["layer"] == "preprint" and kind != "preprint":
        kind = "working_paper" if src["id"] == "nber" else "preprint"
    elif src["layer"] in ("news", "analysis"):
        kind = "news"
    elif src["layer"] == "institutional" and kind != "report":
        kind = "report" if kind == "journal" else "web"
    cite["kind"] = kind or "web"
    cite.setdefault("authors", [])
    if not cite.get("container"):
        # the site name for news and web items, e.g. "The Guardian"
        cite["container"] = re.sub(r"\s*\(.*\)$", "", src["name"])
    if cite["kind"] == "working_paper":
        cite["publisher"] = "National Bureau of Economic Research"
    if not cite.get("doi") and cand.get("doi"):
        cite["doi"] = cand["doi"]
    return {k: v for k, v in cite.items() if v not in (None, "", [])} | {"authors": cite["authors"]}


def build_item(cand: dict, src: dict, matcher: TopicMatcher) -> dict | None:
    if not safe_url(cand.get("url")):
        return None
    estimated = False
    if cand["published"] is None and src.get("date_fallback") == "first_seen":
        # Only for feeds that list new releases but carry no dates (e.g.
        # NBER). The item is dated the day it first appears; merge() keeps
        # that first date on later runs.
        cand["published"] = NOW
        estimated = True
    if not date_ok(cand["published"], src["window_days"]):
        return None
    if src.get("require_work_context") and not matcher.has_work_context(cand["text"]):
        return None
    news = src["layer"] in ("news", "analysis")
    why = matcher.explain(cand["text"], news=news)
    topics = list(why)
    if src.get("needs_topic", True) and not topics:
        return None
    if src.get("require_title_match") and not matcher.topics_for(cand["title"], news=news):
        return None
    key = (cand.get("doi") or cand["url"]).lower()
    labels = []
    if src["layer"] == "preprint":
        labels.append("Not yet peer-reviewed")
    if cand.get("opinion"):
        labels.append("Opinion")
    return {
        "id": item_id(key),
        "title": cand["title"],
        "url": cand["url"],
        "source": cand.get("source_name") or src["name"],
        "source_id": src["id"],
        "layer": src["layer"],
        "type": LAYER_LABELS[src["layer"]],
        "published": iso(cand["published"]),
        "first_seen": iso(NOW),
        "window_days": src["window_days"],
        "topics": topics,
        # Evidence for each topic label: the phrase that matched, its kind,
        # and whether it is in the headline (else in the summary/abstract).
        "why": {t: dict(w, in_title=bool(re.search(r"(?<!\w)" + re.escape(w["phrase"]) + r"(?!\w)",
                                                   cand["title"], re.I)))
                for t, w in why.items()},
        "region": bool(src.get("regional")) or matcher.is_regional(cand["text"], cand.get("countries")),
        "labels": labels,
        "access": "Free to read",
        "cite": cite_for(cand, src),
        **({"date_estimated": True} if estimated else {}),
    }


def removed_urls() -> set[str]:
    """Links the editor removed by hand (config/removed.yaml)."""
    path = CONFIG / "removed.yaml"
    if not path.exists():
        return set()
    cfg = load_yaml("removed.yaml") or {}
    return {str(r["url"]).strip() for r in cfg.get("removed") or [] if r.get("url")}


def drop_removed(items: list[dict], urls: set[str]) -> list[dict]:
    return [i for i in items if i["url"] not in urls and (i.get("doi") or "") not in urls]


def merge(existing: list[dict], fresh: list[dict], enabled_ids: set[str]) -> list[dict]:
    """Combine today's items with the archive, dropping duplicates and
    anything past the archive limit or from a removed source."""
    cutoff = NOW - timedelta(days=ARCHIVE_DAYS)
    by_id: dict[str, dict] = {}
    seen_titles: set[str] = set()
    for item in fresh + existing:   # fresh first so updated details win
        if item["source_id"] not in enabled_ids:
            continue
        published = parse_iso(item["published"])
        if not published or published < cutoff:
            continue
        nt = norm_title(item["title"])
        if item["id"] in by_id or nt in seen_titles:
            # keep the earliest first_seen date (and, for items without a
            # real date, the earliest estimated publication date)
            prev = by_id.get(item["id"])
            if prev and item.get("first_seen", "") < prev.get("first_seen", ""):
                prev["first_seen"] = item["first_seen"]
                if prev.get("date_estimated"):
                    prev["published"] = min(prev["published"], item["published"])
            continue
        by_id[item["id"]] = item
        seen_titles.add(nt)
    return sorted(by_id.values(), key=lambda i: i["published"], reverse=True)


MANILA = timezone(timedelta(hours=8))


def write_edition(items: list[dict]) -> dict:
    """Save today's edition (Manila date) so readers can go back to it.

    An edition file lists the IDs of every item that was current on the
    site that day, and which of them were new that day. The full item
    details stay in items.json for a year. A second run on the same day
    replaces that day's file.
    """
    ed_dir = DATA / "editions"
    ed_dir.mkdir(parents=True, exist_ok=True)
    today = NOW.astimezone(MANILA).strftime("%Y-%m-%d")

    current, new = [], []
    for item in items:
        published = parse_iso(item["published"])
        if published and published >= NOW - timedelta(days=item["window_days"]):
            current.append(item["id"])
            seen = parse_iso(item.get("first_seen", ""))
            if seen and seen.astimezone(MANILA).strftime("%Y-%m-%d") == today:
                new.append(item["id"])

    (ed_dir / f"{today}.json").write_text(json.dumps(
        {"date": today, "generated": iso(NOW), "items": current, "new": new},
        ensure_ascii=False), encoding="utf-8")

    # Rebuild the index from the files on disk; drop editions older than
    # the archive limit (their items are gone from items.json anyway).
    cutoff = (NOW - timedelta(days=ARCHIVE_DAYS)).astimezone(MANILA).strftime("%Y-%m-%d")
    editions = []
    for path in sorted(ed_dir.glob("????-??-??.json"), reverse=True):
        if path.stem < cutoff:
            path.unlink()
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        editions.append({"date": data["date"], "count": len(data["items"]),
                         "new": len(data["new"])})
    (ed_dir / "index.json").write_text(json.dumps(
        {"generated": iso(NOW), "editions": editions}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return {"date": today, "count": len(current), "new": len(new)}


def main() -> int:
    sources_cfg = load_yaml("sources.yaml")
    matcher = TopicMatcher(load_yaml("topics.yaml"))
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()

    DATA.mkdir(parents=True, exist_ok=True)
    items_path = DATA / "items.json"
    existing = []
    if items_path.exists():
        existing = json.loads(items_path.read_text(encoding="utf-8")).get("items", [])

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    fresh, status = [], []
    enabled = [s for s in sources_cfg["sources"] if s.get("enabled", True)]
    for src in enabled:
        entry = {"id": src["id"], "name": src["name"], "layer": src["layer"],
                 "ok": False, "found": 0, "kept": 0, "error": None}
        try:
            if src["kind"] == "rss":
                cands, info = fetch_rss(session, src)
            elif src["kind"] == "openalex":
                cands, info = fetch_openalex(session, src, api_key)
            elif src["kind"] == "openalex_search":
                cands, info = fetch_openalex_search(session, src, api_key)
            elif src["kind"] == "osf":
                cands, info = fetch_osf(session, src)
            else:
                raise ValueError(f"unknown kind: {src['kind']}")
            entry.update(info)
            entry["ok"] = True
            entry["found"] = len(cands)
            dated = [c["published"] for c in cands if c["published"]]
            if dated:
                newest = max(dated)
                entry["newest_item"] = iso(newest)
                entry["stale"] = newest < NOW - timedelta(days=STALE_SOURCE_DAYS)
            for c in cands:
                item = build_item(c, src, matcher)
                if item:
                    if src["kind"] == "osf" and c.get("osf_id"):
                        item["cite"]["authors"] = osf_authors(session, c["osf_id"])
                    fresh.append(item)
                    entry["kept"] += 1
        except Exception as exc:
            entry["error"] = str(exc)[:500]
        status.append(entry)
        state = "ok" if entry["ok"] else "FAILED"
        print(f"[{state:6}] {src['id']:22} found={entry['found']:4} "
              f"kept={entry['kept']:3} {entry['error'] or ''}")

    items = merge(existing, fresh, {s["id"] for s in enabled})
    items = drop_removed(items, removed_urls())

    topics_cfg = load_yaml("topics.yaml")
    topic_names = [
        {"id": t["id"], "name": t["name"], "group": group}
        for group in ("core", "context") for t in topics_cfg.get(group, [])
    ]
    region = topics_cfg.get("region", {})

    items_path.write_text(json.dumps(
        {"generated": iso(NOW), "count": len(items),
         "topics": topic_names,
         "region": {"id": region.get("id", "ph-sea"),
                    "name": region.get("name", "Philippines & Southeast Asia")},
         "items": items},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "status.json").write_text(json.dumps(
        {"generated": iso(NOW),
         "openalex_key_present": bool(api_key),
         "sources": status},
        ensure_ascii=False, indent=1), encoding="utf-8")

    edition = write_edition(items)

    ok = sum(1 for s in status if s["ok"])
    print(f"\n{ok}/{len(status)} sources worked; {len(fresh)} new items kept; "
          f"{len(items)} items on the site; edition {edition['date']}: "
          f"{edition['count']} items, {edition['new']} new.")
    # Never fail the whole run because some sources are down; the status
    # file and the site's sources page show what went wrong.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

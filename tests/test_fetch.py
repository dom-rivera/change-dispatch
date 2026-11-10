"""Checks for the filtering rules. Run with:  python -m pytest tests"""

import sys
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch  # noqa: E402

MATCHER = fetch.TopicMatcher(fetch.load_yaml("topics.yaml"))
NOW = fetch.NOW


def rss(entries):
    items = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        f"<description>{d}</description>"
        + (f"<pubDate>{format_datetime(p)}</pubDate>" if p else "")
        + "</item>"
        for t, l, d, p in entries
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'.encode()


NEWS = {"id": "n", "name": "Test News", "layer": "news", "window_days": 7, "needs_topic": True}
PRE = {"id": "p", "name": "Test Preprints", "layer": "preprint", "window_days": 30, "needs_topic": True}


def build(entries, src=NEWS):
    return [fetch.build_item(c, src, MATCHER) for c in fetch.parse_feed(rss(entries))]


def test_on_topic_recent_item_is_kept_and_tagged():
    [item] = build([("Employees' readiness for change during AI adoption",
                     "https://example.org/a", "A study.", NOW - timedelta(days=1))])
    assert item is not None
    assert "change-readiness" in item["topics"]
    assert "ai-at-work" in item["topics"]
    assert item["access"] == "Free to read"


def test_off_topic_item_is_dropped():
    assert build([("Celebrity wedding photos", "https://example.org/b", "", NOW)]) == [None]


def test_old_item_is_dropped_by_freshness_window():
    assert build([("Burnout rises among nurses", "https://example.org/c", "",
                   NOW - timedelta(days=10))]) == [None]


def test_item_without_date_is_dropped():
    assert build([("Burnout rises among workers", "https://example.org/d", "", None)]) == [None]


def test_future_dated_item_is_dropped():
    assert build([("Burnout rises among workers", "https://example.org/e", "",
                   NOW + timedelta(days=10))]) == [None]


def test_preprint_label_and_opinion_label():
    [pre] = build([("Resistance to change in schools", "https://example.org/f", "",
                    NOW - timedelta(days=2))], PRE)
    assert "Not yet peer-reviewed" in pre["labels"]
    [op] = build([("Why remote work is here to stay", "https://example.org/opinion/g", "",
                   NOW - timedelta(days=1))])
    assert "Opinion" in op["labels"]


def test_region_tag_from_text_and_from_author_country():
    [item] = build([("Remote work trends in the Philippines", "https://example.org/h", "",
                     NOW - timedelta(days=1))])
    assert item["region"] is True
    assert MATCHER.is_regional("A study of hybrid work", {"PH"}) is True
    assert MATCHER.is_regional("A study of hybrid work in Germany", {"DE"}) is False


def test_exclusions_and_whole_word_matching():
    # "stock" excludes AI-at-work tagging
    assert "ai-at-work" not in MATCHER.topics_for("AI adoption lifts chip stock")
    # "nudges" must not match inside other words; "unemployment" must match
    assert MATCHER.topics_for("Unemployment falls") == ["labor-economics"]
    assert "behavioral-economics" not in MATCHER.topics_for("nudgesmith")


def test_merge_dedupes_and_keeps_earliest_first_seen():
    a = build([("Change fatigue at work", "https://example.org/i", "", NOW - timedelta(days=1))])[0]
    older = dict(a, first_seen="2020-01-01T00:00:00Z")
    same_title = dict(a, id="other", url="https://mirror.example.org/i")
    merged = fetch.merge([older, same_title], [a], {"n"})
    assert len(merged) == 1
    assert merged[0]["first_seen"] == "2020-01-01T00:00:00Z"


def test_merge_drops_items_from_removed_sources():
    a = build([("Change fatigue at work", "https://example.org/j", "", NOW - timedelta(days=1))])[0]
    assert fetch.merge([a], [], {"some-other-source"}) == []


def test_weak_words_need_work_context():
    # "self-efficacy" alone (clinical) is not enough; with a work context it counts
    assert "self-efficacy" not in MATCHER.topics_for("Self-efficacy in patients with bipolar disorder")
    assert "self-efficacy" in MATCHER.topics_for("Teacher self-efficacy during school reform")
    assert "ai-at-work" not in MATCHER.topics_for("Level of automation and drivers' scanning")
    assert "ai-at-work" in MATCHER.topics_for("Automation and the future of jobs")


def test_source_can_require_work_context():
    src = dict(PRE, require_work_context=True)
    [clinical] = build([("Resistance to change in patients", "https://example.org/k", "",
                         NOW - timedelta(days=1))], src)
    [work] = build([("Resistance to change among employees", "https://example.org/l", "",
                     NOW - timedelta(days=1))], src)
    assert clinical is None and work is not None


def test_undated_feed_uses_first_seen_and_keeps_it():
    src = dict(PRE, date_fallback="first_seen")
    [item] = build([("Labor market effects of AI", "https://example.org/m", "", None)], src)
    assert item is not None and item["date_estimated"]
    earlier = dict(item, published="2026-01-01T00:00:00Z", first_seen="2026-01-01T00:00:00Z")
    [merged] = fetch.merge([earlier], [item], {"p"})
    assert merged["published"] == "2026-01-01T00:00:00Z"


def test_edition_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "DATA", tmp_path)
    fresh = build([("Change fatigue at work", "https://example.org/n", "", NOW - timedelta(hours=2))])[0]
    old = dict(build([("Burnout at work rises", "https://example.org/o", "", NOW - timedelta(days=3))])[0],
               first_seen="2020-01-01T00:00:00Z")
    expired = dict(old, id="gone", published="2020-01-01T00:00:00Z")
    info = fetch.write_edition([fresh, old, expired])
    assert info["count"] == 2 and info["new"] == 1
    import json
    index = json.loads((tmp_path / "editions" / "index.json").read_text())
    assert index["editions"][0]["date"] == info["date"]


def test_unsafe_links_are_rejected():
    for bad in ["javascript:alert(1)", "data:text/html,x", "ftp://x.org/a", "https://x.org/a b", "//x.org"]:
        assert not fetch.safe_url(bad)
    assert fetch.safe_url("https://doi.org/10.1787/abc")
    cand = {"title": "Burnout at work", "url": "javascript:alert(1)", "published": NOW,
            "text": "Burnout at work", "countries": set()}
    assert fetch.build_item(cand, NEWS, MATCHER) is None


def test_abstract_rebuild():
    assert fetch.abstract_text({"readiness": [0], "change": [2], "for": [1]}) == "readiness for change"


def test_core_search_keeps_only_free_work_related_articles(monkeypatch):
    class Resp:
        def __init__(self, body): self.body = body
        def json(self): return self.body
    work = {"display_name": "Readiness for change among nurses during hospital restructuring",
            "doi": "https://doi.org/10.1/a", "publication_date": NOW.strftime("%Y-%m-%d"),
            "open_access": {"oa_url": "https://journal.org/a"},
            "primary_location": {"source": {"display_name": "Frontiers in Psychology"}},
            "authorships": [{"countries": ["PH"]}], "abstract_inverted_index": {"employees": [0]}}
    paywalled = dict(work, doi="https://doi.org/10.1/b", open_access={"oa_url": None})
    clinical = dict(work, doi="https://doi.org/10.1/c", display_name="Readiness for change in smokers",
                    abstract_inverted_index={"patients": [0]})
    work["primary_location"]["source"]["id"] = "https://openalex.org/S1"
    small = dict(work, doi="https://doi.org/10.1/d",
                 primary_location={"source": {"display_name": "Tiny Journal", "id": "https://openalex.org/S2"}})
    calls = []
    def fake_get(session, url, **kw):
        calls.append(kw["params"].get("filter"))
        if "/sources/" in url:
            return Resp({"summary_stats": {"h_index": 150 if url.endswith("S1") else 4}})
        return Resp({"results": [work, paywalled, clinical, work, small]})
    monkeypatch.setattr(fetch, "http_get", fake_get)
    src = {"id": "s", "name": "Research search", "layer": "research", "window_days": 60,
           "needs_topic": True, "require_work_context": True, "require_title_match": True,
           "queries": ["readiness for change"]}
    cands, info = fetch.fetch_openalex_search(None, src, "key")
    assert "primary_location.source.is_in_doaj:true" in calls[0] and "is_oa:true" in calls[0]
    assert len(cands) == 2      # paywalled dropped, duplicate merged, low h-index journal dropped
    assert info["dropped_low_h_index"] == 1
    items = [fetch.build_item(c, src, MATCHER) for c in cands]
    kept = [i for i in items if i]
    assert len(kept) == 1 and kept[0]["source"] == "Frontiers in Psychology" and kept[0]["region"]


def test_title_match_required_when_configured():
    src = dict(NEWS, require_title_match=True)
    off = {"title": "Rail transport of vegetables", "url": "https://x.org/r", "published": NOW,
           "text": "Rail transport of vegetables. Mentions organizational change in passing for workers.",
           "countries": set()}
    on = dict(off, title="Organizational change in rail companies")
    assert fetch.build_item(off, src, MATCHER) is None
    assert fetch.build_item(on, src, MATCHER) is not None


def test_citation_details_for_feeds_and_nber():
    feed = rss([("Remote work rules for BPO workers", "https://example.org/p", "", NOW - timedelta(hours=3))])
    feed = feed.replace(b"<description>", b"<author>By Ana Cruz and Ben Reyes</author><description>")
    [item] = [fetch.build_item(c, NEWS, MATCHER) for c in fetch.parse_feed(feed)]
    assert item["cite"]["kind"] == "news" and item["cite"]["authors"] == ["Ana Cruz", "Ben Reyes"]
    assert item["cite"]["container"] == "Test News"
    nber = dict(PRE, id="nber", name="NBER Working Papers", date_fallback="first_seen")
    [c] = fetch.parse_feed(rss([("Labor market effects of AI -- by Jennifer Wang, Erik B Smith", "https://nber.org/w1", "", None)]))
    item = fetch.build_item(c, nber, MATCHER)
    assert item["title"] == "Labor market effects of AI"
    assert item["cite"]["authors"] == ["Jennifer Wang", "Erik B Smith"]
    assert item["cite"]["kind"] == "working_paper"


def test_bylines_drop_job_titles_and_places():
    assert fetch.clean_byline("Jasper Jolly Business editor") == "Jasper Jolly"
    assert fetch.clean_byline("Ana Cruz in Manila") == "Ana Cruz"
    assert fetch.clean_byline("Ben Reyes, Technology correspondent".split(", ")[0]) == "Ben Reyes"
    assert fetch.clean_byline("Staff reporter") == ""
    assert fetch.clean_byline("Maria Santos") == "Maria Santos"


def test_editors_notes(tmp_path):
    import build_notes
    (tmp_path / "_template.md").write_text("---\ntitle: T\ndate: 2026-01-01\n---\nx")
    (tmp_path / "2026-11-10-first.md").write_text(
        "---\ntitle: \"Readiness: a first look\"\ndate: 2026-11-10\n---\n"
        "Layoffs test *readiness*. <script>alert(1)</script> [bad](javascript:alert(1)) "
        "[paper](https://doi.org/10.1/x)\n\n## Theory\n\nMore text.")
    (tmp_path / "2026-11-20-later.md").write_text("---\ntitle: Later\ndate: 2026-11-20\n---\nSoon.")
    (tmp_path / "draft.md").write_text("---\ntitle: D\ndate: 2026-11-01\ndraft: true\n---\nWIP")
    notes = build_notes.build(tmp_path, today="2026-11-10")
    assert [n["slug"] for n in notes] == ["2026-11-10-first"]   # template, draft, future skipped
    n = notes[0]
    assert n["title"] == "Readiness: a first look" and n["author"] == "Dom Rivera"
    assert "<script>" not in n["html"] and "javascript:" not in n["html"].split("href=")[-1][:20]
    assert 'target="_blank" rel="noopener noreferrer"' in n["html"]
    assert n["summary"].startswith("Layoffs test readiness.")
    (tmp_path / "broken.md").write_text("no front matter")
    import pytest
    with pytest.raises(build_notes.NoteError):
        build_notes.build(tmp_path, today="2026-11-10")


def test_rss_feed(tmp_path):
    import json, build_feed, feedparser
    item = {"id": "abc", "title": "Pay & <bonuses> in \"AI\" era", "url": "https://x.org/a?b=1&c=2",
            "source": "Test News", "type": "News", "layer": "news", "published": "2026-11-09T02:00:00Z",
            "first_seen": "2026-11-10T00:00:00Z", "window_days": 7, "topics": ["ai-at-work"],
            "region": True, "labels": ["Opinion"], "access": "Free to read",
            "cite": {"kind": "news", "authors": ["Ana Cruz"]}}
    (tmp_path / "items.json").write_text(json.dumps({"generated": "2026-11-10T00:00:00Z", "items": [item],
        "topics": [{"id": "ai-at-work", "name": "AI at work", "group": "context"}],
        "region": {"id": "ph-sea", "name": "Philippines & Southeast Asia"}}))
    (tmp_path / "notes.json").write_text(json.dumps({"notes": [{"slug": "2026-11-11-n", "title": "First note",
        "date": "2026-11-11", "summary": "Hello <world>", "author": "Dom Rivera"}]}))
    xml = build_feed.build(tmp_path)
    f = feedparser.parse(xml)
    assert not f.bozo and len(f.entries) == 2
    note, news = f.entries
    assert note.title == "Editor’s Note: First note" and note.link.endswith("#note/2026-11-11-n")
    assert news.title == 'Pay & <bonuses> in "AI" era' and news.link == "https://x.org/a?b=1&c=2"
    assert "Opinion" in news.description and "Philippines & Southeast Asia" in news.description


def test_news_change_events_need_staff_words_and_skip_research():
    day = NOW - timedelta(days=1)
    kept = build([
        ("Qantas to cut 850 jobs under AI-driven overhaul", "https://example.org/q", "", day),
        ("Bank overhaul of mobile app delights customers", "https://example.org/b", "", day),
        ("Staff push back on return-to-office mandate", "https://example.org/r", "", day),
    ])
    assert "organizational-change" in kept[0]["topics"] and "ai-at-work" in kept[0]["topics"]
    assert kept[1] is None          # change word but no workers, staff or jobs
    assert "future-of-work" in kept[2]["topics"]
    # The same change-event words do not count for research papers.
    research = dict(NEWS, layer="research")
    [paper] = build([("An overhaul of staff rostering", "https://example.org/p", "", day)], research)
    assert paper is None


def test_combined_feeds_dedupe_and_skip_sponsored(monkeypatch):
    day = NOW - timedelta(days=1)
    feeds = {
        "https://a.example/1": rss([("Remote work and teams", "https://a.example/x", "", day),
                                    ("Sponsored: our HR suite", "https://a.example/spons/y", "", day)]),
        "https://a.example/2": rss([("Remote work and teams", "https://a.example/x", "", day),
                                    ("Hybrid work rules", "https://a.example/z", "", day)]),
    }
    class Resp:
        def __init__(self, c): self.content = c
    monkeypatch.setattr(fetch, "http_get", lambda s, url, **kw: Resp(feeds[url]))
    src = {"feeds": list(feeds), "combine": True, "exclude_urls": ["/spons/"]}
    cands, info = fetch.fetch_rss(None, src)
    assert [c["url"] for c in cands] == ["https://a.example/x", "https://a.example/z"]
    assert info["feed_used"] == list(feeds)
    cands, info = fetch.fetch_rss(None, dict(src, combine=False))
    assert len(cands) == 1 and info["feed_used"] == "https://a.example/1"

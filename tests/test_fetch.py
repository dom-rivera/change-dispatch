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


def test_abstract_rebuild():
    assert fetch.abstract_text({"readiness": [0], "change": [2], "for": [1]}) == "readiness for change"

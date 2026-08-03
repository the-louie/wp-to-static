from __future__ import annotations

from pathlib import Path

import feedparser
import pytest

from wp_to_static.config import Config
from wp_to_static.feeds import (
    cdata,
    crosscheck_terms,
    generate,
    guids_in,
    site_relative,
)
from wp_to_static.wpapi import BuildData, load_build_data

FIXTURE = Path(__file__).parent / "fixtures" / "build-data.json"


@pytest.fixture
def data() -> BuildData:
    return load_build_data(FIXTURE)


@pytest.fixture
def built(data: BuildData, cfg: Config):
    cfg.site_dir.mkdir(parents=True)
    feeds = generate(data, cfg)
    feeds.write_all(cfg)
    return feeds


def read(cfg: Config, rel: str) -> str:
    return (cfg.site_dir / rel).read_text(encoding="utf-8")


# --- layout -----------------------------------------------------------------


def test_every_term_gets_four_documents(data: BuildData, cfg: Config, built) -> None:
    for rel in (
        "feed.xml",
        "atom.xml",
        "feed/index.xml",
        "feed/atom/index.xml",
        "tag/kod/feed.xml",
        "tag/kod/atom.xml",
        "tag/kod/feed/index.xml",
        "tag/kod/feed/atom/index.xml",
        "category/teknik/feed.xml",
        "category/tomt/feed.xml",
    ):
        assert (cfg.site_dir / rel).is_file(), rel


def test_non_ascii_slug_keeps_wordpress_encoding(cfg: Config, built) -> None:
    """The path must match what WordPress publishes, not a re-encoding."""
    assert (cfg.site_dir / "tag/k%c3%b6tt/feed.xml").is_file()
    body = read(cfg, "tag/k%c3%b6tt/feed.xml")
    assert "https://louie.se/tag/k%c3%b6tt/feed.xml" in body


def test_site_relative_strips_origin(cfg: Config) -> None:
    assert site_relative("http://localhost:8000/tag/kod/", cfg) == "tag/kod"
    assert site_relative("http://localhost:8000/", cfg) == ""


# --- correctness we now own -------------------------------------------------


def test_guid_is_verbatim(cfg: Config, built) -> None:
    body = read(cfg, "tag/kod/feed.xml")
    assert '<guid isPermaLink="false">http://localhost:8000/?p=42</guid>' in body


def test_atom_id_uses_the_same_guid(cfg: Config, built) -> None:
    assert "<id>http://localhost:8000/?p=42</id>" in read(cfg, "tag/kod/atom.xml")


def test_rss_dates_are_rfc822(cfg: Config, built) -> None:
    assert "<pubDate>Wed, 01 Jul 2026 09:00:00 +0000</pubDate>" in read(
        cfg, "tag/kod/feed.xml"
    )


def test_atom_dates_are_rfc3339(cfg: Config, built) -> None:
    body = read(cfg, "tag/kod/atom.xml")
    assert "<published>2026-07-01T09:00:00+00:00</published>" in body
    assert "<updated>2026-07-01T09:30:00+00:00</updated>" in body


def test_self_link_matches_the_serving_url(cfg: Config, built) -> None:
    """rel="self" must name the URL each document is actually served at."""
    assert 'href="https://louie.se/tag/kod/feed.xml"' in read(cfg, "tag/kod/feed.xml")
    assert 'href="https://louie.se/tag/kod/feed/"' in read(
        cfg, "tag/kod/feed/index.xml"
    )
    assert 'href="https://louie.se/tag/kod/atom.xml"' in read(cfg, "tag/kod/atom.xml")
    assert 'href="https://louie.se/tag/kod/feed/atom/"' in read(
        cfg, "tag/kod/feed/atom/index.xml"
    )


def test_alias_carries_the_same_items(cfg: Config, built) -> None:
    assert guids_in(read(cfg, "tag/kod/feed.xml")) == guids_in(
        read(cfg, "tag/kod/feed/index.xml")
    )


def test_term_membership(cfg: Config, built) -> None:
    assert guids_in(read(cfg, "tag/kod/feed.xml")) == [
        "http://localhost:8000/?p=42",
        "http://localhost:8000/?p=41",
    ]
    assert guids_in(read(cfg, "tag/k%c3%b6tt/feed.xml")) == [
        "http://localhost:8000/?p=41"
    ]
    assert guids_in(read(cfg, "category/teknik/feed.xml")) == [
        "http://localhost:8000/?p=42"
    ]


def test_empty_term_is_valid_not_a_crash(cfg: Config, built) -> None:
    body = read(cfg, "category/tomt/feed.xml")
    assert guids_in(body) == []
    parsed = feedparser.parse(body)
    assert parsed.bozo == 0


def test_no_posts_per_rss_cap(data: BuildData, cfg: Config, built) -> None:
    """WordPress would cap the site feed at posts_per_rss; we do not."""
    assert data.site.posts_per_rss == 10
    assert len(guids_in(read(cfg, "feed.xml"))) == len(data.posts)


def test_ampersand_in_title_is_escaped(cfg: Config, built) -> None:
    body = read(cfg, "tag/kod/feed.xml")
    assert "kod &amp; kott" in body
    assert "kod & kott" not in body


def test_cdata_terminator_is_split(cfg: Config, built) -> None:
    """Content containing ]]> must not close the CDATA section early."""
    body = read(cfg, "tag/kod/feed.xml")
    assert feedparser.parse(body).bozo == 0
    assert cdata("a]]>b") == "<![CDATA[a]]]]><![CDATA[>b]]>"


def test_output_has_no_build_timestamp(data: BuildData, cfg: Config) -> None:
    """Regenerating an unchanged site must produce identical bytes."""
    cfg.site_dir.mkdir(parents=True)
    first = generate(data, cfg).files
    second = generate(data, cfg).files
    assert [f.body for f in first] == [f.body for f in second]


# --- validity ---------------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "feed.xml",
        "atom.xml",
        "tag/kod/feed.xml",
        "tag/kod/atom.xml",
        "tag/k%c3%b6tt/feed.xml",
        "category/teknik/atom.xml",
    ],
)
def test_feeds_parse_cleanly(cfg: Config, built, rel: str) -> None:
    parsed = feedparser.parse(read(cfg, rel))
    assert parsed.bozo == 0, getattr(parsed, "bozo_exception", None)
    assert parsed.feed.get("title")


def test_feedparser_sees_expected_entries(cfg: Config, built) -> None:
    parsed = feedparser.parse(read(cfg, "tag/kod/feed.xml"))
    assert len(parsed.entries) == 2
    assert parsed.entries[0].title == "Nyare inlagg om kod"
    assert parsed.entries[0].id == "http://localhost:8000/?p=42"


# --- cross-check ------------------------------------------------------------


def _wp_feed(guids: list[str]) -> str:
    items = "".join(f'<item><guid isPermaLink="false">{g}</guid></item>' for g in guids)
    return f"<rss><channel>{items}</channel></rss>"


def test_crosscheck_passes_when_wp_is_a_prefix(data: BuildData, cfg: Config) -> None:
    def fetch(url: str) -> str:
        if "kod" in url:
            return _wp_feed(["http://localhost:8000/?p=42"])
        return _wp_feed([])

    result = crosscheck_terms(data, cfg, fetch, sample=None)
    assert result.ok, result.failures
    assert result.checked == 4


def test_crosscheck_fails_on_a_guid_we_are_missing(data: BuildData, cfg: Config) -> None:
    def fetch(url: str) -> str:
        if "kod" in url:
            return _wp_feed(["http://localhost:8000/?p=999"])
        return _wp_feed([])

    result = crosscheck_terms(data, cfg, fetch, sample=None)
    assert not result.ok
    assert any("p=999" in f for f in result.failures)


def test_crosscheck_fails_on_ordering(data: BuildData, cfg: Config) -> None:
    def fetch(url: str) -> str:
        if "kod" in url:
            return _wp_feed(
                ["http://localhost:8000/?p=41", "http://localhost:8000/?p=42"]
            )
        return _wp_feed([])

    result = crosscheck_terms(data, cfg, fetch, sample=None)
    assert not result.ok
    assert any("ordering" in f for f in result.failures)


def test_crosscheck_reports_fetch_failure(data: BuildData, cfg: Config) -> None:
    def fetch(url: str) -> str:
        raise OSError("connection refused")

    result = crosscheck_terms(data, cfg, fetch, sample=1)
    assert not result.ok
    assert "connection refused" in result.failures[0]

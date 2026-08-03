"""Full offline build: crawl output -> feeds -> rewrite -> overlay -> bake.

Covers the interaction the unit tests cannot: that generated feeds survive the
rewrite stage, that archive pages advertise their own term feed, and that
ordinary pages do not.
"""

from __future__ import annotations

from pathlib import Path

import feedparser
import pytest

from test_pipeline import make_args
from wp_to_static.__main__ import build
from wp_to_static.config import Config
from wp_to_static.feeds import archive_dir_for, guids_in

FIXTURE = Path(__file__).parent / "fixtures" / "build-data.json"

ARCHIVE_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link rel="alternate" type="application/rss+xml" href="http://localhost:8000/tag/kod/feed/" />
<link rel="canonical" href="http://localhost:8000/tag/kod/" />
<meta name="generator" content="WordPress 6.1.1" />
</head><body><h1>Kod</h1></body></html>
"""

POST_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link rel="canonical" href="http://localhost:8000/nyare-inlagg/" />
</head><body><p>hej</p></body></html>
"""


@pytest.fixture
def site(cfg: Config) -> Config:
    for directory, page in (
        ("tag/kod", ARCHIVE_PAGE),
        ("tag/kod/page/2", ARCHIVE_PAGE),
        ("tag/k%c3%b6tt", ARCHIVE_PAGE),
        ("category/teknik", ARCHIVE_PAGE),
        ("nyare-inlagg", POST_PAGE),
    ):
        target = cfg.site_dir / directory
        target.mkdir(parents=True)
        (target / "index.html").write_text(page, encoding="utf-8")
    return cfg


@pytest.fixture
def out(site: Config) -> Config:
    args = make_args(build_data=FIXTURE, no_crosscheck=True)
    assert build(site, {"feeds", "rewrite", "overlay", "bake"}, args) == 0
    return site


def read(cfg: Config, rel: str) -> str:
    return (cfg.site_dir / rel).read_text(encoding="utf-8")


def test_archive_dir_ignores_pagination(cfg: Config) -> None:
    assert archive_dir_for(cfg.site_dir / "tag/kod/page/2/index.html", cfg) == "tag/kod"
    assert archive_dir_for(cfg.site_dir / "tag/kod/index.html", cfg) == "tag/kod"
    assert archive_dir_for(cfg.site_dir / "index.html", cfg) == ""


def test_feeds_exist_after_full_build(out: Config) -> None:
    for rel in (
        "feed.xml",
        "atom.xml",
        "tag/kod/feed.xml",
        "tag/kod/feed/index.xml",
        "tag/k%c3%b6tt/atom.xml",
        "category/teknik/feed.xml",
    ):
        assert (out.site_dir / rel).is_file(), rel


def test_rewrite_stage_fixes_the_host_in_generated_feeds(out: Config) -> None:
    """Post links and guids come out of WordPress with the local host; the
    rewrite stage is the single place that owns host rewriting."""
    body = read(out, "tag/kod/feed.xml")
    assert "localhost:8000" not in body
    assert "<link>https://louie.se/nyare-inlagg/</link>" in body
    assert '<guid isPermaLink="false">https://louie.se/?p=42</guid>' in body


def test_generated_feeds_still_parse_after_rewrite(out: Config) -> None:
    for rel in ("feed.xml", "tag/kod/feed.xml", "tag/kod/atom.xml"):
        parsed = feedparser.parse(read(out, rel))
        assert parsed.bozo == 0, (rel, getattr(parsed, "bozo_exception", None))


def test_archive_page_advertises_its_own_feed(out: Config) -> None:
    body = read(out, "tag/kod/index.html")
    assert "https://louie.se/feed.xml" in body       # site feed
    assert "https://louie.se/tag/kod/feed.xml" in body   # term feed
    assert "https://louie.se/tag/kod/atom.xml" in body
    assert body.count("rel=alternate") == 4 or body.count('rel="alternate"') == 4


def test_paginated_archive_advertises_the_same_term_feed(out: Config) -> None:
    body = read(out, "tag/kod/page/2/index.html")
    assert "https://louie.se/tag/kod/feed.xml" in body


def test_non_ascii_archive_uses_wordpress_encoding(out: Config) -> None:
    body = read(out, "tag/k%c3%b6tt/index.html")
    assert "https://louie.se/tag/k%c3%b6tt/feed.xml" in body


def test_ordinary_page_gets_only_the_site_feeds(out: Config) -> None:
    body = read(out, "nyare-inlagg/index.html")
    assert "https://louie.se/feed.xml" in body
    assert "/tag/" not in body
    assert body.count("rel=alternate") == 2 or body.count('rel="alternate"') == 2


def test_wordpress_own_feed_links_are_gone(out: Config) -> None:
    body = read(out, "tag/kod/index.html")
    assert "/tag/kod/feed/\"" not in body
    assert "localhost" not in body


def test_full_build_is_idempotent(site: Config) -> None:
    args = make_args(build_data=FIXTURE, no_crosscheck=True)
    stages = {"feeds", "rewrite", "overlay", "bake"}
    build(site, stages, args)
    first = {
        p.relative_to(site.site_dir).as_posix(): p.read_bytes()
        for p in sorted(site.site_dir.rglob("*"))
        if p.is_file()
    }
    build(site, stages, args)
    second = {
        p.relative_to(site.site_dir).as_posix(): p.read_bytes()
        for p in sorted(site.site_dir.rglob("*"))
        if p.is_file()
    }
    assert first == second


def test_feed_max_items_cap(site: Config) -> None:
    args = make_args(build_data=FIXTURE, no_crosscheck=True, feed_max_items=1)
    build(site, {"feeds"}, args)
    assert len(guids_in(read(site, "tag/kod/feed.xml"))) == 1

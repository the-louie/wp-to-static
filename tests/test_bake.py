from __future__ import annotations

from dataclasses import replace

from pathlib import Path

import pytest

from wp_to_static import bake
from wp_to_static.bake import (
    BakeStats,
    bake_html,
    bake_tree,
    minify_js_source,
    resolve_asset,
)
from wp_to_static.config import Config


@pytest.fixture
def mirror(cfg: Config) -> Config:
    """A small mirror shaped like what wget produces."""
    site = cfg.site_dir
    (site / "assets/js").mkdir(parents=True)
    (site / "inc/js/jquery").mkdir(parents=True)
    (site / "post-a").mkdir()
    (site / "post-b").mkdir()

    (site / "assets/theme.css").write_text("body { color: #112233; }\n")
    (site / "assets/js/app.js").write_text(
        'function greet(namn) { var msg = "hej " + namn; return msg; }\n'
    )
    (site / "inc/js/jquery/jquery.min.js").write_text("var jq=1;\n")

    page = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<link rel="stylesheet" href="/assets/theme.css" />'
        '<link rel="stylesheet" href="https://fonts.example.com/x.css" />'
        '<script src="/assets/js/app.js"></script>'
        "</head><body><p>hej</p></body></html>"
    )
    (site / "post-a/index.html").write_text(page)
    (site / "post-b/index.html").write_text(page)
    return cfg


def test_resolve_asset_skips_remote(cfg: Config) -> None:
    assert resolve_asset("https://cdn.example.com/x.css", cfg) is None
    assert resolve_asset("//cdn.example.com/x.css", cfg) is None


def test_resolve_asset_strips_query(cfg: Config) -> None:
    got = resolve_asset("/assets/x.css%3Fver=1", cfg)
    assert got == cfg.site_dir / "assets/x.css"


def test_css_is_inlined(mirror: Config) -> None:
    stats = BakeStats()
    out = bake_html((mirror.site_dir / "post-a/index.html").read_text(), mirror, stats)
    assert "<style>" in out
    assert "#123" in out or "#112233" in out  # minifier may shorten the hex
    assert stats.css_inlined == 1
    # the remote stylesheet must survive as a link
    assert "fonts.example.com" in out


def test_missing_css_is_counted_not_silent(mirror: Config) -> None:
    stats = BakeStats()
    bake_html('<link rel="stylesheet" href="/nope.css">', mirror, stats)
    assert stats.css_missing == 1


def test_js_minified_once_per_file_not_per_page(mirror: Config, monkeypatch) -> None:
    """The Node version re-minified shared JS from every referencing page.

    EXCLUDE_MINIFY is pinned to the fixture's own file so the test exercises the
    skip mechanism rather than whatever the production list happens to contain.
    """
    monkeypatch.setattr(bake, "EXCLUDE_MINIFY", frozenset({"inc/js/jquery/jquery.min.js"}))
    stats = bake_tree(mirror)
    assert stats.js_minified == 1  # app.js only; jquery.min.js is excluded
    assert "inc/js/jquery/jquery.min.js" in stats.js_skipped
    body = (mirror.site_dir / "assets/js/app.js").read_text()
    assert "var msg" not in body  # actually minified
    assert len(body) < 60


def test_shared_js_is_stable_across_pages(mirror: Config) -> None:
    bake_tree(mirror)
    once = (mirror.site_dir / "assets/js/app.js").read_text()
    # A second full bake must not re-mangle an already-minified file.
    bake_tree(mirror)
    assert (mirror.site_dir / "assets/js/app.js").read_text() == once


def test_js_with_closing_script_tag_is_left_alone() -> None:
    """Wrapping in <script> would let the source terminate the element and get
    entity-escaped, silently corrupting it."""
    js = 'var s = "a</script>b"; var r = /a<\\/b/;'
    assert minify_js_source(js) is None


def test_js_minify_normal_source() -> None:
    out = minify_js_source('function f(a) { var b = a + 1; return b; }')
    assert out is not None
    assert "var b" not in out


def test_no_minify_flag_preserves_markup(mirror: Config) -> None:
    cfg = replace(mirror, minify=False)
    stats = BakeStats()
    out = bake_html((cfg.site_dir / "post-a/index.html").read_text(), cfg, stats)
    assert "<!DOCTYPE html>" in out
    assert "</head>" in out  # optional tags not stripped


def test_no_minify_flag_leaves_js_readable(mirror: Config) -> None:
    """--no-minify is for diffing against the old pipeline, so the JS pass must
    be skipped too, not only the HTML one."""
    cfg = replace(mirror, minify=False)
    stats = bake_tree(cfg)
    assert stats.js_minified == 0
    body = (cfg.site_dir / "assets/js/app.js").read_text()
    assert "var msg" in body  # untouched, still readable
    assert body == 'function greet(namn) { var msg = "hej " + namn; return msg; }\n'


def test_font_awesome_empty_elements_survive(mirror: Config) -> None:
    stats = BakeStats()
    out = bake_html(
        '<html><head></head><body><a href="/x"><i class="fa fa-rss"></i></a></body></html>',
        mirror,
        stats,
    )
    assert "fa-rss" in out
    assert "<i " in out


def test_exclusions_are_keyed_on_post_scrub_paths(mirror: Config) -> None:
    """bake runs after scrub has renamed wp-content and wp-includes, so an
    exclusion written against the original paths can never match."""
    from wp_to_static.bake import EXCLUDE_MINIFY

    assert not any(e.startswith(("wp-content/", "wp-includes/")) for e in EXCLUDE_MINIFY)


def test_stale_exclusions_are_reported(mirror: Config, monkeypatch) -> None:
    """An entry matching no file protects nothing, and silence made that
    invisible for a long time. One entry exists in the fixture, one does not."""
    monkeypatch.setattr(
        bake,
        "EXCLUDE_MINIFY",
        frozenset({"content/does/not/exist.js", "inc/js/jquery/jquery.min.js"}),
    )
    stats = bake_tree(mirror)
    assert "content/does/not/exist.js" in stats.unmatched_exclusions
    assert "inc/js/jquery/jquery.min.js" not in stats.unmatched_exclusions

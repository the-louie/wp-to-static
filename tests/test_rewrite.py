"""Rewrite tests, including an A/B against the original sed scripts.

The A/B is the equivalence proof for this stage: the bash scripts are still in
the tree, so we run both on identical input and diff. Two intentional
divergences are asserted separately in test_fixed_bugs_*.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import WP_PAGE
from wp_to_static.config import Config
from wp_to_static.rewrite import (
    rewrite_css,
    rewrite_html,
    rewrite_xml,
    site_feed_links,
)

WP_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<atom:link href="http://localhost:8000/feed/" rel="self" type="application/rss+xml" />
<link>http://localhost:8000</link>
<item><link>http://localhost:8000/nagot-inlagg/</link>
<guid isPermaLink="false">http://localhost:8000/?p=1234</guid></item>
</channel></rss>
"""

WP_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="http://localhost:8000/wp-sitemap.xsl" ?>
<urlset><url><loc>http://localhost:8000/nagot-inlagg/</loc></url></urlset>
"""


def _run_bash(script: Path, text: str, tmp_path: Path, suffix: str, cfg: Config) -> str:
    """Run one of the original textreplace scripts on `text` and return the result."""
    target = tmp_path / f"subject{suffix}"
    target.write_text(text, encoding="utf-8")
    subprocess.run(
        ["/bin/bash", str(script), str(target)],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "LOCALURL": cfg.local_url,
            "DOMAIN": cfg.domain,
        },
    )
    return target.read_text(encoding="utf-8")


bash_required = pytest.mark.skipif(
    shutil.which("sed") is None, reason="GNU sed not available"
)


@bash_required
def test_html_matches_bash_original(cfg: Config, repo: Path, tmp_path: Path) -> None:
    bash_out = _run_bash(repo / "textreplace_html.sh", WP_PAGE, tmp_path, ".html", cfg)
    py_out = rewrite_html(WP_PAGE, cfg, feed_links=site_feed_links(cfg))
    assert py_out == bash_out


@bash_required
def test_xml_matches_bash_original(cfg: Config, repo: Path, tmp_path: Path) -> None:
    for name, doc in (("feed", WP_FEED), ("sitemap", WP_SITEMAP)):
        bash_out = _run_bash(
            repo / "textreplace_xml.sh", doc, tmp_path, f"-{name}.xml", cfg
        )
        assert rewrite_xml(doc, cfg) == bash_out, name


@bash_required
def test_css_matches_bash_original(cfg: Config, repo: Path, tmp_path: Path) -> None:
    css = ".x{background:url(/wp-content/themes/eisai-child/assets/bg.png)}\n"
    bash_out = _run_bash(repo / "textreplace_css.sh", css, tmp_path, ".css", cfg)
    assert rewrite_css(css) == bash_out


# --- behaviour, independent of the bash originals ---------------------------


def test_absolute_tags_stay_absolute(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg)
    assert 'rel="canonical" href="https://louie.se/nagot-inlagg/"' in out
    assert 'property="og:url" content="https://louie.se/nagot-inlagg/"' in out
    assert 'name="twitter:image" content="https://louie.se/wp-content/uploads/bild.png"' in out


def test_other_links_become_root_relative(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg)
    assert 'href="/annat/"' in out
    assert 'href="/">startsidan' in out
    assert "localhost:8000" not in out


def test_json_escaped_urls_rewritten(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg)
    assert '{"home":"/","v":1}' in out


def test_wordpress_version_scrubbed(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg)
    assert "WordPress" not in out
    assert "OpenBSD 7.5 - ed" in out


def test_shortlink_removed(cfg: Config) -> None:
    assert "shortlink" not in rewrite_html(WP_PAGE, cfg)


def test_theme_assets_flattened(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg)
    assert 'href="/assets/theme.css"' in out
    assert "eisai-child" not in out


def test_feed_autodiscovery_replaced(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg, feed_links=site_feed_links(cfg))
    assert out.count("<link rel=\"alternate\"") == 2
    assert 'href="https://louie.se/feed.xml"' in out
    assert 'href="https://louie.se/atom.xml"' in out
    # WordPress's comment and category feeds must not survive.
    assert "comments/feed" not in out


def test_feed_links_injected_before_head_close(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg, feed_links=site_feed_links(cfg))
    assert out.index('href="https://louie.se/feed.xml"') < out.index("</head>")


def test_no_injection_without_links(cfg: Config) -> None:
    out = rewrite_html(WP_PAGE, cfg)
    assert "<link rel=\"alternate\"" not in out


# --- the two divergences from the sed originals -----------------------------


def test_fixed_bug_index_htm_not_mangled(cfg: Config) -> None:
    """The sed version's \\? made the trailing 'l' optional, so it also ate
    '/index.htm'. Ours matches only the real generated filename."""
    out = rewrite_html('<a href="/foo/index.htm">x</a>', cfg)
    assert 'href="/foo/index.htm"' in out
    assert rewrite_html('<a href="/foo/index.html">x</a>', cfg) == '<a href="/foo/">x</a>'


def test_fixed_bug_ver_with_non_numeric_suffix(cfg: Config) -> None:
    """The sed version stripped only [0-9.], leaving '-rc1' behind while the
    file on disk had lost it. Strip the whole value."""
    out = rewrite_html('<link href="/a.css?ver=6.1-rc1">', cfg)
    assert 'href="/a.css"' in out
    assert "rc1" not in out


def test_xml_bare_origin_rewritten(cfg: Config) -> None:
    """A feed's channel <link> is the origin with no path."""
    out = rewrite_xml(WP_FEED, cfg)
    assert "<link>https://louie.se/</link>" in out
    assert "localhost" not in out


def test_xml_preserves_guid_query_form(cfg: Config) -> None:
    """?p=NN is an opaque identifier; only the host may change."""
    out = rewrite_xml(WP_FEED, cfg)
    assert '<guid isPermaLink="false">https://louie.se/?p=1234</guid>' in out


def test_rewrites_are_idempotent(cfg: Config) -> None:
    once = rewrite_html(WP_PAGE, cfg, feed_links=site_feed_links(cfg))
    twice = rewrite_html(once, cfg, feed_links=site_feed_links(cfg))
    assert once == twice


# --- stored data from a host WordPress no longer runs on ---------------------


def test_legacy_host_in_guid_is_normalised(cfg: Config) -> None:
    """WordPress stores a post's guid at creation and never updates it, so a
    site that has moved hosts still emits the old one. Shipping it verbatim
    would leak the build host and change identifiers subscribers already hold."""
    moved = Config(
        repo_dir=cfg.repo_dir,
        base_dir=cfg.base_dir,
        local_url="louie_se.i.louie.se",
        local_scheme="https",
    )
    doc = (
        "<rss><channel><item>"
        "<link>https://louie_se.i.louie.se/projects/x/</link>"
        '<guid isPermaLink="false">http://localhost:8000/?p=808</guid>'
        "</item></channel></rss>"
    )
    out = rewrite_xml(doc, moved)
    assert "<link>https://louie.se/projects/x/</link>" in out
    assert '<guid isPermaLink="false">https://louie.se/?p=808</guid>' in out
    assert "localhost" not in out
    assert "louie_se.i" not in out


def test_legacy_host_in_html_is_normalised(cfg: Config) -> None:
    moved = Config(
        repo_dir=cfg.repo_dir,
        base_dir=cfg.base_dir,
        local_url="louie_se.i.louie.se",
        local_scheme="https",
    )
    out = rewrite_html('<a href="http://localhost:8000/gammalt/">x</a>', moved)
    assert 'href="/gammalt/"' in out

"""End-to-end tests of the stages that do not need a live WordPress."""

from __future__ import annotations

from dataclasses import replace

import argparse
from pathlib import Path

import pytest

from wp_to_static.__main__ import build
from wp_to_static.config import Config
from wp_to_static.mirror import cleanup, write_sitemap_index
from wp_to_static.overlay import OverlayError, apply_overlay


def make_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        dry_run=False,
        build_data=None,
        feed_max_items=None,
        crosscheck_all=False,
        no_crosscheck=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)

PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link rel="alternate" type="application/rss+xml" href="http://localhost:8000/feed/" />
<link rel="canonical" href="http://localhost:8000/post-a/" />
<link rel="stylesheet" href="http://localhost:8000/wp-content/themes/eisai-child/assets/theme.css?ver=1.2" />
<script src="http://localhost:8000/assets/js/app.js"></script>
<meta name="generator" content="WordPress 6.1.1" />
</head><body><p>hej</p></body></html>
"""


@pytest.fixture
def mirror(cfg: Config, repo: Path) -> Config:
    site = cfg.site_dir
    (site / "assets/js").mkdir(parents=True)
    (site / "post-a").mkdir()
    (site / "assets/theme.css").write_text(
        ".x{background:url(/wp-content/themes/eisai-child/assets/bg.png)}\n"
    )
    (site / "assets/js/app.js").write_text('function f(a){var b="hej "+a;return b;}\n')
    (site / "post-a/index.html").write_text(PAGE)
    # crawl artefacts that must not ship
    (site / "index.html?p=77.html").write_text("dupe")
    (site / "xmlrpc.php?rsd").write_text("x")
    (site / "wp-login.php").write_text("x")
    (site / "assets/theme.css?ver=9").write_text("stale")
    return cfg


def test_cleanup_removes_artefacts(mirror: Config) -> None:
    stats = cleanup(mirror)
    site = mirror.site_dir
    assert stats.query_pages_removed == 1
    assert stats.php_files_removed == 2
    assert not (site / "index.html?p=77.html").exists()
    assert not (site / "wp-login.php").exists()
    assert (site / "post-a/index.html").exists()


def test_cleanup_keeps_existing_asset_when_renaming(mirror: Config) -> None:
    """theme.css already exists, so theme.css?ver=9 must not clobber it --
    and must not survive to ship alongside it either."""
    original = (mirror.site_dir / "assets/theme.css").read_text()
    cleanup(mirror)
    assert (mirror.site_dir / "assets/theme.css").read_text() == original
    assert not (mirror.site_dir / "assets/theme.css?ver=9").exists()


def test_cleanup_renames_versioned_asset_when_target_free(mirror: Config) -> None:
    (mirror.site_dir / "assets/only.css?ver=3").write_text("a{}")
    cleanup(mirror)
    assert (mirror.site_dir / "assets/only.css").read_text() == "a{}"


def test_cleanup_ignores_names_that_merely_look_versioned(mirror: Config) -> None:
    """rglob("*?ver=*") would have matched this, because ? is a wildcard."""
    decoy = mirror.site_dir / "assets/Xver=1.css"
    decoy.write_text("keep")
    cleanup(mirror)
    assert decoy.exists()


def test_overlay_lands_in_site_root(mirror: Config) -> None:
    copied = apply_overlay(mirror)
    site = mirror.site_dir
    assert "robots.txt" in copied
    assert (site / ".well-known/security.txt").is_file()
    robots = (site / "robots.txt").read_text()
    assert "https://louie.se/sitemap.xml" in robots
    assert "__DOMAIN__" not in robots
    assert "GPTBot" in robots


def test_overlay_missing_directory_is_loud(cfg: Config, tmp_path: Path) -> None:
    broken = Config(repo_dir=tmp_path / "nope", base_dir=cfg.base_dir)
    broken.site_dir.mkdir(parents=True)
    with pytest.raises(OverlayError):
        apply_overlay(broken)


def test_sitemap_index_lists_only_existing_files(mirror: Config) -> None:
    write_sitemap_index(mirror, ["sitemap-posts-post-1.xml", "sitemap-posts-post-2.xml"])
    doc = (mirror.site_dir / "sitemap.xml").read_text()
    assert doc.count("<sitemap>") == 2
    assert "https://louie.se/sitemap-posts-post-2.xml" in doc


def test_full_offline_build(mirror: Config) -> None:
    """Everything except crawl/sitemaps/upload, which need a live WordPress."""
    assert build(mirror, {"cleanup", "rewrite", "overlay", "bake"}, make_args()) == 0
    out = (mirror.site_dir / "post-a/index.html").read_text()

    assert "localhost:8000" not in out
    assert "<style>" in out                       # css inlined
    assert "eisai-child" not in out               # asset path flattened
    assert "OpenBSD" in out                       # generator scrubbed
    assert 'href=https://louie.se/feed.xml' in out or 'href="https://louie.se/feed.xml"' in out
    assert "canonical" in out
    # the shared JS was minified exactly once, on disk
    assert "var b" not in (mirror.site_dir / "assets/js/app.js").read_text()


def test_build_is_idempotent(mirror: Config) -> None:
    stages = {"cleanup", "rewrite", "overlay", "bake"}
    build(mirror, stages, make_args())
    first = (mirror.site_dir / "post-a/index.html").read_bytes()
    build(mirror, stages, make_args())
    assert (mirror.site_dir / "post-a/index.html").read_bytes() == first


def test_no_minify_leaves_readable_html(mirror: Config) -> None:
    cfg = replace(mirror, minify=False)
    build(cfg, {"rewrite", "bake"}, make_args())
    out = (cfg.site_dir / "post-a/index.html").read_text()
    assert "<!DOCTYPE html>" in out
    assert "</head>" in out


def test_overlay_never_ships_a_cloudflare_headers_file(mirror: Config) -> None:
    """_headers was Cloudflare syntax on an nginx host: inert, and published at
    https://louie.se/_headers for anyone to read. Server config belongs in
    _server/, which is outside the overlay."""
    apply_overlay(mirror)
    assert not (mirror.site_dir / "_headers").exists()
    assert not (mirror.repo_dir / "_overlay" / "_headers").exists()

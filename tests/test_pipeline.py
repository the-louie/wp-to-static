"""End-to-end tests of the stages that do not need a live WordPress."""

from __future__ import annotations

from dataclasses import replace

import argparse
from pathlib import Path

import pytest

from wp_to_static.__main__ import build
from wp_to_static.config import Config
from wp_to_static.mirror import cleanup, filter_sitemap_urls, write_sitemap_index
from wp_to_static.overlay import OverlayError, apply_overlay


def make_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        dry_run=False,
        build_data=None,
        feed_max_items=None,
        crosscheck_all=False,
        no_crosscheck=True,
        allow_shrink=False,
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


SAMPLE_CATEGORY_SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<url><loc>https://louie-se.i.louie.se/category/coding/</loc>"
    "<lastmod>2025-01-01</lastmod></url>"
    "<url><loc>https://louie-se.i.louie.se/category/about/</loc>"
    "<lastmod>2025-01-01</lastmod></url>"
    "</urlset>"
)


def test_filter_sitemap_drops_excluded_path() -> None:
    out, removed = filter_sitemap_urls(SAMPLE_CATEGORY_SITEMAP, ("category/about",))
    assert removed == 1
    assert "category/about" not in out
    assert "category/coding" in out  # a real page survives
    assert out.count("<url>") == 1


def test_filter_sitemap_matches_subpaths_not_prefixes() -> None:
    doc = (
        "<urlset>"
        "<url><loc>https://h/lost/</loc></url>"
        "<url><loc>https://h/lost-and-found/</loc></url>"
        "<url><loc>https://h/lost/page/2/</loc></url>"
        "</urlset>"
    )
    out, removed = filter_sitemap_urls(doc, ("lost",))
    assert removed == 2  # /lost/ and /lost/page/2/, not /lost-and-found/
    assert "lost-and-found" in out


def test_filter_sitemap_leaves_clean_file_untouched() -> None:
    doc = "<urlset><url><loc>https://h/real-post/</loc></url></urlset>"
    out, removed = filter_sitemap_urls(doc, ("category/about", "lost"))
    assert removed == 0
    assert out == doc


def test_post_tag_sitemap_provider_is_published() -> None:
    """Tag archives were promoted to real pages (self-canonical + H1 in the active
    theme), so the tag sitemap is advertised again."""
    from wp_to_static.mirror import SITEMAP_PROVIDERS

    assert "taxonomies-post_tag" in SITEMAP_PROVIDERS
    assert "posts-post" in SITEMAP_PROVIDERS
    assert "taxonomies-category" in SITEMAP_PROVIDERS


def test_empty_categories_stay_out_of_the_sitemap(cfg: Config) -> None:
    """The two empty category archives render (200) but are thin, so the build
    keeps them out of the sitemap via the per-URL exclude, not the provider list."""
    excludes = cfg.sitemap_exclude
    doc = (
        "<urlset>"
        "<url><loc>https://h/category/coding/</loc></url>"
        "<url><loc>https://h/category/about/</loc></url>"
        "<url><loc>https://h/category/uncategorised/</loc></url>"
        "</urlset>"
    )
    out, removed = filter_sitemap_urls(doc, excludes)
    assert removed == 2
    assert "category/coding" in out
    assert "category/about" not in out
    assert "category/uncategorised" not in out


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


def test_fetch_missing_assets_skips_unfetchable_and_present(mirror: Config) -> None:
    """Content can name assets the crawl never reached -- WordPress bakes
    absolute URLs into posts, so a host move leaves them off-host. Endpoints
    that cannot exist as files must not be requested."""
    from wp_to_static.mirror import LOCAL_REF_RE, UNFETCHABLE_PREFIXES

    page = (
        '<a href="/wp-json/">a</a><a href="/xmlrpc.php?rsd">b</a>'
        '<img src="/assets/theme.css"><img src="//cdn.example.com/x.png">'
    )
    refs = [r for r in LOCAL_REF_RE.findall(page)]
    keep = [
        r for r in refs
        if not r.startswith("//") and not r.startswith(UNFETCHABLE_PREFIXES)
    ]
    assert keep == ["/assets/theme.css"]          # the only fetchable candidate
    assert (mirror.site_dir / "assets/theme.css").exists()  # ...and it is present


def test_fetch_missing_pages_follows_pagination(mirror: Config, monkeypatch) -> None:
    """An archive nothing links to also has /page/N/ that the URL list omits."""
    from wp_to_static import mirror as m

    served = {
        f"{mirror.local_origin}/tag/x/": '<a href="/tag/x/page/2/">next</a>',
        f"{mirror.local_origin}/tag/x/page/2/": '<a href="/tag/x/page/3/">next</a>',
        f"{mirror.local_origin}/tag/x/page/3/": "<p>end</p>",
    }

    def fake_fetch(url, dest, *, required=True):
        if url not in served:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(served[url])
        return True

    monkeypatch.setattr(m, "fetch", fake_fetch)
    fetched, failed = m.fetch_missing_pages(mirror, [f"{mirror.local_origin}/tag/x/"])
    assert fetched == 3, "should follow pagination beyond the supplied URL"
    assert failed == []
    assert (mirror.site_dir / "tag/x/page/3/index.html").exists()


def test_fetch_missing_pages_reports_unreachable(mirror: Config, monkeypatch) -> None:
    from wp_to_static import mirror as m

    monkeypatch.setattr(m, "fetch", lambda url, dest, required=True: False)
    fetched, failed = m.fetch_missing_pages(mirror, [f"{mirror.local_origin}/category/about/"])
    assert fetched == 0 and len(failed) == 1


# --- .env loading -----------------------------------------------------------


def test_load_dotenv_parses_and_strips_quotes(tmp_path: Path) -> None:
    from wp_to_static.config import load_dotenv

    (tmp_path / ".env").write_text(
        '# comment\nWP_RANDOM_STRING="s3cret"\nOTHER=plain\n\nBAD_LINE\n'
    )
    got = load_dotenv(tmp_path / ".env")
    assert got == {"WP_RANDOM_STRING": "s3cret", "OTHER": "plain"}


def test_load_dotenv_missing_file_is_empty(tmp_path: Path) -> None:
    from wp_to_static.config import load_dotenv

    assert load_dotenv(tmp_path / "nope.env") == {}


def test_secret_is_picked_up_from_dotenv(tmp_path: Path, monkeypatch) -> None:
    """Without this the build silently degrades to stock REST."""
    from wp_to_static.config import Config

    monkeypatch.delenv("WPTS_API_SECRET", raising=False)
    (tmp_path / ".env").write_text("WP_RANDOM_STRING=from-dotenv\n")
    assert Config.from_env(tmp_path).api_secret == "from-dotenv"


def test_environment_beats_dotenv(tmp_path: Path, monkeypatch) -> None:
    from wp_to_static.config import Config

    monkeypatch.setenv("WPTS_API_SECRET", "from-env")
    (tmp_path / ".env").write_text("WP_RANDOM_STRING=from-dotenv\n")
    assert Config.from_env(tmp_path).api_secret == "from-env"


# --- upload error reporting -------------------------------------------------


def test_explain_names_the_common_partial_transfer_case() -> None:
    from wp_to_static.publish import explain

    msg = explain(23, "")
    assert "partial transfer" in msg
    assert "overwrite existing files" in msg


def test_explain_includes_the_offending_files() -> None:
    from wp_to_static.publish import explain

    stderr = (
        'rsync: [receiver] mkstemp "/mnt/x/index.html" failed: Permission denied (13)\n'
        'rsync: [receiver] chgrp "/mnt/x/feed.xml" failed: Operation not permitted (1)\n'
        "some noise that is not an error\n"
    )
    msg = explain(23, stderr)
    assert "index.html" in msg and "feed.xml" in msg
    assert "some noise" not in msg


def test_explain_truncates_long_error_lists() -> None:
    from wp_to_static.publish import explain

    stderr = "\n".join(f'rsync: file{i} failed: Permission denied' for i in range(20))
    msg = explain(23, stderr)
    assert "and 12 more" in msg


def test_explain_handles_unknown_code() -> None:
    from wp_to_static.publish import explain

    assert "rsync(1)" in explain(99, "")


def test_upload_omits_directory_times(mirror: Config, monkeypatch) -> None:
    """The web root has directories the uploading user does not own; setting
    their mtimes fails and turns a good upload into exit 23."""
    from wp_to_static import publish

    seen = {}

    class Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        publish.subprocess, "run", lambda cmd, **kw: (seen.update(cmd=cmd), Result())[1]
    )
    publish.upload(mirror)
    assert "--omit-dir-times" in seen["cmd"]
    assert "--delete" not in seen["cmd"], "would destroy hand-placed content"


# --- security.txt Expires ---------------------------------------------------


def test_security_txt_gets_an_expiry_one_year_out(mirror: Config) -> None:
    """RFC 9116 requires Expires, and a hardcoded date rots into an invalid
    file, so it is recomputed every build."""
    from datetime import date

    apply_overlay(mirror, today=date(2026, 8, 3))
    text = (mirror.site_dir / ".well-known/security.txt").read_text()
    assert "Expires: 2027-08-03T00:00:00Z" in text
    assert "Contact: h4xx0rZ@louie.se" in text
    assert "__EXPIRES__" not in text


def test_expiry_handles_leap_day(mirror: Config) -> None:
    """29 February has no counterpart next year."""
    from datetime import date

    from wp_to_static.overlay import security_txt_expiry

    assert security_txt_expiry(date(2028, 2, 29)) == "2029-02-28T00:00:00Z"
    assert security_txt_expiry(date(2027, 3, 1)) == "2028-03-01T00:00:00Z"


def test_expiry_is_always_in_the_future(mirror: Config) -> None:
    from datetime import date

    from wp_to_static.overlay import security_txt_expiry

    today = date.today()
    assert security_txt_expiry() > today.isoformat()


def test_overlay_leaves_no_unsubstituted_placeholders(mirror: Config) -> None:
    """Every __PLACEHOLDER__ in the overlay source must be substituted; one
    that isn't would ship literally."""
    import re

    from wp_to_static.overlay import substitutions

    known = set(substitutions(mirror))
    apply_overlay(mirror)
    for name in ("robots.txt", ".well-known/security.txt"):
        text = (mirror.site_dir / name).read_text()
        leftovers = set(re.findall(r"__[A-Z_]+__", text))
        assert not leftovers, f"{name} still contains {leftovers}"
    # and the placeholders we know about really are covered by the source files
    assert known == {"__DOMAIN__", "__EXPIRES__"}


def test_unsubstituted_domain_in_robots_is_caught(mirror: Config, tmp_path: Path) -> None:
    """The guard must fire if templating ever silently stops working."""
    import shutil as sh

    from wp_to_static.overlay import OverlayError

    broken = tmp_path / "overlay"
    (broken / ".well-known").mkdir(parents=True)
    (broken / "robots.txt").write_text("Sitemap: https://__DOMAIN__/sitemap.xml\n")
    (broken / ".well-known/security.txt").write_text("Contact: x\n")
    cfg = replace(mirror, repo_dir=tmp_path)
    sh.copytree(broken, cfg.overlay_dir, dirs_exist_ok=True)

    # force the substitution to be a no-op the way a renamed token would
    import wp_to_static.overlay as ov

    original = ov.substitutions
    ov.substitutions = lambda c, t=None: {}
    try:
        with pytest.raises(OverlayError, match="unsubstituted"):
            apply_overlay(cfg)
    finally:
        ov.substitutions = original

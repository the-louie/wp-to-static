"""Scrubbing WordPress fingerprints out of the generated site."""

from __future__ import annotations

from pathlib import Path

import pytest

from wp_to_static.config import Config
from wp_to_static.scrub import (
    CONTENT_ALLOWLIST,
    find_leftovers,
    fix_invalid_css,
    rename_classes,
    rename_paths,
    remove_dead_scripts,
    scrub_css,
    scrub_html,
    scrub_tree,
    scrub_xsl,
)

# --- paths ------------------------------------------------------------------


def test_path_segments_renamed() -> None:
    out, n = rename_paths('<img src="/wp-content/uploads/2026/07/x.jpg">')
    assert out == '<img src="/content/uploads/2026/07/x.jpg">'
    assert n == 1


def test_json_escaped_paths_renamed() -> None:
    out, _ = rename_paths(r'{"u":"\/wp-content\/uploads\/x.png"}')
    assert r"\/content\/" in out
    assert "wp-content" not in out


def test_percent_encoded_paths_renamed() -> None:
    out, _ = rename_paths("/x?u=%2Fwp-content%2Fa.png")
    assert "%2Fcontent%2F" in out


def test_wp_includes_renamed() -> None:
    out, _ = rename_paths('<script src="/wp-includes/js/x.js">')
    assert "/inc/js/x.js" in out


def test_path_rename_needs_separators() -> None:
    """A bare mention must not be mistaken for a path."""
    out, n = rename_paths("the wp-content directory")
    assert out == "the wp-content directory"
    assert n == 0


# --- dead machinery ---------------------------------------------------------


def test_emoji_polyfill_removed() -> None:
    html = '<script>window._wpemojiSettings={"x":1};var wpEmojiSettings=1;</script><p>hi</p>'
    out, n = remove_dead_scripts(html)
    assert n == 1 and "wpEmojiSettings" not in out and "<p>hi</p>" in out


def test_speculation_rules_removed() -> None:
    html = '<script type="speculationrules">{"not":{"href_matches":["/wp-*.php"]}}</script>'
    out, n = remove_dead_scripts(html)
    assert n == 1 and out.strip() == ""


def test_emoji_release_script_removed() -> None:
    html = '<script src="/wp-includes/js/wp-emoji-release.min.js"></script>'
    out, n = remove_dead_scripts(html)
    assert n == 1 and out.strip() == ""


def test_unrelated_scripts_survive() -> None:
    html = '<script src="/assets/js/app.js"></script><script>console.log(1)</script>'
    out, n = remove_dead_scripts(html)
    assert n == 0 and out == html


# --- classes ----------------------------------------------------------------


def test_block_classes_renamed_in_markup() -> None:
    out, n = rename_classes('<figure class="wp-block-image size-large">x</figure>')
    assert 'class="blk-image size-large"" ' not in out
    assert "blk-image" in out and "wp-block" not in out
    assert n == 1


def test_remaining_wp_classes_get_the_other_prefix() -> None:
    from wp_to_static.scrub import CLASS_RENAMES

    other = CLASS_RENAMES[1][1]
    out, _ = rename_classes('<body class="wp-singular wp-embed-responsive">')
    assert f"{other}singular" in out and f"{other}embed-responsive" in out
    assert "wp-" not in out


def test_classes_renamed_inside_style_blocks() -> None:
    from wp_to_static.scrub import CLASS_RENAMES

    other = CLASS_RENAMES[1][1]
    out, _ = rename_classes("<style>.wp-block-image{margin:0}.wp-caption{color:red}</style>")
    assert ".blk-image{margin:0}" in out
    assert f".{other}caption{{color:red}}" in out


def test_ids_renamed() -> None:
    out, _ = rename_classes('<style id="wp-block-library-inline-css">a{}</style>')
    assert 'id="blk-library-inline-css"' in out


def test_prose_is_never_touched() -> None:
    """A post on this site talks about wp-to-static by name."""
    html = "<p>I wrote wp-to-static to solve this.</p>"
    out, n = rename_classes(html)
    assert out == html and n == 0


def test_prose_survives_a_full_scrub() -> None:
    html = '<div class="wp-block-group"><p>see wp-to-static for details</p></div>'
    out, _ = scrub_html(html)
    assert "wp-to-static for details" in out
    assert 'class="blk-group"' in out


# --- the invalid selector ---------------------------------------------------


def test_invalid_selector_fixed() -> None:
    """Chained pseudo-elements make lightningcss reject the whole stylesheet,
    so 282KB ships unminified on every page."""
    css = ".has-drop-cap:not(:focus)::first-letter::after{content:''}"
    assert fix_invalid_css(css) == ".has-drop-cap:not(:focus)::first-letter{content:''}"


def test_fixed_css_actually_minifies() -> None:
    import minify_html

    bad = "/* Theme for WordPress */\n.a:not(:focus)::first-letter::after{content:''}\nb  {  color : red }"
    good = fix_invalid_css(bad)
    out = minify_html.minify(f"<style>{good}</style>", minify_css=True)
    assert "WordPress" not in out, "comment should be stripped once CSS parses"
    assert "b{color:red}" in out


def test_scrub_css_does_everything() -> None:
    out = scrub_css(".wp-block-x{background:url(/wp-content/a.png)}\n.y::first-letter::after{}")
    assert ".blk-x" in out
    assert "/content/a.png" in out
    assert "::first-letter::after" not in out


# --- sitemap stylesheets ----------------------------------------------------


def test_xsl_debranded() -> None:
    out = scrub_xsl("<h1>WordPress &raquo; Sitemap</h1><p>generated by WordPress</p>")
    assert "WordPress" not in out and "wordpress" not in out.lower()


# --- whole tree -------------------------------------------------------------


@pytest.fixture
def site(cfg: Config) -> Config:
    s = cfg.site_dir
    (s / "wp-content/uploads/2026").mkdir(parents=True)
    (s / "wp-content/themes/t").mkdir(parents=True)
    (s / "wp-includes/js").mkdir(parents=True)
    (s / "post").mkdir()

    (s / "wp-content/uploads/2026/pic.png").write_bytes(b"\x89PNG binary")
    (s / "wp-content/themes/t/style.css").write_text(
        "/* Theme for WordPress */\n.wp-block-image{margin:0}\n"
        ".a:not(:focus)::first-letter::after{content:''}\n"
    )
    (s / "wp-includes/js/wp-emoji-release.min.js").write_text("var e=1;")
    (s / "post/index.html").write_text(
        '<html><head><style id="wp-block-library-inline-css">.wp-block-image{margin:0}</style>'
        '<script>var wpEmojiSettings={};</script>'
        '<script type="speculationrules">{"href_matches":["/wp-admin/*"]}</script>'
        '</head><body class="wp-singular wp-theme-t">'
        '<figure class="wp-block-image"><img src="/wp-content/uploads/2026/pic.png"></figure>'
        "<p>I built wp-to-static for this</p></body></html>"
    )
    (s / "sitemap.xsl").write_text("<h1>WordPress Sitemap</h1>")
    (s / "feed.xml").write_text("<rss><link>/wp-content/uploads/2026/pic.png</link></rss>")
    return cfg


def test_scrub_tree_leaves_nothing_behind(site: Config) -> None:
    stats = scrub_tree(site)
    assert stats.leftovers == {}, stats.leftovers


def test_directories_renamed_on_disk(site: Config) -> None:
    scrub_tree(site)
    assert (site.site_dir / "content/uploads/2026/pic.png").is_file()
    assert (site.site_dir / "inc/js").is_dir()
    assert not (site.site_dir / "wp-content").exists()
    assert not (site.site_dir / "wp-includes").exists()


def test_markup_and_css_stay_consistent(site: Config) -> None:
    """The rename must hit both sides or the page loses its styling."""
    scrub_tree(site)
    html = (site.site_dir / "post/index.html").read_text()
    css = (site.site_dir / "content/themes/t/style.css").read_text()
    assert 'class="blk-image"' in html
    assert ".blk-image" in css


def test_references_follow_the_directory_rename(site: Config) -> None:
    scrub_tree(site)
    html = (site.site_dir / "post/index.html").read_text()
    assert '/content/uploads/2026/pic.png' in html
    assert (site.site_dir / "content/uploads/2026/pic.png").is_file()


def test_feed_paths_renamed_too(site: Config) -> None:
    scrub_tree(site)
    assert "/content/uploads" in (site.site_dir / "feed.xml").read_text()


def test_dead_scripts_gone_from_the_tree(site: Config) -> None:
    scrub_tree(site)
    html = (site.site_dir / "post/index.html").read_text()
    assert "wpEmojiSettings" not in html
    assert "speculationrules" not in html


def test_content_mention_survives_the_tree_scrub(site: Config) -> None:
    scrub_tree(site)
    html = (site.site_dir / "post/index.html").read_text()
    assert "wp-to-static" in html
    assert "wp-to-static" in CONTENT_ALLOWLIST


def test_leftovers_are_detected(site: Config) -> None:
    """The guard has to actually fire, or it proves nothing."""
    scrub_tree(site)
    (site.site_dir / "post/index.html").write_text('<div class="wp-block-missed"></div>')
    found = find_leftovers(site)
    assert "wp-block-missed" in found


def test_binary_files_untouched(site: Config) -> None:
    before = (site.site_dir / "wp-content/uploads/2026/pic.png").read_bytes()
    scrub_tree(site)
    assert (site.site_dir / "content/uploads/2026/pic.png").read_bytes() == before


# --- fingerprints that are not wp-* tokens ----------------------------------


def test_emoji_settings_json_removed() -> None:
    """It carries s.w.org CDN URLs into every page and nothing consumes it."""
    html = (
        '<script id="wp-emoji-settings" type="application/json">'
        '{"baseUrl":"https://s.w.org/images/core/emoji/17.0.2/72x72/"}</script><p>hi</p>'
    )
    out, n = remove_dead_scripts(html)
    assert n == 1 and "s.w.org" not in out and "<p>hi</p>" in out


def test_emoji_styles_removed() -> None:
    html = '<style id="wp-emoji-styles-inline-css">img.emoji{border:0}</style>'
    out, n = remove_dead_scripts(html)
    assert n == 1 and out.strip() == ""


def test_foreign_fingerprints_are_detected(site: Config) -> None:
    """The wp-* guard cannot see s.w.org, so it is checked separately."""
    scrub_tree(site)
    (site.site_dir / "post/index.html").write_text('<img src="https://s.w.org/x.png">')
    assert "s.w.org" in find_leftovers(site)


def test_orphaned_emoji_file_deleted(site: Config) -> None:
    scrub_tree(site)
    assert not list(site.site_dir.rglob("wp-emoji-release*.js"))


def test_standalone_css_is_minified_and_debranded(site: Config) -> None:
    """The inlined copy gets minified with the page; the served file needs it too."""
    scrub_tree(site)
    css = (site.site_dir / "content/themes/t/style.css").read_text()
    assert "WordPress" not in css
    assert "/*" not in css


def test_css_passthrough_when_unparseable() -> None:
    """minify_html returns the input unchanged if it cannot parse it; we must
    not mistake that for a successful minify."""
    broken = "@media {{{ this is not css"
    assert scrub_css(broken) == scrub_css(broken, minify=False)


# --- collision safety -------------------------------------------------------


def test_collision_detected(cfg: Config) -> None:
    """The theme already uses site-content; renaming wp-content onto it would
    merge the two silently. Whatever prefix is chosen, this must catch it."""
    from wp_to_static.scrub import CLASS_RENAMES, check_collisions

    target = CLASS_RENAMES[1][1]  # the non-block prefix
    cfg.site_dir.mkdir(parents=True)
    (cfg.site_dir / "a.html").write_text(
        f'<div class="{target}header"></div><div class="wp-header"></div>'
    )
    assert check_collisions(cfg) == {"wp-header": f"{target}header"}


def test_no_collision_on_a_clean_tree(site: Config) -> None:
    from wp_to_static.scrub import check_collisions

    assert check_collisions(site) == {}


def test_chosen_prefixes_avoid_the_theme_classes() -> None:
    """site- was rejected precisely because the theme uses site-content."""
    from wp_to_static.scrub import CLASS_RENAMES

    assert all(new != "site-" for _, new in CLASS_RENAMES)


def test_content_allowlist_never_counts_as_a_collision(cfg: Config) -> None:
    from wp_to_static.scrub import check_collisions

    cfg.site_dir.mkdir(parents=True)
    (cfg.site_dir / "a.html").write_text('<p>wp-to-static</p><div class="ui-to-static">')
    assert check_collisions(cfg) == {}


def test_leftover_scan_covers_text_files(cfg: Config) -> None:
    """robots.txt shipped Disallow: /wp-admin/ and an html-only scan missed it.
    It is also one of the first files a fingerprinter fetches."""
    cfg.site_dir.mkdir(parents=True)
    (cfg.site_dir / "robots.txt").write_text("User-agent: *\nDisallow: /wp-admin/\n")
    assert "wp-admin" in find_leftovers(cfg)


def test_overlay_robots_has_no_wordpress_paths(repo: Path) -> None:
    """A static site has no /wp-admin/, so disallowing it only advertises."""
    robots = (repo / "_overlay" / "robots.txt").read_text()
    assert "wp-" not in robots

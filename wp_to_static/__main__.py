"""Command line entry point.

    python -m wp_to_static                 # full build, no upload
    python -m wp_to_static --upload        # full build and publish
    python -m wp_to_static --no-minify     # for A/B diffing against the bash pipeline
    python -m wp_to_static --only rewrite bake
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from dataclasses import replace
from pathlib import Path

from . import bake, feeds, mirror, overlay, publish, verify, wpapi
from .config import Config
from .report import Report
from .rewrite import FeedLink, rewrite_css, rewrite_html, rewrite_xml, site_feed_links

STAGES = (
    "crawl",
    "pages",
    "sitemaps",
    "cleanup",
    "feeds",
    "rewrite",
    "assets",
    "overlay",
    "bake",
    "verify",
    "upload",
)


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def stage_rewrite(cfg: Config, term_links: dict[str, tuple[str, str, str]]) -> None:
    """Apply the URL rewrites to every html, css and xml file in the mirror.

    Archive pages additionally advertise their own term feed. The hrefs come
    from the generated feed set, never rebuilt from the file path, which is what
    keeps percent-encoded slugs correct.
    """
    site_links = site_feed_links(cfg)
    counts = {"html": 0, "css": 0, "xml": 0}
    archives_tagged = 0
    for path in sorted(cfg.site_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm"):
            links = list(site_links)
            entry = term_links.get(feeds.archive_dir_for(path, cfg))
            if entry:
                rss_url, atom_url, name = entry
                label = f"{cfg.domain}: {name}"
                links += [
                    FeedLink("application/rss+xml", label, rss_url),
                    FeedLink("application/atom+xml", label, atom_url),
                ]
                archives_tagged += 1
            kind, new = "html", rewrite_html(
                path.read_text(encoding="utf-8", errors="replace"), cfg, links
            )
        elif suffix == ".css":
            kind, new = "css", rewrite_css(
                path.read_text(encoding="utf-8", errors="replace")
            )
        elif suffix == ".xml":
            kind, new = "xml", rewrite_xml(
                path.read_text(encoding="utf-8", errors="replace"), cfg
            )
        else:
            continue
        path.write_text(new, encoding="utf-8")
        counts[kind] += 1
    log(
        f"rewrote html:{counts['html']} css:{counts['css']} xml:{counts['xml']} "
        f"(term feeds advertised on {archives_tagged} archive pages)"
    )


def stage_feeds(
    cfg: Config,
    args: argparse.Namespace,
    data: wpapi.BuildData,
    report: Report,
) -> dict[str, tuple[str, str, str]]:
    """Generate the site and per-term feeds, then check them against WordPress."""
    generated = feeds.generate(data, cfg, max_items=args.feed_max_items)
    written = generated.write_all(cfg)
    tags = sum(1 for t in data.terms if t.is_tag)
    log(
        f"feeds: {written} documents for {len(data.terms)} terms "
        f"({tags} tags, {len(data.terms) - tags} categories) from "
        f"{len(data.posts)} posts"
    )

    if args.no_crosscheck:
        report.warn("cross-check skipped; generated feeds are unverified")
        return generated.term_links

    context = wpapi.tls_context(cfg)

    def fetch(url: str) -> str:
        with urllib.request.urlopen(url, timeout=30, context=context) as response:
            return response.read().decode("utf-8", errors="replace")

    # Only guid membership and ordering are compared, not titles, dates or
    # body content. A feed could carry the right posts with wrong metadata and
    # still pass; accepted for now.
    sample = None if args.crosscheck_all else 5
    result = feeds.crosscheck_terms(data, cfg, fetch, sample=sample)
    if not result.ok:
        for failure in result.failures:
            report.error(f"cross-check: {failure}")
        return generated.term_links
    log(f"cross-check ok ({result.checked} terms verified against WordPress)")
    return generated.term_links


def build(cfg: Config, stages: set[str], args: argparse.Namespace) -> int:
    report = Report()

    # Plugin data is needed by two stages, so it is fetched once up front.
    data: wpapi.BuildData | None = None
    if {"pages", "feeds"} & stages:
        data = (
            wpapi.load_build_data(args.build_data)
            if args.build_data
            else wpapi.fetch_build_data(cfg)
        )
        if not data.from_plugin:
            report.warn(
                "build data came from stock REST, not the mu-plugin; feed URLs "
                "are reconstructed rather than authoritative"
            )
        elif data.schema < wpapi.EXPECTED_SCHEMA:
            # A stale copy of the plugin degrades the build without failing:
            # term membership silently falls back to each post's own term list,
            # which themes filter.
            report.warn(
                f"mu-plugin is out of date (schema {data.schema}, expected "
                f"{wpapi.EXPECTED_SCHEMA}). Term membership is falling back to "
                "per-post term lists, which themes can filter. Re-copy "
                "wp-plugin/louie-static-build.php to wp-content/mu-plugins/."
            )

    if "crawl" in stages:
        if not mirror.is_up(cfg):
            print(f"{cfg.local_origin}/ is not up", file=sys.stderr)
            return 1
        if cfg.base_dir.exists():
            shutil.rmtree(cfg.base_dir)
        cfg.site_dir.mkdir(parents=True)
        log("crawling")
        mirror.crawl(cfg)

    # wget only finds what something links to, so an archive nothing links to
    # is invisible to it. Without this we would publish a feed whose channel
    # <link> is a 404.
    if "pages" in stages and data is not None:
        fetched, unreachable = mirror.fetch_missing_pages(cfg, data.urls)
        log(f"pages: fetched {fetched} public URLs the crawl did not reach")
        for url in unreachable:
            report.warn(f"public URL could not be fetched: {url}")

    if "sitemaps" in stages:
        log("sitemaps")
        mirror.write_sitemap_index(cfg, mirror.fetch_sitemaps(cfg))

    if "cleanup" in stages:
        stats = mirror.cleanup(cfg)
        log(
            f"cleanup removed:{stats.query_pages_removed} query pages, "
            f"{stats.php_files_removed} php files, "
            f"renamed:{stats.ver_files_renamed} versioned assets"
        )

    # Feeds are generated before the rewrite stage on purpose: post links and
    # guids come out of WordPress with the local host, and the rewrite stage is
    # the one place that owns host rewriting for every *.xml in the tree.
    term_links: dict[str, tuple[str, str, str]] = {}
    if "feeds" in stages and data is not None:
        term_links = stage_feeds(cfg, args, data, report)

    if "rewrite" in stages:
        stage_rewrite(cfg, term_links)

    # After rewriting, every local reference is root-relative, so anything the
    # crawl could not reach can be re-requested from the current origin. Must
    # run before bake, which needs the files present to inline them.
    if "assets" in stages:
        fetched, still_missing = mirror.fetch_missing_assets(cfg)
        log(f"assets: fetched {fetched} referenced files the crawl missed")
        for path in still_missing:
            report.warn(f"referenced asset could not be fetched: {path}")

    if "overlay" in stages:
        copied = overlay.apply_overlay(cfg)
        log(f"overlay: {', '.join(copied)}")

    if "bake" in stages:
        log("baking" + ("" if cfg.minify else " (minification disabled)"))
        stats = bake.bake_tree(cfg)
        log(stats.summary())
        if stats.css_missing or stats.js_missing:
            report.warn(
                f"{stats.css_missing} css and {stats.js_missing} js references "
                "did not resolve in the mirror"
            )

    if "verify" in stages:
        growth = verify.check_growth(cfg, report, allow_shrink=args.allow_shrink)
        delta = "" if growth.delta is None else f" ({growth.delta:+d})"
        log(f"verify: {growth.pages} pages{delta}")

    if report.failed:
        report.emit()
        print(
            "\nBuild NOT fit to publish. Nothing was uploaded.",
            file=sys.stderr,
        )
        return 1

    if "upload" in stages:
        log("uploading")
        publish.upload(cfg, dry_run=args.dry_run)

    report.emit()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wp_to_static")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--no-minify",
        action="store_true",
        help="skip HTML/JS minification, for diffing against the bash pipeline",
    )
    parser.add_argument("--upload", action="store_true", help="publish when done")
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="accept a small drop in page count (see verify stage)",
    )
    parser.add_argument("--dry-run", action="store_true", help="rsync --dry-run")
    parser.add_argument("--only", nargs="+", choices=STAGES, metavar="STAGE")
    parser.add_argument("--skip", nargs="+", choices=STAGES, metavar="STAGE")
    parser.add_argument(
        "--build-data",
        type=Path,
        help="read build data from a captured JSON file instead of WordPress",
    )
    parser.add_argument(
        "--feed-max-items",
        type=int,
        default=None,
        help="cap items per feed (default: no cap, unlike WordPress's posts_per_rss)",
    )
    parser.add_argument(
        "--crosscheck-all",
        action="store_true",
        help="verify every term against WordPress instead of a sample of 5",
    )
    parser.add_argument(
        "--no-crosscheck",
        action="store_true",
        help="skip verification against WordPress's own feeds",
    )
    args = parser.parse_args(argv)

    cfg = Config.from_env(args.repo)
    if args.output:
        cfg = replace(cfg, base_dir=args.output)
    if args.no_minify:
        cfg = replace(cfg, minify=False)

    stages = set(args.only) if args.only else set(STAGES) - {"upload"}
    if args.upload:
        stages.add("upload")
    if args.skip:
        stages -= set(args.skip)

    return build(cfg, stages, args)


if __name__ == "__main__":
    raise SystemExit(main())

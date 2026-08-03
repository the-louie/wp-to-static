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
from dataclasses import replace
from pathlib import Path

from . import bake, feeds, mirror, overlay, publish, wpapi
from .config import Config
from .rewrite import FeedLink, rewrite_css, rewrite_html, rewrite_xml, site_feed_links

STAGES = (
    "crawl",
    "sitemaps",
    "cleanup",
    "feeds",
    "rewrite",
    "overlay",
    "bake",
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
    cfg: Config, args: argparse.Namespace
) -> dict[str, tuple[str, str, str]]:
    """Generate the site and per-term feeds, then check them against WordPress."""
    if args.build_data:
        data = wpapi.load_build_data(args.build_data)
    else:
        data = wpapi.fetch_build_data(cfg)

    generated = feeds.generate(data, cfg, max_items=args.feed_max_items)
    written = generated.write_all(cfg)
    tags = sum(1 for t in data.terms if t.is_tag)
    log(
        f"feeds: {written} documents for {len(data.terms)} terms "
        f"({tags} tags, {len(data.terms) - tags} categories) from "
        f"{len(data.posts)} posts"
    )

    if args.no_crosscheck:
        print(
            "WARNING: cross-check skipped; generated feeds are unverified",
            file=sys.stderr,
        )
        return generated.term_links

    def fetch(url: str) -> str:
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    sample = None if args.crosscheck_all else 5
    result = feeds.crosscheck_terms(data, cfg, fetch, sample=sample)
    if not result.ok:
        raise SystemExit(
            "cross-check failed against WordPress's own feeds:\n  "
            + "\n  ".join(result.failures)
        )
    log(f"cross-check ok ({result.checked} terms verified against WordPress)")
    return generated.term_links


def build(cfg: Config, stages: set[str], args: argparse.Namespace) -> int:
    if "crawl" in stages:
        if not mirror.is_up(cfg):
            print(f"{cfg.local_origin}/ is not up", file=sys.stderr)
            return 1
        if cfg.base_dir.exists():
            shutil.rmtree(cfg.base_dir)
        cfg.site_dir.mkdir(parents=True)
        log("crawling")
        mirror.crawl(cfg)

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
    if "feeds" in stages:
        term_links = stage_feeds(cfg, args)

    if "rewrite" in stages:
        stage_rewrite(cfg, term_links)

    if "overlay" in stages:
        copied = overlay.apply_overlay(cfg)
        log(f"overlay: {', '.join(copied)}")

    if "bake" in stages:
        log("baking" + ("" if cfg.minify else " (minification disabled)"))
        stats = bake.bake_tree(cfg)
        log(stats.summary())
        if stats.css_missing or stats.js_missing:
            print(
                f"WARNING: {stats.css_missing} css and {stats.js_missing} js "
                "references did not resolve in the mirror",
                file=sys.stderr,
            )

    if "upload" in stages:
        log("uploading")
        publish.upload(cfg, dry_run=args.dry_run)

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

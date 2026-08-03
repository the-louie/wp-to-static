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

from . import bake, mirror, overlay, publish
from .config import Config
from .rewrite import rewrite_css, rewrite_html, rewrite_xml, site_feed_links

STAGES = ("crawl", "sitemaps", "cleanup", "rewrite", "overlay", "bake", "upload")


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def stage_rewrite(cfg: Config) -> None:
    """Apply the URL rewrites to every html, css and xml file in the mirror."""
    links = site_feed_links(cfg)
    counts = {"html": 0, "css": 0, "xml": 0}
    for path in sorted(cfg.site_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm"):
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
    log(f"rewrote html:{counts['html']} css:{counts['css']} xml:{counts['xml']}")


def build(cfg: Config, stages: set[str], *, dry_run: bool) -> int:
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

    if "rewrite" in stages:
        stage_rewrite(cfg)

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
        publish.upload(cfg, dry_run=dry_run)

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

    return build(cfg, stages, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

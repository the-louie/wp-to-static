"""Crawling and post-crawl cleanup: the download half of mkstatic.sh.

wget keeps the crawling job. Its -mEpnp link-following and page-requisite
discovery is a lot of well-tested behaviour, and the mu-plugin's URL list
covers its one real weakness (pages nothing links to).

Every fetch here is checked and written atomically. The original used
`wget -O <target>`, which truncates the target before making the request, so a
404 left a zero-byte file that shipped and was referenced from the sitemap
index.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .config import PUBLIC_ASSET_PREFIX, THEME_ASSET_PREFIX, Config

WGET_BASE = ["wget", "--no-cache", "--no-cookies"]

# Paths the recursive crawl must not follow. Feeds are excluded because we
# publish our own; comment/author/admin/REST paths have no place in a static
# mirror.
CRAWL_EXCLUDES = ["wp-json", "author", "comments", "wp-admin"]

# Which WordPress sitemap providers to publish. post_tag is deliberately
# omitted: the 35 tag archives are thin lists with no canonical and no heading,
# so advertising them to crawlers only dilutes the index (see the 2026-11-24 SEO
# report). The tag pages themselves still ship, since the crawl follows links to
# them; they are simply not in the sitemap. Making the few biggest tags real
# pages, or adding noindex, is the theme/content sessions' call.
SITEMAP_PROVIDERS = (
    "posts-post",
    "posts-page",
    "taxonomies-category",
)

# One <url>…</url> entry in a WordPress sitemap. WP emits these in a fixed,
# well-formed shape (loc first), so a regex is enough and avoids pulling in an
# XML parser for a filter this small.
SITEMAP_URL_RE = re.compile(r"\s*<url>\s*<loc>(.*?)</loc>.*?</url>", re.DOTALL)


def _loc_excluded(loc: str, excludes: tuple[str, ...]) -> bool:
    """True when a sitemap loc's path is an excluded path or under one."""
    path = urlsplit(loc).path.strip("/")
    return any(path == e or path.startswith(f"{e}/") for e in excludes)


def filter_sitemap_urls(text: str, excludes: tuple[str, ...]) -> tuple[str, int]:
    """Drop <url> entries whose loc path is in the build's sitemap excludes.

    WordPress advertises every public URL, including ones that resolve to an
    error (the 404 target) or a page the build excludes (a 403 category). Those
    must not reach a crawler, so they are stripped here before the sitemap index
    is written. The loc still carries the build host at this stage, so the match
    is on the path only.
    """
    removed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal removed
        if _loc_excluded(match.group(1), excludes):
            removed += 1
            return ""
        return match.group(0)

    return SITEMAP_URL_RE.sub(repl, text), removed

# Assets the crawl cannot discover, because nothing links to them in a form
# wget follows. The emoji polyfill is deliberately absent: the scrub stage
# removes every script tag that would reference it, so fetching it would only
# add an unreachable file carrying WordPress strings.
EXTRA_ASSETS = (
    (
        "wp-content/themes/Eisai/assets/js/html5.min.js",
        "wp-content/themes/Eisai/assets/js/html5.min.js",
    ),
    (
        "wp-content/themes/eisai-child/assets/VCR_OSD_MONO_1.001.ttf",
        "assets/VCR_OSD_MONO_1.001.ttf",
    ),
    (
        "wp-content/themes/eisai-child/assets/MPLUSRounded1c-Medium.ttf",
        "assets/MPLUSRounded1c-Medium.ttf",
    ),
)


class MirrorError(RuntimeError):
    pass


@dataclass
class CleanupStats:
    query_pages_removed: int = 0
    ver_files_renamed: int = 0
    php_files_removed: int = 0


def is_up(cfg: Config) -> bool:
    result = subprocess.run(
        ["curl", "-so", "/dev/null", "--max-time", "10", f"{cfg.local_origin}/"],
        capture_output=True,
    )
    return result.returncode == 0


def fetch(url: str, dest: Path, *, required: bool = True) -> bool:
    """Fetch one URL to `dest`, atomically. Returns False if it failed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as handle:
        tmp = Path(handle.name)
    result = subprocess.run(
        [*WGET_BASE, "--tries=3", "--waitretry=2", "-q", "-O", str(tmp), url],
        capture_output=True,
    )
    if result.returncode != 0 or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        if required:
            raise MirrorError(f"failed to fetch {url}")
        return False
    tmp.replace(dest)
    dest.chmod(0o644)
    return True


def crawl(cfg: Config) -> None:
    """Recursive mirror of the whole site, plus the targeted extra fetches."""
    excludes: list[str] = []
    for path in CRAWL_EXCLUDES:
        excludes += ["-X", path]
    subprocess.run(
        [
            *WGET_BASE,
            *excludes,
            "--reject-regex=/feed/",
            "-mEpnp",
            f"{cfg.local_origin}/",
        ],
        cwd=cfg.base_dir,
        check=False,  # wget exits non-zero for any single broken link
    )
    # The crawl saves the front page under a name that depends on redirects;
    # fetch it explicitly so index.html is always right.
    fetch(f"{cfg.local_origin}/", cfg.site_dir / "index.html")
    subprocess.run(
        [*WGET_BASE, "-X", "wp-json", "-mEpnp", f"{cfg.local_origin}/lost/"],
        cwd=cfg.base_dir,
        check=False,
    )
    for remote, local in EXTRA_ASSETS:
        fetch(f"{cfg.local_origin}/{remote}", cfg.site_dir / local, required=False)

    _flatten_theme_assets(cfg)


def move_into(source: Path, target: Path) -> None:
    """Move everything from one directory into another, replacing conflicts.

    The target may already exist and hold files, so this merges rather than
    replacing wholesale. Entries already present in the target are removed
    first, because shutil.move refuses to overwrite a directory.
    """
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if destination.is_dir():
            shutil.rmtree(destination)
        elif destination.exists():
            destination.unlink()
        shutil.move(str(item), str(destination))


def _flatten_theme_assets(cfg: Config) -> None:
    """Move the child theme's assets to /assets/, matching the URL rewrite."""
    source = cfg.site_dir / THEME_ASSET_PREFIX.strip("/")
    if not source.is_dir():
        return
    move_into(source, cfg.site_dir / PUBLIC_ASSET_PREFIX.strip("/"))


def fetch_sitemaps(cfg: Config) -> list[str]:
    """Fetch every page of every sitemap provider.

    The original fetched only page 1 of each. WordPress paginates at 2000 URLs
    (wp_sitemaps_max_urls), so a site that grew past that silently lost the
    remainder.
    """
    fetch(f"{cfg.local_origin}/wp-sitemap-index.xsl", cfg.site_dir / "sitemap-index.xsl")
    fetch(f"{cfg.local_origin}/wp-sitemap.xsl", cfg.site_dir / "sitemap.xsl")

    written: list[str] = []
    for provider in SITEMAP_PROVIDERS:
        page = 1
        while True:
            name = f"sitemap-{provider}-{page}.xml"
            target = cfg.site_dir / name
            url = f"{cfg.local_origin}/wp-sitemap-{provider}-{page}.xml"
            if not fetch(url, target, required=False):
                break
            if cfg.sitemap_exclude:
                text = target.read_text(encoding="utf-8")
                filtered, removed = filter_sitemap_urls(text, cfg.sitemap_exclude)
                if removed:
                    target.write_text(filtered, encoding="utf-8")
            written.append(name)
            page += 1
    if not written:
        raise MirrorError("no sitemaps fetched; is the local WordPress serving them?")
    return written


def write_sitemap_index(cfg: Config, members: list[str]) -> None:
    """Generate the sitemap index from the files that actually exist."""
    entries = "".join(
        f"<sitemap><loc>{cfg.public_url(name)}</loc></sitemap>" for name in members
    )
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<?xml-stylesheet type="text/xsl" href="{cfg.public_url("sitemap-index.xsl")}" ?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</sitemapindex>\n"
    )
    (cfg.site_dir / "sitemap.xml").write_text(doc, encoding="utf-8")


PAGINATION_SUFFIX_RE = re.compile(r"/page/\d+$")


def fetch_missing_pages(cfg: Config, urls: list[str]) -> tuple[int, list[str]]:
    """Fetch public pages the crawl never reached.

    wget only finds what something links to. A term archive that nothing links
    to -- an internal tag the theme hides from listings, say -- is invisible to
    it, and we would otherwise publish a feed whose channel <link> is a 404.
    The plugin knows every public URL, so the gap is closeable.

    An archive fetched this way links to its own /page/N/, which the URL list
    does not enumerate, so pagination is followed from each page actually
    fetched until it stops producing new ones.

    Returns (fetched, still_missing).
    """
    fetched = 0
    failed: list[str] = []
    queue = list(urls)
    seen: set[str] = set()

    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)

        path = urlsplit(url).path.strip("/")
        target = (
            (cfg.site_dir / path / "index.html") if path else (cfg.site_dir / "index.html")
        )
        if target.exists():
            continue
        if not fetch(url, target, required=False):
            failed.append(url)
            continue
        fetched += 1

        # Queue this archive's pagination, e.g. /tag/x/page/2/. The base is the
        # archive root, not the page we are on -- otherwise page 2's link to
        # page 3 would not match and the walk would stop after one step.
        body = target.read_text(encoding="utf-8", errors="replace")
        base = PAGINATION_SUFFIX_RE.sub("", url.rstrip("/"))
        for href in re.findall(r'href=["\']([^"\']+)["\']', body):
            if href.startswith("/"):
                href = f"{cfg.local_origin}{href}"
            if href.startswith(f"{base}/page/") and href not in seen:
                queue.append(href)

    return fetched, failed


LOCAL_REF_RE = re.compile(r'(?:href|src)=["\']?(/[^"\'\s>]+)')

# Referenced paths that legitimately do not exist as files in a static mirror.
UNFETCHABLE_PREFIXES = ("/wp-json", "/xmlrpc.php", "/wp-admin", "/wp-login")


def fetch_missing_assets(cfg: Config, *, workers: int = 8) -> tuple[int, list[str]]:
    """Fetch assets referenced by the built pages but absent from the mirror.

    The crawl only follows URLs on the host it is crawling. WordPress bakes
    absolute URLs into post content at authoring time and never rewrites them,
    so a site that has changed hosts has content pointing at the old one --
    wget treats those as off-host and skips them, and the URL rewrite then
    produces a root-relative link to a file that was never downloaded. Here the
    paths are already rewritten, so re-requesting them from the current origin
    resolves it regardless of which host the content named.

    Ordering note: this runs after the rewrite stage, so whatever it fetches is
    never rewritten. That is fine for images, which is all it currently
    retrieves, but a stylesheet arriving this way would keep its unflattened
    theme paths and its build-host URLs. Left as-is deliberately -- the theme is
    to be made self-contained, which removes the case entirely. If that changes,
    move the sweep before the rewrite and re-request with absolute URLs instead.

    Returns (fetched, still_missing).
    """
    wanted: set[str] = set()
    for page in cfg.site_dir.rglob("*.html"):
        text = page.read_text(encoding="utf-8", errors="replace")
        for ref in LOCAL_REF_RE.findall(text):
            if ref.startswith("//") or ref.startswith(UNFETCHABLE_PREFIXES):
                continue
            path = ref.split("?", 1)[0].split("#", 1)[0]
            if not path or path.endswith("/"):
                continue
            if (cfg.site_dir / path.lstrip("/")).exists():
                continue
            wanted.add(path)

    if not wanted:
        return 0, []

    fetched: list[str] = []
    failed: list[str] = []

    def grab(path: str) -> None:
        target = cfg.site_dir / path.lstrip("/")
        if fetch(f"{cfg.local_origin}{path}", target, required=False):
            fetched.append(path)
        else:
            failed.append(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(grab, sorted(wanted)))

    return len(fetched), sorted(failed)


def cleanup(cfg: Config) -> CleanupStats:
    """Remove crawl artefacts that must not ship."""
    stats = CleanupStats()

    for path in cfg.site_dir.rglob("index.html*p=*.html"):
        path.unlink()
        stats.query_pages_removed += 1

    # wget names cache-busted assets "style.css?ver=1.2"; strip the query so
    # the file matches the rewritten href. Not rglob("*?ver=*") -- in glob
    # patterns "?" is a single-character wildcard, so that also matches names
    # like "Xver=".
    for path in sorted(cfg.site_dir.rglob("*")):
        if not path.is_file() or "?ver=" not in path.name:
            continue
        target = path.with_name(path.name.split("?ver=", 1)[0])
        if target == path:
            continue
        if target.exists():
            # Same asset reached by two URLs; drop the duplicate rather than
            # leaving it to ship alongside the canonical name.
            path.unlink()
        else:
            path.rename(target)
        stats.ver_files_renamed += 1

    for path in cfg.site_dir.rglob("*.php*"):
        if path.is_file():
            path.unlink()
            stats.php_files_removed += 1

    return stats

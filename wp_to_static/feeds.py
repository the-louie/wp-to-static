"""RSS 2.0 and Atom generation for the site and every tag/category.

We render the XML rather than fetching WordPress's, because WordPress caps
every feed at posts_per_rss (10 by default) and that cap applies to taxonomy
feeds too. Generating means no cap and no per-term HTTP round trips, at the
cost of owning correctness -- which is what crosscheck() guards.

Nothing here is derived from build time. WordPress's own lastBuildDate comes
from the last post modification, so an unchanged site regenerates byte-identical
feeds: rsync stays quiet and readers' conditional GETs keep working.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from .config import Config
from .wpapi import BuildData, Post, Site, Term

RSS_MIME = "application/rss+xml"
ATOM_MIME = "application/atom+xml"


def rfc822(value: datetime) -> str:
    return format_datetime(value)


def rfc3339(value: datetime) -> str:
    return value.isoformat()


def cdata(text: str) -> str:
    """Wrap in CDATA, splitting any embedded terminator."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def site_relative(url: str, cfg: Config) -> str:
    """Strip the origin from a WordPress URL, keeping the path as WP wrote it."""
    path = urlsplit(url).path
    return path.strip("/")


@dataclass(frozen=True)
class FeedFile:
    """One feed document destined for one path."""

    rel_path: str  # relative to the site root, e.g. tag/kod/feed.xml
    public_url: str
    body: str

    def write(self, cfg: Config) -> Path:
        target = cfg.site_dir / self.rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.body, encoding="utf-8")
        return target


def _items_updated(posts: list[Post], fallback: datetime | None) -> datetime | None:
    if posts:
        return max(p.modified_gmt for p in posts)
    return fallback


def render_rss(
    *,
    title: str,
    description: str,
    archive_url: str,
    self_url: str,
    language: str,
    posts: list[Post],
    use_excerpt: bool,
) -> str:
    updated = _items_updated(posts, None)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"'
        ' xmlns:content="http://purl.org/rss/1.0/modules/content/"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{escape(title)}</title>",
        f'<atom:link href="{escape(self_url)}" rel="self" type="{RSS_MIME}" />',
        f"<link>{escape(archive_url)}</link>",
        f"<description>{escape(description)}</description>",
        f"<language>{escape(language)}</language>",
    ]
    if updated:
        parts.append(f"<lastBuildDate>{rfc822(updated)}</lastBuildDate>")
    for post in posts:
        parts += [
            "<item>",
            f"<title>{escape(post.title)}</title>",
            f"<link>{escape(post.link)}</link>",
            f"<pubDate>{rfc822(post.date_gmt)}</pubDate>",
            f"<dc:creator>{cdata(post.author)}</dc:creator>",
            # Opaque identifier, copied verbatim from WordPress. Changing it
            # makes every subscriber re-download the whole feed.
            f'<guid isPermaLink="false">{escape(post.guid)}</guid>',
            f"<description>{cdata(post.excerpt)}</description>",
        ]
        if not use_excerpt and post.content:
            parts.append(f"<content:encoded>{cdata(post.content)}</content:encoded>")
        parts.append("</item>")
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(parts)


def render_atom(
    *,
    title: str,
    subtitle: str,
    archive_url: str,
    self_url: str,
    language: str,
    feed_id: str,
    posts: list[Post],
    use_excerpt: bool,
) -> str:
    updated = _items_updated(posts, None)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="{escape(language)}">',
        f"<title>{escape(title)}</title>",
        f"<subtitle>{escape(subtitle)}</subtitle>",
        f'<link rel="self" type="{ATOM_MIME}" href="{escape(self_url)}" />',
        f'<link rel="alternate" type="text/html" href="{escape(archive_url)}" />',
        f"<id>{escape(feed_id)}</id>",
    ]
    if updated:
        parts.append(f"<updated>{rfc3339(updated)}</updated>")
    for post in posts:
        parts += [
            "<entry>",
            f"<title>{escape(post.title)}</title>",
            f'<link rel="alternate" type="text/html" href="{escape(post.link)}" />',
            f"<id>{escape(post.guid)}</id>",
            f"<published>{rfc3339(post.date_gmt)}</published>",
            f"<updated>{rfc3339(post.modified_gmt)}</updated>",
            f"<author><name>{escape(post.author)}</name></author>",
            f'<summary type="html">{cdata(post.excerpt)}</summary>',
        ]
        if not use_excerpt and post.content:
            parts.append(f'<content type="html">{cdata(post.content)}</content>')
        parts.append("</entry>")
    parts += ["</feed>", ""]
    return "\n".join(parts)


def _feed_set(
    cfg: Config,
    *,
    directory: str,
    title: str,
    description: str,
    archive_public: str,
    feed_id: str,
    posts: list[Post],
    site: Site,
) -> list[FeedFile]:
    """Build the four documents for one archive: rss, atom and their aliases.

    The aliases exist so WordPress's original /feed/ and /feed/atom/ URLs keep
    working for anyone already subscribed. They carry the same items but a
    different rel="self", because rel="self" must name the URL the document is
    actually served at.
    """
    prefix = f"{directory}/" if directory else ""
    layout = [
        (f"{prefix}feed.xml", "rss"),
        (f"{prefix}atom.xml", "atom"),
        (f"{prefix}feed/index.xml", "rss"),
        (f"{prefix}feed/atom/index.xml", "atom"),
    ]

    files: list[FeedFile] = []
    for rel_path, kind in layout:
        # The alias is served at the directory URL, so rel="self" names that.
        if rel_path.endswith("feed/index.xml"):
            self_url = cfg.public_url(f"{prefix}feed/")
        elif rel_path.endswith("feed/atom/index.xml"):
            self_url = cfg.public_url(f"{prefix}feed/atom/")
        else:
            self_url = cfg.public_url(rel_path)

        if kind == "rss":
            body = render_rss(
                title=title,
                description=description,
                archive_url=archive_public,
                self_url=self_url,
                language=site.language,
                posts=posts,
                use_excerpt=site.use_excerpt,
            )
        else:
            body = render_atom(
                title=title,
                subtitle=description,
                archive_url=archive_public,
                self_url=self_url,
                language=site.language,
                feed_id=feed_id,
                posts=posts,
                use_excerpt=site.use_excerpt,
            )
        files.append(FeedFile(rel_path, self_url, body))
    return files


@dataclass
class GeneratedFeeds:
    files: list[FeedFile]
    # archive directory ("tag/kod") -> (rss url, atom url, term name).
    # Keyed by directory rather than term id because that is what an HTML file
    # path yields during the rewrite stage.
    term_links: dict[str, tuple[str, str, str]]

    def write_all(self, cfg: Config) -> int:
        for feed in self.files:
            feed.write(cfg)
        return len(self.files)


def generate(
    data: BuildData, cfg: Config, *, max_items: int | None = None
) -> GeneratedFeeds:
    """Generate the site feed plus one feed set per term."""
    files: list[FeedFile] = []
    term_links: dict[str, tuple[str, str, str]] = {}

    def limited(posts: list[Post]) -> list[Post]:
        return posts[:max_items] if max_items else posts

    files += _feed_set(
        cfg,
        directory="",
        title=data.site.name,
        description=data.site.description,
        archive_public=cfg.public_url(""),
        feed_id=cfg.public_url(""),
        posts=limited(data.posts),
        site=data.site,
    )

    for term in data.terms:
        directory = site_relative(term.link, cfg)
        if not directory or directory in cfg.feed_exclude:
            continue
        archive_public = cfg.public_url(f"{directory}/")
        label = f"{data.site.name}: {term.name}"
        files += _feed_set(
            cfg,
            directory=directory,
            title=label,
            description=term.description or label,
            archive_public=archive_public,
            feed_id=archive_public,
            posts=limited(data.posts_for(term)),
            site=data.site,
        )
        term_links[directory] = (
            cfg.public_url(f"{directory}/feed.xml"),
            cfg.public_url(f"{directory}/atom.xml"),
            term.name,
        )

    return GeneratedFeeds(files=files, term_links=term_links)


PAGINATION_RE = re.compile(r"/page/\d+$")


def archive_dir_for(path: Path, cfg: Config) -> str:
    """Archive directory an HTML file belongs to, or "" if it is not one.

    /tag/kod/index.html and /tag/kod/page/2/index.html are both the "tag/kod"
    archive.
    """
    try:
        relative = path.relative_to(cfg.site_dir)
    except ValueError:
        return ""
    directory = relative.parent.as_posix()
    if directory == ".":
        return ""
    return PAGINATION_RE.sub("", directory)


# --- cross-check ------------------------------------------------------------


@dataclass
class CrosscheckResult:
    checked: int = 0
    failures: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failures is None:
            self.failures = []

    @property
    def ok(self) -> bool:
        return not self.failures


def guids_in(xml: str) -> list[str]:
    """Extract guids from a WordPress RSS document, in order."""
    return re.findall(r"<guid[^>]*>([^<]+)</guid>", xml)


def crosscheck_terms(
    data: BuildData,
    cfg: Config,
    fetch,
    *,
    sample: int | None = 5,
) -> CrosscheckResult:
    """Compare our item sets against WordPress's own feeds.

    WordPress caps its feeds at posts_per_rss, so its guids must be an
    order-preserving prefix of ours. A guid WordPress has that we do not means
    our term membership or ordering is wrong.

    `fetch` is a callable taking a URL and returning the document text, injected
    so this is testable without a live instance.
    """
    result = CrosscheckResult()
    terms = data.terms if sample is None else data.terms[:sample]

    for term in terms:
        try:
            theirs = guids_in(fetch(term.feed_link))
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            result.failures.append(f"{term.taxonomy}/{term.slug}: fetch failed: {exc}")
            continue
        ours = [p.guid for p in data.posts_for(term)]
        result.checked += 1
        if theirs != ours[: len(theirs)]:
            missing = [g for g in theirs if g not in ours]
            detail = f"missing {missing}" if missing else "ordering differs"
            result.failures.append(f"{term.taxonomy}/{term.slug}: {detail}")
    return result

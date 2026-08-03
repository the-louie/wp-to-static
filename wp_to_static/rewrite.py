"""URL and markup rewriting: the port of textreplace_{html,css,xml}.sh.

Stage order inside rewrite_html() is load-bearing and matches the bash original:
the og/twitter/canonical rules must run before the general rule, because the
general rule turns every remaining absolute local URL into a root-relative one
and those three tags specifically need to stay absolute.

Two bugs in the sed originals are deliberately NOT reproduced; see
INDEX_HTML_RE and VER_QUERY_RE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import PUBLIC_ASSET_PREFIX, THEME_ASSET_PREFIX, Config

# WordPress emits its version in <meta name="generator"> and elsewhere.
WP_VERSION_RE = re.compile(r"WordPress\s\w+\.\w+\.*\w*")
WP_VERSION_REPLACEMENT = "OpenBSD 7.5 - ed"

SHORTLINK_RE = re.compile(r"<link rel=['\"]shortlink['\"][^>]*>")

# Feed autodiscovery links WordPress emits: site, comments, per-post comments,
# category, tag and search feeds. All are stripped and replaced with the feeds
# we actually publish.
FEED_LINK_RE = re.compile(
    r"<link\s+rel=['\"]alternate['\"]\s+type=['\"]application/(?:rss|atom)\+xml['\"][^>]*>"
)

# The original was s/\/index.html\?/\//g. In GNU BRE, \? is the "zero or one"
# quantifier applied to the preceding character, so it made the trailing "l"
# optional and also matched "/index.htm" -- it never matched a literal "?" at
# all, which is what the surrounding code clearly intended. Match exactly the
# generated filename instead.
INDEX_HTML_RE = re.compile(r"/index\.html")

# The original was s/\?ver=[0-9\.]\{1,\}//g -- digits and dots only. The file
# rename step it has to agree with strips everything after "?ver=", so a
# version like "6.1-rc1" left a dangling "-rc1" in the href while the file on
# disk had lost it, breaking the link. Strip the whole value consistently.
VER_QUERY_RE = re.compile(r"\?ver=[^\"'\s>&]*")


@dataclass(frozen=True)
class FeedLink:
    """One <link rel="alternate"> to inject into <head>."""

    mime: str
    title: str
    href: str

    def render(self) -> str:
        return (
            f'<link rel="alternate" type="{self.mime}" '
            f'title="{self.title}" href="{self.href}">'
        )


def _hosts_alternation(cfg: Config) -> str:
    return "|".join(re.escape(host) for host in cfg.source_hosts)


def _local_url_re(cfg: Config) -> re.Pattern[str]:
    """Matches http(s)://<any source host> with an optional trailing slash."""
    return re.compile(rf"https?://(?:{_hosts_alternation(cfg)})/?")


def _escaped_local_url_re(cfg: Config) -> re.Pattern[str]:
    r"""Matches the JSON-escaped form: http:\/\/localhost:8000\/"""
    return re.compile(rf"https?:\\/\\/(?:{_hosts_alternation(cfg)})\\/")


def rewrite_html(text: str, cfg: Config, feed_links: list[FeedLink] | None = None) -> str:
    """Apply the full HTML rewrite chain to one document."""
    local = f"(?:{_hosts_alternation(cfg)})"
    public = f"{cfg.public_origin}/"

    # 1. Tags that must keep an absolute URL. Line-anchored like the sed
    #    original, so a document with several of these is handled one per line.
    for pattern in (
        rf'^(.*meta property="og:.*)https?://{local}/(.*)$',
        rf'^(.*meta name="twitter:.*)https?://{local}/(.*)$',
        rf'^(.*link rel="canonical" href=")https?://{local}/(.*)$',
    ):
        text = re.sub(pattern, rf"\g<1>{public}\g<2>", text, flags=re.MULTILINE)

    # 2. Everything else becomes root-relative.
    text = _local_url_re(cfg).sub("/", text)
    text = _escaped_local_url_re(cfg).sub("/", text)

    # 3. Cache-busting query strings; the files themselves are renamed to match.
    text = VER_QUERY_RE.sub("", text)

    text = SHORTLINK_RE.sub("", text)
    text = INDEX_HTML_RE.sub("/", text)
    text = text.replace(THEME_ASSET_PREFIX, PUBLIC_ASSET_PREFIX)

    # 4. Feed autodiscovery: drop WordPress's, inject ours.
    text = FEED_LINK_RE.sub("", text)
    if feed_links:
        injected = "".join(link.render() for link in feed_links)
        text = text.replace("</head>", f"{injected}</head>", 1)

    return WP_VERSION_RE.sub(WP_VERSION_REPLACEMENT, text)


def rewrite_css(text: str) -> str:
    """Flatten the child-theme asset path, matching textreplace_css.sh."""
    return text.replace(THEME_ASSET_PREFIX, PUBLIC_ASSET_PREFIX)


def rewrite_xml(text: str, cfg: Config) -> str:
    """Rewrite the host in sitemaps and feeds, matching textreplace_xml.sh.

    The trailing slash is optional: a feed's channel <link> is the bare origin
    with no path, and sitemaps never hit that case so it went unnoticed in the
    sed version until feeds were added.
    """
    text = _local_url_re(cfg).sub(f"{cfg.public_origin}/", text)
    return text.replace("/wp-sitemap.xsl", "/sitemap.xsl")


def site_feed_links(cfg: Config) -> list[FeedLink]:
    """The two site-wide feeds, injected into every page."""
    return [
        FeedLink("application/rss+xml", cfg.domain, cfg.public_url("feed.xml")),
        FeedLink("application/atom+xml", cfg.domain, cfg.public_url("atom.xml")),
    ]

"""Client for the build-data endpoint, with a fallback for stock WordPress.

The mu-plugin is the intended source because it returns URLs produced by
WordPress's own link functions. The REST fallback exists so a build still runs
on an instance without the plugin, but it has to reconstruct feed URLs by
string concatenation -- exactly the thing the plugin removes -- so it warns
loudly and is not the supported path.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config

BUILD_DATA_PATH = "/wp-json/louie-static/v1/build-data"
# Schema the generator expects from the mu-plugin. A lower number means the
# copy installed in wp-content/mu-plugins/ is older than this checkout.
EXPECTED_SCHEMA = 2
REST_PATH = "/wp-json/wp/v2"
TIMEOUT = 60


class ApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class Term:
    taxonomy: str
    id: int
    slug: str
    name: str
    count: int
    link: str
    feed_link: str
    atom_link: str
    description: str = ""
    # Authoritative membership, resolved term -> posts. Empty only when the
    # source could not supply it.
    post_ids: tuple[int, ...] = ()

    @property
    def is_tag(self) -> bool:
        return self.taxonomy == "post_tag"


@dataclass(frozen=True)
class Post:
    id: int
    title: str
    link: str
    guid: str
    date_gmt: datetime
    modified_gmt: datetime
    author: str
    excerpt: str
    content: str
    categories: list[int] = field(default_factory=list)
    tags: list[int] = field(default_factory=list)
    thumbnail: str | None = None

    def in_term(self, term: Term) -> bool:
        ids = self.tags if term.is_tag else self.categories
        return term.id in ids


@dataclass(frozen=True)
class Site:
    name: str
    description: str
    url: str
    language: str
    category_base: str
    tag_base: str
    posts_per_rss: int
    use_excerpt: bool
    last_modified_gmt: str
    site_feed_rss: str
    site_feed_atom: str


@dataclass(frozen=True)
class BuildData:
    site: Site
    terms: list[Term]
    posts: list[Post]
    urls: list[str] = field(default_factory=list)
    from_plugin: bool = True
    schema: int = 0

    def posts_for(self, term: Term) -> list[Post]:
        """Posts carrying this term, newest first.

        Prefers the term -> posts membership supplied by the source. A post's
        own term list cannot be trusted: themes and plugins filter
        get_the_terms/wp_get_object_terms to hide internal tags like _featured
        from listings, which also strips them from the post's term list and
        from the REST "tags" field, while the term archive and its feed still
        include the post.
        """
        if term.post_ids:
            wanted = set(term.post_ids)
            return [p for p in self.posts if p.id in wanted]
        return [p for p in self.posts if p.in_term(term)]


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def tls_context(cfg: Config) -> ssl.SSLContext | None:
    """None means "use the default, verified context"."""
    if cfg.verify_tls:
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _get(
    url: str,
    headers: dict[str, str] | None = None,
    context: ssl.SSLContext | None = None,
) -> tuple[Any, dict[str, str]]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body, dict(response.headers)
    except urllib.error.HTTPError as exc:
        raise ApiError(f"{url} -> HTTP {exc.code}") from exc
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise ApiError(f"{url} -> {exc}") from exc


def parse_build_data(payload: dict[str, Any], *, from_plugin: bool = True) -> BuildData:
    """Turn the endpoint payload into typed objects."""
    raw_site = payload["site"]
    site = Site(
        name=raw_site["name"],
        description=raw_site.get("description", ""),
        url=raw_site["url"],
        language=raw_site.get("language", "en"),
        category_base=raw_site.get("category_base") or "category",
        tag_base=raw_site.get("tag_base") or "tag",
        posts_per_rss=int(raw_site.get("posts_per_rss", 10)),
        use_excerpt=bool(raw_site.get("use_excerpt", False)),
        last_modified_gmt=raw_site.get("last_modified_gmt", ""),
        site_feed_rss=raw_site.get("site_feed", {}).get("rss", ""),
        site_feed_atom=raw_site.get("site_feed", {}).get("atom", ""),
    )
    terms = [
        Term(
            taxonomy=t["taxonomy"],
            id=int(t["id"]),
            slug=t["slug"],
            name=t["name"],
            description=t.get("description", ""),
            count=int(t.get("count", 0)),
            link=t["link"],
            feed_link=t["feed_link"],
            atom_link=t["atom_link"],
            post_ids=tuple(int(x) for x in t.get("post_ids", ())),
        )
        for t in payload.get("terms", [])
    ]
    posts = [
        Post(
            id=int(p["id"]),
            title=p["title"],
            link=p["link"],
            guid=p["guid"],
            date_gmt=_parse_time(p["date_gmt"]),
            modified_gmt=_parse_time(p["modified_gmt"]),
            author=p.get("author", ""),
            excerpt=p.get("excerpt", ""),
            content=p.get("content", ""),
            categories=[int(x) for x in p.get("categories", [])],
            tags=[int(x) for x in p.get("tags", [])],
            thumbnail=p.get("thumbnail"),
        )
        for p in payload.get("posts", [])
    ]
    return BuildData(
        site=site,
        terms=terms,
        posts=posts,
        urls=list(payload.get("urls", [])),
        from_plugin=from_plugin,
        schema=int(payload.get("schema", 0)),
    )


def load_build_data(path: Path) -> BuildData:
    """Load a captured payload from disk (fixtures, offline builds)."""
    return parse_build_data(json.loads(path.read_text(encoding="utf-8")))


def fetch_build_data(cfg: Config) -> BuildData:
    """Fetch from the mu-plugin, falling back to stock REST."""
    if cfg.api_secret:
        url = f"{cfg.local_origin}{BUILD_DATA_PATH}"
        try:
            payload, _ = _get(
                url,
                {"X-Static-Build-Secret": cfg.api_secret},
                tls_context(cfg),
            )
            return parse_build_data(payload)
        except ApiError as exc:
            print(f"WARNING: build-data endpoint unavailable ({exc})", file=sys.stderr)
    else:
        print(
            "WARNING: no API secret configured; skipping the build-data endpoint",
            file=sys.stderr,
        )
    return _fetch_via_rest(cfg)


def _rest_collection(
    cfg: Config, name: str, params: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Page through a REST collection using X-WP-TotalPages."""
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        query = {"per_page": "100", "page": str(page), **(params or {})}
        url = f"{cfg.local_origin}{REST_PATH}/{name}?{urllib.parse.urlencode(query)}"
        body, headers = _get(url, context=tls_context(cfg))
        items.extend(body)
        total = int(headers.get("X-WP-TotalPages", "1") or 1)
        if page >= total:
            return items
        page += 1


def _fetch_via_rest(cfg: Config) -> BuildData:
    print(
        "WARNING: falling back to stock REST. Feed URLs will be reconstructed "
        "rather than taken from WordPress, so a non-default category/tag base "
        "or an unusual slug encoding may produce wrong links. Install "
        "wp-plugin/louie-static-build.php on the build instance.",
        file=sys.stderr,
    )

    terms: list[Term] = []
    for name, taxonomy, base, filter_param in (
        ("categories", "category", cfg.category_base, "categories"),
        ("tags", "post_tag", cfg.tag_base, "tags"),
    ):
        for raw in _rest_collection(cfg, name):
            link = raw.get("link") or f"{cfg.local_origin}/{base}/{raw['slug']}/"
            term_id = int(raw["id"])
            # One request per term, because a post's own "tags" field is
            # filterable and unreliable while the term filter is not. See
            # BuildData.posts_for.
            post_ids = tuple(
                int(p["id"])
                for p in _rest_collection(
                    cfg, "posts", {filter_param: str(term_id), "_fields": "id"}
                )
            )
            terms.append(
                Term(
                    taxonomy=taxonomy,
                    id=term_id,
                    slug=raw["slug"],
                    name=raw.get("name", raw["slug"]),
                    description=raw.get("description", ""),
                    count=int(raw.get("count", 0)),
                    link=link,
                    # Reconstructed. This is the assumption the plugin removes.
                    feed_link=f"{link.rstrip('/')}/feed/",
                    atom_link=f"{link.rstrip('/')}/feed/atom/",
                    post_ids=post_ids,
                )
            )

    posts: list[Post] = []
    for raw in _rest_collection(cfg, "posts"):
        posts.append(
            Post(
                id=int(raw["id"]),
                title=raw.get("title", {}).get("rendered", ""),
                link=raw["link"],
                guid=raw.get("guid", {}).get("rendered", raw["link"]),
                date_gmt=_parse_time(raw["date_gmt"]),
                modified_gmt=_parse_time(raw["modified_gmt"]),
                author="",
                excerpt=raw.get("excerpt", {}).get("rendered", ""),
                content=raw.get("content", {}).get("rendered", ""),
                categories=[int(x) for x in raw.get("categories", [])],
                tags=[int(x) for x in raw.get("tags", [])],
            )
        )

    # The REST index carries the site name and description. Without them every
    # feed ships with an empty <title>, which readers display as a blank
    # subscription.
    try:
        index, _ = _get(f"{cfg.local_origin}/wp-json/", context=tls_context(cfg))
    except ApiError:
        index = {}

    site = Site(
        name=index.get("name", ""),
        description=index.get("description", ""),
        url=index.get("home", f"{cfg.local_origin}") + "/",
        language="en",
        category_base=cfg.category_base,
        tag_base=cfg.tag_base,
        posts_per_rss=10,
        use_excerpt=False,
        last_modified_gmt="",
        site_feed_rss=f"{cfg.local_origin}/feed/",
        site_feed_atom=f"{cfg.local_origin}/feed/atom/",
    )
    return BuildData(site=site, terms=terms, posts=posts, from_plugin=False)

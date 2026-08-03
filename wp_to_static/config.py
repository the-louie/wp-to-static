"""Build configuration.

Everything that used to be a bare exported string in mkstatic.sh lives here as
one frozen object, so a stage can never disagree with another about where the
site tree is or what the public domain looks like. The old script had two
different spellings of the mirror directory ($OUTPUTDIR and a hardcoded
localhost:8000) plus an $LOCAL_DOMAIN that was never assigned at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# WordPress serves the mirror under a directory named after the host wget
# crawled, so the site tree name is derived from local_url rather than stored.
DEFAULT_LOCAL_URL = "louiese.i.louie.se"
DEFAULT_LOCAL_SCHEME = "https"
DEFAULT_DOMAIN = "louie.se"

# Hosts WordPress has served from previously. Stored data still refers to them
# -- a post's guid is written once at creation and never updated -- so they
# have to be normalised to the public domain alongside the current build host.
DEFAULT_LEGACY_HOSTS = ("localhost:8000", "louie_se.i.louie.se")
DEFAULT_UPLOAD_TARGET = "static:/mnt/storage/louie.se/www2/"
DEFAULT_SSH_KEY = "~/.ssh/keys/static-nokey"

# The child theme ships its assets under a long theme path that we flatten to
# /assets/ in the published site.
THEME_ASSET_PREFIX = "/wp-content/themes/eisai-child/assets/"
PUBLIC_ASSET_PREFIX = "/assets/"


def load_dotenv(path: Path) -> dict[str, str]:
    """Parse a KEY=value file. Missing or unreadable file yields {}.

    Deliberately not exported into os.environ: the values are returned so the
    caller decides what to use, and a secret in .env does not leak into every
    subprocess the build spawns (wget, rsync, curl).
    """
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class Config:
    repo_dir: Path
    base_dir: Path
    # Host (and port, if any) of the build instance. This is also the directory
    # name wget gives the mirror, and what the URL rewrites match on, so it must
    # not carry a scheme.
    local_url: str = DEFAULT_LOCAL_URL
    local_scheme: str = DEFAULT_LOCAL_SCHEME
    domain: str = DEFAULT_DOMAIN
    upload_target: str = DEFAULT_UPLOAD_TARGET
    ssh_key: str = DEFAULT_SSH_KEY
    minify: bool = True
    # Opt-out of TLS verification when talking to the build instance. Needed
    # only for internal hosts whose certificate does not strictly validate --
    # e.g. an underscore in the hostname, which RFC 1123 disallows, so a
    # wildcard certificate will not match it under OpenSSL's checker even
    # though curl and wget accept it. Never appropriate for a public host.
    verify_tls: bool = True
    # Hosts WordPress may still have baked into stored data, which must be
    # normalised to the public domain alongside the current build host.
    # WordPress stores a post's guid at creation time and never updates it, so
    # a site that has moved hosts carries the old one forever. Shipping that
    # verbatim would leak the build host into every feed item and change the
    # identifiers subscribers already hold.
    legacy_hosts: tuple[str, ...] = DEFAULT_LEGACY_HOSTS
    # Where bylines should point. The crawl excludes /author/ (CRAWL_EXCLUDES),
    # so author archives do not exist in the mirror and every byline would
    # otherwise be a 404. Set to None to leave the links untouched.
    author_page: str | None = "/who-am-i/"
    # Archive directories that should not get a feed, even though the term is
    # public. Keyed the same way as feeds.site_relative().
    feed_exclude: tuple[str, ...] = ("category/about",)
    # A build that publishes fewer pages than the last one is assumed to be a
    # failure rather than an edit. Small shrinks warn and can be overridden;
    # anything larger halts.
    shrink_warn_limit: int = 5

    @property
    def state_file(self) -> Path:
        """Build-to-build state, kept outside base_dir since that is wiped."""
        return self.repo_dir / ".wpts-state.json"
    # Taxonomy bases. Defaults match WordPress's own defaults; the mu-plugin
    # reports the real values so a Settings -> Permalinks change is picked up.
    tag_base: str = "tag"
    category_base: str = "category"
    # Shared secret for the build endpoint, if the mu-plugin is installed.
    api_secret: str | None = field(default=None, repr=False)

    @property
    def site_dir(self) -> Path:
        """Root of the mirrored tree: <base_dir>/localhost:8000."""
        return self.base_dir / self.local_url

    @property
    def overlay_dir(self) -> Path:
        return self.repo_dir / "_overlay"

    @property
    def local_origin(self) -> str:
        """Origin of the build WordPress, no trailing slash."""
        return f"{self.local_scheme}://{self.local_url}"

    @property
    def public_origin(self) -> str:
        """Origin of the published site, no trailing slash."""
        return f"https://{self.domain}"

    def public_url(self, path: str) -> str:
        """Absolute public URL for a site-root-relative path."""
        return f"{self.public_origin}/{path.lstrip('/')}"

    @property
    def source_hosts(self) -> tuple[str, ...]:
        """Every host that may appear in crawled or stored WordPress data."""
        return (self.local_url, *(h for h in self.legacy_hosts if h != self.local_url))

    @classmethod
    def from_env(cls, repo_dir: Path | None = None) -> "Config":
        repo = Path(repo_dir or os.environ.get("WPTS_REPO", ".")).resolve()
        # Load repo/.env before reading anything. Without this the build
        # silently falls back to stock REST whenever the secret is not exported,
        # which produces a quietly worse site rather than an obvious failure.
        env = load_dotenv(repo / ".env")
        base = Path(os.environ.get("WPTS_OUTPUT", repo / "output"))
        # Accept a full origin in WPTS_LOCAL_URL and split it, so callers can
        # paste the URL they actually browse to.
        raw = os.environ.get("WPTS_LOCAL_URL", DEFAULT_LOCAL_URL)
        scheme = os.environ.get("WPTS_LOCAL_SCHEME", DEFAULT_LOCAL_SCHEME)
        if "://" in raw:
            scheme, raw = raw.split("://", 1)
        raw = raw.rstrip("/")
        return cls(
            repo_dir=repo,
            base_dir=base,
            local_url=raw,
            local_scheme=scheme,
            domain=os.environ.get("WPTS_DOMAIN", DEFAULT_DOMAIN),
            upload_target=os.environ.get("WPTS_UPLOAD", DEFAULT_UPLOAD_TARGET),
            ssh_key=os.environ.get("WPTS_SSH_KEY", DEFAULT_SSH_KEY),
            api_secret=(
                os.environ.get("WPTS_API_SECRET")
                or env.get("WPTS_API_SECRET")
                # The secret has lived in .env under this name since before the
                # generator read the file itself.
                or env.get("WP_RANDOM_STRING")
            ),
            verify_tls=os.environ.get("WPTS_INSECURE", "") == "",
        )

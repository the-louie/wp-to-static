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
DEFAULT_LOCAL_URL = "localhost:8000"
DEFAULT_DOMAIN = "louie.se"
DEFAULT_UPLOAD_TARGET = "static:/mnt/storage/louie.se/www2/"
DEFAULT_SSH_KEY = "~/.ssh/keys/static-nokey"

# The child theme ships its assets under a long theme path that we flatten to
# /assets/ in the published site.
THEME_ASSET_PREFIX = "/wp-content/themes/eisai-child/assets/"
PUBLIC_ASSET_PREFIX = "/assets/"


@dataclass(frozen=True)
class Config:
    repo_dir: Path
    base_dir: Path
    local_url: str = DEFAULT_LOCAL_URL
    domain: str = DEFAULT_DOMAIN
    upload_target: str = DEFAULT_UPLOAD_TARGET
    ssh_key: str = DEFAULT_SSH_KEY
    minify: bool = True
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
        """Origin of the local WordPress, no trailing slash."""
        return f"http://{self.local_url}"

    @property
    def public_origin(self) -> str:
        """Origin of the published site, no trailing slash."""
        return f"https://{self.domain}"

    def public_url(self, path: str) -> str:
        """Absolute public URL for a site-root-relative path."""
        return f"{self.public_origin}/{path.lstrip('/')}"

    @classmethod
    def from_env(cls, repo_dir: Path | None = None) -> "Config":
        repo = Path(repo_dir or os.environ.get("WPTS_REPO", ".")).resolve()
        base = Path(os.environ.get("WPTS_OUTPUT", repo / "output"))
        return cls(
            repo_dir=repo,
            base_dir=base,
            local_url=os.environ.get("WPTS_LOCAL_URL", DEFAULT_LOCAL_URL),
            domain=os.environ.get("WPTS_DOMAIN", DEFAULT_DOMAIN),
            upload_target=os.environ.get("WPTS_UPLOAD", DEFAULT_UPLOAD_TARGET),
            ssh_key=os.environ.get("WPTS_SSH_KEY", DEFAULT_SSH_KEY),
            api_secret=os.environ.get("WPTS_API_SECRET"),
        )

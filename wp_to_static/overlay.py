"""Overlay files and robots.txt.

The bash original rsynced "${STARTDIR}/overlay/" (the directory is _overlay)
into "./$OUTPUTDIR/" (a variable that was never assigned), with no exit check.
Nothing in _overlay/ had ever reached the live site.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import Config

DOMAIN_PLACEHOLDER = "__DOMAIN__"


class OverlayError(RuntimeError):
    pass


def apply_overlay(cfg: Config) -> list[str]:
    """Copy _overlay/ into the site root and template robots.txt."""
    if not cfg.overlay_dir.is_dir():
        raise OverlayError(f"overlay directory missing: {cfg.overlay_dir}")

    copied: list[str] = []
    for source in sorted(cfg.overlay_dir.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(cfg.overlay_dir)
        destination = cfg.site_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative.as_posix())

    robots = cfg.site_dir / "robots.txt"
    if not robots.is_file():
        raise OverlayError("robots.txt missing from overlay")
    # _overlay/robots.txt is the single source of truth; only the sitemap URL
    # is templated so the domain stays defined in one place.
    text = robots.read_text(encoding="utf-8")
    robots.write_text(text.replace(DOMAIN_PLACEHOLDER, cfg.domain), encoding="utf-8")

    return copied

"""Overlay files and robots.txt.

The bash original rsynced "${STARTDIR}/overlay/" (the directory is _overlay)
into "./$OUTPUTDIR/" (a variable that was never assigned), with no exit check.
Nothing in _overlay/ had ever reached the live site.

Overlay files may contain placeholders, substituted on copy so the source stays
the single definition and nothing has to be kept in sync by hand.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from .config import Config

DOMAIN_PLACEHOLDER = "__DOMAIN__"
EXPIRES_PLACEHOLDER = "__EXPIRES__"


class OverlayError(RuntimeError):
    pass


def security_txt_expiry(today: date | None = None) -> str:
    """RFC 9116 Expires: one year out, refreshed every build.

    RFC 9116 requires the field and says the value should be less than a year
    ahead, so a hardcoded date silently rots into an invalid file. Recomputing
    each build means it can never go stale.

    This is the one place build time legitimately reaches the output. Feeds
    deliberately carry nothing time-derived -- a changing timestamp there would
    push every feed on every build and defeat conditional GET -- but security.txt
    has no subscribers, and a 60-byte file re-uploading is not worth a stale
    expiry date.
    """
    today = today or date.today()
    try:
        expiry = today.replace(year=today.year + 1)
    except ValueError:
        # 29 February: there is no such date next year.
        expiry = today.replace(year=today.year + 1, day=28)
    return expiry.strftime("%Y-%m-%dT00:00:00Z")


def substitutions(cfg: Config, today: date | None = None) -> dict[str, str]:
    return {
        DOMAIN_PLACEHOLDER: cfg.domain,
        EXPIRES_PLACEHOLDER: security_txt_expiry(today),
    }


def apply_overlay(cfg: Config, today: date | None = None) -> list[str]:
    """Copy _overlay/ into the site root, substituting placeholders."""
    if not cfg.overlay_dir.is_dir():
        raise OverlayError(f"overlay directory missing: {cfg.overlay_dir}")

    values = substitutions(cfg, today)
    copied: list[str] = []

    for source in sorted(cfg.overlay_dir.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(cfg.overlay_dir)
        destination = cfg.site_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

        # Substitute only where a placeholder is actually present, and only in
        # files that are text at all, so binary overlay assets pass through.
        try:
            text = destination.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            copied.append(relative.as_posix())
            continue
        if any(token in text for token in values):
            for token, value in values.items():
                text = text.replace(token, value)
            destination.write_text(text, encoding="utf-8")

        copied.append(relative.as_posix())

    robots = cfg.site_dir / "robots.txt"
    if not robots.is_file():
        raise OverlayError("robots.txt missing from overlay")
    if DOMAIN_PLACEHOLDER in robots.read_text(encoding="utf-8"):
        raise OverlayError("robots.txt still contains an unsubstituted placeholder")

    return copied

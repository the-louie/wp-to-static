"""Post-build sanity checks.

The crawl runs with check=False, because wget exits non-zero for any single
broken link and that must not fail a build. The cost is that a genuinely failed
crawl -- WordPress down mid-run, DNS blip, a redirect loop -- produces a small
but structurally valid tree that the rest of the pipeline will happily process.
Since the upload has no --delete, publishing that would silently leave the site
partially updated with no error anywhere.

So the page count is compared against the previous build. A site gains pages
over time; it does not lose them by accident.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .report import Report


@dataclass
class GrowthResult:
    pages: int
    previous: int | None
    ok: bool

    @property
    def delta(self) -> int | None:
        return None if self.previous is None else self.pages - self.previous


def count_pages(cfg: Config) -> int:
    return sum(1 for _ in cfg.site_dir.rglob("*.html"))


def load_state(cfg: Config) -> dict:
    try:
        return json.loads(cfg.state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(cfg: Config, pages: int) -> None:
    state = load_state(cfg)
    state["pages"] = pages
    cfg.state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    share_with_group(cfg.state_file)


def share_with_group(path: Path) -> None:
    """Make a generated file writable by whoever else builds this repo.

    Builds run as more than one user, so a state file created by one of them
    must not lock the others out. Inheriting the parent directory's group is
    what a setgid directory would do; doing it explicitly means the repo does
    not have to be set up that way, and the repo root cannot be chmod'ed by
    anyone but its owner anyway.

    Best effort: failures here must never fail a build.
    """
    try:
        gid = path.parent.stat().st_gid
        if path.stat().st_gid != gid:
            os.chown(path, -1, gid)
        path.chmod(path.stat().st_mode | stat.S_IRGRP | stat.S_IWGRP)
    except (OSError, PermissionError):
        pass


def check_growth(cfg: Config, report: Report, *, allow_shrink: bool = False) -> GrowthResult:
    """Compare this build's page count against the last recorded one."""
    pages = count_pages(cfg)
    previous = load_state(cfg).get("pages")

    if previous is None:
        report.warn(
            f"no previous build recorded; accepting {pages} pages as the baseline"
        )
        save_state(cfg, pages)
        return GrowthResult(pages, None, True)

    delta = pages - previous
    if delta >= 0:
        save_state(cfg, pages)
        return GrowthResult(pages, previous, True)

    lost = -delta
    if lost > cfg.shrink_warn_limit:
        report.error(
            f"page count fell from {previous} to {pages} ({lost} lost). "
            "A drop this large means the crawl failed rather than that content "
            "was removed. Not publishing. Investigate, then delete "
            f"{cfg.state_file.name} to accept the new count as the baseline."
        )
        return GrowthResult(pages, previous, False)

    if not allow_shrink:
        report.error(
            f"page count fell from {previous} to {pages} ({lost} lost). "
            "If those pages really were deleted, re-run with --allow-shrink."
        )
        return GrowthResult(pages, previous, False)

    report.warn(
        f"page count fell from {previous} to {pages} ({lost} lost); "
        "accepted via --allow-shrink"
    )
    save_state(cfg, pages)
    return GrowthResult(pages, previous, True)

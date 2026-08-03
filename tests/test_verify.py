"""Growth check: a build that publishes fewer pages is assumed to be a failure."""

from __future__ import annotations

from pathlib import Path

from wp_to_static.config import Config
from wp_to_static.report import Report
from wp_to_static.verify import check_growth, count_pages, load_state, save_state


def make_pages(cfg: Config, count: int) -> None:
    for existing in cfg.site_dir.rglob("*.html"):
        existing.unlink()
    for i in range(count):
        page = cfg.site_dir / f"p{i}" / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("<html></html>")


def fresh(cfg: Config) -> Config:
    """Keep state out of the real repo."""
    moved = Config(
        repo_dir=cfg.base_dir.parent, base_dir=cfg.base_dir, local_url="localhost:8000"
    )
    moved.site_dir.mkdir(parents=True, exist_ok=True)
    return moved


def test_first_build_sets_the_baseline(cfg: Config) -> None:
    c = fresh(cfg)
    make_pages(c, 10)
    report = Report()
    result = check_growth(c, report)
    assert result.ok and result.previous is None
    assert load_state(c)["pages"] == 10
    assert any("baseline" in w for w in report.warnings)


def test_growth_is_accepted(cfg: Config) -> None:
    c = fresh(cfg)
    make_pages(c, 10); save_state(c, 8)
    report = Report()
    result = check_growth(c, report)
    assert result.ok and result.delta == 2
    assert not report.errors
    assert load_state(c)["pages"] == 10


def test_equal_count_is_accepted(cfg: Config) -> None:
    c = fresh(cfg)
    make_pages(c, 10); save_state(c, 10)
    report = Report()
    assert check_growth(c, report).ok
    assert not report.errors


def test_small_shrink_fails_but_is_overridable(cfg: Config) -> None:
    c = fresh(cfg)
    make_pages(c, 7); save_state(c, 10)
    report = Report()
    assert not check_growth(c, report).ok
    assert any("--allow-shrink" in e for e in report.errors)
    # state must not advance on a rejected build
    assert load_state(c)["pages"] == 10

    allowed = Report()
    assert check_growth(c, allowed, allow_shrink=True).ok
    assert not allowed.errors
    assert load_state(c)["pages"] == 7


def test_large_shrink_halts_and_is_not_overridable(cfg: Config) -> None:
    c = fresh(cfg)
    make_pages(c, 2); save_state(c, 50)
    report = Report()
    assert not check_growth(c, report, allow_shrink=True).ok
    assert any("crawl failed" in e for e in report.errors)
    assert load_state(c)["pages"] == 50  # baseline preserved


def test_boundary_is_inclusive(cfg: Config) -> None:
    """Exactly shrink_warn_limit lost is the overridable case; one more is not."""
    c = fresh(cfg)
    make_pages(c, 5); save_state(c, 10)          # lost 5
    assert check_growth(c, Report(), allow_shrink=True).ok

    make_pages(c, 4); save_state(c, 10)          # lost 6
    report = Report()
    assert not check_growth(c, report, allow_shrink=True).ok
    assert any("crawl failed" in e for e in report.errors)


def test_count_pages_counts_html_only(cfg: Config) -> None:
    c = fresh(cfg)
    make_pages(c, 3)
    (c.site_dir / "feed.xml").write_text("<rss/>")
    assert count_pages(c) == 3

"""CSS inlining and minification: the port of bake-js.js.

Two structural changes from the Node original:

1. JS files are minified exactly once, in their own pass over the tree, instead
   of once per HTML page that references them. The original re-minified a
   shared file (jquery, the theme bundle) from every page concurrently under
   `parallel`, so N processes did read-modify-write on the same path. It
   survived in practice because minification is idempotent, but the race was
   real and only became reachable once asset resolution was fixed.

2. Assets are resolved against the configured site root rather than a hardcoded
   "./site/" that had not existed for a long time, which silently made the
   whole stage a no-op.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import minify_html

from .config import Config

CSS_LINK_RE = re.compile(
    r"""<link\s[^>]*rel=["']stylesheet["'][^>]*?href=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)
SCRIPT_SRC_RE = re.compile(
    r"""<script\s[^>]*src=["']([^"']+)["'][^>]*>\s*</script>""", re.IGNORECASE
)

# Minifying these breaks them; carried over verbatim from bake-js.js.
EXCLUDE_MINIFY = frozenset(
    {
        "wp-content/plugins/megamenu/js/maxmegamenu.js",
        "wp-includes/js/jquery/jquery.min.js",
        "wp-includes/js/hoverIntent.min.js",
        "wp-content/themes/eisai-child/assets/js/font-awesome.js",
    }
)

# A closing script tag anywhere in the source terminates the wrapper element
# early, which makes minify_html treat the remainder as HTML text and
# entity-escape it. Detect and skip rather than corrupt.
SCRIPT_CLOSE_RE = re.compile(r"</\s*script", re.IGNORECASE)


@dataclass
class BakeStats:
    css_inlined: int = 0
    css_missing: int = 0
    js_rewritten: int = 0
    js_missing: int = 0
    js_minified: int = 0
    js_skipped: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"css inlined:{self.css_inlined} missing:{self.css_missing} | "
            f"js rewritten:{self.js_rewritten} missing:{self.js_missing} "
            f"minified:{self.js_minified} skipped:{len(self.js_skipped)}"
        )


def resolve_asset(url: str, cfg: Config) -> Path | None:
    """Map a site-root-relative asset URL to a path in the mirror.

    Returns None for remote URLs, which are left alone.
    """
    if url.startswith(("http://", "https://", "//", "data:")):
        return None
    # wget stores some hrefs with the query separator percent-encoded.
    clean = url.replace("%3F", "?").split("?", 1)[0].split("#", 1)[0]
    if not clean:
        return None
    return cfg.site_dir / clean.lstrip("/")


def minify_js_source(js: str) -> str | None:
    """Minify standalone JS. Returns None when it cannot be done safely.

    minify_html has no standalone JS entry point, so the source is wrapped in a
    <script> element and unwrapped afterwards. That is only sound when the
    source cannot terminate the element itself.
    """
    if SCRIPT_CLOSE_RE.search(js):
        return None
    wrapped = minify_html.minify(f"<script>{js}</script>", minify_js=True)
    if not (wrapped.startswith("<script>") and wrapped.endswith("</script>")):
        return None
    out = wrapped[len("<script>") : -len("</script>")]
    return out or None


def minify_js_tree(cfg: Config, stats: BakeStats) -> None:
    """Minify every .js file in the mirror, exactly once."""
    for path in sorted(cfg.site_dir.rglob("*.js")):
        rel = path.relative_to(cfg.site_dir).as_posix()
        if rel in EXCLUDE_MINIFY:
            stats.js_skipped.append(rel)
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            stats.js_skipped.append(rel)
            continue
        minified = minify_js_source(source)
        if minified is None:
            stats.js_skipped.append(rel)
            continue
        path.write_text(minified, encoding="utf-8")
        stats.js_minified += 1


def bake_html(text: str, cfg: Config, stats: BakeStats) -> str:
    """Inline local CSS, normalise local script tags, then minify."""

    def inline_css(match: re.Match[str]) -> str:
        target = resolve_asset(match.group(1), cfg)
        if target is None:
            return match.group(0)  # remote stylesheet, leave as a link
        if not target.is_file():
            stats.css_missing += 1
            return match.group(0)
        css = target.read_text(encoding="utf-8", errors="replace")
        stats.css_inlined += 1
        return f"<style>{css}</style>"

    def normalise_script(match: re.Match[str]) -> str:
        target = resolve_asset(match.group(1), cfg)
        if target is None:
            return match.group(0)
        if not target.is_file():
            stats.js_missing += 1
            return match.group(0)
        rel = target.relative_to(cfg.site_dir).as_posix()
        stats.js_rewritten += 1
        return f'<script src="/{rel}"></script>'

    text = CSS_LINK_RE.sub(inline_css, text)
    text = SCRIPT_SRC_RE.sub(normalise_script, text)

    if not cfg.minify:
        return text
    return minify_html.minify(
        text,
        minify_css=True,
        minify_js=True,
        keep_comments=False,
        keep_closing_tags=False,
        keep_html_and_head_opening_tags=False,
    )


def bake_tree(cfg: Config) -> BakeStats:
    """Minify all JS once, then bake every HTML page."""
    stats = BakeStats()
    minify_js_tree(cfg, stats)
    for path in sorted(cfg.site_dir.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(bake_html(text, cfg, stats), encoding="utf-8")
    return stats

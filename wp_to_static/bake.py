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

# Libraries that break when minified again, usually because they are already
# minified and rely on constructs the minifier rewrites.
#
# Paths are relative to the site root and must be written as they exist when
# bake runs, which is after the scrub stage has renamed wp-content to content
# and wp-includes to inc. An entry that matches nothing is reported rather than
# ignored, so a list that has drifted out of date is visible instead of silently
# protecting nothing.
EXCLUDE_MINIFY = frozenset(
    {
        "content/plugins/megamenu/js/maxmegamenu.js",
        "inc/js/jquery/jquery.min.js",
        "inc/js/hoverIntent.min.js",
        "content/themes/louie-theme/assets/js/uikit.min.js",
        "content/themes/louie-theme/assets/js/uikit-icons.min.js",
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
    unmatched_exclusions: list[str] = field(default_factory=list)

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


def minify_wrapped(source: str, tag: str, **options) -> str | None:
    """Minify a standalone stylesheet or script via minify_html.

    minify_html only accepts documents, so the source is wrapped in an element
    and unwrapped afterwards. Returns None when the wrapper did not survive,
    which happens if the source terminates the element itself; slicing blindly
    in that case would return malformed output.
    """
    open_tag, close_tag = f"<{tag}>", f"</{tag}>"
    out = minify_html.minify(f"{open_tag}{source}{close_tag}", **options)
    if not (out.startswith(open_tag) and out.endswith(close_tag)):
        return None
    return out[len(open_tag) : -len(close_tag)]


def minify_js_source(js: str) -> str | None:
    """Minify standalone JS. Returns None when it cannot be done safely.

    minify_html has no standalone JS entry point, so the source is wrapped in a
    <script> element and unwrapped afterwards. That is only sound when the
    source cannot terminate the element itself.
    """
    if SCRIPT_CLOSE_RE.search(js):
        return None
    return minify_wrapped(js, "script", minify_js=True) or None


def minify_js_tree(cfg: Config, stats: BakeStats) -> None:
    """Minify every .js file in the mirror, exactly once."""
    present = {p.relative_to(cfg.site_dir).as_posix() for p in cfg.site_dir.rglob("*.js")}
    stats.unmatched_exclusions = sorted(EXCLUDE_MINIFY - present)
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

"""Remove WordPress fingerprints from the generated site.

The site is not WordPress any more, so it should not read like it. This is
tidying, not concealment: nothing here tries to defeat fingerprinting, and
anything whose only benefit would be hiding from a scanner is left alone.

Three kinds of change, in this order, because the later ones would otherwise
chew on the earlier ones' output:

1. Path segments -- /wp-content/ and /wp-includes/ get renamed on disk and in
   every reference.
2. Dead machinery -- the emoji polyfill, the oEmbed script and the speculation
   rules block, all of which reference paths a static site does not have.
3. Class and id names -- wp-block-* and the rest of the wp-* namespace.

The class rename is deliberately NOT applied to prose. One of the posts talks
about wp-to-static by name, and a blanket rename would corrupt it. Only
<style> and <script> bodies and class/id attribute values are rewritten.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

# Path segments. Renaming these is the single biggest change: every image URL
# on the site currently starts /wp-content/uploads/.
PATH_RENAMES = {
    "wp-content": "content",
    "wp-includes": "inc",
}

# Class/id prefixes.
#
# NOT site-: the theme already uses site-content, site-header, site-footer and
# site-wrapper, and wp-content would have mapped straight onto site-content.
# Nothing broke, only because rename_paths turns /wp-content/ into /content/
# before the class rename ever sees it -- but that is ordering luck rather than
# safety, so the prefix is chosen to be free and check_collisions() enforces it.
CLASS_RENAMES = (
    ("wp-block-", "blk-"),
    ("wp-", "ui-"),
)

# WordPress ships an emoji polyfill for browsers that no longer exist, an
# oEmbed script that needs an endpoint we do not serve, and a speculation-rules
# block whose JSON lists /wp-*.php and /wp-admin/* -- paths that cannot exist
# here. All three are dead weight and all three name WordPress loudly.
DEAD_SCRIPTS = (
    re.compile(r"<script[^>]*>[^<]*wpEmojiSettings.*?</script>", re.S | re.I),
    re.compile(r'<script[^>]*type=["\']?speculationrules["\']?[^>]*>.*?</script>', re.S | re.I),
    re.compile(r'<script[^>]*src=[^>]*wp-emoji-release[^>]*>\s*</script>', re.I),
    re.compile(r'<script[^>]*src=[^>]*/wp-embed(\.min)?\.js[^>]*>\s*</script>', re.I),
    # The emoji settings blob, which carries s.w.org CDN URLs into every page.
    # Nothing consumes it once the loader above is gone, and no img.emoji is
    # generated anywhere in the content.
    re.compile(r'<script[^>]*id=["\']?wp-emoji-settings["\']?[^>]*>.*?</script>', re.S | re.I),
    re.compile(r'<style[^>]*id=["\']?wp-emoji-styles[^"\'>]*["\']?[^>]*>.*?</style>', re.S | re.I),
)

# Fingerprints that are not wp-* tokens and so slip past the identifier guard.
# The bare word "WordPress" is deliberately absent: a post on this site talks
# about it, and an image is called wordpress.png.
FOREIGN_FINGERPRINTS = ("s.w.org", "api.w.org", "wp-emoji", "wpemoji")

# Chained pseudo-elements are not valid CSS. lightningcss refuses the whole
# stylesheet over this one selector and minify-html then passes 282KB through
# untouched, on every page. Fixing it is worth ~122KB per page and, as a side
# effect, lets the minifier strip the theme's WordPress-branded header comment.
INVALID_SELECTOR = ("::first-letter::after", "::first-letter")

STYLE_BLOCK = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.S | re.I)
SCRIPT_BLOCK = re.compile(r"(<script[^>]*>)(.*?)(</script>)", re.S | re.I)
CLASS_OR_ID_ATTR = re.compile(r"""\b(class|id)=(["']?)([^"'>\s][^"'>]*)(\2)""", re.I)

WP_TOKEN = re.compile(r"\bwp[-_][a-zA-Z0-9_-]+")

# Content that legitimately mentions WordPress and must survive untouched.
CONTENT_ALLOWLIST = ("wp-to-static",)


@dataclass
class ScrubStats:
    paths_renamed: int = 0
    dirs_renamed: list[str] = field(default_factory=list)
    scripts_removed: int = 0
    orphans_removed: int = 0
    classes_renamed: int = 0
    leftovers: dict[str, int] = field(default_factory=dict)
    collisions: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"paths:{self.paths_renamed} dirs:{len(self.dirs_renamed)} "
            f"dead scripts:{self.scripts_removed} orphans:{self.orphans_removed} "
            f"classes:{self.classes_renamed}"
        )


def fix_invalid_css(text: str) -> str:
    return text.replace(*INVALID_SELECTOR)


def rename_paths(text: str) -> tuple[str, int]:
    """Rewrite /wp-content/ and /wp-includes/ in every form they appear.

    Plain, JSON-escaped (\\/wp-content\\/) and percent-encoded forms all occur;
    the leading separator is required so a prose mention could never match.
    """
    count = 0
    for old, new in PATH_RENAMES.items():
        for pattern, replacement in (
            (rf"/{re.escape(old)}/", f"/{new}/"),
            (rf"\\/{re.escape(old)}\\/", f"\\\\/{new}\\\\/"),
            (rf"%2F{re.escape(old)}%2F", f"%2F{new}%2F"),
        ):
            text, n = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
            count += n
    return text, count


def remove_dead_scripts(text: str) -> tuple[str, int]:
    count = 0
    for pattern in DEAD_SCRIPTS:
        text, n = pattern.subn("", text)
        count += n
    return text, count


def _rename_tokens(blob: str) -> tuple[str, int]:
    count = 0
    for old, new in CLASS_RENAMES:
        blob, n = re.subn(rf"\b{re.escape(old)}", new, blob)
        count += n
    return blob, count


def rename_classes(text: str) -> tuple[str, int]:
    """Rename wp-* identifiers, but only where they can be identifiers.

    Scoped to <style> and <script> bodies and to class/id attribute values, so
    prose is never touched -- a post on this site mentions wp-to-static, and a
    blanket rename would rewrite it.
    """
    total = 0

    def in_block(match: re.Match[str]) -> str:
        nonlocal total
        body, n = _rename_tokens(match.group(2))
        total += n
        return f"{match.group(1)}{body}{match.group(3)}"

    def in_attr(match: re.Match[str]) -> str:
        nonlocal total
        value, n = _rename_tokens(match.group(3))
        total += n
        return f"{match.group(1)}={match.group(2)}{value}{match.group(2)}"

    text = STYLE_BLOCK.sub(in_block, text)
    text = SCRIPT_BLOCK.sub(in_block, text)
    text = CLASS_OR_ID_ATTR.sub(in_attr, text)
    return text, total


def scrub_html(text: str) -> tuple[str, ScrubStats]:
    stats = ScrubStats()
    text, stats.paths_renamed = rename_paths(text)
    text, stats.scripts_removed = remove_dead_scripts(text)
    text, stats.classes_renamed = rename_classes(text)
    return text, stats


def scrub_css(text: str, *, minify: bool = True) -> str:
    """Scrub a standalone stylesheet, and strip its comments.

    The inlined copy of this CSS gets minified as part of the page, but the
    file itself is also uploaded and served. Without minifying it here, the
    theme's WordPress-branded header comment survives in the served file even
    though it is gone from every page.
    """
    text = fix_invalid_css(text)
    text, _ = rename_paths(text)
    text, _ = _rename_tokens(text)
    if not minify:
        return text
    import minify_html

    wrapped = minify_html.minify(f"<style>{text}</style>", minify_css=True)
    inner = wrapped[len("<style>") : -len("</style>")]
    # minify_html passes CSS through untouched when it cannot parse it, so only
    # accept output that actually got smaller.
    return inner if 0 < len(inner) < len(text) else text


def scrub_xml(text: str) -> str:
    text, _ = rename_paths(text)
    return text


def scrub_xsl(text: str) -> str:
    """De-brand the sitemap stylesheets WordPress ships."""
    text, _ = rename_paths(text)
    return re.sub(r"WordPress", "", text, flags=re.IGNORECASE)


def mapped_name(token: str) -> str:
    for old, new in CLASS_RENAMES:
        if token.startswith(old):
            return new + token[len(old) :]
    return token


def check_collisions(cfg: Config) -> dict[str, str]:
    """Names a rename would merge into an identifier that already exists.

    Renaming wp-foo to X-foo is only safe while nothing is already called
    X-foo. If something is, the two collapse into one class and inherit each
    other's styling -- silently, and only on whichever pages use both. Run this
    before renaming anything.
    """
    existing: set[str] = set()
    wp_tokens: set[str] = set()
    prefixes = tuple(new for _, new in CLASS_RENAMES)

    for path in cfg.site_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in (".html", ".htm", ".css"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        existing.update(re.findall(rf"\b((?:{'|'.join(prefixes)})[a-zA-Z0-9_-]+)", text))
        wp_tokens.update(WP_TOKEN.findall(text))

    return {
        token: mapped_name(token)
        for token in wp_tokens
        if token not in CONTENT_ALLOWLIST and mapped_name(token) in existing
    }


def remove_orphans(cfg: Config) -> int:
    """Delete files nothing references any more.

    The emoji polyfill is the case that matters: its script tags are removed,
    so the file is unreachable, but it would still be uploaded and would still
    be the only thing on the site saying wp-emoji.
    """
    removed = 0
    for pattern in ("**/wp-emoji-release*.js", "**/wp-embed*.js"):
        for path in cfg.site_dir.glob(pattern):
            path.unlink()
            removed += 1
    return removed


def rename_directories(cfg: Config, stats: ScrubStats) -> None:
    """Rename the wp-* directories on disk to match the rewritten references."""
    for old, new in PATH_RENAMES.items():
        source = cfg.site_dir / old
        if not source.is_dir():
            continue
        target = cfg.site_dir / new
        if target.exists():
            # Merge rather than clobber; the target may already hold overlay
            # files or an earlier rename.
            for item in source.iterdir():
                destination = target / item.name
                if destination.exists():
                    shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
                shutil.move(str(item), str(destination))
            source.rmdir()
        else:
            source.rename(target)
        stats.dirs_renamed.append(f"{old} -> {new}")


def find_leftovers(cfg: Config) -> dict[str, int]:
    """Any wp-* token still present, excluding genuine content.

    This is the check that makes the class rename safe to do at all: a rename
    that missed occurrences would leave markup referencing classes the CSS no
    longer defines, and the page would quietly lose its styling.
    """
    found: dict[str, int] = {}
    for path in cfg.site_dir.rglob("*"):
        # .txt included because robots.txt shipped a Disallow: /wp-admin/ for a
        # path a static site cannot have -- a fingerprint in one of the first
        # files anyone fetches, and one an html-only scan walked straight past.
        if not path.is_file() or path.suffix.lower() not in (
            ".html", ".htm", ".css", ".js", ".xml", ".xsl", ".txt",
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in WP_TOKEN.findall(text):
            if token in CONTENT_ALLOWLIST:
                continue
            found[token] = found.get(token, 0) + 1
        for mark in FOREIGN_FINGERPRINTS:
            n = text.count(mark)
            if n:
                found[mark] = found.get(mark, 0) + n
    return found


def scrub_tree(cfg: Config) -> ScrubStats:
    """Scrub every generated file, then rename the directories to match."""
    stats = ScrubStats()
    stats.collisions = check_collisions(cfg)

    for path in sorted(cfg.site_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8", errors="replace")

        if suffix in (".html", ".htm"):
            new, file_stats = scrub_html(text)
            stats.paths_renamed += file_stats.paths_renamed
            stats.scripts_removed += file_stats.scripts_removed
            stats.classes_renamed += file_stats.classes_renamed
        elif suffix == ".css":
            new = scrub_css(text)
        elif suffix == ".js":
            new, _ = rename_paths(text)
        elif suffix == ".xml":
            new = scrub_xml(text)
        elif suffix == ".xsl":
            new = scrub_xsl(text)
        else:
            continue

        if new != text:
            path.write_text(new, encoding="utf-8")

    stats.orphans_removed = remove_orphans(cfg)
    rename_directories(cfg, stats)
    # The leftover check deliberately runs later, from the verify stage:
    # overlay files land after this stage and bake rewrites every page, so
    # checking here would inspect a tree that is not what gets published.
    return stats

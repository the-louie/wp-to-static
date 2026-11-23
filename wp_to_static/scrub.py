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

from dataclasses import dataclass, field
from collections.abc import Iterator
from pathlib import Path

from .bake import minify_wrapped
from .config import Config
from .mirror import move_into

# Path segments. Renaming these is the single biggest change: every image URL
# on the site currently starts /wp-content/uploads/.
PATH_RENAMES = {
    "wp-content": "content",
    "wp-includes": "inc",
}

# Class and id prefixes.
#
# A target prefix must be one nothing on the site already uses. If it is not,
# a renamed identifier merges into an existing one and the two inherit each
# other's styling, silently, and only on pages that use both. site- is unusable
# here for that reason: the theme defines site-content, site-header, site-footer
# and site-wrapper. check_collisions enforces this rather than trusting it.
CLASS_RENAMES = (
    ("wp-block-", "blk-"),
    ("wp-", "ui-"),
)

# Script and style blocks that are inert on a static site and name WordPress
# while being so. The emoji polyfill targets browsers that no longer exist, the
# oEmbed script needs an endpoint that is not served, and the speculation rules
# block lists /wp-*.php and /wp-admin/* paths that cannot exist here.
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
# Prefix matched, so wp-to-static-v2 and similar are covered too.
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


def mapped_name(token: str) -> str:
    """The name a wp-* identifier becomes, or the token unchanged."""
    for old, new in CLASS_RENAMES:
        if token.startswith(old):
            return new + token[len(old) :]
    return token


def _rename_tokens(blob: str) -> tuple[str, int]:
    """Apply the identifier map to every wp-* token in a fragment.

    Routed through mapped_name so the renamer and check_collisions cannot
    disagree about what a given token becomes.
    """
    return WP_TOKEN.subn(lambda m: mapped_name(m.group(0)), blob)


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
    inner = minify_wrapped(text, "style", minify_css=True)
    # minify_html returns the input untouched when it cannot parse it, so treat
    # output that did not shrink as a failed minify and keep the original.
    return inner if inner and len(inner) < len(text) else text


def scrub_xml(text: str) -> tuple[str, int]:
    """Scrub a generated feed or sitemap, returning the rename count.

    Feeds carry each post's body HTML inside CDATA, so the same wp-block-*
    class names the HTML pages are scrubbed of appear here too. Rename them the
    same way: otherwise the feed advertises a different class set than the page
    it mirrors, and the verify stage's fingerprint scan -- which reads .xml --
    fails the build on content that is really just the post. rename_classes is
    scoped to class/id attribute values and <style>/<script> bodies, so feed
    prose and the feed's own XML element names are left untouched.
    """
    text, _ = rename_paths(text)
    text, renamed = rename_classes(text)
    return text, renamed


def scrub_xsl(text: str) -> str:
    """De-brand the sitemap stylesheets WordPress ships."""
    text, _ = rename_paths(text)
    return re.sub(r"WordPress", "", text, flags=re.IGNORECASE)


# Every file type that can carry an identifier. .txt matters as much as the
# markup: robots.txt is among the first files anyone fetches, and a Disallow
# rule naming a WordPress path is as much a fingerprint as a class name.
TEXT_SUFFIXES = (".html", ".htm", ".css", ".js", ".xml", ".xsl", ".txt")


def read_text_files(cfg: Config, suffixes: tuple[str, ...]) -> "Iterator[tuple[Path, str]]":
    """Yield each text file in the tree with its contents.

    The suffix is tested before the file is opened. The output tree is mostly
    uploaded images, half a gigabyte of them, and decoding those to decide they
    are not markup costs the whole build.

    Decoding is strict. errors="replace" would substitute U+FFFD for any byte it
    could not read, and writing that back would silently destroy the file, so a
    file that is not valid UTF-8 is skipped instead.
    """
    for path in sorted(cfg.site_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def check_collisions(cfg: Config) -> dict[str, str]:
    """Names a rename would merge into an identifier that already exists.

    Renaming wp-foo to X-foo is only safe while nothing is already called
    X-foo. If something is, the two collapse into one class and inherit each
    other's styling -- silently, and only on whichever pages use both. Run this
    before renaming anything.
    """
    existing: set[str] = set()
    wp_tokens: set[str] = set()
    alternation = "|".join(re.escape(new) for _, new in CLASS_RENAMES)
    target = re.compile(rf"\b((?:{alternation})[a-zA-Z0-9_-]+)")

    for _, text in read_text_files(cfg, (".html", ".htm", ".css")):
        existing.update(target.findall(text))
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
            move_into(source, target)
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
    for _, text in read_text_files(cfg, TEXT_SUFFIXES):
        for token in WP_TOKEN.findall(text):
            if token.startswith(CONTENT_ALLOWLIST):
                continue
            found[token] = found.get(token, 0) + 1
        for mark in FOREIGN_FINGERPRINTS:
            # Only those a wp-* token would not already have reported, so a
            # single occurrence is not counted twice.
            if WP_TOKEN.fullmatch(mark):
                continue
            n = text.count(mark)
            if n:
                found[mark] = found.get(mark, 0) + n
    return found


def scrub_tree(cfg: Config) -> ScrubStats:
    """Scrub every generated file, then rename the directories to match."""
    stats = ScrubStats()
    stats.collisions = check_collisions(cfg)
    if stats.collisions:
        # Returning before any file is touched. Renaming anyway would leave the
        # tree in exactly the state the guard exists to prevent, and the caller
        # cannot tell a half applied rename from a clean one.
        return stats

    for path, text in read_text_files(cfg, TEXT_SUFFIXES):
        suffix = path.suffix.lower()

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
            new, n = scrub_xml(text)
            stats.classes_renamed += n
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

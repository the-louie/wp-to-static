# TODO

Items identified during review that were not resolved at the time, with enough
context to pick them up cold.

## Verify the minify exclusion list against the live theme

**Source:** `__doc/code_reviews/20260803-1847_wordpress_scrub.md`, first finding.
**Files:** `wp_to_static/bake.py`, `EXCLUDE_MINIFY`.

`EXCLUDE_MINIFY` names JavaScript files that must not be minified because
minifying them breaks the theme. The list was inherited from the original
`bake-js.js` and had drifted: every entry referenced `wp-content/` or
`wp-includes/` paths, and the theme has since moved from `eisai-child` to
`louie-theme`, so no entry matched any file. The protection had been inert for
some time and builds reported `skipped:0` without comment.

The entries have been rewritten against post scrub paths, and `bake` now reports
exclusions that match no file, so further drift is visible. What remains is a
judgement that cannot be made from the repository alone.

**What needs deciding.** The site currently ships five JavaScript files:

    content/plugins/gallery-block-lightbox/dist/baguetteBox.min.js
    content/themes/louie-theme/js/louie.js
    content/themes/louie-theme/assets/js/uikit.min.js
    content/themes/louie-theme/assets/js/uikit-icons.min.js
    content/themes/louie-theme/assets/js/eisai.min.js

`uikit.min.js` and `uikit-icons.min.js` have been added to the exclusion list
because UIkit is the kind of already minified library the original list existed
to protect, and re-minifying such a bundle is the documented failure mode. This
is a precaution, not an observation: no breakage has been seen, because until
now nothing was being excluded at all and the site worked.

The remaining three are still minified. `baguetteBox.min.js` is also already
minified and may deserve the same treatment.

**How to settle it.** Build twice, once as configured and once with
`EXCLUDE_MINIFY` emptied, then load a page using each library and compare
behaviour in a browser. The lightbox and the menu are the features to exercise,
since those are what the excluded libraries drive. Whichever files misbehave
when minified belong in the list; the rest can come out, and the entries that
match nothing should be deleted rather than left to rot again.

**Why it is not resolved here.** It needs a browser and a human looking at the
rendered page. Static analysis cannot tell whether a minified bundle still
works, and the safe default, excluding a file that did not need excluding, costs
only a few kilobytes.

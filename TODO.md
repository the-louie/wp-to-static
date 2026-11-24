# TODO

Items identified during review that were not resolved at the time, with enough
context to pick them up cold.

_No open items._

## Resolved

- **Verify the minify exclusion list against the live theme** — RESOLVED
  2026-11-24. The old `EXCLUDE_MINIFY` had drifted: three of its five entries
  (`maxmegamenu.js`, `jquery.min.js`, `hoverIntent.min.js`) matched no shipped
  file. A headless-Chrome test loaded every JS file the site ships both
  re-minified and in its original form; UIkit and baguetteBox initialise and the
  UIkit offcanvas menu opens identically either way, with no JS error. The list
  is now the four already-minified bundles the site actually ships
  (`baguetteBox.min.js`, `uikit.min.js`, `uikit-icons.min.js`, `eisai.min.js`),
  excluded because re-minifying them saves under 1% for the risk of corrupting a
  third-party bundle. `louie.js` is hand-written and still minified (~40%).
  Tracked as B-006 in `docs/planning/`.

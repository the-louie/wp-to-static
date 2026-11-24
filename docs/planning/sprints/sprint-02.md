# Sprint 02 — SEO sitemap hygiene and honest --no-minify

**Status:** in progress (opened 2026-11-24)
**Current ticket:** — (all tickets closed)
**Last completed:** T-03 (`done` — honest --no-minify)
**Budget:** 6h estimated (below the 80–120h band on purpose: these three rows are
the entire schedulable backlog after the SEO-report intake; B-010 is decision-
blocked on a server change. The sprint ends on the demo, not on filling hours.)

## Goal
The generated sitemap advertises only real, indexable pages, and `--no-minify`
actually produces readable JS.

## Demo
`./mkstatic.sh --dry-run` (or the sitemaps + bake stages against a fixture)
produces a `sitemap.xml` index with no `post_tag` member, member sitemaps with
no `/lost/` and no `/category/about/`, and a `--no-minify` build leaves a `.js`
file unminified. `.venv/bin/python -m pytest` is green.

## Tickets
| ID | Title | Est h | Deps | From | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| T-01 | Filter dead/excluded URLs out of the fetched sitemaps | 3 | — | B-008 | done | Added `filter_sitemap_urls` + `config.sitemap_exclude` (`category/about`, `lost`); `fetch_sitemaps` now strips matching `<url>` entries (path match, subpaths too) from each member before the index is written. README sitemaps row updated. +3 tests. 164 pass. |
| T-02 | Drop the post_tag sitemap provider | 1 | — | B-009 | done | Removed `taxonomies-post_tag` from `mirror.SITEMAP_PROVIDERS` (with a comment on why); the tag sitemap is no longer fetched or indexed, tag pages still ship. +1 test asserts the tuple. 165 pass. |
| T-03 | Gate JS minification on cfg.minify (honest --no-minify) | 2 | — | B-007 | done | Gated `minify_js_tree` on `cfg.minify` in `bake_tree`; `--no-minify` now leaves JS readable too. README `--no-minify` row + test count (→166) updated. +1 test, 166 pass. |

## Scope changes
(none yet)

## Retro
(filled at close)

# Sprint 02 — SEO sitemap hygiene and honest --no-minify

**Status:** in progress (opened 2026-11-24)
**Current ticket:** T-01 (`todo` — Filter dead/excluded URLs out of the fetched sitemaps)
**Last completed:** —
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
| T-01 | Filter dead/excluded URLs out of the fetched sitemaps | 3 | — | B-008 | todo | `fetch_sitemaps` writes WP's member sitemaps verbatim; add a loc filter keyed on a build-side exclude list (lost path + `feed_exclude`) so `/lost/` and `/category/about/` (403) are stripped before the index is written. Acceptance: a fixture category sitemap loses `/category/about/`, no member lists `/lost/`, index still resolves. Files: mirror.py, config.py, tests. |
| T-02 | Drop the post_tag sitemap provider | 1 | — | B-009 | todo | Remove `taxonomies-post_tag` from `mirror.SITEMAP_PROVIDERS` so the 35 thin tag pages are neither fetched nor indexed; the pages still ship for visitors. noindex meta / make-real-pages is the theme session's call. Acceptance: dry run's index lists no post_tag member; a test asserts the provider tuple. Files: mirror.py, test. |
| T-03 | Gate JS minification on cfg.minify (honest --no-minify) | 2 | — | B-007 | todo | `bake_tree` calls `minify_js_tree` unconditionally, so `--no-minify` only skips HTML minify despite the README saying "HTML/JS". Gate the JS pass on `cfg.minify`. Acceptance: a `--no-minify` bake leaves a non-excluded `.js` file unminified; README matches. Files: bake.py, README.md, test. |

## Scope changes
(none yet)

## Retro
(filled at close)

# Sprint 02 — SEO sitemap hygiene and honest --no-minify

**Status:** done (closed 2026-11-24)
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
(none)

## Retro
**Status set to done 2026-11-24.** All three tickets closed, one commit each
(`9340f84`, `faec6f8`, `fef55c7`).

Shipped:
- T-01 (B-008): `filter_sitemap_urls` + `config.sitemap_exclude` strip
  `/category/about/` (403) and `/lost/` (404 target) from the fetched member
  sitemaps before the index is written. Match is on the loc path and subpaths.
- T-02 (B-009): dropped `taxonomies-post_tag` from `SITEMAP_PROVIDERS`; the 35
  thin tag archives are no longer advertised, the pages still ship.
- T-03 (B-007): `bake_tree` gates `minify_js_tree` on `cfg.minify`, so
  `--no-minify` leaves JS readable, matching the README.

Tests: 161 → 166 (+5). README updated in two tickets (sitemaps row, `--no-minify`
row, test count).

Estimate accuracy: 6h planned, 3 tickets closed in roughly that envelope. Sprint
ran far below the 80–120h band by design (the whole schedulable backlog after
the SEO intake), same as Sprint 01; not a recalibration signal.

Discovered, not ticketed: the test-count claim lives in both `README.md` (now
166) and project `CLAUDE.md` (still "160"); it drifts every sprint. Noted rather
than chased, since it recurs (see also Sprint 01 B-005). A one-line check or a
dynamic count would end it; left for a human to decide if it is worth automating.

What changed in the backlog: B-007/008/009 struck as closed. B-010 (robots.txt
`/lost` lines) remains, still `decision:`-blocked on the nginx 404 change landing
on static5. No schedulable row left.

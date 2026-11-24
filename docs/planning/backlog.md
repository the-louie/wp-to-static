# Backlog

Next ID: **B-011**

Everything not in the active sprint, priority order. IDs are issued once and
never reused. Closed rows are struck in place with proof.

## Intake 2026-11-24 — SEO report (louie-se-seo-report-2026-11-24.md)

Report split three ways on purpose. Only the build-step slice is ticketed here
(B-008..B-010): the sitemaps and robots.txt are produced by this generator. The
rest is left for other sessions, do not ticket it here:

- **nginx on static5** (server session, not this repo): real 404 instead of
  301→/lost/ (`error_page 404 /lost/index.html`), `absolute_redirect off` to keep
  redirects on https, HSTS. These are the report's "critical, blocks indexing"
  items but they live in `sites/louie.se.conf`, not the build. B-010 (robots.txt)
  must not land before the 404 change, or /lost/ becomes indexable.
- **WP theme session**: self-canonical + single H1 on tag/category/`/blog/`
  pages, `noindex` meta on thin tag pages and the lost page, JSON-LD BlogPosting,
  one-H1-per-page. All page-HTML, rendered by the theme, not the build.
- **content session**: alt text on 389 images, fix or remove the empty
  `/category/about/` category, decide which tags deserve real intro pages.

Not ticketed (root cause is upstream WP, not the build): the 2 orphan pages
missing from the sitemap and stale `lastmod` dates. The sitemaps are fetched
verbatim from WordPress, so those are WP export/content fixes, not build fixes.

## Last grooming 2026-11-23

Seeded from the README-vs-code review. All five review fixes verified open
against the tree before ticketing. Ordered: the publish blocker first (B-001,
it is the only thing stopping an upload), then the behavioural drift (B-002),
then the three documentation-alignment rows (B-003..B-005). B-006 carried over
from `TODO.md`, left as P3 because it needs a browser and a human.

## Open

- ~~**B-001 · Reconcile scrub vs verify on wp-block-* in feed CDATA**~~ — CLOSED 2026-11-23 (Sprint 01 T-01): scrub.py `scrub_xml` now renames classes; dry run clears verify and reaches the upload gate.
- ~~**B-002 · Fix theme asset path (eisai-child vs louie-theme)**~~ — DISPROVED 2026-11-23 (Sprint 01 T-02): not a bug. THEME_ASSET_PREFIX is the *source* path of the flattened `/assets/` fonts, which `louie-theme` still keeps under `eisai-child/assets/` (server returns 304 for them). The CSS references `/assets/VCR_OSD_MONO…`, which resolves; louie-theme's own JS uses full paths and resolves (bake `missing:0`). Changing the prefix would break the font flattening. README clarified to say so.
- ~~**B-003 · Document or remove --no-crosscheck**~~ — CLOSED 2026-11-23 (Sprint 01 T-03): documented in README flag table; it is needed for offline --build-data builds, so kept not removed.
- ~~**B-004 · Document or drop --repo / --output**~~ — CLOSED 2026-11-23 (Sprint 01 T-04): both documented in README; they override WPTS_REPO / WPTS_OUTPUT, kept as convenience flags.
- ~~**B-005 · Refresh README test count**~~ — CLOSED 2026-11-23 (Sprint 01 T-05): README now says 161 tests (was 115), matching the suite.

- ~~**B-006 · Settle the EXCLUDE_MINIFY list against the live theme**~~ — CLOSED 2026-11-24: headless-Chrome test (both minified-again and original) showed UIkit + baguetteBox init and the offcanvas menu work identically, no JS errors. EXCLUDE_MINIFY set to the 4 already-minified shipped bundles; 3 dead entries removed; mechanism tests decoupled from production values. bake.py EXCLUDE_MINIFY.

- → Sprint 02 T-03 (B-007 · `--no-minify` does not disable JS minification)

- ~~**B-008 · Filter dead and excluded URLs out of the fetched sitemaps**~~ — CLOSED 2026-11-24 (Sprint 02 T-01): `mirror.filter_sitemap_urls` + `config.sitemap_exclude` strip `/category/about/` (403) and `/lost/` from the member sitemaps before the index is written.

- → Sprint 02 T-02 (B-009 · Drop the post_tag sitemap from the build)

- [ ] **B-010 · Remove the `/lost` disallows from robots.txt** · 0.5h · prio P2 · decision: blocked on the nginx 404 change · src: SEO report §3.1
      `_overlay/robots.txt` has three `Disallow: /lost…` lines. The report wants
      them gone so Google can read that /lost/ is an error page, BUT only *after*
      nginx stops 301-ing dead URLs to /lost/ and the lost page carries a `noindex`
      meta. Landing this first would make the error page indexable. One-line overlay
      edit, held until the server session confirms the `error_page 404` change is
      live on static5 and the theme/content session has added noindex to the lost
      page. Files: `_overlay/robots.txt`.

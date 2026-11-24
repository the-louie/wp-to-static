# Backlog

Next ID: **B-007**

Everything not in the active sprint, priority order. IDs are issued once and
never reused. Closed rows are struck in place with proof.

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

- [ ] **B-007 · `--no-minify` does not disable JS minification** · 2h · prio P2 · src: B-006 investigation
      `bake_tree` calls `minify_js_tree` unconditionally, so `--no-minify` only
      skips HTML minification. README says it skips "HTML/JS minification" and
      the flag is meant for diffing against the old pipeline, which needs the JS
      readable. Fix: gate `minify_js_tree` on `cfg.minify` (or document the
      actual behaviour). Found while building a no-minify baseline for B-006.

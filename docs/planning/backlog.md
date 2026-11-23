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
- → Sprint 01 T-05

- [ ] **B-006 · Settle the EXCLUDE_MINIFY list against the live theme** · 2h · prio P3 · src: TODO.md
      Decide which of the 5 shipped JS files must stay unminified. Needs a
      browser to exercise the lightbox and menu. Carried from TODO.md; a
      `decision:`-shaped row in practice (cannot be settled from the repo).

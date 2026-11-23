# Sprint 01 — Make the moved build publishable and align README with code

**Status:** done (closed 2026-11-23)
**Current ticket:** — (all tickets closed)
**Last completed:** T-05 (`done` — README test count refreshed)
**Budget:** 8h estimated (below the 80–120h band on purpose: these five rows are
the entire known backlog after the review; the sprint ends on the demo, not on
filling hours)

## Goal
A dry run reaches the upload gate cleanly, and every functional claim in the
README matches the code.

## Demo
`./mkstatic.sh --dry-run` runs to the rsync preview with no verify error, and
`grep` of the README for the fixed claims (theme path, flags, test count)
matches the code. `.venv/bin/python -m pytest` is green.

## Tickets
| ID | Title | Est h | Deps | From | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| T-01 | Reconcile scrub vs verify on wp-block-* in feed CDATA | 3 | — | B-001 | done | scrub_xml now renames classes in feed CDATA (consistent with HTML pages); dry run clears verify, reaches `==> uploading`; README updated; +1 regression test. |
| T-02 | Point THEME_ASSET_PREFIX at the active louie-theme | 2 | — | B-002 | dropped | Disproved on investigation: the prefix is the source path of the flattened `/assets/` fonts, which louie-theme still keeps under eisai-child/assets/ (304s confirm). CSS resolves `/assets/…`; louie-theme JS uses full paths (bake missing:0). Changing it would break font flattening. README clarified; no code change. See Scope changes. |
| T-03 | Document or remove --no-crosscheck | 1 | — | B-003 | done | Kept and documented: it is needed for offline --build-data builds (WordPress not reachable to cross-check against). Added to README flag table. |
| T-04 | Document or drop --repo / --output | 1 | — | B-004 | done | Documented both in README as per-run overrides of WPTS_REPO / WPTS_OUTPUT; kept (functional, no test depends on them). |
| T-05 | Refresh README test count | 1 | — | B-005 | done | README 115 -> 161, matching `pytest` (160 before this sprint + 1 new regression test in T-01). |

## Scope changes
- 2026-11-23: T-02 **dropped** (B-002 disproved). `THEME_ASSET_PREFIX` is
  correct; it is the source path of the `/assets/` fonts louie-theme still keeps
  under eisai-child. No code change; README clarified. Budget now 6h.

## Retro
**Status set to done 2026-11-23.**

Shipped:
- T-01 (B-001): `scrub_xml` now renames classes inside feed CDATA, so the feed
  matches the scrubbed page it mirrors. The build clears `verify` and reaches
  the upload gate for the first time since the move. +1 regression test. The
  only remaining dry-run error is rsync's ssh to the `static` alias, which is an
  environment credential, not a code defect, and lands past the verify gate.
- T-03 (B-003): `--no-crosscheck` documented (kept: offline `--build-data`
  builds need it).
- T-04 (B-004): `--repo` / `--output` documented as overrides of `WPTS_REPO` /
  `WPTS_OUTPUT`.
- T-05 (B-005): README test count 115 → 161.

Dropped:
- T-02 (B-002): disproved. `THEME_ASSET_PREFIX` is correct, it is the source
  path of the `/assets/` fonts louie-theme still keeps under eisai-child. One
  one-line README clarification landed under this dropped ticket (logged in its
  commit), because it is what answers the confusion that created the row.

Estimate accuracy: 6h planned after the T-02 drop, 4 tickets closed plus one
disproved in roughly that envelope. Sprint ran far below the 80–120h band by
design: these five rows were the entire known backlog after the review, so the
band does not apply. Not a recalibration signal.

What changed in the backlog: B-001/003/004/005 closed, B-002 struck as
disproved. B-006 (EXCLUDE_MINIFY) remains, P3, and is decision-shaped: it needs
a browser and a human, so it is not schedulable by the loop.

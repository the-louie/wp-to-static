# Sprint 01 — Make the moved build publishable and align README with code

**Status:** in progress (opened 2026-11-23)
**Current ticket:** T-01 (`todo` — Reconcile scrub vs verify on feed fingerprints)
**Last completed:** —
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
| T-01 | Reconcile scrub vs verify on wp-block-* in feed CDATA | 3 | — | B-001 | todo | Acceptance: dry run reaches upload gate (no fingerprint error); README scrub/verify scope and code agree; tests green. Files: scrub.py, verify.py (find_leftovers), __main__.py, README.md, tests. |
| T-02 | Point THEME_ASSET_PREFIX at the active louie-theme | 2 | — | B-002 | todo | Acceptance: prefix matches live theme; mirror.py font paths checked; README sentence updated; bake reports css/js missing:0; tests green. |
| T-03 | Document or remove --no-crosscheck | 1 | — | B-003 | todo | Acceptance: README flag table and __main__.py agree. Lean preference: remove unless it earns a row. Tests green. |
| T-04 | Document or drop --repo / --output | 1 | — | B-004 | todo | Acceptance: README and __main__.py agree on both flags. Tests green. |
| T-05 | Refresh README test count | 1 | — | B-005 | todo | Acceptance: README number equals `pytest` collected count. |

## Scope changes
(none yet)

## Retro
(filled at close)

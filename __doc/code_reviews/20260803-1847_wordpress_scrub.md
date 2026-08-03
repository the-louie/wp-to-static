# Code review, WordPress fingerprint scrubbing

Date: 2026 08 03, 18:47
Scope: commits `443af40` and `31fa2ca`, unpushed on `main`
Reviewer: Senior Staff Engineer, DevSecOps

## Summary

The change adds a `scrub` pipeline stage that removes WordPress identifiers from
the generated site. It renames `/wp-content/` to `/content/` and `/wp-includes/`
to `/inc/` on disk and across roughly 5,200 references, renames about 31,800
class and id tokens from the `wp-*` namespace, deletes dead WordPress machinery
including the emoji polyfill and a speculation rules block, and corrects an
invalid CSS selector that had been defeating stylesheet minification.

Supporting changes cover an nginx snippet that keeps the old URLs resolving, a
collision guard for the class rename, a leftover scan that runs in the verify
stage, and 34 new tests.

The design is sound and the two guards, `check_collisions` and `find_leftovers`,
both demonstrably caught real defects during development. The findings below
concern a lost safety mechanism in a downstream component, resource use, and
several consistency and robustness issues.

## Critical findings

| Issue | Severity | Description | Suggested fix |
| :--- | :--- | :--- | :--- |
| `EXCLUDE_MINIFY` no longer matches anything | High | `bake.EXCLUDE_MINIFY` lists four JavaScript files that must not be minified because minifying them breaks the theme. All four are keyed on `wp-content/` and `wp-includes/` paths. The scrub renames those directories before `bake` runs, so the set can never match. The list was already stale, the theme moved from `eisai-child` to `louie-theme`, so the protection has been inert for some time and the scrub makes it permanently so. Builds report `skipped:0` while minifying five JavaScript files including `uikit.min.js`, which is exactly the class of library the list was written to protect. | Key the exclusions on post scrub paths, and make the stage report when an exclusion entry matches no file so a stale list is visible rather than silent. |
| `scrub_tree` reads every file in the tree as text | Medium | The loop calls `read_text` before inspecting the suffix, so all 517 MB of the output tree is decoded on every build to process the 24 MB that is actually text. The 493 MB difference is mostly JPEG and PNG data, decoded with `errors="replace"`. | Move the suffix test above the read. |
| Corrupting decode on write back | Medium | Files are read with `errors="replace"`, which substitutes U+FFFD for undecodable bytes. Any file that both fails to decode and matches a rule is written back with the replacement characters baked in, silently losing data. | Read strictly, and skip with a warning when a file is not valid UTF-8. |
| `scrub_css` slices the minifier output without checking it | Medium | The function wraps CSS in a `<style>` element, minifies, then slices by fixed offsets. `bake.minify_js_source` performs the same wrap and unwrap but verifies the wrapper survived before slicing. If `minify_html` ever alters or drops the tag, `scrub_css` silently returns malformed CSS. | Apply the same guard used in `bake`, and factor the shared wrap, minify, unwrap sequence into one helper. |
| Collision guard detects but does not prevent | Medium | `scrub_tree` calls `check_collisions` and stores the result, then proceeds to rename regardless. The build later fails and refuses to publish, so nothing reaches production, but the working tree is left in the damaged state the guard exists to avoid. | Raise before any file is modified when collisions are present. |
| Two implementations of one mapping | Low | `_rename_tokens` applies the prefix map by regular expression, `mapped_name` applies it by `startswith`. They encode the same rule twice and can drift apart, which would make `check_collisions` reason about a mapping the renamer does not perform. | Express one in terms of the other. |
| Fingerprint totals are inflated | Low | `find_leftovers` counts `wp-emoji` twice, once through `WP_TOKEN` and once through `FOREIGN_FINGERPRINTS`. Only the reported numbers are wrong, detection is unaffected. | Count foreign fingerprints only when they are not already `wp-*` tokens. |
| Directory merge logic duplicated | Low | `scrub.rename_directories` and `mirror._flatten_theme_assets` implement the same merge, including the same conditional expression evaluated for its side effects. | Extract one helper and call it from both. |
| Allowlist matching is exact | Low | `CONTENT_ALLOWLIST` compares whole tokens, so a legitimate mention such as `wp-to-static-v2` would be reported as a leftover and fail the build. | Match by prefix. |
| Unescaped prefixes in a pattern | Low | `check_collisions` interpolates the rename targets into an alternation without `re.escape`. The current values are safe, a future value containing a metacharacter would not be. | Escape the interpolated values. |
| Function level import | Low | `scrub_css` imports `minify_html` inside the function body. The module is already a hard dependency imported by `bake`, so there is no deferred cost to gain. | Move to module scope. |
| Comments describing history rather than behaviour | Low | Several comments narrate what changed instead of explaining the code. Examples are `mirror.py:40`, "The emoji polyfill used to be fetched here", and `scrub.py:290`, "one an html-only scan walked straight past". | Rewrite to state the rule and its rationale. |

## Notes on items deliberately not changed

The `CLASS_OR_ID_ATTR` pattern accepts unquoted attribute values and its second
character class permits spaces, so it can capture beyond a single attribute.
The capture cannot cross `>`, so it stays inside one tag and prose is never
reached, and at the point `scrub` runs the markup is not yet minified so
attributes are still quoted. The behaviour is acceptable, the constraint is
worth recording because it depends on stage ordering.

`scrub_xsl` deletes the word WordPress rather than replacing it, which can leave
awkward spacing in the sitemap stylesheet. The file is presentational and rarely
seen, so the cosmetic result does not justify more complex handling.

## Verification performed

The findings were confirmed against a full build of the live site rather than by
inspection alone. `EXCLUDE_MINIFY` was tested for each entry under both the
original and renamed paths, the read amplification was measured across the
output tree, and the double counting was reproduced directly.

## Remediation

All findings were addressed in this pass except one, which is recorded in
`TODO.md` because it requires a judgement that cannot be made from the
repository alone.

| Issue | Resolution |
| :--- | :--- |
| `EXCLUDE_MINIFY` no longer matches | Entries rewritten against post scrub paths, and `bake` now reports entries that match no file. Builds previously reported `skipped:0`, they now report `skipped:2`, so the mechanism is working for the first time. Which files genuinely need excluding is left to `TODO.md`. |
| Reading every file as text | The suffix is tested before the file is opened, through a single `read_text_files` walker shared by all three consumers. |
| Corrupting decode on write back | Decoding is strict, and a file that is not valid UTF-8 is skipped rather than rewritten with replacement characters. |
| `scrub_css` slicing blind | Both call sites now use `bake.minify_wrapped`, which verifies the wrapper survived before slicing. |
| Guard detects but does not prevent | `scrub_tree` returns before touching any file when collisions are present. |
| Two implementations of one mapping | `_rename_tokens` is expressed in terms of `mapped_name`, so the renamer and the collision check cannot disagree. |
| Inflated fingerprint totals | Foreign fingerprints that a `wp-*` token would already report are no longer counted a second time. |
| Duplicated directory merge | Extracted as `mirror.move_into`, called from both sites. |
| Exact allowlist matching | Matched by prefix. |
| Unescaped prefixes | Escaped, and the pattern is compiled once rather than per file. |
| Function level import | Moved to module scope. |
| Comments describing history | Rewritten to state the rule and its rationale. |

Six tests were added covering the behaviours above, including that a collision
leaves the tree untouched, that binary files are never decoded, and that an
undecodable text file is skipped rather than mangled.

### Verification after remediation

A full build against the live instance produced identical scrub figures, 5,189
path rewrites and 31,849 identifier renames, with zero broken references, 144
valid feeds and no surviving fingerprints other than the project name in the
author's own prose. The suite stands at 160 tests.

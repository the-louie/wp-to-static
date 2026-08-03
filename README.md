# wp-to-static

Dumps a WordPress site to static HTML. Purpose-built for louie.se.

Still works for me(tm), now with tests.

## Usage

```sh
uv venv .venv && uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python -m wp_to_static              # build into ./output
.venv/bin/python -m wp_to_static --upload     # build and publish
```

Requires a local WordPress at `localhost:8000`, plus `wget`, `curl` and `rsync`.
`wget` still does the crawling; everything after it is Python.

Useful flags:

| Flag | Why |
|---|---|
| `--only STAGE...` / `--skip STAGE...` | stages are `crawl sitemaps cleanup feeds rewrite overlay bake upload` |
| `--no-minify` | leaves HTML readable, for diffing against the old bash pipeline |
| `--build-data FILE` | use a captured JSON payload instead of talking to WordPress |
| `--crosscheck-all` | verify every term's feed against WordPress, not a sample of 5 |
| `--feed-max-items N` | cap feed length (default: no cap) |

Configuration is environment-driven: `WPTS_LOCAL_URL`, `WPTS_DOMAIN`,
`WPTS_OUTPUT`, `WPTS_UPLOAD`, `WPTS_SSH_KEY`, `WPTS_API_SECRET`.

## Feeds

The site and every tag and category get RSS and Atom:

```
/feed.xml                    /atom.xml
/tag/<slug>/feed.xml         /tag/<slug>/atom.xml
/category/<slug>/feed.xml    /category/<slug>/atom.xml
```

WordPress's original `/feed/` and `/feed/atom/` URLs keep working at every level
via `index.xml` aliases, so existing subscribers do not break.

Feed XML is generated rather than scraped, because WordPress caps every feed at
`posts_per_rss` (10 by default) and that cap applies to taxonomy feeds too.
Generating means no cap and no per-term HTTP round trips. The price is owning
correctness, so each build fetches WordPress's own feed for a sample of terms
and asserts its items are an order-preserving prefix of ours. A guid WordPress
has that we do not fails the build.

`guid` values are copied verbatim. They are opaque identifiers, not URLs —
rewriting one makes every subscriber re-download the whole feed.

## The mu-plugin

`wp-plugin/louie-static-build.php` goes in `wp-content/mu-plugins/` on the
**local build instance only**, with a secret in `wp-config.php`:

```php
define( 'LOUIE_STATIC_BUILD_SECRET', '...' );
```

Without the constant the endpoint is not registered at all.

Its job is to hand over data the generator would otherwise have to infer from
URLs. Every URL it returns comes from WordPress's own link functions
(`get_permalink`, `get_term_link`, `get_term_feed_link`), so a changed category
or tag base, a non-ASCII slug, or a non-default feed type all just work.

Builds fall back to the stock REST API without it, but then feed URLs are
reconstructed by string concatenation — it warns, and it is not the supported
path.

## Server configuration

See `_server/`. Those files are deliberately outside `_overlay/` so they are
never published. Deploying them is a manual server-side step, documented in
`_server/README.md`.

## Tests

```sh
.venv/bin/python -m pytest
```

Everything runs offline against fixtures. `tests/test_rewrite.py` additionally
runs the original `textreplace_*.sh` scripts and asserts the Python rewrites
produce byte-identical output; that is why those scripts are still in the tree.

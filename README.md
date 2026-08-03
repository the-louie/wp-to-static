# wp-to-static

Turns a WordPress site into static HTML. Purpose-built for
[louie.se](https://louie.se/).

Still works for me(tm) — now in Python, with tests.

## Read this before you clone it

This is not a general-purpose WordPress exporter, and it will not work on your
site without changes. It is a personal tool published in case the approach is
useful, not a product.

Specifically, it hardcodes:

- **louie.se** as the public domain, and a particular internal host as the
  WordPress instance it crawls
- a **theme-specific asset path** (`wp-content/themes/eisai-child/assets/` gets
  flattened to `/assets/`), and a list of JS files that must not be minified
  because minifying them breaks the theme
- **`localhost:8000`** as a legacy host, because this site's database still
  carries URLs from an earlier home
- a **bio page** at `/who-am-i/`, where bylines are pointed since author
  archives are not exported
- one **excluded category**, and an nginx document root at
  `/mnt/storage/louie.se/www2`

Most of that lives in `wp_to_static/config.py` and is one edit away from being
yours instead. The theme-specific parts are not.

More to the point, the interesting work here is in the corner cases — stale
hosts baked into a database, a theme that hides a tag from its own posts, feeds
that must keep their identifiers stable across a migration. Those are *this*
site's corner cases. Yours will be different ones.

## What it does

```
WordPress ──wget──▶ mirror ──▶ cleanup ──▶ feeds ──▶ rewrite ──▶ assets
                                                                    │
                             published ◀── verify ◀── bake ◀── overlay
```

`wget` still does the crawling: its link-following and page-requisite discovery
is a lot of well-tested behaviour to reimplement badly. Everything after it is
Python. There is no Node — `minify-html` covers HTML, CSS and JS in one
dependency.

| Stage | What it does |
|---|---|
| `crawl` | recursive `wget` mirror, plus targeted fetches for things nothing links to |
| `pages` | fetches public URLs the crawl never reached, from the plugin's URL list |
| `sitemaps` | every page of every sitemap provider; regenerates the index |
| `cleanup` | drops `?p=` duplicates and `.php` files, strips `?ver=` from filenames |
| `feeds` | generates site and per-term RSS/Atom, then checks them against WordPress |
| `rewrite` | URL rewriting, feed autodiscovery, scrubs the WordPress version |
| `assets` | re-fetches referenced files the crawl could not reach |
| `overlay` | copies `_overlay/`, substituting `__DOMAIN__` and `__EXPIRES__` |
| `bake` | inlines CSS, minifies JS once per file, minifies HTML |
| `verify` | refuses to publish a build that lost pages |
| `upload` | rsync, opt-in |

## Usage

```sh
uv venv .venv && uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python -m wp_to_static            # build into ./output
```

Needs `wget`, `curl` and `rsync` on the path, and a reachable WordPress.

| Flag | Why |
|---|---|
| `--only STAGE…` / `--skip STAGE…` | run part of the pipeline |
| `--upload` / `--dry-run` | publish; preview the file list first |
| `--allow-shrink` | accept a small drop in page count |
| `--crosscheck-all` | verify every term's feed, not a sample of five |
| `--feed-max-items N` | cap feed length (default: no cap) |
| `--build-data FILE` | use a captured JSON payload instead of WordPress |
| `--no-minify` | leave HTML readable, for diffing against the old pipeline |

Configuration comes from the environment, and `.env` in the repo root is read
automatically: `WPTS_LOCAL_URL` (accepts a full origin), `WPTS_DOMAIN`,
`WPTS_OUTPUT`, `WPTS_UPLOAD`, `WPTS_API_SECRET`, `WPTS_INSECURE`.

The ssh identity for uploading comes from the uploading user's `~/.ssh/config`,
not from here.

## Feeds

The site and **every tag and category** get RSS and Atom:

```
/feed.xml                    /atom.xml
/tag/<slug>/feed.xml         /tag/<slug>/atom.xml
/category/<slug>/feed.xml    /category/<slug>/atom.xml
```

WordPress's original `/feed/` and `/feed/atom/` URLs keep working at every
level via `index.xml` aliases, so nobody's subscription breaks.

The XML is **generated, not scraped**. WordPress caps every feed at
`posts_per_rss` — ten by default — and that cap applies to taxonomy feeds too,
so scraping would have meant either truncated feeds or mutating a live setting
mid-build. Generating means no cap and no per-term round trips.

The price is that we now own correctness, so every build fetches WordPress's
own feed for a sample of terms and asserts its items are an order-preserving
prefix of ours. A guid WordPress has that we do not fails the build. That check
has already earned its place: it caught a tag shipping zero items because the
theme hides it from its own posts' term lists.

`guid` values are copied verbatim. They are opaque identifiers, not URLs —
rewriting one makes every subscriber re-download the entire archive.

Nothing in a feed is derived from build time, so an unchanged site regenerates
byte-identical feeds and conditional GET keeps working.

## The mu-plugin

`wp-plugin/louie-static-build.php` goes in `wp-content/mu-plugins/` on the
build instance only, with a secret in `wp-config.php`:

```php
define( 'LOUIE_STATIC_BUILD_SECRET', '...' );
```

Without that constant the endpoint is not registered at all.

Its real job is that **every URL it returns comes from WordPress's own link
functions** — `get_permalink`, `get_term_link`, `get_term_feed_link`. The
generator therefore never builds a WordPress URL by string concatenation, and a
changed category base, a percent-encoded slug or a non-default feed type all
just work without it knowing they exist.

It also resolves term membership as **term → posts** rather than reading each
post's own term list, which themes routinely filter.

Builds fall back to the stock REST API without it and say so loudly, but that
path reconstructs URLs by hand and is not the supported one. The payload
carries a schema version, so a stale copy of the plugin is reported rather than
silently degrading the build.

## Things specific to this site

**Stale hosts in the database.** WordPress writes absolute URLs into post
content, and a post's `guid` at creation time, and never revisits them. This
site still carries `http://localhost:8000` from an earlier home. Two
consequences: guids would ship pointing at a host that is not the site, and
images referenced that way are off-host to the crawler and never downloaded.
`Config.legacy_hosts` normalises the first; the `assets` stage re-fetches the
second — ninety files, at the time of writing. Both are workarounds for
something a `wp search-replace` on the database would fix properly.

**Hand-placed content.** `.well-known/` holds ACME challenges and is not owned
by the uploading user. `/dumpster/` is served by nginx from a different root
entirely, so it is outside the upload tree. The upload deliberately omits
`--delete`, which would destroy the ACME challenges; clear stale files by path
instead.

Because nothing is ever deleted, some URLs still resolve on the live site
purely because an old build left the files there. "It loads in a browser" is
not proof the generator still produces it.

## Server configuration

See `_server/`. Those files live outside `_overlay/` so they can never be
rsynced into the document root — the previous incarnation was Cloudflare Pages
syntax sitting on an nginx host, which did nothing except publish the intended
CSP at `/_headers` for anyone to read.

They are snippets to include in an existing `server { }` block, not a
replacement for one. Deploying them is a manual step, documented in
`_server/README.md`, including the one trap: nginx drops every inherited
`add_header` in any `location` that sets one of its own.

## Tests

```sh
.venv/bin/python -m pytest        # 115 tests, all offline
```

Everything runs against fixtures; no WordPress required. `tests/test_rewrite.py`
additionally runs the original `textreplace_*.sh` scripts and asserts the
Python rewrites produce byte-identical output — which is why those shell
scripts are still in the tree, and why they should stay until the equivalence
stops being interesting.

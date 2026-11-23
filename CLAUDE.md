# CLAUDE.md — wp-to-static

Static-site generator for **louie.se**. Crawls a locally-hosted WordPress with
`wget`, then transforms the mirror in Python and rsyncs it to the public nginx
host. Personal tool, not a general exporter. `README.md` is the authoritative
reference — read it for the stage-by-stage detail; this file is the working
context an agent needs on top of it.

## State of the project

The bash + Node pipeline (`mkstatic.sh`, `textreplace_*.sh`, `bake-js.js`) is
**gone**; the port to Python is done and lives on `main`. There are no other
branches. `./mkstatic.sh` is now a thin wrapper that builds the venv and calls
`python -m wp_to_static`. So "convert to a well-formed Python project" is
already achieved — further work is refinement, not conversion.

## Build host

The WordPress instance is at **`https://louie-se.i.louie.se/`** (hyphen). Its
TLS certificate validates cleanly, so `verify_tls` stays on and `WPTS_INSECURE`
is not needed. Earlier homes — `localhost:8000` and `louie_se.i.louie.se`
(underscore, cert would not validate) — are in `DEFAULT_LEGACY_HOSTS` because
post guids and content URLs baked at creation time still point at them.

## Running it

```sh
./mkstatic.sh                 # build + upload (first run builds .venv via uv)
./mkstatic.sh --skip upload   # build only, into ./output
./mkstatic.sh --dry-run       # build, preview the rsync file list
.venv/bin/python -m pytest    # 160 tests, all offline against fixtures
```

Needs `wget`, `curl`, `rsync`, and `uv` on PATH. `--upload` is opt-in; the bare
command from the wrapper adds it. The `verify` stage refuses to upload a build
that lost pages or leaked a WordPress fingerprint, so publishing by habit is
safe.

## Where things live

- `wp_to_static/` — the package. One stage per concern: `mirror` (crawl/fetch),
  `feeds`, `rewrite`, `scrub`, `overlay`, `bake`, `verify`, `publish`, `wpapi`
  (mu-plugin client). `__main__.py` is the ordered pipeline; `config.py` is the
  single frozen `Config` every stage shares.
- `config.py` — **all site-specific values** (hosts, domain, upload target,
  excluded category, byline target). Change config here, not in stages.
- `wp-plugin/louie-static-build.php` — mu-plugin on the build WP only; makes WP
  emit its own canonical URLs/term membership. Build warns loudly and degrades
  to stock REST without it. Needs `LOUIE_STATIC_BUILD_SECRET` in `wp-config.php`
  and the same secret in repo `.env` as `WPTS_API_SECRET` (gitignored).
- `_overlay/` — files copied verbatim into the site (robots.txt, `.well-known`).
- `_server/` — nginx include snippets, **deployed manually**, never rsynced.
  `louie-legacy-paths.conf` must be live *before* the first scrubbed upload, or
  already-published `/wp-content/` URLs 404.
- `TODO.md` — carried-over review items. `__doc/code_reviews/` — past reviews.

## Conventions / gotchas

- Config comes from env + repo `.env` (`WPTS_LOCAL_URL`, `WPTS_DOMAIN`,
  `WPTS_OUTPUT`, `WPTS_UPLOAD`, `WPTS_API_SECRET`, `WPTS_INSECURE`). The ssh
  identity for upload lives in the uploading user's `~/.ssh/config`, never here.
- Upload omits `--delete` on purpose (would wipe ACME challenges under
  `.well-known/`). Nothing is deleted remotely, so "it loads in a browser" does
  not prove the generator still produces it — clear stale files by path.
- Feeds are generated, not scraped, and cross-checked against WordPress's own
  feeds each build. `guid` values are copied verbatim — never rewrite them.
- Do not put secrets (the API secret, ssh keys) in the repo or in any note.

# Server configuration

These files are **not** part of the generated site. They live outside
`_overlay/` on purpose, so they can never be rsynced into the document root.

That is the whole reason this directory exists. `_overlay/_headers` used to hold
this configuration in Cloudflare Pages syntax, on a host running nginx. It did
nothing, and because it sat in `_overlay/` it was published at
`https://louie.se/_headers` for anyone to read.

## Deploying

Two things must happen together, in one change:

1. Install the config:
   ```
   cp louie-security-headers.conf /etc/nginx/snippets/
   cp louie.se.nginx.conf         /etc/nginx/sites-available/louie.se
   nginx -t && systemctl reload nginx
   ```
2. Remove the stale published copy of the old file. The upload rsync has no
   `--delete`, so removing it from the repo does not unpublish it:
   ```
   rm /mnt/storage/louie.se/www2/_headers
   ```

Ship the corrected feed `Content-Type`s and `nosniff` at the same time. Feeds
are currently served as `text/xml` and readers sniff their way to the right
answer; enabling `nosniff` without the correct types would break every
browser-based reader, and the types without `nosniff` change nothing.

## Verifying

```
curl -sI https://louie.se/tag/<slug>/feed.xml
```

must show **all three** together:

- `content-type: application/rss+xml; charset=utf-8`
- `x-content-type-options: nosniff`
- `content-security-policy: ...`

All three appearing is what proves the `add_header` inheritance trap was
avoided: a `location` block that sets any header drops every `add_header`
inherited from `server`, which is why the security headers are `include`d in
both places rather than written once at the top.

Repeat for `atom.xml`, `/feed/`, `/feed/atom/`, and the site-level `/feed.xml`.
Then check `curl -sI https://louie.se/_headers` returns 404.

Finally, subscribe to one tag feed in a real reader. Readers are stricter than
any of the above.

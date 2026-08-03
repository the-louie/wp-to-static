# Server configuration

These files are **not** part of the generated site. They live outside
`_overlay/` on purpose, so they can never be rsynced into the document root.

That is why this directory exists. `_overlay/_headers` used to hold this
configuration in Cloudflare Pages syntax, on a host running nginx. It did
nothing, and because it sat in `_overlay/` it was published at
`https://louie.se/_headers` for anyone to read.

## What these are

| File | Purpose |
|---|---|
| `louie-feeds.conf` | feed Content-Types, `index.xml` directory index, feed-only CORS |
| `louie-security-headers.conf` | the security headers, included from both places below |

**Both are snippets to include inside your existing `server { }` block.**
Neither is a server block. They set no `listen`, `ssl_*` or `server_name`, so
they cannot clobber TLS, user-agent filtering, `.well-known` handling, or
anything else already configured.

## Installing

```sh
sudo cp louie-feeds.conf louie-security-headers.conf /etc/nginx/snippets/
```

Then, inside the existing `server { }` block for louie.se:

```nginx
server {
    # ...everything already there, untouched...

    include /etc/nginx/snippets/louie-security-headers.conf;
    include /etc/nginx/snippets/louie-feeds.conf;
}
```

Back up first, then check and reload:

```sh
sudo cp /etc/nginx/sites-available/louie.se ~/louie.se.nginx.bak
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` validates the whole config before anything is applied, so a mistake
fails there rather than taking the site down.

Also remove the stale file the old overlay published. The upload has no
`--delete`, so deleting it from the repo did not unpublish it:

```sh
rm /mnt/storage/louie.se/www2/_headers
```

## The one trap

nginx's `add_header` inheritance is all-or-nothing per level: a `location` that
sets **any** header discards **every** `add_header` inherited from `server`.
The feed locations set CORS, so without care they would silently lose `nosniff`
and the CSP — on exactly the responses whose Content-Type we just started
caring about.

That is why the security headers are a separate snippet, included at server
level *and* inside each feed location. Do not "simplify" it by including it
once at the top.

## Why it must go out as one change

Feeds are currently served as `text/xml` with no `nosniff`, and readers sniff
their way to the right answer. Turning on `nosniff` without the corrected
Content-Types would break every browser-based reader; the Content-Types without
`nosniff` change nothing. Ship both together.

## Verifying

```sh
curl -sI https://louie.se/tag/lora/feed.xml
```

must show **all three** together:

- `content-type: application/rss+xml; charset=utf-8`
- `x-content-type-options: nosniff`
- `content-security-policy: ...`

All three appearing is what proves the `add_header` trap was avoided.

Then confirm the legacy WordPress URLs, which currently return **403** because
nginx will not serve `index.xml` as a directory index:

```sh
for u in /feed/ /feed/atom/ /tag/lora/feed/ /tag/lora/feed/atom/; do
  curl -s -o /dev/null -w "$u -> %{http_code} %{content_type}\n" "https://louie.se$u"
done
```

All four should become 200. And `curl -sI https://louie.se/_headers` should 404.

Finally, subscribe to one tag feed in a real reader. Readers are stricter than
any of the above.

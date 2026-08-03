#! /bin/bash
echo "$1"
# Trailing slash is optional: a feed's channel <link> is the bare origin with
# no path, and sitemaps never hit that case so it went unnoticed.
sed --in-place "s/https*:\/\/$LOCALURL\/\{0,1\}/https:\/\/"$DOMAIN"\//g" "$1"
sed --in-place "s/\/wp-sitemap.xsl/\/sitemap.xsl/g" "$1"
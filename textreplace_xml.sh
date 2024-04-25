#! /bin/bash
echo "$1"
sed --in-place "s/https*:\/\/$LOCALURL\//https:\/\/"$DOMAIN"\//g" "$1"
sed --in-place "s/\/wp-sitemap.xsl/\/sitemap.xsl/g" "$1"
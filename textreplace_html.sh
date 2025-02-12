#! /bin/bash
echo "$1"

echo "Fix special absolute links"
sed --in-place "s/^\(.*meta property=\"og:.*\)https*:\/\/$LOCALURL\/\(.*\)$/\1https:\/\/$DOMAIN\/\2/g" "$1"
sed --in-place "s/^\(.*meta name=\"twitter:.*\)https*:\/\/$LOCALURL\/\(.*\)$/\1https:\/\/$DOMAIN\/\2/g" "$1"
sed --in-place "s/^\(.*link rel=\"canonical\" href=\"\)https*:\/\/$LOCALURL\/\(.*\)$/\1https:\/\/$DOMAIN\/\2/g" "$1"

echo "fix all general absolute links"
sed --in-place "s/https*:\/\/$LOCALURL\/\{0,1\}/\//g" "$1"

echo "fix all double escaped links"
sed --in-place "s/https*:\\\\\/\\\\\/$LOCALURL\\\\\//\//g" "$1"

echo "fix ?ver="
sed --in-place "s/\?ver=[0-9\.]\{1,\}//g" "$1"

echo " * Remove all shortlinks in html ..."
sed --in-place "s/<link rel=['\"]shortlink['\"].*\/>//g" "$1";

echo "remove index.html from links"
sed --in-place "s/\/index.html\?/\//g" "$1"

echo "update assets url"
sed --in-place "s/\/wp-content\/themes\/eisai-child\/assets\//\/assets\//g" "$1"

echo "remove feeds references"
sed --in-place "s/<link rel=\"alternate\" type=\"application\/rss+xml\" .*\/>//" "$1"

echo "Remove wordpress from headers"
sed --in-place "s/WordPress\s\w\{1,\}\.\w\{1,\}\.\{0,\}\w\{0,\}/OpenBSD 7.5 - ed/g" "$1"
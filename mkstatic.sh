#! /bin/bash

#
#
# Louie.se static site generator
#
#
#

export BASEDIR='./output'
export LOCALURL='localhost:8000'
export DOMAIN='louie.se'
export STARTDIR=$(pwd)
# Site tree, relative to $BASEDIR. wget names the mirror after the host it
# crawled, so this has to match $LOCALURL.
export OUTPUTDIR="$LOCALURL"


# cleanup and init
##########################

which parallel > /dev/null 2>&1 || { echo >&2 "I require parallel but it's not installed. Aborting."; exit 1; }
which wget > /dev/null 2>&1 || { echo >&2 "I require wget but it's not installed. Aborting."; exit 1; }
which node > /dev/null 2>&1 || { echo >&2 "I require node but it's not installed. Aborting."; exit 1; }
which rsync > /dev/null 2>&1 || { echo >&2 "I require rsync but it's not installed. Aborting."; exit 1; }

# cleanup and init
##########################
test -d "$BASEDIR" && { rm -rf "$BASEDIR" || exit; }
mkdir -p "$BASEDIR/$OUTPUTDIR" || exit
cd "$BASEDIR" || exit

# is it up
curl -so /dev/null http://${LOCALURL}/ || { echo "http://${LOCALURL}/ not up. Exiting..."; exit; }

# download site
##########################
wget  --no-cache --no-cookies -X wp-json -X author -X comments -X wp-admin --reject-regex="/feed/" -mEpnp "http://$LOCALURL/"

wget  --no-cache --no-cookies -O "./${OUTPUTDIR}/index.html"  "http://$LOCALURL/"
wget  --no-cache --no-cookies -X wp-json -mEpnp "http://$LOCALURL/lost/"
mkdir -p ${OUTPUTDIR}/wp-includes/js
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/wp-includes/js/wp-emoji-release.min.js "http://$LOCALURL/wp-includes/js/wp-emoji-release.min.js?ver=6.1"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/wp-content/themes/Eisai/assets/js/html5.min.js "http://$LOCALURL/wp-content/themes/Eisai/assets/js/html5.min.js"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/assets/VCR_OSD_MONO_1.001.ttf "http://$LOCALURL/wp-content/themes/eisai-child/assets/VCR_OSD_MONO_1.001.ttf"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/assets/MPLUSRounded1c-Medium.ttf "http://$LOCALURL/wp-content/themes/eisai-child/assets/MPLUSRounded1c-Medium.ttf"
mkdir -p ${OUTPUTDIR}/assets && mv ${OUTPUTDIR}/wp-content/themes/eisai-child/assets/* ${OUTPUTDIR}/assets/

# sitemap
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/sitemap-index.xsl  "http://$LOCALURL/wp-sitemap-index.xsl"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/sitemap.xsl  "http://$LOCALURL/wp-sitemap.xsl"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/sitemap-posts-post-1.xml  "http://$LOCALURL/wp-sitemap-posts-post-1.xml"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/sitemap-posts-page-1.xml  "http://$LOCALURL/wp-sitemap-posts-page-1.xml"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/sitemap-taxonomies-category-1.xml  "http://$LOCALURL/wp-sitemap-taxonomies-category-1.xml"
wget  --no-cache --no-cookies -O ${OUTPUTDIR}/sitemap-taxonomies-post_tag-1.xml  "http://$LOCALURL/wp-sitemap-taxonomies-post_tag-1.xml"
# add sitemap
echo -e '<?xml version="1.0" encoding="UTF-8"?>\n<?xml-stylesheet type="text/xsl" href="https://'$DOMAIN'/sitemap-index.xsl" ?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://'$DOMAIN'/sitemap-posts-post-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-posts-page-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-taxonomies-category-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-taxonomies-post_tag-1.xml</loc></sitemap></sitemapindex>\n' > ${OUTPUTDIR}/sitemap.xml

# feed
# The recursive crawl above rejects /feed/ so it doesn't drag in a feed for
# every category and tag; the two we actually publish are fetched by hand.
# WP's <guid isPermaLink="false">...?p=NN</guid> is an opaque identifier, not a
# URL, and is left alone on purpose -- rewriting it makes every subscriber
# re-download the whole feed.
wget  --no-cache --no-cookies -O "$OUTPUTDIR/feed.xml"  "http://$LOCALURL/feed/" || exit
wget  --no-cache --no-cookies -O "$OUTPUTDIR/atom.xml"  "http://$LOCALURL/feed/atom/" || exit
# Keep the pre-static /feed/ URL working for anyone already subscribed.
mkdir -p "$OUTPUTDIR/feed" && cp "$OUTPUTDIR/feed.xml" "$OUTPUTDIR/feed/index.xml"

# download images from header meta-tags
for f in $(find ./${OUTPUTDIR}/ -iname "*.html" -exec sed -n "s/^.*meta.*:image.*content=\"\(.*\)\">/\1/p" {} \; | sort | uniq | sed -n 's/http:\/\///p'); do
    if [ ! -f "$f" ]; then
        DIR=$(dirname "$f")
        test -d "$DIR" || mkdir -p "$DIR";
        wget --no-cache --no-cookies -O "$f" "http://$f";
    fi;
done

# cleanup site
##########################
echo "Cleanup ?p=..."
# Was 'parallel -0 -exec rm {}'. parallel silently ignores the undocumented
# -exec and runs plain 'rm', so that worked -- but deleting is syscall-bound,
# so there is nothing to parallelise and no reason to lean on that quirk.
find ./${OUTPUTDIR}/ -type f -name "index.html*p=*.html" -delete

echo "Remove ?ver= files"
IFS=$'\n'; for f in $(find . -iname "*\?ver?*"); do g=$(echo "$f" | sed 's/\?ver=.*//'); mv "$f" "$g"; done

echo "remove xmlrpc"
rm ./${OUTPUTDIR}/xmlrpc.php\?rsd

echo " * Remove all php files ..."
find "./${OUTPUTDIR}/" -iname "*.php*" -exec rm {} \;

echo "fix html"
find ./${OUTPUTDIR}/ -type f -name '*.html' -print0 | parallel --eta --bar --progress -0 /bin/bash ../textreplace_html.sh {}

echo "fix css"
find ./${OUTPUTDIR}/ -type f -name '*.css' -print0 | parallel --eta --bar --progress -0 /bin/bash ../textreplace_css.sh {}

echo "fix XML"
find ./${OUTPUTDIR}/ -type f -name '*.xml' -print0 | parallel --eta --bar --progress -0 /bin/bash ../textreplace_xml.sh {}

# textreplace_xml.sh has already rewritten the host by now, so the feeds point
# at https://$DOMAIN/feed/ -- but we serve them from /feed.xml and /atom.xml,
# and rel="self" has to match where the file actually lives. Restricting the
# substitution to the rel="self" line keeps the per-item <link>s untouched.
echo "fix feed self-links"
sed --in-place "/rel=[\"']self[\"']/ s|https://$DOMAIN/feed/|https://$DOMAIN/feed.xml|" "./$OUTPUTDIR/feed.xml" || exit
sed --in-place "/rel=[\"']self[\"']/ s|https://$DOMAIN/feed/atom/|https://$DOMAIN/atom.xml|" "./$OUTPUTDIR/atom.xml" || exit

echo " * Copy in overlay files ..."
rsync -av "${STARTDIR}/_overlay/" "./$OUTPUTDIR/" || exit

# _overlay/robots.txt is the single source of truth for robots rules. Only the
# sitemap URL is templated, so $DOMAIN stays defined in exactly one place.
echo "Update robots.txt"
test -f "./$OUTPUTDIR/robots.txt" || { echo >&2 "robots.txt missing from overlay. Aborting."; exit 1; }
sed --in-place "s|__DOMAIN__|$DOMAIN|g" "./$OUTPUTDIR/robots.txt" || exit

# bake in all local javascript and minify html
find ./${OUTPUTDIR}/ -type f -name '*.html' -print0 | parallel --eta --bar --progress -0 node ../bake-js.js {}

# upload site
##########################
rsync -e "ssh -i ~/.ssh/keys/static-nokey" -av ./${OUTPUTDIR}/ static:/mnt/storage/louie.se/www2/

date

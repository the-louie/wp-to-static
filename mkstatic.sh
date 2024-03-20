#! /bin/bash

BASEDIR='./output'
LOCALURL='localhost:8000'
DOMAIN='louie.se'

# cleanup and init
##########################

which parallel > /dev/null 2>&1 || { echo >&2 "I require parallel but it's not installed. Aborting."; exit 1; }
which wget > /dev/null 2>&1 || { echo >&2 "I require wget but it's not installed. Aborting."; exit 1; }
which node > /dev/null 2>&1 || { echo >&2 "I require wget but it's not installed. Aborting."; exit 1; }

rm -rf "$BASEDIR" || exit
mkdir "$BASEDIR" || exit
cd "$BASEDIR" || exit

# FIXME:
# feed is broken, needs lots of love to get working. It doesn't
# use permalinks for the urls but rather ?p=NN links. Could mmaybe
# be replaced with /page/NN?


# download site
##########################

wget  --no-cache --no-cookies -X wp-json -X author -X comments --reject-regex="/feed/" --convert-links -mEpnp "http://$LOCALURL/"

wget  --no-cache --no-cookies -O "./$LOCALURL/index.html"  "http://$LOCALURL/"
wget  --no-cache --no-cookies -X wp-json --convert-links -mEpnp "http://$LOCALURL/lost/"
mkdir -p localhost\:8000/wp-includes/js
wget  --no-cache --no-cookies -O localhost\:8000/wp-includes/js/wp-emoji-release.min.js "http://$LOCALURL/wp-includes/js/wp-emoji-release.min.js?ver=6.1"
wget  --no-cache --no-cookies -O localhost\:8000/wp-content/themes/Eisai/assets/js/html5.min.js "http://$LOCALURL/wp-content/themes/Eisai/assets/js/html5.min.js"
wget  --no-cache --no-cookies -O localhost\:8000/assets/MPLUSRounded1c-Medium.ttf "http://$LOCALURL/wp-content/themes/eisai-child/assets/MPLUSRounded1c-Medium.ttf"
mkdir -p localhost\:8000/assets && mv $LOCALURL/wp-content/themes/eisai-child/assets/* localhost\:8000/assets/
# sitemap
wget  --no-cache --no-cookies -O localhost\:8000/sitemap-index.xsl  "http://$LOCALURL/wp-sitemap-index.xsl"
wget  --no-cache --no-cookies -O localhost\:8000/sitemap.xsl  "http://$LOCALURL/wp-sitemap.xsl"
wget  --no-cache --no-cookies -O localhost\:8000/sitemap-posts-post-1.xml  "http://$LOCALURL/wp-sitemap-posts-post-1.xml"
wget  --no-cache --no-cookies -O localhost\:8000/sitemap-posts-page-1.xml  "http://$LOCALURL/wp-sitemap-posts-page-1.xml"
wget  --no-cache --no-cookies -O localhost\:8000/sitemap-taxonomies-category-1.xml  "http://$LOCALURL/wp-sitemap-taxonomies-category-1.xml"
wget  --no-cache --no-cookies -O localhost\:8000/sitemap-taxonomies-post_tag-1.xml  "http://$LOCALURL/wp-sitemap-taxonomies-post_tag-1.xml"
echo -e '<?xml version="1.0" encoding="UTF-8"?>\n<?xml-stylesheet type="text/xsl" href="https://'$DOMAIN'/sitemap-index.xsl" ?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://'$DOMAIN'/sitemap-posts-post-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-posts-page-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-taxonomies-category-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-taxonomies-post_tag-1.xml</loc></sitemap></sitemapindex>\n' > localhost\:8000/sitemap.xml

# download images from header meta-tags
for f in $(find ./localhost\:8000/ -iname "*.html" -exec sed -n "s/^.*meta.*:image.*content=\"\(.*\)\">/\1/p" {} \; | sort | uniq | sed -n 's/http:\/\///p'); do
    if [ ! -f "$f" ]; then
        DIR=$(dirname "$f")
        test -d "$DIR" || mkdir -p "$DIR";
        wget --no-cache --no-cookies -O "$f" "http://$f";
    fi;
done

# cleanup site
##########################
# remove all index.html?p=XXX.html
find ./ -name "index.html*p=*.html" -exec rm {} \;

# fix all absolute links that needs to be absolute (open graph stuff etc)
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/^\(.*meta property=\"og:.*\)https*:\/\/$LOCALURL\/\(.*\)$/\1https:\/\/$DOMAIN\/\2/g" {} \;
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/^\(.*meta name=\"twitter:.*\)https*:\/\/$LOCALURL\/\(.*\)$/\1https:\/\/$DOMAIN\/\2/g" {} \;

# fix all absolute links to relative links
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/https*:\/\/$LOCALURL\//\//g" {} \;

# fix double escaped absolute links also
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/https*:\\\\\/\\\\\/$LOCALURL\\\\\//\//g" {} \;

# remove wordpress in headers
find ./ -iname "*.html" -exec sed --in-place "s/WordPress\s\w\{1,\}\.\w\{1,\}\.\{0,\}\w\{0,\}/OpenBSD 7.2 - ed/g" {} \;

# fix ?ver=
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/\?ver=[0-9\.]\{1,\}//g" {} \;
IFS=$'\n'; for f in $(find . -iname "*\?ver?*"); do g=$(echo "$f" | sed 's/\?ver=.*//'); mv "$f" "$g"; done

# remove index.html from links
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/\/index.html\?/\//g" {} \;

# fix links in xml
find ./localhost\:8000/ -name '*.xml' -exec sed --in-place "s/https*:\/\/$LOCALURL\//https:\/\/"$DOMAIN"\//g" {} \;
find ./localhost\:8000/ -name '*.xml' -exec sed --in-place "s/\/wp-sitemap.xsl/\/sitemap.xsl/g" {} \;


# remove xmlrpc file
rm ./localhost\:8000/xmlrpc.php\?rsd

# fix robots.txt and remove wordpress stuff
echo -ne "User-agent: *\nDisallow: /lost/\n\nSitemap: /sitemap.xml\n" > localhost\:8000/robots.txt

# bake in all local javascript and minify html
# single thread ./mkstatic.sh  389.51s user 18.20s system 116% cpu 5:48.60 total
# find ./localhost\:8000/ -name '*.html' -exec node ../bake-js.js {} \;

# parallell ./mkstatic.sh  830.76s user 45.18s system 790% cpu 1:50.87 total
find ./localhost\:8000/ -type f -name '*.html' -print0 | parallel --eta --bar --progress -0 node ../bake-js.js {}


# upload site
##########################
rsync -e "ssh -i ~/.ssh/keys/static-nokey" -av ./localhost\:8000/ static:/mnt/storage/louie.se/www2/

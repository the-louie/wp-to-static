#! /bin/bash

BASEDIR='./output'
DOMAIN='louie.se'

# cleanup and init
##########################

rm -rf "$BASEDIR" || exit
mkdir "$BASEDIR" || exit
cd "$BASEDIR" || exit

# FIXME:
# feed is broken, needs lots of love to get working. It doesn't
# use permalinks for the urls but rather ?p=NN links. Could mmaybe
# be replaced with /page/NN?


# download site
##########################

wget -X wp-json -X author -X comments --reject-regex="/feed/" --convert-links -mEpnp "http://localhost:8000/"
wget -X wp-json --convert-links -mEpnp "http://localhost:8000/lost/"
mkdir -p localhost\:8000/wp-includes/js
wget -O localhost\:8000/wp-includes/js/wp-emoji-release.min.js "http://localhost:8000/wp-includes/js/wp-emoji-release.min.js?ver=6.1"
wget -O localhost\:8000/wp-content/themes/Eisai/assets/js/html5.min.js "http://localhost:8000/wp-content/themes/Eisai/assets/js/html5.min.js"
# sitemap
wget -O localhost\:8000/sitemap-index.xsl  "http://localhost:8000/wp-sitemap-index.xsl"
wget -O localhost\:8000/sitemap.xsl  "http://localhost:8000/wp-sitemap.xsl"
wget -O localhost\:8000/sitemap-posts-post-1.xml  "http://localhost:8000/wp-sitemap-posts-post-1.xml"
wget -O localhost\:8000/sitemap-posts-page-1.xml  "http://localhost:8000/wp-sitemap-posts-page-1.xml"
wget -O localhost\:8000/sitemap-taxonomies-category-1.xml  "http://localhost:8000/wp-sitemap-taxonomies-category-1.xml"
wget -O localhost\:8000/sitemap-taxonomies-post_tag-1.xml  "http://localhost:8000/wp-sitemap-taxonomies-post_tag-1.xml"
echo -e '<?xml version="1.0" encoding="UTF-8"?>\n<?xml-stylesheet type="text/xsl" href="https://'$DOMAIN'/sitemap-index.xsl" ?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://'$DOMAIN'/sitemap-posts-post-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-posts-page-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-taxonomies-category-1.xml</loc></sitemap><sitemap><loc>https://'$DOMAIN'/sitemap-taxonomies-post_tag-1.xml</loc></sitemap></sitemapindex>\n' > localhost\:8000/sitemap.xml



# cleanup site
##########################

# fix all absolute links to relative links
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/https*:\/\/localhost:8000\//\//g" {} \;

# fix double escaped absolute links also
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/https*:\\\\\/\\\\\/localhost:8000\\\\\//\//g" {} \;

# remove index.html from links
find ./localhost\:8000/ -name '*.html' -exec sed --in-place "s/\/index.html\?/\//g" {} \;

# fix links in xml
find ./localhost\:8000/ -name '*.xml' -exec sed --in-place "s/https*:\/\/localhost:8000\//https:\/\/"$DOMAIN"\//g" {} \;
find ./localhost\:8000/ -name '*.xml' -exec sed --in-place "s/\/wp-sitemap.xsl/\/sitemap.xsl/g" {} \;


# remove xmlrpc file
rm ./localhost\:8000/xmlrpc.php\?rsd

# fix robots.txt and remove wordpress stuff
echo -ne "User-agent: *\nDisallow: /lost/\n\nSitemap: /sitemap.xml\n" > localhost\:8000/robots.txt

# bake in all local javascript and minify html
find ./localhost\:8000/ -name '*.html' -exec node ../bake-js.js {} \;



# upload site
##########################
rsync -av ./localhost\:8000/ static:/mnt/storage/louie.se/www2/

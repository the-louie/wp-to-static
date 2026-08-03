<?php
/**
 * Plugin Name: Louie static build data
 * Description: Read-only endpoint that hands the static generator everything it
 *              would otherwise have to infer from URLs and scraped HTML.
 * Version:     1.0.0
 *
 * Install by copying this file to wp-content/mu-plugins/ on the LOCAL build
 * instance only. It is not needed, and should not be installed, on a public
 * site.
 *
 * Every URL in the response comes from WordPress's own link functions
 * (get_permalink, get_term_link, get_term_feed_link). That is the whole point
 * of the plugin: the generator never builds a WordPress URL by string
 * concatenation, so changing the category/tag base under Settings ->
 * Permalinks, a non-ASCII slug, or the default feed type all just work.
 *
 * Auth: set LOUIE_STATIC_BUILD_SECRET in wp-config.php and send it as
 * X-Static-Build-Secret. Without the constant the endpoint is not registered
 * at all, so a stray copy of this file cannot expose anything.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

const LOUIE_STATIC_NS = 'louie-static/v1';

add_action( 'rest_api_init', 'louie_static_register_routes' );

function louie_static_register_routes() {
	if ( ! defined( 'LOUIE_STATIC_BUILD_SECRET' ) || ! LOUIE_STATIC_BUILD_SECRET ) {
		return;
	}
	register_rest_route(
		LOUIE_STATIC_NS,
		'/build-data',
		array(
			'methods'             => 'GET',
			'callback'            => 'louie_static_build_data',
			'permission_callback' => 'louie_static_check_secret',
		)
	);
}

function louie_static_check_secret( $request ) {
	$sent = (string) $request->get_header( 'x-static-build-secret' );
	if ( '' === $sent || ! hash_equals( (string) LOUIE_STATIC_BUILD_SECRET, $sent ) ) {
		return new WP_Error( 'louie_static_forbidden', 'Bad or missing build secret', array( 'status' => 403 ) );
	}
	return true;
}

/**
 * Whether feeds should carry full content or just the excerpt.
 * rss_use_excerpt is '1' for excerpt, '0' for full text.
 */
function louie_static_use_excerpt() {
	return '1' === (string) get_option( 'rss_use_excerpt' );
}

function louie_static_site_data() {
	return array(
		'name'                => get_bloginfo( 'name' ),
		'description'         => get_bloginfo( 'description' ),
		'url'                 => home_url( '/' ),
		'language'            => get_bloginfo( 'language' ),
		'permalink_structure' => get_option( 'permalink_structure' ),
		'category_base'       => get_option( 'category_base' ) ?: 'category',
		'tag_base'            => get_option( 'tag_base' ) ?: 'tag',
		'default_feed'        => get_default_feed(),
		'posts_per_rss'       => (int) get_option( 'posts_per_rss' ),
		'use_excerpt'         => louie_static_use_excerpt(),
		'site_feed'           => array(
			'rss'  => get_feed_link( 'rss2' ),
			'atom' => get_feed_link( 'atom' ),
		),
		'last_modified_gmt'   => get_lastpostmodified( 'GMT' ),
	);
}

/**
 * Published post IDs carrying a term, newest first.
 *
 * Deliberately a term -> posts query rather than reading each post's term
 * list: see the note at the call site.
 */
function louie_static_term_post_ids( $term_id, $taxonomy ) {
	$ids = get_posts(
		array(
			'post_type'           => 'post',
			'post_status'         => 'publish',
			'posts_per_page'      => -1,
			'orderby'             => 'date',
			'order'               => 'DESC',
			'ignore_sticky_posts' => true,
			'fields'              => 'ids',
			'tax_query'           => array(
				array(
					'taxonomy'         => $taxonomy,
					'field'            => 'term_id',
					'terms'            => $term_id,
					'include_children' => false,
				),
			),
		)
	);
	return array_map( 'intval', $ids );
}

function louie_static_terms_data() {
	$out = array();
	foreach ( array( 'category', 'post_tag' ) as $taxonomy ) {
		$terms = get_terms(
			array(
				'taxonomy'   => $taxonomy,
				'hide_empty' => true,
			)
		);
		if ( is_wp_error( $terms ) ) {
			continue;
		}
		foreach ( $terms as $term ) {
			$link = get_term_link( $term );
			if ( is_wp_error( $link ) ) {
				continue;
			}
			$out[] = array(
				'taxonomy'    => $taxonomy,
				'id'          => (int) $term->term_id,
				'slug'        => $term->slug,
				'name'        => $term->name,
				'description' => $term->description,
				'count'       => (int) $term->count,
				// Authoritative URLs, straight from WordPress.
				'link'        => $link,
				'feed_link'   => get_term_feed_link( $term->term_id, $taxonomy, 'rss2' ),
				'atom_link'   => get_term_feed_link( $term->term_id, $taxonomy, 'atom' ),
				// Membership is resolved term -> posts, never post -> terms.
				// Themes and plugins routinely filter get_the_terms /
				// wp_get_object_terms to hide internal tags such as _featured
				// from listings, and that filter also strips them from a post's
				// own term list (and from the REST "tags" field). Querying by
				// term is the same path the feed templates take, so this agrees
				// with WordPress's own feeds by construction.
				'post_ids'    => louie_static_term_post_ids( $term->term_id, $taxonomy ),
			);
		}
	}
	return $out;
}

function louie_static_posts_data() {
	$query = new WP_Query(
		array(
			'post_type'              => 'post',
			'post_status'            => 'publish',
			'posts_per_page'         => -1,
			'orderby'                => 'date',
			'order'                  => 'DESC',
			'ignore_sticky_posts'    => true,
			'no_found_rows'          => true,
			'update_post_meta_cache' => false,
		)
	);

	$use_excerpt = louie_static_use_excerpt();
	$out         = array();

	foreach ( $query->posts as $post ) {
		setup_postdata( $post );

		// The stored guid, verbatim. It is an opaque identifier, not a URL --
		// rewriting it makes every subscriber re-download the entire feed.
		$guid = $post->guid;

		$content = '';
		if ( ! $use_excerpt ) {
			$content = apply_filters( 'the_content', $post->post_content );
		}

		$out[] = array(
			'id'           => (int) $post->ID,
			'title'        => get_the_title( $post ),
			'link'         => get_permalink( $post ),
			'guid'         => $guid,
			'date_gmt'     => get_post_time( 'c', true, $post ),
			'modified_gmt' => get_post_modified_time( 'c', true, $post ),
			'author'       => get_the_author_meta( 'display_name', $post->post_author ),
			'excerpt'      => wp_strip_all_tags( get_the_excerpt( $post ) ),
			'content'      => $content,
			'categories'   => wp_get_post_categories( $post->ID ),
			'tags'         => wp_get_post_tags( $post->ID, array( 'fields' => 'ids' ) ),
			'thumbnail'    => get_the_post_thumbnail_url( $post, 'full' ) ?: null,
		);
	}
	wp_reset_postdata();

	return $out;
}

/**
 * Every public URL, so the generator can tell whether the crawl missed
 * something nothing links to.
 */
function louie_static_urls() {
	$urls = array( home_url( '/' ) );

	$posts = get_posts(
		array(
			'post_type'      => array( 'post', 'page' ),
			'post_status'    => 'publish',
			'posts_per_page' => -1,
			'fields'         => 'ids',
		)
	);
	foreach ( $posts as $id ) {
		$permalink = get_permalink( $id );
		if ( $permalink ) {
			$urls[] = $permalink;
		}
	}

	foreach ( louie_static_terms_data() as $term ) {
		$urls[] = $term['link'];
	}

	return array_values( array_unique( $urls ) );
}

function louie_static_build_data() {
	return rest_ensure_response(
		array(
			'schema' => 1,
			'site'   => louie_static_site_data(),
			'terms'  => louie_static_terms_data(),
			'posts'  => louie_static_posts_data(),
			'urls'   => louie_static_urls(),
		)
	);
}

from atproto import Client, models
from typing import List, Dict, Optional
import os
import json


class BlueskyPostSearcher:
    def __init__(self, handle: str, password: str):
        self.client = Client()
        try:
            # Login to establish the session
            self.client.login(handle, password)
            print(f"Logged in as {handle}")
        except Exception as e:
            print(f"Login failed: {e}")
            self.client = None


    def search_recent_posts(
            self,
            keyword: str,
            hashtags: Optional[List[str]] = None,
            limit: int = 30
    ) -> List[Dict]:
        if not self.client:
            return []

        full_query = keyword
        if hashtags:
            formatted_tags = [f"#{t.lstrip('#')}" for t in hashtags]
            full_query += " " + " ".join(formatted_tags)

        print(f"Executing search for: [{full_query}]")

        try:
            response = self.client.app.bsky.feed.search_posts(params={
                'q': full_query,
                'limit': limit,
                'sort': 'latest'
            })

            results = []
            for post in response.posts:
                rkey = post.uri.split("/")[-1]
                post_url = f"https://bsky.app/profile/{post.author.handle}/post/{rkey}"

                image_urls = extract_media_urls(post)

                # fallback: grab URLs from text facets
                if not image_urls:
                    image_urls = extract_links_from_facets(post)

                results.append({
                    "author_handle": post.author.handle,
                    "post_url": post_url,
                    "text": post.record.text,
                    "created_at": post.record.created_at,
                    "image_urls": image_urls
                })

            print(f"Successfully processed {len(results)} posts.")
            return results

        except Exception as e:
            print(f"Search error: {e}")
            return []


def extract_media_urls(post_view) -> list:
    media_urls = []

    # 1. Ensure we have an embed
    embed = getattr(post_view, "embed", None)
    if not embed:
        return media_urls

    # 2. Handle 'Record With Media' (Quote posts with images)
    # We must check this FIRST because the media is nested inside
    if hasattr(embed, "media"):
        embed = embed.media

        # 3. Extract Thumbnails from Images
    if hasattr(embed, "images"):
        for img in embed.images:
            # .thumb is the CDN URL like: https://cdn.bsky.app/img/feed_thumbnail/...
            if hasattr(img, "thumb") and img.thumb:
                media_urls.append(img.thumb)
            elif hasattr(img, "fullsize") and img.fullsize:
                media_urls.append(img.fullsize)

    # 4. Extract Thumbnails from External link previews (if they exist)
    elif hasattr(embed, "external") and hasattr(embed.external, "thumb"):
        if embed.external.thumb:
            media_urls.append(embed.external.thumb)

    return media_urls

def extract_links_from_facets(post):
    urls = []

    facets = getattr(post.record, "facets", None)
    if not facets:
        return urls

    for facet in facets:
        for feature in facet.features:

            # Only grab actual links
            if isinstance(feature, models.AppBskyRichtextFacet.Link):
                urls.append(feature.uri)

    return urls


def write_to_jsonl(data: List[Dict], filename: str):
    """Writes results to a .jsonl file in the specified directory."""
    output_dir = os.path.dirname(filename)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(filename, 'w', encoding='utf-8') as f:
        for record in data:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    print(f"Saved {len(data)} records to: {os.path.abspath(filename)}")


if __name__ == '__main__':
    # --- CONFIG ---
    HANDLE = "ethicalsearch.bsky.social"
    # Ensure your APP PASSWORD is set in your environment variables
    PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    # --- PARAMETERS ---
    search_term = "dog"
    tags = ["surrender"]
    output_path = f"search_results/bsky_{search_term}_03-09-2026.jsonl"

    searcher = BlueskyPostSearcher(HANDLE, PASSWORD)

    if searcher.client:
        posts = searcher.search_recent_posts(
            keyword=search_term,
            hashtags=tags,
            limit=30
        )

        if posts:
            write_to_jsonl(posts, output_path)

            # Verification Preview
            print("\n--- JSONL Entry Preview ---")
            print(json.dumps(posts[0], indent=2))
        else:
            print("No posts found. Try broadening your search term or reducing hashtags.")
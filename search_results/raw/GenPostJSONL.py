from atproto import Client
import json
import os
from typing import List, Set


class BlueskyURLFetcher:

    def __init__(self, handle: str, password: str):
        self.client = Client()

        try:
            self.client.login(handle, password)
            print(f"Logged in as {handle}")
        except Exception as e:
            print("Login failed:", e)
            self.client = None

    def fetch_and_save(self, urls: List[str], output_file: str):

        processed_urls = load_existing_urls(output_file)
        print(f"Loaded {len(processed_urls)} already processed posts")

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        did_cache = {}

        with open(output_file, "a", encoding="utf-8") as f:

            for url in urls:

                if url in processed_urls:
                    print(f"Skipping existing: {url}")
                    continue

                try:

                    parts = url.split("/")
                    handle = parts[4]
                    rkey = parts[6]

                    # Resolve handle -> DID (cached)
                    if handle not in did_cache:
                        identity = self.client.com.atproto.identity.resolve_handle(
                            params={"handle": handle}
                        )
                        did_cache[handle] = identity.did

                    did = did_cache[handle]

                    uri = f"at://{did}/app.bsky.feed.post/{rkey}"

                    response = self.client.app.bsky.feed.get_posts(
                        params={"uris": [uri]}
                    )

                    if not response.posts:
                        print(f"No post found: {url}")
                        continue

                    post = response.posts[0]

                    record = {
                        "author_handle": post.author.handle,
                        "post_url": url,
                        "text": post.record.text,
                        "created_at": post.record.created_at,
                        "image_urls": extract_media_urls(post)
                    }

                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()

                    print(f"Saved: {url}")

                except Exception as e:
                    print(f"Failed: {url} → {e}")


def extract_media_urls(post_view):

    media_urls = []

    embed = getattr(post_view, "embed", None)
    if not embed:
        return media_urls

    if hasattr(embed, "media"):
        embed = embed.media

    if hasattr(embed, "images"):
        for img in embed.images:

            if hasattr(img, "thumb") and img.thumb:
                media_urls.append(img.thumb)

            elif hasattr(img, "fullsize") and img.fullsize:
                media_urls.append(img.fullsize)

    return media_urls


def load_existing_urls(filename: str) -> Set[str]:

    urls = set()

    if not os.path.exists(filename):
        return urls

    with open(filename, "r", encoding="utf-8") as f:

        for line in f:
            try:
                obj = json.loads(line)
                urls.add(obj["post_url"])
            except:
                pass

    return urls


if __name__ == "__main__":

    HANDLE = "ethicalsearch.bsky.social"
    PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    urls = [

        "https://bsky.app/profile/sandy174.bsky.social/post/3mgj4ulxr4c2d",
        "https://bsky.app/profile/sandy174.bsky.social/post/3mehqledxzs26",
        "https://bsky.app/profile/pawspathtofurever.bsky.social/post/3mfv6akc3ok2h",
        "https://bsky.app/profile/sandy174.bsky.social/post/3mgnllxp5uc26",
        "https://bsky.app/profile/sandy174.bsky.social/post/3mf3ztnw5ns2a",
        "https://bsky.app/profile/dovewoman.bsky.social/post/3mej2lrkmtc27",
        "https://bsky.app/profile/v3ndettaval.bsky.social/post/3mgh5ylov4c2m",
        "https://bsky.app/profile/notthesameone2.bsky.social/post/3mgj7dekfbs23",
        "https://bsky.app/profile/sandy174.bsky.social/post/3mggo5pziok2w",
        "https://bsky.app/profile/ckinser.bsky.social/post/3mgj3ofmwck2n",
        "https://bsky.app/profile/ckinser.bsky.social/post/3mgj3lffq4s2n",
        "https://bsky.app/profile/tammyfeabakker.bsky.social/post/3mgkkds7svs2b",
        "https://bsky.app/profile/tammyfeabakker.bsky.social/post/3mgkkgxqgxk2b",
        "https://bsky.app/profile/ckinser.bsky.social/post/3mgjaucqilc2n",
        "https://bsky.app/profile/ckinser.bsky.social/post/3mgjhfawdx22u",
        "https://bsky.app/profile/sandy174.bsky.social/post/3mgf6memk222q"
    ]

    output = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/search_results/raw/manual_1630.jsonl"

    fetcher = BlueskyURLFetcher(HANDLE, PASSWORD)

    if fetcher.client:
        fetcher.fetch_and_save(urls, output)
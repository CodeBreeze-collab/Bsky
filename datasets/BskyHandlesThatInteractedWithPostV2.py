import os
import json
import logging
import time
import requests
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_BASE_URL = "https://bsky.social/xrpc"
PAGINATION_DELAY = 0.6  # polite delay between requests


class BlueskyInteractionsFetcher:
    def __init__(self, handle: str, password: str):
        self.handle = handle
        self.password = password
        self.token = None

    def login(self) -> bool:
        url = f"{API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            self.token = res.json().get("accessJwt")
            logging.info(f"Logged in as {self.handle}")
            return bool(self.token)
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def resolve_did(self, handle: str) -> str:
        url = f"{API_BASE_URL}/com.atproto.identity.resolveHandle"
        # The API expects the full handle string in the query parameters
        params = {"handle": handle}
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            res = requests.get(url, params=params, headers=headers)
            res.raise_for_status()
            return res.json().get("did")
        except Exception as e:
            logging.error(f"Failed to resolve DID for {handle}: {e}")
            return None

    def parse_post_url(self, post_url: str):
        try:
            parts = urlparse(post_url).path.strip("/").split("/")
            if len(parts) >= 4 and parts[2] == "post":
                # KEEP the full handle (e.g., "vegansearchengine.bsky.social")
                handle = parts[1]
                rkey = parts[3]
                return handle, rkey
        except Exception as e:
            logging.warning(f"Failed to parse URL {post_url}: {e}")
        return None, None

    def build_post_uri(self, did: str, rkey: str):
        """Construct the correct AT URI for interaction endpoints."""
        return f"at://{did}/app.bsky.feed.post/{rkey}"

    def fetch_likes(self, post_uri: str) -> list:
        url = f"{API_BASE_URL}/app.bsky.feed.getLikes"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"uri": post_uri}
        try:
            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            return [like["actor"]["handle"] for like in res.json().get("likes", [])]
        except Exception as e:
            logging.warning(f"Failed to fetch likes for {post_uri}: {e}")
            return []

    def fetch_reposts(self, post_uri: str) -> list:
        url = f"{API_BASE_URL}/app.bsky.feed.getRepostedBy"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"uri": post_uri}
        try:
            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            return [r["handle"] for r in res.json().get("repostedBy", [])]
        except Exception as e:
            logging.warning(f"Failed to fetch reposts for {post_uri}: {e}")
            return []

    def fetch_replies(self, post_uri: str) -> list:
        # FIX: Changed getThread to getPostThread
        url = f"{API_BASE_URL}/app.bsky.feed.getPostThread"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"uri": post_uri}
        handles_set = set()
        try:
            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json()

            def collect_replies(post_obj):
                # The 'post' might be nested in a 'thread' or 'replies' object
                post_data = post_obj.get("post", {})
                author = post_data.get("author", {}).get("handle")
                if author:
                    handles_set.add(author)

                # Recursively walk through the replies
                for reply in post_obj.get("replies", []):
                    collect_replies(reply)

            # The root of the response is 'thread'
            collect_replies(data.get("thread", {}))
            return list(handles_set)
        except Exception as e:
            logging.warning(f"Failed to fetch thread for {post_uri}: {e}")
            return []

    def run(self, posts_file: str, output_file: str):
        posts_path = Path(posts_file)
        output_path = Path(output_file)
        os.makedirs(output_path.parent, exist_ok=True)

        # 1. Load already processed URLs to skip them
        processed_urls = set()
        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f_check:
                for line in f_check:
                    try:
                        data = json.loads(line)
                        processed_urls.add(data.get("post_url"))
                    except json.JSONDecodeError:
                        continue
            logging.info(f"Resuming: Already processed {len(processed_urls)} posts.")

        # 2. Open in append mode
        with open(posts_path, "r", encoding="utf-8") as f_in, \
                open(output_path, "a", encoding="utf-8") as f_out:

            for line in f_in:
                post_url = line.strip()
                if not post_url or post_url in processed_urls:
                    # Skips empty lines OR URLs we already have data for
                    continue

                handle, rkey = self.parse_post_url(post_url)
                if not handle or not rkey:
                    continue

                did = self.resolve_did(handle)
                if not did: continue

                post_uri = self.build_post_uri(did, rkey)

                # Fetching...
                handles_set = set()
                handles_set.update(self.fetch_likes(post_uri))
                handles_set.update(self.fetch_reposts(post_uri))
                handles_set.update(self.fetch_replies(post_uri))

                record = {"post_url": post_url, "handles": list(handles_set)}
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()  # Forces write to disk

                logging.info(f"Processed: {post_url} ({len(handles_set)} handles)")
                time.sleep(PAGINATION_DELAY)


def main():
    my_handle = "vegansearchengine.bsky.social"  # Your Bluesky handle
    my_password = os.environ.get("BLUESKY_APP_PASSWORD") # BLUESKY_APP_PASSWORD=pscu-5sha-c7za-xrcb
    if not my_password:
        logging.error("BLUESKY_APP_PASSWORD environment variable not set")
        return

    posts_file = "bluesky_posts.txt"  # input .txt with post URLs
    output_file = "bluesky_post_interactions_v2.jsonl"  # output JSONL

    fetcher = BlueskyInteractionsFetcher(my_handle, my_password)
    if fetcher.login():
        fetcher.run(posts_file, output_file)
        logging.info(f"Finished writing interactions to {output_file}")


if __name__ == "__main__":
    main()
import os
import logging
import requests
import time
import json
import argparse
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyPostFetcher:
    API_BASE_URL = "https://bsky.social/xrpc"
    PAGINATION_DELAY = 0.6

    def __init__(self, handle: str, password: str):
        self.handle = handle
        self.password = password
        self.token = None

    def login(self) -> bool:
        """Logs in to Bluesky and stores the access token."""
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}
        try:
            res = requests.post(url, json=payload, timeout=15)
            res.raise_for_status()
            self.token = res.json().get("accessJwt")
            logging.info(f"Logged in as {self.handle}")
            return bool(self.token)
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def fetch_posts(self, handle: str, cursor: str = None) -> dict:
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"actor": handle, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        res = requests.get(url, headers=headers, params=params, timeout=15)
        res.raise_for_status()
        return res.json()

    def write_batch_to_file(self, posts: list, target_handle: str, output_file: str) -> int:
        count = 0
        with open(output_file, "a", encoding="utf-8") as f:
            for item in posts:
                if "reason" in item:
                    continue

                post_view = item.get("post", {})
                record = post_view.get("record", {})
                author_info = post_view.get("author", {})
                actual_author_handle = author_info.get("handle")

                if actual_author_handle == target_handle:
                    uri = post_view.get("uri")
                    rkey = uri.split("/")[-1]

                    post_data = {
                        "url": f"https://bsky.app/profile/{actual_author_handle}/post/{rkey}",
                        "text": record.get("text", ""),
                        "created_at": record.get("createdAt", ""),
                        "handle": actual_author_handle
                    }
                    f.write(json.dumps(post_data) + "\n")
                    count += 1
        return count

    def run(self, target_handle: str, output_file: str):
        cursor = None
        last_cursor = None
        total_saved = 0
        consecutive_empty_batches = 0

        logging.info(f"Writing data to: {output_file}")

        with open(output_file, "w", encoding="utf-8") as f:
            pass

        while True:
            try:
                data = self.fetch_posts(target_handle, cursor)
                new_posts = data.get("feed", [])
                new_cursor = data.get("cursor")

                if not new_posts and not new_cursor:
                    break

                if new_cursor == cursor and cursor is not None:
                    logging.warning("Stuck cursor detected. Finishing.")
                    break

                if new_posts:
                    batch_count = self.write_batch_to_file(new_posts, target_handle, output_file)
                    total_saved += batch_count
                    consecutive_empty_batches = 0
                else:
                    consecutive_empty_batches += 1

                logging.info(
                    f"Fetched {len(new_posts)} items. Total saved: {total_saved}. Cursor: {new_cursor[:15] if new_cursor else 'None'}")

                cursor = new_cursor
                if not cursor or consecutive_empty_batches > 5:
                    break

                time.sleep(self.PAGINATION_DELAY)

            except Exception as e:
                logging.error(f"Error: {e}")
                break

        logging.info(f"Done! Saved {total_saved} posts to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Fetch posts from a Bluesky user and save to JSONL.")

    # Arguments
    parser.add_argument("--handle", required=True, help="Your Bluesky handle (e.g., user.bsky.social)")
    parser.add_argument("--password", required=True, help="Your Bluesky App Password")
    parser.add_argument("--target", required=True, help="The handle of the user you want to scrape")
    parser.add_argument("--output", help="Optional: specific output file path")

    args = parser.parse_args()

    # Determine output path if not provided
    if args.output:
        output_path = args.output
    else:
        output_path = f"posts_{args.target.replace('.', '_')}.jsonl"

    fetcher = BlueskyPostFetcher(args.handle, args.password)
    if fetcher.login():
        fetcher.run(args.target, output_path)


if __name__ == "__main__":
    main()
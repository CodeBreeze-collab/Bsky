import os
import logging
import requests
import time
import json

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
            res = requests.post(url, json=payload)
            res.raise_for_status()
            self.token = res.json().get("accessJwt")
            logging.info(f"Logged in as {self.handle}")
            return bool(self.token)
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def fetch_posts(self, handle: str, cursor: str = None) -> dict:
        """Fetches a single page of posts with a safety timeout."""
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"actor": handle, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        # timeout=15 ensures the script doesn't stall indefinitely on network lag
        res = requests.get(url, headers=headers, params=params, timeout=15)
        res.raise_for_status()
        return res.json()

    def write_posts_to_file(self, posts: list, target_handle: str, output_file: str):
        """
        Filters out reposts and writes post URLs to a text file.
        """
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            for item in posts:
                # Skip reposts (identified by 'reason' or different author)
                if "reason" in item:
                    continue

                post_view = item.get("post", {})
                author_info = post_view.get("author", {})
                actual_author_handle = author_info.get("handle")

                if actual_author_handle != target_handle:
                    continue  # skip reposts

                uri = post_view.get("uri")
                if uri:
                    rkey = uri.split("/")[-1]
                    post_url = f"https://bsky.app/profile/{actual_author_handle}/post/{rkey}"
                    f.write(post_url + "\n")
                    logging.info(f"Saved: {post_url}")



    def write_batch_to_file(self, posts: list, target_handle: str, output_file: str) -> int:
        """Writes a batch of posts as JSONL and returns the count."""
        count = 0
        with open(output_file, "a", encoding="utf-8") as f:
            for item in posts:
                # Skip reposts
                if "reason" in item:
                    continue

                post_view = item.get("post", {})
                record = post_view.get("record", {})
                author_info = post_view.get("author", {})
                actual_author_handle = author_info.get("handle")

                if actual_author_handle == target_handle:
                    uri = post_view.get("uri")
                    rkey = uri.split("/")[-1]

                    # Construct the data object
                    post_data = {
                        "url": f"https://bsky.app/profile/{actual_author_handle}/post/{rkey}",
                        "text": record.get("text", ""),
                        "created_at": record.get("createdAt", ""),
                        "handle": actual_author_handle
                    }

                    # Write as a single JSON line
                    f.write(json.dumps(post_data) + "\n")
                    count += 1
        return count

    def run(self, target_handle: str, output_file: str):
        """Fetches ALL posts with protection against infinite loops and stalls."""
        cursor = None
        last_cursor = None
        total_saved = 0
        consecutive_empty_batches = 0

        logging.info(f"Writing data to: {output_file}")
        logging.info(f"Starting fetch for {target_handle}...")

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Initialize/Clear the file
        with open(output_file, "w", encoding="utf-8") as f:
            pass

        while True:
            try:
                data = self.fetch_posts(target_handle, cursor)
                new_posts = data.get("feed", [])
                new_cursor = data.get("cursor")

                # 1. Check if the API returned no data and no new cursor
                if not new_posts and not new_cursor:
                    logging.info("End of feed reached (no data, no cursor).")
                    break

                # 2. Prevent Infinite Loop: Check if the cursor is stuck
                if new_cursor == cursor and cursor is not None:
                    logging.warning("API returned the same cursor twice. Breaking to avoid infinite loop.")
                    break

                # 3. Process the batch
                if new_posts:
                    batch_count = self.write_batch_to_file(new_posts, target_handle, output_file)
                    total_saved += batch_count
                    consecutive_empty_batches = 0
                else:
                    consecutive_empty_batches += 1

                # Logging visibility: shows you the script is active even if not saving anything
                logging.info(f"Fetched {len(new_posts)} items. Total saved: {total_saved}. Cursor: {new_cursor[:15] if new_cursor else 'None'}...")

                # 4. Update cursor for next iteration
                cursor = new_cursor

                # 5. Safety break for extremely long empty stretches
                if not cursor or consecutive_empty_batches > 5:
                    if consecutive_empty_batches > 5:
                        logging.info("Too many consecutive empty batches. Finishing.")
                    break

                time.sleep(self.PAGINATION_DELAY)

            except requests.exceptions.RequestException as e:
                logging.error(f"Network error: {e}. Attempting to stop gracefully.")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                break

        logging.info(f"Finished! Total: {total_saved} JSONL lines written to {output_file}")


def main():
    import os
    from pathlib import Path

    # Your Bluesky login handle
    my_handle = "ethicalsearch.bsky.social"

    # Password stored in environment variable for security
    my_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not my_password:
        logging.error("BLUESKY_APP_PASSWORD environment variable not set")
        return

    # The handle you want to fetch posts from
    target_handle = "icegoons.bsky.social"

    # Output file path
    output_file = Path("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_posts" + target_handle + ".jsonl")  # will create in current directory

    # Initialize fetcher and login
    fetcher = BlueskyPostFetcher(my_handle, my_password)
    if not fetcher.login():
        logging.error("Login failed, cannot proceed.")
        return

    # Fetch posts and write URLs
    fetcher.run(target_handle, str(output_file))
    logging.info(f"Finished writing posts to {output_file}")


if __name__ == "__main__":
    main()
import os
import json
import time
import logging
import requests

from datetime import datetime, timezone, timedelta
from typing import List, Dict
from pathlib import Path
from google import genai  # Ensure you have run: pip install google-genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyRescueChecker:
    API_BASE_URL = "https://bsky.social/xrpc"
    PAGINATION_DELAY = 0.6

    RESCUE_KEYWORDS = [
        "adopt", "adoption", "foster", "rescue", "urgent",
        "needs home", "needs a home", "save", "help", "shelter",
        "rehoming", "looking for a home", "deadline", "euth",
        "at risk", "kill shelter", "transport",
        "needs placement", "rescue commitment", "needs rescue",
        "needs foster", "needs adopter"
    ]

    def __init__(self, handle: str, password: str, gemini_api_key: str):
        self.handle = handle
        self.password = password
        self.token = None

        # UPDATED: Initialize the Client object
        self.client = genai.Client(api_key=gemini_api_key)
        # UPDATED: Using a stable current model ID
        self.model_id = "gemini-2.5-flash"
        logging.info("Gemini client initialized.")

    def login(self) -> bool:
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}

        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            self.token = data.get("accessJwt")
            if self.token:
                logging.info(f"Logged in successfully as {self.handle}")
                return True
            else:
                logging.error("Login succeeded but no access token received.")
                return False
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def load_accounts(self, jsonl_path: str) -> List[Dict]:
        accounts = []
        if not os.path.exists(jsonl_path):
            logging.error(f"Input file not found: {jsonl_path}")
            return accounts
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    account = json.loads(line)
                    accounts.append(account)
                except Exception as e:
                    logging.warning(f"Skipping invalid line in JSONL: {e}")
        logging.info(f"Loaded {len(accounts)} accounts from {jsonl_path}")
        return accounts

    def fetch_posts(self, did: str, since_date: datetime) -> List[Dict]:
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"actor": did, "limit": 50}
        try:
            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            feed = res.json().get("feed", [])
        except Exception as e:
            logging.warning(f"Error fetching posts for {did}: {e}")
            return []

        posts = []
        for item in feed:
            post = item.get("post", {})
            if not post:
                continue

            ts_str = post.get("indexedAt")
            if not ts_str:
                continue
            try:
                post_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                continue

            if post_dt < since_date:
                continue

            posts.append(post)

        return posts

    def extract_images(self, post: Dict) -> List[str]:
        images = []
        embed = post.get("embed")
        if not embed:
            return images
        if embed.get("$type") == "app.bsky.embed.images#view":
            for img in embed.get("images", []):
                if "fullsize" in img:
                    images.append(img["fullsize"])
        return images

    def call_gemini(self, title: str, text: str, image_urls: List[str]) -> str:
        """Classify posts into NEED_A_HOME, DONATION_REQUEST, OTHER"""
        prompt = f"""
        You are analyzing posts from animal rescue organizations.

        Classify the post into ONE category:
        NEED_A_HOME
        DONATION_REQUEST
        OTHER

        Return ONLY the category name.

        Post title: {title}
        Post text: {text}
        Image URLs: {", ".join(image_urls) if image_urls else "None"}
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            answer = response.text.strip().upper()

            if "NEED_A_HOME" in answer:
                return "NEED_A_HOME"
            elif "DONATION_REQUEST" in answer:
                return "DONATION_REQUEST"
            else:
                return "OTHER"
        except Exception as e:
            logging.warning(f"Gemini API call failed: {e}")
            return "OTHER"

    def process_accounts(self, accounts: List[Dict], since_days: int, output_file: str, dry_run: bool = False):
        since_date = datetime.now(timezone.utc) - timedelta(days=since_days)
        out_f = None

        if not dry_run:
            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_f = open(out_path, "a", encoding="utf-8")
            logging.info(f"Target file: {out_path.absolute()}")

        logging.info(f"Scanning {len(accounts)} accounts since {since_date.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        try:
            for acct in accounts:
                handle = acct.get("handle")
                did = acct.get("did")
                if not did or not handle:
                    continue

                feed_items = self.fetch_posts(did, since_date)

                if not feed_items:
                    logging.info(f"{handle}: 0 posts found in time range.")
                    continue

                logging.info(f"{handle}: Processing {len(feed_items)} posts...")

                for post_view in feed_items:
                    record = post_view.get("record", {})
                    text = record.get("text", "") or ""

                    if not text:
                        logging.debug(f" [!] Skipping empty text post in {handle}")
                        continue

                    # Extract Quoted Content
                    quote_text = ""
                    embed = post_view.get("embed", {})
                    if embed.get("$type") == "app.bsky.embed.record#view":
                        rec_data = embed.get("record", {})
                        quote_text = rec_data.get("value", {}).get("text", "") or rec_data.get("text", "")

                    # Construct URL
                    post_uri = post_view.get("uri", "")
                    post_id = post_uri.split("/")[-1] if "/" in post_uri else "unknown"
                    post_url = f"https://bsky.app/profile/{handle}/post/{post_id}"

                    # Gemini Classification
                    images = self.extract_images(post_view)
                    full_context = f"Post: {text}\nQuoted Content: {quote_text}"

                    category = self.call_gemini("", full_context, images)

                    logging.info(f" [→] Post: {text[:50]}... | Result: {category}")

                    if category == "OTHER":
                        continue

                    result = {
                        "handle": handle,
                        "post_url": post_url,
                        "category": category,
                        "text": text,
                        "quoted_text": quote_text,
                        "indexedAt": post_view.get("indexedAt")
                    }

                    if not dry_run and out_f:
                        out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                        out_f.flush()
                        logging.info(f" [SAVED] {category}: {post_url}")

                time.sleep(self.PAGINATION_DELAY)

        except KeyboardInterrupt:
            logging.warning("\nUser interrupted execution.")
        finally:
            if out_f:
                out_f.close()
                logging.info("File handle closed.")


def main():
    # 1. Configuration
    bluesky_handle = "ethicalsearch.bsky.social"
    bluesky_password = os.environ.get("BLUESKY_APP_PASSWORD")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not bluesky_password or not gemini_key:
        logging.error("Missing environment variables (BLUESKY_APP_PASSWORD or GEMINI_API_KEY). Exiting.")
        return

    # 2. Path Handling
    base_path = Path("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets")
    input_file = base_path / "bluesky_rescue_accounts_active.jsonl"

    date_str = datetime.now().strftime('%m-%d-%Y')
    output_dir = base_path / "needs_help" / date_str
    output_file = output_dir / "bluesky_rescue_posts_output-v2.jsonl"

    # 3. Initialize and Login
    checker = BlueskyRescueChecker(bluesky_handle, bluesky_password, gemini_key)

    if not checker.login():
        return

    # 4. Load Accounts
    accounts = checker.load_accounts(str(input_file))
    if not accounts:
        return

    # 5. Execute Process
    checker.process_accounts(
        accounts,
        since_days=1,
        output_file=str(output_file),
        dry_run=False
    )

    logging.info(f"Finished processing. Results saved to: {output_file}")


if __name__ == "__main__":
    main()
import os
import json
import time
import logging
import requests
import google.generativeai as genai

from datetime import datetime, timezone, timedelta
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyRescueChecker:
    API_BASE_URL = "https://bsky.social/xrpc"
    PAGINATION_DELAY = 0.6

    RESCUE_KEYWORDS = [
        "adopt",
        "adoption",
        "foster",
        "rescue",
        "urgent",
        "needs home",
        "needs a home",
        "save",
        "help",
        "shelter",
        "rehoming",
        "looking for a home"
    ]

    def __init__(self, handle: str, password: str, gemini_api_key: str):
        self.handle = handle
        self.password = password
        self.token = None

        # Configure Gemini
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def login(self) -> bool:
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}

        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            self.token = data["accessJwt"]
            logging.info(f"Logged in as {self.handle}")
            return True
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def load_accounts(self, jsonl_path: str) -> List[Dict]:
        accounts = []

        if not os.path.exists(jsonl_path):
            return accounts

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    accounts.append(json.loads(line))
                except Exception:
                    continue

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
            record = post.get("record", {})

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
        """Extract image URLs from Bluesky embed."""
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
        """
        Classify whether a post is about a rescue animal needing help.
        Returns 'yes' or 'no'.
        """

        prompt = f"""
    You are classifying posts from animal rescue organizations.

    Return ONLY one word: YES or NO.

    YES if the post is about:
    - an animal needing adoption
    - foster requests
    - rescue appeals
    - injured/sick animals needing help
    - urgent rescue situations
    - animals needing a home

    NO if the post is about:
    - general updates
    - fundraising without a specific animal
    - news
    - memes
    - general awareness posts

    Post title:
    {title}

    Post text:
    {text}

    Image URLs:
    {", ".join(image_urls) if image_urls else "None"}

    Answer ONLY YES or NO.
    """

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0,
                    "max_output_tokens": 5
                }
            )

            answer = response.text.strip().lower()

            if answer.startswith("yes"):
                return "yes"
            elif answer.startswith("no"):
                return "no"
            else:
                logging.warning(f"Unexpected Gemini response: {answer}")
                return "no"

        except Exception as e:
            logging.warning(f"Gemini API call failed: {e}")
            return "no"

    def process_accounts(self, accounts: List[Dict], since_days: int, output_file: str):

        since_date = datetime.now(timezone.utc) - timedelta(days=since_days)

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        for acct in accounts:

            did = acct.get("did")
            handle = acct.get("handle")
            display_name = acct.get("display_name", "")

            if not did or not handle:
                continue

            posts = self.fetch_posts(did, since_date)

            logging.info(f"Fetched {len(posts)} posts for {handle}")

            for post in posts:

                record = post.get("record", {})
                uri = post.get("uri", "")

                title = record.get("title", "") or ""
                text = record.get("text", "") or ""

                images = self.extract_images(post)

                # Extract Bluesky post ID
                post_id = ""
                if uri:
                    try:
                        post_id = uri.split("/")[-1]
                    except Exception:
                        pass

                post_url = ""
                if post_id:
                    post_url = f"https://bsky.app/profile/{handle}/post/{post_id}"

                combined_text = f"{title} {text}".lower()

                # Keyword pre-filter to reduce Gemini calls
                likely_rescue = any(
                    keyword in combined_text for keyword in self.RESCUE_KEYWORDS
                )

                if likely_rescue:
                    rescue_flag = self.call_gemini(title, text, images)
                else:
                    rescue_flag = "no"

                result = {
                    "handle": handle,
                    "did": did,
                    "display_name": display_name,
                    "title": title,
                    "text": text,
                    "images": images,
                    "post_url": post_url,
                    "rescue_post": rescue_flag,
                    "indexedAt": post.get("indexedAt")
                }

                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")

                if rescue_flag == "yes":
                    logging.info(f"RESCUE POST FOUND: {post_url}")

                time.sleep(self.PAGINATION_DELAY)


if __name__ == "__main__":

    bluesky_handle = "ethicalsearch.bsky.social"
    bluesky_password = os.environ.get("BLUESKY_APP_PASSWORD")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not (bluesky_handle and bluesky_password and gemini_key):
        logging.error("Missing environment variables.")
        exit(1)

    input_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_rescue_accounts_active.jsonl"

    output_file = "/bsky/datasets/needs_help/03-11-2026-v1/bluesky_rescue_posts_output.jsonl"

    checker = BlueskyRescueChecker(
        bluesky_handle,
        bluesky_password,
        gemini_key
    )

    if not checker.login():
        exit(1)

    accounts = checker.load_accounts(input_file)

    checker.process_accounts(accounts, since_days=1, output_file=output_file)
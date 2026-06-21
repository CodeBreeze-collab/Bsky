import os
import json
import time
import logging
import requests
import sys
import argparse

from datetime import datetime, timezone, timedelta
from typing import List, Dict
from pathlib import Path
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyRescueChecker:
    API_BASE_URL = "https://bsky.social/xrpc"
    PAGINATION_DELAY = 0.6

    def __init__(self, handle: str, password: str, gemini_api_key: str):
        self.handle = handle
        self.password = password
        self.token = None

        http_options = types.HttpOptions(timeout=30000)

        self.client = genai.Client(
            vertexai=True,
            project="summary-334d4",
            location="us-east4",
            http_options=http_options
        )
        self.model_id = "gemini-2.5-flash"
        logging.info(f"Gemini client initialized with model: {self.model_id}")

    def login(self) -> bool:
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}
        try:
            res = requests.post(url, json=payload, timeout=15)
            res.raise_for_status()
            self.token = res.json().get("accessJwt")
            return True if self.token else False
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
                    accounts.append(json.loads(line))
                except:
                    continue
        return accounts

    def fetch_posts(self, did: str, since_date: datetime) -> List[Dict]:
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"actor": did, "limit": 50}

        try:
            res = requests.get(url, headers=headers, params=params, timeout=15)
            res.raise_for_status()
            feed = res.json().get("feed", [])
        except Exception as e:
            logging.warning(f" [!] Error fetching posts: {e}")
            return []

        posts = []
        for item in feed:
            post_data = item.get("post", {})
            ts_str = post_data.get("indexedAt") or item.get("indexedAt")

            if not ts_str:
                continue

            try:
                post_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if post_dt >= since_date:
                    posts.append(item)
            except Exception as e:
                logging.error(f"Date parsing error: {e}")
                continue

        return posts

    def load_seen_posts(self, output_file: str) -> set:
        seen = set()
        if not os.path.exists(output_file):
            return seen

        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if "post_url" in data:
                        seen.add(data["post_url"])
                except:
                    continue
        logging.info(f"Loaded {len(seen)} already processed posts.")
        return seen

    def extract_images(self, post_view: Dict) -> List[str]:
        images = []
        embed = post_view.get("embed", {})
        if not embed:
            return images

        if embed.get("$type") == "app.bsky.embed.images#view":
            for img in embed.get("images", []):
                url = img.get("fullsize") or img.get("thumb")
                if url: images.append(url)

        elif embed.get("$type") == "app.bsky.embed.recordWithMedia#view":
            media = embed.get("media", {})
            if media.get("$type") == "app.bsky.embed.images#view":
                for img in media.get("images", []):
                    url = img.get("fullsize") or img.get("thumb")
                    if url: images.append(url)

        elif not images and embed.get("$type") == "app.bsky.embed.external#view":
            thumb = embed.get("external", {}).get("thumb")
            if thumb: images.append(thumb)

        return images

    def call_gemini(self, text: str, images: List[str]) -> str:
        prompt = (
            "Classify into NEED_A_HOME, DONATION_REQUEST, or OTHER. "
            f"Return ONLY the word.\n\nText: {text}\nImages: {', '.join(images)}"
        )

        max_retries = 5
        base_delay = 5

        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    time.sleep(1.0)

                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt
                )

                if not response.text:
                    finish_reason = "UNKNOWN"
                    if response.candidates:
                        finish_reason = response.candidates[0].finish_reason

                    logging.warning(f" [!] Gemini returned empty text. Reason: {finish_reason}. Defaulting to OTHER.")
                    return "OTHER"

                return response.text.strip().upper()

            except Exception as e:
                err_msg = str(e).upper()
                retry_keywords = ["429", "RESOURCE_EXHAUSTED", "503", "500", "DISCONNECTED", "RESPONSE", "RESET",
                                  "TIMEOUT", "DEADLINE"]

                if any(x in err_msg for x in retry_keywords):
                    wait_time = base_delay * (2 ** attempt)
                    logging.warning(
                        f" [!] Gemini Rate Limit/Server/Timeout Error ({e}). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                logging.error(f"Gemini API Call failed on attempt {attempt + 1}: {e}")
                raise e

        raise Exception("Gemini API failed after maximum retries.")

    def process_accounts(self, accounts: List[Dict], since_date: datetime, output_file: str):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        processed_urls = self.load_seen_posts(output_file)
        out_f = open(output_file, "a", encoding="utf-8")

        logging.info(f"Processing {len(accounts)} accounts since {since_date}")

        try:
            for acct in accounts:
                scanner_handle = acct.get("handle")
                scanner_did = acct.get("did")
                if not scanner_did:
                    continue

                feed_items = self.fetch_posts(scanner_did, since_date)
                if not feed_items:
                    logging.info(f"[-] {scanner_handle}: No recent posts.")
                    continue

                for item in feed_items:
                    if "reason" in item:
                        continue

                    post_view = item.get("post", {})
                    author_info = post_view.get("author", {})
                    if not post_view or author_info.get("did") != scanner_did:
                        continue

                    uri = post_view.get("uri", "")
                    actual_author_handle = author_info.get("handle")
                    if not uri or not actual_author_handle:
                        continue

                    rkey = uri.split("/")[-1]
                    post_url = f"https://bsky.app/profile/{actual_author_handle}/post/{rkey}"

                    if post_url in processed_urls:
                        continue

                    record = post_view.get("record", {})
                    text = record.get("text", "")
                    if not text:
                        continue

                    images = self.extract_images(post_view)

                    # --- LOCAL TRY-CATCH SAFEGUARD ---
                    try:
                        category = self.call_gemini(text, images)
                    except Exception as post_error:
                        # Catching the exhausted retry exception here prevents the master script from halting.
                        logging.error(
                            f" [⚠️] SKIPPING POST: Gemini timed out persistently on {post_url}. Error: {post_error}")
                        continue  # Safely advance to the next available post

                    if any(cat in category for cat in ["NEED_A_HOME", "DONATION_REQUEST"]):
                        result = {
                            "scanned_via": scanner_handle,
                            "author_handle": actual_author_handle,
                            "post_url": post_url,
                            "category": "NEED_A_HOME" if "NEED_A_HOME" in category else "DONATION_REQUEST",
                            "text": text,
                            "image_urls": images,
                            "posted_at": record.get("createdAt"),
                            "indexedAt": post_view.get("indexedAt")
                        }

                        out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                        out_f.flush()
                        logging.info(f" [✅] SAVED: {post_url}")
                    else:
                        logging.info(f" [🤖] OTHER: {actual_author_handle}")

                    time.sleep(1.5)
                time.sleep(self.PAGINATION_DELAY)

        except Exception as fatal_error:
            # This only fires if something severe crashes the loop framework itself (e.g., file system unmounted)
            logging.error(f"!!! HALTING SCRIPT: {fatal_error}")
            sys.exit(1)
        finally:
            out_f.close()
            logging.info("File closed safely.")


def main():
    base = Path("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets")

    parser = argparse.ArgumentParser(description="Bluesky Rescue Checker CLI")
    parser.add_argument("--handle", type=str, default="ethicalsearch.bsky.social", help="Bluesky user handle")
    parser.add_argument("--input-file", type=str, default=None, help="Path to input accounts JSONL file")
    parser.add_argument("--output-file", type=str, default=None, help="Path to output JSONL file")
    parser.add_argument("--days", type=int, default=1, help="Number of days to look back for posts")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date in MM-DD-YYYY format to run from midnight UTC")

    args = parser.parse_args()

    pwd = os.environ.get("BLUESKY_APP_PASSWORD")
    key = os.environ.get("GEMINI_API_KEY")

    if not pwd or not key:
        logging.error("Env vars missing.")
        return

    if args.date:
        try:
            target_dt = datetime.strptime(args.date, "%m-%d-%Y")
            since_date = target_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            folder_date = args.date
        except ValueError:
            logging.error(f"Invalid date format: '{args.date}'. Please use MM-DD-YYYY.")
            return
    else:
        since_date = datetime.now(timezone.utc) - timedelta(days=args.days)
        folder_date = datetime.now().strftime('%m-%d-%Y')

    final_input = args.input_file or str(base / "bluesky_rescue_accounts-03-12-2026-handle-title.jsonl")
    final_output = args.output_file or str(
        base / "needs_help" / folder_date / "bluesky_rescue_posts_output-w-post-date.jsonl")

    checker = BlueskyRescueChecker(args.handle, pwd, key)
    if checker.login():
        accounts = checker.load_accounts(final_input)
        checker.process_accounts(accounts, since_date=since_date, output_file=final_output)


if __name__ == "__main__":
    main()
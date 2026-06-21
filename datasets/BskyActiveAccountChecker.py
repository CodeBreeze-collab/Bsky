import requests
import json
import os
import time
import logging
from typing import List, Dict
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DRY_RUN_LOG_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_rescue_accounts_active.jsonl"

class BlueskyActiveChecker:
    API_BASE_URL = "https://bsky.social/xrpc"
    PAGINATION_DELAY = 0.6  # seconds between requests

    def __init__(self, handle: str, password: str):
        self.handle = handle
        self.password = password
        self.token = None

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
                    record = json.loads(line)
                    accounts.append(record)
                except Exception:
                    continue
        logging.info(f"Loaded {len(accounts)} accounts from {jsonl_path}")
        return accounts

    def load_already_processed(self, jsonl_path: str) -> set:
        processed = set()
        if not os.path.exists(jsonl_path):
            return processed
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    processed.add(record["handle"])
                except Exception:
                    continue
        return processed

    def check_activity(self, acct: Dict, min_posts: int, recent_days: int) -> Dict:
        """Check if an account is active and return updated record with 'active' flag"""
        did = acct.get("did")
        handle = acct.get("handle")
        record = acct.copy()
        record["active"] = 0  # default inactive

        if not did or not handle:
            return record

        cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            res = requests.get(url, headers=headers, params={"actor": did, "limit": 50})
            res.raise_for_status()
            feed = res.json().get("feed", [])
        except Exception as e:
            logging.warning(f"Error fetching posts for {handle}: {e}")
            return record

        total_posts = len(feed)
        record["total_posts"] = total_posts

        if total_posts < min_posts:
            logging.info(f"Inactive (too few posts): {handle}, posts={total_posts}")
            return record

        last_post = feed[0].get("post", {})
        ts_str = last_post.get("indexedAt")
        if not ts_str:
            logging.info(f"Inactive (no valid timestamp): {handle}")
            return record

        try:
            last_post_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            logging.info(f"Inactive (invalid timestamp): {handle}, raw={ts_str}")
            return record

        record["last_post_indexedAt"] = ts_str
        record["last_post_age_days"] = (datetime.now(timezone.utc) - last_post_dt).days

        if last_post_dt >= cutoff:
            record["active"] = 1
            logging.info(f"Active: {handle}, posts={total_posts}, last_post={last_post_dt}")
        else:
            logging.info(f"Inactive (last post too old): {handle}, last_post={last_post_dt}")

        return record

    def write_jsonl_line(self, record: Dict, jsonl_path: str):
        os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def filter_and_write_active(self, accounts: List[Dict], jsonl_path: str,
                                min_posts: int = 5, recent_days: int = 30):
        processed_handles = self.load_already_processed(jsonl_path)
        logging.info(f"{len(processed_handles)} handles already processed. Skipping them.")

        for acct in accounts:
            handle = acct.get("handle")
            if not handle or handle in processed_handles:
                continue

            record = self.check_activity(acct, min_posts=min_posts, recent_days=recent_days)
            self.write_jsonl_line(record, jsonl_path)
            processed_handles.add(handle)
            time.sleep(self.PAGINATION_DELAY)


if __name__ == "__main__":
    checker = BlueskyActiveChecker(
        handle="ethicalsearch.bsky.social",
        password=os.environ.get("BLUESKY_APP_PASSWORD")
    )
    if not checker.login():
        exit(1)

    input_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_rescue_accounts.jsonl"
    output_file = DRY_RUN_LOG_FILE

    accounts = checker.load_accounts(input_file)
    checker.filter_and_write_active(accounts, output_file, min_posts=5, recent_days=30)
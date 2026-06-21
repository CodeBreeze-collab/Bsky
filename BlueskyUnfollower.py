import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Robust imports based on your provided pattern
try:
    from atproto import Client
except ImportError:
    logging.error("FATAL: Could not import 'Client' from 'atproto'.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyUnfollower:
    def __init__(self, username: str, password: str, request_delay: int = 2):
        self.client = Client()
        self.username = username
        self.password = password
        self.request_delay = request_delay

    def login(self) -> bool:
        logging.info(f"Logging in as {self.username}...")
        try:
            self.client.login(self.username, self.password)
            return True
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def _get_follow_uri(self, target_did: str) -> Optional[str]:
        """
        Retrieves the URI of the follow record for a specific DID.
        In Bluesky, unfollowing is deleting this specific record.
        """
        try:
            # We fetch the target's profile to see our current 'viewer' relationship
            profile = self.client.get_profile(target_did)
            # viewer.following contains the AT-URI of the follow record if it exists
            return profile.viewer.following
        except Exception as e:
            logging.error(f"Could not find follow status for {target_did}: {e}")
            return None

    def unfollow_by_did(self, did: str, handle: str = "Unknown") -> bool:
        """Executes the unfollow action using the DID."""
        follow_uri = self._get_follow_uri(did)

        if not follow_uri:
            logging.info(f"ℹ️ Skipping @{handle}: You are not following them.")
            return False

        try:
            self.client.delete_follow(follow_uri)
            logging.info(f"✅ Unfollowed @{handle} ({did})")
            return True
        except Exception as e:
            logging.error(f"❌ Failed to delete follow record for @{handle}: {e}")
            return False

    def process_jsonl_file(self, file_path: str):
        """Iterates through a .jsonl file and unfollows the targets within."""
        path = Path(file_path)
        if not path.exists():
            logging.error(f"File not found: {file_path}")
            return

        with path.open('r', encoding='utf-8') as f:
            lines = f.readlines()

        logging.info(f"📋 Found {len(lines)} records in {path.name}. Starting...")

        for i, line in enumerate(lines):
            try:
                data = json.loads(line.strip())
                target_did = data.get("target_did")
                target_handle = data.get("target_handle", "Unknown")

                if not target_did:
                    logging.warning(f"Line {i + 1}: Missing 'target_did'. Skipping.")
                    continue

                logging.info(f"[{i + 1}/{len(lines)}] Target: @{target_handle}")
                self.unfollow_by_did(target_did, target_handle)

                # Delay between actions to prevent rate limiting
                if i < len(lines) - 1:
                    time.sleep(self.request_delay)

            except json.JSONDecodeError:
                logging.error(f"Line {i + 1}: Invalid JSON formatting. Skipping.")
                continue


if __name__ == '__main__':
    # --- CONFIGURATION ---
    YOUR_HANDLE = "vegansearchengine.bsky.social"
    YOUR_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

    # Path to your .jsonl file
    JSONL_INPUT = "unfollow_list.jsonl"

    if not YOUR_PASSWORD:
        logging.critical("FATAL: BLUESKY_APP_PASSWORD environment variable not set.")
        sys.exit(1)

    unfollower = BlueskyUnfollower(YOUR_HANDLE, YOUR_PASSWORD, request_delay=3)

    if unfollower.login():
        unfollower.process_jsonl_file(JSONL_INPUT)
        logging.info("Process finished.")
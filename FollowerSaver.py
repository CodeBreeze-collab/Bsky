import requests
import time
import logging
import os
import sys
import re
from datetime import datetime
from typing import List, Dict, Optional

# --- LOGGING CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION ---
MY_HANDLE = "ethicalsearch.bsky.social"
APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")


class BlueskyFollowTool:
    API_BASE_URL = "https://bsky.social/xrpc"
    PAGINATION_DELAY = 0.5  # Time to wait between pages to respect rate limits

    def __init__(self, handle: str, password: str):
        self.handle = handle
        self.password = password
        self.token = None

    def _get_session(self) -> bool:
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}
        logging.info("Authenticating...")
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            self.token = res.json()["accessJwt"]
            return True
        except Exception as e:
            logging.error(f"❌ Auth Error: {e}")
            return False

    def resolve_handle(self, handle: str) -> Optional[str]:
        url = f"{self.API_BASE_URL}/com.atproto.identity.resolveHandle"
        try:
            res = requests.get(url, params={"handle": handle})
            return res.json().get("did")
        except:
            return None

    def get_all_followers_raw(self, target_did: str) -> List[Dict[str, str]]:
        """
        Paginates through EVERY follower until the API returns no more cursors.
        """
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.API_BASE_URL}/app.bsky.graph.getFollowers"
        all_followers = []
        cursor = None
        page_count = 0

        logging.info("📥 Starting full extraction. This may take a while for large accounts...")

        while True:
            params = {"actor": target_did, "limit": 100}
            if cursor:
                params["cursor"] = cursor

            try:
                res = requests.get(url, headers=headers, params=params)
                if res.status_code == 429:
                    logging.warning("⚠️ Rate limited! Cooling down for 30s...")
                    time.sleep(30)
                    continue
                res.raise_for_status()
                data = res.json()
            except Exception as e:
                logging.error(f"❌ API Error during pagination: {e}")
                break

            batch = data.get('followers', [])
            if not batch:
                break

            for p in batch:
                all_followers.append({'handle': p.get('handle'), 'did': p.get('did')})

            page_count += 1
            if page_count % 10 == 0:
                logging.info(f"📑 Progress: Collected {len(all_followers)} followers...")

            cursor = data.get('cursor')
            if not cursor:
                logging.info("🏁 No more pages. Extraction complete.")
                break

            time.sleep(self.PAGINATION_DELAY)

        return all_followers


class FollowerSaver:
    def __init__(self, tool: BlueskyFollowTool):
        self.tool = tool

    def _sanitize_filename(self, name: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '', name)

    def save_all_to_txt(self, target_handle: str):
        """Resolves target and saves ALL followers to a timestamped file."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        clean_handle = self._sanitize_filename(target_handle)
        filename = f"{clean_handle}_ALL_{timestamp}.txt"

        target_did = self.tool.resolve_handle(target_handle)
        if not target_did:
            logging.error(f"❌ Could not find DID for {target_handle}")
            return

        followers = self.tool.get_all_followers_raw(target_did)

        if not followers:
            logging.warning("⚠️ No followers found.")
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for person in followers:
                    f.write(f"{person['handle']},{person['did']}\n")
            logging.info(f"💾 Success! Total {len(followers)} followers saved to: {filename}")
        except IOError as e:
            logging.error(f"❌ File Write Error: {e}")


# --- MAIN METHOD ---
def main():
    if not APP_PASSWORD:
        logging.error("❌ BLUESKY_APP_PASSWORD environment variable not set.")
        sys.exit(1)

    tool = BlueskyFollowTool(MY_HANDLE, APP_PASSWORD)
    if tool._get_session():
        saver = FollowerSaver(tool)

        # Example Target
        target = "vegansearchengine.bsky.social"
        saver.save_all_to_txt(target)


if __name__ == "__main__":
    main()
import os
import requests
import time
import csv
from datetime import datetime


class BlueskyInteraction:
    API_BASE_URL = "https://bsky.social/xrpc"

    def __init__(self, handle: str, password: str):
        self.handle = handle.lower().lstrip('@')
        self.password = password
        self.token = None
        self.my_did = None
        self._get_session()

    def _get_session(self):
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        res = requests.post(url, json={"identifier": self.handle, "password": self.password})
        res.raise_for_status()
        data = res.json()
        self.token = data["accessJwt"]
        self.my_did = data["did"]

    def _get_latest_post_info(self, target_handle: str):
        """Fetches the URI and CID of the user's most recent post."""
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        try:
            # We only need the very first post in the feed
            res = requests.get(url, headers=headers, params={"actor": target_handle, "limit": 1})
            res.raise_for_status()
            feed = res.json().get("feed", [])

            if not feed:
                return None

            post = feed[0]["post"]
            return {
                "uri": post["uri"],
                "cid": post["cid"]
            }
        except Exception as e:
            print(f"❌ Could not fetch feed for {target_handle}: {e}")
            return None

    def like_post(self, post_uri: str, post_cid: str):
        """Creates a 'Like' record for a specific post."""
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.API_BASE_URL}/com.atproto.repo.createRecord"

        payload = {
            "repo": self.my_did,
            "collection": "app.bsky.feed.like",
            "record": {
                "subject": {
                    "uri": post_uri,
                    "cid": post_cid
                },
                "createdAt": datetime.utcnow().isoformat() + "Z"
            }
        }

        res = requests.post(url, headers=headers, json=payload)
        return res.status_code == 200

    def engage_active_users(self, tsv_path: str, active_within_days: int):
        if not os.path.exists(tsv_path):
            print(f"❌ File not found: {tsv_path}")
            return

        print(f"🚀 Liking posts for users active within {active_within_days} day(s)...")
        print("-" * 60)

        with open(tsv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter='\t')

            for row in reader:
                handle = row.get('handle', '').lower()
                days_str = row.get('number_of_days', '')

                # Skip metadata and self
                if not handle or "run date" in handle or handle == self.handle:
                    continue

                # Parse activity
                try:
                    if days_str in ["None", "Error"]:
                        continue
                    days = int(days_str)
                except:
                    continue

                # If they are active enough, give them a like
                if days <= active_within_days:
                    print(f"✨ @{handle} was active {days} days ago. Finding post...")

                    post_data = self._get_latest_post_info(handle)

                    if post_data:
                        if self.like_post(post_data["uri"], post_data["cid"]):
                            print(f"❤️  Successfully liked most recent post from @{handle}")
                        else:
                            print(f"❌ Failed to like post from @{handle}")
                    else:
                        print(f"⏩ No post found to like for @{handle}")

                    time.sleep(0.5)  # Anti-spam delay


# --- Run ---
if __name__ == "__main__":
    # The handle that will be doing the 'Liking'
    MY_HANDLE = "vegansearchengine.bsky.social"
    MY_PWD = os.environ.get("BLUESKY_APP_PASSWORD")
    TSV_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/activity_report_20251219_160159.tsv"

    if not MY_PWD:
        print("🚨 Set your BLUESKY_APP_PASSWORD environment variable!")
    else:
        liker = BlueskyInteraction(MY_HANDLE, MY_PWD)
        # Configure the 'recency' threshold here (e.g., 0 for today only, 1 for yesterday)
        liker.engage_active_users(TSV_FILE, active_within_days=1)
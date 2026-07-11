import os
import requests
import time
import csv


class BlueskyTSVUnfollower:
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

    def unfollow_user(self, follow_uri: str):
        """Uses the exact URI from the TSV to delete the follow record."""
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.API_BASE_URL}/com.atproto.repo.deleteRecord"

        # follow_uri example: at://did:plc:jag2kvikoewpjcq5dmr2nswb/app.bsky.graph.follow/3m7syc55qdh2z
        # We need the collection and the rkey (the last two parts)
        parts = follow_uri.replace("at://", "").split('/')

        payload = {
            "repo": self.my_did,
            "collection": parts[1],  # app.bsky.graph.follow
            "rkey": parts[2]  # the unique record key
        }
        res = requests.post(url, headers=headers, json=payload)
        return res.status_code == 200

    def cleanup_from_tsv(self, tsv_path: str, max_days: int):
        if not os.path.exists(tsv_path):
            print(f"❌ File not found: {tsv_path}")
            return

        print(f"🚀 Processing TSV: {tsv_path}")
        print(f"Targeting accounts inactive for > {max_days} days.")
        print("-" * 60)

        with open(tsv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter='\t')

            for row in reader:
                handle = row.get('handle', '').lower()
                days_str = row.get('number_of_days', '')
                uri = row.get('follow_uri', '')

                # 1. Skip non-account metadata rows found in your file
                if "run date" in handle or "follows that are not" in handle or not handle:
                    continue

                # 2. Skip yourself
                if handle == self.handle:
                    continue

                # 3. Parse the days
                try:
                    if days_str == "None":
                        days = 9999
                    elif days_str == "Error":
                        continue
                    else:
                        days = int(days_str)
                except (ValueError, TypeError):
                    continue

                # 4. Action Logic
                if days > max_days:
                    # Only attempt unfollow if we actually have a URI
                    if uri and uri != "None" and uri.startswith("at://"):
                        print(f"⚠️  {handle} ({days} days) matches threshold. Unfollowing...")
                        if self.unfollow_user(uri):
                            print(f"✅ Successfully unfollowed @{handle}")
                        else:
                            print(f"❌ Failed to unfollow @{handle}")
                    else:
                        print(f"⏩ Skip: No follow URI found in TSV for @{handle} (Already unfollowed?)")

                    time.sleep(0.3)  # Faster now since we aren't searching
                else:
                    print(f"🟢 Keep: @{handle} (active {days} days ago).")


# --- Run ---
if __name__ == "__main__":
    # Handle A (The one doing the unfollowing)
    MY_HANDLE = "vegansearchengine.bsky.social"
    MY_PWD = os.environ.get("BLUESKY_APP_PASSWORD")

    TSV_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/activity_report_20251219_160159.tsv"

    if not MY_PWD:
        print("🚨 Set your BLUESKY_APP_PASSWORD environment variable!")
    else:
        cleaner = BlueskyTSVUnfollower(MY_HANDLE, MY_PWD)
        # Adjust threshold here
        cleaner.cleanup_from_tsv(TSV_FILE, max_days=30)
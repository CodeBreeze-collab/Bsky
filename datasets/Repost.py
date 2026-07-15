from datetime import datetime, timezone
import json
import os
import random
import time
import requests


class BlueskyReposter:

    def __init__(self, history_file="reposted_history.json"):
        self.pds_url = "https://bsky.social"
        self.history_file = history_file
        self.reposted_uris = self._load_history()
        self.access_jwt = None
        self.did = None

    def _load_history(self) -> set:
        """Loads a list of previously reposted URIs to prevent duplicates."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception as e:
                print(f"[Warning] Failed to load history file: {e}. Starting fresh.")
        return set()

    def _save_history(self):
        """Saves the updated list of reposted URIs to disk."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(list(self.reposted_uris), f, indent=2)
        except Exception as e:
            print(f"[Warning] Failed to save repost history: {e}")

    def login(self, handle: str, app_password: str) -> bool:
        """Authenticates with the PDS and retrieves a session JWT."""
        url = f"{self.pds_url}/xrpc/com.atproto.server.createSession"
        payload = {"identifier": handle, "password": app_password}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.access_jwt = data.get("accessJwt")
                self.did = data.get("did")
                print(f"🔑 Logged in successfully as @{handle}")
                return True
            else:
                print(f"❌ Login failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"❌ Error during login request: {e}")
        return False

    def repost(self, uri: str, cid: str) -> bool:
        """Sends the createRecord request to register a repost on the user's feed."""
        if not self.access_jwt or not self.did:
            print("[Error] No active session. Please call login() first.")
            return False

        url = f"{self.pds_url}/xrpc/com.atproto.repo.createRecord"
        headers = {
            "Authorization": f"Bearer {self.access_jwt}",
            "Content-Type": "application/json",
        }

        # Format timestamp to RFC 3339 format, utilizing Z instead of +00:00
        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        payload = {
            "repo": self.did,
            "collection": "app.bsky.feed.repost",
            "record": {
                "$type": "app.bsky.feed.repost",
                "subject": {"uri": uri, "cid": cid},
                "createdAt": now_str,
            },
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                return True
            else:
                print(f"[API Error] Failed to repost {uri}: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"[Network Error] Connection failed during repost: {e}")
        return False

    def process_queue(self, jsonl_file: str, min_delay: float = 5.0, max_delay: float = 15.0):
        """Reads JSONL output and reposts matching, underperforming rescue posts with randomized delays."""
        if not os.path.exists(jsonl_file):
            print(f"[Error] Source file not found: {jsonl_file}")
            return

        target_categories = {"Needs Foster", "Needs Shelter Pull", "Needs Donations"}
        actions_taken = 0

        print(f"📖 Scanning {jsonl_file} for actionable posts...")

        with open(jsonl_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        for index, line in enumerate(lines):
            if not line.strip():
                continue

            try:
                post = json.loads(line)
            except Exception as e:
                print(f"[Warning] Skipped malformed JSON line: {e}")
                continue

            category = post.get("category")
            is_repost = post.get("is_repost", False)
            uri = post.get("uri")
            cid = post.get("cid")
            post_url = post.get("post_url", "Unknown Link")

            # Validation checks
            if not uri or not cid:
                continue

            if category not in target_categories:
                continue

            if is_repost:
                continue

            if uri in self.reposted_uris:
                continue

            print(f"\n📢 Found actionable post: [{category}] - {post_url}")

            # Perform the repost
            success = self.repost(uri, cid)
            if success:
                print(f"✅ Reposted successfully!")
                self.reposted_uris.add(uri)
                actions_taken += 1

                # Only delay if there are potentially more lines left to check in the file
                if index < total_lines - 1:
                    sleep_time = random.uniform(min_delay, max_delay)
                    print(f"⏳ Sleeping for {sleep_time:.2f} seconds to mimic human pacing...")
                    time.sleep(sleep_time)

        if actions_taken > 0:
            self._save_history()
            print(f"\n🎉 Finished! Made {actions_taken} new reposts.")
        else:
            print("\n☕ No new, matching posts found to repost.")


# --- Execution Sandbox ---
if __name__ == "__main__":
    BOT_HANDLE = os.environ.get("BLUESKY_BOT_HANDLE")
    BOT_APP_PASSWORD = os.environ.get("BLUESKY_BOT_PASSWORD")
    INPUT_FILE = "flagged_posts.jsonl"

    if not BOT_HANDLE or not BOT_APP_PASSWORD:
        print("[Error] Missing environment variables. Please configure:")
        print("export BLUESKY_BOT_HANDLE='your-bot.bsky.social'")
        print("export BLUESKY_BOT_PASSWORD='your-app-specific-password'")
    else:
        reposter = BlueskyReposter()

        # Log in, then process the file with a random delay between 5.0 and 15.0 seconds
        if reposter.login(BOT_HANDLE, BOT_APP_PASSWORD):
            reposter.process_queue(INPUT_FILE, min_delay=5.0, max_delay=15.0)
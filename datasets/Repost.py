from datetime import datetime, timezone, timedelta
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

    def process_queue(
        self,
        jsonl_file: str,
        min_delay: float = 5.0,
        max_delay: float = 15.0,
        min_age_days: float = None,
        max_age_days: float = None
    ):
        """Reads JSONL output and reposts matching, underperforming rescue posts with age filtering and randomized delays."""
        if not os.path.exists(jsonl_file):
            print(f"[Error] Source file not found: {jsonl_file}")
            return

        target_categories = {"Needs Foster", "Needs Shelter Pull", "Needs Donations"}
        actions_taken = 0
        now = datetime.now(timezone.utc)

        # Build dynamic time limits for age filtering if defined
        min_cutoff = timedelta(days=min_age_days) if min_age_days is not None else None
        max_cutoff = timedelta(days=max_age_days) if max_age_days is not None else None

        # Print out the current target window configuration
        age_info = []
        if min_age_days is not None:
            age_info.append(f"at least {min_age_days} days old")
        if max_age_days is not None:
            age_info.append(f"at most {max_age_days} days old")
        window_str = f" ({' and '.join(age_info)})" if age_info else ""

        print(f"📖 Scanning {jsonl_file} for actionable posts{window_str}...")

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

            # 1. Category and basic validation filters
            category = post.get("category")
            is_repost = post.get("is_repost", False)
            uri = post.get("uri")
            cid = post.get("cid")
            post_url = post.get("post_url", "Unknown Link")

            if not uri or not cid:
                continue

            if category not in target_categories:
                continue

            if is_repost:
                continue

            if uri in self.reposted_uris:
                continue

            # 2. Dynamic Age Window Filter
            # Fall back to 'posted_at' if 'indexedAt' isn't available
            timestamp_str = post.get("indexedAt") or post.get("posted_at")
            if timestamp_str:
                try:
                    post_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    post_age = now - post_time

                    if min_cutoff is not None and post_age < min_cutoff:
                        # Post is too new
                        continue
                    if max_cutoff is not None and post_age > max_cutoff:
                        # Post is too old
                        continue
                except Exception as e:
                    print(f"[Warning] Could not parse timestamp '{timestamp_str}': {e}. Skipping post.")
                    continue

            print(f"\n📢 Found actionable post: [{category}] - {post_url}")

            # 3. Perform the repost
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
    INPUT_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/07-16-2026/low-reposts-2.jsonl"

    if not BOT_HANDLE or not BOT_APP_PASSWORD:
        print("[Error] Missing environment variables. Please configure:")
        print("export BLUESKY_BOT_HANDLE='your-bot.bsky.social'")
        print("export BLUESKY_BOT_PASSWORD='your-app-specific-password'")
    else:
        reposter = BlueskyReposter()

        # Log in, then process the file with:
        # - Randomized delay between 5.0 and 15.0 seconds
        # - Only repost items that were posted between 3 and 5 days ago (supports float values like 3.5 too!)
        if reposter.login(BOT_HANDLE, BOT_APP_PASSWORD):
            reposter.process_queue(
                jsonl_file=INPUT_FILE,
                min_delay=5.0,
                max_delay=15.0,
                min_age_days=1.0,
                max_age_days=2.0
            )
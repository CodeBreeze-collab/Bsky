import json
import os
import time
import requests
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("purge_status.log"),
        logging.StreamHandler()
    ]
)


class BlueskyStablePurge:
    def __init__(self, handle, password, input_jsonl, state_file="processed_dids_ne.txt"):
        self.api_base_url = "https://bsky.social/xrpc"
        self.handle = handle
        self.password = password
        self.input_file = input_jsonl
        self.state_file = state_file
        self.batch_size = 10  # AT Protocol handles 10-25 writes per batch safely

    def get_processed_dids(self):
        """Loads already unfollowed DIDs from the state file."""
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                return set(line.strip() for line in f)
        return set()

    def mark_as_done(self, dids):
        """Appends finished DIDs to the state file immediately."""
        with open(self.state_file, 'a') as f:
            for did in dids:
                f.write(f"{did}\n")

    def _authenticate(self):
        """Creates a fresh session and returns headers + user DID."""
        try:
            res = requests.post(
                f"{self.api_base_url}/com.atproto.server.createSession",
                json={"identifier": self.handle, "password": self.password},
                timeout=20
            )
            res.raise_for_status()
            session = res.json()
            logging.info(f"🔑 Authenticated as {self.handle}")
            return {"Authorization": f"Bearer {session['accessJwt']}"}, session['did']
        except Exception as e:
            logging.error(f"❌ Auth Failed: {e}")
            return None, None

    def run(self):
        # 1. Auth
        headers, my_did = self._authenticate()
        if not headers:
            return

        # 2. Load and Filter Candidates
        processed_dids = self.get_processed_dids()
        candidates = []

        if not os.path.exists(self.input_file):
            logging.error(f"❌ Input file {self.input_file} not found.")
            return

        with open(self.input_file, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    did = item.get('did')
                    # We look for the URI we saved in the audit step
                    follow_uri = item.get('viewer', {}).get('following')

                    if did and did not in processed_dids and follow_uri:
                        candidates.append(item)
                except json.JSONDecodeError:
                    continue

        total = len(candidates)
        logging.info(f"📂 Found {total} users to unfollow (skipping {len(processed_dids)} already done).")

        # 3. Processing Loop
        for i in range(0, total, self.batch_size):
            # Refresh session every 500 operations to be safe
            if i > 0 and i % 500 == 0:
                headers, my_did = self._authenticate()

            batch = candidates[i:i + self.batch_size]
            writes = []
            batch_dids = []

            for user in batch:
                uri = user['viewer']['following']
                # URI Format: at://did:plc:xxx/app.bsky.graph.follow/rkey
                try:
                    parts = uri.replace("at://", "").split("/")
                    writes.append({
                        "$type": "com.atproto.repo.applyWrites#delete",
                        "collection": parts[1],
                        "rkey": parts[2]
                    })
                    batch_dids.append(user['did'])
                except IndexError:
                    logging.warning(f"⚠️ Malformed URI for {user.get('handle')}: {uri}")

            if not writes:
                continue

            try:
                # Use applyWrites for high-speed batch deletion
                res = requests.post(
                    f"{self.api_base_url}/com.atproto.repo.applyWrites",
                    json={"repo": my_did, "writes": writes},
                    headers=headers,
                    timeout=30
                )
                res.raise_for_status()

                logging.info(f"✅ [{min(i + self.batch_size, total)}/{total}] Successfully unfollowed batch.")

                # Checkpoint progress
                self.mark_as_done(batch_dids)

                # Gentle sleep to respect the server
                time.sleep(1.5)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logging.error("⏳ Rate limit hit. Sleeping 60s...")
                    time.sleep(60)
                else:
                    logging.error(f"⚠️ HTTP Error: {e}. Skipping batch.")
                    time.sleep(5)
            except Exception as e:
                logging.error(f"❌ Unexpected Error: {e}")
                time.sleep(10)

        logging.info("🏁 Purge complete.")


if __name__ == "__main__":
    # CONFIGURATION
    HANDLE = "westcoastnews.bsky.social"
    # Ensure this env var is set or replace with your password string
    PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD_west_coast_news")
    # Path to the results.jsonl we generated earlier
    INPUT_FILE = "westcoastnews_unrequitted.jsonl"

    if not PASSWORD:
        print("❌ Error: Set BLUESKY_APP_PASSWORD_ne_news environment variable.")
    else:
        purger = BlueskyStablePurge(HANDLE, PASSWORD, INPUT_FILE)
        purger.run()
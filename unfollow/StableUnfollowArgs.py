import json
import os
import time
import requests
import logging
import argparse

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
        self.batch_size = 10

    def get_processed_dids(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                return set(line.strip() for line in f)
        return set()

    def mark_as_done(self, dids):
        with open(self.state_file, 'a') as f:
            for did in dids:
                f.write(f"{did}\n")

    def _authenticate(self):
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
        headers, my_did = self._authenticate()
        if not headers:
            return

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
                    follow_uri = item.get('viewer', {}).get('following')

                    if did and did not in processed_dids and follow_uri:
                        candidates.append(item)
                except json.JSONDecodeError:
                    continue

        total = len(candidates)
        logging.info(f"📂 Found {total} users to unfollow (skipping {len(processed_dids)} already done).")

        for i in range(0, total, self.batch_size):
            if i > 0 and i % 500 == 0:
                headers, my_did = self._authenticate()

            batch = candidates[i:i + self.batch_size]
            writes = []
            batch_dids = []

            for user in batch:
                uri = user['viewer']['following']
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
                res = requests.post(
                    f"{self.api_base_url}/com.atproto.repo.applyWrites",
                    json={"repo": my_did, "writes": writes},
                    headers=headers,
                    timeout=30
                )
                res.raise_for_status()

                logging.info(f"✅ [{min(i + self.batch_size, total)}/{total}] Successfully unfollowed batch.")
                self.mark_as_done(batch_dids)
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
    parser = argparse.ArgumentParser(description="Purge Bluesky follows based on a JSONL input file.")

    # Define Arguments
    parser.add_argument("--handle", required=True, help="Your Bluesky handle (e.g., user.bsky.social)")
    parser.add_argument("--password", help="Bluesky App Password. If not provided, will check environment variable.")
    parser.add_argument("--input", required=True, help="Path to the .jsonl file containing users to unfollow.")
    parser.add_argument("--state", default="processed_dids.txt", help="File to store/track processed DIDs.")
    parser.add_argument("--env-var", default="BLUESKY_APP_PASSWORD",
                        help="Name of the environment variable for the password (fallback).")

    args = parser.parse_args()

    # Password Logic: CLI Arg > Env Var
    password = args.password or os.environ.get(args.env_var)

    if not password:
        logging.error(
            f"❌ Error: Password not provided via --password and {args.env_var} environment variable is not set.")
    else:
        purger = BlueskyStablePurge(args.handle, password, args.input, args.state)
        purger.run()
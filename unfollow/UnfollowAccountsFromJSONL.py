import json
import os
import time
import requests
import logging
import argparse
import getpass
import random
from datetime import datetime


class BlueskyStablePurge:
    def __init__(self, handle, password, input_jsonl, delay, state_file, limit=None):
        self.api_base_url = "https://bsky.social/xrpc"
        self.handle = handle
        self.password = password
        self.input_file = input_jsonl
        self.state_file = state_file
        self.delay = delay
        self.limit = limit
        # Use a Session to reuse TCP connections and prevent 'Connection reset by peer'
        self.session = requests.Session()

    def get_processed_dids(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                dids = set(line.strip() for line in f)
                logging.info(f"📁 [{self.handle}] Loaded {len(dids)} processed DIDs from {self.state_file}")
                return dids
        return set()

    def mark_as_done(self, dids):
        with open(self.state_file, 'a') as f:
            for did in dids:
                f.write(f"{did}\n")

    def _authenticate(self):
        try:
            res = self.session.post(
                f"{self.api_base_url}/com.atproto.server.createSession",
                json={"identifier": self.handle, "password": self.password},
                timeout=20
            )
            res.raise_for_status()
            session = res.json()
            # Update session headers for all subsequent requests
            self.session.headers.update({"Authorization": f"Bearer {session['accessJwt']}"})
            return session['did']
        except Exception as e:
            logging.error(f"❌ [{self.handle}] Auth Failed: {e}")
            return None

    def run(self):
        my_did = self._authenticate()
        if not my_did: return

        processed_dids = self.get_processed_dids()
        candidates = []

        with open(self.input_file, 'r') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    item = json.loads(line)
                    did = item.get('target_did') or item.get('did')
                    if did:
                        item['target_did'] = did

                    if did and did not in processed_dids:
                        candidates.append(item)
                except:
                    continue

        if self.limit:
            candidates = candidates[:self.limit]
            logging.info(f"🛑 [{self.handle}] Limit set: Processing only up to {self.limit} users.")

        total = len(candidates)
        logging.info(f"📊 [{self.handle}] Found {total} users left to unfollow.")

        for i, candidate in enumerate(candidates):
            target_did = candidate['target_did']
            logging.info(f"✅ [{self.handle}] [{i + 1}/{total}] Unfollowing {target_did}")

            jitter_range = 0.20
            if i > 0:
                time.sleep(self.delay * random.uniform(1 - jitter_range, 1 + jitter_range))

            if i > 0 and i % 500 == 0:
                self._authenticate()

            try:
                # 🛠️ OPTIMIZATION: Check if Script 1 already cached the following URI string
                following_uri = candidate.get('viewer', {}).get('following')

                if not following_uri:
                    # Safe Fallback: If it's missing from the file cache, pull it from the API live
                    logging.info(f"🔍 URI not in cache for {target_did}. Fetching relationship live...")
                    rel_res = self.session.get(
                        f"{self.api_base_url}/app.bsky.graph.getRelationships",
                        params={"actor": my_did, "others": target_did},
                        timeout=30
                    )
                    rel_res.raise_for_status()

                    rels = rel_res.json().get('relationships', [])
                    following_uri = rels[0].get('following') if rels else None

                if following_uri:
                    uri_parts = following_uri.replace("at://", "").split("/")

                    self.session.post(
                        f"{self.api_base_url}/com.atproto.repo.applyWrites",
                        json={
                            "repo": my_did,
                            "writes": [{"$type": "com.atproto.repo.applyWrites#delete",
                                        "collection": uri_parts[1], "rkey": uri_parts[2]}]
                        },
                        timeout=30
                    ).raise_for_status()
                    logging.info(f"✅ [{self.handle}] [{i + 1}/{total}] Unfollowed {target_did}")
                else:
                    logging.warning(f"⚠️ [{self.handle}] Could not find an active follow relationship for {target_did}. Skipping.")

                self.mark_as_done([target_did])

            except requests.exceptions.HTTPError as e:
                code = e.response.status_code
                if code in [502, 503, 504]:
                    logging.warning(f"⚠️ [{self.handle}] Server {code}. Sleeping 60s...")
                    time.sleep(60)
                else:
                    logging.error(f"❌ [{self.handle}] HTTP Error {code}: {e}")
                    time.sleep(10)
            except Exception as e:
                logging.error(f"❌ [{self.handle}] Unexpected: {e}")
                time.sleep(10)

        logging.info(f"🏁 [{self.handle}] Finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bluesky Purge Tool")
    parser.add_argument("--handle", required=True, help="Bluesky handle")
    parser.add_argument("--password", "--api-key", help="Bluesky App Password/API Key")
    parser.add_argument("--input", required=True, help="Input JSONL file")
    parser.add_argument("--state-file", required=True, help="Unique text file to track progress for this handle")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests")
    parser.add_argument("--limit", type=int, default=None, help="Max accounts to unfollow")
    parser.add_argument("--log-file", help="Custom path for the log file (optional)")

    args = parser.parse_args()

    # Generate a unique timestamp for this specific execution run
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Determine the log file path dynamically
    if args.log_file:
        # Splits the extension so we inject the timestamp cleanly (e.g., path/to/file_20260615_132441.log)
        base, ext = os.path.splitext(args.log_file)
        log_path = f"{base}_{run_timestamp}{ext}"
    else:
        # Defaults to 'purge_user_bsky_social_20260615_132441.log'
        safe_handle = args.handle.replace('.', '_')
        log_path = f"purge_{safe_handle}_{run_timestamp}.log"

    abs_log_path = os.path.abspath(log_path)

    # 2. Print the path immediately when the script starts
    print(f"🚀 Script starting. Output logs are being written to:\n📂 {abs_log_path}\n" + "-" * 60)

    # 3. Configure logging with both StreamHandler (console) and FileHandler (file)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(abs_log_path, encoding='utf-8')
        ]
    )

    pwd = args.password or getpass.getpass("Enter App Password: ")

    BlueskyStablePurge(
        handle=args.handle,
        password=pwd,
        input_jsonl=args.input,
        delay=args.delay,
        state_file=args.state_file,
        limit=args.limit
    ).run()
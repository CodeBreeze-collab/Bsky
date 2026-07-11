import json
import requests
import time
import os
from datetime import datetime, timedelta, timezone

# Configuration
BASE_PATH = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/'
INPUT_FILE = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/auto_follow_logs/texas_news_auto_follow_log.jsonl'
OUTPUT_FILE = f"{BASE_PATH}bsky/v2/unfollow/unfollow-jsonl/unfollow-parallel/"


class HighScaleRelationshipFilter:
    def __init__(self, operator_handle, app_password):
        self.api_base_url = "https://bsky.social/xrpc"
        self.operator_handle = operator_handle
        self.password = app_password
        self.headers = self._authenticate()

    def _authenticate(self):
        print(f"🔐 Authenticating as {self.operator_handle}...")
        res = requests.post(f"{self.api_base_url}/com.atproto.server.createSession",
                            json={"identifier": self.operator_handle, "password": self.password})
        res.raise_for_status()
        return {"Authorization": f"Bearer {res.json()['accessJwt']}"}

    def process_batch(self, batch, subject_handle, outfile):
        """
        Checks relationships and identifies users who the subject follows,
        but who do not follow the subject back.
        """
        try:
            # Map DIDs to their original data objects for easy lookup
            batch_map = {item['target_did']: item for item in batch}
            dids = list(batch_map.keys())

            params = {"actor": subject_handle, "others": dids}

            r = requests.get(
                f"{self.api_base_url}/app.bsky.graph.getRelationships",
                headers=self.headers,
                params=params
            )
            r.raise_for_status()

            relationships = r.json().get("relationships", [])

            # Logic Filter:
            # 1. 'following' is NOT None -> Subject is currently following them.
            # 2. 'followedBy' IS None    -> They are NOT following the subject back.
            targets_to_purge = [
                rel['did'] for rel in relationships
                if rel.get('following') is not None and rel.get('followedBy') is None
            ]

            count = 0
            for did in targets_to_purge:
                if did in batch_map:
                    outfile.write(json.dumps(batch_map[did]) + '\n')
                    count += 1

            return count

        except Exception as e:
            print(f"⚠️ Batch error: {e}")
            return 0

    def run(self, subject_handle, min_days=15, max_days=30):
        """
        Filters for accounts followed within a specific window:
        Older than min_days (e.g., 15) but newer than max_days (e.g., 30).
        """
        # "Newest" boundary (e.g., 15 days ago)
        upper_cutoff = datetime.now(timezone.utc) - timedelta(days=min_days)
        # "Oldest" boundary (e.g., 30 days ago)
        lower_cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

        batch = []
        total_found = 0
        lines_checked = 0

        print(f"🚀 Scanning {INPUT_FILE}")
        print(f"📅 Target Window: Between {max_days} and {min_days} days ago.")

        with open(INPUT_FILE, 'r') as infile, open(OUTPUT_FILE, 'w') as outfile:
            for line in infile:
                if not line.strip(): continue
                lines_checked += 1

                try:
                    data = json.loads(line)
                    log_date = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))

                    # CHECK: Is the follow date between the 30-day and 15-day marks?
                    if lower_cutoff < log_date < upper_cutoff:
                        batch.append(data)

                    # Process in batches of 30 (Bluesky API limit for getRelationships)
                    if len(batch) == 30:
                        total_found += self.process_batch(batch, subject_handle, outfile)
                        batch = []
                        print(f"📡 Progress: Checked {lines_checked} lines... Found {total_found} targets so far.")
                        time.sleep(0.4)

                except Exception:
                    continue

                    # Process any remaining items that didn't fill a final batch of 30
            if batch:
                total_found += self.process_batch(batch, subject_handle, outfile)

        print(f"---")
        print(f"✅ Finished!")
        print(f"📂 Purge list saved to: {OUTPUT_FILE}")
        print(f"👤 Total non-followers identified: {total_found}")


def fetch_existing_blocks(client):
    cursor = None
    blocked = set()

    while True:
        resp = client.app.bsky.graph.get_blocks(
            {"limit": 100, "cursor": cursor} if cursor else {"limit": 100}
        )

        for b in (resp.blocks or []):
            blocked.add(b.did)

        cursor = resp.cursor
        if not cursor:
            break

    return blocked




if __name__ == "__main__":
    # Credentials - Ensure BLUESKY_APP_PASSWORD is set in your environment
    OPERATOR_H = "ethicalsearch.bsky.social"
    OPERATOR_P = os.environ.get("BLUESKY_APP_PASSWORD")
    SUBJECT_H = "texastopnews.bsky.social"

    if not OPERATOR_P:
        print("❌ Error: BLUESKY_APP_PASSWORD environment variable not found.")
    else:
        worker = HighScaleRelationshipFilter(OPERATOR_H, OPERATOR_P)
        # To get accounts followed > 15 days ago but < 30 days ago:
        worker.run(SUBJECT_H, min_days=7, max_days=180)
import json
import requests
import time
import os
import argparse


class BlueskyManager:
    def __init__(self, handle, password):
        self.api_base_url = "https://bsky.social/xrpc"
        self.session = requests.Session()
        self.auth_data = self._authenticate(handle, password)
        self.session.headers.update({"Authorization": f"Bearer {self.auth_data['accessJwt']}"})
        self.my_did = self.auth_data['did']

    def _authenticate(self, handle, password):
        res = self.session.post(
            f"{self.api_base_url}/com.atproto.server.createSession",
            json={"identifier": handle, "password": password}
        )
        res.raise_for_status()
        return res.json()

    def _handle_rate_limit(self, response):
        if response.status_code == 429:
            reset_time = response.headers.get("ratelimit-reset")
            wait_time = max(int(reset_time) - int(time.time()), 5) if reset_time else 60
            print(f"\n⏳ Rate limit hit. Sleeping {wait_time}s...")
            time.sleep(wait_time + 1)
            return True
        return False

    def get_all_following(self, actor, skip_fetch=False):
        cache_file = f"follows_cache_{actor}.jsonl"
        cursor_file = f"cursor_{actor}.txt"
        follows = []

        # Always try to load existing cache first
        if os.path.exists(cache_file):
            print(f"📦 Loading follows from cache: {cache_file}")
            with open(cache_file, 'r') as f:
                for line in f:
                    follows.append(json.loads(line))
            print(f"✅ Loaded {len(follows)} accounts.")

        if skip_fetch:
            print("⏭️ --skip-fetch active. Proceeding with current cache.")
            return follows

        # Check if we already finished previously
        if os.path.exists(cursor_file):
            with open(cursor_file, 'r') as f:
                if f.read().strip() == "DONE":
                    print("✨ Follow list is already fully cached.")
                    return follows

        # If not skipping and not done, fetch the rest
        print(f"🔍 Fetching/Resuming follows for {actor}...")
        cursor = None
        if os.path.exists(cursor_file):
            with open(cursor_file, 'r') as f:
                cursor = f.read().strip()

        with open(cache_file, 'a') as f_cache, open(cursor_file, 'w') as f_cursor:
            while True:
                params = {"actor": actor, "limit": 100}
                if cursor: params["cursor"] = cursor
                try:
                    r = self.session.get(f"{self.api_base_url}/app.bsky.graph.getFollows", params=params)
                    if self._handle_rate_limit(r): continue
                    r.raise_for_status()

                    data = r.json()
                    batch = data.get("follows", [])
                    for user in batch:
                        f_cache.write(json.dumps(user) + '\n')

                    follows.extend(batch)
                    cursor = data.get("cursor")

                    if not cursor:
                        f_cursor.seek(0);
                        f_cursor.write("DONE");
                        f_cursor.truncate()
                        break

                    f_cursor.seek(0);
                    f_cursor.write(cursor);
                    f_cursor.truncate();
                    f_cursor.flush()
                    print(f"📑 Total retrieved: {len(follows)}...", end='\r')
                    time.sleep(0.1)
                except Exception as e:
                    print(f"\n⚠️ Fetch error: {e}. Retrying in 10s...");
                    time.sleep(10)

        return follows

    def run_audit(self, subject_handle, output_file, skip_fetch=False):
        all_following = self.get_all_following(subject_handle, skip_fetch=skip_fetch)
        total = len(all_following)

        processed_dids = set()
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    try:
                        processed_dids.add(json.loads(line)['did'])
                    except:
                        continue

        print(f"📡 Auditing {total} relationships for {subject_handle}...")

        with open(output_file, 'a') as f:
            i = 0
            while i < total:
                batch = all_following[i:i + 30]
                batch_to_query = [u for u in batch if u['did'] not in processed_dids]

                if not batch_to_query:
                    i += 30
                    continue

                user_map = {u['did']: u for u in batch_to_query}
                dids = list(user_map.keys())

                try:
                    r = self.session.get(
                        f"{self.api_base_url}/app.bsky.graph.getRelationships",
                        params={"actor": subject_handle, "others": dids}
                    )
                    if self._handle_rate_limit(r): continue
                    r.raise_for_status()

                    relationships = r.json().get("relationships", [])
                    for rel in relationships:
                        did = rel.get('did')
                        # Capture "following" (the URI needed for deleteRecord)
                        if rel.get('following') and not rel.get('followedBy'):
                            user_data = user_map[did]
                            # Inject the follow record URI into the results!
                            user_data['viewer'] = {'following': rel['following']}
                            f.write(json.dumps(user_data) + '\n')
                            f.flush()

                    i += 30
                    print(f"⏳ Progress: {min(i, total)}/{total} analyzed...", end='\r')
                    time.sleep(0.3)

                except Exception as e:
                    print(f"\n⚠️ Audit error: {e}. Retrying...");
                    time.sleep(5)

        print(f"\n\n✅ Done! Non-followers with URIs saved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--handle", required=True, help="Your handle")
    parser.add_argument("--subject", required=True, help="Handle to audit (likely yours)")
    parser.add_argument("--output", default="results.jsonl", help="Where to save non-followers")
    parser.add_argument("--skip-fetch", action="store_true", help="Use local cache instead of API for following list")

    args = parser.parse_args()
    PWD = os.environ.get("BLUESKY_APP_PASSWORD")

    if not PWD:
        print("❌ Error: Set BLUESKY_APP_PASSWORD environment variable.")
    else:
        app = BlueskyManager(args.handle, PWD)
        app.run_audit(args.subject, args.output, skip_fetch=args.skip_fetch)
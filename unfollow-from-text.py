import requests, json, time, os, logging, re, random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyUnfollowForce:
    def __init__(self, handle, app_password_env, input_file):
        self.api_base_url = "https://bsky.social/xrpc"
        self.handle = handle
        self.password = os.environ.get(app_password_env)
        self.input_file = input_file

    def run(self):
        # 1. Auth
        res = requests.post(f"{self.api_base_url}/com.atproto.server.createSession",
                            json={"identifier": self.handle, "password": self.password})
        res.raise_for_status()
        session = res.json()
        token, my_did = session['accessJwt'], session['did']
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Parse Handles with heavy cleaning
        target_handles = set()
        with open(self.input_file, 'r') as f:
            for line in f:
                # Find anything that looks like a handle, then strip common log-file debris
                matches = re.findall(r'([\w\.-]+\.[a-z]+)', line.lower())
                for m in matches:
                    clean = m.strip().strip('.').strip(':')
                    if clean and not clean.startswith('did:'):
                        target_handles.add(clean)

        logging.info(f"📂 Loaded {len(target_handles)} unique handles to target.")
        # Debug: Show the first 3 handles to ensure they look right
        logging.info(f"Sample targets: {list(target_handles)[:3]}")

        # 3. Match against your Following list
        follow_map = {}
        cursor = None
        total_checked = 0

        logging.info("📡 Scanning your following list for matches...")
        while True:
            params = {"actor": my_did, "limit": 100}
            if cursor: params["cursor"] = cursor
            r = requests.get(f"{self.api_base_url}/app.bsky.graph.getFollows", headers=headers, params=params)
            data = r.json()

            follows = data.get("follows", [])
            total_checked += len(follows)

            for f in follows:
                h = f['handle'].lower()
                if h in target_handles:
                    follow_map[h] = f.get("viewer", {}).get("following")

            logging.info(f"🔎 Scanned {total_checked} followers... Matches found so far: {len(follow_map)}")

            cursor = data.get("cursor")
            if not cursor or not follows: break

        # 4. Execution
        if not follow_map:
            logging.error("❌ No matches found! Check if the handles in the text file match your 'Following' list.")
            return

        logging.info(f"🚀 Starting unfollow of {len(follow_map)} users...")
        for handle, uri in follow_map.items():
            if not uri: continue

            p = uri.replace("at://", "").split("/")
            requests.post(f"{self.api_base_url}/com.atproto.repo.deleteRecord",
                          json={"repo": my_did, "collection": p[1], "rkey": p[2]}, headers=headers)

            logging.info(f"✅ Unfollowed: {handle}")
            time.sleep(random.uniform(1.5, 3.0))


if __name__ == "__main__":
    # Settings
    H = "newenglandtopnews.bsky.social"
    P = "BLUESKY_APP_PASSWORD"
    F = "/Users/hdon/Desktop/unfollow-n.txt"

    BlueskyUnfollowForce(H, P, F).run()
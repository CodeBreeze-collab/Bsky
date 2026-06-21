import os
import requests
import time
from datetime import datetime, timezone
from typing import Optional


class BlueskyDualHandleChecker:
    API_BASE_URL = "https://bsky.social/xrpc"

    def __init__(self, follower_handle, follower_pwd, checker_handle, checker_pwd):
        # Handle A: The one who actually follows people
        self.follower_handle = follower_handle.lower().lstrip('@')
        self.follower_pwd = follower_pwd
        self.follower_token = None
        self.follower_did = None
        self.follow_map = {}

        # Handle B: The one who checks the feeds
        self.checker_handle = checker_handle.lower().lstrip('@')
        self.checker_pwd = checker_pwd
        self.checker_token = None

        self._authenticate()
        self._map_follower_list()

    def _authenticate(self):
        # Auth Handle A
        res_a = requests.post(f"{self.API_BASE_URL}/com.atproto.server.createSession",
                              json={"identifier": self.follower_handle, "password": self.follower_pwd})
        res_a.raise_for_status()
        data_a = res_a.json()
        self.follower_token = data_a["accessJwt"]
        self.follower_did = data_a["did"]
        print(f"✅ Authenticated Handle A: {self.follower_handle}")

        # Auth Handle B
        res_b = requests.post(f"{self.API_BASE_URL}/com.atproto.server.createSession",
                              json={"identifier": self.checker_handle, "password": self.checker_pwd})
        res_b.raise_for_status()
        self.checker_token = res_b.json()["accessJwt"]
        print(f"✅ Authenticated Handle B: {self.checker_handle}")

    def _map_follower_list(self):
        """Handle A's follows are indexed to get the URIs needed for unfollowing."""
        print(f"📥 Indexing follows for {self.follower_handle}...")
        headers = {"Authorization": f"Bearer {self.follower_token}"}
        url = f"{self.API_BASE_URL}/app.bsky.graph.getFollows"
        params = {"actor": self.follower_did, "limit": 100}
        cursor = None
        while True:
            if cursor: params["cursor"] = cursor
            res = requests.get(url, headers=headers, params=params)
            data = res.json()
            for f in data.get("follows", []):
                handle = f["handle"].lower()
                uri = f.get("viewer", {}).get("following")
                if uri: self.follow_map[handle] = uri
            cursor = data.get("cursor")
            if not cursor: break
        print(f"✨ Found {len(self.follow_map)} follows on Handle A.")

    def _get_activity_with_handle_b(self, target_handle: str) -> Optional[int]:
        """Uses Handle B's token to check the activity feed."""
        headers = {"Authorization": f"Bearer {self.checker_token}"}
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        try:
            res = requests.get(url, headers=headers, params={"actor": target_handle, "limit": 1})
            feed = res.json().get("feed", [])
            if not feed: return None

            last_ts = feed[0]["post"]["indexedAt"]
            last_dt = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - last_dt).days
        except:
            return -1

    def analyze_file(self, file_path: str):
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tsv_name = f"activity_report_{run_ts}.tsv"

        with open(file_path, "r") as f:
            handles = [line.strip().lstrip('@').lower() for line in f if line.strip() and not line.startswith("-")]

        with open(tsv_name, "w") as tsv:
            tsv.write("handle\tnumber_of_days\tfollow_uri\n")
            for h in handles:
                if len(h) < 5: continue

                days = self._get_activity_with_handle_b(h)
                uri = self.follow_map.get(h, "None")

                print(
                    f"🔍 {h:<30} | {days if days is not None else 'None':<4} days | URI: {'Yes' if uri != 'None' else 'No'}")
                tsv.write(f"{h}\t{days}\t{uri}\n")
                time.sleep(0.3)


if __name__ == "__main__":
    # HANDLE A (The Follower)
    H_A = "vegansearchengine.bsky.social"
    P_A = os.environ.get("BSKY_PWD_VEGAN")
    # HANDLE B (The Checker)
    H_B = "ethicalsearch.bsky.social"
    P_B = os.environ.get("BSKY_PWD_ETHICAL")

    INPUT = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/unrecognized_follows_20251219_131402.txt"

    checker = BlueskyDualHandleChecker(H_A, P_A, H_B, P_B)
    checker.analyze_file(INPUT)
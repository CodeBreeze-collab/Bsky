import requests
import logging
import time
import os
import json
from typing import List, Optional, Set

# --- LOGGING CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyUnfollowTool:
    def __init__(self, handle: str, app_password_env: str, log_file: str = "unfollowed_users.jsonl"):
        self.api_base_url = "https://bsky.social/xrpc"
        self.handle = handle
        self.password = os.environ.get(app_password_env)
        self.log_file = log_file
        self.checkpoint_file = "unfollow_progress.json"

        if not self.password:
            raise ValueError(f"Environment variable {app_password_env} not set.")

        self.token = None
        self.my_did = None

    def authenticate(self) -> bool:
        url = f"{self.api_base_url}/com.atproto.server.createSession"
        try:
            res = requests.post(url, json={"identifier": self.handle, "password": self.password})
            res.raise_for_status()
            data = res.json()
            self.token = data.get("accessJwt")
            self.my_did = data.get("did")
            return True
        except Exception as e:
            logging.error(f"Auth failed: {e}")
            return False

    def _load_checkpoint(self) -> dict:
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, 'r') as f:
                return json.load(f)
        return {"processed_dids": [], "target_queue": []}

    def _save_checkpoint(self, processed_dids: List[str], target_queue: List[dict]):
        with open(self.checkpoint_file, 'w') as f:
            json.dump({"processed_dids": processed_dids, "target_queue": target_queue}, f)

    def get_my_followers(self) -> Set[str]:
        followers = set()
        cursor = None
        while True:
            params = {"actor": self.my_did, "limit": 100}
            if cursor: params["cursor"] = cursor
            res = requests.get(f"{self.api_base_url}/app.bsky.graph.getFollowers",
                               headers={"Authorization": f"Bearer {self.token}"}, params=params)
            data = res.json()
            for f in data.get("followers", []):
                followers.add(f["did"])
            cursor = data.get("cursor")
            if not cursor: break
        return followers

    def get_my_following(self) -> List[dict]:
        following = []
        cursor = None
        while True:
            params = {"actor": self.my_did, "limit": 100}
            if cursor: params["cursor"] = cursor
            res = requests.get(f"{self.api_base_url}/app.bsky.graph.getFollows",
                               headers={"Authorization": f"Bearer {self.token}"}, params=params)
            data = res.json()
            for f in data.get("follows", []):
                following.append({
                    "did": f["did"],
                    "handle": f["handle"],
                    "uri": f.get("viewer", {}).get("following")
                })
            cursor = data.get("cursor")
            if not cursor: break
        return following

    def unfollow_user(self, follow_record_uri: str) -> bool:
        try:
            parts = follow_record_uri.replace("at://", "").split("/")
            url = f"{self.api_base_url}/com.atproto.repo.deleteRecord"
            payload = {"repo": self.my_did, "collection": parts[1], "rkey": parts[2]}
            res = requests.post(url, json=payload, headers={"Authorization": f"Bearer {self.token}"})
            return res.status_code == 200
        except:
            return False

    def run_cleanup(self, follower_threshold: int = 10000, dry_run: bool = True):
        if not self.authenticate(): return

        state = self._load_checkpoint()
        processed_dids = set(state["processed_dids"])

        # Only build queue if it's empty (New run or previous run finished)
        if not state["target_queue"]:
            logging.info("Refreshing following/followers lists...")
            my_followers = self.get_my_followers()
            all_following = self.get_my_following()

            # Step 1: Filter non-followers
            not_following_back = [u for u in all_following if u["did"] not in my_followers]

            # Step 2: Batch check profile stats
            logging.info(f"Checking follower counts for {len(not_following_back)} users...")
            for i in range(0, len(not_following_back), 25):
                batch = not_following_back[i:i + 25]
                res = requests.get(f"{self.api_base_url}/app.bsky.actor.getProfiles",
                                   headers={"Authorization": f"Bearer {self.token}"},
                                   params={"actors": [u["did"] for u in batch]})

                for p in res.json().get("profiles", []):
                    if p.get("followersCount", 0) < follower_threshold:
                        original = next(u for u in batch if u["did"] == p["did"])
                        state["target_queue"].append({
                            "did": p["did"],
                            "handle": p["handle"],
                            "uri": original["uri"],
                            "followersCount": p.get("followersCount", 0)
                        })
                time.sleep(0.5)
            self._save_checkpoint(list(processed_dids), state["target_queue"])

        # Step 3: Execution Logic
        queue = state["target_queue"]
        logging.info(f"Queue size: {len(queue)} targets.")

        for user in list(queue):
            if user["did"] in processed_dids:
                queue.remove(user)
                continue

            if dry_run:
                logging.info(f"[DRY RUN] Would unfollow {user['handle']} ({user['followersCount']} followers)")
                processed_dids.add(user["did"])
            else:
                if self.unfollow_user(user["uri"]):
                    logging.info(f"✅ Unfollowed {user['handle']}")
                    # Log to JSONL
                    with open(self.log_file, "a") as f:
                        f.write(json.dumps({
                            "did": user["did"],
                            "handle": user["handle"],
                            "follower_count": user["followersCount"],
                            "timestamp": time.time()
                        }) + "\n")

                    processed_dids.add(user["did"])
                    queue.remove(user)
                    # Save progress every successful action
                    self._save_checkpoint(list(processed_dids), queue)
                    time.sleep(0.5)
                else:
                    logging.error(f"❌ Failed to unfollow {user['handle']}, skipping for now.")

        # Cleanup checkpoint if finished
        if not queue:
            if os.path.exists(self.checkpoint_file):
                os.remove(self.checkpoint_file)
            logging.info("✨ Cleanup complete. Checkpoint cleared.")


if __name__ == "__main__":
    # CONFIGURATION
    HANDLE = "vegansearchengine.bsky.social"
    ENV_VAR = "BLUESKY_APP_PASSWORD"

    tool = BlueskyUnfollowTool(HANDLE, ENV_VAR)
    tool.run_cleanup(follower_threshold=10000, dry_run=True)
import requests
import json
import time
import logging
import os
import sys
import argparse
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

# --- CONSTANTS ---
CONFIG_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/all-in-one-configs/"

# --- LOGGING CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyFollowTool:
    def __init__(self, config: dict, env_override: Optional[str] = None):
        api_config = config.get("api", {})
        self.api_base_url = api_config.get("base_url", "https://bsky.social/xrpc")

        tool_config = config.get("tool", {})
        self.pagination_delay = tool_config.get("pagination_delay", 0.6)
        self.max_profiles_per_batch = tool_config.get("max_profiles_per_batch", 25)
        self.heartbeat_interval_minutes = tool_config.get("heartbeat_interval_minutes", 5)

        env_var_name = env_override or config["app_password_env_var"]

        self.handle = config["my_handle"]
        self.password = os.environ.get(env_var_name)

        # --- DEBUG LOGGING ---
        logging.info(f"Using handle: {self.handle}")
        logging.info(f"Password env var: {env_var_name} {'FOUND' if self.password else 'NOT FOUND'}")

        if not self.password:
            raise ValueError(f"Environment variable '{env_var_name}' not set or empty.")

        self.dry_run_log_file = config["files"]["dry_run_log_file"]
        self.cursor_file = config["files"]["cursor_file"]
        self.auto_follow_log = config["files"]["auto_follow_log"]

        self.token = None
        self.my_did = None
        self.last_heartbeat = time.time()

        self.processed_dids: Set[str] = self._load_processed_history()
        self.already_followed_dids: Set[str] = self._load_auto_follow_history()

        logging.info(
            f"Loaded {len(self.processed_dids)} processed and {len(self.already_followed_dids)} followed from history."
        )

    def _get_session(self) -> bool:
        url = f"{self.api_base_url}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}

        logging.info(f"Authenticating as {self.handle}...pass: {self.password}")
        logging.debug(f"Auth POST payload keys: {list(payload.keys())}")  # Never log actual password
        logging.debug(f"Auth URL: {url}")

        try:
            res = requests.post(url, json=payload)
            logging.debug(f"Status: {res.status_code}, headers: {res.headers}, text: {res.text}")
            res.raise_for_status()
            data = res.json()
            self.token = data.get("accessJwt")
            self.my_did = data.get("did")
            logging.info(f"✅ Auth successful for {self.handle}. DID: {self.my_did}")
            return True
        except requests.HTTPError as e:
            logging.error(f"❌ Auth Error: {e} | Response: {e.response.text if e.response else 'No response'}")
            return False
        except Exception as e:
            logging.error(f"❌ Unexpected Auth Error: {e}")
            return False

    def resolve_handle(self, handle: str) -> Optional[str]:
        url = f"{self.api_base_url}/com.atproto.identity.resolveHandle"
        try:
            res = requests.get(url, params={"handle": handle})
            res.raise_for_status()
            return res.json().get("did")
        except Exception as e:
            logging.error(f"❌ Error resolving handle {handle}: {e}")
            return None

    def get_followers_map(
            self, target_did: str, max_count: int, start_cursor: Optional[str] = None
    ) -> Tuple[Dict[str, str], Optional[str]]:
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.api_base_url}/app.bsky.graph.getFollowers"
        followers_map = {}
        cursor = start_cursor

        logging.info(f"📡 Extraction: Starting fetch for {target_did} (Limit: {max_count})")

        while len(followers_map) < max_count:
            # Calculate remaining needed to avoid over-fetching
            remaining = max_count - len(followers_map)
            current_limit = min(remaining, 100)

            params = {"actor": target_did, "limit": current_limit}
            if cursor:
                params["cursor"] = cursor

            try:
                res = requests.get(url, headers=headers, params=params)

                # Check for rate limits (429) specifically
                if res.status_code == 429:
                    logging.warning("⚠️ Rate limit hit! Cooling down for 30 seconds...")
                    time.sleep(30)
                    continue

                res.raise_for_status()
                data = res.json()
            except Exception as e:
                logging.error(f"❌ API Error during extraction: {e}")
                break

            batch = data.get('followers', [])
            batch_count = len(batch)

            # --- NEW DETAILED LOGGING ---
            logging.info(
                f"  └─ Received batch of {batch_count} users. (Total collected: {len(followers_map) + batch_count})")

            if not batch:
                logging.info("  └─ No more followers returned by API (end of list).")
                break

            for p in batch:
                # Use DID as key to ensure uniqueness if the API sends duplicates
                followers_map[p['did']] = p['handle']
                if len(followers_map) >= max_count:
                    logging.info(f"✅ Reached desired limit of {max_count} users.")
                    return followers_map, data.get('cursor')

            cursor = data.get('cursor')

            if not cursor:
                logging.info("  └─ No next cursor provided. End of stream.")
                break

            # Respectful delay to prevent 429s
            time.sleep(self.pagination_delay)

        return followers_map, cursor

    def run_audit(self, entries: Set[str], keywords: List[str]):
        # Filter out history
        remaining = entries.difference(self.processed_dids).difference(self.already_followed_dids)

        logging.info(f"Filtering: {len(entries)} input -> {len(remaining)} after history removal.")

        total = len(remaining)
        if total == 0:
            logging.info("⏭️ No new users to audit. Skipping audit phase.")
            return

        is_bypassing = not keywords
        logging.info(f"🚀 Audit Start: {total} users. Keyword Filter: {'DISABLED' if is_bypassing else 'ENABLED'}")

        entry_list = list(remaining)
        activity_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        kw_lower = [k.lower() for k in keywords]

        for i in range(0, total, self.max_profiles_per_batch):
            batch = entry_list[i:i + self.max_profiles_per_batch]

            if (time.time() - self.last_heartbeat) > (self.heartbeat_interval_minutes * 60):
                logging.info(f"💓 Progress: {i}/{total} ({round((i / total) * 100, 1)}%)")
                self.last_heartbeat = time.time()

            if is_bypassing:
                for did in batch:
                    self._check_activity_and_save(did, "BYPASS", activity_cutoff)
            else:
                try:
                    res = requests.get(f"{self.api_base_url}/app.bsky.actor.getProfiles",
                                       headers={"Authorization": f"Bearer {self.token}"},
                                       params={"actors": batch})
                    res.raise_for_status()
                    profiles = res.json().get("profiles", [])
                    for p in profiles:
                        bio = p.get('description', '').lower()
                        match = next((k.upper() for k in kw_lower if k in bio), None)
                        if match:
                            self._check_activity_and_save(p['did'], match, activity_cutoff, p['handle'])
                except Exception as e:
                    logging.error(f"❌ Error fetching profiles: {e}")
                    continue

            time.sleep(self.pagination_delay)

    def _check_activity_and_save(self, did: str, kw: str, cutoff: datetime, handle: str = None):
        url = f"{self.api_base_url}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            res = requests.get(url, headers=headers, params={"actor": did, "limit": 1})
            res.raise_for_status()
            feed = res.json().get("feed", [])
            if not feed:
                logging.debug(f"User {handle or did} has an empty feed.")
                return

            ts_str = feed[0]['post']['indexedAt']
            last_active = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))

            if last_active > cutoff:
                age = (datetime.now(timezone.utc) - last_active).days
                logging.info(f"🎯 MATCH: {handle or did} ({age}d ago) [{kw}]")
                self._save_match({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "handle": handle, "did": did, "kw": kw, "age": age
                })
        except Exception as e:
            logging.debug(f"Error checking activity for {did}: {e}")
            pass

    def _save_match(self, record: dict):
        with open(self.dry_run_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

    def _load_processed_history(self) -> Set[str]:
        dids = set()
        if os.path.exists(self.dry_run_log_file):
            with open(self.dry_run_log_file, 'r') as f:
                for line in f:
                    try:
                        dids.add(json.loads(line)["did"])
                    except:
                        continue
        return dids

    def _load_auto_follow_history(self) -> Set[str]:
        dids = set()
        if os.path.exists(self.auto_follow_log):
            with open(self.auto_follow_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("success"): dids.add(record["target_did"])
                    except:
                        continue
        return dids


def main():
    parser = argparse.ArgumentParser(description="Bluesky Follow Extraction Tool")
    parser.add_argument("config", help="The name of the config file")
    parser.add_argument("--env", help="The environment variable name to use for the password", default=None)
    args = parser.parse_args()

    config_path = os.path.join(CONFIG_DIR, args.config)
    if not os.path.exists(config_path):
        logging.error(f"❌ Config file not found at: {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = json.load(f)

    try:
        tool = BlueskyFollowTool(config_data, env_override=args.env)
    except ValueError as e:
        logging.error(f"❌ Configuration Error: {e}")
        sys.exit(1)

    if not tool._get_session():
        sys.exit(1)

    start_cursor = None
    if os.path.exists(tool.cursor_file):
        with open(tool.cursor_file, "r") as f:
            start_cursor = f.read().strip() or None

    # --- Resolve Target Handles ---
    did_a = tool.resolve_handle(config_data["targets"]["target_a"])
    if not did_a:
        logging.error(f"❌ Could not resolve target_a handle {config_data['targets']['target_a']}")
        sys.exit(1)

    # Handle multiple target_b handles
    target_b_handles = config_data["targets"]["target_b"]
    if isinstance(target_b_handles, str):
        target_b_handles = [target_b_handles]  # Ensure it's a list

    all_followers_b = {}
    last_cursor = None
    for handle in target_b_handles:
        did_b = tool.resolve_handle(handle)
        if not did_b:
            logging.warning(f"❌ Could not resolve target_b handle {handle}. Skipping.")
            continue

        followers, next_cursor = tool.get_followers_map(
            did_b, config_data["controls"]["max_per_run"], start_cursor
        )
        logging.info(f"Target B ({handle}) retrieved: {len(followers)} followers.")
        all_followers_b.update(followers)
        last_cursor = next_cursor  # keep cursor of the last resolved target

    # Update cursor if available
    if last_cursor is not None:
        with open(tool.cursor_file, "w") as f:
            f.write(last_cursor)

    # Fetch followers of A (comparison target)
    logging.info(f"Target A ({config_data['targets']['target_a']}) retrieval starting...")
    map_a, _ = tool.get_followers_map(did_a, 50000)
    logging.info(f"Target A retrieved: {len(map_a)} followers.")

    # Compute difference: B followers not following A
    diff_dids = set(all_followers_b.keys()).difference(set(map_a.keys()))
    logging.info(f"✅ Comparison Complete: {len(diff_dids)} users from B are not following A.")

    # Audit phase
    tool.run_audit(diff_dids, config_data["controls"]["keywords"])
    logging.info("✨ Run complete.")


if __name__ == "__main__":
    main()
import requests
import json
import time
import logging
import os
import sys
import argparse
import sqlite3
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

# --- CONSTANTS ---
CONFIG_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/all-in-one-configs/"

# --- LOGGING CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyFollowTool:
    def __init__(self, config: dict, env_override: Optional[str] = None):
        self.api_base_url = config["api"]["base_url"]
        self.pagination_delay = config["tool"]["pagination_delay"]
        self.max_profiles_per_batch = config["tool"]["max_profiles_per_batch"]
        self.heartbeat_interval_minutes = config["tool"]["heartbeat_interval_minutes"]

        env_var_name = env_override or config["app_password_env_var"]
        self.handle = config["my_handle"]
        self.password = os.environ.get(env_var_name)

        if not self.password:
            raise ValueError(f"Environment variable '{env_var_name}' not set or empty.")

        # Database Config
        self.db_path = config["database"]["db_path"]
        self.followers_table = config["database"]["followers_table"]
        self.following_table = config["database"]["following_table"]
        self.matches_table = self.followers_table.replace("followers", "matches")

        self.dry_run_log_file = config["files"]["dry_run_log_file"]
        self._init_db()

        self.token = None
        self.my_did = None
        self.last_heartbeat = time.time()

        # History Loading
        self.processed_dids: Set[str] = self._load_processed_history()
        self.already_followed_dids: Set[str] = self._load_db_following_history()

        logging.info(
            f"Loaded {len(self.processed_dids)} from dry-run log and {len(self.already_followed_dids)} from DB following table."
        )

    def _init_db(self):
        """Ensure the matches table exists."""
        with self._get_db_conn() as conn:
            conn.execute(f'''
                CREATE TABLE IF NOT EXISTS {self.matches_table} (
                    did TEXT PRIMARY KEY,
                    handle TEXT,
                    kw TEXT,
                    age INTEGER,
                    timestamp TIMESTAMP
                )
            ''')

    def _get_db_conn(self):
        return sqlite3.connect(self.db_path)

    def _load_db_following_history(self) -> Set[str]:
        dids = set()
        try:
            with self._get_db_conn() as conn:
                cursor = conn.cursor()
                query = f"SELECT did FROM {self.following_table} WHERE unfollowed = 0"
                cursor.execute(query)
                dids = {row[0] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            logging.error(f"Database error loading history: {e}")
        return dids

    def load_local_followers(self) -> Dict[str, str]:
        """Loads all followers for Target A from the local database."""
        followers_map = {}
        try:
            with self._get_db_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT did, handle FROM {self.followers_table}")
                for did, handle in cursor.fetchall():
                    followers_map[did] = handle
            if followers_map:
                logging.info(f"📁 Local Cache: Loaded {len(followers_map)} profiles from '{self.followers_table}'.")
        except sqlite3.Error:
            pass
        return followers_map

    def sync_followers_to_db(self, followers_map: Dict[str, str]):
        """Saves a bulk map of followers to the database."""
        logging.info(f"💾 Syncing {len(followers_map)} followers to local DB...")
        now = datetime.now(timezone.utc).isoformat()
        with self._get_db_conn() as conn:
            conn.executemany(f'''
                INSERT OR REPLACE INTO {self.followers_table} (did, handle, last_synced)
                VALUES (?, ?, ?)
            ''', [(did, handle, now) for did, handle in followers_map.items()])
        logging.info("✅ Sync complete.")

    def _get_session(self) -> bool:
        url = f"{self.api_base_url}/com.atproto.server.createSession"

        # DEBUG: Verify credentials aren't empty/weirdly short
        logging.debug(f"Attempting login for handle: {self.handle}")
        if not self.password:
            logging.error("❌ Auth Error: Password is None or Empty.")
            return False

        payload = {"identifier": self.handle, "password": self.password}

        try:
            res = requests.post(url, json=payload)

            # If it's a 401, let's see exactly what the server says
            if res.status_code == 401:
                logging.error(f"❌ Auth Failed (401): Check your handle and App Password. Response: {res.text}")
                logging.info(f"✅ Auth failed for {self.handle} (DID: {self.my_did}).")
                return False

            res.raise_for_status()
            data = res.json()
            self.token = data.get("accessJwt")
            self.my_did = data.get("did")
            logging.info(f"✅ Auth successful for {self.handle} (DID: {self.my_did}).")
            return True
        except Exception as e:
            logging.error(f"❌ Auth Exception: {e}")
            return False

    def resolve_handle(self, handle: str) -> Optional[str]:
        url = f"{self.api_base_url}/com.atproto.identity.resolveHandle"
        try:
            res = requests.get(url, params={"handle": handle})
            res.raise_for_status()
            return res.json().get("did")
        except Exception:
            return None

    def get_followers_map(
            self, target_did: str, max_count: int, start_cursor: Optional[str] = None
    ) -> Tuple[Dict[str, str], Optional[str]]:
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.api_base_url}/app.bsky.graph.getFollowers"
        followers_map = {}
        cursor = start_cursor

        logging.info(f"📡 API Fetch: Starting for {target_did} (Limit: {max_count})")

        while len(followers_map) < max_count:
            remaining = max_count - len(followers_map)
            params = {"actor": target_did, "limit": min(remaining, 100)}
            if cursor:
                params["cursor"] = cursor

            try:
                res = requests.get(url, headers=headers, params=params)
                if res.status_code == 429:
                    logging.warning("⚠️ Rate limit hit! Cooling down for 30s...")
                    time.sleep(30)
                    continue
                res.raise_for_status()
                data = res.json()
            except Exception as e:
                logging.error(f"❌ API Error: {e}")
                break

            batch = data.get('followers', [])
            if not batch: break

            for p in batch:
                followers_map[p['did']] = p['handle']

            if len(followers_map) % 1000 == 0:
                logging.info(f"  └─ Progress: Collected {len(followers_map)}...")

            cursor = data.get('cursor')
            if not cursor: break
            time.sleep(self.pagination_delay)

        return followers_map, cursor

    def run_audit(self, entries: Set[str], keywords: List[str]):
        remaining = entries.difference(self.processed_dids).difference(self.already_followed_dids)
        total = len(remaining)
        if total == 0:
            logging.info("⏭️ No new users to audit.")
            return

        logging.info(f"🚀 Audit Start: {total} users.")
        entry_list = list(remaining)
        activity_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        kw_lower = [k.lower() for k in keywords]

        for i in range(0, total, self.max_profiles_per_batch):
            batch = entry_list[i:i + self.max_profiles_per_batch]
            try:
                res = requests.get(f"{self.api_base_url}/app.bsky.actor.getProfiles",
                                   headers={"Authorization": f"Bearer {self.token}"},
                                   params={"actors": batch})
                res.raise_for_status()
                for p in res.json().get("profiles", []):
                    bio = p.get('description', '').lower()
                    match = next((k.upper() for k in kw_lower if k in bio), None) if kw_lower else "BYPASS"
                    if match:
                        self._check_activity_and_save(p['did'], match, activity_cutoff, p['handle'])
            except Exception:
                continue
            time.sleep(self.pagination_delay)

    def _check_activity_and_save(self, did: str, kw: str, cutoff: datetime, handle: str = None):
        url = f"{self.api_base_url}/app.bsky.feed.getAuthorFeed"
        try:
            res = requests.get(url, headers={"Authorization": f"Bearer {self.token}"},
                               params={"actor": did, "limit": 1})
            res.raise_for_status()
            feed = res.json().get("feed", [])
            if feed:
                ts_str = feed[0]['post']['indexedAt']
                last_active = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                if last_active > cutoff:
                    age = (datetime.now(timezone.utc) - last_active).days
                    logging.info(f"🎯 MATCH: {handle or did} ({age}d ago)")
                    self._save_match({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "handle": handle, "did": did, "kw": kw, "age": age
                    })
        except Exception:
            pass

    def _save_match(self, record: dict):
        # 1. Save to dry-run text file
        with open(self.dry_run_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

        # 2. Save to DB matches table
        try:
            with self._get_db_conn() as conn:
                conn.execute(f'''
                    INSERT OR REPLACE INTO {self.matches_table} (did, handle, kw, age, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (record['did'], record['handle'], record['kw'], record['age'], record['timestamp']))
        except sqlite3.Error as e:
            logging.error(f"DB Match Save Error: {e}")

    def _load_processed_history(self) -> Set[str]:
        dids = set()
        # Load from DB matches table first
        try:
            with self._get_db_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT did FROM {self.matches_table}")
                dids.update(row[0] for row in cursor.fetchall())
        except sqlite3.Error:
            pass

        # Then supplement from file
        if os.path.exists(self.dry_run_log_file):
            with open(self.dry_run_log_file, 'r') as f:
                for line in f:
                    try:
                        dids.add(json.loads(line)["did"])
                    except:
                        continue
        return dids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--env", default=None)
    parser.add_argument("--refresh", action="store_true", help="Force refresh Target A from API")
    args = parser.parse_args()

    if os.path.exists(args.config):
        config_path = args.config
    else:
        config_path = os.path.join(CONFIG_DIR, args.config)

    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = json.load(f)

    tool = BlueskyFollowTool(config_data, env_override=args.env)
    if not tool._get_session(): sys.exit(1)

    # 1. Target A (The "Don't follow if already here" list)
    did_a = tool.resolve_handle(config_data["targets"]["target_a"])
    map_a = {} if args.refresh else tool.load_local_followers()

    if not map_a:
        logging.info(f"🔄 Syncing Target A from API (this may take a moment)...")
        map_a, _ = tool.get_followers_map(did_a, 50000)
        tool.sync_followers_to_db(map_a)
    else:
        logging.info("⚡ Using local database for Target A followers.")

    # 2. Target B (The Sources)
    target_b_handles = config_data["targets"]["target_b"]
    if isinstance(target_b_handles, str): target_b_handles = [target_b_handles]

    all_followers_b = {}
    for handle in target_b_handles:
        did_b = tool.resolve_handle(handle)
        if did_b:
            followers, _ = tool.get_followers_map(did_b, config_data["controls"]["max_per_run"])
            all_followers_b.update(followers)

    # 3. Compute Difference and Audit
    diff_dids = set(all_followers_b.keys()).difference(set(map_a.keys()))
    tool.run_audit(diff_dids, config_data["controls"]["keywords"])
    logging.info("✨ Run complete.")


if __name__ == "__main__":
    main()
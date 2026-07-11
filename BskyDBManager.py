import sqlite3
import time
import os
import json
import argparse
import requests
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(message)s')


class BlueskyDBManager:
    def __init__(self, config: dict):
        self.api_url = config.get("api", {}).get("base_url", "https://bsky.social/xrpc")
        self.handle = config["my_handle"]

        # Get targets from config
        self.target_a = config.get("targets", {}).get("target_a")
        self.target_b_list = config.get("targets", {}).get("target_b", [])
        if isinstance(self.target_b_list, str):
            self.target_b_list = [self.target_b_list]

        # Resolve password
        env_var_name = config["app_password_env_var"]
        self.password = os.environ.get(env_var_name)

        # DB Settings
        self.db_path = config["database"]["db_path"]
        self.f_table = config["database"]["followers_table"]
        self.g_table = config["database"]["following_table"]

        self.conn = sqlite3.connect(self.db_path)
        self._create_tables()

        self.token = None
        self._login()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute(
            f'CREATE TABLE IF NOT EXISTS {self.f_table} (did TEXT PRIMARY KEY, handle TEXT, last_synced TIMESTAMP)')
        cursor.execute(
            f'CREATE TABLE IF NOT EXISTS {self.g_table} (did TEXT PRIMARY KEY, handle TEXT, unfollowed BOOLEAN DEFAULT 0, last_synced TIMESTAMP)')
        self.conn.commit()

    def _login(self):
        url = f"{self.api_url}/com.atproto.server.createSession"
        res = requests.post(url, json={"identifier": self.handle, "password": self.password})
        res.raise_for_status()
        self.token = res.json()["accessJwt"]

    def sync_all_targets(self):
        """Syncs Target A and all accounts in Target B list."""
        now = datetime.now(timezone.utc).isoformat()

        # Combine Target A and Target B list for a full sync
        all_targets = []
        if self.target_a: all_targets.append(self.target_a)
        all_targets.extend(self.target_b_list)

        for target in all_targets:
            logging.info(f"\n🚀 Starting sync for target: {target}")

            # 1. Sync Followers for this target
            followers = self._get_paginated("app.bsky.graph.getFollowers", "followers", target)
            for f in followers:
                self.conn.execute(f'''
                    INSERT OR REPLACE INTO {self.f_table} (did, handle, last_synced)
                    VALUES (?, ?, ?)
                ''', (f['did'], f['handle'], now))

            # 2. Sync Following for this target
            following = self._get_paginated("app.bsky.graph.getFollows", "follows", target)
            for f in following:
                self.conn.execute(f'''
                    INSERT INTO {self.g_table} (did, handle, last_synced, unfollowed)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(did) DO UPDATE SET handle = excluded.handle, last_synced = excluded.last_synced
                ''', (f['did'], f['handle'], now))

            self.conn.commit()
            logging.info(f"✅ Finished sync for {target}")

    def _get_paginated(self, endpoint, key_name, target):
        results = []
        cursor = None
        url = f"{self.api_url}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}"}

        while True:
            params = {"actor": target, "limit": 100}
            if cursor: params["cursor"] = cursor

            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 429:
                time.sleep(30)
                continue
            if res.status_code != 200: break

            data = res.json()
            batch = data.get(key_name, [])
            results.extend(batch)
            logging.info(f"  .. {endpoint.split('.')[-1]}: {len(results)} items")

            cursor = data.get("cursor")
            if not cursor: break
            time.sleep(0.2)
        return results

    def close(self):
        """Safely closes the database connection."""
        if self.conn:
            self.conn.close()
            logging.info("Database connection closed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = json.load(f)

    mgr = BlueskyDBManager(config)
    mgr.sync_all_targets()
    mgr.close()


if __name__ == "__main__":
    main()
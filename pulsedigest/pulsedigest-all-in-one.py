import requests
import json
import time
import logging
import os
import sys
from typing import List, Dict, Optional, Set
from datetime import datetime, timezone, timedelta

# Standard logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TARGET_A = "pulsedigest.bsky.social"
TARGET_B = "gsgsdgsgddfg.bsky.social"
INPUT_FILE_PATH = "pulsedigest_non_overlapping_gsgsdgsgddfg_bsky_social.txt"
DRY_RUN_LOG_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/pulsedigest/pulsedigest_dry_run_matches.jsonl"
AUTO_FOLLOW_LOG = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/pulsedigest/auto_follow_log.jsonl"


class BlueskyFollowTool:
    API_BASE_URL = "https://bsky.social/xrpc"
    PAGINATION_DELAY = 0.6
    MAX_PROFILES_PER_BATCH = 25
    HEARTBEAT_INTERVAL_MINUTES = 2

    def __init__(self, handle: str, password: str):
        self.handle = handle
        self.password = password
        self.token = None
        self.my_did = None

        self.log_abs_path = os.path.abspath(DRY_RUN_LOG_FILE)

        print("\n" + "=" * 60)
        logging.info(f"📝 MATCH OUTPUT: {self.log_abs_path}")
        print("=" * 60 + "\n")

        # Load history from previous audits
        self.processed_dids: Set[str] = self._load_processed_history()
        # Load history from the auto-follow log
        self.already_followed_dids: Set[str] = self._load_auto_follow_history()

        self.last_heartbeat = time.time()

    def _get_session(self) -> bool:
        """Authenticates with debugging for handle/password issues"""
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"

        if not self.handle or not self.password:
            logging.error(f"❌ Missing Credentials: Handle='{self.handle}', Password Set={bool(self.password)}")
            return False

        clean_handle = self.handle.replace("@", "").strip()

        # Security-safe preview
        pw_preview = f"{self.password[:2]}***{self.password[-2:]}" if len(self.password) > 4 else "****"
        logging.info(f"Authenticating as {clean_handle} with password: {pw_preview}...")

        payload = {"identifier": clean_handle, "password": self.password}
        try:
            res = requests.post(url, json=payload)

            if res.status_code == 401:
                logging.error(f"❌ Auth Error: 401 Unauthorized. Details: {res.text}")
                return False

            res.raise_for_status()
            session_data = res.json()
            self.token = session_data["accessJwt"]
            self.my_did = session_data["did"]
            logging.info("✅ Authentication successful.")
            return True
        except Exception as e:
            logging.error(f"❌ Connection Error: {e}")
            return False

    def _load_auto_follow_history(self) -> Set[str]:
        """Loads DIDs from the auto_follow_log.jsonl to omit them"""
        followed = set()
        if os.path.exists(AUTO_FOLLOW_LOG):
            logging.info(f"📜 Cross-referencing {AUTO_FOLLOW_LOG}...")
            with open(AUTO_FOLLOW_LOG, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("success") is True and record.get("target_did"):
                            followed.add(record["target_did"])
                    except:
                        continue
            logging.info(f"✅ Omit list updated: {len(followed)} users already followed.")
        return followed

    def resolve_handle(self, handle: str) -> Optional[str]:
        url = f"{self.API_BASE_URL}/com.atproto.identity.resolveHandle"
        try:
            res = requests.get(url, params={"handle": handle})
            return res.json().get("did")
        except:
            return None

    def get_followers_map(self, target_did: str) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.API_BASE_URL}/app.bsky.graph.getFollowers"
        followers_map = {}
        cursor = None
        logging.info(f"📡 Fetching all followers for DID: {target_did}...")
        while True:
            params = {"actor": target_did, "limit": 100}
            if cursor: params["cursor"] = cursor
            res = requests.get(url, headers=headers, params=params)
            data = res.json()
            for p in data.get('followers', []):
                followers_map[p['did']] = p['handle']
            cursor = data.get('cursor')
            if not cursor: break
            time.sleep(self.PAGINATION_DELAY)
        return followers_map

    def _load_processed_history(self) -> Set[str]:
        dids = set()
        if os.path.exists(DRY_RUN_LOG_FILE):
            logging.info(f"🔍 Reading existing matches from history...")
            with open(DRY_RUN_LOG_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        dids.add(json.loads(line).get("did"))
                    except:
                        continue
            logging.info(f"✅ Loaded {len(dids)} previous matches to skip.")
        return dids

    def load_targets_from_file(self, file_path: str) -> Set[str]:
        entries = set()
        if not os.path.exists(file_path):
            logging.error(f"❌ Input file not found: {file_path}")
            return entries

        logging.info(f"📂 Parsing target file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip().replace("@", "")
                if not line or line.startswith("handle,did"): continue
                entries.add(line.split(',')[-1].strip())
        return entries

    def _get_latest_activity_date(self, did: str) -> Optional[datetime]:
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            res = requests.get(url, headers=headers, params={"actor": did, "limit": 1})
            feed = res.json().get("feed", [])
            if not feed: return None
            ts = feed[0]['post']['indexedAt']
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except:
            return None

    def _save_match(self, record: dict):
        with open(DRY_RUN_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def run_audit(self, entries: Set[str], include_kw: List[str], exclude_kw: List[str] = None):
        """Processes audit with keyword inclusion and exclusion filters"""
        inc_lower = [k.lower() for k in (include_kw or [])]
        exc_lower = [k.lower() for k in (exclude_kw or [])]

        # Filter out users we've already interacted with
        remaining = entries.difference(self.processed_dids).difference(self.already_followed_dids)
        total = len(remaining)

        logging.info(f"🚀 Audit Start: {total} new users to process.")
        logging.info(f"Include filter: {inc_lower if inc_lower else 'ALL (None specified)'}")
        logging.info(f"Exclude filter: {exc_lower if exc_lower else 'NONE (None specified)'}")

        entry_list = list(remaining)
        activity_cutoff = datetime.now(timezone.utc) - timedelta(days=14)

        for i in range(0, total, self.MAX_PROFILES_PER_BATCH):
            batch = entry_list[i:i + self.MAX_PROFILES_PER_BATCH]

            if (time.time() - self.last_heartbeat) > (self.HEARTBEAT_INTERVAL_MINUTES * 60):
                pct = round((i / total) * 100, 1)
                logging.info(f"💓 [HEARTBEAT] Progress: {i}/{total} ({pct}%). Logging to: {self.log_abs_path}")
                self.last_heartbeat = time.time()

            try:
                res = requests.get(f"{self.API_BASE_URL}/app.bsky.actor.getProfiles",
                                   headers={"Authorization": f"Bearer {self.token}"},
                                   params={"actors": batch})
                profiles = res.json().get("profiles", [])
            except Exception as e:
                logging.error(f"⚠️ Batch fetch error: {e}")
                time.sleep(5)
                continue

            for p in profiles:
                desc = p.get('description', '').lower()

                # 1. EXCLUDE LOGIC: If an exclusion word is found, skip this profile immediately
                if exc_lower and any(word in desc for word in exc_lower):
                    continue

                # 2. INCLUDE LOGIC: If inclusion list is provided, must match one.
                # If list is empty, everyone passes.
                match_found = False
                found_label = "MATCH"

                if not inc_lower:
                    match_found = True
                else:
                    found_kw = next((k for k in inc_lower if k in desc), None)
                    if found_kw:
                        match_found = True
                        found_label = found_kw.upper()

                if match_found:
                    last_active = self._get_latest_activity_date(p['did'])
                    if last_active and last_active > activity_cutoff:
                        age = (datetime.now(timezone.utc) - last_active).days
                        logging.info(f"🎯 MATCH: @{p['handle']} (Reason: {found_label}, Active: {age}d ago)")

                        self._save_match({
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "handle": p['handle'],
                            "did": p['did'],
                            "kw": found_label,
                            "age": age
                        })

                time.sleep(0.05)  # Small intra-batch delay

            time.sleep(self.PAGINATION_DELAY)


if __name__ == "__main__":
    # --- CONFIGURATION ---
    MY_HANDLE = "ethicalsearch.bsky.social"
    APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    INCLUDE_KEYWORDS = ["independent news"]
    EXCLUDE_KEYWORDS = ["vegan", "🌱", "Ⓥ"]
    # ---------------------

    tool = BlueskyFollowTool(MY_HANDLE, APP_PASSWORD)
    if not tool._get_session():
        sys.exit(1)

    # 1. Determine the Target List
    if TARGET_B:
        logging.info(f"🔎 Phase 1: Extracting followers of {TARGET_B} not in {TARGET_A}")
        did_a = tool.resolve_handle(TARGET_A)
        did_b = tool.resolve_handle(TARGET_B)

        if not did_a or not did_b:
            logging.error("Could not resolve handles for Target A or B. Exiting.")
            sys.exit(1)

        map_a = tool.get_followers_map(did_a)
        map_b = tool.get_followers_map(did_b)

        # Calculate the difference (DIDs in B but not in A)
        diff_dids = set(map_b.keys()).difference(set(map_a.keys()))

        # Save to file for records
        output_file = f"non_overlapping_{TARGET_B.replace('.', '_')}.txt"
        with open(output_file, "w", encoding='utf-8') as f:
            for d in diff_dids:
                f.write(f"{map_b[d]},{d}\n")

        logging.info(f"✅ Extracted {len(diff_dids)} potential targets.")
        targets_to_audit = diff_dids
    else:
        logging.info(f"📂 No Target B provided. Loading targets from {INPUT_FILE_PATH}")
        targets_to_audit = set()
        if os.path.exists(INPUT_FILE_PATH):
            with open(INPUT_FILE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    # Extracts the DID (last element in comma-separated line)
                    parts = line.strip().split(',')
                    if parts:
                        targets_to_audit.add(parts[-1])
        else:
            logging.error(f"File {INPUT_FILE_PATH} not found and no TARGET_B provided.")
            sys.exit(1)

    # 2. Run the AUDIT Phase
    if targets_to_audit:
        logging.info(f"🚀 Phase 2: Auditing {len(targets_to_audit)} users...")
        tool.run_audit(targets_to_audit, INCLUDE_KEYWORDS, EXCLUDE_KEYWORDS)
        logging.info("✨ Process complete.")
    else:
        logging.warning("No targets found to audit.")
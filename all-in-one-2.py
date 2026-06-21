import requests
import json
import time
import logging
import os
import sys
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

# --- LOGGING CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION ---
MY_HANDLE = "ethicalsearch.bsky.social"
APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

TARGET_A = "vegansearchengine.bsky.social" # animal-justice.bsky.social #corruption occrp.org, #bluebarnsanctuary.bsky.social
TARGET_B = ["lincolnsquare.media"] #  "freebird07.bsky.social", "politicaled.bsky.social", "yogini108.bsky.social", mrrickygervais.bsky.social papyrusgardens.bsky.social, lorenzothecat.bsky.social, "4snowflakes.bsky.social", "loudouncats.bsky.social", "crits4cats.org", "ellenscats.bsky.social", "snflunky.bsky.social", pfeifferpack.bsky.social, wishesrescue.bsky.social, karaisntactive.bsky.social, 15outof10.org, loki-dog-nc.bsky.social, dogs.bsky.social, sahumane.bsky.social, downdogpets.bsky.social, elle1968.bsky.social, princessluna.bsky.social, downdogpets.bsky.social, cubsgirl.bsky.social, #themindfulnomad.bsky.social, johnmoe.bsky.social #mothergoose104.bsky.social #doodnat.bsky.social

# FILES
DRY_RUN_LOG_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/dry_run_matches/ve_dry_run_matches.jsonl"
CURSOR_FILE = "last_follower_cursor.txt"
AUTO_FOLLOW_LOG = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/auto_follow_log.jsonl"

# CONTROLS #
KEYWORDS =  ["mindful", "yoga", "vegan", "🌱", "Ⓥ", "animal rights", " cat", " dog", "cat", "dog", "pets" ,"Buddhist", "Buddhism", "Zen", "cats", " meditation", "kindness", "New York", "NY", "Manhattan", "Queens", "Bronx", "Long Island", "Staten Island", "Brooklyn"]

# --- EXCLUSION LIST ---
# Users with these words in their bio will be skipped immediately.
EXCLUDE_KEYWORDS = ["pornstar", "onlyfans", "nsfw", "adult", "🔞", "escort", "content creator", "sex", "xxx"]

MAX_PER_RUN = 5000


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
        self.last_heartbeat = time.time()

        # Load existing history to avoid re-auditing or following
        self.processed_dids: Set[str] = self._load_processed_history()
        self.already_followed_dids: Set[str] = self._load_auto_follow_history()

    def _get_session(self) -> bool:
        url = f"{self.API_BASE_URL}/com.atproto.server.createSession"
        payload = {"identifier": self.handle, "password": self.password}
        logging.info("Authenticating...")
        try:
            res = requests.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            self.token = data["accessJwt"]
            self.my_did = data["did"]
            return True
        except Exception as e:
            logging.error(f"❌ Auth Error: {e}")
            return False

    def resolve_handle(self, handle: str) -> Optional[str]:
        url = f"{self.API_BASE_URL}/com.atproto.identity.resolveHandle"
        try:
            res = requests.get(url, params={"handle": handle})
            return res.json().get("did")
        except:
            return None

    def get_followers_map(self, target_did: str, max_count: int, start_cursor: Optional[str] = None) -> Tuple[
        Dict[str, str], Optional[str]]:
        """Fetches up to max_count followers. Returns (map, next_cursor)."""
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.API_BASE_URL}/app.bsky.graph.getFollowers"
        followers_map = {}
        cursor = start_cursor

        logging.info(f"📡 Extraction: Target {target_did} (Resume cursor: {cursor or 'None'})")

        while len(followers_map) < max_count:
            params = {"actor": target_did, "limit": 100}
            if cursor: params["cursor"] = cursor

            try:
                res = requests.get(url, headers=headers, params=params)
                res.raise_for_status()
                data = res.json()
            except Exception as e:
                logging.error(f"❌ API Error: {e}")
                break

            batch = data.get('followers', [])
            if not batch: break

            for p in batch:
                followers_map[p['did']] = p['handle']
                if len(followers_map) >= max_count:
                    return followers_map, data.get('cursor')

            cursor = data.get('cursor')
            if not cursor: break
            time.sleep(self.PAGINATION_DELAY)

        return followers_map, cursor

    def run_audit(self, entries: Set[str], keywords: List[str]):
        """Audits for activity. Filters out adult content and matches specific keywords."""
        remaining = entries.difference(self.processed_dids).difference(self.already_followed_dids)
        total = len(remaining)

        is_bypassing_keywords = not keywords
        logging.info(f"🚀 Audit Start: {total} users. Exclusion Filter: ACTIVE.")

        entry_list = list(remaining)
        activity_cutoff = datetime.now(timezone.utc) - timedelta(days=14)

        kw_lower = [k.lower() for k in keywords]
        ex_lower = [e.lower() for e in EXCLUDE_KEYWORDS]

        for i in range(0, total, self.MAX_PROFILES_PER_BATCH):
            batch = entry_list[i:i + self.MAX_PROFILES_PER_BATCH]

            if (time.time() - self.last_heartbeat) > (self.HEARTBEAT_INTERVAL_MINUTES * 60):
                logging.info(f"💓 Progress: {i}/{total} ({round((i / total) * 100, 1)}%)")
                self.last_heartbeat = time.time()

            try:
                # Fetch profiles to check bios for both exclusions and inclusions
                res = requests.get(f"{self.API_BASE_URL}/app.bsky.actor.getProfiles",
                                   headers={"Authorization": f"Bearer {self.token}"},
                                   params={"actors": batch})

                for p in res.json().get("profiles", []):
                    bio = p.get('description', '').lower()

                    # --- FILTER 1: EXCLUSIONS ---
                    if any(bad_word in bio for bad_word in ex_lower):
                        continue  # Skip to next profile immediately

                    # --- FILTER 2: INCLUSIONS ---
                    if is_bypassing_keywords:
                        self._check_activity_and_save(p['did'], "BYPASS", activity_cutoff, p['handle'])
                    else:
                        match = next((k.upper() for k in kw_lower if k in bio), None)
                        if match:
                            self._check_activity_and_save(p['did'], match, activity_cutoff, p['handle'])

            except Exception as e:
                logging.error(f"❌ Profile Batch Error: {e}")
                continue

            time.sleep(self.PAGINATION_DELAY)

    def _check_activity_and_save(self, did: str, kw: str, cutoff: datetime, handle: str = None):
        """Verifies if user has posted within cutoff and logs result."""
        url = f"{self.API_BASE_URL}/app.bsky.feed.getAuthorFeed"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            res = requests.get(url, headers=headers, params={"actor": did, "limit": 1})
            feed = res.json().get("feed", [])
            if not feed: return

            ts_str = feed[0]['post']['indexedAt']
            last_active = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))

            if last_active > cutoff:
                age = (datetime.now(timezone.utc) - last_active).days
                logging.info(f"🎯 MATCH: {handle or did} ({age}d ago) [{kw}]")
                self._save_match({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "handle": handle, "target_did": did, "kw": kw, "age": age
                })
        except:
            pass

    def _save_match(self, record: dict):
        with open(DRY_RUN_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

    def _load_processed_history(self) -> Set[str]:
        dids = set()
        if os.path.exists(DRY_RUN_LOG_FILE):
            with open(DRY_RUN_LOG_FILE, 'r') as f:
                for line in f:
                    try:
                        dids.add(json.loads(line)["did"])
                    except:
                        continue
        return dids

    def _load_auto_follow_history(self) -> Set[str]:
        dids = set()
        if os.path.exists(AUTO_FOLLOW_LOG):
            with open(AUTO_FOLLOW_LOG, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("success"): dids.add(record["target_did"])
                    except:
                        continue
        return dids


if __name__ == "__main__":
    tool = BlueskyFollowTool(MY_HANDLE, APP_PASSWORD)
    if not tool._get_session(): sys.exit(1)

    # 1. Load Existing Data for Filtering
    # Fetch Target A (your account) followers once to exclude them from the audit
    did_a = tool.resolve_handle(TARGET_A)
    res_a = tool.get_followers_map(did_a, 50000)
    map_a = res_a[0]

    # 2. Extract Phase (Iterating through the list)
    all_potential_dids = set()

    for handle in TARGET_B:
        logging.info(f"--- Starting Extraction for: {handle} ---")

        did_b = tool.resolve_handle(handle)
        if not did_b:
            logging.error(f"Could not resolve handle: {handle}")
            continue

        # Fetch followers from this specific target
        # Note: start_cursor is shared; for multiple targets,
        # you may want to reset or ignore CURSOR_FILE logic.
        followers_b, next_cursor = tool.get_followers_map(did_b, MAX_PER_RUN)

        # Add these DIDs to our master set
        all_potential_dids.update(followers_b.keys())

    # 3. Filter Phase
    # Remove people who already follow Target A
    diff_dids = all_potential_dids.difference(set(map_a.keys()))

    logging.info(f"✅ Total Extracted: {len(all_potential_dids)}")
    logging.info(f"✅ Unique candidates not following {TARGET_A}: {len(diff_dids)}")

    # 4. Audit Phase
    if diff_dids:
        tool.run_audit(diff_dids, KEYWORDS)

    logging.info("✨ Run complete.")
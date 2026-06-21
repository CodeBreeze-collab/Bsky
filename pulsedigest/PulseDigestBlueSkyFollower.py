import json
import logging
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
import time

# --- FIX: ROBUST ATPROTO IMPORTS ---
Client = None
DID = None

try:
    from atproto import Client

    try:
        from atproto.models import DID
    except ImportError:
        try:
            from atproto.pydantic.models import DID
        except ImportError:
            DID = str
except ImportError:
    logging.error("FATAL: Could not import 'Client' from 'atproto'.")
    sys.exit(1)

if DID is None:
    DID = str
# -----------------------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyFollower:
    def __init__(self, username: str, password: str, log_file_path: str, dry_run_path: str,
                 request_delay_seconds: int = 5):
        if Client is None:
            raise RuntimeError("BlueskyFollower cannot be initialized: atproto.Client not available.")

        self.client = Client()
        self.username = username
        self.password = password
        self.log_file_path = Path(log_file_path)
        self.dry_run_path = Path(dry_run_path)
        self.session_did: Optional[DID] = None
        self.followed_dids: Set[str] = self._load_followed_dids()
        self.request_delay = request_delay_seconds

    def _load_followed_dids(self) -> Set[str]:
        """Loads DIDs from the history log to avoid duplicates."""
        dids = set()
        if not self.log_file_path.exists():
            return dids
        with self.log_file_path.open('r', encoding='utf-8') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if record.get('success') is True and record.get('target_did'):
                        dids.add(record['target_did'])
                except:
                    continue
        return dids

    def perform_cross_check(self):
        """Prints handles unique to the dry run vs the follow log."""
        logging.info("--- STARTING CROSS-CHECK REPORT ---")

        # Helper to get handles from a file
        def get_handles_from_file(path, key_name):
            handles = set()
            if Path(path).exists():
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            h = data.get(key_name)
                            if h and h != "N/A": handles.add(h)
                        except:
                            continue
            return handles

        dry_run_handles = get_handles_from_file(self.dry_run_path, "handle")
        followed_handles = get_handles_from_file(self.log_file_path, "target_handle")

        to_be_followed = dry_run_handles - followed_handles
        past_only = followed_handles - dry_run_handles

        print(f"\n[!] UNIQUE TO DRY RUN (Not followed yet): {len(to_be_followed)}")
        for h in sorted(to_be_followed)[:10]: print(f"  - @{h}")
        if len(to_be_followed) > 10: print(f"  ... and {len(to_be_followed) - 10} more")

        print(f"\n[!] UNIQUE TO HISTORY (Followed but not in current dry run): {len(past_only)}")
        for h in sorted(past_only)[:10]: print(f"  - @{h}")
        if len(past_only) > 10: print(f"  ... and {len(past_only) - 10} more")

        print("\n" + "-" * 35)
        time.sleep(2)

    def _log_follow_result(self, target_handle: str, target_did: str, success: bool):
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        log_entry = {
            "timestamp": timestamp,
            "target_handle": target_handle,
            "target_did": target_did,
            "success": success,
            "source_user": self.username
        }
        try:
            with self.log_file_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
            if success: self.followed_dids.add(target_did)
        except Exception as e:
            logging.error(f"Failed to write log for {target_handle}: {e}")

    def login(self) -> bool:
        logging.info(f"Logging in as {self.username}...")
        try:
            profile = self.client.login(self.username, self.password)
            self.session_did = profile.did
            return True
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def read_jsonl(self, file_path: str) -> List[Dict[str, Any]]:
        records = []
        if not Path(file_path).exists(): return []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    records.append(json.loads(line.strip()))
                except:
                    continue
        return records

    def process_records(self, dry_run_records: List[Dict[str, Any]]):
        """
        Strictly follows handles found in dry_run but NOT in the history log.
        """
        if not self.session_did:
            logging.error("Not logged in. Cannot process records.")
            return

        # 1. Identify the 'UNIQUE TO DRY RUN' group
        # We use a dictionary keyed by DID to ensure uniqueness and preserve handle info
        to_follow_map = {}
        for record in dry_run_records:
            did = record.get('target_did')
            handle = record.get('handle', 'Unknown')

            # The heart of the filter: Is it in the dry run but NOT in our history set?
            if did and did not in self.followed_dids:
                to_follow_map[did] = handle

        if not to_follow_map:
            logging.info("✨ No unique accounts found to follow. (Everything in dry run is already in your log).")
            return

        # 2. PREVIEW SUMMARY
        to_follow_list = list(to_follow_map.items())  # List of (did, handle)
        logging.info(f"--- 🎯 TARGETING UNIQUE HANDLES ({len(to_follow_list)}) ---")
        for did, handle in to_follow_list[:15]:
            print(f"  - @{handle} ({did})")
        if len(to_follow_list) > 15:
            print(f"  ... and {len(to_follow_list) - 15} others.")

        print("\nPress Ctrl+C now to abort, or wait 5 seconds to begin follows...")
        time.sleep(5)

        # 3. EXECUTION
        for i, (did, handle) in enumerate(to_follow_list):
            logging.info(f"[{i + 1}/{len(to_follow_list)}] Action: Follow @{handle}")
            try:
                self.client.follow(did)
                logging.info(f"    ✅ Success.")
                self._log_follow_result(handle, did, True)
            except Exception as e:
                logging.error(f"    ❌ Failed: {e}")
                self._log_follow_result(handle, did, False)

            if i < len(to_follow_list) - 1:
                time.sleep(self.request_delay)

    def run(self):
        """Main execution flow with cross-check and targeted follows."""
        # Print the comparison report first
        self.perform_cross_check()

        if self.login():
            # Only read the dry_run file for processing
            dry_run_records = self.read_jsonl(str(self.dry_run_path))
            self.process_records(dry_run_records)
            logging.info("Processing complete.")

    def run(self):
        self.perform_cross_check()
        if self.login():
            records = self.read_jsonl(str(self.dry_run_path))
            self.process_records(records)


if __name__ == '__main__':
    YOUR_BLUESKY_HANDLE = "pulsedigest.bsky.social"
    YOUR_BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

    DRY_RUN_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/pulsedigest/pulsedigest_dry_run_matches.jsonl"
    LOG_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/pulsedigest/auto_follow_log.jsonl"

    if not YOUR_BLUESKY_APP_PASSWORD:
        logging.critical("FATAL: BLUESKY_APP_PASSWORD not set.")
        sys.exit(1)

    follower = BlueskyFollower(
        YOUR_BLUESKY_HANDLE,
        YOUR_BLUESKY_APP_PASSWORD,
        LOG_FILE,
        DRY_RUN_FILE,
        request_delay_seconds=10
    )
    follower.run()
import json
import logging
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
import time  # <-- ADDED: For sleep functionality

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
    logging.error("Please ensure the 'atproto' library is installed: pip install atproto")
    sys.exit(1)

if DID is None:
    DID = str
# -----------------------------------


# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyFollower:
    """
    Reads a JSONL file with target accounts, avoids following already logged accounts,
    executes follow requests with a delay, and logs the results.
    """

    def __init__(self, username: str, password: str, log_file_path: str, request_delay_seconds: int = 5):
        """
        Initializes the client, sets paths, pre-loads DIDs, and sets the delay.

        :param username: Bluesky handle or email.
        :param password: Bluesky App Password.
        :param log_file_path: Path to the auto_follow_log.jsonl file.
        :param request_delay_seconds: The time to wait between follow requests (in seconds).
        """
        if Client is None:
            raise RuntimeError("BlueskyFollower cannot be initialized: atproto.Client not available.")

        self.client = Client()
        self.username = username
        self.password = password
        self.log_file_path = Path(log_file_path)
        self.session_did: Optional[DID] = None
        self.followed_dids: Set[str] = self._load_followed_dids()
        self.request_delay = request_delay_seconds  # <-- NEW: Stored delay value

    def _load_followed_dids(self) -> Set[str]:
        """
        Reads the dry_run_matches file and extracts all 'target_did'
        to ensure we don't follow them again.
        """
        dids = set()
        # Path to your dry run file
        dry_run_path = Path("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/dry_run_matches.jsonl")

        if not dry_run_path.exists():
            logging.warning(f"Dry run file not found at {dry_run_path}.")
            return dids

        logging.info(f"Loading DIDs from {dry_run_path}...")

        with dry_run_path.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # We look for 'target_did' regardless of a success key
                    if record.get('target_did'):
                        dids.add(record['target_did'])
                except json.JSONDecodeError as e:
                    logging.warning(f"Skipping line {i + 1} due to JSON error.")

        logging.info(f"Loaded {len(dids)} DIDs to skip.")
        return dids

    def _log_follow_result(self, target_handle: str, target_did: str, success: bool):
        """
        Appends the follow result to the log file in JSONL format.
        """
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

            if success:
                self.followed_dids.add(target_did)
        except Exception as e:
            logging.error(f"FATAL: Failed to write log entry for {target_handle}. Error: {e}")

    def login(self) -> bool:
        """
        Logs into the Bluesky service.
        """
        logging.info(f"Attempting to log in as {self.username}...")
        try:
            profile = self.client.login(self.username, self.password)
            self.session_did = profile.did
            logging.info(f"Successfully logged in! DID: {self.session_did}")
            return True
        except Exception as e:
            logging.error(f"Login failed for {self.username}. Error: {e}")
            return False

    def read_jsonl(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Reads and parses the JSONL file.
        """
        path = Path(file_path)
        if not path.exists():
            logging.error(f"File not found: {file_path}. Please check the path.")
            return []

        records = []
        logging.info(f"Reading records from {file_path}...")

        with path.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logging.warning(f"Skipping line {i + 1} due to JSON error: {e}. Line start: {line[:50]}")

        logging.info(f"Successfully read {len(records)} valid records.")
        return records

    def process_records(self, records: List[Dict[str, Any]]):
        """
        Filters records, previews the plan, and then executes follows.
        """
        if not self.session_did:
            logging.error("Not logged in. Cannot process records.")
            return

        # 1. Filter the list first to see who we actually NEED to follow
        to_follow = []
        for record in records:
            target_did = record.get('target_did')
            # Check for 'handle' or 'target_handle'
            target_handle = record.get('handle') or record.get('target_handle', 'Unknown')

            if target_did and target_did not in self.followed_dids:
                to_follow.append({'did': target_did, 'handle': target_handle})

        if not to_follow:
            logging.info("No new accounts to follow. Everything is up to date.")
            return

        # 2. PREVIEW PHASE: Print all handles before starting
        logging.info("--- FOLLOW PLAN ---")
        logging.info(f"Found {len(to_follow)} accounts to follow:")
        for entry in to_follow:
            print(f"  - @{entry['handle']}")
        logging.info("-------------------")

        # Give a small 3-second pause so you can read the list
        time.sleep(3)

        # 3. EXECUTION PHASE
        total = len(to_follow)
        for i, entry in enumerate(to_follow):
            target_did = entry['did']
            target_handle = entry['handle']

            logging.info(f"[EXECUTING {i + 1}/{total}] Target: @{target_handle}")

            try:
                self.client.follow(target_did)
                logging.info(f"    ✅ Successfully followed @{target_handle}.")
                # Log success so we don't do it again next time
                self._log_follow_result(target_handle, target_did, True)
            except Exception as e:
                logging.error(f"    ❌ Failed to follow @{target_handle}. Error: {e}")
                self._log_follow_result(target_handle, target_did, False)

            # Delay logic
            if i < total - 1:
                logging.info(f"⏳ Waiting {self.request_delay}s...")
                time.sleep(self.request_delay)

        logging.info("All records processed.")

    def run(self, file_path: str):
        """
        Main execution method: logs in, reads file, and processes actions.
        """
        if self.login():
            records = self.read_jsonl(file_path)
            self.process_records(records)
            logging.info("Processing complete.")



if __name__ == '__main__':
    YOUR_BLUESKY_HANDLE = "vegansearchengine.bsky.social"
    YOUR_BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

    # --- CONFIGURATION ---
    # 🎯 INPUT FILE: List of accounts to attempt to follow.
    JSONL_FILE_PATH = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/auto_follow_log.jsonl"

    # 📝 OUTPUT FILE: Log of accounts that were processed.
    LOG_FILE_PATH = "auto_follow_log.jsonl"

    # 💤 DELAY: Time to wait between each follow request (seconds).
    REQUEST_DELAY_SECONDS = 10  # Adjust this value as needed (e.g., 5-10 seconds is usually safe)
    # ---------------------

    if not YOUR_BLUESKY_APP_PASSWORD:
        logging.critical("FATAL: BLUESKY_APP_PASSWORD environment variable is not set.")
        sys.exit(1)

    try:
        follower = BlueskyFollower(
            YOUR_BLUESKY_HANDLE,
            YOUR_BLUESKY_APP_PASSWORD,
            LOG_FILE_PATH,
            request_delay_seconds=REQUEST_DELAY_SECONDS  # Pass the delay
        )
        follower.run(JSONL_FILE_PATH)
    except RuntimeError as e:
        logging.critical(f"Execution aborted: {e}")
    except SystemExit:
        pass
    except Exception as e:
        logging.error(f"An unexpected error occurred during execution: {e}")
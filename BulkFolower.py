import json
import logging
import time
import os
import sys
from typing import Dict, Any, List, Set
from datetime import datetime

from atproto import Client, AtUri
from atproto.exceptions import AtProtocolError

# Setup logging
LOG_FILE = "follow_log.txt"

# Ensure the log file starts fresh for a new run's attempts
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Console output
        logging.FileHandler(LOG_FILE, mode='a')  # Log file output (append mode)
    ]
)


class BulkFollower:
    """
    Reads a list of handles from a JSONL file, filters for positive keyword counts,
    checks existing follow status, and sends follow actions with rate limiting.
    Uses the atproto Client to talk to Bluesky.
    """

    DELAY_SECONDS = 15  # 1 minute delay
    MAX_FOLLOWS = 10  # Maximum number of NEW follows to attempt
    BATCH_SIZE = 25  # Max size you want to process in one loop batch

    def __init__(self, input_filepath: str, auth_handle: str, auth_password: str):
        self.input_filepath = input_filepath
        self.auth_handle = auth_handle
        self.auth_password = auth_password
        self.client = Client()
        self.handles_to_process: List[str] = []
        self.already_following: Set[str] = set()
        self.handles_to_follow_final: List[str] = []
        # Handle -> DID mapping after resolution
        self.prospect_did_map: Dict[str, str] = {}

    def _load_handles(self) -> None:
        """Loads unique, non-zero keyword count handles from the input JSONL file."""
        prospects: List[Dict[str, Any]] = []
        logging.info(f"--- Loading and filtering handles from {self.input_filepath} ---")

        try:
            with open(self.input_filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record: Dict[str, Any] = json.loads(line.strip())
                        handle = record.get("handle")
                        if handle and record.get("total_keyword_count", 0) > 0:
                            prospects.append(record)
                    except json.JSONDecodeError:
                        logging.warning("Skipping malformed JSON line in input file.")

            prospects.sort(key=lambda x: x.get("total_keyword_count", 0), reverse=True)
            self.handles_to_process = [p['handle'] for p in prospects]

            logging.info(f"✅ Loaded {len(prospects)} unique prospects with positive keyword counts.")

        except FileNotFoundError:
            logging.error(f"❌ FATAL: Input file not found: {self.input_filepath}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"❌ Error during handle loading: {e}")
            sys.exit(1)

    def _fetch_all_prospect_dids(self) -> None:
        """
        Resolves all handles in self.handles_to_process into DIDs using app.bsky.actor.getProfiles.
        Stores handle -> DID in self.prospect_did_map and filters out failures.
        """
        logging.info("--- STEP 1.5: Resolving Handles to DIDs ---")

        handles = self.handles_to_process
        resolved_count = 0

        for i in range(0, len(handles), self.BATCH_SIZE):
            batch = handles[i:i + self.BATCH_SIZE]
            try:
                # Use the low-level namespace on the client
                # This call accepts params as a dict
                response = self.client.app.bsky.actor.get_profiles(
                    params={"actors": batch}
                )

                for profile in response.profiles:
                    self.prospect_did_map[profile.handle] = profile.did
                    resolved_count += 1

            except Exception as e:
                logging.warning(
                    f"⚠️ Failed to batch-resolve DIDs for a group of handles. Error: {e}"
                )

        logging.info(f"✅ Successfully resolved DIDs for {resolved_count}/{len(handles)} prospects.")
        # Keep only handles that were successfully resolved
        self.handles_to_process = list(self.prospect_did_map.keys())

    def _check_existing_follows(self) -> None:
        """
        Fetches all accounts the authenticated user already follows, compares against
        the prospect DID map, and builds the final list of new accounts to follow.
        """
        logging.info("--- STEP 2: Checking Current Follow Status (Full Follower List) ---")

        user_did = self.client.me.did
        followed_dids: Set[str] = set()
        cursor = None

        # Paginate over getFollows using the Client API.[web:14][web:11]
        while True:
            try:
                follows_response = self.client.app.bsky.graph.get_follows(
                    params={
                        "actor": user_did,
                        "limit": 100,
                        "cursor": cursor,
                    }
                )

                followed_dids.update({follow.did for follow in follows_response.follows})
                cursor = follows_response.cursor

                if not cursor:
                    break

            except Exception as e:
                logging.error(
                    f"❌ Failed to fetch full 'following' list. Stopping pagination early: {e}"
                )
                break

        logging.info(f"Successfully retrieved DIDs for {len(followed_dids)} accounts currently being followed.")

        # Check each prospect against the set of followed DIDs
        for handle in self.handles_to_process:
            prospect_did = self.prospect_did_map.get(handle)
            if prospect_did and prospect_did in followed_dids:
                self.already_following.add(handle)

        logging.info(f"Found {len(self.already_following)} accounts already followed. These will be skipped.")

        new_prospects = [
            h for h in self.handles_to_process
            if h not in self.already_following
        ]

        self.handles_to_follow_final = new_prospects[:self.MAX_FOLLOWS]
        logging.info(f"Will attempt to follow {len(self.handles_to_follow_final)} *new* accounts.")

    def _log_action(self, handle: str, status: str, result_uri: str = "N/A") -> None:
        """Writes a time-stamped log entry."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = (
            f"ACTION: FOLLOW | TIME: {timestamp} | HANDLE: @{handle} | "
            f"STATUS: {status} | URI: {result_uri}"
        )
        logging.info(log_entry)

    def run_follows(self) -> None:
        """Authenticates, loads handles, filters, and executes the follow sequence."""
        if not os.path.exists(self.input_filepath):
            logging.error(f"FATAL: Input file not found: {self.input_filepath}")
            return

        self._load_handles()

        logging.info("--- STEP 1: Authenticating ---")
        try:
            self.client.login(self.auth_handle, self.auth_password)
            logging.info("✅ Authentication successful.")
        except Exception as e:
            logging.error(f"❌ FATAL AUTHENTICATION ERROR. Check credentials: {e}")
            return

        # Resolve DIDs for all prospects
        self._fetch_all_prospect_dids()

        # Check existing follows
        self._check_existing_follows()

        if not self.handles_to_follow_final:
            logging.info("No new accounts to follow after filtering. Exiting.")
            return

        logging.info("\n--- STEP 3: Executing Follow Sequence ---")

        newline = '\n'

        for i, handle in enumerate(self.handles_to_follow_final):

            try:
                logging.info(f"Attempting follow {i + 1}/{len(self.handles_to_follow_final)} for @{handle}...")

                target_did = self.prospect_did_map.get(handle)

                if not target_did:
                    self._log_action(handle, "FAILURE: DID Lookup Failed", "N/A")
                    continue

                # follow() expects the DID of the target.[web:11]
                response = self.client.follow(target_did)

                if isinstance(response, AtUri) and response.uri:
                    self._log_action(handle, "SUCCESS", response.uri)
                else:
                    self._log_action(handle, "SUCCESS (Generic/Unexpected Response)")

            except AtProtocolError as e:
                self._log_action(handle, f"FAILURE: AT Protocol Error - {str(e).split(';')[0]}")
            except Exception as e:
                self._log_action(handle, f"FAILURE: Python Exception - {str(e).split(newline)[0]}")

            if i < len(self.handles_to_follow_final) - 1:
                logging.info(f"Pausing for {self.DELAY_SECONDS} seconds...")
                time.sleep(self.DELAY_SECONDS)

        print("\n" + "=" * 60)
        print(f"🎉 Follow sequence complete. {len(self.handles_to_follow_final)} new accounts targeted.")
        print(f"Check '{LOG_FILE}' for full details.")
        print("=" * 60)


if __name__ == "__main__":

    # --- CONFIGURATION ---
    INPUT_FILE = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/prospects/to_follow_12-12-2025.jsonl"
    AUTH_HANDLE = "vegansearchengine.bsky.social"
    APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD")

    if not APP_PASSWORD:
        logging.error("FATAL: Environment variable 'BLUESKY_APP_PASSWORD' not set.")
        sys.exit(1)

    try:
        follower = BulkFollower(
            input_filepath=INPUT_FILE,
            auth_handle=AUTH_HANDLE,
            auth_password=APP_PASSWORD
        )

        follower.run_follows()

    except Exception as e:
        logging.critical(f"A critical error occurred during execution: {e}")

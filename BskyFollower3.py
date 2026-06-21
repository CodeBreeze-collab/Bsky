import json
import logging
import sys
import os
import argparse
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
import random


# --- ROBUST ATPROTO IMPORTS ---
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
    print("FATAL: Could not import 'atproto'. Install it via: pip install atproto")
    sys.exit(1)

# Set logging to INFO by default (change to DEBUG to see skip reasons)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyFollower:
    def __init__(self, username: str, password: str, log_file_path: str, dry_run_path: str,
                 request_delay_seconds: int = 5):
        self.client = Client()
        self.username = username
        self.password = password
        self.log_file_path = Path(log_file_path)
        self.dry_run_path = Path(dry_run_path)
        self.session_did: Optional[str] = None
        self.handle_to_did_cache = {}
        # Load existing follows from log immediately
        self.followed_dids: Set[str] = self._load_followed_dids()
        logging.info(f"Loaded {len(self.followed_dids)} previously-followed DIDs")
        self.request_delay = request_delay_seconds

    def _load_followed_dids(self) -> Set[str]:
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

    def resolve_handle_to_did(self, handle: str) -> Optional[str]:
        if handle in self.handle_to_did_cache:
            return self.handle_to_did_cache[handle]
        try:
            response = self.client.resolve_handle(handle)
            did = response.did
            self.handle_to_did_cache[handle] = did
            return did
        except Exception as e:
            logging.error(f"Failed to resolve handle @{handle}: {e}")
            return None

    def perform_cross_check(self):
        logging.info("--- STARTING CROSS-CHECK REPORT ---")

        def get_dids_from_file(path):
            dids = set()
            if Path(path).exists():
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            d = data.get('target_did') or data.get('did')
                            if d: dids.add(d)
                        except:
                            continue
            return dids

        dry_run_dids = get_dids_from_file(self.dry_run_path)
        followed_dids = get_dids_from_file(self.log_file_path)
        to_be_followed = dry_run_dids - followed_dids

        print(f"\n[!] UNIQUE TO DRY RUN (Not followed yet): {len(to_be_followed)}")
        if to_be_followed:
            print(f"    (Sample DIDs: {list(to_be_followed)[:3]})")
        print("\n" + "-" * 35)
        time.sleep(1)

    def _log_follow_result(self, target_handle: str, target_did: str, success: bool):
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        log_entry = {
            "timestamp": timestamp,
            "target_handle": target_handle or "N/A",
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
            logging.error(f"Failed to write log: {e}")

    def login(self) -> bool:
        logging.info(f"Attempting login for: {self.username}")

        # Security check: Ensure we aren't sending an empty string
        if not self.password:
            logging.error("Login aborted: Password/App Password is empty or None.")
            return False

        try:
            # The .login() method returns a Session object on success
            profile = self.client.login(self.username, self.password)
            self.session_did = profile.did
            logging.info(f"Login successful. Session DID: {self.session_did}")
            return True

        except Exception as e:
            # Identify specific failure types
            error_msg = str(e).lower()
            if "authentication failed" in error_msg or "invalid identifier" in error_msg:
                logging.error(f"AUTH ERROR: Check if your handle ({self.username}) or App Password is correct.")
            elif "rate limit" in error_msg:
                logging.error("RATE LIMIT: Bluesky is temporarily blocking login attempts from this IP.")
            else:
                logging.error(f"UNEXPECTED LOGIN FAILURE: {type(e).__name__}: {e}")

            # Suggesting the most common fix
            if not self.password.startswith("xxxx-"):  # App passwords usually follow a hyphenated format
                logging.warning(
                    "HINT: Ensure you are using an 'App Password' from Settings -> Advanced -> App Passwords, NOT your main Bluesky password.")

            return False

    def process_records(self, dry_run_records: List[Dict[str, Any]]):
        if not self.session_did:
            logging.error("Not logged in.")
            return

        to_follow_queue = []
        logging.info(f"Analyzing {len(dry_run_records)} records...")

        skip_stats = {
            "no_did": 0,
            "already_followed": 0,
            "duplicate_in_run": 0,
            "queued": 0
        }

        for record in dry_run_records:
            handle = record.get('handle')
            did = record.get('target_did') or record.get('did')

            if not did and handle:
                did = self.resolve_handle_to_did(handle)

            if not did:
                skip_stats["no_did"] += 1
                logging.debug(f"SKIP no DID | record={record}")
                continue

            if did in self.followed_dids:
                skip_stats["already_followed"] += 1
                logging.debug(f"SKIP already followed | did={did}")
                continue

            if not any(item[1] == did for item in to_follow_queue):
                display = handle if handle else f"DID:{did[:15]}..."
                to_follow_queue.append((display, did))
                skip_stats["queued"] += 1
            else:
                skip_stats["duplicate_in_run"] += 1

        logging.info(
            "Skip summary | "
            f"queued={skip_stats['queued']} | "
            f"already_followed={skip_stats['already_followed']} | "
            f"no_did={skip_stats['no_did']} | "
            f"duplicate_in_run={skip_stats['duplicate_in_run']}"
        )

        if not to_follow_queue:
            logging.info("✨ No unique accounts found to follow.")
            return

        logging.info(f"--- 🎯 TARGETING {len(to_follow_queue)} ACCOUNTS ---")
        for label, did in to_follow_queue[:10]:
            print(f"  - {label} ({did})")

        print("\nWaiting 5s before starting...")
        time.sleep(5)

        for i, (label, did) in enumerate(to_follow_queue):
            logging.info(f"[{i + 1}/{len(to_follow_queue)}] Following {label}")
            try:
                self.client.follow(did)
                logging.info("    ✅ Success")
                self._log_follow_result(label if "DID:" not in label else None, did, True)
            except Exception as e:
                logging.error(f"    ❌ Failed: {e}")
                self._log_follow_result(None, did, False)

            if i < len(to_follow_queue) - 1:
                # Generates a multiplier between 0.8 and 1.2
                jitter = random.uniform(0.8, 1.2)
                actual_sleep = self.request_delay * jitter
                logging.info(f"Sleeping for {actual_sleep:.2f}s...")
                time.sleep(actual_sleep)

    def run(self):
        """Run the Bluesky follower sequence with robust JSONL loading and logging."""
        self.perform_cross_check()

        if not self.login():
            logging.error("Aborting run: login failed.")
            return

        records = []
        if self.dry_run_path.exists():
            logging.info(f"Loading dry-run records from {self.dry_run_path}")
            with self.dry_run_path.open('r', encoding='utf-8') as f:
                for lineno, line in enumerate(f, start=1):
                    stripped_line = line.strip()
                    if not stripped_line:
                        continue
                    try:
                        record = json.loads(stripped_line)
                        records.append(record)
                    except json.JSONDecodeError as e:
                        logging.error(
                            f"JSON decode error in {self.dry_run_path} at line {lineno}:\n"
                            f"    {stripped_line}\n"
                            f"    Error: {e}"
                        )
                    except Exception as e:
                        logging.error(
                            f"Unexpected error while parsing line {lineno} in {self.dry_run_path}:\n"
                            f"    {stripped_line}\n"
                            f"    Error: {e}"
                        )
            logging.info(f"Loaded {len(records)} valid records from {self.dry_run_path}")

        if not records:
            logging.warning("No records found to process. Exiting run.")
            return

        self.process_records(records)


# --- CLI EXECUTION ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    CONFIG_DIR = Path("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/all-in-one-configs/")
    config_path = CONFIG_DIR / args.config if not Path(args.config).is_absolute() else Path(args.config)

    with open(config_path, "r") as f:
        cfg = json.load(f)

    password = os.getenv(cfg["password_env_var"])
    # NEW DIAGNOSTIC LOGGING
    if not password:
        logging.critical(f"Env var '{cfg['password_env_var']}' not found in environment!")
        sys.exit(1)
    else:
        # Log the length and first/last char to verify it's loading the right string
        # without leaking the full secret in logs.
        masked_pw = f"{password[0]}***{password[-1]}" if len(password) > 2 else "***"
        logging.info(f"Credential Loaded: {cfg['password_env_var']} (Length: {len(password)}, Format: {masked_pw})")

    follower = BlueskyFollower(
        cfg["username"], password, cfg["log_file"], cfg["dry_run_file"],
        request_delay_seconds=cfg.get("request_delay_seconds", 15)
    )
    follower.run()
